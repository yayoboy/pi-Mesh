"""Pure-Python helpers for the offline tile map.

Web Mercator (EPSG:3857) is the projection used by OpenStreetMap raster tiles
and by Leaflet's default tile layer, so we adopt it here for parity with the
existing tiles in ``data/tiles/{z}/{x}/{y}.png``.

No Qt imports: this module is fully testable without a display server.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path
from typing import Iterator

TILE_SIZE = 256
MIN_ZOOM = 0
MAX_ZOOM = 22  # OSM goes up to 19 in practice, but math is valid up to 22.


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------

def lonlat_to_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Convert (lon, lat) to absolute pixel coordinates at the given zoom.

    The world is ``2**zoom * TILE_SIZE`` pixels wide at zoom level ``zoom``.
    """
    if not (MIN_ZOOM <= zoom <= MAX_ZOOM):
        raise ValueError(f"zoom {zoom} out of range [{MIN_ZOOM}, {MAX_ZOOM}]")
    # Clip latitude to valid Mercator range to avoid math.tan(pi/2).
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def pixel_to_lonlat(x: float, y: float, zoom: int) -> tuple[float, float]:
    """Inverse of :func:`lonlat_to_pixel`."""
    if not (MIN_ZOOM <= zoom <= MAX_ZOOM):
        raise ValueError(f"zoom {zoom} out of range [{MIN_ZOOM}, {MAX_ZOOM}]")
    n = 2 ** zoom
    lon = x / (n * TILE_SIZE) * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / (n * TILE_SIZE))))
    lat = math.degrees(lat_rad)
    return lon, lat


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Return the (tile_x, tile_y) containing the given (lon, lat) at zoom."""
    px, py = lonlat_to_pixel(lon, lat, zoom)
    return int(px // TILE_SIZE), int(py // TILE_SIZE)


def tile_bounds_lonlat(tile_x: int, tile_y: int, zoom: int) -> tuple[float, float, float, float]:
    """Return ``(lon_min, lat_min, lon_max, lat_max)`` of the given tile."""
    n = 2 ** zoom
    if not (0 <= tile_x < n and 0 <= tile_y < n):
        raise ValueError(f"tile ({tile_x},{tile_y}) out of range at zoom {zoom}")
    px0 = tile_x * TILE_SIZE
    py0 = tile_y * TILE_SIZE
    px1 = (tile_x + 1) * TILE_SIZE
    py1 = (tile_y + 1) * TILE_SIZE
    lon0, lat1 = pixel_to_lonlat(px0, py0, zoom)
    lon1, lat0 = pixel_to_lonlat(px1, py1, zoom)
    return lon0, lat0, lon1, lat1


def visible_tiles(
    center_lon: float,
    center_lat: float,
    zoom: int,
    viewport_w: int,
    viewport_h: int,
) -> Iterator[tuple[int, int]]:
    """Yield ``(tile_x, tile_y)`` for every tile visible in the viewport.

    Includes a one-tile margin around the viewport so panning has tiles ready.
    """
    cx, cy = lonlat_to_pixel(center_lon, center_lat, zoom)
    half_w = viewport_w / 2
    half_h = viewport_h / 2
    x_min = int((cx - half_w) // TILE_SIZE) - 1
    x_max = int((cx + half_w) // TILE_SIZE) + 1
    y_min = int((cy - half_h) // TILE_SIZE) - 1
    y_max = int((cy + half_h) // TILE_SIZE) + 1
    n = 2 ** zoom
    for tx in range(max(0, x_min), min(n, x_max + 1)):
        for ty in range(max(0, y_min), min(n, y_max + 1)):
            yield tx, ty


# ---------------------------------------------------------------------------
# Tile cache
# ---------------------------------------------------------------------------

class TileCache:
    """LRU cache mapping ``(z, x, y)`` to whatever pixmap-like object we hold.

    The cache is generic over the value type so it can be unit-tested with
    plain strings/bytes; the runtime ``MapWidget`` will store ``QPixmap``.
    """

    def __init__(self, max_entries: int = 256):
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max = max_entries
        self._data: OrderedDict[tuple[int, int, int], object] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, z: int, x: int, y: int):
        key = (z, x, y)
        if key in self._data:
            self._data.move_to_end(key)
            self.hits += 1
            return self._data[key]
        self.misses += 1
        return None

    def put(self, z: int, x: int, y: int, value) -> None:
        key = (z, x, y)
        if key in self._data:
            self._data.move_to_end(key)
            self._data[key] = value
            return
        self._data[key] = value
        if len(self._data) > self._max:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: tuple[int, int, int]) -> bool:
        return key in self._data

    def clear(self) -> None:
        self._data.clear()
        self.hits = 0
        self.misses = 0


# ---------------------------------------------------------------------------
# Filesystem tile loader
# ---------------------------------------------------------------------------

def tile_path(tiles_root: Path, z: int, x: int, y: int) -> Path:
    """Build the standard ``{z}/{x}/{y}.png`` path under ``tiles_root``."""
    return tiles_root / str(z) / str(x) / f"{y}.png"


class TileLoader:
    """Filesystem-backed loader with an in-memory LRU cache.

    Returns ``None`` for missing tiles (the MapWidget renders a placeholder).
    The reader callback is injected so the runtime can plug in
    ``QPixmap(str(path))`` while tests use plain ``bytes`` reads.
    """

    def __init__(self, tiles_root: Path, reader=None, cache: TileCache | None = None):
        self.tiles_root = Path(tiles_root)
        self._reader = reader if reader is not None else self._read_bytes
        self._cache = cache if cache is not None else TileCache()

    @property
    def cache(self) -> TileCache:
        return self._cache

    @staticmethod
    def _read_bytes(path: Path) -> bytes:
        return path.read_bytes()

    def get(self, z: int, x: int, y: int):
        cached = self._cache.get(z, x, y)
        if cached is not None:
            return cached
        path = tile_path(self.tiles_root, z, x, y)
        if not path.exists():
            return None
        value = self._reader(path)
        self._cache.put(z, x, y, value)
        return value
