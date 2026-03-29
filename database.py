# database.py
import aiosqlite
import json
import logging

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    short_name TEXT,
    long_name TEXT,
    latitude REAL,
    longitude REAL,
    last_heard INTEGER,
    snr REAL,
    battery_level INTEGER,
    hop_count INTEGER,
    hw_model TEXT,
    is_local INTEGER DEFAULT 0,
    raw_json TEXT,
    distance_km REAL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel INTEGER DEFAULT 0,
    from_id TEXT,
    to_id TEXT,
    text TEXT,
    ts INTEGER,
    ack INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER,
    from_id TEXT,
    packet_type TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS custom_markers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    icon_type TEXT NOT NULL DEFAULT 'poi',
    latitude REAL NOT NULL,
    longitude REAL NOT NULL
);
"""


async def init(db_path: str) -> None:
    """Initialize DB with WAL mode and schema."""
    import os
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute('PRAGMA journal_mode=WAL')
        await db.executescript(_SCHEMA)
        await db.commit()
    logger.info(f'Database initialized: {db_path}')


async def upsert_node(db_path: str, node: dict) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO nodes (id, short_name, long_name, latitude, longitude,
                last_heard, snr, battery_level, hop_count, hw_model, is_local, raw_json,
                distance_km)
            VALUES (:id, :short_name, :long_name, :latitude, :longitude,
                :last_heard, :snr, :battery_level, :hop_count, :hw_model, :is_local, :raw_json,
                :distance_km)
            ON CONFLICT(id) DO UPDATE SET
                short_name=excluded.short_name, long_name=excluded.long_name,
                latitude=excluded.latitude, longitude=excluded.longitude,
                last_heard=excluded.last_heard, snr=excluded.snr,
                battery_level=excluded.battery_level, hop_count=excluded.hop_count,
                hw_model=excluded.hw_model, is_local=excluded.is_local,
                raw_json=excluded.raw_json,
                distance_km=excluded.distance_km
        """, node)
        await db.commit()


async def get_all_nodes(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM nodes ORDER BY is_local DESC, last_heard DESC'
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def save_packet(db_path: str, from_id: str, packet_type: str, raw: dict) -> None:
    import time
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            'INSERT INTO packets (ts, from_id, packet_type, raw_json) VALUES (?,?,?,?)',
            (int(time.time()), from_id, packet_type, json.dumps(raw))
        )
        await db.commit()


async def get_markers(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM custom_markers ORDER BY id')
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def create_marker(db_path: str, label: str, icon_type: str,
                        latitude: float, longitude: float) -> dict:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            'INSERT INTO custom_markers (label, icon_type, latitude, longitude) VALUES (?,?,?,?)',
            (label, icon_type, latitude, longitude)
        )
        await db.commit()
        row_id = cursor.lastrowid
    return {'id': row_id, 'label': label, 'icon_type': icon_type,
            'latitude': latitude, 'longitude': longitude}


async def delete_marker(db_path: str, marker_id: int) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            'DELETE FROM custom_markers WHERE id = ?', (marker_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
