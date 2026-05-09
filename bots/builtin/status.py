"""!status → CPU/RAM/temp/uptime of the host Pi."""

from __future__ import annotations

from typing import Callable, Iterable

from bots.base import BotBase, BotMessage, BotReply


def _fmt_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    days = s // 86400
    hours = (s % 86400) // 3600
    minutes = (s % 3600) // 60
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


def format_status(data: dict) -> str:
    cpu = data.get("cpu_percent")
    ram = data.get("ram_percent")
    temp = data.get("cpu_temp")
    up = data.get("uptime_seconds")
    cpu_s = f"CPU {cpu:.0f}%" if isinstance(cpu, (int, float)) else "CPU —"
    ram_s = f"RAM {ram:.0f}%" if isinstance(ram, (int, float)) else "RAM —"
    temp_s = f"{temp:.0f}°C" if isinstance(temp, (int, float)) else "—°C"
    up_s = f"up {_fmt_uptime(up)}"
    return " · ".join([cpu_s, ram_s, temp_s, up_s])


class StatusBot(BotBase):
    name = "status"
    description = "Risponde con CPU/RAM/temperatura/uptime del Raspberry Pi."
    default_enabled = True

    def __init__(self, collect_telemetry: Callable[[], dict]):
        super().__init__()
        self._collect = collect_telemetry

    async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
        if not self.matches(msg, "status"):
            return ()
        try:
            data = self._collect() or {}
        except Exception:
            data = {}
        return (BotReply(text=format_status(data)),)
