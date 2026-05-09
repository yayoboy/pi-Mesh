"""Async runner that wires the bots into ``meshtasticd_client``.

Lifecycle (mirrors ``mqtt_bridge``):

  await start(db_path)        # called from main.py:lifespan
  ...
  reload_config()             # idempotent, called when settings change
  ...
  await stop()                # cancel tasks, unsubscribe queue

The runner owns:
- a ``BotsConfig`` snapshot
- a list of bot instances
- one asyncio task draining the meshtasticd_client event queue
- one asyncio task that calls ``on_tick`` every TICK_SECONDS
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Iterable

from bots.base import BotBase, BotMessage, BotReply, resolve_destination
from bots.config import BotsConfig
from bots.parser import parse_command

log = logging.getLogger(__name__)


TICK_SECONDS = 60
DEFAULT_BEACON_INTERVAL = 600


class _RunnerState:
    """Module-level singleton so main.py / API / GUI can talk to one runner."""

    config: BotsConfig | None = None
    bots: list[BotBase] = []
    queue: asyncio.Queue | None = None
    msg_task: asyncio.Task | None = None
    tick_task: asyncio.Task | None = None
    started: bool = False


_state = _RunnerState()


# -- bot factory ----------------------------------------------------------

def _build_bots(config: BotsConfig) -> list[BotBase]:
    """Construct all built-ins, wiring their data sources."""
    import meshtasticd_client
    import rpi_telemetry
    from bots import build_default_bots

    def get_state() -> tuple[str, list[BotBase]]:
        # Live snapshot of (prefix, enabled bots). Used by HelpBot.
        return config.prefix, [b for b in _state.bots if config.is_enabled(b.name)]

    def get_beacon_interval() -> int:
        try:
            return int(config.get_param("beacon", "interval_seconds",
                                        str(DEFAULT_BEACON_INTERVAL)))
        except (TypeError, ValueError):
            return DEFAULT_BEACON_INTERVAL

    return build_default_bots(
        get_nodes=meshtasticd_client.get_nodes,
        get_local_node=meshtasticd_client.get_local_node,
        collect_telemetry=rpi_telemetry.collect,
        get_state=get_state,
        get_beacon_interval=get_beacon_interval,
    )


# -- public API -----------------------------------------------------------

async def start(db_path: str) -> None:
    """Initialize config, build bots, subscribe to events, spawn tasks."""
    if _state.started:
        return
    from bots import DEFAULT_ENABLED
    import meshtasticd_client

    cfg = BotsConfig(db_path)
    await cfg.load(DEFAULT_ENABLED)
    _state.config = cfg
    _state.bots = _build_bots(cfg)
    _state.queue = meshtasticd_client.subscribe_events()
    loop = asyncio.get_running_loop()
    _state.msg_task = loop.create_task(_message_loop())
    _state.tick_task = loop.create_task(_tick_loop())
    _state.started = True
    log.info("bots runner started: prefix=%r, %d bots loaded",
             cfg.prefix, len(_state.bots))


async def stop() -> None:
    if not _state.started:
        return
    import meshtasticd_client

    for task in (_state.msg_task, _state.tick_task):
        if task is not None:
            task.cancel()
    await asyncio.gather(
        *(t for t in (_state.msg_task, _state.tick_task) if t is not None),
        return_exceptions=True,
    )
    if _state.queue is not None:
        meshtasticd_client.unsubscribe_events(_state.queue)
    _state.queue = None
    _state.msg_task = None
    _state.tick_task = None
    _state.bots = []
    _state.config = None
    _state.started = False
    log.info("bots runner stopped")


async def reload_config() -> None:
    """Re-read ``bots.*`` settings from the DB and rebuild bot instances."""
    if not _state.started or _state.config is None:
        return
    from bots import DEFAULT_ENABLED
    await _state.config.load(DEFAULT_ENABLED)
    _state.bots = _build_bots(_state.config)
    log.info("bots runner reloaded: prefix=%r, enabled=%s",
             _state.config.prefix,
             [b.name for b in _state.bots if _state.config.is_enabled(b.name)])


def get_state_snapshot() -> dict:
    """Read-only view used by the API to render the bots list."""
    if _state.config is None:
        return {"prefix": "", "bots": [], "running": False}
    return {
        "prefix": _state.config.prefix,
        "bots": [
            {"name": b.name, "description": b.description,
             "enabled": _state.config.is_enabled(b.name),
             "default_enabled": b.default_enabled}
            for b in _state.bots
        ],
        "running": _state.started,
    }


# -- message dispatch ----------------------------------------------------

def _build_bot_message(event: dict, prefix: str, local_id: str) -> BotMessage:
    text = event.get("text") or ""
    cmd, args = parse_command(text, prefix)
    return BotMessage(
        from_id=event.get("from") or event.get("id") or "?",
        text=text,
        command=cmd,
        args=args,
        channel=int(event.get("channel") or 0),
        is_dm=bool(event.get("is_dm")) or _is_dm_for_local(event, local_id),
        ts=int(event.get("ts") or time.time()),
    )


def _is_dm_for_local(event: dict, local_id: str) -> bool:
    # Fallback if the event upstream forgot to include is_dm.
    dest = event.get("destination") or event.get("to")
    return bool(dest and local_id and dest == local_id)


async def _message_loop() -> None:
    import meshtasticd_client

    assert _state.queue is not None and _state.config is not None
    while True:
        try:
            event = await _state.queue.get()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("bots runner: queue read failed")
            await asyncio.sleep(0.5)
            continue

        if event.get("type") != "message":
            continue
        try:
            local_id = meshtasticd_client.get_local_id() or ""
            msg = _build_bot_message(event, _state.config.prefix, local_id)
            # Skip our own outgoing echoes.
            if msg.from_id == local_id:
                continue
            await _dispatch_one(msg)
        except Exception:
            log.exception("bots runner: dispatch failed for event=%r", event)


async def _dispatch_one(msg: BotMessage) -> None:
    """Run every enabled bot's on_message in parallel and send the replies."""
    assert _state.config is not None
    enabled = [b for b in _state.bots if _state.config.is_enabled(b.name)]
    if not enabled:
        return
    results = await asyncio.gather(
        *(_safe_on_message(b, msg) for b in enabled),
        return_exceptions=False,
    )
    for replies in results:
        await _send_replies(replies, msg)


async def _safe_on_message(bot: BotBase, msg: BotMessage) -> Iterable[BotReply]:
    try:
        return list(await bot.on_message(msg)) or []
    except Exception:
        log.exception("bot %r raised on_message", bot.name)
        return []


# -- tick scheduler -------------------------------------------------------

async def _tick_loop() -> None:
    """Call on_tick on every enabled bot every TICK_SECONDS."""
    while True:
        try:
            await asyncio.sleep(TICK_SECONDS)
        except asyncio.CancelledError:
            raise
        if _state.config is None:
            continue
        enabled = [b for b in _state.bots if _state.config.is_enabled(b.name)]
        if not enabled:
            continue
        now = int(time.time())
        try:
            results = await asyncio.gather(
                *(_safe_on_tick(b, now) for b in enabled),
                return_exceptions=False,
            )
        except Exception:
            log.exception("bots runner: tick gather failed")
            continue
        for replies in results:
            await _send_replies(replies, _tick_origin(now))


def _tick_origin(now: int) -> BotMessage:
    """Synthesise a 'message' to feed resolve_destination for tick replies.

    Tick replies are typically broadcasts (channel 0), so the placeholder
    has is_dm=False and channel=0; bots that want a different routing can
    set ``BotReply.to`` / ``channel`` explicitly.
    """
    return BotMessage(
        from_id="!self", text="", command=None, args=[],
        channel=0, is_dm=False, ts=now,
    )


async def _safe_on_tick(bot: BotBase, now: int) -> Iterable[BotReply]:
    try:
        return list(await bot.on_tick(now)) or []
    except Exception:
        log.exception("bot %r raised on_tick", bot.name)
        return []


# -- send -----------------------------------------------------------------

async def _send_replies(replies: Iterable[BotReply], src: BotMessage) -> None:
    import meshtasticd_client

    for reply in replies:
        if not reply or not reply.text:
            continue
        to, channel = resolve_destination(reply, src)
        try:
            await meshtasticd_client.send_text(reply.text, to, channel=channel)
        except Exception:
            log.exception("bot reply send failed (to=%r ch=%d)", to, channel)
