import asyncio
import pytest
import database


@pytest.fixture
def tmp_db(tmp_path):
    path = str(tmp_path / 'test.db')
    asyncio.run(database.init(path))
    yield path
    asyncio.run(database.close())


def test_waypoint_upsert_and_get(tmp_db):
    wp = {'id': 1, 'name': 'Base', 'lat': 44.5, 'lon': 11.3, 'icon': 'default',
          'description': 'QTH', 'expire': 0, 'from_id': '!aabb', 'ts': 1000}
    asyncio.run(database.upsert_waypoint(wp))
    result = asyncio.run(database.get_waypoints())
    assert len(result) == 1
    assert result[0]['name'] == 'Base'


def test_waypoint_upsert_updates_existing(tmp_db):
    wp = {'id': 1, 'name': 'Old', 'lat': 44.5, 'lon': 11.3, 'icon': 'default',
          'description': '', 'expire': 0, 'from_id': '!aabb', 'ts': 1000}
    asyncio.run(database.upsert_waypoint(wp))
    wp['name'] = 'New'
    asyncio.run(database.upsert_waypoint(wp))
    result = asyncio.run(database.get_waypoints())
    assert len(result) == 1
    assert result[0]['name'] == 'New'


def test_waypoint_expire_filters(tmp_db):
    import time
    expired = {'id': 2, 'name': 'Old', 'lat': 0, 'lon': 0, 'icon': 'default',
               'description': '', 'expire': int(time.time()) - 10, 'from_id': '!x', 'ts': 0}
    asyncio.run(database.upsert_waypoint(expired))
    result = asyncio.run(database.get_waypoints(active_only=True))
    assert len(result) == 0


def test_neighbor_info_upsert(tmp_db):
    asyncio.run(database.upsert_neighbor_info('!aa', '!bb', 5.5))
    asyncio.run(database.upsert_neighbor_info('!aa', '!bb', 3.0))
    rows = asyncio.run(database.get_neighbor_info())
    assert len(rows) == 1
    assert rows[0]['snr'] == 3.0


def test_sensor_event_save(tmp_db):
    asyncio.run(database.save_sensor_event('!cc', 'detection', {'triggered': True}))
