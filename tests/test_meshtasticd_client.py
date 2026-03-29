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


import asyncio


def test_get_event_queue_returns_asyncio_queue():
    q = meshtasticd_client.get_event_queue()
    assert isinstance(q, asyncio.Queue)


@pytest.mark.asyncio
async def test_on_receive_always_emits_log_event():
    import meshtasticd_client as mc
    # Drain queue
    q = mc.get_event_queue()
    while not q.empty():
        q.get_nowait()

    mc._loop = asyncio.get_event_loop()
    packet = {
        'fromId': '!aabbccdd',
        'rxSnr': 5.5,
        'hopLimit': 3,
        'decoded': {'portnum': 'TEXT_MESSAGE_APP'},
    }
    mc._on_receive(packet, None)
    await asyncio.sleep(0)

    assert not q.empty()
    event = q.get_nowait()
    assert event['type'] == 'log'
    assert event['from'] == '!aabbccdd'
    mc._loop = None


@pytest.mark.asyncio
async def test_on_receive_position_emits_typed_event():
    import meshtasticd_client as mc
    q = mc.get_event_queue()
    while not q.empty():
        q.get_nowait()

    mc._loop = asyncio.get_event_loop()
    packet = {
        'fromId': '!aabbccdd',
        'rxSnr': 4.0,
        'hopLimit': 3,
        'decoded': {
            'portnum': 'POSITION_APP',
            'position': {'latitude': 41.9, 'longitude': 12.5},
        },
    }
    mc._on_receive(packet, None)
    await asyncio.sleep(0)

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    types = [e['type'] for e in events]
    assert 'position' in types
    pos_event = next(e for e in events if e['type'] == 'position')
    assert pos_event['id'] == '!aabbccdd'
    assert pos_event['latitude'] == pytest.approx(41.9)
    mc._loop = None


@pytest.mark.asyncio
async def test_on_receive_telemetry_emits_typed_event():
    import meshtasticd_client as mc
    q = mc.get_event_queue()
    while not q.empty():
        q.get_nowait()

    mc._loop = asyncio.get_event_loop()
    packet = {
        'fromId': '!aabbccdd',
        'rxSnr': 3.0,
        'hopLimit': 2,
        'decoded': {
            'portnum': 'TELEMETRY_APP',
            'telemetry': {'deviceMetrics': {'batteryLevel': 78}},
        },
    }
    mc._on_receive(packet, None)
    await asyncio.sleep(0)

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    tel_event = next((e for e in events if e['type'] == 'telemetry'), None)
    assert tel_event is not None
    assert tel_event['battery_level'] == 78
    mc._loop = None


@pytest.mark.asyncio
async def test_request_traceroute_enqueues_callable():
    import meshtasticd_client as mc
    while not mc._command_queue.empty():
        mc._command_queue.get_nowait()

    mc._connected = True
    await mc.request_traceroute('!aabbccdd')
    assert not mc._command_queue.empty()
    cmd = mc._command_queue.get_nowait()
    assert callable(cmd)


@pytest.mark.asyncio
async def test_send_text_enqueues_callable():
    import meshtasticd_client as mc
    while not mc._command_queue.empty():
        mc._command_queue.get_nowait()

    mc._connected = True
    await mc.send_text('Hello', '!aabbccdd', channel=0)
    assert not mc._command_queue.empty()
    cmd = mc._command_queue.get_nowait()
    assert callable(cmd)


@pytest.mark.asyncio
async def test_request_position_enqueues_callable():
    import meshtasticd_client as mc
    while not mc._command_queue.empty():
        mc._command_queue.get_nowait()

    mc._connected = True
    await mc.request_position('!aabbccdd')
    assert not mc._command_queue.empty()
    cmd = mc._command_queue.get_nowait()
    assert callable(cmd)


def test_get_traceroute_result_returns_none_when_missing():
    import meshtasticd_client as mc
    result = mc.get_traceroute_result('!nonexistent')
    assert result is None


def test_get_traceroute_result_returns_cached_entry():
    import meshtasticd_client as mc
    mc._traceroute_cache['!aabbccdd'] = {
        'node_id': '!aabbccdd',
        'hops': ['!00000001', '!00000002'],
        'ts': 1700000000,
    }
    result = mc.get_traceroute_result('!aabbccdd')
    assert result is not None
    assert result['hops'] == ['!00000001', '!00000002']


@pytest.mark.asyncio
async def test_load_nodes_from_db_populates_cache(tmp_path):
    import meshtasticd_client as mc
    import database

    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)

    node = {
        'id': '!aabbccdd',
        'short_name': 'PERSIST',
        'long_name': 'Persisted Node',
        'latitude': 41.9,
        'longitude': 12.5,
        'last_heard': 1700000000,
        'snr': 7.0,
        'battery_level': 90,
        'hop_count': 1,
        'hw_model': 'HELTEC_V3',
        'is_local': 0,
        'distance_km': 3.5,
        'raw_json': '{}',
    }
    await database.upsert_node(db_path, node)

    mc._node_cache = {}
    await mc.load_nodes_from_db(db_path)

    assert '!aabbccdd' in mc._node_cache
    assert mc._node_cache['!aabbccdd']['short_name'] == 'PERSIST'


@pytest.mark.asyncio
async def test_flush_dirty_writes_nodes_to_db(tmp_path):
    import meshtasticd_client as mc
    import database

    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)

    mc._node_cache = {
        '!aabbccdd': {
            'id': '!aabbccdd',
            'short_name': 'DIRTY',
            'long_name': 'Dirty Node',
            'latitude': 41.9,
            'longitude': 12.5,
            'last_heard': 1700000000,
            'snr': 6.0,
            'battery_level': 75,
            'hop_count': 2,
            'hw_model': 'HELTEC_V3',
            'is_local': 0,
            'distance_km': 5.0,
            'raw_json': '{}',
        }
    }
    mc._dirty_nodes = {'!aabbccdd'}

    await mc._flush_dirty(db_path)

    assert len(mc._dirty_nodes) == 0
    nodes = await database.get_all_nodes(db_path)
    assert any(n['id'] == '!aabbccdd' for n in nodes)
