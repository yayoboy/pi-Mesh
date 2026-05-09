"""!nodes → mesh node summary, !nodes !aabb → details for one node.

The data source is injected so the bot is testable without
``meshtasticd_client``.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable

from bots.base import BotBase, BotMessage, BotReply


_ACTIVE_WINDOW_SECONDS = 60 * 60  # 1 h


def _format_summary(nodes: list[dict], *, now: int | None = None) -> str:
    if not nodes:
        return "Nessun nodo conosciuto."
    ref = now if now is not None else int(time.time())
    active = sum(1 for n in nodes if (ref - (n.get("last_heard") or 0)) < _ACTIVE_WINDOW_SECONDS)
    return f"{len(nodes)} nodi · {active} attivi (ultima h)"


def _format_node_detail(node: dict, *, now: int | None = None) -> str:
    if not node:
        return "Nodo non trovato."
    ref = now if now is not None else int(time.time())
    name = node.get("short_name") or node.get("id") or "?"
    bits = [name]
    snr = node.get("snr")
    if snr is not None:
        bits.append(f"SNR {snr:+.1f}")
    batt = node.get("battery_level")
    if batt is not None:
        bits.append(f"{batt}%")
    hops = node.get("hop_count")
    if hops is not None:
        bits.append(f"{hops} hops")
    last = node.get("last_heard")
    if last:
        delta = max(0, ref - int(last))
        if delta < 60:
            age = f"{delta}s"
        elif delta < 3600:
            age = f"{delta // 60}m"
        elif delta < 86400:
            age = f"{delta // 3600}h"
        else:
            age = f"{delta // 86400}d"
        bits.append(age)
    return " · ".join(bits)


class NodesBot(BotBase):
    name = "nodes"
    description = "!nodes per il sommario, !nodes !aabb per i dettagli di un nodo."
    default_enabled = True

    def __init__(self, get_nodes: Callable[[], list[dict]]):
        super().__init__()
        self._get_nodes = get_nodes

    async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
        if not self.matches(msg, "nodes"):
            return ()
        nodes = self._get_nodes()
        if not msg.args:
            return (BotReply(text=_format_summary(nodes)),)
        target = msg.args[0]
        node = next((n for n in nodes if n.get("id") == target), None)
        return (BotReply(text=_format_node_detail(node or {})),)
