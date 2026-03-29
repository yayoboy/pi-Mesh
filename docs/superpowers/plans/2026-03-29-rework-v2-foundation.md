# Rework v2 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete rewrite of pi-Mesh on branch `rework/v2-rewrite`: meshtasticd TCP client, FastAPI multi-page, SQLite WAL, PinesUI + Alpine.js + Heroicons, SSE log stream, with all 6 pages functional (4 as placeholders).

**Architecture:** meshtasticd handles board via USB serial and exposes TCP :4403; a Python `TCPInterface` wrapper talks to it, caches node data in memory, and feeds FastAPI endpoints; each HTML page is independent (multi-page), using Alpine.js for polling and PinesUI components; Heroicons SVG inline everywhere, zero emoji.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, meshtastic-python (TCPInterface), SQLite WAL, aiosqlite, PinesUI + Alpine.js + Tailwind CSS (CDN), Heroicons SVG, pytest + httpx

**Branch:** `rework/v2-rewrite`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `main.py` | Create (replace) | FastAPI app, lifespan, router mounting |
| `config.py` | Create (replace) | All env vars with defaults |
| `meshtasticd_client.py` | Create (replace) | TCPInterface wrapper, node cache, SSE event queue |
| `database.py` | Create (replace) | SQLite WAL, schema init, CRUD helpers |
| `routers/__init__.py` | Create | Package marker |
| `routers/nodes.py` | Create | GET /nodes (page) + GET /api/nodes (JSON) |
| `routers/map.py` | Create | GET /map (page) + existing /api/map/* endpoints |
| `routers/log.py` | Create | GET /log (page) + GET /api/log/stream (SSE) |
| `routers/placeholders.py` | Create | GET /messages, /config, /metrics (placeholder pages) |
| `templates/base.html` | Create (replace) | Layout: head, tabbar, content area |
| `templates/nodes.html` | Create | Node list with Alpine.js polling |
| `templates/map.html` | Create (port from master) | Leaflet map page |
| `templates/log.html` | Create | Log stream with SSE |
| `templates/placeholder.html` | Create | Reusable "coming soon" page |
| `static/map.js` | Port from master | Leaflet logic (adapted for new layout) |
| `tests/test_database.py` | Create | DB schema and CRUD tests |
| `tests/test_api.py` | Create | FastAPI endpoint tests with httpx |
| `tests/conftest.py` | Create | Pytest fixtures |
| `systemd/meshtasticd.service` | Create | meshtasticd systemd unit |
| `systemd/pimesh.service` | Create | FastAPI app systemd unit |
| `setup.sh` | Create | One-command Pi setup script |

---

### Task 1: Clean up old structure and set up directories

**Files:**
- Remove: old top-level Python files not in new structure
- Create: `routers/__init__.py`, `tests/conftest.py`, `systemd/`

- [ ] **Step 1: Check what exists on the branch**

```bash
git log --oneline -3
ls *.py routers/ tests/ 2>/dev/null || echo "not found"
```

- [ ] **Step 2: Create directory structure**

```bash
mkdir -p routers tests systemd
touch routers/__init__.py
```

- [ ] **Step 3: Create tests/conftest.py**

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_client():
    """Mock meshtasticd_client module for tests that don't need real board."""
    with patch('meshtasticd_client.get_nodes') as mock_nodes, \
         patch('meshtasticd_client.is_connected') as mock_conn:
        mock_conn.return_value = True
        mock_nodes.return_value = [
            {
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
                'is_local': True,
            }
        ]
        yield {'nodes': mock_nodes, 'connected': mock_conn}


@pytest.fixture
async def client(mock_client):
    """Async HTTP client for testing FastAPI app."""
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
    ) as ac:
        yield ac
```

- [ ] **Step 4: Commit skeleton**

```bash
git add routers/__init__.py tests/conftest.py
git commit -m "chore: set up v2 rewrite directory structure"
```

---

### Task 2: config.py

**Files:**
- Create: `config.py`

- [ ] **Step 1: Write config.py**

```python
# config.py
import os

MESHTASTICD_HOST = os.getenv('MESHTASTICD_HOST', 'localhost')
MESHTASTICD_PORT = int(os.getenv('MESHTASTICD_PORT', '4403'))
DB_PATH          = os.getenv('DB_PATH', 'data/mesh.db')
LOG_LEVEL        = os.getenv('LOG_LEVEL', 'WARNING')
NODE_CACHE_TTL   = float(os.getenv('NODE_CACHE_TTL', '8.0'))
```

- [ ] **Step 2: Ensure data directory exists**

```bash
mkdir -p data
touch data/.gitkeep
```

- [ ] **Step 3: Commit**

```bash
git add config.py data/.gitkeep
git commit -m "feat: config module with env var defaults"
```

---

### Task 3: database.py with WAL mode and schema

**Files:**
- Create: `database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write test first**

```python
# tests/test_database.py
import pytest
import asyncio
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
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd /home/pimesh/pi-Mesh  # or local dev path
pip install pytest pytest-asyncio aiosqlite httpx 2>/dev/null
python -m pytest tests/test_database.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'database'`

- [ ] **Step 3: Write database.py**

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest tests/test_database.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "feat: database module with WAL mode and schema"
```

---

### Task 4: meshtasticd_client.py

**Files:**
- Create: `meshtasticd_client.py`
- Create: `tests/test_meshtasticd_client.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_meshtasticd_client.py
import pytest
import time
from unittest.mock import MagicMock, patch
import meshtasticd_client as mc


def test_is_connected_false_initially():
    mc._connected = False
    assert mc.is_connected() is False


def test_get_nodes_returns_cache_within_ttl():
    mc._node_cache = {'!abc': {'id': '!abc', 'short_name': 'X'}}
    mc._last_node_fetch = time.time()  # just fetched
    nodes = mc.get_nodes()
    assert len(nodes) == 1
    assert nodes[0]['short_name'] == 'X'


def test_get_nodes_empty_when_cache_cold():
    mc._node_cache = {}
    mc._last_node_fetch = 0.0
    # Without a real connection, returns empty list
    with patch.object(mc, '_connected', False):
        nodes = mc.get_nodes()
    assert nodes == []


def test_get_local_node_returns_none_when_empty():
    mc._node_cache = {}
    assert mc.get_local_node() is None


def test_get_local_node_finds_is_local():
    mc._node_cache = {
        '!aaa': {'id': '!aaa', 'is_local': False},
        '!bbb': {'id': '!bbb', 'is_local': True, 'short_name': 'LOCAL'},
    }
    node = mc.get_local_node()
    assert node is not None
    assert node['short_name'] == 'LOCAL'
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python -m pytest tests/test_meshtasticd_client.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'meshtasticd_client'`

- [ ] **Step 3: Write meshtasticd_client.py**

```python
# meshtasticd_client.py
import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

# --- State ---
_interface      = None
_connected      = False
_node_cache: dict[str, dict] = {}
_last_node_fetch: float = 0.0
_log_queue: deque = deque(maxlen=500)
_subscribers: list = []

import config as cfg

NODE_CACHE_TTL = cfg.NODE_CACHE_TTL


# --- Public API ---

def is_connected() -> bool:
    return _connected


def get_nodes() -> list[dict]:
    """Return cached node list. Refreshes from interface if TTL expired."""
    global _node_cache, _last_node_fetch
    if _connected and _interface and (time.time() - _last_node_fetch) > NODE_CACHE_TTL:
        _refresh_node_cache()
    return list(_node_cache.values())


def get_local_node() -> dict | None:
    for node in _node_cache.values():
        if node.get('is_local'):
            return node
    return None


def get_log_queue() -> deque:
    return _log_queue


def subscribe_log(callback) -> None:
    _subscribers.append(callback)


def unsubscribe_log(callback) -> None:
    if callback in _subscribers:
        _subscribers.remove(callback)


# --- Internal ---

def _refresh_node_cache() -> None:
    global _node_cache, _last_node_fetch
    try:
        raw = _interface.nodes or {}
        _node_cache = {}
        for node_id, info in raw.items():
            user = info.get('user', {})
            pos  = info.get('position', {})
            metrics = info.get('deviceMetrics', {})
            _node_cache[node_id] = {
                'id':            user.get('id', node_id),
                'short_name':    user.get('shortName', ''),
                'long_name':     user.get('longName', ''),
                'hw_model':      user.get('hwModel', ''),
                'latitude':      pos.get('latitude'),
                'longitude':     pos.get('longitude'),
                'last_heard':    info.get('lastHeard'),
                'snr':           info.get('snr'),
                'hop_count':     info.get('hopsAway'),
                'battery_level': metrics.get('batteryLevel'),
                'is_local':      info.get('isFavorite', False) and node_id == _get_local_id(),
                'raw_json':      str(info),
            }
        _last_node_fetch = time.time()
    except Exception as e:
        logger.warning(f'Node cache refresh failed: {e}')


def _get_local_id() -> str:
    try:
        return _interface.localNode.nodeNum
    except Exception:
        return ''


def _on_receive(packet, interface) -> None:
    entry = {
        'ts':          int(time.time()),
        'from':        packet.get('fromId', '?'),
        'type':        packet.get('decoded', {}).get('portnum', 'UNKNOWN'),
        'snr':         packet.get('rxSnr'),
        'hop_limit':   packet.get('hopLimit'),
    }
    _log_queue.append(entry)
    for cb in list(_subscribers):
        try:
            cb(entry)
        except Exception:
            pass
    # Refresh node cache on any packet
    if _connected and _interface:
        _refresh_node_cache()


async def connect() -> None:
    global _interface, _connected
    import meshtastic.tcp_interface
    from pubsub import pub
    backoff = 15
    while True:
        try:
            logger.warning(f'Connecting to meshtasticd at {cfg.MESHTASTICD_HOST}:{cfg.MESHTASTICD_PORT}')
            _interface = meshtastic.tcp_interface.TCPInterface(
                hostname=cfg.MESHTASTICD_HOST,
                portNumber=cfg.MESHTASTICD_PORT,
                noProto=False,
            )
            pub.subscribe(_on_receive, 'meshtastic.receive')
            _connected = True
            backoff = 15
            logger.warning('Connected to meshtasticd')
            # Keep alive — poll every 30s
            while _connected:
                _refresh_node_cache()
                await asyncio.sleep(30)
        except Exception as e:
            _connected = False
            logger.warning(f'meshtasticd connection failed: {e}. Retry in {backoff}s')
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


async def disconnect() -> None:
    global _connected
    _connected = False
    if _interface:
        try:
            _interface.close()
        except Exception:
            pass
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest tests/test_meshtasticd_client.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add meshtasticd_client.py tests/test_meshtasticd_client.py
git commit -m "feat: meshtasticd TCP client with node cache and log queue"
```

---

### Task 5: main.py — FastAPI app with lifespan

**Files:**
- Create: `main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write API tests**

```python
# tests/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_nodes_page_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/nodes')
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']


@pytest.mark.asyncio
async def test_api_nodes_returns_json(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/api/nodes')
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]['short_name'] == 'TEST'


@pytest.mark.asyncio
async def test_map_page_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/map')
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_log_page_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/log')
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_messages_placeholder_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/messages')
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python -m pytest tests/test_api.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'main'` or import errors.

- [ ] **Step 3: Write main.py**

```python
# main.py
import asyncio
import logging
import os

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config as cfg
import database
import meshtasticd_client

logging.basicConfig(level=getattr(logging, cfg.LOG_LEVEL, logging.WARNING))

from routers import nodes, map_router, log_router, placeholders


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init(cfg.DB_PATH)
    asyncio.create_task(meshtasticd_client.connect())
    yield
    await meshtasticd_client.disconnect()


app = FastAPI(lifespan=lifespan)

app.mount('/static', StaticFiles(directory='static'), name='static')
app.mount('/tiles', StaticFiles(directory='static/tiles'), name='tiles')

app.include_router(nodes.router)
app.include_router(map_router.router)
app.include_router(log_router.router)
app.include_router(placeholders.router)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest tests/test_api.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_api.py
git commit -m "feat: FastAPI main app with lifespan and router mounting"
```

---

### Task 6: base.html — PinesUI layout with Tailwind + heroicons tabbar

**Files:**
- Create: `templates/base.html`
- Create: `templates/placeholder.html`

- [ ] **Step 1: Write base.html**

The tabbar uses 6 heroicons SVG inline. Content area fills remaining height. Dark theme via Tailwind arbitrary classes and CSS vars.

```html
<!DOCTYPE html>
<html lang="it" class="h-full bg-gray-950">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=320, initial-scale=1.0, maximum-scale=1.0">
  <title>pi-Mesh</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>
    :root {
      --accent: #4a9eff;
      --bg: #060810;
      --panel: #0d1017;
      --border: #1a2233;
      --text: #c9d1e0;
      --muted: #4a5568;
    }
    body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; }
    .tab-active { color: var(--accent); }
    .tab-active svg { stroke: var(--accent); }
  </style>
  {% block head %}{% endblock %}
</head>
<body class="h-full flex flex-col">

  <!-- Status bar (opzionale) -->
  <div id="statusbar" class="flex items-center justify-between px-3 py-1 text-xs"
       style="background:var(--panel);border-bottom:1px solid var(--border);height:24px;">
    <span style="color:var(--muted);">pi-Mesh</span>
    <div class="flex gap-3" style="color:var(--muted);">
      <span id="sb-conn">
        <!-- heroicon: signal -->
        <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" class="inline">
          <path stroke-linecap="round" stroke-linejoin="round" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"/>
        </svg>
      </span>
    </div>
  </div>

  <!-- Content area -->
  <main class="flex-1 overflow-hidden" style="height:calc(100vh - 24px - 48px);">
    {% block content %}{% endblock %}
  </main>

  <!-- Tabbar fissa in basso -->
  <nav class="flex items-stretch shrink-0" style="height:48px;background:var(--panel);border-top:1px solid var(--border);">

    {% set tabs = [
      ('nodes',    '/nodes',    'Nodi',    'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z'),
      ('map',      '/map',      'Mappa',   'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7'),
      ('messages', '/messages', 'Msg',     'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z'),
      ('config',   '/config',   'Config',  'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z'),
      ('metrics',  '/metrics',  'Metriche','M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'),
      ('log',      '/log',      'Log',     'M4 6h16M4 10h16M4 14h16M4 18h7'),
    ] %}

    {% for key, href, label, icon_path in tabs %}
    <a href="{{ href }}"
       class="flex-1 flex flex-col items-center justify-center gap-0.5 text-center no-underline
              {% if active_tab == key %}tab-active{% endif %}"
       style="color:{% if active_tab == key %}var(--accent){% else %}var(--muted){% endif %};
              font-size:9px;font-weight:500;text-decoration:none;">
      <svg width="20" height="20" fill="none"
           stroke="{% if active_tab == key %}var(--accent){% else %}var(--muted){% endif %}"
           stroke-width="1.8" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="{{ icon_path }}"/>
      </svg>
      {{ label }}
    </a>
    {% endfor %}

  </nav>
</body>
</html>
```

- [ ] **Step 2: Write templates/placeholder.html**

```html
{% extends "base.html" %}
{% block content %}
<div class="flex flex-col items-center justify-center h-full gap-3" style="color:var(--muted);">
  <svg width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/>
  </svg>
  <p class="text-sm">{{ page_title }} — in arrivo</p>
</div>
{% endblock %}
```

- [ ] **Step 3: Commit**

```bash
git add templates/base.html templates/placeholder.html
git commit -m "feat: base.html with PinesUI/Tailwind layout, tabbar heroicons, placeholder template"
```

---

### Task 7: routers/placeholders.py + routers/nodes.py + templates/nodes.html

**Files:**
- Create: `routers/placeholders.py`
- Create: `routers/nodes.py`
- Create: `templates/nodes.html`

- [ ] **Step 1: Write routers/placeholders.py**

```python
# routers/placeholders.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/messages', response_class=HTMLResponse)
async def messages_page(request: Request):
    return templates.TemplateResponse('placeholder.html', {
        'request': request, 'active_tab': 'messages', 'page_title': 'Messaggi'
    })


@router.get('/config', response_class=HTMLResponse)
async def config_page(request: Request):
    return templates.TemplateResponse('placeholder.html', {
        'request': request, 'active_tab': 'config', 'page_title': 'Configurazione'
    })


@router.get('/metrics', response_class=HTMLResponse)
async def metrics_page(request: Request):
    return templates.TemplateResponse('placeholder.html', {
        'request': request, 'active_tab': 'metrics', 'page_title': 'Metriche'
    })
```

- [ ] **Step 2: Write routers/nodes.py**

```python
# routers/nodes.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/nodes', response_class=HTMLResponse)
async def nodes_page(request: Request):
    return templates.TemplateResponse('nodes.html', {
        'request': request, 'active_tab': 'nodes'
    })


@router.get('/api/nodes')
async def api_nodes():
    return meshtasticd_client.get_nodes()
```

- [ ] **Step 3: Write templates/nodes.html**

```html
{% extends "base.html" %}
{% block content %}
<div x-data="nodesPage()" x-init="init()" class="h-full flex flex-col overflow-hidden">

  <!-- Header -->
  <div class="flex items-center justify-between px-3 py-2 shrink-0"
       style="border-bottom:1px solid var(--border);font-size:11px;">
    <span style="color:var(--accent);font-weight:600;">Nodi</span>
    <span x-text="nodes.length + ' trovati'" style="color:var(--muted);"></span>
  </div>

  <!-- Node list -->
  <div class="flex-1 overflow-y-auto">
    <template x-if="nodes.length === 0">
      <div class="flex items-center justify-center h-32" style="color:var(--muted);font-size:12px;">
        Nessun nodo rilevato
      </div>
    </template>

    <template x-for="node in nodes" :key="node.id">
      <div class="flex items-center gap-3 px-3 py-2"
           style="border-bottom:1px solid var(--border);min-height:52px;">

        <!-- Avatar -->
        <div class="shrink-0 flex items-center justify-center rounded-full text-white font-bold"
             :style="`width:34px;height:34px;font-size:9px;font-family:monospace;
                      background:${node.is_local ? '#4a9eff' : (isOnline(node) ? '#4caf50' : '#374151')};
                      ${node.is_local ? 'box-shadow:0 0 8px #4a9eff' : ''}`"
             x-text="(node.short_name || node.id).slice(0,6)">
        </div>

        <!-- Info -->
        <div class="flex-1 min-w-0">
          <div class="font-semibold truncate" style="font-size:12px;"
               x-text="node.long_name || node.short_name || node.id"></div>
          <div style="font-size:10px;color:var(--muted);"
               x-text="node.hw_model || ''"></div>
          <div class="flex gap-3 mt-0.5" style="font-size:10px;color:var(--muted);">
            <span x-text="node.snr != null ? node.snr + ' dB' : ''"></span>
            <span x-text="node.battery_level != null ? node.battery_level + '%' : ''"></span>
            <span x-text="node.hop_count != null ? node.hop_count + ' hop' : ''"></span>
          </div>
        </div>

        <!-- Online dot -->
        <div class="shrink-0 w-2 h-2 rounded-full"
             :style="`background:${isOnline(node) ? '#4caf50' : '#374151'}`"></div>
      </div>
    </template>
  </div>
</div>

<script>
function nodesPage() {
  return {
    nodes: [],
    async init() {
      await this.fetch()
      setInterval(() => this.fetch(), 10000)
    },
    async fetch() {
      try {
        const r = await window.fetch('/api/nodes')
        this.nodes = await r.json()
      } catch(e) {}
    },
    isOnline(node) {
      if (!node.last_heard) return false
      return (Date.now() / 1000 - node.last_heard) < 1800
    }
  }
}
</script>
{% endblock %}
```

- [ ] **Step 4: Commit**

```bash
git add routers/placeholders.py routers/nodes.py templates/nodes.html
git commit -m "feat: nodes page with Alpine.js polling and placeholder routes"
```

---

### Task 8: routers/log.py + templates/log.html (SSE)

**Files:**
- Create: `routers/log.py`
- Create: `templates/log.html`

- [ ] **Step 1: Write routers/log.py**

```python
# routers/log.py
import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/log', response_class=HTMLResponse)
async def log_page(request: Request):
    return templates.TemplateResponse('log.html', {
        'request': request, 'active_tab': 'log'
    })


@router.get('/api/log/stream')
async def log_stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    def on_packet(entry: dict):
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            pass

    meshtasticd_client.subscribe_log(on_packet)

    async def event_generator():
        # Send last 20 entries on connect
        for entry in list(meshtasticd_client.get_log_queue())[-20:]:
            yield f'data: {json.dumps(entry)}\n\n'
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f'data: {json.dumps(entry)}\n\n'
                except asyncio.TimeoutError:
                    yield ': keepalive\n\n'
        finally:
            meshtasticd_client.unsubscribe_log(on_packet)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
```

- [ ] **Step 2: Write templates/log.html**

```html
{% extends "base.html" %}
{% block content %}
<div x-data="logPage()" x-init="init()" class="h-full flex flex-col overflow-hidden">

  <!-- Header -->
  <div class="flex items-center justify-between px-3 py-2 shrink-0"
       style="border-bottom:1px solid var(--border);font-size:11px;">
    <span style="color:var(--accent);font-weight:600;">Log board</span>
    <div class="flex items-center gap-2">
      <span class="w-2 h-2 rounded-full"
            :style="`background:${connected ? '#4caf50' : '#374151'}`"></span>
      <button @click="entries = []"
              style="color:var(--muted);background:none;border:none;cursor:pointer;font-size:10px;">
        <!-- heroicon: trash -->
        <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round"
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
        </svg>
      </button>
    </div>
  </div>

  <!-- Log entries -->
  <div class="flex-1 overflow-y-auto font-mono" style="font-size:10px;" id="log-scroll">
    <template x-for="(e, i) in entries" :key="i">
      <div class="px-3 py-1 flex gap-2" style="border-bottom:1px solid rgba(26,34,51,0.5);">
        <span style="color:var(--muted);flex-shrink:0;" x-text="fmtTime(e.ts)"></span>
        <span style="color:var(--accent);flex-shrink:0;" x-text="e.from || '?'"></span>
        <span style="color:var(--text);" x-text="e.type || ''"></span>
        <span style="color:var(--muted);margin-left:auto;flex-shrink:0;"
              x-show="e.snr != null" x-text="e.snr != null ? e.snr + 'dB' : ''"></span>
      </div>
    </template>
    <template x-if="entries.length === 0">
      <div class="flex items-center justify-center h-24" style="color:var(--muted);">
        In attesa di pacchetti...
      </div>
    </template>
  </div>
</div>

<script>
function logPage() {
  return {
    entries: [],
    connected: false,
    es: null,
    init() {
      this.connect()
    },
    connect() {
      this.es = new EventSource('/api/log/stream')
      this.es.onopen = () => { this.connected = true }
      this.es.onmessage = (e) => {
        try {
          const entry = JSON.parse(e.data)
          this.entries.unshift(entry)
          if (this.entries.length > 200) this.entries.pop()
        } catch(_) {}
      }
      this.es.onerror = () => {
        this.connected = false
        this.es.close()
        setTimeout(() => this.connect(), 5000)
      }
    },
    fmtTime(ts) {
      if (!ts) return '--:--:--'
      const d = new Date(ts * 1000)
      return d.toTimeString().slice(0,8)
    }
  }
}
</script>
{% endblock %}
```

- [ ] **Step 3: Commit**

```bash
git add routers/log.py templates/log.html
git commit -m "feat: log page with SSE stream and Alpine.js client"
```

---

### Task 9: routers/map_router.py + templates/map.html (port from master)

**Files:**
- Create: `routers/map_router.py`
- Create: `templates/map.html` (ported from master, adapted for new layout)
- Port: `static/map.js` (from master branch)

- [ ] **Step 1: Port map.js from master**

```bash
git show master:static/map.js > static/map.js
```

Verify it contains `initMapIfNeeded`, `switchLayer`, `showNodePopup`.

- [ ] **Step 2: Write routers/map_router.py**

```python
# routers/map_router.py
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')

# Tile bounds for Italy (adjust if needed)
DEFAULT_BOUNDS = {
    'lat_min': 35.0, 'lat_max': 47.5,
    'lon_min': 6.5,  'lon_max': 18.5,
}


@router.get('/map', response_class=HTMLResponse)
async def map_page(request: Request):
    nodes = meshtasticd_client.get_nodes()
    local = next((n for n in nodes if n.get('is_local')), None)
    return templates.TemplateResponse('map.html', {
        'request':  request,
        'active_tab': 'map',
        'bounds':   DEFAULT_BOUNDS,
        'zoom_min': 7,
        'zoom_max': 16,
        'nodes_json': json.dumps(nodes),
    })


@router.get('/api/map/nodes')
async def api_map_nodes():
    return meshtasticd_client.get_nodes()
```

- [ ] **Step 3: Create templates/map.html adapted for new base**

The map page overrides the content block and sets `#content` to `overflow:hidden`. It pre-populates `nodeCache` from server-side JSON to avoid initial flash.

```html
{% extends "base.html" %}
{% block head %}
<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  main { overflow: hidden !important; }
  .leaflet-control-zoom a {
    background: rgba(6,8,16,0.55) !important;
    border-color: rgba(26,34,51,0.5) !important;
    color: var(--text,#c9d1e0) !important;
  }
</style>
{% endblock %}
{% block content %}
<div style="position:relative;width:100%;height:100%;">

  <div id="map-container"
       data-bounds='{{ bounds | tojson }}'
       data-zoom-min="{{ zoom_min }}"
       data-zoom-max="{{ zoom_max }}"
       style="position:absolute;inset:0;"></div>

  <!-- Panel toggle top-right -->
  <button id="panel-toggle"
          style="position:absolute;top:6px;right:6px;z-index:1000;
                 width:32px;height:32px;padding:0;
                 display:flex;align-items:center;justify-content:center;
                 background:rgba(6,8,16,0.55);border:1px solid rgba(26,34,51,0.5);
                 border-radius:4px;color:var(--text);
                 -webkit-tap-highlight-color:transparent;">
    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h7"/>
    </svg>
  </button>

  <!-- Layer switcher compatto -->
  <div style="position:absolute;top:46px;right:6px;z-index:1000;
              background:rgba(6,8,16,0.55);border:1px solid rgba(26,34,51,0.5);
              border-radius:4px;overflow:hidden;width:32px;">
    <button class="layer-btn" data-layer="osm" onclick="switchLayer('osm')" title="Stradale"
            style="width:100%;height:28px;padding:0;border:none;border-bottom:1px solid rgba(26,34,51,0.4);
                   background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
                   color:var(--accent);-webkit-tap-highlight-color:transparent;">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
      </svg>
    </button>
    <button class="layer-btn" data-layer="topo" onclick="switchLayer('topo')" title="Topo"
            style="width:100%;height:28px;padding:0;border:none;border-bottom:1px solid rgba(26,34,51,0.4);
                   background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
                   color:var(--text);-webkit-tap-highlight-color:transparent;">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 21l5-10 5 5 4-7 4 12"/>
      </svg>
    </button>
    <button class="layer-btn" data-layer="satellite" onclick="switchLayer('satellite')" title="Satellite"
            style="width:100%;height:28px;padding:0;border:none;
                   background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
                   color:var(--text);-webkit-tap-highlight-color:transparent;">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="3"/>
        <path stroke-linecap="round" stroke-linejoin="round" d="M6.3 6.3l11.4 11.4M17.7 6.3L6.3 17.7"/>
      </svg>
    </button>
  </div>

  <!-- Centra sulla board -->
  <button id="btn-center-board" onclick="centerOnBoard()" title="Centra sulla board"
          style="position:absolute;bottom:70px;right:6px;z-index:1000;
                 width:32px;height:32px;padding:0;
                 display:flex;align-items:center;justify-content:center;
                 background:rgba(6,8,16,0.55);border:1px solid rgba(26,34,51,0.5);
                 border-radius:4px;cursor:pointer;color:var(--text);
                 -webkit-tap-highlight-color:transparent;">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <circle cx="12" cy="12" r="3"/>
      <path stroke-linecap="round" d="M12 2v4m0 12v4M2 12h4m12 0h4"/>
    </svg>
  </button>

  <!-- Popup nodo -->
  <div id="node-popup"
       style="display:none;position:absolute;z-index:900;
              background:rgba(6,8,16,0.96);border:1px solid var(--border);
              border-radius:6px;padding:10px;width:190px;
              box-shadow:0 4px 16px rgba(0,0,0,0.6);font-size:10px;pointer-events:auto;">
  </div>

  <!-- Pannello laterale -->
  <div id="right-panel"
       style="display:none;position:absolute;top:0;right:0;bottom:0;width:160px;z-index:700;
              flex-direction:column;overflow:hidden;
              background:var(--bg);border-left:1px solid var(--border);">
    <div style="padding:5px 10px;font-size:9px;color:var(--accent);text-transform:uppercase;
                border-bottom:1px solid var(--border);">Filtri</div>
    <!-- filtri omessi — implementati nella milestone Nodi+Mappa -->
  </div>
</div>

<script>
// Pre-populate nodeCache from server-rendered JSON (no initial HTTP request)
var _serverNodes = {{ nodes_json | safe }};
</script>
<script src="/static/map.js?v=5"></script>
<script>
document.getElementById('panel-toggle').onclick = function() {
  var p = document.getElementById('right-panel')
  p.style.display = p.style.display === 'flex' ? 'none' : 'flex'
}

// Feed server nodes into nodeCache on load
if (typeof nodeCache !== 'undefined' && _serverNodes) {
  _serverNodes.forEach(function(n) { nodeCache.set(n.id, n) })
}
</script>
{% endblock %}
```

- [ ] **Step 4: Commit**

```bash
git add routers/map_router.py templates/map.html static/map.js
git commit -m "feat: map page ported to new layout with server-side node preload"
```

---

### Task 10: Systemd service files and setup.sh

**Files:**
- Create: `systemd/meshtasticd.service`
- Create: `systemd/pimesh.service`
- Create: `setup.sh`

- [ ] **Step 1: Write systemd/meshtasticd.service**

```ini
[Unit]
Description=Meshtastic Daemon
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=/usr/sbin/meshtasticd --port /dev/ttyACM0
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Write systemd/pimesh.service**

```ini
[Unit]
Description=pi-Mesh FastAPI App
After=network.target meshtasticd.service
Requires=meshtasticd.service

[Service]
Type=simple
User=pimesh
WorkingDirectory=/home/pimesh/pi-Mesh
ExecStart=/home/pimesh/pi-Mesh/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1 --log-level warning
Restart=always
RestartSec=5
EnvironmentFile=/home/pimesh/pi-Mesh/config.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Write setup.sh**

```bash
#!/usr/bin/env bash
# setup.sh — One-command pi-Mesh setup on Raspberry Pi OS Bookworm
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="${SUDO_USER:-pimesh}"
HOME_DIR="/home/$USER"

echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3-venv python3-pip git meshtasticd \
    epiphany-browser xorg openbox

echo "==> Setting up Python venv..."
sudo -u "$USER" python3 -m venv "$REPO_DIR/venv"
sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

echo "==> Creating data directory..."
sudo -u "$USER" mkdir -p "$REPO_DIR/data"

echo "==> Installing systemd services..."
cp "$REPO_DIR/systemd/meshtasticd.service" /etc/systemd/system/
cp "$REPO_DIR/systemd/pimesh.service"      /etc/systemd/system/
systemctl daemon-reload
systemctl enable meshtasticd pimesh
systemctl start  meshtasticd
sleep 3
systemctl start  pimesh

echo "==> Done. App available at http://localhost:8080"
```

- [ ] **Step 4: Write requirements.txt**

```
fastapi>=0.115
uvicorn>=0.29
aiosqlite>=0.20
meshtastic>=2.5
jinja2>=3.1
python-multipart>=0.0.9
```

- [ ] **Step 5: Make setup.sh executable and commit**

```bash
chmod +x setup.sh
git add systemd/ setup.sh requirements.txt
git commit -m "feat: systemd service files and automated setup script"
```

---

### Task 11: Final integration test

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests pass (database: 3, meshtasticd_client: 5, api: 5 = 13 total).

- [ ] **Step 2: Smoke test locally without real board**

```bash
# Start app with no meshtasticd (it will retry in background)
MESHTASTICD_HOST=127.0.0.1 uvicorn main:app --port 8080 &
sleep 2
curl -s http://localhost:8080/nodes | head -5
curl -s http://localhost:8080/api/nodes
curl -s http://localhost:8080/map | grep -c 'map-container'
curl -s http://localhost:8080/messages | grep -c 'arrivo'
kill %1
```

Expected: all endpoints return 200, `/api/nodes` returns `[]`, `/map` contains `map-container`.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: v2 Foundation milestone complete — meshtasticd wrapper, multi-page FastAPI, PinesUI layout"
```
