"""Pure formatter for telemetry rows on the Telemetry page."""

from __future__ import annotations

import json
import time


def fmt_age(ts: int | None, *, now: int | None = None) -> str:
    if not ts:
        return "—"
    ref = now if now is not None else int(time.time())
    delta = max(0, ref - int(ts))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def format_telemetry_row(row: dict, *, now: int | None = None, max_pairs: int = 8) -> str:
    """One-line summary of a telemetry row.

    Format: ``[age] ttype  k=v  k=v  …`` (max_pairs limits column count).
    Nested dict values are JSON-encoded inline so the line stays scannable.
    """
    age = fmt_age(row.get("ts"), now=now)
    ttype = row.get("ttype") or "?"
    data = row.get("data") or {}
    pairs = []
    for k, v in data.items():
        if isinstance(v, dict):
            v = json.dumps(v, separators=(",", ":"))
        pairs.append(f"{k}={v}")
    extra = "  ".join(pairs[:max_pairs])
    return f"[{age}] {ttype}  {extra}"
