"""Pure PSK helpers for the channel editor — no Qt imports."""

from __future__ import annotations

import base64
import secrets


def random_psk_b64() -> str:
    """Generate a 256-bit base64-encoded PSK suitable for a Meshtastic channel."""
    return base64.b64encode(secrets.token_bytes(32)).decode()


def is_valid_psk_b64(s: str) -> bool:
    """Quick sanity check for a PSK string supplied by the user."""
    if not s:
        return True  # empty is allowed (default channel)
    try:
        raw = base64.b64decode(s, validate=True)
    except (ValueError, base64.binascii.Error):
        return False
    return len(raw) in (16, 32)  # AES-128 or AES-256
