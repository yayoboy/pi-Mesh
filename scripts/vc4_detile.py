#!/usr/bin/env python3
"""Detile a VC4 T-tiled screenshot: scrambled PNG in, correct PNG out.

cog/WPE on vc4 KMS scans out DRM_FORMAT_MOD_BROADCOM_VC4_T_TILED buffers
(modifier 0x0700000000000001). ffmpeg's kmsgrab+hwdownload copies the raw
bytes linearly, producing an image whose pixels are in tile order instead
of raster order. This script rearranges them.

T-format at 32bpp (empirically validated on the Pi 3 / 1024x600 panel):
  - 64B utiles: 4x4 px, raster order
  - 1KB subtiles: 4x4 utiles raster order (16x16 px)
  - 4KB tiles: 2x2 subtiles (32x32 px), storage order (TL, BL, BR, TR)
    on even tile rows and (BR, TR, TL, BL) on odd rows
  - tile rows boustrophedon: even rows left-to-right, odd right-to-left

If the display height is not a multiple of 32, the linear dump truncates
the last tile row: the unreconstructable bottom-right corner is left black.

Usage: vc4_detile.py <tiled.png> <out.png>
"""
import sys

import numpy as np
from PIL import Image

POS = {'TL': (0, 0), 'TR': (0, 16), 'BL': (16, 0), 'BR': (16, 16)}
ORDER_EVEN = ('TL', 'BL', 'BR', 'TR')
ORDER_ODD = ('BR', 'TR', 'TL', 'BL')


def detile(img: np.ndarray) -> np.ndarray:
    h, w, ch = img.shape
    tiles_x = w // 32
    flat = img.reshape(h * w, ch)
    out = np.zeros_like(img)
    for tr in range((h + 31) // 32):
        order = ORDER_EVEN if tr % 2 == 0 else ORDER_ODD
        for ti in range(tiles_x):
            tx = ti if tr % 2 == 0 else (tiles_x - 1 - ti)
            base = (tr * tiles_x + ti) * 1024          # px, not bytes
            if base + 1024 > flat.shape[0]:
                continue                                # truncated dump
            tile = flat[base:base + 1024]
            y0, x0 = tr * 32, tx * 32
            for s, name in enumerate(order):
                dy, dx = POS[name]
                sub = tile[s * 256:(s + 1) * 256].reshape(4, 4, 4, 4, ch)
                block = sub.transpose(0, 2, 1, 3, 4).reshape(16, 16, ch)
                ys = y0 + dy
                rows = min(16, h - ys)
                if rows > 0:
                    out[ys:ys + rows, x0 + dx:x0 + dx + 16] = block[:rows]
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    img = np.asarray(Image.open(sys.argv[1]).convert('RGBA'))
    Image.fromarray(detile(img), 'RGBA').convert('RGB').save(sys.argv[2])
    return 0


if __name__ == '__main__':
    sys.exit(main())
