"""Persistent, user-editable keyboard bindings.

Bindings live in ``~/.config/pimesh/keymap.json`` (or under
``$XDG_CONFIG_HOME``) and are loaded once at startup by ``ShortcutManager``.
If the file is missing, malformed, or an action_id has no entry, the
default key sequence wins, so a fresh install or a corrupted file never
breaks the keyboard.

The schema is intentionally flat: ``{action_id: "QKeySequence string"}``.
``QKeySequence.toString()`` and ``QKeySequence(str)`` round-trip cleanly,
which keeps the file human-editable for anyone who'd rather use vim than
the Config > Tasti UI.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from PySide6.QtGui import QKeySequence

log = logging.getLogger(__name__)


# (action_id, italian description shown in the UI, default key sequence).
# Order is the row order in the Config > Tasti section.
ACTIONS: list[tuple[str, str, str]] = [
    ("page_nodi",     "Pagina Nodi",       "F2"),
    ("page_mappa",    "Pagina Mappa",      "F3"),
    ("page_msg",      "Pagina Msg",        "F4"),
    ("page_config",   "Pagina Config",     "F5"),
    ("page_metriche", "Pagina Metriche",   "F6"),
    ("page_log",      "Pagina Log",        "F7"),
    ("telemetry",     "Telemetria",        "F8"),
    ("screenshot",    "Screenshot",        "F9"),
    ("rotation",      "Rotazione",         "F10"),
    ("reboot",        "Riavvio",           "F11"),
    ("shutdown",      "Spegnimento",       "F12"),
    ("toggle_vkb",    "Tastiera on/off",   "Shift+F12"),
    ("cheatsheet",    "Cheatsheet",        "F1"),
]


def default_keymap_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "pimesh" / "keymap.json"


def load_keymap(path: Path | None = None) -> dict[str, QKeySequence]:
    """Return a complete mapping ``action_id -> QKeySequence``. Missing or
    invalid user entries silently fall back to the default."""
    if path is None:
        path = default_keymap_path()
    user: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            user = {k: v for k, v in data.items() if isinstance(v, str)}
    except FileNotFoundError:
        log.info("keymap file %s not present, using defaults", path)
    except Exception:
        log.exception("keymap load failed at %s; using defaults", path)

    result: dict[str, QKeySequence] = {}
    for action_id, _label, default in ACTIONS:
        result[action_id] = QKeySequence(user.get(action_id, default))
    return result


def save_keymap(bindings: dict[str, QKeySequence], path: Path | None = None) -> None:
    """Persist atomically: write to a sibling .tmp file and rename, so a
    crashed write can't leave a half-truncated keymap."""
    if path is None:
        path = default_keymap_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serial = {aid: seq.toString() for aid, seq in bindings.items()}
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(serial, fp, indent=2, sort_keys=True)
    tmp.replace(path)


def label_for(action_id: str) -> str:
    for aid, label, _ in ACTIONS:
        if aid == action_id:
            return label
    return action_id


def default_for(action_id: str) -> QKeySequence:
    for aid, _, default in ACTIONS:
        if aid == action_id:
            return QKeySequence(default)
    return QKeySequence()
