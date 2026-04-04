# database.py
import aiosqlite
import json
import logging
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Persistent connection (WAL mode allows concurrent reads with single writer)
_db: aiosqlite.Connection | None = None
_db_path: str | None = None


@asynccontextmanager
async def _get_db():
    """Async context manager returning a persistent DB connection (no close on exit)."""
    global _db
    if _db is not None:
        try:
            await _db.execute('SELECT 1')
        except Exception:
            _db = None
    if _db is None:
        _db = await aiosqlite.connect(_db_path)
        await _db.execute('PRAGMA journal_mode=WAL')
        await _db.execute('PRAGMA busy_timeout=5000')
    yield _db


async def close() -> None:
    """Close the persistent connection."""
    global _db
    if _db is not None:
        try:
            await _db.close()
        except Exception:
            pass
        _db = None

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
    distance_km REAL,
    rssi INTEGER,
    firmware_version TEXT,
    role TEXT,
    public_key TEXT,
    altitude REAL
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

CREATE TABLE IF NOT EXISTS config_cache (
    section    TEXT NOT NULL,
    key        TEXT NOT NULL DEFAULT 'data',
    value      TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (section, key)
);

CREATE TABLE IF NOT EXISTS gpio_devices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type         TEXT NOT NULL,
    name         TEXT NOT NULL,
    enabled      INTEGER DEFAULT 1,
    pin_a        INTEGER,
    pin_b        INTEGER,
    pin_sw       INTEGER,
    i2c_bus      INTEGER DEFAULT 1,
    i2c_address  TEXT,
    sensor_type  TEXT,
    action       TEXT,
    config_json  TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS telemetry (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,
    node_id   TEXT NOT NULL,
    ttype     TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_node_ts ON telemetry(node_id, ts DESC);

CREATE TABLE IF NOT EXISTS canned_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);
"""


async def init(db_path: str) -> None:
    """Initialize DB with WAL mode and schema. Migrates old messages table if needed."""
    global _db_path
    _db_path = db_path
    import os
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
    async with _get_db() as db:
        await db.execute('PRAGMA journal_mode=WAL')
        # Migrate messages table if schema predates M3 (node_id column missing)
        cursor = await db.execute("PRAGMA table_info(messages)")
        cols = [row[1] for row in await cursor.fetchall()]
        if cols and 'node_id' not in cols:
            await db.execute('DROP TABLE IF EXISTS messages')
            await db.execute('DROP TABLE IF EXISTS dm_reads')
        await db.executescript(_SCHEMA)

        # Migrate nodes table if distance_km column missing (M4 addition)
        cursor = await db.execute("PRAGMA table_info(nodes)")
        node_cols = [row[1] for row in await cursor.fetchall()]
        if node_cols and 'distance_km' not in node_cols:
            logger.info('Migrating nodes table: adding distance_km column')
            await db.execute('ALTER TABLE nodes ADD COLUMN distance_km REAL')

        # Migrate nodes table: add advanced fields (M5 — YAY-107)
        for col, col_type in [
            ('rssi', 'INTEGER'),
            ('firmware_version', 'TEXT'),
            ('role', 'TEXT'),
            ('public_key', 'TEXT'),
            ('altitude', 'REAL'),
        ]:
            if col not in node_cols:
                logger.info('Migrating nodes table: adding %s column', col)
                await db.execute(f'ALTER TABLE nodes ADD COLUMN {col} {col_type}')

        await db.commit()
    logger.info(f'Database initialized: {db_path}')


async def upsert_node(db_path: str, node: dict) -> None:
    async with _get_db() as db:
        await db.execute("""
            INSERT INTO nodes (id, short_name, long_name, latitude, longitude,
                last_heard, snr, battery_level, hop_count, hw_model, is_local, raw_json,
                distance_km, rssi, firmware_version, role, public_key, altitude)
            VALUES (:id, :short_name, :long_name, :latitude, :longitude,
                :last_heard, :snr, :battery_level, :hop_count, :hw_model, :is_local, :raw_json,
                :distance_km, :rssi, :firmware_version, :role, :public_key, :altitude)
            ON CONFLICT(id) DO UPDATE SET
                short_name=excluded.short_name, long_name=excluded.long_name,
                latitude=excluded.latitude, longitude=excluded.longitude,
                last_heard=excluded.last_heard, snr=excluded.snr,
                battery_level=excluded.battery_level, hop_count=excluded.hop_count,
                hw_model=excluded.hw_model, is_local=excluded.is_local,
                raw_json=excluded.raw_json,
                distance_km=excluded.distance_km,
                rssi=excluded.rssi,
                firmware_version=excluded.firmware_version,
                role=excluded.role,
                public_key=excluded.public_key,
                altitude=excluded.altitude
        """, node)
        await db.commit()


async def bulk_upsert_nodes(db_path: str, nodes: list[dict]) -> None:
    """Upsert multiple nodes in a single transaction."""
    if not nodes:
        return
    async with _get_db() as db:
        for node in nodes:
            await db.execute(
                '''INSERT INTO nodes
                   (id, short_name, long_name, latitude, longitude,
                    last_heard, snr, battery_level, hop_count, hw_model,
                    is_local, raw_json, distance_km,
                    rssi, firmware_version, role, public_key, altitude)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                     distance_km=excluded.distance_km,
                     rssi=excluded.rssi,
                     firmware_version=excluded.firmware_version,
                     role=excluded.role,
                     public_key=excluded.public_key,
                     altitude=excluded.altitude''',
                (
                    node.get('id'), node.get('short_name'), node.get('long_name'),
                    node.get('latitude'), node.get('longitude'),
                    node.get('last_heard'), node.get('snr'),
                    node.get('battery_level'), node.get('hop_count'),
                    node.get('hw_model'), node.get('is_local'),
                    node.get('raw_json'), node.get('distance_km'),
                    node.get('rssi'), node.get('firmware_version'),
                    node.get('role'), node.get('public_key'),
                    node.get('altitude'),
                )
            )
        await db.commit()


async def get_all_nodes(db_path: str) -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM nodes ORDER BY is_local DESC, last_heard DESC'
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def delete_node(db_path: str, node_id: str, purge: bool = False) -> None:
    """Delete a node from DB. If purge=True, also remove messages and telemetry."""
    async with _get_db() as db:
        if purge:
            await db.execute('DELETE FROM messages WHERE node_id = ?', (node_id,))
            await db.execute('DELETE FROM packets WHERE from_id = ?', (node_id,))
        await db.execute('DELETE FROM nodes WHERE id = ?', (node_id,))
        await db.commit()


async def save_telemetry(db_path: str, node_id: str, ttype: str, data: dict) -> int:
    ts = int(time.time())
    async with _get_db() as db:
        cursor = await db.execute(
            'INSERT INTO telemetry (ts, node_id, ttype, data_json) VALUES (?,?,?,?)',
            (ts, node_id, ttype, json.dumps(data))
        )
        await db.commit()
        return cursor.lastrowid


async def get_telemetry(db_path: str, node_id: str | None = None,
                        ttype: str | None = None, limit: int = 100,
                        since: int | None = None) -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        where = []
        params = []
        if node_id:
            where.append('node_id = ?')
            params.append(node_id)
        if ttype:
            where.append('ttype = ?')
            params.append(ttype)
        if since:
            where.append('ts > ?')
            params.append(since)
        clause = ('WHERE ' + ' AND '.join(where)) if where else ''
        cursor = await db.execute(
            f'SELECT * FROM telemetry {clause} ORDER BY ts DESC LIMIT ?',
            params + [limit]
        )
        rows = await cursor.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['data'] = json.loads(d.pop('data_json'))
        result.append(d)
    return result


async def cleanup_telemetry(db_path: str, max_age_hours: int = 72) -> None:
    cutoff = int(time.time()) - (max_age_hours * 3600)
    async with _get_db() as db:
        await db.execute('DELETE FROM telemetry WHERE ts < ?', (cutoff,))
        await db.commit()


async def get_canned_messages() -> list:
    async with _get_db() as db:
        cur = await db.execute(
            'SELECT id, text, sort_order FROM canned_messages ORDER BY sort_order, id'
        )
        rows = await cur.fetchall()
        return [{'id': r[0], 'text': r[1], 'sort_order': r[2]} for r in rows]


async def add_canned_message(text: str, sort_order: int = 0) -> int:
    async with _get_db() as db:
        cur = await db.execute(
            'INSERT INTO canned_messages (text, sort_order) VALUES (?, ?)',
            (text, sort_order)
        )
        await db.commit()
        return cur.lastrowid


async def update_canned_message(msg_id: int, text: str, sort_order: int) -> None:
    async with _get_db() as db:
        await db.execute(
            'UPDATE canned_messages SET text=?, sort_order=? WHERE id=?',
            (text, sort_order, msg_id)
        )
        await db.commit()


async def delete_canned_message(msg_id: int) -> None:
    async with _get_db() as db:
        await db.execute('DELETE FROM canned_messages WHERE id=?', (msg_id,))
        await db.commit()


async def save_packet(db_path: str, from_id: str, packet_type: str, raw: dict) -> None:
    async with _get_db() as db:
        await db.execute(
            'INSERT INTO packets (ts, from_id, packet_type, raw_json) VALUES (?,?,?,?)',
            (int(time.time()), from_id, packet_type, json.dumps(raw))
        )
        await db.commit()


async def get_markers(db_path: str) -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM custom_markers ORDER BY id')
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def create_marker(db_path: str, label: str, icon_type: str,
                        latitude: float, longitude: float) -> dict:
    async with _get_db() as db:
        cursor = await db.execute(
            'INSERT INTO custom_markers (label, icon_type, latitude, longitude) VALUES (?,?,?,?)',
            (label, icon_type, latitude, longitude)
        )
        await db.commit()
        row_id = cursor.lastrowid
    return {'id': row_id, 'label': label, 'icon_type': icon_type,
            'latitude': latitude, 'longitude': longitude}


async def delete_marker(db_path: str, marker_id: int) -> bool:
    async with _get_db() as db:
        cursor = await db.execute(
            'DELETE FROM custom_markers WHERE id = ?', (marker_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def save_message(
    db_path: str, node_id: str, channel: int, text: str,
    ts: int, is_outgoing: bool, rx_snr, hop_count, destination: str
) -> int:
    async with _get_db() as db:
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
    async with _get_db() as db:
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
    async with _get_db() as db:
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
    async with _get_db() as db:
        await db.execute('DELETE FROM messages')
        await db.execute('DELETE FROM dm_reads')
        await db.commit()


async def cleanup_old_messages(db_path: str, days: int = 30) -> None:
    cutoff = int(time.time()) - days * 86400
    async with _get_db() as db:
        await db.execute('DELETE FROM messages WHERE ts < ?', (cutoff,))
        await db.commit()


async def get_dm_threads(db_path: str, local_id: str) -> list[dict]:
    """Return list of DM conversations with unread count, newest thread first."""
    async with _get_db() as db:
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
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        base_where = """destination != '^all' AND (
            (node_id = ? AND destination = ?) OR
            (node_id = ? AND destination = ?)
        )"""
        # params order: peer→local, local→peer
        params = (peer_id, local_id, local_id, peer_id)
        if before_id is not None:
            cursor = await db.execute(
                f'SELECT * FROM messages WHERE id < ? AND {base_where} ORDER BY id DESC LIMIT ?',
                (before_id, *params, limit)
            )
        else:
            cursor = await db.execute(
                f'SELECT * FROM messages WHERE {base_where} ORDER BY id DESC LIMIT ?',
                (*params, limit)
            )
        rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]


async def mark_dm_read(db_path: str, peer_id: str) -> None:
    """Upsert dm_reads with current timestamp for peer_id."""
    async with _get_db() as db:
        await db.execute(
            '''INSERT INTO dm_reads (peer_id, last_read_ts) VALUES (?, ?)
               ON CONFLICT(peer_id) DO UPDATE SET last_read_ts = excluded.last_read_ts''',
            (peer_id, int(time.time()))
        )
        await db.commit()


async def get_total_unread(db_path: str, local_id: str) -> int:
    """Return total unread DM count across all peers."""
    async with _get_db() as db:
        c = await db.execute('''
            SELECT COALESCE(SUM(cnt), 0) FROM (
                SELECT COUNT(*) as cnt
                FROM messages m
                LEFT JOIN dm_reads dr ON dr.peer_id = m.node_id
                WHERE m.destination = ?
                  AND m.node_id != ?
                  AND m.ts > COALESCE(dr.last_read_ts, 0)
            )
        ''', (local_id, local_id))
        row = await c.fetchone()
        return row[0] if row else 0


async def get_config_cache(db_path: str, section: str) -> dict | None:
    """Return cached config for section, or None if not cached."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            'SELECT value FROM config_cache WHERE section = ? AND key = ?',
            (section, 'data')
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row['value'])


async def set_config_cache(db_path: str, section: str, data: dict) -> None:
    """Upsert config cache for section."""
    async with _get_db() as db:
        await db.execute(
            'INSERT INTO config_cache (section, key, value, updated_at) VALUES (?, ?, ?, ?)'
            ' ON CONFLICT(section, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at',
            (section, 'data', json.dumps(data), int(time.time()))
        )
        await db.commit()


async def get_gpio_devices(db_path: str) -> list[dict]:
    """Return all GPIO devices."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute('SELECT * FROM gpio_devices ORDER BY id')
        return [dict(r) for r in await cur.fetchall()]


async def add_gpio_device(db_path: str, device: dict) -> int:
    """Insert a new GPIO device. Returns new id."""
    async with _get_db() as db:
        cur = await db.execute(
            '''INSERT INTO gpio_devices
               (type, name, enabled, pin_a, pin_b, pin_sw, i2c_bus, i2c_address,
                sensor_type, action, config_json)
               VALUES (:type, :name, :enabled, :pin_a, :pin_b, :pin_sw, :i2c_bus,
                       :i2c_address, :sensor_type, :action, :config_json)''',
            device
        )
        await db.commit()
        return cur.lastrowid


async def update_gpio_device(db_path: str, device_id: int, device: dict) -> None:
    """Update an existing GPIO device."""
    async with _get_db() as db:
        await db.execute(
            '''UPDATE gpio_devices SET
               type=:type, name=:name, enabled=:enabled, pin_a=:pin_a, pin_b=:pin_b,
               pin_sw=:pin_sw, i2c_bus=:i2c_bus, i2c_address=:i2c_address,
               sensor_type=:sensor_type, action=:action, config_json=:config_json
               WHERE id=:id''',
            {**device, 'id': device_id}
        )
        await db.commit()


async def delete_gpio_device(db_path: str, device_id: int) -> None:
    """Delete a GPIO device."""
    async with _get_db() as db:
        await db.execute('DELETE FROM gpio_devices WHERE id = ?', (device_id,))
        await db.commit()
