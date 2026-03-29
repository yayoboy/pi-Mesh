# tests/test_meshtasticd_client.py
import pytest
import time
from unittest.mock import MagicMock, patch
import meshtasticd_client as mc


def test_is_connected_false_initially():
    mc._connected = False
    assert mc.is_connected() is False


def test_get_nodes_returns_cache_within_ttl():
    mc._node_cache = {'!abc': {'id': '!abc', 'short_name': 'X'}}
    mc._last_node_fetch = time.time()  # just fetched
    nodes = mc.get_nodes()
    assert len(nodes) == 1
    assert nodes[0]['short_name'] == 'X'


def test_get_nodes_empty_when_cache_cold():
    mc._node_cache = {}
    mc._last_node_fetch = 0.0
    # Without a real connection, returns empty list
    with patch.object(mc, '_connected', False):
        nodes = mc.get_nodes()
    assert nodes == []


def test_get_local_node_returns_none_when_empty():
    mc._node_cache = {}
    assert mc.get_local_node() is None


def test_get_local_node_finds_is_local():
    mc._node_cache = {
        '!aaa': {'id': '!aaa', 'is_local': False},
        '!bbb': {'id': '!bbb', 'is_local': True, 'short_name': 'LOCAL'},
    }
    node = mc.get_local_node()
    assert node is not None
    assert node['short_name'] == 'LOCAL'
