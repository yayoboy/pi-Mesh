import math
from pathlib import Path

import pytest

from gui.pages.map_math import (
    MAX_ZOOM,
    TILE_SIZE,
    TileCache,
    TileLoader,
    lonlat_to_pixel,
    lonlat_to_tile,
    pixel_to_lonlat,
    tile_bounds_lonlat,
    tile_path,
    visible_tiles,
)


# --- coordinate conversion --------------------------------------------------

def test_zoom_zero_world_is_one_tile():
    # At zoom 0 the world fits in one tile of TILE_SIZE.
    x, y = lonlat_to_pixel(0.0, 0.0, 0)
    assert x == pytest.approx(TILE_SIZE / 2)
    assert y == pytest.approx(TILE_SIZE / 2)


@pytest.mark.parametrize(
    "lon,lat,zoom",
    [
        (0.0, 0.0, 1),
        (12.5, 41.9, 12),    # Rome
        (-0.13, 51.51, 14),  # London
        (-74.0, 40.7, 10),   # New York
        (151.2, -33.8, 8),   # Sydney
        (139.7, 35.7, 16),   # Tokyo
    ],
)
def test_lonlat_pixel_round_trip(lon, lat, zoom):
    px, py = lonlat_to_pixel(lon, lat, zoom)
    lon2, lat2 = pixel_to_lonlat(px, py, zoom)
    assert lon2 == pytest.approx(lon, abs=1e-6)
    assert lat2 == pytest.approx(lat, abs=1e-6)


def test_lonlat_to_pixel_zoom_doubles_with_each_level():
    px0, py0 = lonlat_to_pixel(12.5, 41.9, 5)
    px1, py1 = lonlat_to_pixel(12.5, 41.9, 6)
    assert px1 == pytest.approx(px0 * 2, abs=1e-3)
    assert py1 == pytest.approx(py0 * 2, abs=1e-3)


def test_extreme_latitude_is_clipped_to_mercator_range():
    # Without clipping math.tan(pi/2) would diverge.
    px, py = lonlat_to_pixel(0.0, 89.9, 5)
    assert math.isfinite(px)
    assert math.isfinite(py)


def test_zoom_out_of_range_raises():
    with pytest.raises(ValueError):
        lonlat_to_pixel(0, 0, -1)
    with pytest.raises(ValueError):
        lonlat_to_pixel(0, 0, MAX_ZOOM + 1)


def test_lonlat_to_tile_north_pole_is_top_row():
    tx, ty = lonlat_to_tile(0.0, 85.0, 4)
    assert ty == 0


def test_lonlat_to_tile_south_pole_is_bottom_row():
    tx, ty = lonlat_to_tile(0.0, -85.0, 4)
    n = 2 ** 4
    assert ty == n - 1


def test_tile_bounds_at_zoom_zero_covers_whole_world():
    lon0, lat0, lon1, lat1 = tile_bounds_lonlat(0, 0, 0)
    assert lon0 == pytest.approx(-180.0)
    assert lon1 == pytest.approx(180.0)
    assert lat0 < -85 and lat1 > 85


def test_tile_bounds_out_of_range_raises():
    with pytest.raises(ValueError):
        tile_bounds_lonlat(5, 0, 0)  # zoom 0 has only one tile (0,0)


# --- visible tiles ----------------------------------------------------------

def test_visible_tiles_returns_at_least_one_tile_for_tiny_viewport():
    tiles = list(visible_tiles(12.5, 41.9, 8, 1, 1))
    assert len(tiles) >= 1


def test_visible_tiles_grows_with_viewport_size():
    small = list(visible_tiles(12.5, 41.9, 12, 320, 320))
    big = list(visible_tiles(12.5, 41.9, 12, 1920, 1080))
    assert len(big) > len(small)


def test_visible_tiles_never_yields_negative_indices():
    # Center near top-left of the world to push the margin negative
    tiles = list(visible_tiles(-179.9, 85.0, 1, 320, 320))
    assert all(tx >= 0 and ty >= 0 for tx, ty in tiles)


def test_visible_tiles_never_yields_indices_beyond_world():
    n = 2 ** 4
    tiles = list(visible_tiles(179.9, -85.0, 4, 320, 320))
    assert all(tx < n and ty < n for tx, ty in tiles)


def test_visible_tiles_includes_one_tile_margin():
    # At zoom 0 there is exactly one tile, viewport of 1px should still yield it.
    tiles = list(visible_tiles(0, 0, 0, 1, 1))
    assert (0, 0) in tiles


# --- TileCache (LRU) --------------------------------------------------------

def test_tile_cache_stores_and_retrieves():
    cache = TileCache(max_entries=4)
    cache.put(10, 0, 0, "a")
    assert cache.get(10, 0, 0) == "a"
    assert cache.hits == 1
    assert cache.misses == 0


def test_tile_cache_miss_returns_none_and_counts():
    cache = TileCache()
    assert cache.get(1, 2, 3) is None
    assert cache.misses == 1


def test_tile_cache_evicts_oldest_when_full():
    cache = TileCache(max_entries=2)
    cache.put(1, 0, 0, "first")
    cache.put(1, 0, 1, "second")
    cache.put(1, 0, 2, "third")  # evicts "first"
    assert cache.get(1, 0, 0) is None
    assert cache.get(1, 0, 1) == "second"
    assert cache.get(1, 0, 2) == "third"


def test_tile_cache_lru_promotes_on_access():
    cache = TileCache(max_entries=2)
    cache.put(1, 0, 0, "first")
    cache.put(1, 0, 1, "second")
    cache.get(1, 0, 0)  # promote "first" to most-recent
    cache.put(1, 0, 2, "third")  # evicts "second"
    assert cache.get(1, 0, 0) == "first"
    assert cache.get(1, 0, 1) is None


def test_tile_cache_put_existing_key_updates_value():
    cache = TileCache(max_entries=2)
    cache.put(1, 0, 0, "v1")
    cache.put(1, 0, 0, "v2")
    assert cache.get(1, 0, 0) == "v2"
    assert len(cache) == 1


def test_tile_cache_invalid_size_raises():
    with pytest.raises(ValueError):
        TileCache(max_entries=0)
    with pytest.raises(ValueError):
        TileCache(max_entries=-3)


def test_tile_cache_clear_resets_counters():
    cache = TileCache()
    cache.put(1, 0, 0, "x")
    cache.get(1, 0, 0)
    cache.clear()
    assert len(cache) == 0
    assert cache.hits == 0
    assert cache.misses == 0


# --- TileLoader -------------------------------------------------------------

def test_tile_path_layout(tmp_path):
    p = tile_path(tmp_path, 12, 1234, 5678)
    assert p == tmp_path / "12" / "1234" / "5678.png"


def test_tile_loader_returns_none_for_missing(tmp_path):
    loader = TileLoader(tmp_path)
    assert loader.get(10, 0, 0) is None


def test_tile_loader_reads_existing_file(tmp_path):
    target = tile_path(tmp_path, 10, 5, 7)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake-png-bytes")

    loader = TileLoader(tmp_path)
    assert loader.get(10, 5, 7) == b"fake-png-bytes"


def test_tile_loader_caches_after_first_read(tmp_path):
    target = tile_path(tmp_path, 10, 5, 7)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")

    reads = []

    def reader(p):
        reads.append(p)
        return p.read_bytes()

    loader = TileLoader(tmp_path, reader=reader)
    loader.get(10, 5, 7)
    loader.get(10, 5, 7)  # should hit cache, not call reader again
    loader.get(10, 5, 7)

    assert len(reads) == 1
    assert loader.cache.hits == 2
    assert loader.cache.misses == 1


def test_tile_loader_does_not_cache_misses(tmp_path):
    loader = TileLoader(tmp_path)
    loader.get(10, 999, 999)
    loader.get(10, 999, 999)
    # Both lookups should still be misses (no negative caching).
    assert loader.cache.misses == 2


def test_tile_loader_uses_injected_cache(tmp_path):
    custom_cache = TileCache(max_entries=1)
    loader = TileLoader(tmp_path, cache=custom_cache)
    assert loader.cache is custom_cache
