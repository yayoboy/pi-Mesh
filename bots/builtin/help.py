"""!help → list of currently-enabled bot commands.

Lazily reads the runner's enabled-bot registry through a callable
injected at construction time, so the help bot stays decoupled from
the global state.
"""

from __future__ import annotations

from typing import Callable, Iterable

from bots.base import BotBase, BotMessage, BotReply


def format_help(prefix: str, bots: list[BotBase]) -> str:
    """Render the help text given the prefix and the enabled-bot list.

    Pure helper so it can be unit-tested without a runner.
    """
    if not bots:
        return "Nessun bot abilitato."
    cmds = " ".join(f"{prefix}{b.name}" for b in bots if b.name)
    return f"Comandi: {cmds}"


def format_help_for(prefix: str, bots: list[BotBase], target: str) -> str:
    """Format the detail line for a single bot."""
    target = target.lower().lstrip(prefix)
    bot = next((b for b in bots if b.name == target), None)
    if bot is None:
        return f"Comando sconosciuto: {target}"
    return f"{prefix}{bot.name}: {bot.description}"


class HelpBot(BotBase):
    name = "help"
    description = "Mostra l'elenco comandi attivi (e dettaglio con !help <cmd>)."
    default_enabled = True

    def __init__(self, get_state: Callable[[], tuple[str, list[BotBase]]]):
        """``get_state`` returns ``(prefix, enabled_bots)`` at call time."""
        super().__init__()
        self._get_state = get_state

    async def on_message(self, msg: BotMessage) -> Iterable[BotReply]:
        if not self.matches(msg, "help"):
            return ()
        prefix, bots = self._get_state()
        if msg.args:
            return (BotReply(text=format_help_for(prefix, bots, msg.args[0])),)
        return (BotReply(text=format_help(prefix, bots)),)
