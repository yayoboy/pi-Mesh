# database.py
import aiosqlite
import json
import logging
import time

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
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT NOT NULL,
    channel     INTEGER DEFAULT 0,
    text        TEXT NOT NULL,
    ts          INTEGER NOT NULL,
    is_outgoing INTEGER DEFAULT 0,
    rx_snr      REAL,
    hop_count   INTEGER,
    ack         INTEGER DEFAULT 0,
    destination TEXT DEFAULT '^all'
);

CREATE TABLE IF NOT EXISTS dm_reads (
    peer_id      TEXT PRIMARY KEY,
    last_read_ts INTEGER NOT NULL
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
    """Initialize DB with WAL mode and schema. Migrates old messages table if needed."""
    import os
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute('PRAGMA journal_mode=WAL')
        # Migrate messages table if schema predates M3 (node_id column missing)
        cursor = await db.execute("PRAGMA table_info(messages)")
        cols = [row[1] for row in await cursor.fetchall()]
        if cols and 'node_id' not in cols:
            await db.execute('DROP TABLE IF EXISTS messages')
            await db.execute('DROP TABLE IF EXISTS dm_reads')
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


async def bulk_upsert_nodes(db_path: str, nodes: list[dict]) -> None:
    """Upsert multiple nodes in a single transaction."""
    if not nodes:
        return
    async with aiosqlite.connect(db_path) as db:
        for node in nodes:
            await db.execute(
                '''INSERT INTO nodes
                   (id, short_name, long_name, latitude, longitude,
                    last_heard, snr, battery_level, hop_count, hw_model,
                    is_local, raw_json, distance_km)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     short_name=excluded.short_name,
                     long_name=excluded.long_name,
                     latitude=excluded.latitude,
                     longitude=excluded.longitude,
                     last_heard=excluded.last_heard,
                     snr=excluded.snr,
                     battery_level=excluded.battery_level,
                     hop_count=excluded.hop_count,
                     hw_model=excluded.hw_model,
                     is_local=excluded.is_local,
                     raw_json=excluded.raw_json,
                     distance_km=excluded.distance_km''',
                (
                    node.get('id'), node.get('short_name'), node.get('long_name'),
                    node.get('latitude'), node.get('longitude'),
                    node.get('last_heard'), node.get('snr'),
                    node.get('battery_level'), node.get('hop_count'),
                    node.get('hw_model'), node.get('is_local'),
                    node.get('raw_json'), node.get('distance_km'),
                )
            )
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


async def save_message(
    db_path: str, node_id: str, channel: int, text: str,
    ts: int, is_outgoing: bool, rx_snr, hop_count, destination: str
) -> int:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            '''INSERT INTO messages (node_id, channel, text, ts, is_outgoing, rx_snr, hop_count, ack, destination)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)''',
            (node_id, channel, text, ts, 1 if is_outgoing else 0, rx_snr, hop_count, destination)
        )
        await db.commit()
        return cursor.lastrowid


async def get_messages(
    db_path: str, channel: int, limit: int = 50, before_id: int | None = None
) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if before_id is not None:
            cursor = await db.execute(
                '''SELECT * FROM messages WHERE channel = ? AND destination = '^all' AND id < ?
                   ORDER BY id DESC LIMIT ?''',
                (channel, before_id, limit)
            )
        else:
            cursor = await db.execute(
                '''SELECT * FROM messages WHERE channel = ? AND destination = '^all'
                   ORDER BY id DESC LIMIT ?''',
                (channel, limit)
            )
        rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]


async def update_message_ack(db_path: str, node_id: str) -> None:
    """Set ack=1 on the most recent outgoing message to node_id."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            '''UPDATE messages SET ack = 1
               WHERE id = (
                   SELECT id FROM messages
                   WHERE is_outgoing = 1 AND destination = ? AND ack = 0
                   ORDER BY id DESC LIMIT 1
               )''',
            (node_id,)
        )
        await db.commit()


async def clear_messages(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute('DELETE FROM messages')
        await db.execute('DELETE FROM dm_reads')
        await db.commit()


async def cleanup_old_messages(db_path: str, days: int = 30) -> None:
    cutoff = int(time.time()) - days * 86400
    async with aiosqlite.connect(db_path) as db:
        await db.execute('DELETE FROM messages WHERE ts < ?', (cutoff,))
        await db.commit()


async def get_dm_threads(db_path: str, local_id: str) -> list[dict]:
    """Return list of DM conversations with unread count, newest thread first."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Get distinct peer + last message per thread
        cursor = await db.execute("""
            SELECT
                CASE WHEN is_outgoing = 1 THEN destination ELSE node_id END AS peer_id,
                text AS last_text,
                MAX(ts) AS last_ts
            FROM messages
            WHERE destination != '^all'
            GROUP BY CASE WHEN is_outgoing = 1 THEN destination ELSE node_id END
            ORDER BY last_ts DESC
        """)
        threads = [dict(r) for r in await cursor.fetchall()]

        result = []
        for t in threads:
            peer_id = t['peer_id']
            # short_name from nodes table
            c = await db.execute('SELECT short_name FROM nodes WHERE id = ?', (peer_id,))
            row = await c.fetchone()
            short_name = row['short_name'] if row else None
            # unread = incoming msgs since last_read_ts
            c2 = await db.execute(
                'SELECT last_read_ts FROM dm_reads WHERE peer_id = ?', (peer_id,)
            )
            r2 = await c2.fetchone()
            last_read = r2['last_read_ts'] if r2 else 0
            c3 = await db.execute(
                '''SELECT COUNT(*) FROM messages
                   WHERE node_id = ? AND is_outgoing = 0 AND destination = ? AND ts > ?''',
                (peer_id, local_id, last_read)
            )
            r3 = await c3.fetchone()
            unread = r3[0] if r3 else 0
            result.append({
                'peer_id': peer_id,
                'short_name': short_name,
                'last_text': t['last_text'],
                'last_ts': t['last_ts'],
                'unread': unread,
            })
    return result


async def get_dm_messages(
    db_path: str, peer_id: str, local_id: str,
    limit: int = 50, before_id: int | None = None
) -> list[dict]:
    """Return messages in a DM thread (both directions), oldest first."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if before_id is not None:
            cursor = await db.execute(
                '''SELECT * FROM messages
                   WHERE id < ? AND destination != '^all'
                     AND (node_id = ? OR destination = ?)
                   ORDER BY id DESC LIMIT ?''',
                (before_id, peer_id, peer_id, limit)
            )
        else:
            cursor = await db.execute(
                '''SELECT * FROM messages
                   WHERE destination != '^all'
                     AND (node_id = ? OR destination = ?)
                   ORDER BY id DESC LIMIT ?''',
                (peer_id, peer_id, limit)
            )
        rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]


async def mark_dm_read(db_path: str, peer_id: str) -> None:
    """Upsert dm_reads with current timestamp for peer_id."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            '''INSERT INTO dm_reads (peer_id, last_read_ts) VALUES (?, ?)
               ON CONFLICT(peer_id) DO UPDATE SET last_read_ts = excluded.last_read_ts''',
            (peer_id, int(time.time()))
        )
        await db.commit()
