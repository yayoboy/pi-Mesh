import pytest

from bots.builtin.beacon import BeaconBot, format_beacon


def test_format_beacon_full():
    out = format_beacon({
        "short_name": "ME", "latitude": 41.9, "longitude": 12.5, "battery_level": 80,
    })
    assert "ME" in out
    assert "41.9000,12.5000" in out
    assert "80%" in out


def test_format_beacon_minimal():
    out = format_beacon({"id": "!aabb"})
    assert "!aabb" in out
    assert "," not in out  # no coords


def test_format_beacon_empty():
    out = format_beacon({})
    assert "sconosciuto" in out


@pytest.mark.asyncio
async def test_beacon_first_tick_arms_no_broadcast():
    bot = BeaconBot(get_local_node=lambda: {"short_name": "X"},
                    get_interval=lambda: 60)
    out = list(await bot.on_tick(now=0))
    assert out == []


@pytest.mark.asyncio
async def test_beacon_emits_after_interval_elapsed():
    bot = BeaconBot(get_local_node=lambda: {"short_name": "X", "battery_level": 50},
                    get_interval=lambda: 60)
    # Arm.
    await bot.on_tick(now=0)
    # Half-way: still nothing.
    assert list(await bot.on_tick(now=30)) == []
    # Elapsed: one broadcast.
    out = list(await bot.on_tick(now=60))
    assert len(out) == 1
    assert "X" in out[0].text
    assert "50%" in out[0].text
    assert out[0].to == "^all"


@pytest.mark.asyncio
async def test_beacon_resets_after_each_emit():
    bot = BeaconBot(get_local_node=lambda: {"short_name": "X"},
                    get_interval=lambda: 60)
    await bot.on_tick(now=0)
    await bot.on_tick(now=60)  # emits
    # Right after, no further emit until next interval.
    assert list(await bot.on_tick(now=70)) == []
    assert list(await bot.on_tick(now=120)) != []


@pytest.mark.asyncio
async def test_beacon_clamps_too_short_interval():
    bot = BeaconBot(get_local_node=lambda: {"short_name": "X"},
                    get_interval=lambda: 1)
    await bot.on_tick(now=0)  # arms with min(10, …)
    # 5s elapsed: still no emit because interval is clamped to >= 10s.
    assert list(await bot.on_tick(now=5)) == []
    assert list(await bot.on_tick(now=10)) != []
