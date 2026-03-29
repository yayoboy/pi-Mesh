# tests/test_database.py
import pytest
import aiosqlite
import database


@pytest.mark.asyncio
async def test_init_creates_tables(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in await cursor.fetchall()}
    assert 'nodes' in tables
    assert 'messages' in tables
    assert 'packets' in tables
    assert 'custom_markers' in tables


@pytest.mark.asyncio
async def test_wal_mode_enabled(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute('PRAGMA journal_mode')
        row = await cursor.fetchone()
    assert row[0] == 'wal'


@pytest.mark.asyncio
async def test_upsert_node(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    node = {
        'id': '!aabbccdd',
        'short_name': 'TEST',
        'long_name': 'Test Node',
        'latitude': 41.9,
        'longitude': 12.5,
        'last_heard': 1700000000,
        'snr': 8.0,
        'battery_level': 85,
        'hop_count': 0,
        'hw_model': 'HELTEC_V3',
        'is_local': 1,
        'raw_json': '{}',
        'distance_km': None,
    }
    await database.upsert_node(db_path, node)
    nodes = await database.get_all_nodes(db_path)
    assert len(nodes) == 1
    assert nodes[0]['short_name'] == 'TEST'


@pytest.mark.asyncio
async def test_nodes_table_has_distance_km(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA table_info(nodes)")
        cols = {row[1] for row in await cursor.fetchall()}
    assert 'distance_km' in cols


@pytest.mark.asyncio
async def test_upsert_node_with_distance_km(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    node = {
        'id': '!aabbccdd', 'short_name': 'TEST', 'long_name': 'Test Node',
        'latitude': 41.9, 'longitude': 12.5, 'last_heard': 1700000000,
        'snr': 8.0, 'battery_level': 85, 'hop_count': 0,
        'hw_model': 'HELTEC_V3', 'is_local': 1, 'raw_json': '{}',
        'distance_km': 2.4,
    }
    await database.upsert_node(db_path, node)
    nodes = await database.get_all_nodes(db_path)
    assert nodes[0]['distance_km'] == 2.4


@pytest.mark.asyncio
async def test_upsert_node_distance_km_none(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    node = {
        'id': '!aabbccdd', 'short_name': 'TEST', 'long_name': 'Test Node',
        'latitude': None, 'longitude': None, 'last_heard': 1700000000,
        'snr': None, 'battery_level': None, 'hop_count': None,
        'hw_model': 'HELTEC_V3', 'is_local': 0, 'raw_json': '{}',
        'distance_km': None,
    }
    await database.upsert_node(db_path, node)
    nodes = await database.get_all_nodes(db_path)
    assert nodes[0]['distance_km'] is None


@pytest.mark.asyncio
async def test_custom_markers_table_exists(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='custom_markers'"
        )
        row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_create_marker_returns_dict(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    marker = await database.create_marker(db_path, 'Test Marker', 'poi', 41.9, 12.5)
    assert marker['label'] == 'Test Marker'
    assert marker['icon_type'] == 'poi'
    assert marker['latitude'] == 41.9
    assert marker['longitude'] == 12.5
    assert 'id' in marker


@pytest.mark.asyncio
async def test_get_markers_returns_list(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    await database.create_marker(db_path, 'M1', 'poi', 41.0, 12.0)
    await database.create_marker(db_path, 'M2', 'antenna', 42.0, 13.0)
    markers = await database.get_markers(db_path)
    assert len(markers) == 2
    assert markers[0]['label'] == 'M1'
    assert markers[1]['label'] == 'M2'


@pytest.mark.asyncio
async def test_delete_marker_returns_true(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    marker = await database.create_marker(db_path, 'Del Me', 'poi', 41.0, 12.0)
    result = await database.delete_marker(db_path, marker['id'])
    assert result is True
    markers = await database.get_markers(db_path)
    assert len(markers) == 0


@pytest.mark.asyncio
async def test_delete_marker_nonexistent_returns_false(tmp_path):
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    result = await database.delete_marker(db_path, 9999)
    assert result is False
