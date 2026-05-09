import pytest

from bots.base import BotBase, BotMessage, BotReply, resolve_destination


def _msg(**kw):
    base = dict(
        from_id="!aabb", text="x", command=None, args=[],
        channel=0, is_dm=False, ts=0,
    )
    base.update(kw)
    return BotMessage(**base)


# --- BotMessage / BotReply construction ------------------------------------

def test_botmessage_is_frozen():
    m = _msg()
    with pytest.raises(Exception):
        m.text = "y"  # type: ignore[misc]


def test_botreply_defaults_are_none():
    r = BotReply(text="hi")
    assert r.to is None
    assert r.channel is None


# --- BotBase.matches -------------------------------------------------------

def test_matches_returns_true_for_listed_command():
    assert BotBase.matches(_msg(command="ping"), "ping")
    assert BotBase.matches(_msg(command="ping"), "ping", "pong")


def test_matches_false_when_command_none():
    assert BotBase.matches(_msg(command=None), "ping") is False


def test_matches_false_when_not_in_list():
    assert BotBase.matches(_msg(command="hello"), "ping") is False


# --- resolve_destination --------------------------------------------------

def test_resolve_dm_reply_routes_to_sender():
    msg = _msg(from_id="!sender", is_dm=True, channel=2)
    to, ch = resolve_destination(BotReply("hi"), msg)
    assert to == "!sender"
    assert ch == 2


def test_resolve_broadcast_reply_keeps_channel_and_uses_caret_all():
    msg = _msg(from_id="!sender", is_dm=False, channel=3)
    to, ch = resolve_destination(BotReply("hi"), msg)
    assert to == "^all"
    assert ch == 3


def test_resolve_explicit_to_overrides_auto_routing():
    msg = _msg(from_id="!sender", is_dm=True, channel=0)
    to, ch = resolve_destination(BotReply("hi", to="!other"), msg)
    assert to == "!other"
    assert ch == 0


def test_resolve_explicit_channel_overrides_source_channel():
    msg = _msg(from_id="!sender", is_dm=False, channel=0)
    to, ch = resolve_destination(BotReply("hi", channel=5), msg)
    assert to == "^all"
    assert ch == 5


# --- BotBase default behaviour --------------------------------------------

@pytest.mark.asyncio
async def test_botbase_default_on_message_returns_empty():
    class B(BotBase):
        name = "x"

    out = list(await B().on_message(_msg()))
    assert out == []


@pytest.mark.asyncio
async def test_botbase_default_on_tick_returns_empty():
    class B(BotBase):
        name = "x"

    out = list(await B().on_tick(now=0))
    assert out == []
