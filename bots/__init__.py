"""Bots package — see ``bots.runner`` for the lifecycle.

``build_default_bots(…)`` returns a fresh list of bot instances every
time it's called so the runner can rebuild them after a config reload.
Each factory closure injects its data dependencies (``meshtasticd_client``,
``rpi_telemetry``, …) so the bots themselves stay testable in
isolation — see ``bots/tests/`` for the pure unit tests.
"""

from __future__ import annotations

from typing import Callable

from bots.base import BotBase
from bots.builtin.beacon import BeaconBot
from bots.builtin.help import HelpBot
from bots.builtin.nodes import NodesBot
from bots.builtin.ping import PingBot
from bots.builtin.status import StatusBot


def build_default_bots(
    *,
    get_nodes: Callable[[], list[dict]],
    get_local_node: Callable[[], dict | None],
    collect_telemetry: Callable[[], dict],
    get_state: Callable[[], "tuple[str, list[BotBase]]"],
    get_beacon_interval: Callable[[], int],
) -> list[BotBase]:
    """Construct one instance of each built-in bot.

    Order of the returned list matters: it determines the order in which
    bots are dispatched and shown in the help/UI.
    """
    return [
        PingBot(),
        HelpBot(get_state=get_state),
        NodesBot(get_nodes=get_nodes),
        StatusBot(collect_telemetry=collect_telemetry),
        BeaconBot(get_local_node=get_local_node, get_interval=get_beacon_interval),
    ]


# Names + default-enabled flags, used by config.load() before instances exist.
DEFAULT_ENABLED: dict[str, bool] = {
    PingBot.name:   PingBot.default_enabled,
    HelpBot.name:   HelpBot.default_enabled,
    NodesBot.name:  NodesBot.default_enabled,
    StatusBot.name: StatusBot.default_enabled,
    BeaconBot.name: BeaconBot.default_enabled,
}


# Static metadata used by GUI / API to enumerate bots without instantiating
# them (no need for the data-source callbacks).
BOT_META: list[dict] = [
    {"name": cls.name, "description": cls.description, "default_enabled": cls.default_enabled}
    for cls in (PingBot, HelpBot, NodesBot, StatusBot, BeaconBot)
]


__all__ = ["build_default_bots", "DEFAULT_ENABLED", "BOT_META", "BotBase"]
