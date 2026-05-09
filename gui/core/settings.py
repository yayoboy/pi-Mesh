"""In-memory settings cache backed by the SQLite ``settings`` table.

Also exposes a tiny pub-sub for keys the GUI cares about (``display.theme``,
``pimesh-accent``, ``pimesh-custom-theme``) so the theme can hot-reload when
the user changes it from the Config page.


The Qt GUI runs on the same asyncio loop as uvicorn (qasync). That loop is the
GUI thread, so calling ``await database.get_setting`` from a Qt slot is not
ergonomic — slots are sync and cannot await.

Solution: load all settings into memory once at startup (``await load()``),
expose them via sync ``get`` / ``set``, and persist writes asynchronously by
scheduling a ``create_task`` on the running loop. Writes are best-effort:
the in-memory value is always consistent, the DB catches up on the next loop
tick.

Tests cover the cache logic without requiring a real DB by injecting fake
``loader`` / ``saver`` callables. Integration with ``database.py`` is wired in
``init_from_database()`` and exercised on the Pi at runtime.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Iterable, List

log = logging.getLogger(__name__)


# Type aliases for the dependency-injection points used by tests.
Loader = Callable[[Iterable[str]], Awaitable[dict[str, str]]]
Saver = Callable[[str, str], Awaitable[None]]


class Settings:
    """In-memory cache of GUI-side settings, with async write-through."""

    def __init__(self, saver: Saver, loop: asyncio.AbstractEventLoop | None = None):
        self._cache: dict[str, str] = {}
        self._saver = saver
        self._loop = loop
        self._pending_writes: set[asyncio.Task] = set()
        # key -> list of subscribers; called sync after every set().
        self._subscribers: dict[str, list[Callable[[str | None], None]]] = {}

    async def load(self, loader: Loader, keys: Iterable[str]) -> None:
        """Populate the cache by calling ``loader(keys)`` once."""
        values = await loader(keys)
        self._cache.update(values)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._cache.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Update the cache, schedule a DB write, fire subscribers.

        If no loop is set or running, the write is dropped with a warning;
        the cache and subscribers are still updated so the GUI stays
        consistent even if persistence fails.
        """
        self._cache[key] = value
        for cb in self._subscribers.get(key, ()):
            try:
                cb(value)
            except Exception:
                log.exception("Settings subscriber for %r failed", key)
        loop = self._loop or self._running_loop()
        if loop is None:
            log.warning("Settings.set(%r): no loop available, write dropped", key)
            return
        task = loop.create_task(self._saver(key, value))
        self._pending_writes.add(task)
        task.add_done_callback(self._on_write_done)

    def subscribe(self, key: str, callback: Callable[[str | None], None]) -> None:
        """Register a sync callback fired immediately on every ``set(key, …)``.

        The callback receives the new value. There is no unsubscribe — the
        whole cache is owned by the app and lives until shutdown.
        """
        self._subscribers.setdefault(key, []).append(callback)

    def _on_write_done(self, task: asyncio.Task) -> None:
        self._pending_writes.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.warning("Settings write failed: %s", exc)

    @staticmethod
    def _running_loop() -> asyncio.AbstractEventLoop | None:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    async def flush(self) -> None:
        """Wait for all pending writes to complete (used at shutdown / in tests)."""
        if self._pending_writes:
            await asyncio.gather(*self._pending_writes, return_exceptions=True)


# --- Module-level singleton wired against database.py at runtime -------------

_singleton: Settings | None = None


# Settings keys that the GUI needs at startup. Add new ones here as features land.
_GUI_SETTINGS_KEYS: tuple[str, ...] = (
    "display.theme",
    "display.brightness",
    "display.rotation",
    "pimesh-accent",
    "pimesh-custom-theme",
)


async def init_from_database(db_path: str) -> Settings:
    """Build the singleton, load known keys from ``database.py``, return it."""
    import database

    async def loader(keys: Iterable[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k in keys:
            v = await database.get_setting(k, default=None)
            if v is not None:
                out[k] = v
        return out

    async def saver(key: str, value: str) -> None:
        await database.set_setting(key, value)

    s = Settings(saver=saver, loop=asyncio.get_running_loop())
    await s.load(loader, _GUI_SETTINGS_KEYS)
    global _singleton
    _singleton = s
    return s


def get_settings() -> Settings:
    """Return the global ``Settings`` instance, raising if not initialised."""
    if _singleton is None:
        raise RuntimeError("Settings not initialised: call init_from_database() first")
    return _singleton
