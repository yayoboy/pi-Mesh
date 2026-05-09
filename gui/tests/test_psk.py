import base64

import pytest

from gui.pages._psk import is_valid_psk_b64, random_psk_b64


def test_random_psk_decodes_to_32_bytes():
    s = random_psk_b64()
    raw = base64.b64decode(s)
    assert len(raw) == 32


def test_random_psk_is_unique_per_call():
    a = random_psk_b64()
    b = random_psk_b64()
    assert a != b


def test_empty_is_accepted_as_valid():
    assert is_valid_psk_b64("") is True


def test_random_psk_round_trip_is_valid():
    assert is_valid_psk_b64(random_psk_b64())


def test_aes128_psk_is_valid():
    assert is_valid_psk_b64(base64.b64encode(b"\x00" * 16).decode())


def test_garbage_is_rejected():
    assert is_valid_psk_b64("not-base64!!!") is False


def test_wrong_length_is_rejected():
    # 8 bytes — too short for AES-128.
    assert is_valid_psk_b64(base64.b64encode(b"\x00" * 8).decode()) is False
    # 64 bytes — too long.
    assert is_valid_psk_b64(base64.b64encode(b"\x00" * 64).decode()) is False
