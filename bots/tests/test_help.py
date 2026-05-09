import pytest

from bots.base import BotBase, BotMessage
from bots.builtin.help import HelpBot, format_help, format_help_for


class _FakeBot(BotBase):
    def __init__(self, name: str, desc: str = ""):
        super().__init__()
        self.name = name
        self.description = desc


def _msg(command="help", args=()):
    return BotMessage(
        from_id="!a", text=f"!{command}", command=command, args=list(args),
        channel=0, is_dm=False, ts=0,
    )


def test_format_help_lists_each_bot_with_prefix():
    out = format_help("!", [_FakeBot("ping"), _FakeBot("nodes")])
    assert out == "Comandi: !ping !nodes"


def test_format_help_empty_when_no_bots_enabled():
    assert "Nessun bot abilitato" in format_help("!", [])


def test_format_help_for_known_command():
    bots = [_FakeBot("nodes", desc="elenca nodi")]
    out = format_help_for("!", bots, "nodes")
    assert out == "!nodes: elenca nodi"


def test_format_help_for_strips_prefix_in_arg():
    bots = [_FakeBot("nodes", desc="x")]
    out = format_help_for("!", bots, "!nodes")
    assert "!nodes:" in out


def test_format_help_for_unknown_command():
    out = format_help_for("!", [_FakeBot("ping")], "missing")
    assert "sconosciuto" in out


@pytest.mark.asyncio
async def test_help_bot_with_no_args_returns_summary():
    bots = [_FakeBot("ping"), _FakeBot("status")]
    h = HelpBot(get_state=lambda: ("!", bots))
    out = list(await h.on_message(_msg(command="help")))
    assert len(out) == 1
    assert "Comandi:" in out[0].text
    assert "!ping" in out[0].text


@pytest.mark.asyncio
async def test_help_bot_with_arg_returns_detail():
    bots = [_FakeBot("ping", desc="risponde a !ping")]
    h = HelpBot(get_state=lambda: ("!", bots))
    out = list(await h.on_message(_msg(command="help", args=["ping"])))
    assert "risponde a !ping" in out[0].text


@pytest.mark.asyncio
async def test_help_bot_ignores_other_commands():
    h = HelpBot(get_state=lambda: ("!", []))
    out = list(await h.on_message(_msg(command="ping")))
    assert out == []
