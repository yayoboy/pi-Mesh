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
    raw_json TEXT
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
                last_heard, snr, battery_level, hop_count, hw_model, is_local, raw_json)
            VALUES (:id, :short_name, :long_name, :latitude, :longitude,
                :last_heard, :snr, :battery_level, :hop_count, :hw_model, :is_local, :raw_json)
            ON CONFLICT(id) DO UPDATE SET
                short_name=excluded.short_name, long_name=excluded.long_name,
                latitude=excluded.latitude, longitude=excluded.longitude,
                last_heard=excluded.last_heard, snr=excluded.snr,
                battery_level=excluded.battery_level, hop_count=excluded.hop_count,
                hw_model=excluded.hw_model, is_local=excluded.is_local,
                raw_json=excluded.raw_json
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
