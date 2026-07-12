# tests/test_map_router.py
"""Tests for local tile set max-zoom detection."""
from routers import map_router


def test_local_tiles_max_zoom_from_dirs(tmp_path):
    base = tmp_path / 'tiles' / 'osm'
    for z in ('7', '10', '12'):
        (base / z).mkdir(parents=True)
    (base / 'not-a-zoom').mkdir()
    assert map_router._local_tiles_max_zoom(str(base)) == 12


def test_local_tiles_max_zoom_missing_dir(tmp_path):
    assert map_router._local_tiles_max_zoom(str(tmp_path / 'nope')) is None


def test_local_tiles_max_zoom_empty(tmp_path):
    assert map_router._local_tiles_max_zoom(str(tmp_path)) is None
