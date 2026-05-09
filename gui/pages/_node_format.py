"""Pure-Python formatters for the Nodes page table.

Extracted so they can be unit-tested without importing Qt; the page widget
calls into here from ``data()``.
"""

from __future__ import annotations

import time


def fmt_age(last_heard: int | None, *, now: int | None = None) -> str:
    """Human age (e.g. "12s", "3m", "5h", "2d") for a unix timestamp."""
    if not last_heard:
        return "—"
    ref = now if now is not None else int(time.time())
    delta = max(0, ref - int(last_heard))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def fmt_node(node: dict, key: str, *, now: int | None = None) -> str:
    """Format a single column value from a node dict."""
    if key == "short":
        return node.get("short_name") or "?"
    if key == "long":
        return node.get("long_name") or ""
    if key == "snr":
        v = node.get("snr")
        return f"{v:.1f}" if v is not None else "—"
    if key == "batt":
        v = node.get("battery_level")
        return f"{v}%" if v is not None else "—"
    if key == "hops":
        v = node.get("hop_count")
        return str(v) if v is not None else "—"
    if key == "dist":
        v = node.get("distance_km")
        if v is None:
            return "—"
        return f"{v:.1f}" if v >= 1 else f"{v * 1000:.0f} m"
    if key == "seen":
        return fmt_age(node.get("last_heard"), now=now)
    return ""
