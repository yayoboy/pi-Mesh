"""!ping → pong (with one-way RTT estimate based on the packet timestamp)."""

from __future__ import annotations

import time
from typing import Iterable

from bots.base import BotBase, BotMessage, BotReply


class PingBot(BotBase):
    name = "ping"
    description = "Risponde a !ping con 'pong' e RTT one-way (ms)."
    default_enabled = True

    async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
        if not self.matches(msg, "ping"):
            return ()
        # The radio packet ts is in seconds; convert to ms relative to now.
        rtt_ms = max(0, int((time.time() - msg.ts) * 1000)) if msg.ts else None
        suffix = f" (one-way ~{rtt_ms} ms)" if rtt_ms is not None else ""
        return (BotReply(text=f"pong{suffix}"),)
