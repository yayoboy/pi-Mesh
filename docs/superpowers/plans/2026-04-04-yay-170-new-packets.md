# New Packet Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gestire 4 nuovi portnums Meshtastic: WAYPOINT_APP (waypoint su mappa), NEIGHBOR_INFO_APP (topologia mesh), DETECTION_SENSOR_APP (sensore binario), PAXCOUNTER_APP (contatore BLE/WiFi).

**Architecture:** Approccio B. Handler in `meshtasticd_client.py` emettono WS events. Due nuovi router per API REST. Tre nuove tabelle DB. Layer Leaflet per waypoints e neighbor links in `map.js`. Tab "Topology" nel pannello laterale della mappa (HTML inline). Pattern identico agli handler TELEMETRY_APP/TRACEROUTE_APP esistenti.

**Tech Stack:** FastAPI, aiosqlite, meshtastic-python, Leaflet.js, Alpine.js, SVG (no librerie esterne per grafo)

---

### Task 1: DB schema — 3 nuove tabelle

**Files:**
- Modify: `database.py`
- Create: `tests/test_new_packets_db.py`

- [ ] **Step 1: Aggiungi tabelle a `_SCHEMA`**

In `database.py`, nella stringa `_SCHEMA`, aggiungi prima della `"""` di chiusura:

```sql
CREATE TABLE IF NOT EXISTS waypoints (
    id INTEGER PRIMARY KEY,
    name TEXT,
    lat REAL,
    lon REAL,
    icon TEXT DEFAULT 'default',
    description TEXT,
    expire INTEGER,
    from_id TEXT,
    ts INTEGER
);

CREATE TABLE IF NOT EXISTS neighbor_info (
    from_id TEXT NOT NULL,
    neighbor_id TEXT NOT NULL,
    snr REAL,
    ts INTEGER,
    PRIMARY KEY (from_id, neighbor_id)
);

CREATE TABLE IF NOT EXISTS sensor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    from_id TEXT NOT NULL,
    type TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sensor_events_node_ts ON sensor_events(from_id, ts DESC);
```

- [ ] **Step 2: Aggiungi funzioni DB in `database.py`** (dopo le funzioni `canned_messages`):

```python
async def upsert_waypoint(wp: dict) -> None:
    async with _get_db() as db:
        await db.execute('''
            INSERT INTO waypoints (id, name, lat, lon, icon, description, expire, from_id, ts)
            VALUES (:id, :name, :lat, :lon, :icon, :description, :expire, :from_id, :ts)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, lat=excluded.lat, lon=excluded.lon,
              icon=excluded.icon, description=excluded.description,
              expire=excluded.expire, ts=excluded.ts
        ''', wp)
        await db.commit()


async def get_waypoints(active_only: bool = True) -> list:
    async with _get_db() as db:
        now = int(time.time())
        if active_only:
            cur = await db.execute(
                'SELECT id,name,lat,lon,icon,description,expire,from_id,ts FROM waypoints WHERE expire=0 OR expire>?',
                (now,)
            )
        else:
            cur = await db.execute(
                'SELECT id,name,lat,lon,icon,description,expire,from_id,ts FROM waypoints'
            )
        rows = await cur.fetchall()
        keys = ('id','name','lat','lon','icon','description','expire','from_id','ts')
        return [dict(zip(keys, r)) for r in rows]


async def delete_waypoint(wp_id: int) -> None:
    async with _get_db() as db:
        await db.execute('DELETE FROM waypoints WHERE id=?', (wp_id,))
        await db.commit()


async def upsert_neighbor_info(from_id: str, neighbor_id: str, snr: float) -> None:
    async with _get_db() as db:
        await db.execute('''
            INSERT INTO neighbor_info (from_id, neighbor_id, snr, ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(from_id, neighbor_id) DO UPDATE SET snr=excluded.snr, ts=excluded.ts
        ''', (from_id, neighbor_id, snr, int(time.time())))
        await db.commit()


async def get_neighbor_info() -> list:
    async with _get_db() as db:
        cur = await db.execute(
            'SELECT from_id, neighbor_id, snr, ts FROM neighbor_info ORDER BY ts DESC'
        )
        rows = await cur.fetchall()
        return [{'from_id': r[0], 'neighbor_id': r[1], 'snr': r[2], 'ts': r[3]} for r in rows]


async def save_sensor_event(from_id: str, etype: str, data: dict) -> None:
    async with _get_db() as db:
        await db.execute(
            'INSERT INTO sensor_events (ts, from_id, type, data_json) VALUES (?,?,?,?)',
            (int(time.time()), from_id, etype, json.dumps(data))
        )
        await db.commit()
```

- [ ] **Step 3: Crea `tests/test_new_packets_db.py`**

```python
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
```

- [ ] **Step 4: Esegui test**

```bash
cd ~/Desktop/GitHub/pi-Mesh && python -m pytest tests/test_new_packets_db.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_new_packets_db.py
git commit -m "feat(packets): add waypoints, neighbor_info, sensor_events tables and DB functions"
```

---

### Task 2: Handler portnum in meshtasticd_client.py

**Files:**
- Modify: `meshtasticd_client.py`

- [ ] **Step 1: Estendi `_build_log_summary`**

Trova `elif portnum == 'TRACEROUTE_APP':` in `_build_log_summary` e aggiungi dopo:

```python
        elif portnum == 'WAYPOINT_APP':
            wp = decoded.get('waypoint', {})
            name = wp.get('name', '')
            return f"Waypoint: {name}" if name else 'Waypoint'
        elif portnum == 'NEIGHBORINFO_APP':
            neighbors = decoded.get('neighborinfo', {}).get('neighbors', [])
            return f"{len(neighbors)} neighbor(s)"
        elif portnum == 'DETECTION_SENSOR_APP':
            ds = decoded.get('detectionSensor', {})
            triggered = ds.get('triggered', False)
            name = ds.get('name', 'sensor')
            return f"{name}: triggered" if triggered else f"{name}: cleared"
        elif portnum == 'PAXCOUNTER_APP':
            px = decoded.get('paxcounter', {})
            return f"BLE: {px.get('ble', 0)} WiFi: {px.get('wifi', 0)}"
```

- [ ] **Step 2: Aggiungi handler in `_on_receive`**

Trova `elif portnum == 'ROUTING_APP':` in `_on_receive` e aggiungi dopo (prima del commento `# Notify log subscribers`):

```python
    elif portnum == 'WAYPOINT_APP':
        wp_raw = decoded.get('waypoint', {})
        lat = wp_raw.get('latitudeI', 0) / 1e7 if wp_raw.get('latitudeI') else None
        lon = wp_raw.get('longitudeI', 0) / 1e7 if wp_raw.get('longitudeI') else None
        wp = {
            'id':          wp_raw.get('id', int(time.time())),
            'name':        wp_raw.get('name', ''),
            'lat':         lat,
            'lon':         lon,
            'icon':        wp_raw.get('icon', 'default'),
            'description': wp_raw.get('description', ''),
            'expire':      wp_raw.get('expire', 0),
            'from_id':     from_id,
            'ts':          int(time.time()),
        }
        if lat is not None and lon is not None and _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                database.upsert_waypoint(wp), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('upsert_waypoint failed: %s', f.exception())
                if f.exception() else None
            )
            _loop.call_soon_threadsafe(_enqueue_event, {'type': 'waypoint', **wp})

    elif portnum == 'NEIGHBORINFO_APP':
        ni = decoded.get('neighborinfo', {})
        neighbors = ni.get('neighbors', [])
        for nb in neighbors:
            neighbor_id = f"!{nb.get('nodeId', 0):08x}"
            snr = float(nb.get('snr', 0.0))
            if _loop is not None:
                fut = asyncio.run_coroutine_threadsafe(
                    database.upsert_neighbor_info(from_id, neighbor_id, snr), _loop
                )
                fut.add_done_callback(
                    lambda f: logger.error('upsert_neighbor_info failed: %s', f.exception())
                    if f.exception() else None
                )
        typed_event = {
            'type':      'neighbor_info',
            'from_id':   from_id,
            'neighbors': [{'node_id': f"!{nb.get('nodeId',0):08x}", 'snr': float(nb.get('snr', 0.0))}
                          for nb in neighbors],
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_enqueue_event, typed_event)

    elif portnum == 'DETECTION_SENSOR_APP':
        ds = decoded.get('detectionSensor', {})
        data = {'triggered': ds.get('triggered', False), 'name': ds.get('name', '')}
        if _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                database.save_sensor_event(from_id, 'detection', data), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_sensor_event failed: %s', f.exception())
                if f.exception() else None
            )
            _loop.call_soon_threadsafe(_enqueue_event, {'type': 'sensor', 'from_id': from_id, 'data': data})

    elif portnum == 'PAXCOUNTER_APP':
        px = decoded.get('paxcounter', {})
        data = {'ble': px.get('ble', 0), 'wifi': px.get('wifi', 0)}
        if _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                database.save_sensor_event(from_id, 'paxcounter', data), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_sensor_event failed: %s', f.exception())
                if f.exception() else None
            )
            _loop.call_soon_threadsafe(_enqueue_event, {'type': 'paxcounter', 'from_id': from_id, 'data': data})
```

- [ ] **Step 3: Commit**

```bash
git add meshtasticd_client.py
git commit -m "feat(packets): add handlers for WAYPOINT, NEIGHBORINFO, DETECTION_SENSOR, PAXCOUNTER"
```

---

### Task 3: Router waypoints e neighbor_info

**Files:**
- Create: `routers/waypoints_router.py`
- Create: `routers/neighbor_router.py`
- Modify: `meshtasticd_client.py` (aggiunta `send_waypoint`)
- Modify: `main.py`

- [ ] **Step 1: Aggiungi `send_waypoint` in `meshtasticd_client.py`**

Aggiungi dopo `set_lora_config`:

```python
async def send_waypoint(name: str, lat: float, lon: float,
                        icon: str, description: str, expire: int) -> None:
    """Send a waypoint via serial interface."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    import random
    wp_id = random.randint(1, 0x7FFFFFFF)
    _n, _la, _lo, _ic, _de, _ex, _id = name, lat, lon, icon, description, expire, wp_id

    def _do():
        from meshtastic.protobuf import mesh_pb2
        wp = mesh_pb2.Waypoint(
            id=_id,
            name=_n,
            description=_de,
            expire=_ex,
            latitude_i=int(_la * 1e7),
            longitude_i=int(_lo * 1e7),
        )
        _interface.sendWaypoint(wp)

    await _command_queue.put(_do)
```

- [ ] **Step 2: Crea `routers/waypoints_router.py`**

```python
# routers/waypoints_router.py
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import database
import meshtasticd_client

router = APIRouter()


@router.get('/api/waypoints')
async def get_waypoints():
    return await database.get_waypoints(active_only=True)


@router.delete('/api/waypoints/{wp_id}')
async def delete_waypoint(wp_id: int):
    await database.delete_waypoint(wp_id)
    return {'ok': True}


class WaypointSend(BaseModel):
    name: str
    lat: float
    lon: float
    icon: str = 'default'
    description: str = ''
    expire_hours: int = 24


@router.post('/api/waypoints/send')
async def send_waypoint(body: WaypointSend):
    if not meshtasticd_client.is_connected():
        raise HTTPException(503, detail='board not connected')
    expire_ts = int(time.time()) + body.expire_hours * 3600 if body.expire_hours > 0 else 0
    await meshtasticd_client.send_waypoint(
        name=body.name, lat=body.lat, lon=body.lon,
        icon=body.icon, description=body.description, expire=expire_ts,
    )
    return {'ok': True}
```

- [ ] **Step 3: Crea `routers/neighbor_router.py`**

```python
# routers/neighbor_router.py
from fastapi import APIRouter
import database

router = APIRouter()


@router.get('/api/neighbor-info')
async def get_neighbor_info():
    return await database.get_neighbor_info()
```

- [ ] **Step 4: Registra in `main.py`**

Aggiungi `waypoints_router, neighbor_router` all'import dei router e le righe `app.include_router(...)` corrispondenti dopo `module_config_router`.

Import (aggiorna la riga esistente):
```python
from routers import nodes, map_router, log_router, commands, ws_router, messages_router, config_router, metrics_router, canned_router, module_config_router, waypoints_router, neighbor_router
```

Include (aggiungi dopo `app.include_router(module_config_router.router)`):
```python
app.include_router(waypoints_router.router)
app.include_router(neighbor_router.router)
```

- [ ] **Step 5: Commit**

```bash
git add routers/waypoints_router.py routers/neighbor_router.py main.py meshtasticd_client.py
git commit -m "feat(packets): add waypoints and neighbor_info routers + send_waypoint"
```

---

### Task 4: map.js — layer waypoints e neighbor links

**Files:**
- Modify: `static/map.js`

- [ ] **Step 1: Aggiungi `showWaypoints` e `showNeighborLinks` a `DEFAULT_FILTERS`**

Trova:
```javascript
  showHopLines: true, showCustomMarkers: true, showLocalNode: true,
  showBreadcrumbs: true,
```

Sostituisci con:
```javascript
  showHopLines: true, showCustomMarkers: true, showLocalNode: true,
  showBreadcrumbs: true, showWaypoints: true, showNeighborLinks: false,
```

- [ ] **Step 2: Dichiara variabili layer globali**

Trova la sezione con le altre dichiarazioni `var hopLinesLayer, tracerouteLayer` e aggiungi:
```javascript
var waypointsLayer, neighborLinksLayer
```

Trova il blocco dove vengono inizializzati i layer (con `L.layerGroup()`):
```javascript
  hopLinesLayer = L.layerGroup()
  tracerouteLayer = L.layerGroup()
  customMarkersLayer = L.layerGroup()
  breadcrumbLayer = L.layerGroup()
```

Aggiungi dopo:
```javascript
  waypointsLayer = L.layerGroup()
  neighborLinksLayer = L.layerGroup()
```

- [ ] **Step 3: Aggiungi applyFilters per nuovi layer**

Trova:
```javascript
  if (f.showHopLines)      hopLinesLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(hopLinesLayer)
```

Aggiungi dopo:
```javascript
  if (f.showWaypoints)     waypointsLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(waypointsLayer)
  if (f.showNeighborLinks) neighborLinksLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(neighborLinksLayer)
```

- [ ] **Step 4: Aggiungi bindCheckbox**

Trova `bindCheckbox('filter-hoplines', 'showHopLines')` e aggiungi dopo:
```javascript
  bindCheckbox('filter-waypoints',  'showWaypoints')
  bindCheckbox('filter-neighbor',   'showNeighborLinks')
```

- [ ] **Step 5: Aggiungi helper `escHtml` e funzioni waypoints/neighbor**

Aggiungi dopo la funzione `snrColor` (o definiscila se non esiste nel file):

```javascript
function snrColor(snr) {
  if (snr == null) return '#888'
  if (snr >= 5)   return '#4caf50'
  if (snr >= 0)   return '#fb8c00'
  return '#e53935'
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function renderWaypoints(waypoints) {
  if (!waypointsLayer) return
  waypointsLayer.clearLayers()
  waypoints.forEach(function(wp) {
    if (wp.lat == null || wp.lon == null) return
    var icon = L.divIcon({
      html: '<span style="font-size:18px;line-height:1;">&#128205;</span>',
      className: '',
      iconSize: [22, 22],
      iconAnchor: [11, 22],
    })
    var marker = L.marker([wp.lat, wp.lon], {icon: icon})
    var expireStr = wp.expire ? new Date(wp.expire * 1000).toLocaleString() : 'Mai'
    var popupEl = document.createElement('div')
    var title = document.createElement('b')
    title.textContent = wp.name || 'Waypoint'
    popupEl.appendChild(title)
    if (wp.description) {
      var desc = document.createElement('div')
      desc.textContent = wp.description
      popupEl.appendChild(desc)
    }
    var meta = document.createElement('div')
    meta.style.fontSize = '9px'
    meta.textContent = 'Da: ' + wp.from_id + ' — Scade: ' + expireStr
    popupEl.appendChild(meta)
    var delBtn = document.createElement('button')
    delBtn.textContent = 'Elimina'
    delBtn.style.cssText = 'margin-top:4px;font-size:10px;color:#e53935;background:none;border:1px solid #e53935;border-radius:3px;padding:2px 6px;cursor:pointer;'
    delBtn.onclick = function() { deleteWaypoint(wp.id) }
    popupEl.appendChild(delBtn)
    marker.bindPopup(popupEl, {maxWidth: 180})
    waypointsLayer.addLayer(marker)
  })
}

function deleteWaypoint(id) {
  fetch('/api/waypoints/' + id, {method: 'DELETE'}).then(function() { loadWaypoints() })
}

function loadWaypoints() {
  fetch('/api/waypoints').then(function(r) { return r.json() }).then(renderWaypoints)
}

function renderNeighborLinks(links) {
  if (!neighborLinksLayer) return
  neighborLinksLayer.clearLayers()
  links.forEach(function(link) {
    var fromNode = nodeCache.get(link.from_id)
    var toNode   = nodeCache.get(link.neighbor_id)
    if (!fromNode || !toNode) return
    if (fromNode.latitude == null || toNode.latitude == null) return
    var line = L.polyline(
      [[fromNode.latitude, fromNode.longitude], [toNode.latitude, toNode.longitude]],
      {color: snrColor(link.snr), weight: 2, opacity: 0.65}
    )
    line.bindTooltip('SNR: ' + (link.snr != null ? link.snr.toFixed(1) : '?') + ' dB', {sticky: true})
    neighborLinksLayer.addLayer(line)
  })
}

function loadNeighborLinks() {
  fetch('/api/neighbor-info').then(function(r) { return r.json() }).then(renderNeighborLinks)
}
```

- [ ] **Step 6: Chiama loadWaypoints e loadNeighborLinks all'avvio**

Trova il blocco di fine inizializzazione (dopo `applyFilters(filters)`) e aggiungi:
```javascript
  loadWaypoints()
  loadNeighborLinks()
```

- [ ] **Step 7: Gestisci WS events `waypoint` e `neighbor_info`**

Nel WebSocket handler (dove vengono gestiti `data.type`), aggiungi:
```javascript
      case 'waypoint':
        loadWaypoints()
        break
      case 'neighbor_info':
        loadNeighborLinks()
        break
```

- [ ] **Step 8: Commit**

```bash
git add static/map.js
git commit -m "feat(packets): add waypoints and neighbor links layers to map"
```

---

### Task 5: map.html — checkbox filtri + tab Topology e Waypoints

**Files:**
- Modify: `templates/map.html`

- [ ] **Step 1: Aggiungi checkbox nel filter-panel**

Trova:
```html
<input type="checkbox" id="filter-breadcrumbs" style="accent-color:var(--accent,#4a9eff);"> Tracce GPS
```

Aggiungi dopo la `</label>` corrispondente:
```html
<label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
  <input type="checkbox" id="filter-waypoints" style="accent-color:var(--accent,#4a9eff);"> Waypoints
</label>
<label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
  <input type="checkbox" id="filter-neighbor" style="accent-color:var(--accent,#4a9eff);"> Neighbor links
</label>
```

- [ ] **Step 2: Sostituisci header right-panel con tab bar**

Trova:
```html
<div style="padding:5px 10px;font-size:9px;color:var(--accent);text-transform:uppercase;
            border-bottom:1px solid var(--border);">Filtri</div>
```

Sostituisci con:
```html
<div style="display:flex;border-bottom:1px solid var(--border);">
  <button id="panel-tab-filters"
          onclick="setPanelTab('filters')"
          style="flex:1;padding:5px 0;font-size:9px;border:none;cursor:pointer;
                 color:var(--accent);background:var(--panel);border-bottom:2px solid var(--accent);">
    Filtri
  </button>
  <button id="panel-tab-topology"
          onclick="setPanelTab('topology')"
          style="flex:1;padding:5px 0;font-size:9px;border:none;cursor:pointer;
                 color:var(--muted);background:transparent;border-bottom:2px solid transparent;">
    Topo
  </button>
  <button id="panel-tab-waypoints"
          onclick="setPanelTab('waypoints')"
          style="flex:1;padding:5px 0;font-size:9px;border:none;cursor:pointer;
                 color:var(--muted);background:transparent;border-bottom:2px solid transparent;">
    WP
  </button>
</div>
```

- [ ] **Step 3: Aggiungi pannelli Topology e Waypoints**

Trova `</div>` che chiude `#right-panel` e aggiungi prima:

```html
<div id="panel-topology"
     style="display:none;padding:8px;overflow-y:auto;flex:1;flex-direction:column;">
  <div style="font-size:9px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:6px;">
    Grafo mesh
  </div>
  <svg id="topology-svg" width="144" height="200"
       style="background:rgba(0,0,0,.2);border-radius:4px;display:block;"></svg>
  <button onclick="renderTopologyGraph()"
          style="margin-top:6px;width:100%;padding:4px 0;font-size:9px;
                 background:none;border:1px solid var(--border);border-radius:3px;
                 color:var(--muted);cursor:pointer;">
    Aggiorna
  </button>
</div>

<div id="panel-waypoints"
     style="display:none;padding:8px;overflow-y:auto;flex:1;flex-direction:column;">
  <div style="font-size:9px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:6px;">
    Waypoints attivi
  </div>
  <div id="waypoints-list" style="font-size:10px;color:var(--text);"></div>
</div>
```

- [ ] **Step 4: Aggiungi funzioni JS inline**

Nel blocco `<script>` alla fine di map.html, aggiungi:

```javascript
function setPanelTab(tab) {
  var tabs = ['filters', 'topology', 'waypoints']
  tabs.forEach(function(t) {
    var btn = document.getElementById('panel-tab-' + t)
    var panel = t === 'filters'
      ? document.getElementById('filter-panel')
      : document.getElementById('panel-' + t)
    if (btn) {
      var active = (t === tab)
      btn.style.color      = active ? 'var(--accent)' : 'var(--muted)'
      btn.style.background = active ? 'var(--panel)'  : 'transparent'
      btn.style.borderBottom = active ? '2px solid var(--accent)' : '2px solid transparent'
    }
    if (panel) panel.style.display = (t === tab) ? 'block' : 'none'
  })
  if (tab === 'topology')  renderTopologyGraph()
  if (tab === 'waypoints') refreshWaypointsList()
}

function renderTopologyGraph() {
  var svg = document.getElementById('topology-svg')
  if (!svg) return
  fetch('/api/neighbor-info').then(function(r) { return r.json() }).then(function(links) {
    while (svg.firstChild) svg.removeChild(svg.firstChild)
    var nodeIds = {}
    links.forEach(function(l) { nodeIds[l.from_id] = 1; nodeIds[l.neighbor_id] = 1 })
    var ids = Object.keys(nodeIds)
    if (ids.length === 0) {
      var t = document.createElementNS('http://www.w3.org/2000/svg', 'text')
      t.setAttribute('x', '72'); t.setAttribute('y', '100')
      t.setAttribute('text-anchor', 'middle')
      t.setAttribute('fill', '#666'); t.setAttribute('font-size', '10')
      t.textContent = 'Nessun dato'
      svg.appendChild(t)
      return
    }
    var W = 144, H = 200, cx = W / 2, cy = H / 2, r = Math.min(cx, cy) - 20
    var pos = {}
    ids.forEach(function(id, i) {
      var angle = (2 * Math.PI * i / ids.length) - Math.PI / 2
      pos[id] = {x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle)}
    })
    links.forEach(function(l) {
      var a = pos[l.from_id], b = pos[l.neighbor_id]
      if (!a || !b) return
      var line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
      line.setAttribute('x1', a.x); line.setAttribute('y1', a.y)
      line.setAttribute('x2', b.x); line.setAttribute('y2', b.y)
      line.setAttribute('stroke', snrColor(l.snr))
      line.setAttribute('stroke-width', '1.5')
      line.setAttribute('opacity', '0.7')
      svg.appendChild(line)
    })
    ids.forEach(function(id) {
      var p = pos[id]
      var node = nodeCache ? nodeCache.get(id) : null
      var isLocal = node && node.is_local
      var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      circle.setAttribute('cx', p.x); circle.setAttribute('cy', p.y)
      circle.setAttribute('r', isLocal ? 8 : 6)
      circle.setAttribute('fill', isLocal ? '#2196f3' : '#333')
      circle.setAttribute('stroke', '#fff'); circle.setAttribute('stroke-width', '1')
      svg.appendChild(circle)
      var label = document.createElementNS('http://www.w3.org/2000/svg', 'text')
      label.setAttribute('x', p.x); label.setAttribute('y', p.y + 3)
      label.setAttribute('text-anchor', 'middle')
      label.setAttribute('fill', '#ccc'); label.setAttribute('font-size', '7')
      label.textContent = isLocal ? 'ME' : id.slice(-4)
      svg.appendChild(label)
    })
  })
}

function refreshWaypointsList() {
  fetch('/api/waypoints').then(function(r) { return r.json() }).then(function(data) {
    var el = document.getElementById('waypoints-list')
    if (!el) return
    while (el.firstChild) el.removeChild(el.firstChild)
    if (data.length === 0) {
      var empty = document.createElement('div')
      empty.style.color = 'var(--muted)'
      empty.textContent = 'Nessun waypoint'
      el.appendChild(empty)
      return
    }
    data.forEach(function(wp) {
      var item = document.createElement('div')
      item.style.cssText = 'border-bottom:1px solid var(--border);padding:4px 0;'
      var name = document.createElement('b')
      name.textContent = wp.name || '?'
      item.appendChild(name)
      var meta = document.createElement('div')
      meta.style.cssText = 'font-size:9px;color:var(--muted);'
      meta.textContent = wp.from_id
      item.appendChild(meta)
      el.appendChild(item)
    })
  })
}
```

- [ ] **Step 5: Aggiorna versione cache-busting**

Trova `<script src="/static/map.js?v=13"></script>` e sostituisci `v=13` con `v=14`.

- [ ] **Step 6: Commit**

```bash
git add templates/map.html
git commit -m "feat(packets): add Topology and Waypoints tabs to map panel"
```

---

### Task 6: Deploy e verifica su Pi

- [ ] **Step 1: Deploy**

```bash
sshpass -p pimesh rsync -avz --relative \
  database.py meshtasticd_client.py \
  routers/waypoints_router.py routers/neighbor_router.py \
  main.py static/map.js templates/map.html \
  tests/test_new_packets_db.py \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Verifica API**

```bash
curl http://192.168.1.36:8080/api/waypoints
# Expected: []

curl http://192.168.1.36:8080/api/neighbor-info
# Expected: []
```

- [ ] **Step 3: Verifica mappa**

Apri `http://192.168.1.36:8080/map` → pannello laterale → verifica 3 tab (Filtri / Topo / WP) → tab Topo → "Nessun dato" → pannello Filtri → checkbox Waypoints e Neighbor links presenti.

- [ ] **Step 4: Commit finale**

```bash
git add -A
git commit -m "feat: M9 complete — new packet types (YAY-170)"
```
