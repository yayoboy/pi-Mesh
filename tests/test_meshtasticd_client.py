# tests/test_meshtasticd_client.py
import pytest
import meshtasticd_client


def test_haversine_same_point():
    result = meshtasticd_client._haversine(41.9, 12.5, 41.9, 12.5)
    assert result == 0.0


def test_haversine_one_degree_latitude():
    # 1 degree latitude ≈ 111 km
    result = meshtasticd_client._haversine(0.0, 0.0, 1.0, 0.0)
    assert 110 < result < 112


def test_haversine_rome_to_milan():
    # Rome (41.9, 12.5) to Milan (45.46, 9.19) ≈ 477 km
    result = meshtasticd_client._haversine(41.9, 12.5, 45.46, 9.19)
    assert 470 < result < 490


def test_add_distances_local_node_gets_zero():
    meshtasticd_client._node_cache.clear()
    meshtasticd_client._node_cache['!local'] = {
        'id': '!local', 'latitude': 41.9, 'longitude': 12.5,
        'is_local': True, 'distance_km': None,
    }
    meshtasticd_client._add_distances()
    assert meshtasticd_client._node_cache['!local']['distance_km'] == 0.0


def test_add_distances_remote_node_gets_distance():
    meshtasticd_client._node_cache.clear()
    meshtasticd_client._node_cache['!local'] = {
        'id': '!local', 'latitude': 41.9, 'longitude': 12.5,
        'is_local': True, 'distance_km': None,
    }
    meshtasticd_client._node_cache['!remote'] = {
        'id': '!remote', 'latitude': 45.46, 'longitude': 9.19,
        'is_local': False, 'distance_km': None,
    }
    meshtasticd_client._add_distances()
    d = meshtasticd_client._node_cache['!remote']['distance_km']
    assert d is not None
    assert 470 < d < 490


def test_add_distances_no_coords_returns_none():
    meshtasticd_client._node_cache.clear()
    meshtasticd_client._node_cache['!local'] = {
        'id': '!local', 'latitude': 41.9, 'longitude': 12.5,
        'is_local': True, 'distance_km': None,
    }
    meshtasticd_client._node_cache['!nogps'] = {
        'id': '!nogps', 'latitude': None, 'longitude': None,
        'is_local': False, 'distance_km': None,
    }
    meshtasticd_client._add_distances()
    assert meshtasticd_client._node_cache['!nogps']['distance_km'] is None


def test_add_distances_no_local_node_all_none():
    meshtasticd_client._node_cache.clear()
    meshtasticd_client._node_cache['!remote'] = {
        'id': '!remote', 'latitude': 45.46, 'longitude': 9.19,
        'is_local': False, 'distance_km': None,
    }
    meshtasticd_client._add_distances()
    assert meshtasticd_client._node_cache['!remote']['distance_km'] is None
