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
    }
    await database.upsert_node(db_path, node)
    nodes = await database.get_all_nodes(db_path)
    assert len(nodes) == 1
    assert nodes[0]['short_name'] == 'TEST'
