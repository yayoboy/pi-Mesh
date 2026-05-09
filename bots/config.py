"""Database-backed config wrapper for the bots framework.

Reuses ``database.get_setting`` / ``database.set_setting`` so we don't
duplicate schema. Exposes the small surface the runner and the GUI
need: prefix, per-bot enabled flag, opaque per-bot params, plus a
``subscribe(callback)`` so the runner can react to config changes
without restarting.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


PREFIX_KEY = "bots.prefix"
DEFAULT_PREFIX = "!"


def enabled_key(name: str) -> str:
    return f"bots.{name}.enabled"


def param_key(name: str, field: str) -> str:
    return f"bots.{name}.{field}"


class BotsConfig:
    """In-memory snapshot of bots.* settings, refreshable from the DB."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._cache: dict[str, str] = {}
        self._listeners: list[Callable[[], None]] = []

    # -- load / save ---------------------------------------------------

    async def load(self, default_enabled: dict[str, bool]) -> None:
        """Read all known bots.* keys into the in-memory cache.

        ``default_enabled`` is ``{name: bool}`` from the bot registry; used
        only as a fallback when the DB has no value for ``bots.<name>.enabled``.
        """
        import database

        prefix = await database.get_setting(PREFIX_KEY, DEFAULT_PREFIX)
        self._cache[PREFIX_KEY] = prefix or DEFAULT_PREFIX

        for name, default in default_enabled.items():
            key = enabled_key(name)
            value = await database.get_setting(key, None)
            if value is None:
                value = "1" if default else "0"
            self._cache[key] = str(value)

    async def set(self, key: str, value: str) -> None:
        import database
        self._cache[key] = str(value)
        await database.set_setting(key, str(value))
        self._fire_listeners()

    # -- queries -------------------------------------------------------

    @property
    def prefix(self) -> str:
        return self._cache.get(PREFIX_KEY, DEFAULT_PREFIX) or DEFAULT_PREFIX

    def is_enabled(self, name: str) -> bool:
        return self._cache.get(enabled_key(name), "0") == "1"

    def get_param(self, name: str, field: str, default: str = "") -> str:
        return self._cache.get(param_key(name, field), default) or default

    # -- pub-sub -------------------------------------------------------

    def subscribe(self, callback: Callable[[], None]) -> None:
        """Register a sync callback fired after every ``set()``."""
        self._listeners.append(callback)

    def _fire_listeners(self) -> None:
        for cb in self._listeners:
            try:
                cb()
            except Exception:
                log.exception("BotsConfig subscriber failed")

    # -- helpers used by the GUI / API -------------------------------

    async def set_enabled(self, name: str, enabled: bool) -> None:
        await self.set(enabled_key(name), "1" if enabled else "0")

    async def set_prefix(self, prefix: str) -> None:
        await self.set(PREFIX_KEY, prefix or DEFAULT_PREFIX)
