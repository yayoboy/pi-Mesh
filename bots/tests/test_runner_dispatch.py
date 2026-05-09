"""Unit tests for ``bots.runner`` internals that don't need the radio.

We exercise the pure helpers (``_build_bot_message``, ``_is_dm_for_local``,
``resolve_destination`` integration) and the dispatch fan-out via mock
bots — no asyncio.Queue, no meshtasticd_client.
"""

from __future__ import annotations

import time
from typing import Iterable

import pytest

from bots.base import BotBase, BotMessage, BotReply
from bots.runner import (
    _build_bot_message,
    _is_dm_for_local,
    _safe_on_message,
)


# --- _build_bot_message --------------------------------------------------

def test_build_bot_message_parses_command_with_prefix():
    NOW = int(time.time())
    event = {"type": "message", "text": "!ping arg1", "from": "!a",
             "channel": 2, "is_dm": False, "ts": NOW}
    msg = _build_bot_message(event, "!", local_id="!local")
    assert msg.command == "ping"
    assert msg.args == ["arg1"]
    assert msg.channel == 2
    assert msg.from_id == "!a"
    assert msg.is_dm is False


def test_build_bot_message_no_prefix_match_yields_command_none():
    event = {"type": "message", "text": "hello", "from": "!a"}
    msg = _build_bot_message(event, "!", local_id="!local")
    assert msg.command is None
    assert msg.args == []


def test_build_bot_message_uses_event_is_dm_first():
    event = {"type": "message", "text": "x", "is_dm": True, "from": "!a"}
    msg = _build_bot_message(event, "!", local_id="!local")
    assert msg.is_dm is True


def test_build_bot_message_falls_back_to_destination_match():
    event = {"type": "message", "text": "x", "from": "!a", "destination": "!local"}
    msg = _build_bot_message(event, "!", local_id="!local")
    assert msg.is_dm is True


def test_build_bot_message_channel_defaults_to_zero():
    event = {"type": "message", "text": "x", "from": "!a"}
    msg = _build_bot_message(event, "!", local_id="!local")
    assert msg.channel == 0


def test_build_bot_message_ts_defaults_to_now_if_missing():
    event = {"type": "message", "text": "x", "from": "!a"}
    before = int(time.time())
    msg = _build_bot_message(event, "!", local_id="!local")
    assert before <= msg.ts <= int(time.time()) + 1


# --- _is_dm_for_local ----------------------------------------------------

def test_is_dm_for_local_true_when_destination_matches():
    assert _is_dm_for_local({"destination": "!local"}, "!local") is True


def test_is_dm_for_local_false_when_destination_differs():
    assert _is_dm_for_local({"destination": "!other"}, "!local") is False


def test_is_dm_for_local_false_for_broadcast_marker():
    assert _is_dm_for_local({"destination": "^all"}, "!local") is False


def test_is_dm_for_local_false_when_local_id_missing():
    assert _is_dm_for_local({"destination": "!local"}, "") is False


# --- _safe_on_message ----------------------------------------------------

class _AlwaysReplies(BotBase):
    name = "always"
    async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
        return (BotReply(text="ok"),)


class _Raises(BotBase):
    name = "boom"
    async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
        raise RuntimeError("kaboom")


def _msg():
    return BotMessage(
        from_id="!a", text="x", command=None, args=[],
        channel=0, is_dm=False, ts=0,
    )


@pytest.mark.asyncio
async def test_safe_on_message_returns_replies():
    out = await _safe_on_message(_AlwaysReplies(), _msg())
    assert [r.text for r in out] == ["ok"]


@pytest.mark.asyncio
async def test_safe_on_message_swallows_exception():
    out = await _safe_on_message(_Raises(), _msg())
    assert list(out) == []


# --- end-to-end dispatch via _dispatch_one -----------------------------

@pytest.mark.asyncio
async def test_dispatch_runs_every_enabled_bot_and_sends_replies(monkeypatch):
    from bots import config as config_mod
    from bots import runner

    sent: list[tuple[str, str, int]] = []

    class _FakeMC:
        @staticmethod
        def get_local_id() -> str:
            return "!local"

        @staticmethod
        async def send_text(text, dest, channel=0):
            sent.append((text, dest, channel))

    monkeypatch.setitem(__import__("sys").modules, "meshtasticd_client", _FakeMC)

    class _Cfg:
        prefix = "!"

        def __init__(self):
            self._enabled = {"always": True, "boom": True, "off": False}

        def is_enabled(self, name: str) -> bool:
            return self._enabled.get(name, False)

    fake_cfg = _Cfg()

    class _OffBot(BotBase):
        name = "off"
        async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
            return (BotReply(text="should-not-send"),)

    monkeypatch.setattr(runner._state, "bots",
                        [_AlwaysReplies(), _Raises(), _OffBot()])
    monkeypatch.setattr(runner._state, "config", fake_cfg)

    msg = BotMessage(
        from_id="!sender", text="!always", command="always", args=[],
        channel=3, is_dm=False, ts=0,
    )

    await runner._dispatch_one(msg)

    # AlwaysReplies → "ok" broadcast on channel 3.
    assert ("ok", "^all", 3) in sent
    # Raises → swallowed (no send).
    # Off bot → not invoked.
    assert all(t[0] != "should-not-send" for t in sent)
