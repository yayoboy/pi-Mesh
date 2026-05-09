"""beacon → periodic broadcast of local node name + position + battery.

Pure on-tick bot: doesn't react to text messages, just emits a single
``BotReply`` every ``interval_seconds``. Time-keeping uses the timestamp
passed by the runner to ``on_tick``, so tests can advance time
deterministically.
"""

from __future__ import annotations

from typing import Callable, Iterable

from bots.base import BotBase, BotMessage, BotReply


def format_beacon(local: dict) -> str:
    """Render the broadcast text from the local node dict (or {})."""
    if not local:
        return "beacon: nodo locale sconosciuto"
    name = local.get("short_name") or local.get("id") or "?"
    bits = [f"📡 {name}"]
    lat = local.get("latitude")
    lon = local.get("longitude")
    if lat is not None and lon is not None:
        bits.append(f"{lat:.4f},{lon:.4f}")
    batt = local.get("battery_level")
    if batt is not None:
        bits.append(f"🔋{batt}%")
    return " · ".join(bits)


class BeaconBot(BotBase):
    name = "beacon"
    description = "Broadcast periodico con nome / posizione / batteria del nodo locale."
    default_enabled = False  # opt-in: noisy on busy networks
    config_schema = {
        "interval_seconds": ("int", 600, "Periodo (s)"),
    }

    def __init__(self, get_local_node: Callable[[], dict | None],
                 get_interval: Callable[[], int]):
        super().__init__()
        self._get_local = get_local_node
        self._get_interval = get_interval
        self._next_tick_ts: int | None = None

    async def on_tick(self, now: int) -> Iterable[BotReply]:
        if self._next_tick_ts is None:
            # First call: arm the timer for the next interval, no broadcast yet.
            self._next_tick_ts = now + max(10, int(self._get_interval()))
            return ()
        if now < self._next_tick_ts:
            return ()
        self._next_tick_ts = now + max(10, int(self._get_interval()))
        local = self._get_local() or {}
        return (BotReply(text=format_beacon(local), to="^all", channel=0),)
