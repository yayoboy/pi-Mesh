"""Pure-Python key layout data for the virtual keyboard.

Mirrors the rows in ``static/vkbd.js`` so the touchscreen keyboard behaves
the same in the web UI and the native GUI.
"""

from __future__ import annotations


ROWS_ALPHA: list[list[str]] = [
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]

ROWS_SYM: list[list[str]] = [
    list("1234567890"),
    list("@#$%&*-+="),
    list("!\"'():;/."),
]

ROWS_SYM2: list[list[str]] = [
    list("_~<>{}[]"),
    list("^|\\`?€"),
    [],
]


PAGES = (ROWS_ALPHA, ROWS_SYM, ROWS_SYM2)


def page_for(index: int) -> list[list[str]]:
    return PAGES[index % len(PAGES)]


def shift_char(ch: str) -> str:
    """What the alpha shift should display for a character."""
    return ch.upper()
