import os, shutil, logging, time
import aiosqlite
import config as cfg

async def init_db(runtime_path: str = None, persistent_path: str = None) -> aiosqlite.Connection:
    runtime    = runtime_path    or cfg.DB_RUNTIME
    persistent = persistent_path or cfg.DB_PERSISTENT

    if os.path.exists(persistent):
        shutil.copy2(persistent, runtime)

    conn = await aiosqlite.connect(runtime)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA cache_size=-4000")
    await conn.execute("PRAGMA temp_store=MEMORY")
    await _create_tables(conn)
    return conn

async def _create_tables(conn):
    await conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
    await conn.executescript("""
    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id     TEXT NOT NULL,
        channel     INTEGER DEFAULT 0,
        text        TEXT NOT NULL,
        timestamp   INTEGER NOT NULL,
        is_outgoing INTEGER DEFAULT 0,
        rx_snr      REAL,
        rx_rssi     INTEGER,
        ack         INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS nodes (
        id            TEXT PRIMARY KEY,
        long_name     TEXT,
        short_name    TEXT,
        hw_model      TEXT,
        battery_level INTEGER,
        voltage       REAL,
        snr           REAL,
        last_heard    INTEGER,
        latitude      REAL,
        longitude     REAL,
        altitude      INTEGER,
        is_local      INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS telemetry (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id   TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        type      TEXT NOT NULL,
        value_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_name TEXT NOT NULL,
        timestamp   INTEGER NOT NULL,
        value_json  TEXT NOT NULL
    );
    """)
    await conn.commit()

async def save_message(conn, node_id, channel, text, timestamp, is_outgoing, snr, rssi):
    await conn.execute(
        "INSERT INTO messages (node_id,channel,text,timestamp,is_outgoing,rx_snr,rx_rssi) VALUES (?,?,?,?,?,?,?)",
        (node_id, channel, text, timestamp, is_outgoing, snr, rssi)
    )
    await conn.commit()

async def get_messages(conn, channel: int, limit: int = 50, before_id: int = None) -> list:
    if before_id:
        cur = await conn.execute(
            "SELECT * FROM messages WHERE channel=? AND id<? ORDER BY id DESC LIMIT ?",
            (channel, before_id, limit)
        )
    else:
        cur = await conn.execute(
            "SELECT * FROM messages WHERE channel=? ORDER BY id DESC LIMIT ?",
            (channel, limit)
        )
    rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def get_message_count(conn, channel: int) -> int:
    cur = await conn.execute("SELECT COUNT(*) FROM messages WHERE channel=?", (channel,))
    row = await cur.fetchone()
    return row[0]

async def save_node(conn, node: dict):
    await conn.execute("""
        INSERT OR REPLACE INTO nodes
        (id,long_name,short_name,hw_model,battery_level,voltage,snr,last_heard,latitude,longitude,altitude,is_local)
        VALUES (:id,:long_name,:short_name,:hw_model,:battery_level,:voltage,:snr,:last_heard,:latitude,:longitude,:altitude,:is_local)
    """, node)
    await conn.commit()

async def get_nodes(conn) -> list:
    cur = await conn.execute("SELECT * FROM nodes ORDER BY is_local DESC, last_heard DESC LIMIT 100")
    rows = await cur.fetchall()
    return [dict(r) for r in rows]

async def get_node(conn, node_id: str):
    cur = await conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,))
    row = await cur.fetchone()
    return dict(row) if row else None

async def save_telemetry(conn, node_id: str, type_: str, value_dict: dict):
    import json
    await conn.execute(
        "INSERT INTO telemetry (node_id,timestamp,type,value_json) VALUES (?,?,?,?)",
        (node_id, int(time.time()), type_, json.dumps(value_dict))
    )
    await conn.commit()

async def get_telemetry(conn, node_id: str, type_: str, limit: int = 100) -> list:
    import json
    cur = await conn.execute(
        "SELECT * FROM telemetry WHERE node_id=? AND type=? ORDER BY timestamp DESC LIMIT ?",
        (node_id, type_, limit)
    )
    rows = await cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["values"] = json.loads(d["value_json"])
        result.append(d)
    return result

async def prune_telemetry(conn, max_rows: int = 500):
    cur = await conn.execute("SELECT DISTINCT node_id, type FROM telemetry")
    pairs = await cur.fetchall()
    for node_id, type_ in pairs:
        await conn.execute("""
            DELETE FROM telemetry WHERE id NOT IN (
                SELECT id FROM telemetry WHERE node_id=? AND type=?
                ORDER BY timestamp DESC LIMIT ?
            ) AND node_id=? AND type=?
        """, (node_id, type_, max_rows, node_id, type_))
    await conn.commit()

async def prune_sensor_readings(conn, max_rows: int = 200):
    cur = await conn.execute("SELECT DISTINCT sensor_name FROM sensor_readings")
    names = [row[0] for row in await cur.fetchall()]
    for name in names:
        await conn.execute("""
            DELETE FROM sensor_readings WHERE id NOT IN (
                SELECT id FROM sensor_readings WHERE sensor_name=?
                ORDER BY timestamp DESC LIMIT ?
            ) AND sensor_name=?
        """, (name, max_rows, name))
    await conn.commit()

async def save_sensor_reading(conn, sensor_name: str, value_dict: dict):
    import json
    await conn.execute(
        "INSERT INTO sensor_readings (sensor_name,timestamp,value_json) VALUES (?,?,?)",
        (sensor_name, int(time.time()), json.dumps(value_dict))
    )
    await conn.commit()

async def get_sensor_readings(conn, sensor_name: str, limit: int = 100) -> list:
    import json
    cur = await conn.execute(
        "SELECT * FROM sensor_readings WHERE sensor_name=? ORDER BY timestamp DESC LIMIT ?",
        (sensor_name, limit)
    )
    rows = await cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["values"] = json.loads(d["value_json"])
        result.append(d)
    return result

async def sync_to_sd(conn, runtime_path: str = None, persistent_path: str = None):
    runtime    = runtime_path    or cfg.DB_RUNTIME
    persistent = persistent_path or cfg.DB_PERSISTENT
    try:
        await conn.commit()
        await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        tmp = persistent + ".tmp"
        shutil.copy2(runtime, tmp)
        os.replace(tmp, persistent)
    except Exception as e:
        logging.error(f"Sync DB fallito: {e}")
