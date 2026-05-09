import pytest

from bots.base import BotMessage
from bots.builtin.nodes import (
    NodesBot,
    _format_node_detail,
    _format_summary,
)


def _msg(args=()):
    return BotMessage(
        from_id="!a", text="!nodes", command="nodes", args=list(args),
        channel=0, is_dm=False, ts=0,
    )


def test_summary_empty_list():
    assert "Nessun nodo" in _format_summary([])


def test_summary_counts_active_within_one_hour():
    NOW = 1_000_000
    nodes = [
        {"id": "!a", "last_heard": NOW - 600},          # 10m → active
        {"id": "!b", "last_heard": NOW - 7200},         # 2h  → not active
        {"id": "!c", "last_heard": NOW},                # now → active
    ]
    out = _format_summary(nodes, now=NOW)
    assert out == "3 nodi · 2 attivi (ultima h)"


def test_node_detail_renders_known_fields():
    NOW = 1_000_000
    out = _format_node_detail(
        {"id": "!a", "short_name": "ALPHA",
         "snr": -3.5, "battery_level": 70, "hop_count": 2,
         "last_heard": NOW - 90},
        now=NOW,
    )
    assert "ALPHA" in out
    assert "SNR -3.5" in out
    assert "70%" in out
    assert "2 hops" in out
    assert "1m" in out


def test_node_detail_missing_node():
    assert "non trovato" in _format_node_detail({})


def test_node_detail_falls_back_to_id_when_no_short_name():
    out = _format_node_detail({"id": "!aabb"}, now=1)
    assert out.startswith("!aabb")


@pytest.mark.asyncio
async def test_nodes_bot_summary():
    NOW = 1_000_000
    fixture = [{"id": "!a", "last_heard": NOW - 100}]
    bot = NodesBot(get_nodes=lambda: fixture)
    out = list(await bot.on_message(_msg()))
    assert "1 nodi" in out[0].text


@pytest.mark.asyncio
async def test_nodes_bot_detail_lookup():
    fixture = [{"id": "!aabb", "short_name": "X", "battery_level": 50}]
    bot = NodesBot(get_nodes=lambda: fixture)
    out = list(await bot.on_message(_msg(args=["!aabb"])))
    assert "X" in out[0].text
    assert "50%" in out[0].text


@pytest.mark.asyncio
async def test_nodes_bot_detail_unknown_id():
    bot = NodesBot(get_nodes=lambda: [{"id": "!a"}])
    out = list(await bot.on_message(_msg(args=["!missing"])))
    assert "non trovato" in out[0].text


@pytest.mark.asyncio
async def test_nodes_bot_ignores_other_commands():
    bot = NodesBot(get_nodes=lambda: [])
    msg = BotMessage(from_id="!a", text="!ping", command="ping", args=[],
                     channel=0, is_dm=False, ts=0)
    assert list(await bot.on_message(msg)) == []
