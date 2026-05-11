"""Global keyboard shortcut manager.

Bindings are no longer hard-coded: they come from ``gui.keymap`` (which
merges user overrides from ``~/.config/pimesh/keymap.json`` with the
defaults). Each action has a stable ``action_id``; the user can rebind any
of them at runtime via the Config > Tasti UI, which calls
``ShortcutManager.set_binding(action_id, QKeySequence)``.

Why F1..F12 specifically: Qt's ``evdevkeyboard`` plugin (used by the
``linuxfb`` platform on the Pi) ships a built-in keymap that does not
cover F13..F24. Sticking to F1..F12 + a single Shift+F12 combo keeps the
defaults working out-of-the-box without a custom keymap file.

Why a module-level singleton (``get_instance``): the Config > Tasti UI
needs to reach the live ShortcutManager to update bindings; threading a
reference through every Page constructor would be invasive, so we expose
the manager via this module instead.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from gui.keymap import ACTIONS, load_keymap, save_keymap

if TYPE_CHECKING:
    from gui.main_window import MainWindow

log = logging.getLogger(__name__)

# See discussion in the file header: Qt linuxfb runs an internal evdev
# keyboard reader alongside our explicit `evdevkeyboard` generic plugin,
# so every key press fires twice. We dedup at the application layer.
_DEBOUNCE_SECONDS = 0.5

_INSTANCE: "ShortcutManager | None" = None


def get_instance() -> "ShortcutManager | None":
    """Returns the live ShortcutManager (set when MainWindow.attach runs).

    Used by the Config > Tasti section to rebind shortcuts without a hard
    reference passed through Page constructors.
    """
    return _INSTANCE


class ShortcutManager:
    def __init__(self, window: "MainWindow"):
        global _INSTANCE
        self._window = window
        self._bindings: dict[str, QKeySequence] = load_keymap()
        self._shortcuts: dict[str, QShortcut] = {}
        self._handlers: dict[str, Callable[[], None]] = self._build_handlers()
        self._wire_all()
        _INSTANCE = self
        log.info("ShortcutManager: %d bindings registered", len(self._shortcuts))

    # ------------------------------------------------------------------
    # Handler table — one entry per action_id declared in gui.keymap.

    def _build_handlers(self) -> dict[str, Callable[[], None]]:
        w = self._window
        page_names = ["Nodi", "Mappa", "Msg", "Config", "Metriche", "Log"]
        page_slugs = ["nodi", "mappa", "msg", "config", "metriche", "log"]

        handlers: dict[str, Callable[[], None]] = {}
        for idx, (slug, name) in enumerate(zip(page_slugs, page_names)):
            def _switch(i=idx, n=name):
                log.warning("shortcut page %s", n)
                w._select_tab(i)
            handlers[f"page_{slug}"] = _switch

        handlers["telemetry"]  = self._wrap("telemetry",  w.show_telemetry)
        handlers["screenshot"] = self._wrap("screenshot", w.take_screenshot)
        handlers["rotation"]   = self._wrap("rotation",   w.show_rotation_menu)
        handlers["reboot"]     = self._wrap("reboot",     w.confirm_reboot)
        handlers["shutdown"]   = self._wrap("shutdown",   w.confirm_shutdown)
        handlers["toggle_vkb"] = self._wrap("toggle_vkb", w.toggle_vkb)
        handlers["cheatsheet"] = self._cheatsheet_placeholder
        return handlers

    # ------------------------------------------------------------------
    # Wiring

    def _wire_all(self) -> None:
        for action_id, _label, _default in ACTIONS:
            seq = self._bindings.get(action_id, QKeySequence())
            handler = self._handlers.get(action_id)
            if handler is None:
                log.warning("no handler registered for action %s", action_id)
                continue
            self._register(action_id, seq, handler)
            log.warning("wired %s -> %s", action_id, seq.toString())

    def _register(self, action_id: str, seq: QKeySequence, handler: Callable[[], None]) -> None:
        sc = QShortcut(seq, self._window)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        # See _DEBOUNCE_SECONDS for the why; autoRepeat doesn't help against
        # the double-source double-fire so we add a per-shortcut debounce.
        sc.setAutoRepeat(False)
        last = [0.0]
        def _debounced(h=handler):
            now = time.monotonic()
            if now - last[0] < _DEBOUNCE_SECONDS:
                return
            last[0] = now
            h()
        sc.activated.connect(_debounced)
        self._shortcuts[action_id] = sc

    # ------------------------------------------------------------------
    # Public API used by Config > Tasti

    def get_binding(self, action_id: str) -> QKeySequence:
        return self._bindings.get(action_id, QKeySequence())

    def all_bindings(self) -> dict[str, QKeySequence]:
        return dict(self._bindings)

    def set_binding(self, action_id: str, seq: QKeySequence) -> None:
        """Update the live QShortcut and persist the change to disk.

        Silently no-ops on unknown ``action_id`` so callers don't have to
        guard, and skips persist when the binding didn't actually change.
        """
        if action_id not in self._handlers:
            return
        if self._bindings.get(action_id) == seq:
            return
        self._bindings[action_id] = seq
        sc = self._shortcuts.get(action_id)
        if sc is not None:
            sc.setKey(seq)
        try:
            save_keymap(self._bindings)
        except Exception:
            log.exception("save_keymap failed for action %s", action_id)
        log.info("rebound %s -> %s", action_id, seq.toString())

    def reset_to_defaults(self) -> None:
        for action_id, _label, default in ACTIONS:
            self.set_binding(action_id, QKeySequence(default))

    # ------------------------------------------------------------------

    @staticmethod
    def _wrap(label: str, fn: Callable[[], None]) -> Callable[[], None]:
        def _runner():
            log.warning("shortcut %s", label)
            fn()
        return _runner

    def _cheatsheet_placeholder(self) -> None:
        # Renamed-for-history reasons only — actually shows the overlay now.
        log.warning("shortcut cheatsheet")
        try:
            from gui.widgets.cheatsheet import CheatsheetOverlay
            # If the overlay is already up, do nothing: re-pressing F1
            # while it's open feels like "toggle off", and the overlay's
            # own keyPressEvent handles that path via _dismiss.
            existing = self._window.findChild(CheatsheetOverlay)
            if existing is not None and existing.isVisible():
                return
            CheatsheetOverlay(self._window)
        except Exception:
            log.exception("cheatsheet overlay failed to open")
