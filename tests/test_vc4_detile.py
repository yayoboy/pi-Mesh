# tests/test_vc4_detile.py
"""Roundtrip test for the VC4 T-format detiler."""
import importlib.util
import os

import numpy as np
import pytest

_SPEC = importlib.util.spec_from_file_location(
    'vc4_detile',
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'vc4_detile.py'))
vc4_detile = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vc4_detile)


def _tile(img):
    """Inverse of detile(): produce the linear dump of a T-tiled buffer."""
    h, w, ch = img.shape
    tiles_x = w // 32
    flat = np.zeros((h * w, ch), dtype=img.dtype)
    for tr in range(h // 32):
        order = vc4_detile.ORDER_EVEN if tr % 2 == 0 else vc4_detile.ORDER_ODD
        for ti in range(tiles_x):
            tx = ti if tr % 2 == 0 else (tiles_x - 1 - ti)
            base = (tr * tiles_x + ti) * 1024
            y0, x0 = tr * 32, tx * 32
            for s, name in enumerate(order):
                dy, dx = vc4_detile.POS[name]
                block = img[y0 + dy:y0 + dy + 16, x0 + dx:x0 + dx + 16]
                sub = block.reshape(4, 4, 4, 4, ch).transpose(0, 2, 1, 3, 4)
                flat[base + s * 256:base + (s + 1) * 256] = sub.reshape(256, ch)
    return flat.reshape(h, w, ch)


def test_detile_roundtrip():
    rng = np.random.default_rng(42)
    img = rng.integers(0, 256, size=(64, 64, 4), dtype=np.uint8)
    assert np.array_equal(vc4_detile.detile(_tile(img)), img)


def test_detile_truncated_height():
    # 40 rows: the second tile row is truncated in the linear dump — the
    # detiler must not crash and must reproduce at least the complete rows.
    rng = np.random.default_rng(7)
    img = rng.integers(0, 256, size=(64, 64, 4), dtype=np.uint8)
    tiled = _tile(img)[:40]                    # truncated dump
    out = vc4_detile.detile(tiled)
    assert out.shape == (40, 64, 4)
    assert np.array_equal(out[:32], img[:32])  # first full tile row intact
