import pytest

from bots.base import BotMessage
from bots.builtin.status import StatusBot, format_status, _fmt_uptime


def _msg(command="status"):
    return BotMessage(
        from_id="!a", text=f"!{command}", command=command, args=[],
        channel=0, is_dm=False, ts=0,
    )


# -- _fmt_uptime ----------------------------------------------------------

def test_fmt_uptime_minutes():
    assert _fmt_uptime(60) == "1m"
    assert _fmt_uptime(59 * 60) == "59m"


def test_fmt_uptime_hours_then_minutes():
    assert _fmt_uptime(3600 + 60) == "1h1m"


def test_fmt_uptime_days_then_hours():
    assert _fmt_uptime(86400 + 3600) == "1d1h"


def test_fmt_uptime_none_returns_dash():
    assert _fmt_uptime(None) == "—"


# -- format_status --------------------------------------------------------

def test_format_status_full_payload():
    out = format_status({
        "cpu_percent": 23.4, "ram_percent": 67.0,
        "cpu_temp": 51.6, "uptime_seconds": 90061,
    })
    assert "CPU 23%" in out
    assert "RAM 67%" in out
    assert "52°C" in out
    assert "1d1h" in out


def test_format_status_partial_payload_uses_dashes():
    out = format_status({})
    assert "CPU —" in out
    assert "RAM —" in out
    assert "—°C" in out
    assert "up —" in out


# -- StatusBot ------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_bot_returns_formatted_line():
    bot = StatusBot(collect_telemetry=lambda: {"cpu_percent": 10, "ram_percent": 20})
    out = list(await bot.on_message(_msg()))
    assert "CPU 10%" in out[0].text


@pytest.mark.asyncio
async def test_status_bot_swallows_collect_exception():
    def boom() -> dict:
        raise RuntimeError("no /proc")

    bot = StatusBot(collect_telemetry=boom)
    out = list(await bot.on_message(_msg()))
    assert len(out) == 1
    assert "CPU —" in out[0].text


@pytest.mark.asyncio
async def test_status_bot_ignores_other_commands():
    bot = StatusBot(collect_telemetry=lambda: {})
    out = list(await bot.on_message(_msg(command="ping")))
    assert out == []
