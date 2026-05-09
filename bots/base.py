"""Bot framework primitives.

A bot is a subclass of :class:`BotBase` that returns zero or more
:class:`BotReply` objects from its ``on_message`` and/or ``on_tick``
hooks. The runner (``bots.runner``) is responsible for parsing inbound
text into :class:`BotMessage`, dispatching to enabled bots, and sending
the resulting replies back over the radio.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class BotMessage:
    """An incoming text packet, normalised for bot consumption."""

    from_id: str          # e.g. "!aabbccdd"
    text: str             # full original text
    command: str | None   # parsed command after prefix, e.g. "ping"; None if no prefix matched
    args: list[str]       # tokens after the command
    channel: int          # 0..7
    is_dm: bool           # True if the packet was addressed to the local node
    ts: int               # unix timestamp when received


@dataclass(frozen=True)
class BotReply:
    """One outbound message a bot wants the runner to send.

    - ``to=None`` → auto-route: DM the sender if the source was a DM,
      otherwise broadcast (``"^all"``).
    - ``channel=None`` → reply on the same channel the source was on.
    """

    text: str
    to: str | None = None
    channel: int | None = None


class BotBase(ABC):
    """Subclass and override ``on_message`` and/or ``on_tick``."""

    name: str = ""                  # unique snake_case id
    description: str = ""           # human one-liner
    default_enabled: bool = True
    config_schema: dict = {}        # {field: (kind, default, label)} — optional metadata for UI

    async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
        """Called for every text message. Default: no reply."""
        return ()

    async def on_tick(self, now: int) -> Iterable[BotReply]:
        """Called every TICK_SECONDS by the runner. Default: no reply."""
        return ()

    # -- helpers used by built-in bots ----------------------------------

    @classmethod
    def matches(cls, msg: BotMessage, *commands: str) -> bool:
        """True when ``msg.command`` is one of ``commands`` (lower-case)."""
        if not msg.command:
            return False
        return msg.command in commands


def resolve_destination(reply: BotReply, src: BotMessage) -> tuple[str, int]:
    """Decide where to actually send a reply.

    Pure helper extracted so the runner is testable without faking sends.
    """
    to = reply.to if reply.to is not None else (src.from_id if src.is_dm else "^all")
    channel = reply.channel if reply.channel is not None else src.channel
    return to, channel
