# Meshtastic Pi — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Costruire un'app Python/FastAPI su Raspberry Pi che funge da nodo Meshtastic con UI web locale su display Waveshare 3.5" SPI (480×320 landscape / 320×480 portrait), parità funzionale con l'app Meshtastic mobile.

**Architecture:** FastAPI + uvicorn su asyncio single-thread. meshtastic-python e gpiozero girano in thread separati e usano `asyncio.run_coroutine_threadsafe()` per comunicare con l'event loop. SQLite lavora su tmpfs e viene sincronizzato sulla SD periodicamente.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, aiosqlite, meshtastic-python, pypubsub, gpiozero, pigpio, smbus2, Leaflet.js, Chart.js, pytest, unittest.mock

**Riprendibilità:** Aggiorna `PROGRESS.md` dopo ogni task completato (`[x]`). Per riprendere: trova il primo `[ ]`.

---

## Task 0: Setup progetto

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `config.env`
- Create: `tests/__init__.py`

**Step 1: Crea struttura directory**

```bash
cd /home/pi/meshtastic-pi   # o il tuo path locale
mkdir -p templates static/tiles/{osm,topo} data tests bots docs/plans
touch tests/__init__.py
```

**Step 2: Crea `requirements.txt`**

```
fastapi
uvicorn[standard]
meshtastic
pypubsub
aiosqlite
gpiozero
smbus2
```

**Step 3: Crea `requirements-dev.txt`**

```
pytest
pytest-asyncio
httpx
anyio
```

**Step 4: Crea `config.env`**

```bash
# Percorsi
SERIAL_PORT=/dev/ttyMESHTASTIC
DB_PERSISTENT=/home/pi/meshtastic-pi/data/mesh.db
DB_SYNC_INTERVAL=300

# GPIO encoder 1 (navigazione globale)
ENC1_A=17
ENC1_B=27
ENC1_SW=22

# GPIO encoder 2 (contestuale)
ENC2_A=5
ENC2_B=6
ENC2_SW=13

# Sensori I2C (formato: "bme280:0x76,ina219:0x40" oppure vuoto)
I2C_SENSORS=

# Mappa (Italia centrale come default)
MAP_LAT_MIN=41.0
MAP_LAT_MAX=43.0
MAP_LON_MIN=11.5
MAP_LON_MAX=14.5
MAP_ZOOM_MIN=8
MAP_ZOOM_MAX=12

# Display
DISPLAY_ROTATION=0

# UI
UI_THEME=dark
```

**Step 5: Installa dipendenze**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

**Step 6: Commit**

```bash
git init
git add requirements.txt requirements-dev.txt config.env tests/ docs/
git commit -m "chore: project scaffold"
```

**Aggiorna PROGRESS.md:** `[x] M1-S0 setup`

---

## Task 1: config.py

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

**Step 1: Scrivi il test**

```python
# tests/test_config.py
import os, pytest

def test_serial_port_default(monkeypatch):
    monkeypatch.delenv("SERIAL_PORT", raising=False)
    import importlib, config
    importlib.reload(config)
    assert config.SERIAL_PORT == "/dev/ttyMESHTASTIC"

def test_serial_port_override(monkeypatch):
    monkeypatch.setenv("SERIAL_PORT", "/dev/ttyUSB0")
    import importlib, config
    importlib.reload(config)
    assert config.SERIAL_PORT == "/dev/ttyUSB0"

def test_parse_sensor_config_empty():
    from config import parse_sensor_config
    assert parse_sensor_config("") == []

def test_parse_sensor_config_valid():
    from config import parse_sensor_config
    result = parse_sensor_config("bme280:0x76,ina219:0x40")
    assert result == [
        {"name": "bme280", "address": 0x76},
        {"name": "ina219", "address": 0x40},
    ]

def test_parse_sensor_config_invalid_skips():
    from config import parse_sensor_config
    result = parse_sensor_config("bme280:0x76,badentry,ina219:0x40")
    assert len(result) == 2
```

**Step 2: Verifica fallimento**

```bash
pytest tests/test_config.py -v
# Expected: ImportError o ModuleNotFoundError
```

**Step 3: Implementa `config.py`**

```python
import os

def parse_sensor_config(s: str) -> list:
    result = []
    if not s.strip():
        return result
    for entry in s.split(","):
        entry = entry.strip()
        try:
            name, addr_str = entry.split(":")
            result.append({"name": name.strip(), "address": int(addr_str.strip(), 16)})
        except (ValueError, TypeError):
            pass
    return result

# Percorsi
SERIAL_PORT      = os.getenv("SERIAL_PORT", "/dev/ttyMESHTASTIC")
DB_PERSISTENT    = os.getenv("DB_PERSISTENT", "/home/pi/meshtastic-pi/data/mesh.db")
DB_RUNTIME       = "/tmp/mesh_runtime.db"
DB_SYNC_INTERVAL = int(os.getenv("DB_SYNC_INTERVAL", "300"))

# GPIO encoder
ENC1_A  = int(os.getenv("ENC1_A", "17"))
ENC1_B  = int(os.getenv("ENC1_B", "27"))
ENC1_SW = int(os.getenv("ENC1_SW", "22"))
ENC2_A  = int(os.getenv("ENC2_A", "5"))
ENC2_B  = int(os.getenv("ENC2_B", "6"))
ENC2_SW = int(os.getenv("ENC2_SW", "13"))

# Sensori I2C
I2C_SENSORS = parse_sensor_config(os.getenv("I2C_SENSORS", ""))

# Mappa
MAP_BOUNDS = {
    "lat_min": float(os.getenv("MAP_LAT_MIN", "41.0")),
    "lat_max": float(os.getenv("MAP_LAT_MAX", "43.0")),
    "lon_min": float(os.getenv("MAP_LON_MIN", "11.5")),
    "lon_max": float(os.getenv("MAP_LON_MAX", "14.5")),
}
MAP_ZOOM_MIN = int(os.getenv("MAP_ZOOM_MIN", "8"))
MAP_ZOOM_MAX = int(os.getenv("MAP_ZOOM_MAX", "12"))

# Display
DISPLAY_ROTATION = int(os.getenv("DISPLAY_ROTATION", "0"))

# UI
UI_THEME = os.getenv("UI_THEME", "dark")

# Limiti memoria
MAX_MESSAGES_PER_CHANNEL = 200
MAX_NODES_IN_MEMORY      = 100
```

**Step 4: Verifica i test**

```bash
pytest tests/test_config.py -v
# Expected: 5 passed
```

**Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat(M1-S1): config.py con parse_sensor_config"
```

**Aggiorna PROGRESS.md:** `[x] M1-S1`

---

## Task 2: database.py

**Files:**
- Create: `database.py`
- Create: `tests/test_database.py`

**Step 1: Scrivi i test**

```python
# tests/test_database.py
import asyncio, os, pytest, time
import pytest_asyncio

@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test.db")

@pytest.mark.asyncio
async def test_init_creates_tables(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in await cur.fetchall()}
    assert {"messages", "nodes", "telemetry", "sensor_readings"} <= tables
    await conn.close()

@pytest.mark.asyncio
async def test_save_and_get_message(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    ts = int(time.time())
    await database.save_message(conn, "node1", 0, "hello", ts, 0, 1.5, -90)
    msgs = await database.get_messages(conn, 0, limit=10)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "hello"
    await conn.close()

@pytest.mark.asyncio
async def test_save_and_get_node(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    await database.save_node(conn, {
        "id": "abc123", "long_name": "Test Node", "short_name": "TST",
        "hw_model": "HELTEC_V3", "battery_level": 80, "voltage": 3.8,
        "snr": 5.0, "last_heard": int(time.time()),
        "latitude": 41.9, "longitude": 12.5, "altitude": 50, "is_local": 1
    })
    nodes = await database.get_nodes(conn)
    assert len(nodes) == 1
    assert nodes[0]["id"] == "abc123"
    await conn.close()

@pytest.mark.asyncio
async def test_sync_to_sd(tmp_db, tmp_path):
    import database
    persistent = str(tmp_path / "persistent.db")
    conn = await database.init_db(runtime_path=tmp_db)
    await database.sync_to_sd(conn, runtime_path=tmp_db, persistent_path=persistent)
    assert os.path.exists(persistent)
    await conn.close()

@pytest.mark.asyncio
async def test_get_messages_pagination(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    for i in range(10):
        await database.save_message(conn, "n1", 0, f"msg{i}", i+1, 0, None, None)
    page1 = await database.get_messages(conn, 0, limit=5)
    assert len(page1) == 5
    oldest_id = page1[-1]["id"]
    page2 = await database.get_messages(conn, 0, limit=5, before_id=oldest_id)
    assert len(page2) == 5
    await conn.close()
```

**Step 2: Verifica fallimento**

```bash
pytest tests/test_database.py -v
# Expected: ImportError
```

**Step 3: Aggiungi a `pytest.ini` (o `pyproject.toml`)**

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
```

**Step 4: Implementa `database.py`**

```python
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

async def get_node(conn, node_id: str) -> dict | None:
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
```

**Step 5: Verifica i test**

```bash
pytest tests/test_database.py -v
# Expected: 5 passed
```

**Step 6: Commit**

```bash
git add database.py tests/test_database.py pytest.ini
git commit -m "feat(M1-S2): database.py con aiosqlite + sync SD-safe"
```

**Aggiorna PROGRESS.md:** `[x] M1-S2`

---

## Task 3: meshtastic_client.py

> Nota: questo modulo usa hardware reale (porta seriale). I test usano mock.

**Files:**
- Create: `meshtastic_client.py`
- Create: `tests/test_meshtastic_client.py`

**Step 1: Scrivi i test**

```python
# tests/test_meshtastic_client.py
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

@pytest.fixture(autouse=True)
def reset_module():
    import meshtastic_client as mc
    mc._interface  = None
    mc._connected  = False
    mc._loop       = None
    mc._broadcast  = None
    yield

def test_is_connected_false_initially():
    import meshtastic_client as mc
    assert mc.is_connected() is False

def test_init_sets_loop_and_broadcast():
    import meshtastic_client as mc
    loop = asyncio.new_event_loop()
    broadcast = AsyncMock()
    mc.init(loop, broadcast)
    assert mc._loop is loop
    assert mc._broadcast is broadcast
    loop.close()

def test_parse_message_valid():
    import meshtastic_client as mc
    packet = {
        "fromId": "!abc123",
        "channel": 1,
        "decoded": {"text": "ciao"},
        "rxTime": 1700000000,
        "rxSnr": 7.5,
        "rxRssi": -90,
    }
    result = mc._parse_message(packet)
    assert result["node_id"] == "!abc123"
    assert result["text"] == "ciao"
    assert result["rx_snr"] == 7.5

def test_parse_message_malformed_returns_none():
    import meshtastic_client as mc
    result = mc._parse_message(None)
    assert result is None

@pytest.mark.asyncio
async def test_connect_sets_connected_on_success():
    import meshtastic_client as mc
    with patch("meshtastic.serial_interface.SerialInterface") as mock_si:
        mock_si.return_value = MagicMock()
        mc._loop = asyncio.get_event_loop()
        mc._broadcast = AsyncMock()
        await mc.connect()
        assert mc.is_connected() is True
```

**Step 2: Verifica fallimento**

```bash
pytest tests/test_meshtastic_client.py -v
# Expected: ImportError
```

**Step 3: Implementa `meshtastic_client.py`**

```python
import asyncio, logging, time
from pubsub import pub
import meshtastic.serial_interface
import config as cfg

_interface  = None
_loop       = None
_broadcast  = None
_connected  = False
_conn_getter = None   # callable che restituisce la connessione DB, impostato da main.py

def init(loop, broadcast_fn, conn_getter=None):
    global _loop, _broadcast, _conn_getter
    _loop        = loop
    _broadcast   = broadcast_fn
    _conn_getter = conn_getter
    pub.subscribe(_on_receive_text,      "meshtastic.receive.text")
    pub.subscribe(_on_receive_telemetry, "meshtastic.receive.telemetry")
    pub.subscribe(_on_receive_position,  "meshtastic.receive.position")
    pub.subscribe(_on_receive_user,      "meshtastic.receive.user")
    pub.subscribe(_on_connected,         "meshtastic.connection.established")
    pub.subscribe(_on_lost,              "meshtastic.connection.lost")

def _bridge(coro):
    if _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(coro, _loop)

async def connect():
    global _interface, _connected
    while True:
        try:
            _interface = meshtastic.serial_interface.SerialInterface(cfg.SERIAL_PORT)
            _connected = True
            logging.info("Connesso a Heltec V3")
            return
        except Exception as e:
            _connected = False
            logging.warning(f"Connessione fallita ({e}), riprovo in 10s...")
            await asyncio.sleep(10)

async def disconnect():
    global _interface, _connected
    if _interface:
        try:
            _interface.close()
        except Exception:
            pass
        _interface = None
    _connected = False

def is_connected() -> bool:
    return _connected

def get_local_node() -> dict | None:
    if not _interface:
        return None
    try:
        node = _interface.getNode('^local')
        info = _interface.getMyNodeInfo()
        return {
            "id":         info.get("user", {}).get("id"),
            "long_name":  info.get("user", {}).get("longName"),
            "short_name": info.get("user", {}).get("shortName"),
            "hw_model":   info.get("user", {}).get("hwModel"),
        }
    except Exception:
        return None

async def send_message(text: str, channel: int = 0, destination: str = "^all"):
    if not _interface:
        raise RuntimeError("Non connesso")
    _interface.sendText(text, channelIndex=channel, destinationId=destination)

async def set_config(config_dict: dict):
    if not _interface:
        raise RuntimeError("Non connesso")
    node = _interface.getNode('^local')
    for section, values in config_dict.items():
        cfg_section = getattr(node.localConfig, section, None)
        if cfg_section is None:
            cfg_section = getattr(node.moduleConfig, section, None)
        if cfg_section:
            for k, v in values.items():
                setattr(cfg_section, k, v)
            node.writeConfig(section)

async def request_position(node_id: str):
    if _interface:
        _interface.sendPosition(destinationId=node_id)

# --- Callback pubsub (girano in thread separati) ---

def _on_connected(interface, topic=pub.AUTO_TOPIC):
    global _connected
    _connected = True
    _bridge(_broadcast({"type": "status", "data": {"connected": True}}))

def _on_lost(interface, topic=pub.AUTO_TOPIC):
    global _connected
    _connected = False
    _bridge(_broadcast({"type": "status", "data": {"connected": False}}))

def _on_receive_text(packet, interface):
    _bridge(_handle_message(packet))

async def _handle_message(packet):
    import database
    data = _parse_message(packet)
    if data and _conn_getter:
        await database.save_message(_conn_getter(), **data)
        await _broadcast({"type": "message", "data": data})

def _on_receive_user(packet, interface):
    _bridge(_handle_user(packet))

async def _handle_user(packet):
    import database, time
    try:
        user = packet.get("decoded", {}).get("user", {})
        node = {
            "id":            packet.get("fromId", "unknown"),
            "long_name":     user.get("longName", ""),
            "short_name":    user.get("shortName", ""),
            "hw_model":      user.get("hwModel", ""),
            "battery_level": None,
            "voltage":       None,
            "snr":           packet.get("rxSnr"),
            "last_heard":    packet.get("rxTime", int(time.time())),
            "latitude":      None,
            "longitude":     None,
            "altitude":      None,
            "is_local":      0,
        }
        if _conn_getter:
            await database.save_node(_conn_getter(), node)
        await _broadcast({"type": "node", "data": node})
    except Exception as e:
        logging.error(f"Parsing user fallito: {e}")

def _on_receive_position(packet, interface):
    _bridge(_handle_position(packet))

async def _handle_position(packet):
    try:
        pos = packet.get("decoded", {}).get("position", {})
        data = {
            "node_id":   packet.get("fromId", "unknown"),
            "latitude":  pos.get("latitudeI", 0) / 1e7 if pos.get("latitudeI") else None,
            "longitude": pos.get("longitudeI", 0) / 1e7 if pos.get("longitudeI") else None,
            "altitude":  pos.get("altitude"),
        }
        await _broadcast({"type": "position", "data": data})
    except Exception as e:
        logging.error(f"Parsing position fallito: {e}")

def _on_receive_telemetry(packet, interface):
    _bridge(_handle_telemetry(packet))

async def _handle_telemetry(packet):
    import database
    try:
        telem = packet.get("decoded", {}).get("telemetry", {})
        node_id = packet.get("fromId", "unknown")
        for type_ in ("deviceMetrics", "environmentMetrics", "powerMetrics"):
            values = telem.get(type_)
            if values and _conn_getter:
                await database.save_telemetry(_conn_getter(), node_id, type_, dict(values))
                await _broadcast({"type": "telemetry", "data": {
                    "node_id": node_id, "type": type_, "values": dict(values)
                }})
    except Exception as e:
        logging.error(f"Parsing telemetry fallito: {e}")

def _parse_message(packet) -> dict | None:
    try:
        decoded = packet.get("decoded", {})
        return {
            "node_id":      packet.get("fromId", "unknown"),
            "channel":      packet.get("channel", 0),
            "text":         decoded.get("text", ""),
            "timestamp":    packet.get("rxTime", int(time.time())),
            "is_outgoing":  0,
            "snr":          packet.get("rxSnr"),
            "rssi":         packet.get("rxRssi"),
        }
    except Exception as e:
        logging.error(f"Parsing messaggio fallito: {e}")
        return None
```

**Step 4: Verifica i test**

```bash
pytest tests/test_meshtastic_client.py -v
# Expected: 5 passed
```

**Step 5: Commit**

```bash
git add meshtastic_client.py tests/test_meshtastic_client.py
git commit -m "feat(M1-S3): meshtastic_client con bridge thread→asyncio"
```

**Aggiorna PROGRESS.md:** `[x] M1-S3`

---

## Task 4: watchdog.py

**Files:**
- Create: `watchdog.py`
- Create: `tests/test_watchdog.py`

**Step 1: Scrivi i test**

```python
# tests/test_watchdog.py
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

@pytest.mark.asyncio
async def test_db_sync_task_calls_sync(monkeypatch):
    import watchdog, database
    sync_called = []
    async def fake_sync(conn, **kw):
        sync_called.append(1)
    monkeypatch.setattr(database, "sync_to_sd", fake_sync)
    conn = MagicMock()
    task = asyncio.create_task(watchdog.db_sync_task(conn, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    assert len(sync_called) >= 1

@pytest.mark.asyncio
async def test_memory_watchdog_collects_gc(monkeypatch):
    import watchdog, gc
    gc_collected = []
    monkeypatch.setattr(gc, "collect", lambda: gc_collected.append(1))
    broadcast = AsyncMock()
    # simula RAM alta (> 120MB) patchando resource
    fake_usage = MagicMock()
    fake_usage.ru_maxrss = 130 * 1024  # 130MB in KB
    with patch("resource.getrusage", return_value=fake_usage):
        task = asyncio.create_task(watchdog.memory_watchdog_task(broadcast, interval=0.01))
        await asyncio.sleep(0.05)
        task.cancel()
    assert len(gc_collected) >= 1
```

**Step 2: Verifica fallimento**

```bash
pytest tests/test_watchdog.py -v
# Expected: ImportError
```

**Step 3: Implementa `watchdog.py`**

```python
import asyncio, gc, logging, os, signal
import database, meshtastic_client
import config as cfg

async def db_sync_task(conn, interval: int = None):
    interval = interval or cfg.DB_SYNC_INTERVAL
    while True:
        await asyncio.sleep(interval)
        await database.sync_to_sd(conn)
        logging.debug("DB sincronizzato su SD")

async def connection_watchdog_task(broadcast_fn, interval: int = 30):
    while True:
        await asyncio.sleep(interval)
        if not meshtastic_client.is_connected():
            logging.warning("Connessione persa, tentativo reconnect...")
            await meshtastic_client.connect()
            await broadcast_fn({"type": "status", "data": {
                "connected": meshtastic_client.is_connected()
            }})

async def memory_watchdog_task(broadcast_fn, interval: int = 60):
    import resource
    while True:
        await asyncio.sleep(interval)
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = rss_kb / 1024
        if rss_mb > 120:
            logging.warning(f"RAM alta: {rss_mb:.1f}MB")
            gc.collect()
        if rss_mb > 150:
            logging.error(f"RAM critica: {rss_mb:.1f}MB — riavvio")
            await broadcast_fn({"type": "status", "data": {"warning": "riavvio per memoria"}})
            await asyncio.sleep(2)
            os.kill(os.getpid(), signal.SIGTERM)

async def db_maintenance_task(conn, interval: int = 3600):
    while True:
        await asyncio.sleep(interval)
        await database.prune_telemetry(conn)
        await conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

def start_all(conn, broadcast_fn):
    loop = asyncio.get_event_loop()
    loop.create_task(db_sync_task(conn))
    loop.create_task(connection_watchdog_task(broadcast_fn))
    loop.create_task(memory_watchdog_task(broadcast_fn))
    loop.create_task(db_maintenance_task(conn))
```

**Step 4: Verifica i test**

```bash
pytest tests/test_watchdog.py -v
# Expected: 2 passed
```

**Step 5: Commit**

```bash
git add watchdog.py tests/test_watchdog.py
git commit -m "feat(M1-S4): watchdog — sync DB, RAM, connessione, manutenzione"
```

**Aggiorna PROGRESS.md:** `[x] M1-S4`

---

## Task 5: main.py scheletro + WebSocket

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

**Step 1: Scrivi i test**

```python
# tests/test_main.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_db_conn():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.commit  = AsyncMock()
    return conn

@pytest.mark.asyncio
async def test_root_redirects_to_messages():
    with patch("database.init_db", new_callable=AsyncMock) as mock_db, \
         patch("meshtastic_client.init"), \
         patch("meshtastic_client.connect", new_callable=AsyncMock), \
         patch("sensor_handler.init", return_value=[]), \
         patch("gpio_handler.init"), \
         patch("watchdog.start_all"):
        mock_db.return_value = MagicMock()
        from main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)

@pytest.mark.asyncio
async def test_api_status_returns_json():
    with patch("database.init_db", new_callable=AsyncMock) as mock_db, \
         patch("meshtastic_client.init"), \
         patch("meshtastic_client.connect", new_callable=AsyncMock), \
         patch("meshtastic_client.is_connected", return_value=True), \
         patch("database.get_nodes", new_callable=AsyncMock, return_value=[]), \
         patch("sensor_handler.init", return_value=[]), \
         patch("gpio_handler.init"), \
         patch("watchdog.start_all"):
        mock_db.return_value = MagicMock()
        from main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        assert "ram_mb" in data
```

**Step 2: Verifica fallimento**

```bash
pytest tests/test_main.py -v
# Expected: ImportError
```

**Step 3: Implementa `main.py`**

```python
import asyncio, gc, logging, os, signal, subprocess, sys, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config as cfg
import database, meshtastic_client, gpio_handler, sensor_handler, watchdog

gc.set_threshold(100, 5, 5)

ws_clients: set[WebSocket] = set()
_conn = None
_keyboard_proc = None

def get_conn():
    return _conn

async def broadcast(data: dict):
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    ws_clients -= dead

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn
    logging.basicConfig(level=logging.INFO)

    _conn = await database.init_db()
    loop  = asyncio.get_event_loop()

    meshtastic_client.init(loop, broadcast, get_conn)
    asyncio.create_task(meshtastic_client.connect())

    drivers = sensor_handler.init(cfg.I2C_SENSORS)
    asyncio.create_task(sensor_handler.start_polling(drivers, _conn, broadcast))

    gpio_handler.init(
        (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        broadcast
    )

    watchdog.start_all(_conn, broadcast)

    def handle_sigterm(sig, frame):
        asyncio.create_task(_shutdown())
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT,  handle_sigterm)

    yield

    await _shutdown()

async def _shutdown():
    logging.info("Shutdown in corso...")
    await meshtastic_client.disconnect()
    await database.sync_to_sd(_conn)
    await _conn.close()
    logging.info("Shutdown completato")
    sys.exit(0)

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/tiles",  StaticFiles(directory="static/tiles"), name="tiles")
templates = Jinja2Templates(directory="templates")

# --- Route pagine ---

@app.get("/")
async def root():
    return RedirectResponse("/messages")

@app.get("/messages")
async def messages_page(request: Request):
    msgs = await database.get_messages(_conn, channel=0, limit=50)
    return templates.TemplateResponse("messages.html", {
        "request": request, "messages": msgs,
        "theme": cfg.UI_THEME, "active": "messages"
    })

@app.get("/nodes")
async def nodes_page(request: Request):
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse("nodes.html", {
        "request": request, "nodes": nodes,
        "theme": cfg.UI_THEME, "active": "nodes"
    })

@app.get("/map")
async def map_page(request: Request):
    return templates.TemplateResponse("map.html", {
        "request": request,
        "bounds":    cfg.MAP_BOUNDS,
        "zoom_min":  cfg.MAP_ZOOM_MIN,
        "zoom_max":  cfg.MAP_ZOOM_MAX,
        "theme":     cfg.UI_THEME,
        "active":    "map"
    })

@app.get("/telemetry")
async def telemetry_page(request: Request):
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse("telemetry.html", {
        "request": request, "nodes": nodes,
        "theme": cfg.UI_THEME, "active": "telemetry"
    })

@app.get("/settings")
async def settings_page(request: Request):
    node_info = meshtastic_client.get_local_node()
    return templates.TemplateResponse("settings.html", {
        "request": request, "node": node_info,
        "theme": cfg.UI_THEME, "active": "settings",
        "enc1": (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        "enc2": (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        "i2c_sensors": cfg.I2C_SENSORS,
        "display_rotation": cfg.DISPLAY_ROTATION,
    })

# --- Route API JSON ---

@app.post("/send")
async def send_message(payload: dict):
    text        = payload.get("text", "").strip()
    channel     = int(payload.get("channel", 0))
    destination = payload.get("destination", "^all")
    if not text:
        return JSONResponse({"ok": False, "error": "testo vuoto"}, 400)
    try:
        await meshtastic_client.send_message(text, channel, destination)
        await database.save_message(_conn, "local", channel, text, int(time.time()), 1, None, None)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)

@app.post("/settings")
async def apply_settings(payload: dict):
    try:
        await meshtastic_client.set_config(payload)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)

@app.get("/api/nodes")
async def api_nodes():
    return await database.get_nodes(_conn)

@app.get("/api/messages")
async def api_messages(channel: int = 0, limit: int = 50, before_id: int = None):
    return await database.get_messages(_conn, channel, limit, before_id)

@app.get("/api/telemetry/{node_id}/{type_}")
async def api_telemetry(node_id: str, type_: str, limit: int = 100):
    return await database.get_telemetry(_conn, node_id, type_, limit)

@app.get("/api/sensor/{sensor_name}")
async def api_sensor(sensor_name: str, limit: int = 100):
    return await database.get_sensor_readings(_conn, sensor_name, limit)

@app.get("/api/status")
async def api_status():
    import resource
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return {
        "connected":  meshtastic_client.is_connected(),
        "node_count": len(await database.get_nodes(_conn)),
        "ram_mb":     round(rss_mb, 1),
    }

@app.post("/api/keyboard/show")
async def keyboard_show():
    global _keyboard_proc
    if _keyboard_proc is None or _keyboard_proc.poll() is not None:
        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        _keyboard_proc = subprocess.Popen(["matchbox-keyboard"], env=env)
    return {"ok": True}

@app.post("/api/keyboard/hide")
async def keyboard_hide():
    global _keyboard_proc
    if _keyboard_proc and _keyboard_proc.poll() is None:
        _keyboard_proc.terminate()
        _keyboard_proc = None
    return {"ok": True}

# --- WebSocket ---

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "init",
            "data": {
                "connected": meshtastic_client.is_connected(),
                "nodes":     await database.get_nodes(_conn),
                "messages":  await database.get_messages(_conn, 0, 50),
                "theme":     cfg.UI_THEME,
            }
        })
        while True:
            await asyncio.wait_for(websocket.receive_text(), timeout=30)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        pass
    except Exception as e:
        logging.debug(f"WS disconnesso: {e}")
    finally:
        ws_clients.discard(websocket)
```

**Step 4: Verifica i test**

```bash
pytest tests/test_main.py -v
# Expected: 2 passed
```

**Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(M2-S1): main.py FastAPI + WebSocket + tutte le route"
```

**Aggiorna PROGRESS.md:** `[x] M2-S1`

---

## Task 6: CSS + base.html dual-orientation + temi

**Files:**
- Create: `static/style.css`
- Create: `templates/base.html`

**Step 1: Crea `static/style.css`**

```css
/* ===== TEMI ===== */
.theme-dark {
  --bg:       #1a1a1a;
  --bg2:      #242424;
  --border:   #333;
  --text:     #e0e0e0;
  --muted:    #888;
  --accent:   #4a9eff;
  --ok:       #4caf50;
  --warn:     #ff9800;
  --danger:   #f44336;
}
.theme-light {
  --bg:       #f5f5f5;
  --bg2:      #ffffff;
  --border:   #ddd;
  --text:     #1a1a1a;
  --muted:    #666;
  --accent:   #1565c0;
  --ok:       #2e7d32;
  --warn:     #e65100;
  --danger:   #c62828;
}
.theme-hc {
  --bg:       #000000;
  --bg2:      #111111;
  --border:   #ffffff;
  --text:     #ffffff;
  --muted:    #cccccc;
  --accent:   #ffff00;
  --ok:       #00ff00;
  --warn:     #ff8800;
  --danger:   #ff0000;
}

/* ===== RESET ===== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ===== BODY LANDSCAPE (default 480×320) ===== */
body {
  background: var(--bg);
  color: var(--text);
  font-family: sans-serif;
  font-size: 14px;
  width: 480px;
  height: 320px;
  overflow: hidden;
  touch-action: manipulation;
  -webkit-text-size-adjust: none;
}

/* ===== BODY PORTRAIT (320×480) ===== */
@media (orientation: portrait) {
  body {
    width: 320px;
    height: 480px;
  }
}

/* ===== LAYOUT VARIABILI ===== */
:root {
  --tabbar-h:    48px;
  --statusbar-h: 20px;
}

/* ===== STATUS BAR ===== */
#status-bar {
  height: var(--statusbar-h);
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 8px;
  gap: 8px;
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
}

/* ===== CONTENT AREA ===== */
#content {
  height: calc(320px - var(--statusbar-h) - var(--tabbar-h));
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
  background: var(--bg);
}
#content::-webkit-scrollbar { display: none; }

@media (orientation: portrait) {
  #content {
    height: calc(480px - var(--statusbar-h) - var(--tabbar-h));
  }
}

/* ===== TAB BAR ===== */
#tabbar {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: var(--tabbar-h);
  background: var(--bg2);
  border-top: 1px solid var(--border);
  display: flex;
}
.tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  text-decoration: none;
  font-size: 10px;
  flex-direction: column;
  gap: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
}
.tab.active { color: var(--accent); }
.tab svg { width: 20px; height: 20px; fill: currentColor; }

/* ===== BADGE CONNESSIONE ===== */
#connection-badge { color: var(--danger); font-size: 14px; line-height: 1; }
#connection-badge.connected { color: var(--ok); }

/* ===== INPUT/BUTTON ===== */
input, select, button, textarea {
  min-height: 44px;
  font-size: 16px;
  background: var(--bg2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0 10px;
  width: 100%;
}
button {
  background: var(--accent);
  color: #fff;
  border: none;
  cursor: pointer;
}
button:active { opacity: 0.8; }

/* ===== LISTE ===== */
.list-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  min-height: 48px;
}
.list-item:active { background: var(--bg2); }

/* ===== MESSAGGI ===== */
#msg-list { padding: 4px 0; }
.msg-row {
  padding: 4px 12px;
  max-width: 100%;
}
.msg-row.outgoing { text-align: right; }
.msg-bubble {
  display: inline-block;
  background: var(--bg2);
  border-radius: 8px;
  padding: 4px 8px;
  max-width: 85%;
  word-break: break-word;
}
.msg-row.outgoing .msg-bubble { background: var(--accent); color: #fff; }
.msg-meta { font-size: 10px; color: var(--muted); margin-top: 2px; }

/* ===== FORM INVIO ===== */
#send-form {
  display: flex;
  gap: 4px;
  padding: 4px 8px;
  background: var(--bg2);
  border-top: 1px solid var(--border);
  position: sticky;
  bottom: 0;
}
#send-form input { flex: 1; min-height: 36px; font-size: 14px; }
#send-form button { width: 60px; min-height: 36px; flex-shrink: 0; }

/* ===== MAPPA ===== */
#map-container { width: 100%; height: 100%; }

/* ===== BADGE STATO NODO ===== */
.node-badge {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-right: 8px;
}
.node-badge.online  { background: var(--ok); }
.node-badge.recent  { background: var(--warn); }
.node-badge.offline { background: var(--muted); }

/* ===== GRAFICI ===== */
.chart-wrap { padding: 8px; }
canvas { max-width: 100%; }

/* ===== SETTINGS ===== */
.settings-section { padding: 8px 12px; }
.settings-label {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 4px 0;
}
.settings-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.settings-row label { flex: 1; font-size: 13px; }
.settings-row input,
.settings-row select { flex: 1; min-height: 36px; font-size: 13px; }

**Step 2: Crea `templates/base.html`**

```html
<!DOCTYPE html>
<html lang="it" class="theme-{{ theme }}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Meshtastic</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="theme-{{ theme }}">
  <div id="status-bar">
    <span id="connection-badge">●</span>
    <span id="node-name"></span>
    <span style="flex:1"></span>
    <span id="ram-badge"></span>
  </div>
  <main id="content">
    {% block content %}{% endblock %}
  </main>
  <nav id="tabbar">
    <a href="/messages" class="tab {% if active=='messages' %}active{% endif %}" data-tab="messages">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
      <span>Msg</span>
    </a>
    <a href="/nodes" class="tab {% if active=='nodes' %}active{% endif %}" data-tab="nodes">
      <svg viewBox="0 0 24 24"><path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg>
      <span>Nodi</span>
    </a>
    <a href="/map" class="tab {% if active=='map' %}active{% endif %}" data-tab="map">
      <svg viewBox="0 0 24 24"><path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/></svg>
      <span>Mappa</span>
    </a>
    <a href="/telemetry" class="tab {% if active=='telemetry' %}active{% endif %}" data-tab="telemetry">
      <svg viewBox="0 0 24 24"><path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z"/></svg>
      <span>Telem</span>
    </a>
    <a href="/settings" class="tab {% if active=='settings' %}active{% endif %}" data-tab="settings">
      <svg viewBox="0 0 24 24"><path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61 l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41 h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87 C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58 c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54 c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96 c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6 s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/></svg>
      <span>Config</span>
    </a>
  </nav>
  <script src="/static/app.js"></script>
</body>
</html>
```

**Step 3: Test visivo su Surf**

```bash
# Sul Pi, con uvicorn avviato:
surf http://localhost:8080/messages &
# Verifica: status bar visibile, tab bar in basso, nessun overflow
# Ruota display (modifica /boot/config.txt display_rotate=1) → verifica portrait
```

**Step 4: Commit**

```bash
git add static/style.css templates/base.html
git commit -m "feat(M2-S2): CSS dual-orientation + temi dark/light/hc + base.html"
```

**Aggiorna PROGRESS.md:** `[x] M2-S2`

---

## Task 7: app.js

**Files:**
- Create: `static/app.js`

```javascript
// static/app.js

// ===== STATO GLOBALE =====
let ws = null
let wsReady = false
const activeTab = { name: document.querySelector('.tab.active')?.dataset.tab || 'messages' }
const nodeCache = new Map()
const messageCache = []

// ===== WEBSOCKET =====
function initWS() {
  ws = new WebSocket('ws://localhost:8080/ws')

  ws.onopen = () => {
    wsReady = true
    document.getElementById('connection-badge').classList.add('connected')
  }

  ws.onclose = () => {
    wsReady = false
    document.getElementById('connection-badge').classList.remove('connected')
    setTimeout(initWS, 3000)
  }

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    const handlers = {
      init:      handleInit,
      message:   handleMessage,
      node:      handleNode,
      position:  handlePosition,
      telemetry: handleTelemetry,
      sensor:    handleSensor,
      encoder:   handleEncoder,
      status:    handleStatus,
    }
    handlers[msg.type]?.(msg.data)
  }

  setInterval(() => { if (wsReady) ws.send('ping') }, 20000)
}

// ===== HANDLER MESSAGGI WS =====
function handleInit(data) {
  updateConnectionStatus(data.connected)
  data.nodes.forEach(n => nodeCache.set(n.id, n))
  if (activeTab.name === 'messages') renderMessages(data.messages)
  if (data.theme) applyTheme(data.theme)
}

function handleMessage(data) {
  messageCache.unshift(data)
  if (messageCache.length > 200) messageCache.pop()
  if (activeTab.name === 'messages') appendMessage(data)
}

function handleNode(data) {
  nodeCache.set(data.id, data)
  if (activeTab.name === 'nodes') updateNodeRow(data)
  if (activeTab.name === 'map' && mapReady) updateMapMarker(data)
}

function handlePosition(data) {
  const node = nodeCache.get(data.node_id)
  if (node) {
    node.latitude  = data.latitude
    node.longitude = data.longitude
    if (activeTab.name === 'map' && mapReady) updateMapMarker(node)
  }
}

function handleTelemetry(data) {
  if (activeTab.name === 'telemetry') updateTelemetryChart(data)
}

function handleSensor(data) {
  if (activeTab.name === 'telemetry') updateSensorDisplay(data)
}

function handleStatus(data) {
  if (data.connected !== undefined) updateConnectionStatus(data.connected)
  if (data.ram_mb) {
    const el = document.getElementById('ram-badge')
    if (el) el.textContent = data.ram_mb + 'MB'
  }
}

function updateConnectionStatus(connected) {
  const badge = document.getElementById('connection-badge')
  if (!badge) return
  badge.classList.toggle('connected', connected)
}

// ===== ENCODER =====
function handleEncoder(data) {
  const { encoder, action } = data
  if (encoder === 1) {
    const tabs = ['messages', 'nodes', 'map', 'telemetry', 'settings']
    const current = tabs.indexOf(activeTab.name)
    if (action === 'cw' && current < tabs.length - 1) navigateTo(tabs[current + 1])
    else if (action === 'ccw' && current > 0) navigateTo(tabs[current - 1])
    else if (action === 'long_press') navigateTo('messages')
    return
  }
  if (encoder === 2) {
    const handlers = {
      messages:  enc2Messages,
      nodes:     enc2Nodes,
      map:       enc2Map,
      telemetry: enc2Telemetry,
      settings:  enc2Settings,
    }
    handlers[activeTab.name]?.(action)
  }
}

function enc2Messages(action) {
  const list = document.getElementById('msg-list')
  if (list) list.scrollTop += (action === 'cw' ? 48 : -48)
}
function enc2Nodes(action) {
  const list = document.getElementById('node-list')
  if (list) list.scrollTop += (action === 'cw' ? 48 : -48)
}
function enc2Map(action) {
  if (!mapReady) return
  if (action === 'cw') leafletMap.zoomIn()
  if (action === 'ccw') leafletMap.zoomOut()
}
function enc2Telemetry(action) {
  const el = document.getElementById('content')
  if (el) el.scrollTop += (action === 'cw' ? 48 : -48)
}
function enc2Settings(action) {
  const el = document.getElementById('content')
  if (el) el.scrollTop += (action === 'cw' ? 48 : -48)
}

// ===== NAVIGAZIONE SENZA RELOAD =====
async function navigateTo(tabName) {
  if (tabName === activeTab.name) return
  activeTab.name = tabName

  const response = await fetch('/' + tabName)
  const html     = await response.text()
  const parser   = new DOMParser()
  const doc      = parser.parseFromString(html, 'text/html')
  const newContent = doc.getElementById('content')
  if (newContent) document.getElementById('content').innerHTML = newContent.innerHTML

  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabName)
  })

  if (tabName === 'map')       initMapIfNeeded()
  if (tabName === 'telemetry') initChartsIfNeeded()
  attachKeyboardListeners()
}

// ===== TASTIERA =====
function attachKeyboardListeners() {
  document.querySelectorAll('input[type=text], input[type=number], textarea').forEach(el => {
    el.addEventListener('focus', () => fetch('/api/keyboard/show', { method: 'POST' }))
    el.addEventListener('blur', () => {
      setTimeout(() => fetch('/api/keyboard/hide', { method: 'POST' }), 200)
    })
  })
}

// ===== MESSAGGI =====
function renderMessages(messages) {
  const list = document.getElementById('msg-list')
  if (!list) return
  list.innerHTML = ''
  ;[...messages].reverse().forEach(m => appendMessage(m))
}

function appendMessage(m) {
  const list = document.getElementById('msg-list')
  if (!list) return
  const div = document.createElement('div')
  div.className = 'msg-row' + (m.is_outgoing ? ' outgoing' : '')
  const name = nodeCache.get(m.node_id)?.short_name || m.node_id
  const ts   = new Date(m.timestamp * 1000).toLocaleTimeString('it', { hour: '2-digit', minute: '2-digit' })
  div.innerHTML = `
    <div class="msg-bubble">${escHtml(m.text)}</div>
    <div class="msg-meta">${m.is_outgoing ? '' : escHtml(name) + ' · '}${ts}${m.rx_snr != null ? ' · ' + m.rx_snr + 'dB' : ''}</div>
  `
  list.appendChild(div)
  list.scrollTop = list.scrollHeight
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

// ===== TEMA =====
function applyTheme(theme) {
  document.body.className = 'theme-' + theme
  document.documentElement.className = 'theme-' + theme
}

// ===== MAPPA =====
let leafletMap = null
let mapReady = false
const markerCache = new Map()

function initMapIfNeeded() {
  if (mapReady || typeof L === 'undefined') return
  const bounds = window.MAP_BOUNDS
  if (!bounds) return
  const center = [(bounds.lat_min + bounds.lat_max) / 2, (bounds.lon_min + bounds.lon_max) / 2]

  leafletMap = L.map('map-container', {
    center, zoom: 10, zoomControl: false,
    maxBounds: [[bounds.lat_min, bounds.lon_min], [bounds.lat_max, bounds.lon_max]],
    maxBoundsViscosity: 1.0,
  })

  const osmLayer  = L.tileLayer('/tiles/osm/{z}/{x}/{y}.png',  { maxZoom: window.MAP_ZOOM_MAX })
  const topoLayer = L.tileLayer('/tiles/topo/{z}/{x}/{y}.png', { maxZoom: window.MAP_ZOOM_MAX })
  osmLayer.addTo(leafletMap)
  L.control.layers({ 'Stradale': osmLayer, 'Topo': topoLayer }).addTo(leafletMap)

  nodeCache.forEach(node => updateMapMarker(node))
  mapReady = true
}

function updateMapMarker(node) {
  if (!node.latitude || !node.longitude || !mapReady) return
  const color = node.is_local ? '#4a9eff' : '#4caf50'
  const existing = markerCache.get(node.id)
  if (existing) {
    existing.setLatLng([node.latitude, node.longitude])
  } else {
    const marker = L.circleMarker([node.latitude, node.longitude], {
      radius: 8, color, fillColor: color, fillOpacity: 0.8
    })
    marker.bindPopup(`<b>${node.short_name || node.id}</b><br>${node.long_name || ''}<br>SNR: ${node.snr ?? '—'} dB<br>Batt: ${node.battery_level ?? '—'}%`)
    marker.addTo(leafletMap)
    markerCache.set(node.id, marker)
  }
}

// ===== GRAFICI (stub, completato in Task telemetry) =====
function initChartsIfNeeded() { /* implementato in telemetry.html inline */ }
function updateTelemetryChart(data) { window.dispatchEvent(new CustomEvent('telemetry-update', { detail: data })) }
function updateSensorDisplay(data) { window.dispatchEvent(new CustomEvent('sensor-update', { detail: data })) }
function updateNodeRow(data) { window.dispatchEvent(new CustomEvent('node-update', { detail: data })) }

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
  initWS()
  attachKeyboardListeners()
  // link tab bar a navigateTo
  document.querySelectorAll('.tab[data-tab]').forEach(t => {
    t.addEventListener('click', e => {
      e.preventDefault()
      navigateTo(t.dataset.tab)
    })
  })
})
```

**Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat(M2-S3): app.js WebSocket client + encoder handler + navigazione"
```

**Aggiorna PROGRESS.md:** `[x] M2-S3`

---

## Task 8: messages.html

**Files:**
- Create: `templates/messages.html`

```html
{% extends "base.html" %}
{% block content %}
<div id="msg-list" style="height: calc(100% - 52px); overflow-y:auto; padding: 4px 0;">
  {% for m in messages|reverse %}
  <div class="msg-row {% if m.is_outgoing %}outgoing{% endif %}">
    <div class="msg-bubble">{{ m.text }}</div>
    <div class="msg-meta">
      {% if not m.is_outgoing %}{{ m.node_id }} · {% endif %}
      {{ m.timestamp|int }}
      {% if m.rx_snr is not none %} · {{ m.rx_snr }}dB{% endif %}
    </div>
  </div>
  {% endfor %}
  <div id="load-more"></div>
</div>
<form id="send-form" onsubmit="sendMsg(event)">
  <select id="ch-select" style="width:48px; min-height:36px; font-size:13px; flex-shrink:0;">
    <option value="0">0</option>
    <option value="1">1</option>
    <option value="2">2</option>
  </select>
  <input id="msg-input" type="text" placeholder="Messaggio..." autocomplete="off">
  <button type="submit">▶</button>
</form>
<script>
async function sendMsg(e) {
  e.preventDefault()
  const text = document.getElementById('msg-input').value.trim()
  const ch   = parseInt(document.getElementById('ch-select').value)
  if (!text) return
  const r = await fetch('/send', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ text, channel: ch })
  })
  if (r.ok) document.getElementById('msg-input').value = ''
}

// Scroll infinito verso il passato
const sentinel = document.getElementById('load-more')
let loadingMore = false
let oldestId = null

new IntersectionObserver(async ([entry]) => {
  if (!entry.isIntersecting || loadingMore) return
  const items = document.querySelectorAll('.msg-row')
  if (items.length === 0) return
  loadingMore = true
  const firstId = items[0].dataset.msgId
  if (!firstId) { loadingMore = false; return }
  const resp = await fetch(`/api/messages?channel=0&limit=50&before_id=${firstId}`)
  const msgs = await resp.json()
  const list = document.getElementById('msg-list')
  const prevH = list.scrollHeight
  msgs.forEach(m => {
    const div = document.createElement('div')
    div.className = 'msg-row' + (m.is_outgoing ? ' outgoing' : '')
    div.dataset.msgId = m.id
    div.innerHTML = `<div class="msg-bubble">${m.text}</div><div class="msg-meta">${m.node_id} · ${new Date(m.timestamp*1000).toLocaleTimeString('it',{hour:'2-digit',minute:'2-digit'})}</div>`
    list.insertBefore(div, list.firstChild)
  })
  list.scrollTop = list.scrollHeight - prevH
  loadingMore = false
}).observe(sentinel)
</script>
{% endblock %}
```

**Step 2: Test su Surf**

```
http://localhost:8080/messages
- Messaggi presenti nel DB appaiono
- Focus input → matchbox keyboard appare
- Invio messaggio → appare nella lista
- Scroll in cima → carica messaggi precedenti
```

**Step 3: Commit**

```bash
git add templates/messages.html
git commit -m "feat(M2-S4): messages.html con scroll infinito e form invio"
```

**Aggiorna PROGRESS.md:** `[x] M2-S4`

---

## Task 9: nodes.html

**Files:**
- Create: `templates/nodes.html`

```html
{% extends "base.html" %}
{% block content %}
<div id="node-list">
{% for n in nodes %}
<div class="list-item" onclick="toggleDetail('{{ n.id }}')" style="flex-direction:column; align-items:stretch; cursor:pointer;">
  <div style="display:flex; align-items:center; gap:8px;">
    <div class="node-badge" id="badge-{{ n.id }}"></div>
    <div style="flex:1">
      <div style="font-weight:bold;">{{ n.short_name or n.id }}</div>
      <div style="font-size:11px; color:var(--muted);">{{ n.long_name or '' }}</div>
    </div>
    <div style="font-size:11px; color:var(--muted); text-align:right;">
      {% if n.battery_level is not none %}🔋{{ n.battery_level }}%{% endif %}<br>
      {% if n.snr is not none %}SNR {{ n.snr }}dB{% endif %}
    </div>
  </div>
  <div id="detail-{{ n.id }}" style="display:none; padding-top:8px; font-size:12px; color:var(--muted); border-top:1px solid var(--border); margin-top:8px;">
    HW: {{ n.hw_model or '—' }}<br>
    {% if n.latitude %}Pos: {{ '%.4f'|format(n.latitude) }}, {{ '%.4f'|format(n.longitude) }}<br>{% endif %}
    <button onclick="reqPos('{{ n.id }}')" style="min-height:32px; margin-top:4px; width:auto; padding:0 12px; font-size:12px;">📍 Richiedi pos</button>
  </div>
</div>
{% endfor %}
</div>
<script>
// Badge stato in base a last_heard
document.querySelectorAll('[id^="badge-"]').forEach(badge => {
  const nodeId = badge.id.replace('badge-','')
  // last_heard è iniettato come data attribute nel template
})

// Aggiorna badge via JS con nodeCache dal parent
window.addEventListener('node-update', e => {
  const n = e.detail
  updateBadge(n.id, n.last_heard)
})

function updateBadge(id, lastHeard) {
  const badge = document.getElementById('badge-' + id)
  if (!badge) return
  const ago = Date.now()/1000 - lastHeard
  badge.className = 'node-badge ' + (ago < 300 ? 'online' : ago < 1800 ? 'recent' : 'offline')
}

// Inizializza badge
{% for n in nodes %}
updateBadge('{{ n.id }}', {{ n.last_heard or 0 }})
{% endfor %}

function toggleDetail(id) {
  const el = document.getElementById('detail-' + id)
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none'
}

async function reqPos(nodeId) {
  await fetch('/send', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ text: '', destination: nodeId, type: 'position_request' })
  })
}
</script>
{% endblock %}
```

**Step 2: Commit**

```bash
git add templates/nodes.html
git commit -m "feat(M2-S5): nodes.html con badge stato e dettaglio inline"
```

**Aggiorna PROGRESS.md:** `[x] M2-S5`

---

## Task 10: map.html + tile offline

**Files:**
- Create: `templates/map.html`

**Step 1: Scarica tile offline (esegui sul Pi, una volta)**

```bash
# Installa tile downloader
pip install owntracks-tileserver  # oppure usa wget con osmtiles

# Oppure usa questo script minimale per scaricare tile Italia zoom 8-12:
python3 - << 'EOF'
import os, urllib.request, time

def download_tiles(lat_min, lat_max, lon_min, lon_max, zoom_min, zoom_max, out_dir):
    import math
    def deg2tile(lat, lon, z):
        n = 2**z
        x = int((lon + 180) / 360 * n)
        y = int((1 - math.log(math.tan(math.radians(lat)) + 1/math.cos(math.radians(lat))) / math.pi) / 2 * n)
        return x, y
    for z in range(zoom_min, zoom_max+1):
        x0, y0 = deg2tile(lat_max, lon_min, z)
        x1, y1 = deg2tile(lat_min, lon_max, z)
        for x in range(x0, x1+1):
            for y in range(y0, y1+1):
                path = f"{out_dir}/{z}/{x}/{y}.png"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if not os.path.exists(path):
                    url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                    urllib.request.urlretrieve(url, path)
                    time.sleep(0.1)  # rispetta rate limit OSM

download_tiles(41.0, 43.0, 11.5, 14.5, 8, 12, "static/tiles/osm")
EOF
```

**Step 2: Crea `templates/map.html`**

```html
{% extends "base.html" %}
{% block content %}
<div id="map-container" style="width:100%; height:100%;"></div>
<link rel="stylesheet" href="/static/leaflet.css">
<script src="/static/leaflet.min.js"></script>
<script>
window.MAP_BOUNDS   = {{ bounds | tojson }};
window.MAP_ZOOM_MAX = {{ zoom_max }};
window.MAP_ZOOM_MIN = {{ zoom_min }};
// initMapIfNeeded è chiamata da app.js quando il tab diventa attivo
document.addEventListener('DOMContentLoaded', initMapIfNeeded)
</script>
{% endblock %}
```

**Step 3: Scarica leaflet.min.js e leaflet.css**

```bash
cd static
curl -L https://unpkg.com/leaflet@1.9.4/dist/leaflet.min.js -o leaflet.min.js
curl -L https://unpkg.com/leaflet@1.9.4/dist/leaflet.css   -o leaflet.css
# Poi carica i file .png delle icone Leaflet default in static/images/
curl -L https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png    -o images/marker-icon.png
curl -L https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png  -o images/marker-shadow.png
```

**Step 4: Commit**

```bash
git add templates/map.html static/leaflet.min.js static/leaflet.css
git commit -m "feat(M2-S6): map.html Leaflet + tile offline"
```

**Aggiorna PROGRESS.md:** `[x] M2-S6`

---

## Task 11: gpio_handler.py

> Nota: richiede pigpio daemon in esecuzione (`sudo pigpiod`). I test usano mock.

**Files:**
- Create: `gpio_handler.py`
- Create: `tests/test_gpio_handler.py`

**Step 1: Scrivi i test**

```python
# tests/test_gpio_handler.py
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio, pytest

def test_init_calls_gpiozero_with_correct_pins():
    mock_enc = MagicMock()
    mock_btn = MagicMock()
    broadcast = AsyncMock()
    with patch('gpiozero.RotaryEncoder', return_value=mock_enc) as MockRE, \
         patch('gpiozero.Button',        return_value=mock_btn) as MockBtn, \
         patch('gpiozero.pins.pigpio.PiGPIOFactory', return_value=MagicMock()):
        import gpio_handler
        gpio_handler.init((17, 27, 22), (5, 6, 13), broadcast)
        assert MockRE.call_count == 2
        assert MockBtn.call_count == 2

def test_bridge_event_sends_to_loop():
    loop = asyncio.new_event_loop()
    broadcast = AsyncMock()
    import gpio_handler
    gpio_handler._loop = loop
    gpio_handler._broadcast = broadcast
    # non crashare
    gpio_handler._bridge_event(1, 'cw')
    loop.close()
```

**Step 2: Implementa `gpio_handler.py`**

```python
import asyncio, logging, time
from unittest.mock import MagicMock

_loop      = None
_broadcast = None
_conn      = None

try:
    from gpiozero import RotaryEncoder, Button
    from gpiozero.pins.pigpio import PiGPIOFactory
    _factory = PiGPIOFactory()
    _GPIO_AVAILABLE = True
except Exception:
    logging.warning("gpiozero/pigpio non disponibile — GPIO disabilitato")
    _GPIO_AVAILABLE = False

def init(enc1_pins: tuple, enc2_pins: tuple, broadcast_fn, loop=None):
    global _loop, _broadcast
    _broadcast = broadcast_fn
    _loop = loop or asyncio.get_event_loop()

    if not _GPIO_AVAILABLE:
        return

    enc1 = RotaryEncoder(enc1_pins[0], enc1_pins[1], pin_factory=_factory, wrap=False, max_steps=0)
    btn1 = Button(enc1_pins[2], pin_factory=_factory, hold_time=1.0)
    enc2 = RotaryEncoder(enc2_pins[0], enc2_pins[1], pin_factory=_factory, wrap=False, max_steps=0)
    btn2 = Button(enc2_pins[2], pin_factory=_factory, hold_time=1.0)

    def make_handler(encoder_num, action):
        def handler():
            _bridge_event(encoder_num, action)
        return handler

    enc1.when_rotated_clockwise          = make_handler(1, "cw")
    enc1.when_rotated_counter_clockwise  = make_handler(1, "ccw")
    btn1.when_pressed                    = make_handler(1, "press")
    btn1.when_held                       = make_handler(1, "long_press")
    enc2.when_rotated_clockwise          = make_handler(2, "cw")
    enc2.when_rotated_counter_clockwise  = make_handler(2, "ccw")
    btn2.when_pressed                    = make_handler(2, "press")
    btn2.when_held                       = make_handler(2, "long_press")

    # Gesture shutdown: press lungo simultaneo entrambi gli encoder per 3s
    import database as db_module
    def check_shutdown():
        if btn1.is_held and btn2.is_held:
            logging.info("Gesture shutdown rilevata")
            _bridge_coroutine(_graceful_shutdown())
    btn1.when_held = check_shutdown
    btn2.when_held = check_shutdown

def _bridge_event(encoder_num: int, action: str):
    if _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(
            _broadcast({"type": "encoder", "data": {
                "encoder": encoder_num,
                "action":  action,
                "ts":      int(time.time())
            }}),
            _loop
        )

def _bridge_coroutine(coro):
    if _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(coro, _loop)

async def _graceful_shutdown():
    import database, os
    if _conn:
        await database.sync_to_sd(_conn)
    os.system("sudo shutdown -h now")
```

**Step 3: Verifica i test**

```bash
pytest tests/test_gpio_handler.py -v
# Expected: 2 passed
```

**Step 4: Commit**

```bash
git add gpio_handler.py tests/test_gpio_handler.py
git commit -m "feat(M3-S1): gpio_handler con gpiozero/pigpio + gesture shutdown"
```

**Aggiorna PROGRESS.md:** `[x] M3-S1`

---

## Task 12: sensor_handler.py

**Files:**
- Create: `sensor_handler.py`
- Create: `tests/test_sensor_handler.py`

**Step 1: Scrivi i test**

```python
# tests/test_sensor_handler.py
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

def test_init_returns_empty_list_for_no_sensors():
    import sensor_handler
    result = sensor_handler.init([])
    assert result == []

def test_init_skips_unavailable_sensor():
    import sensor_handler
    with patch.object(sensor_handler, '_make_driver') as mock_make:
        mock_driver = MagicMock()
        mock_driver.available.return_value = False
        mock_make.return_value = mock_driver
        result = sensor_handler.init([{"name": "bme280", "address": 0x76}])
        assert result == []

@pytest.mark.asyncio
async def test_polling_calls_broadcast(tmp_path):
    import sensor_handler, database
    conn = await database.init_db(runtime_path=str(tmp_path / "t.db"))
    mock_driver = MagicMock()
    mock_driver.name = "bme280"
    mock_driver.read.return_value = {"temp": 22.0}
    broadcast = AsyncMock()
    task = asyncio.create_task(
        sensor_handler.start_polling([mock_driver], conn, broadcast, interval=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    assert broadcast.called
    await conn.close()
```

**Step 2: Implementa `sensor_handler.py`**

```python
import asyncio, logging, time

try:
    import smbus2
    _SMBUS_AVAILABLE = True
except ImportError:
    logging.warning("smbus2 non disponibile — sensori I2C disabilitati")
    _SMBUS_AVAILABLE = False


class BaseSensor:
    def __init__(self, address: int):
        self.address = address
        self._bus = smbus2.SMBus(1) if _SMBUS_AVAILABLE else None

    def read(self) -> dict | None:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError

    def available(self) -> bool:
        if not _SMBUS_AVAILABLE:
            return False
        try:
            self._bus.read_byte(self.address)
            return True
        except OSError:
            return False


class BME280Driver(BaseSensor):
    @property
    def name(self): return "bme280"

    def read(self) -> dict | None:
        try:
            import bme280
            calibration_params = bme280.load_calibration_params(self._bus, self.address)
            data = bme280.sample(self._bus, self.address, calibration_params)
            return {"temp": round(data.temperature, 1), "humidity": round(data.humidity, 1), "pressure": round(data.pressure, 1)}
        except Exception as e:
            logging.error(f"BME280 read error: {e}")
            return None


class INA219Driver(BaseSensor):
    @property
    def name(self): return "ina219"

    def read(self) -> dict | None:
        try:
            from ina219 import INA219
            ina = INA219(0.1, busnum=1, address=self.address)
            ina.configure()
            return {"voltage": round(ina.voltage(), 2), "current": round(ina.current(), 1), "power": round(ina.power(), 1)}
        except Exception as e:
            logging.error(f"INA219 read error: {e}")
            return None


_DRIVER_MAP = {
    "bme280": BME280Driver,
    "ina219": INA219Driver,
}

def _make_driver(name: str, address: int) -> BaseSensor | None:
    cls = _DRIVER_MAP.get(name)
    if cls:
        return cls(address)
    logging.warning(f"Driver sconosciuto: {name}")
    return None

def init(sensor_config_list: list) -> list:
    drivers = []
    for cfg in sensor_config_list:
        driver = _make_driver(cfg["name"], cfg["address"])
        if driver and driver.available():
            drivers.append(driver)
            logging.info(f"Sensore {cfg['name']} @ {hex(cfg['address'])} ok")
        else:
            logging.warning(f"Sensore {cfg['name']} @ {hex(cfg['address'])} non trovato")
    return drivers

async def start_polling(drivers: list, conn, broadcast_fn, interval: int = 30):
    import database
    while True:
        for driver in drivers:
            try:
                data = driver.read()
                if data is not None:
                    await database.save_sensor_reading(conn, driver.name, data)
                    await broadcast_fn({"type": "sensor", "data": {"sensor": driver.name, "values": data}})
            except Exception as e:
                logging.error(f"Lettura {driver.name} fallita: {e}")
        await asyncio.sleep(interval)
```

**Step 3: Verifica i test**

```bash
pytest tests/test_sensor_handler.py -v
# Expected: 3 passed
```

**Step 4: Commit**

```bash
git add sensor_handler.py tests/test_sensor_handler.py
git commit -m "feat(M3-S2): sensor_handler driver I2C + polling asincrono"
```

**Aggiorna PROGRESS.md:** `[x] M3-S2`

---

## Task 13: telemetry.html

**Files:**
- Create: `templates/telemetry.html`

```html
{% extends "base.html" %}
{% block content %}
<div style="padding: 4px 8px; overflow-y: auto; height: 100%;">

  <!-- Sensori I2C locali -->
  <div id="sensors-section" style="display:flex; gap:8px; flex-wrap:wrap; padding:4px 0; border-bottom:1px solid var(--border); margin-bottom:8px;">
    <div id="sensor-display" style="font-size:12px; color:var(--muted);">Nessun sensore rilevato</div>
  </div>

  <!-- Selezione nodo -->
  <div style="display:flex; gap:4px; align-items:center; margin-bottom:4px;">
    <label style="font-size:12px; color:var(--muted); flex-shrink:0;">Nodo:</label>
    <select id="node-select" style="min-height:32px; font-size:12px;" onchange="loadNodeTelemetry(this.value)">
      {% for n in nodes %}
      <option value="{{ n.id }}">{{ n.short_name or n.id }}</option>
      {% endfor %}
    </select>
  </div>

  <!-- Grafici -->
  <div class="chart-wrap"><canvas id="chart-snr"     height="80"></canvas></div>
  <div class="chart-wrap"><canvas id="chart-battery" height="80"></canvas></div>

</div>

<script src="/static/chart.min.js"></script>
<script>
let snrChart = null, battChart = null

function initCharts() {
  const opts = { responsive: true, animation: false,
    scales: { x: { display: false }, y: { ticks: { color: '#888', font:{size:10} }, grid: { color: '#333' } } },
    plugins: { legend: { labels: { color: '#e0e0e0', font:{size:10} } } }
  }
  snrChart  = new Chart(document.getElementById('chart-snr'),     { type:'line', data:{ labels:[], datasets:[{label:'SNR (dB)',  data:[], borderColor:'#4a9eff', borderWidth:1.5, pointRadius:0, tension:0.3}] }, options: opts })
  battChart = new Chart(document.getElementById('chart-battery'), { type:'line', data:{ labels:[], datasets:[{label:'Batteria %', data:[], borderColor:'#4caf50', borderWidth:1.5, pointRadius:0, tension:0.3}] }, options: opts })
}

async function loadNodeTelemetry(nodeId) {
  const [snrData, battData] = await Promise.all([
    fetch(`/api/telemetry/${nodeId}/deviceMetrics`).then(r=>r.json()),
    fetch(`/api/telemetry/${nodeId}/deviceMetrics`).then(r=>r.json()),
  ])
  const labels = snrData.map(d => new Date(d.timestamp*1000).toLocaleTimeString('it',{hour:'2-digit',minute:'2-digit'})).reverse()
  snrChart.data.labels  = labels
  battChart.data.labels = labels
  snrChart.data.datasets[0].data  = snrData.map(d => d.values?.snr ?? null).reverse()
  battChart.data.datasets[0].data = battData.map(d => d.values?.batteryLevel ?? null).reverse()
  snrChart.update(); battChart.update()
}

// Aggiornamenti live
window.addEventListener('telemetry-update', e => {
  const { node_id, type, values } = e.detail
  const sel = document.getElementById('node-select')
  if (!sel || sel.value !== node_id) return
  const ts = new Date().toLocaleTimeString('it',{hour:'2-digit',minute:'2-digit'})
  if (type === 'deviceMetrics') {
    if (values.snr != null) { snrChart.data.labels.push(ts); snrChart.data.datasets[0].data.push(values.snr); if(snrChart.data.labels.length>100){snrChart.data.labels.shift();snrChart.data.datasets[0].data.shift()} snrChart.update() }
    if (values.batteryLevel != null) { battChart.data.labels.push(ts); battChart.data.datasets[0].data.push(values.batteryLevel); if(battChart.data.labels.length>100){battChart.data.labels.shift();battChart.data.datasets[0].data.shift()} battChart.update() }
  }
})

// Sensori I2C
window.addEventListener('sensor-update', e => {
  const { sensor, values } = e.detail
  const container = document.getElementById('sensor-display')
  let el = document.getElementById('sensor-' + sensor)
  if (!el) {
    el = document.createElement('div')
    el.id = 'sensor-' + sensor
    el.style.cssText = 'padding:4px 8px; background:var(--bg2); border-radius:4px; font-size:12px;'
    container.innerHTML = ''
    container.appendChild(el)
  }
  el.innerHTML = `<b>${sensor}</b><br>` + Object.entries(values).map(([k,v])=>`${k}: ${v}`).join('<br>')
})

document.addEventListener('DOMContentLoaded', () => {
  initCharts()
  const sel = document.getElementById('node-select')
  if (sel && sel.value) loadNodeTelemetry(sel.value)
})
</script>
{% endblock %}
```

**Step 2: Scarica Chart.min.js**

```bash
curl -L https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js -o static/chart.min.js
```

**Step 3: Commit**

```bash
git add templates/telemetry.html static/chart.min.js
git commit -m "feat(M3-S3): telemetry.html grafici Chart.js + display sensori I2C"
```

**Aggiorna PROGRESS.md:** `[x] M3-S3`

---

## Task 14: settings.html + temi + config hardware

**Files:**
- Create: `templates/settings.html`

```html
{% extends "base.html" %}
{% block content %}
<div style="overflow-y:auto; height:100%; padding-bottom:8px;">

  <!-- NODO -->
  <div class="settings-section">
    <div class="settings-label">Nodo locale</div>
    <div class="settings-row"><label>Nome lungo</label><input type="text" id="long-name" value="{{ node.long_name if node else '' }}" maxlength="36"></div>
    <div class="settings-row"><label>Nome breve</label><input type="text" id="short-name" value="{{ node.short_name if node else '' }}" maxlength="4"></div>
    <div class="settings-row">
      <label>Ruolo</label>
      <select id="node-role">
        <option value="CLIENT">Client</option>
        <option value="CLIENT_MUTE">Client (muto)</option>
        <option value="ROUTER">Router</option>
        <option value="ROUTER_CLIENT">Router+Client</option>
        <option value="REPEATER">Repeater</option>
        <option value="TRACKER">Tracker</option>
      </select>
    </div>
    <button onclick="saveNodeConfig()" style="margin-top:4px; min-height:36px;">Salva nodo</button>
    <div id="node-status" style="font-size:11px; color:var(--muted); margin-top:4px;"></div>
  </div>

  <!-- LORA -->
  <div class="settings-section" style="border-top:1px solid var(--border);">
    <div class="settings-label">LoRa</div>
    <div class="settings-row">
      <label>Regione</label>
      <select id="lora-region">
        <option value="EU_868">EU 868MHz</option>
        <option value="US_915">US 915MHz</option>
        <option value="EU_433">EU 433MHz</option>
      </select>
    </div>
    <div class="settings-row">
      <label>Preset</label>
      <select id="lora-preset">
        <option value="LONG_FAST">Long Fast</option>
        <option value="LONG_SLOW">Long Slow</option>
        <option value="MEDIUM_FAST">Medium Fast</option>
        <option value="SHORT_FAST">Short Fast</option>
      </select>
    </div>
    <button onclick="saveLoraConfig()" style="margin-top:4px; min-height:36px;">Salva LoRa</button>
  </div>

  <!-- TEMA -->
  <div class="settings-section" style="border-top:1px solid var(--border);">
    <div class="settings-label">Tema UI</div>
    <div style="display:flex; gap:8px;">
      <button onclick="setTheme('dark')"  style="flex:1; min-height:36px; font-size:12px;">🌙 Dark</button>
      <button onclick="setTheme('light')" style="flex:1; min-height:36px; font-size:12px;">☀️ Light</button>
      <button onclick="setTheme('hc')"    style="flex:1; min-height:36px; font-size:12px;">⬛ HC</button>
    </div>
  </div>

  <!-- ADMIN REMOTO -->
  <div class="settings-section" style="border-top:1px solid var(--border);">
    <div class="settings-label">Admin nodo remoto</div>
    <div class="settings-row">
      <label>Nodo target</label>
      <select id="remote-node-select">
        <option value="">— seleziona —</option>
        <!-- popolato via JS -->
      </select>
    </div>
    <div class="settings-row"><label>Nuovo nome</label><input type="text" id="remote-long-name" maxlength="36"></div>
    <div class="settings-row">
      <label>Ruolo</label>
      <select id="remote-role">
        <option value="CLIENT">Client</option>
        <option value="ROUTER">Router</option>
        <option value="REPEATER">Repeater</option>
      </select>
    </div>
    <button onclick="sendRemoteConfig()" style="margin-top:4px; min-height:36px;">Invia configurazione</button>
    <div id="remote-status" style="font-size:11px; color:var(--muted); margin-top:4px;"></div>
  </div>

  <!-- HARDWARE: GPIO / I2C -->
  <div class="settings-section" style="border-top:1px solid var(--border);">
    <div class="settings-label">Hardware GPIO</div>
    <div class="settings-row"><label>ENC1 A/B/SW</label>
      <input type="text" id="enc1-pins" value="{{ enc1[0] }},{{ enc1[1] }},{{ enc1[2] }}" style="width:80px; flex:unset;">
    </div>
    <div class="settings-row"><label>ENC2 A/B/SW</label>
      <input type="text" id="enc2-pins" value="{{ enc2[0] }},{{ enc2[1] }},{{ enc2[2] }}" style="width:80px; flex:unset;">
    </div>
    <div class="settings-label" style="margin-top:8px;">Sensori I2C</div>
    <div class="settings-row"><label>Config (es: bme280:0x76)</label>
      <input type="text" id="i2c-sensors" value="{{ i2c_sensors | map(attribute='name') | zip(i2c_sensors | map(attribute='address') | map('hex')) | map('join', ':') | join(',') if i2c_sensors else '' }}">
    </div>
    <div class="settings-label" style="margin-top:8px;">Display</div>
    <div class="settings-row">
      <label>Rotazione</label>
      <select id="display-rotation">
        <option value="0"  {% if display_rotation==0  %}selected{% endif %}>Landscape (0°)</option>
        <option value="1"  {% if display_rotation==1  %}selected{% endif %}>Portrait (90°)</option>
        <option value="2"  {% if display_rotation==2  %}selected{% endif %}>Landscape inv (180°)</option>
        <option value="3"  {% if display_rotation==3  %}selected{% endif %}>Portrait inv (270°)</option>
      </select>
    </div>
    <button onclick="saveHardwareConfig()" style="margin-top:4px; min-height:36px;">Salva hardware</button>
    <div id="hw-status" style="font-size:11px; color:var(--muted); margin-top:4px;">Richiede riavvio display per rotazione</div>
  </div>

  <!-- BOT -->
  <div class="settings-section" style="border-top:1px solid var(--border);">
    <div class="settings-label">Bot</div>
    <div class="settings-row"><label>Echo bot</label>
      <input type="checkbox" id="bot-echo" style="width:auto; min-height:auto; height:24px; width:24px;">
    </div>
    <button onclick="saveBotConfig()" style="margin-top:4px; min-height:36px;">Salva bot</button>
  </div>

  <!-- INFO SISTEMA -->
  <div class="settings-section" style="border-top:1px solid var(--border);">
    <div class="settings-label">Sistema</div>
    <div id="sys-info" style="font-size:11px; color:var(--muted);"></div>
  </div>

</div>

<script>
// Popola nodi remoti
fetch('/api/nodes').then(r=>r.json()).then(nodes => {
  const sel = document.getElementById('remote-node-select')
  nodes.filter(n=>!n.is_local).forEach(n => {
    const opt = document.createElement('option')
    opt.value = n.id
    opt.textContent = (n.short_name || n.id) + ' — ' + (n.long_name || '')
    sel.appendChild(opt)
  })
})

// Info sistema
fetch('/api/status').then(r=>r.json()).then(s => {
  document.getElementById('sys-info').innerHTML =
    `Connesso: ${s.connected ? '✓' : '✗'} | Nodi: ${s.node_count} | RAM: ${s.ram_mb}MB`
})

async function saveNodeConfig() {
  const payload = {
    device: {
      role: document.getElementById('node-role').value
    },
    owner: {
      longName:  document.getElementById('long-name').value,
      shortName: document.getElementById('short-name').value,
    }
  }
  const r = await fetch('/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
  document.getElementById('node-status').textContent = r.ok ? '✓ Salvato' : '✗ Errore'
}

async function saveLoraConfig() {
  const payload = { lora: { region: document.getElementById('lora-region').value, modemPreset: document.getElementById('lora-preset').value } }
  const r = await fetch('/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
}

async function setTheme(theme) {
  await fetch('/api/set-theme', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({theme})})
  document.body.className = 'theme-' + theme
  document.documentElement.className = 'theme-' + theme
}

async function sendRemoteConfig() {
  const nodeId = document.getElementById('remote-node-select').value
  if (!nodeId) return
  const payload = {
    remote_node_id: nodeId,
    owner: { longName: document.getElementById('remote-long-name').value },
    device: { role: document.getElementById('remote-role').value }
  }
  const r = await fetch('/api/remote-config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
  document.getElementById('remote-status').textContent = r.ok ? '✓ Inviato' : '✗ Errore'
}

async function saveHardwareConfig() {
  const payload = {
    enc1_pins:        document.getElementById('enc1-pins').value,
    enc2_pins:        document.getElementById('enc2-pins').value,
    i2c_sensors:      document.getElementById('i2c-sensors').value,
    display_rotation: document.getElementById('display-rotation').value,
  }
  const r = await fetch('/api/hardware-config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
  document.getElementById('hw-status').textContent = r.ok ? '✓ Salvato (riavvia display per rotazione)' : '✗ Errore'
}

async function saveBotConfig() {
  const payload = { echo: document.getElementById('bot-echo').checked }
  await fetch('/api/bot-config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
}
</script>
{% endblock %}
```

**Step 2: Aggiungi route mancanti a main.py**

```python
# In main.py aggiungi dopo le route esistenti:

@app.post("/api/set-theme")
async def set_theme(payload: dict):
    import re
    theme = payload.get("theme", "dark")
    if theme not in ("dark", "light", "hc"):
        return JSONResponse({"ok": False}, 400)
    _update_config_env("UI_THEME", theme)
    cfg.UI_THEME = theme
    return {"ok": True}

@app.post("/api/remote-config")
async def remote_config(payload: dict):
    node_id = payload.pop("remote_node_id", None)
    if not node_id:
        return JSONResponse({"ok": False, "error": "node_id mancante"}, 400)
    try:
        # meshtastic supporta admin remoto via adminChannel
        node = meshtastic_client._interface.getNode(node_id)
        for section, values in payload.items():
            cfg_section = getattr(node.localConfig, section, None) or getattr(node.moduleConfig, section, None)
            if cfg_section:
                for k, v in values.items():
                    setattr(cfg_section, k, v)
                node.writeConfig(section)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)

@app.post("/api/hardware-config")
async def hardware_config(payload: dict):
    try:
        if "enc1_pins" in payload:
            pins = [int(p.strip()) for p in payload["enc1_pins"].split(",")]
            _update_config_env("ENC1_A", str(pins[0]))
            _update_config_env("ENC1_B", str(pins[1]))
            _update_config_env("ENC1_SW", str(pins[2]))
        if "i2c_sensors" in payload:
            _update_config_env("I2C_SENSORS", payload["i2c_sensors"])
        if "display_rotation" in payload:
            _update_config_env("DISPLAY_ROTATION", payload["display_rotation"])
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, 500)

@app.post("/api/bot-config")
async def bot_config(payload: dict):
    import importlib, sys
    echo = payload.get("echo", False)
    if echo:
        try:
            import bots.echo_bot as echo_bot
            echo_bot.start(meshtastic_client._interface)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, 500)
    return {"ok": True}

def _update_config_env(key: str, value: str):
    """Aggiorna una chiave in config.env."""
    import re
    env_path = "config.env"
    try:
        with open(env_path) as f:
            content = f.read()
        pattern = rf'^{key}=.*$'
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f'{key}={value}', content, flags=re.MULTILINE)
        else:
            content += f'\n{key}={value}'
        with open(env_path, 'w') as f:
            f.write(content)
    except Exception as e:
        logging.error(f"_update_config_env fallito: {e}")
```

**Step 3: Commit**

```bash
git add templates/settings.html main.py
git commit -m "feat(M3-S4,S5,S6,M4-S1,S2): settings completo — temi, GPIO/I2C, admin remoto, LoRa"
```

**Aggiorna PROGRESS.md:** `[x] M3-S4 [x] M3-S5 [x] M3-S6 [x] M4-S1 [x] M4-S2`

---

## Task 15: Framework bot

**Files:**
- Create: `bots/__init__.py`
- Create: `bots/echo_bot.py`

```python
# bots/__init__.py
```

```python
# bots/echo_bot.py
"""Bot echo: risponde ad ogni messaggio ricevuto sul canale configurato."""
import logging
from pubsub import pub

_interface = None
_CHANNEL   = 0

def start(interface, channel: int = 0):
    global _interface, _CHANNEL
    _interface = interface
    _CHANNEL   = channel
    pub.subscribe(_on_message, "meshtastic.receive.text")
    logging.info(f"Echo bot attivo sul canale {channel}")

def stop():
    try:
        pub.unsubscribe(_on_message, "meshtastic.receive.text")
    except Exception:
        pass

def _on_message(packet, interface):
    if _interface is None:
        return
    try:
        decoded = packet.get("decoded", {})
        text    = decoded.get("text", "")
        src     = packet.get("fromId", "unknown")
        channel = packet.get("channel", 0)
        if channel != _CHANNEL or not text:
            return
        # Non rispondere ai propri messaggi
        local = _interface.getMyNodeInfo()
        if src == local.get("user", {}).get("id"):
            return
        _interface.sendText(f"[echo] {text}", channelIndex=channel, destinationId=src)
    except Exception as e:
        logging.error(f"Echo bot errore: {e}")
```

**Step 2: Commit**

```bash
git add bots/
git commit -m "feat(M4-S3): framework bot + echo_bot"
```

**Aggiorna PROGRESS.md:** `[x] M4-S3`

---

## Task 16: systemd service + setup finale

**Files:**
- Create: `meshtastic-pi.service`

```ini
[Unit]
Description=Meshtastic Pi Backend
After=network.target pigpiod.service
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
User=pi
Group=pi
WorkingDirectory=/home/pi/meshtastic-pi
ExecStart=/home/pi/meshtastic-pi/venv/bin/uvicorn main:app \
    --host 127.0.0.1 \
    --port 8080 \
    --workers 1 \
    --log-level warning
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=10
EnvironmentFile=/boot/firmware/config.env
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPYCACHEPREFIX=/tmp/pycache
Environment=XDG_CACHE_HOME=/tmp/cache
MemoryMax=200M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
```

**Step 2: Installa e abilita il servizio sul Pi**

```bash
sudo cp meshtastic-pi.service /etc/systemd/system/
sudo cp config.env /boot/firmware/config.env
sudo systemctl daemon-reload
sudo systemctl enable meshtastic-pi
sudo systemctl start meshtastic-pi
sudo systemctl status meshtastic-pi
```

**Step 3: Aggiungi pi al sudoers per shutdown**

```bash
echo "pi ALL=(ALL) NOPASSWD: /sbin/shutdown" | sudo tee /etc/sudoers.d/meshtastic-pi
```

**Step 4: Avvia Surf al boot (aggiungi a ~/.config/autostart/surf.desktop)**

```ini
[Desktop Entry]
Type=Application
Name=Surf Browser
Exec=surf -x http://localhost:8080/messages
X-GNOME-Autostart-enabled=true
```

**Step 5: Collaudo completo (M4-S4)**

```
1. Riavvia senza SSH: sudo reboot
2. Verifica: app appare su display dopo il boot
3. Verifica tutti i tab funzionanti
4. Ruota display: modifica /boot/config.txt display_rotate → riavvia → verifica portrait
5. Stacca corrente bruscamente → riavvia → verifica DB integro (messaggi presenti)
6. Stacca USB Heltec → verifica reconnect entro 10s
7. Gesture shutdown: press lungo simultaneo enc1+enc2 per 3s → verifica sync DB + spegnimento
8. RAM > 150MB: verifica riavvio automatico con systemd
```

**Step 6: Commit finale**

```bash
git add meshtastic-pi.service
git commit -m "feat(M4-S4): systemd service + checklist collaudo completo"
```

**Aggiorna PROGRESS.md:** `[x] M4-S4`

---

## Riepilogo test suite

```bash
# Esegui tutti i test
pytest tests/ -v

# Test specifici per milestone
pytest tests/test_config.py tests/test_database.py -v           # M1
pytest tests/test_meshtastic_client.py tests/test_watchdog.py -v # M1
pytest tests/test_main.py -v                                      # M2
pytest tests/test_gpio_handler.py tests/test_sensor_handler.py -v # M3
```

---

## Per riprendere il lavoro

1. Apri `PROGRESS.md` → trova il primo `[ ]`
2. Apri questo file → trova il Task corrispondente
3. Segui gli step dall'inizio del task
4. Ogni step è autonomo: se sei a metà di un task, i file già creati sono validi — continua dal prossimo step

