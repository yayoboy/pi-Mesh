import time

import pytest

from bots.base import BotMessage
from bots.builtin.ping import PingBot


def _msg(command="ping", ts=0):
    return BotMessage(
        from_id="!a", text=f"!{command}", command=command, args=[],
        channel=0, is_dm=False, ts=ts,
    )


@pytest.mark.asyncio
async def test_ping_returns_pong_with_rtt():
    bot = PingBot()
    out = list(await bot.on_message(_msg(ts=int(time.time()) - 1)))
    assert len(out) == 1
    assert out[0].text.startswith("pong")
    assert "ms" in out[0].text


@pytest.mark.asyncio
async def test_ping_without_ts_omits_rtt_suffix():
    bot = PingBot()
    out = list(await bot.on_message(_msg(ts=0)))
    assert out[0].text == "pong"


@pytest.mark.asyncio
async def test_ping_ignores_other_commands():
    bot = PingBot()
    out = list(await bot.on_message(_msg(command="status")))
    assert out == []
