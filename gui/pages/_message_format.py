"""Pure formatter for the messages list. Extracted for unit-testability."""

from __future__ import annotations

import time


def format_message(msg: dict, *, now: int | None = None) -> str:
    """Render a message row as a single line.

    Format: ``[age] src: text [✓]``
    - age is "Ns", "Nm", "Nh", or "Nd" relative to ``now``.
    - src is "me" for outgoing, otherwise the node id / "?" if missing.
    - "✓" suffix appears only on outgoing messages with ack truthy.
    """
    ts = msg.get("ts") or 0
    if ts:
        ref = now if now is not None else int(time.time())
        delta = max(0, ref - int(ts))
        if delta < 60:
            age = f"{delta}s"
        elif delta < 3600:
            age = f"{delta // 60}m"
        elif delta < 86400:
            age = f"{delta // 3600}h"
        else:
            age = f"{delta // 86400}d"
    else:
        age = "—"
    src = "me" if msg.get("is_outgoing") else (msg.get("node_id") or "?")
    text = (msg.get("text") or "").replace("\n", " ").strip()
    ack = " ✓" if msg.get("is_outgoing") and msg.get("ack") else ""
    return f"[{age}] {src}: {text}{ack}"
