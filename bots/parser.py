"""Pure-Python prefix command parser.

Used by ``bots.runner`` to turn a raw incoming text message into
``(command, args)`` if it matches the configured prefix.
"""

from __future__ import annotations


def parse_command(text: str, prefix: str) -> tuple[str | None, list[str]]:
    """Return (command, args) when ``text`` starts with ``prefix``.

    - ``text`` is stripped of leading whitespace before matching.
    - ``command`` is the first whitespace-separated token after the prefix,
      lower-cased.
    - ``args`` is the remaining tokens.
    - Returns ``(None, [])`` if the prefix doesn't match, the command is
      empty, or the prefix itself is empty/None (no command mode).

    Examples:
        parse_command("!ping",       "!") → ("ping",  [])
        parse_command("!nodes !aa",  "!") → ("nodes", ["!aa"])
        parse_command("hello",       "!") → (None, [])
        parse_command("!  ",         "!") → (None, [])
    """
    if not prefix or not text:
        return None, []
    stripped = text.lstrip()
    if not stripped.startswith(prefix):
        return None, []
    body = stripped[len(prefix):].strip()
    if not body:
        return None, []
    parts = body.split()
    return parts[0].lower(), parts[1:]
