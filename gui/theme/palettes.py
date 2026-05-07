"""Color palettes for the Qt GUI.

Mirror the four themes the web UI defines in templates/base.html so that the
local kiosk and the remote browser stay visually consistent. Only colors are
parametrized; spacing and typography are handled by the QSS template.
"""

from __future__ import annotations

from typing import Literal


PaletteName = Literal["dark", "light", "hc", "custom"]


_REQUIRED_KEYS = (
    "bg",
    "panel",
    "border",
    "text",
    "muted",
    "accent",
    "ok",
    "warn",
    "danger",
)


PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg":     "#060810",
        "panel":  "#0d1017",
        "border": "#1a2233",
        "text":   "#c9d1e0",
        "muted":  "#4a5568",
        "accent": "#4a9eff",
        "ok":     "#4caf50",
        "warn":   "#ff9800",
        "danger": "#f44336",
    },
    "light": {
        "bg":     "#f8fafc",
        "panel":  "#ffffff",
        "border": "#e2e8f0",
        "text":   "#1a202c",
        "muted":  "#718096",
        "accent": "#1565c0",
        "ok":     "#2e7d32",
        "warn":   "#e65100",
        "danger": "#c62828",
    },
    "hc": {
        "bg":     "#000000",
        "panel":  "#111111",
        "border": "#444444",
        "text":   "#ffffff",
        "muted":  "#aaaaaa",
        "accent": "#ffff00",
        "ok":     "#00ff00",
        "warn":   "#ff8800",
        "danger": "#ff0000",
    },
}


def _validate(palette: dict[str, str]) -> dict[str, str]:
    missing = [k for k in _REQUIRED_KEYS if k not in palette]
    if missing:
        raise ValueError(f"palette missing keys: {missing}")
    return palette


def get_palette(name: str, custom: dict[str, str] | None = None) -> dict[str, str]:
    """Return the palette dict for ``name``.

    For ``"custom"``, ``custom`` must be supplied (typically loaded from the
    ``pimesh-custom-theme`` setting in the database).
    """
    if name == "custom":
        if custom is None:
            raise ValueError("custom palette requires a 'custom' dict argument")
        return _validate(custom)
    if name not in PALETTES:
        raise KeyError(f"unknown palette: {name!r}")
    return _validate(PALETTES[name])
