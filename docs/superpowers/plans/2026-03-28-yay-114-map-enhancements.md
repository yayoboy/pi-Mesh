# YAY-114 — Map Enhancements: Implementation Plan

**Data:** 2026-03-28
**Issue:** [YAY-114](https://linear.app/yayoboy/issue/YAY-114/mappa)
**Branch:** `feature/yay-114-map-enhancements`
**Worktree:** `/Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements`

---

## Goal

Trasformare la mappa da visualizzatore di marker statici a strumento operativo completo:
legenda visiva, linee hop colorate per SNR, filtri persistenti, marker personalizzati con
sidebar, context menu long-press sui nodi, e traceroute end-to-end (richiesta → parsing
pacchetto → visualizzazione percorso giallo).

---

## Architecture

```
meshtastic_client.py          database.py               main.py
  request_traceroute()  ───>  save_traceroute()  <───  POST /api/traceroute
  _on_receive_traceroute()     get_traceroutes()         GET  /api/traceroute/{node_id}
  _handle_traceroute()         save_marker()             GET  /api/map/markers
       | _broadcast()          get_markers()             POST /api/map/markers
       v                       delete_marker()           DELETE /api/map/markers/{id}
  WebSocket "traceroute_result"
       |
       v (app.js dispatch)
  window event "traceroute_result"
       |
       v (map.js listener)
  renderTraceroutePath(hops)    <── also triggered by URL param ?traceroute=
```

**Nuovo file `static/map.js`** — tutta la logica mappa, caricato solo da `map.html`.
`app.js` mantiene il dispatch WebSocket e chiama `initMapIfNeeded()` / `updateMapMarker()`
che ora risiedono in `map.js` (stessa API pubblica, zero break per `app.js`).

---

## Tech Stack

- Python 3.11 · aiosqlite · FastAPI · pypubsub
- Vanilla JS (ES2020, no bundle) · Leaflet 1.9.4 · SVG Heroicons inline
- SQLite con migration try/except ALTER TABLE (pattern esistente)

---

## Files Modified / Created

| File | Operazione |
|------|-----------|
| `database.py` | Modifica — 2 nuove tabelle + 5 funzioni + `import json` |
| `meshtastic_client.py` | Modifica — `request_traceroute()` + handler traceroute |
| `main.py` | Modifica — 5 nuovi endpoint |
| `static/map.js` | Crea — tutta la logica mappa |
| `static/app.js` | Modifica — rimuovi sezione MAPPA + aggiungi handler `traceroute_result` |
| `templates/map.html` | Riscrittura — sidebar + filtri + legenda + modal + carica map.js |
| `templates/nodes.html` | Modifica — bottone Traceroute nel menu azioni nodo |
| `tests/test_database.py` | Modifica — 3 nuovi test per le funzioni DB |

---

## Task 1 — DB: tabelle `map_markers` + `traceroute_results` + 5 funzioni

**TDD: scrivi i test prima, verifica che falliscano, implementa, verifica che passino.**

**Files:** `database.py`, `tests/test_database.py`

### Step 1.1 — Aggiungi i 3 test al file di test (RED)

- [ ] Apri `tests/test_database.py` e aggiungi alla fine questi tre test:

```python
@pytest.mark.asyncio
async def test_save_and_get_marker(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    marker_id = await database.save_marker(conn, "Test", "poi", 45.0, 9.0)
    markers = await database.get_markers(conn)
    assert len(markers) == 1
    assert markers[0]["label"] == "Test"
    assert markers[0]["id"] == marker_id
    await conn.close()

@pytest.mark.asyncio
async def test_delete_marker(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    mid = await database.save_marker(conn, "Del", "poi", 45.0, 9.0)
    await database.delete_marker(conn, mid)
    markers = await database.get_markers(conn)
    assert len(markers) == 0
    await conn.close()

@pytest.mark.asyncio
async def test_save_and_get_traceroute(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    hops = ["!local", "!a1b2c3d4", "!dest0001"]
    tid = await database.save_traceroute(conn, "!dest0001", hops)
    results = await database.get_traceroutes(conn, "!dest0001")
    assert len(results) == 1
    assert results[0]["hops"] == hops
    assert results[0]["id"] == tid
    await conn.close()
```

### Step 1.2 — Verifica che i 3 nuovi test falliscano (RED)

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -m pytest tests/test_database.py -v -k "marker or traceroute"
  ```
  Atteso: **3 FAILED** — `AttributeError: module 'database' has no attribute 'save_marker'`
  (i 10 test esistenti devono continuare a passare)

### Step 1.3 — Aggiungi `import json` in cima a `database.py`

- [ ] La riga 1 di `database.py` e' attualmente:
  ```python
  import asyncio, os, shutil, logging, time
  ```
  Cambiala in:
  ```python
  import asyncio, json, os, shutil, logging, time
  ```

### Step 1.4 — Aggiungi le 2 nuove tabelle in `_create_tables`

- [ ] In `database.py`, alla fine della funzione `_create_tables`, subito dopo il secondo
  `await conn.commit()` (riga 81, quello dopo i migration ALTER TABLE), aggiungi:

```python
    # YAY-114: tabelle mappa e traceroute
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS map_markers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            label      TEXT NOT NULL,
            icon_type  TEXT NOT NULL DEFAULT 'poi',
            latitude   REAL NOT NULL,
            longitude  REAL NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS traceroute_results (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id   TEXT NOT NULL,
            hops      TEXT NOT NULL,
            timestamp INTEGER NOT NULL
        )
    """)
    await conn.commit()
```

### Step 1.5 — Aggiungi le 5 nuove funzioni in `database.py`

- [ ] Aggiungi alla fine del file `database.py`, subito prima della funzione `sync_to_sd`:

```python
# --- YAY-114: Map markers ---

async def save_marker(conn, label: str, icon_type: str, latitude: float, longitude: float) -> int:
    cur = await conn.execute(
        "INSERT INTO map_markers (label, icon_type, latitude, longitude, created_at) VALUES (?,?,?,?,?)",
        (label, icon_type, latitude, longitude, int(time.time()))
    )
    await conn.commit()
    return cur.lastrowid

async def get_markers(conn) -> list:
    cur = await conn.execute("SELECT * FROM map_markers ORDER BY created_at DESC")
    return [dict(r) for r in await cur.fetchall()]

async def delete_marker(conn, marker_id: int):
    await conn.execute("DELETE FROM map_markers WHERE id = ?", (marker_id,))
    await conn.commit()

async def save_traceroute(conn, node_id: str, hops: list) -> int:
    cur = await conn.execute(
        "INSERT INTO traceroute_results (node_id, hops, timestamp) VALUES (?,?,?)",
        (node_id, json.dumps(hops), int(time.time()))
    )
    await conn.commit()
    return cur.lastrowid

async def get_traceroutes(conn, node_id: str, limit: int = 10) -> list:
    cur = await conn.execute(
        "SELECT * FROM traceroute_results WHERE node_id=? ORDER BY timestamp DESC LIMIT ?",
        (node_id, limit)
    )
    rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["hops"] = json.loads(r["hops"])
    return rows
```

Note: `sync_to_sd` rimane l'ultima funzione del file.

### Step 1.6 — Verifica GREEN + tutti i test passano

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -m pytest tests/test_database.py -v
  ```
  Atteso: **13 passed** (10 preesistenti + 3 nuovi)

  Verifica anche che le nuove tabelle vengano create:
  ```bash
  python3 -c "
  import asyncio, database
  async def chk():
      c = await database.init_db(runtime_path='/tmp/test_yay114.db', persistent_path='/tmp/test_yay114_p.db')
      cur = await c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
      print([r[0] for r in await cur.fetchall()])
      await c.close()
  asyncio.run(chk())
  "
  ```
  Atteso: lista include `map_markers` e `traceroute_results`

### Step 1.7 — Commit

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  git add database.py tests/test_database.py
  git commit -m "feat(yay-114): DB map_markers + traceroute_results tables + 5 functions"
  ```

---

## Task 2 — meshtastic_client.py: `request_traceroute` + handler

**Files:** `meshtastic_client.py`

### Step 2.1 — Aggiungi `request_traceroute` e i due handler

- [ ] In `meshtastic_client.py`, dopo la funzione `request_position` (che termina
  alla riga ~155), inserisci:

```python
async def request_traceroute(node_id: str):
    """Invia richiesta traceroute al nodo specificato."""
    iface = _interface
    if iface is None:
        raise RuntimeError("Meshtastic non connesso")
    await asyncio.to_thread(iface.sendTraceRoute, node_id, hopLimit=7)

def _on_receive_traceroute(packet, interface):
    _bridge(_handle_traceroute(packet))

async def _handle_traceroute(packet):
    import database
    try:
        node_id    = packet.get("toId", "unknown")
        from_id    = packet.get("fromId", "unknown")
        route_nums = packet.get("decoded", {}).get("traceroute", {}).get("route", [])
        # Costruisci lista hop: mittente -> intermedi -> destinazione
        hops = [from_id] + [f"!{num:08x}" for num in route_nums] + [node_id]
        if _conn_getter:
            await database.save_traceroute(_conn_getter(), node_id, hops)
        await _broadcast({"type": "traceroute_result", "data": {
            "node_id":   node_id,
            "hops":      hops,
            "timestamp": int(time.time()),
        }})
        _log_event("info", f"Traceroute verso {node_id}: {len(hops)-1} hop")
    except Exception as e:
        logging.error(f"Parsing traceroute fallito: {e}")
```

### Step 2.2 — Registra il subscriber in `init()`

- [ ] In `meshtastic_client.py`, nella funzione `init()` (riga ~51), subito dopo la riga
  che registra `_on_receive_routing`, aggiungi:

```python
    pub.subscribe(_on_receive_traceroute,  "meshtastic.receive.traceroute")
```

  Il blocco completo dopo la modifica:
  ```python
  pub.subscribe(_on_receive_text,        "meshtastic.receive.text")
  pub.subscribe(_on_receive_telemetry,   "meshtastic.receive.telemetry")
  pub.subscribe(_on_receive_position,    "meshtastic.receive.position")
  pub.subscribe(_on_receive_user,        "meshtastic.receive.user")
  pub.subscribe(_on_connected,           "meshtastic.connection.established")
  pub.subscribe(_on_lost,                "meshtastic.connection.lost")
  pub.subscribe(_on_receive_routing,     "meshtastic.receive.routing")
  pub.subscribe(_on_receive_traceroute,  "meshtastic.receive.traceroute")
  ```

### Step 2.3 — Verifica sintassi

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -c "import meshtastic_client; print('OK')"
  ```
  Atteso: `OK`

### Step 2.4 — Commit

- [ ] Esegui:
  ```bash
  git add meshtastic_client.py
  git commit -m "feat(yay-114): traceroute request + receive handler in meshtastic_client"
  ```

---

## Task 3 — main.py: 5 nuovi endpoint

**Files:** `main.py`

### Step 3.1 — Aggiungi i 5 endpoint dopo `/api/dm/read`

- [ ] In `main.py`, dopo il blocco `@app.post("/api/dm/read")` (che termina alla
  riga ~208), inserisci:

```python
# --- YAY-114: Map markers ---

@app.get("/api/map/markers")
async def api_map_markers():
    markers = await database.get_markers(_conn)
    return JSONResponse({"markers": markers})

@app.post("/api/map/markers")
async def api_map_markers_create(payload: dict):
    label     = payload.get("label", "").strip()
    icon_type = payload.get("icon_type", "poi")
    latitude  = payload.get("latitude")
    longitude = payload.get("longitude")
    if not label or latitude is None or longitude is None:
        return JSONResponse(
            {"ok": False, "error": "label, latitude e longitude obbligatori"},
            status_code=400
        )
    if icon_type not in ("antenna", "base", "obstacle", "poi"):
        icon_type = "poi"
    marker_id = await database.save_marker(
        _conn, label, icon_type, float(latitude), float(longitude)
    )
    return JSONResponse({"ok": True, "id": marker_id})

@app.delete("/api/map/markers/{marker_id}")
async def api_map_markers_delete(marker_id: int):
    await database.delete_marker(_conn, marker_id)
    return JSONResponse({"ok": True})

# --- YAY-114: Traceroute ---

@app.post("/api/traceroute")
async def api_traceroute_start(payload: dict):
    node_id = payload.get("node_id", "").strip()
    if not node_id:
        return JSONResponse(
            {"ok": False, "error": "node_id obbligatorio"},
            status_code=400
        )
    try:
        await meshtastic_client.request_traceroute(node_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/api/traceroute/{node_id}")
async def api_traceroute_get(node_id: str):
    results = await database.get_traceroutes(_conn, node_id, limit=10)
    return JSONResponse({"results": results})
```

### Step 3.2 — Verifica sintassi e route registrate

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -c "import main; print('OK')"
  ```
  Atteso: `OK`

- [ ] Verifica route:
  ```bash
  python3 -c "
  import main
  for r in main.app.routes:
      if hasattr(r, 'path') and ('map' in r.path or 'traceroute' in r.path):
          print(r.path)
  "
  ```
  Atteso (in qualsiasi ordine):
  ```
  /api/map/markers
  /api/map/markers/{marker_id}
  /api/traceroute
  /api/traceroute/{node_id}
  ```

### Step 3.3 — Commit

- [ ] Esegui:
  ```bash
  git add main.py
  git commit -m "feat(yay-114): 5 new endpoints — map markers + traceroute"
  ```

---

## Task 4 — static/map.js: nuovo file con tutta la logica mappa

**Files:** `static/map.js`

### Step 4.1 — Crea `static/map.js`

- [ ] Crea il file con il contenuto seguente.
  Nota: `escHtml()` e `nodeCache` sono globali definiti in `app.js` e sempre disponibili
  quando `map.js` e' caricato (perche' `base.html` carica `app.js` prima di `map.html`
  che carica `map.js`).

```javascript
// static/map.js — YAY-114 map enhancements
// Caricato solo da map.html, NON da base.html
'use strict'

// --- Stato globale ---

let leafletMap = null
let mapReady = false
const markerCache = new Map()
const hopLinesLayer = L.layerGroup()
const tracerouteLayer = L.layerGroup()
const customMarkersLayer = L.layerGroup()
let customMarkersData = []

// --- Icone SVG Heroicons ---

const ICON_PATHS = {
  antenna:  'M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0',
  base:     'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
  obstacle: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  poi:      'M17.657 16.657L13.414 20.9a2 2 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z',
  route:    'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7',
}

function makeSvgIcon(type, size, color) {
  size = size || 16
  color = color || 'currentColor'
  const path = ICON_PATHS[type] || ICON_PATHS.poi
  return '<svg width="' + size + '" height="' + size + '" fill="none" stroke="' + color +
    '" stroke-width="2" viewBox="0 0 24 24">' +
    '<path stroke-linecap="round" stroke-linejoin="round" d="' + path + '"/></svg>'
}

// --- Filtri ---

const DEFAULT_FILTERS = {
  showOnline: true, showOffline: false,
  showHopLines: true, showCustomMarkers: true, showLocalNode: true,
  maxHops: 7,
}

function loadFilters() {
  try {
    return Object.assign({}, DEFAULT_FILTERS, JSON.parse(localStorage.getItem('mapFilters') || '{}'))
  } catch (e) {
    return Object.assign({}, DEFAULT_FILTERS)
  }
}

function saveFilters(f) {
  localStorage.setItem('mapFilters', JSON.stringify(f))
}

function applyFilters() {
  if (!mapReady) return
  var f = loadFilters()
  markerCache.forEach(function(marker, nodeId) {
    var node = nodeCache.get(nodeId)
    if (!node) return
    var ago    = Date.now() / 1000 - (node.last_heard || 0)
    var online = ago < 1800
    var isLocal = !!node.is_local
    var visible = true
    if (isLocal && !f.showLocalNode)          visible = false
    if (!isLocal && online  && !f.showOnline)  visible = false
    if (!isLocal && !online && !f.showOffline) visible = false
    if (node.hop_count != null && node.hop_count > f.maxHops) visible = false
    if (visible) marker.addTo(leafletMap)
    else         leafletMap.removeLayer(marker)
  })
  if (f.showHopLines)      hopLinesLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(hopLinesLayer)
  if (f.showCustomMarkers) customMarkersLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(customMarkersLayer)
}

function initFilters() {
  var panel = document.getElementById('filter-panel')
  if (!panel) return
  var f = loadFilters()

  function bindCheckbox(id, key) {
    var el = document.getElementById(id)
    if (!el) return
    el.checked = f[key]
    el.onchange = function() {
      var nf = loadFilters()
      nf[key] = el.checked
      saveFilters(nf)
      applyFilters()
      renderHopLines()
    }
  }

  function bindRange(id, key) {
    var el  = document.getElementById(id)
    var lbl = document.getElementById(id + '-val')
    if (!el) return
    el.value = f[key]
    if (lbl) lbl.textContent = f[key]
    el.oninput = function() {
      var nf = loadFilters()
      nf[key] = parseInt(el.value)
      saveFilters(nf)
      if (lbl) lbl.textContent = el.value
      applyFilters()
    }
  }

  bindCheckbox('filter-online',   'showOnline')
  bindCheckbox('filter-offline',  'showOffline')
  bindCheckbox('filter-hoplines', 'showHopLines')
  bindCheckbox('filter-markers',  'showCustomMarkers')
  bindCheckbox('filter-local',    'showLocalNode')
  bindRange('filter-maxhops',     'maxHops')
}

// --- Hop Lines ---

function snrColor(snr) {
  if (snr == null) return '#555'
  if (snr > 5)     return '#4caf50'
  if (snr >= 0)    return '#fb8c00'
  return '#e53935'
}

function renderHopLines() {
  if (!mapReady) return
  hopLinesLayer.clearLayers()
  var f = loadFilters()
  if (!f.showHopLines) return
  var nodes = []
  nodeCache.forEach(function(n) { if (n.latitude && n.longitude) nodes.push(n) })
  var now = Date.now() / 1000
  nodes.forEach(function(a) {
    if (now - (a.last_heard || 0) > 1800) return
    nodes.forEach(function(b) {
      if (a.id >= b.id) return
      if (now - (b.last_heard || 0) > 1800) return
      var line = L.polyline(
        [[a.latitude, a.longitude], [b.latitude, b.longitude]],
        { color: snrColor(a.snr != null ? a.snr : b.snr), weight: 2.5, opacity: 0.75 }
      )
      hopLinesLayer.addLayer(line)
    })
  })
}

// --- Traceroute path ---

function renderTraceroutePath(hops) {
  if (!mapReady) return
  tracerouteLayer.clearLayers()
  var latlngs = []
  hops.forEach(function(nodeId) {
    var n = nodeCache.get(nodeId)
    if (n && n.latitude && n.longitude) latlngs.push([n.latitude, n.longitude])
  })
  if (latlngs.length < 2) return
  L.polyline(latlngs, {
    color: '#ffd54f', weight: 4, opacity: 0.85, dashArray: '10,6'
  }).addTo(tracerouteLayer)
  for (var i = 0; i < latlngs.length - 1; i++) {
    var mid = [
      (latlngs[i][0] + latlngs[i + 1][0]) / 2,
      (latlngs[i][1] + latlngs[i + 1][1]) / 2,
    ]
    L.circleMarker(mid, {
      radius: 3, color: '#ffd54f', fillColor: '#ffd54f', fillOpacity: 1
    }).addTo(tracerouteLayer)
  }
  tracerouteLayer.addTo(leafletMap)
  var badge    = document.getElementById('traceroute-badge')
  var badgeTxt = document.getElementById('traceroute-badge-text')
  if (badge && badgeTxt) {
    var last = nodeCache.get(hops[hops.length - 1])
    var name = (last && last.short_name) ? last.short_name : hops[hops.length - 1]
    badgeTxt.textContent = 'Traceroute: ' + name + ' (' + (latlngs.length - 1) + ' hop)'
    badge.style.display = 'flex'
  }
}

// --- Marker personalizzati ---

function renderCustomMarkersOnMap() {
  customMarkersLayer.clearLayers()
  customMarkersData.forEach(function(m) {
    var icon = L.divIcon({
      html:       makeSvgIcon(m.icon_type, 18, '#ffd54f'),
      className:  '',
      iconSize:   [18, 18],
      iconAnchor: [9, 18],
    })
    var marker = L.marker([m.latitude, m.longitude], { icon: icon })
    marker.bindPopup('<b>' + escHtml(m.label) + '</b>')
    marker.addTo(customMarkersLayer)
    marker._markerId = m.id
  })
}

async function loadCustomMarkers() {
  var r = await fetch('/api/map/markers')
  if (!r.ok) return
  var data = await r.json()
  customMarkersData = data.markers || []
  renderCustomMarkersOnMap()
  renderMarkerSidebar()
}

async function addCustomMarker(label, iconType, latlng) {
  var r = await fetch('/api/map/markers', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ label: label, icon_type: iconType, latitude: latlng.lat, longitude: latlng.lng }),
  })
  if (r.ok) await loadCustomMarkers()
}

async function removeCustomMarker(id) {
  await fetch('/api/map/markers/' + id, { method: 'DELETE' })
  customMarkersData = customMarkersData.filter(function(m) { return m.id !== id })
  renderCustomMarkersOnMap()
  renderMarkerSidebar()
}

function renderMarkerSidebar() {
  var list = document.getElementById('marker-list')
  if (!list) return
  list.textContent = ''
  customMarkersData.forEach(function(m) {
    var item = document.createElement('div')
    item.style.cssText = 'background:var(--panel,#1e2535);border-radius:3px;padding:3px 5px;display:flex;align-items:center;gap:4px;font-size:11px;margin-bottom:3px;'
    item.innerHTML = makeSvgIcon(m.icon_type, 11, 'var(--accent,#5c9bd6)')
    var lbl = document.createElement('span')
    lbl.style.flex = '1'
    lbl.textContent = m.label
    var del = document.createElement('button')
    del.style.cssText = 'background:none;border:none;color:var(--danger,#c62828);cursor:pointer;padding:0;font-size:11px;line-height:1;'
    del.textContent = '\u2715'
    ;(function(markerId) {
      del.onclick = function() { removeCustomMarker(markerId) }
    })(m.id)
    item.append(lbl, del)
    list.appendChild(item)
  })
}

// --- Context menu long-press su nodo ---

var _longPressTimer = null

function initNodeContextMenu(marker, node) {
  function showMenu() {
    closeContextMenu()
    var menu = document.createElement('div')
    menu.id = 'node-ctx-menu'
    menu.style.cssText = 'position:fixed;z-index:1000;background:var(--panel,#1e2535);border:1px solid var(--border,#2a3a4a);border-radius:5px;padding:3px 0;font-size:12px;min-width:140px;box-shadow:0 4px 12px rgba(0,0,0,.5);'

    var title = document.createElement('div')
    title.style.cssText = 'padding:3px 10px;font-size:10px;color:var(--accent,#5c9bd6);border-bottom:1px solid var(--border,#2a3a4a);margin-bottom:2px;'
    title.textContent = (node.short_name || node.id) + ' \u00b7 ' + node.id
    menu.appendChild(title)

    function menuItem(iconType, label, onClick) {
      var row = document.createElement('div')
      row.style.cssText = 'padding:5px 10px;display:flex;align-items:center;gap:7px;cursor:pointer;color:var(--text,#ccc);'
      row.onmouseenter = function() { row.style.background = 'var(--border,#2a3a4a)' }
      row.onmouseleave = function() { row.style.background = '' }
      row.innerHTML = makeSvgIcon(iconType, 12)
      row.appendChild(document.createTextNode(label))
      row.onclick = function() { closeContextMenu(); onClick() }
      menu.appendChild(row)
    }

    menuItem('poi', 'Invia DM', function() {
      window.location.href = '/messages?open_dm=' + encodeURIComponent(node.id)
    })
    menuItem('poi', 'Richiedi posizione', function() {
      fetch('/send', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ text: '', destination: node.id, type: 'position_request' }),
      })
    })
    menuItem('route', 'Traceroute', function() {
      fetch('/api/traceroute', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ node_id: node.id }),
      })
    })

    var pt    = leafletMap.latLngToContainerPoint(marker.getLatLng())
    var mapEl = document.getElementById('map-container')
    var rect  = mapEl.getBoundingClientRect()
    menu.style.left = (rect.left + pt.x + 10) + 'px'
    menu.style.top  = (rect.top  + pt.y - 20) + 'px'
    document.body.appendChild(menu)
    setTimeout(function() {
      document.addEventListener('click', closeContextMenu, { once: true })
    }, 50)
  }

  marker.on('mousedown touchstart', function() {
    _longPressTimer = setTimeout(showMenu, 300)
  })
  marker.on('mouseup touchend mousemove touchmove', function() {
    clearTimeout(_longPressTimer)
  })
}

function closeContextMenu() {
  var m = document.getElementById('node-ctx-menu')
  if (m) m.remove()
}

// --- Inizializzazione mappa ---

function initMapIfNeeded() {
  if (mapReady || typeof L === 'undefined') return
  var el = document.getElementById('map-container')
  if (!el) return
  var bounds = JSON.parse(el.dataset.bounds || 'null')
  if (!bounds) return
  var zoomMin = parseInt(el.dataset.zoomMin || '7')
  var zoomMax = parseInt(el.dataset.zoomMax || '12')
  var center  = [
    (bounds.lat_min + bounds.lat_max) / 2,
    (bounds.lon_min + bounds.lon_max) / 2,
  ]

  leafletMap = L.map('map-container', {
    center: center, zoom: 10, zoomControl: false,
    minZoom: zoomMin, maxZoom: zoomMax,
    maxBounds: [[bounds.lat_min, bounds.lon_min], [bounds.lat_max, bounds.lon_max]],
    maxBoundsViscosity: 1.0,
    tap: true,
  })

  var tileOpts       = { minZoom: zoomMin, maxZoom: zoomMax }
  var osmLayer       = L.tileLayer('/tiles/osm/{z}/{x}/{y}',       tileOpts)
  var topoLayer      = L.tileLayer('/tiles/topo/{z}/{x}/{y}',      tileOpts)
  var satelliteLayer = L.tileLayer('/tiles/satellite/{z}/{x}/{y}', tileOpts)
  osmLayer.addTo(leafletMap)
  L.control.layers({ 'Stradale': osmLayer, 'Topo': topoLayer, 'Satellite': satelliteLayer }).addTo(leafletMap)
  L.control.zoom({ position: 'topleft' }).addTo(leafletMap)

  hopLinesLayer.addTo(leafletMap)
  customMarkersLayer.addTo(leafletMap)

  nodeCache.forEach(function(node) { updateMapMarker(node) })
  mapReady = true

  initFilters()
  applyFilters()
  renderHopLines()
  loadCustomMarkers()

  var trNode = new URLSearchParams(window.location.search).get('traceroute')
  if (trNode) {
    fetch('/api/traceroute/' + encodeURIComponent(trNode))
      .then(function(r) { return r.json() })
      .then(function(data) {
        if (data.results && data.results[0]) renderTraceroutePath(data.results[0].hops)
      })
  }
}

function updateMapMarker(node) {
  if (!node.latitude || !node.longitude || !mapReady) return
  var color    = node.is_local ? '#4a9eff' : '#4caf50'
  var existing = markerCache.get(node.id)
  if (existing) {
    existing.setLatLng([node.latitude, node.longitude])
  } else {
    var marker = L.circleMarker([node.latitude, node.longitude], {
      radius: 8, color: color, fillColor: color, fillOpacity: 0.8,
    })
    marker.bindPopup(
      '<b>' + escHtml(String(node.short_name || node.id)) + '</b><br>' +
      escHtml(String(node.long_name || '')) + '<br>' +
      'SNR: ' + escHtml(String(node.snr != null ? node.snr : '\u2014')) + ' dB<br>' +
      'Batt: ' + escHtml(String(node.battery_level != null ? node.battery_level : '\u2014')) + '%'
    )
    initNodeContextMenu(marker, node)
    marker.addTo(leafletMap)
    markerCache.set(node.id, marker)
  }
  renderHopLines()
  applyFilters()
}

// --- Listener eventi WebSocket (dispatchati da app.js) ---

window.addEventListener('node-update',       function(e) { updateMapMarker(e.detail) })
window.addEventListener('traceroute_result', function(e) { renderTraceroutePath(e.detail.hops) })
```

### Step 4.2 — Verifica sintassi JS

- [ ] Esegui:
  ```bash
  node --check /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements/static/map.js && echo "OK"
  ```
  Atteso: `OK`

### Step 4.3 — Commit

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  git add static/map.js
  git commit -m "feat(yay-114): create static/map.js with hop lines, traceroute, filters, markers"
  ```

---

## Task 5 — static/app.js: rimuovi sezione MAPPA + aggiungi handler traceroute_result

**Files:** `static/app.js`

Il file attuale ha la sezione mappa alle righe **322–374** (da `// ===== MAPPA =====`
fino alla parentesi graffa che chiude `updateMapMarker`). Queste funzioni ora vivono
in `map.js`. Bisogna rimuoverle da `app.js` e aggiungere il nuovo handler WebSocket.

### Step 5.1 — Rimuovi la sezione `// ===== MAPPA =====` da app.js

- [ ] In `static/app.js`, individua e cancella l'intero blocco che inizia con:
  ```
  // ===== MAPPA =====
  let leafletMap = null
  ```
  e termina con la parentesi graffa che chiude `updateMapMarker` (la riga `}`
  subito prima di `// ===== GRAFICI`).

  Il testo da cancellare comprende esattamente queste righe (322–374 nel file
  corrente):
  - la riga `// ===== MAPPA =====`
  - le tre dichiarazioni `let leafletMap`, `let mapReady`, `const markerCache`
  - la funzione completa `function initMapIfNeeded() { ... }`
  - la funzione completa `function updateMapMarker(node) { ... }`

  Dopo la cancellazione, la riga immediatamente successiva all'ultimo blocco
  cancellato deve essere:
  ```
  // ===== GRAFICI (stub, completato in Task telemetry) =====
  ```

### Step 5.2 — Aggiungi handler `traceroute_result` nel dispatcher WebSocket

- [ ] In `static/app.js`, individua il dizionario `handlers` nel blocco
  `ws.onmessage` (righe ~62–74). Aggiungi la voce `traceroute_result`:

  Prima:
  ```javascript
  const handlers = {
    init:      handleInit,
    message:   handleMessage,
    node:      handleNode,
    position:  handlePosition,
    telemetry: handleTelemetry,
    sensor:    handleSensor,
    encoder:   handleEncoder,
    status:    handleStatus,
    log:       handleLog,
    ack:       handleAck,
  }
  ```

  Dopo:
  ```javascript
  const handlers = {
    init:              handleInit,
    message:           handleMessage,
    node:              handleNode,
    position:          handlePosition,
    telemetry:         handleTelemetry,
    sensor:            handleSensor,
    encoder:           handleEncoder,
    status:            handleStatus,
    log:               handleLog,
    ack:               handleAck,
    traceroute_result: handleTracerouteResult,
  }
  ```

- [ ] Aggiungi la funzione handler subito dopo la funzione `handleAck` (in coda alla
  sezione `// ===== HANDLER MESSAGGI WS =====`):

  ```javascript
  function handleTracerouteResult(data) {
    window.dispatchEvent(new CustomEvent('traceroute_result', { detail: data }))
  }
  ```

### Step 5.3 — Verifica che handleNode e handlePosition siano intatti

- [ ] Controlla che `handleNode` contenga ancora la riga:
  ```javascript
  if (activeTab.name === 'map' && mapReady) updateMapMarker(data)
  ```
  e che `handlePosition` contenga:
  ```javascript
  if (activeTab.name === 'map' && mapReady) updateMapMarker(node)
  ```
  Queste chiamate sono corrette: `mapReady` e `updateMapMarker` vengono risolte
  da `map.js` quando la pagina `/map` e' aperta. Non occorre modificarle.

- [ ] Verifica sintassi:
  ```bash
  node --check /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements/static/app.js && echo "OK"
  ```
  Atteso: `OK`

### Step 5.4 — Commit

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  git add static/app.js
  git commit -m "feat(yay-114): app.js — remove map section, add traceroute_result handler"
  ```

---

## Task 6 — templates/map.html: riscrittura completa

**Files:** `templates/map.html`

### Step 6.1 — Riscrivi `templates/map.html`

- [ ] Sostituisci l'intero contenuto del file con:

```html
{% extends "base.html" %}
{% block content %}
<div id="map-wrapper" style="display:flex;height:100%;position:relative;overflow:hidden;">

  <!-- Sidebar sinistra: marker personalizzati -->
  <div id="marker-sidebar"
       style="width:110px;border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;overflow:hidden;background:var(--bg);">
    <div style="padding:6px 8px 3px;font-size:9px;color:var(--accent);text-transform:uppercase;letter-spacing:.06em;">
      Marker
    </div>
    <div id="marker-list" style="flex:1;overflow-y:auto;padding:0 6px;"></div>
    <div style="padding:5px 6px;border-top:1px solid var(--border);">
      <button id="add-marker-btn"
              style="width:100%;font-size:10px;padding:4px 0;display:flex;align-items:center;justify-content:center;gap:4px;">
        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4"/>
        </svg>
        Aggiungi
      </button>
    </div>
  </div>

  <!-- Area mappa principale -->
  <div style="flex:1;display:flex;flex-direction:column;position:relative;overflow:hidden;">

    <!-- Pannello filtri (assoluto in alto a destra) -->
    <div id="filter-panel"
         style="position:absolute;top:8px;right:8px;z-index:500;background:rgba(15,15,25,0.93);border:1px solid var(--border);border-radius:5px;padding:7px 10px;min-width:140px;font-size:11px;">
      <div style="color:var(--accent);font-size:9px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px;">Filtri</div>
      <label style="display:flex;align-items:center;gap:5px;margin-bottom:3px;cursor:pointer;">
        <input type="checkbox" id="filter-online"> Online
      </label>
      <label style="display:flex;align-items:center;gap:5px;margin-bottom:3px;cursor:pointer;">
        <input type="checkbox" id="filter-offline"> Offline
      </label>
      <label style="display:flex;align-items:center;gap:5px;margin-bottom:3px;cursor:pointer;">
        <input type="checkbox" id="filter-hoplines"> Linee hop
      </label>
      <label style="display:flex;align-items:center;gap:5px;margin-bottom:3px;cursor:pointer;">
        <input type="checkbox" id="filter-markers"> Marker
      </label>
      <label style="display:flex;align-items:center;gap:5px;margin-bottom:5px;cursor:pointer;">
        <input type="checkbox" id="filter-local"> Nodo locale
      </label>
      <div style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--muted);">
        <span>hop &le;</span>
        <input type="range" id="filter-maxhops" min="1" max="7" style="flex:1;">
        <span id="filter-maxhops-val" style="color:var(--accent);min-width:10px;">7</span>
      </div>
    </div>

    <!-- Badge traceroute result -->
    <div id="traceroute-badge"
         style="display:none;position:absolute;top:8px;left:120px;z-index:500;background:rgba(15,15,25,0.93);border:1px solid var(--accent);border-radius:4px;padding:4px 10px;font-size:10px;color:var(--accent);align-items:center;gap:5px;">
      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
      </svg>
      <span id="traceroute-badge-text"></span>
    </div>

    <!-- Contenitore Leaflet -->
    <div id="map-container"
         data-bounds='{{ bounds | tojson }}'
         data-zoom-min="{{ zoom_min }}"
         data-zoom-max="{{ zoom_max }}"
         style="flex:1;"></div>

    <!-- Barra legenda fissa in fondo -->
    <div id="map-legend"
         style="height:34px;border-top:1px solid var(--border);background:rgba(12,12,22,0.95);display:flex;align-items:center;gap:12px;padding:0 10px;font-size:10px;flex-shrink:0;overflow-x:auto;white-space:nowrap;">
      <div style="display:flex;align-items:center;gap:5px;">
        <div style="width:9px;height:9px;border-radius:50%;background:#4a9eff;box-shadow:0 0 4px #4a9eff;flex-shrink:0;"></div>Locale
      </div>
      <div style="display:flex;align-items:center;gap:5px;">
        <div style="width:9px;height:9px;border-radius:50%;background:#4caf50;flex-shrink:0;"></div>Online
      </div>
      <div style="display:flex;align-items:center;gap:5px;">
        <div style="width:9px;height:9px;border-radius:50%;background:#555;flex-shrink:0;"></div>Offline
      </div>
      <div style="width:1px;height:16px;background:var(--border);flex-shrink:0;"></div>
      <div style="display:flex;align-items:center;gap:5px;">
        <div style="width:22px;height:3px;background:#4caf50;border-radius:1px;flex-shrink:0;"></div>SNR buono
      </div>
      <div style="display:flex;align-items:center;gap:5px;">
        <div style="width:22px;height:3px;background:#fb8c00;border-radius:1px;flex-shrink:0;"></div>medio
      </div>
      <div style="display:flex;align-items:center;gap:5px;">
        <div style="width:22px;height:3px;background:#e53935;border-radius:1px;flex-shrink:0;"></div>scarso
      </div>
      <div style="width:1px;height:16px;background:var(--border);flex-shrink:0;"></div>
      <div style="display:flex;align-items:center;gap:5px;">
        <div style="width:22px;height:3px;background:#ffd54f;opacity:0.8;border-radius:1px;flex-shrink:0;"></div>traceroute
      </div>
    </div>

  </div>
</div>

<!-- Modal aggiunta marker -->
<div id="marker-modal"
     style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:2000;align-items:center;justify-content:center;">
  <div style="background:var(--panel,#1e2535);border:1px solid var(--border);border-radius:8px;padding:16px;min-width:220px;font-size:12px;">
    <div style="font-weight:bold;margin-bottom:10px;color:var(--accent);">Nuovo marker</div>
    <input id="marker-label" type="text" placeholder="Nome..."
           style="width:100%;margin-bottom:8px;box-sizing:border-box;">
    <select id="marker-type" style="width:100%;margin-bottom:10px;box-sizing:border-box;">
      <option value="poi">Punto di interesse</option>
      <option value="antenna">Antenna</option>
      <option value="base">Base operativa</option>
      <option value="obstacle">Ostacolo</option>
    </select>
    <div id="marker-coords-hint"
         style="font-size:10px;color:var(--muted);margin-bottom:10px;">
      Clicca sulla mappa per posizionare
    </div>
    <div style="display:flex;gap:6px;justify-content:flex-end;">
      <button id="marker-cancel">Annulla</button>
      <button id="marker-save"
              style="background:var(--accent);color:#fff;border:none;border-radius:3px;padding:4px 10px;cursor:pointer;">
        Salva
      </button>
    </div>
  </div>
</div>

<script src="/static/map.js"></script>
<script>
var _pendingMarkerLatLng = null

document.getElementById('add-marker-btn').onclick = function() {
  _pendingMarkerLatLng = null
  document.getElementById('marker-coords-hint').textContent = 'Clicca sulla mappa per posizionare'
  document.getElementById('marker-coords-hint').style.color = ''
  document.getElementById('marker-label').value = ''
  document.getElementById('marker-modal').style.display = 'flex'
  if (typeof leafletMap !== 'undefined' && leafletMap) {
    leafletMap.once('click', function(e) {
      _pendingMarkerLatLng = e.latlng
      document.getElementById('marker-coords-hint').textContent =
        e.latlng.lat.toFixed(4) + '\u00b0, ' + e.latlng.lng.toFixed(4) + '\u00b0'
    })
  }
}

document.getElementById('marker-cancel').onclick = function() {
  document.getElementById('marker-modal').style.display = 'none'
}

document.getElementById('marker-save').onclick = async function() {
  var label = document.getElementById('marker-label').value.trim()
  var type  = document.getElementById('marker-type').value
  if (!label) {
    document.getElementById('marker-label').focus()
    return
  }
  if (!_pendingMarkerLatLng) {
    var hint = document.getElementById('marker-coords-hint')
    hint.textContent = 'Clicca prima sulla mappa!'
    hint.style.color = 'var(--danger,#ef9a9a)'
    return
  }
  await addCustomMarker(label, type, _pendingMarkerLatLng)
  document.getElementById('marker-modal').style.display = 'none'
}
</script>
{% endblock %}
```

### Step 6.2 — Verifica Jinja2

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -c "
  from jinja2 import Environment, FileSystemLoader
  env = Environment(loader=FileSystemLoader('templates'))
  env.get_template('map.html')
  print('map.html OK')
  "
  ```
  Atteso: `map.html OK`

### Step 6.3 — Commit

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  git add templates/map.html
  git commit -m "feat(yay-114): rewrite map.html — sidebar, filter panel, legend bar, traceroute badge"
  ```

---

## Task 7 — templates/nodes.html: aggiungi bottone Traceroute

**Files:** `templates/nodes.html`

Bisogna aggiungere il bottone Traceroute in due posti:
1. Nella sezione Jinja server-rendered (blocco `{% for n in nodes %}`)
2. Nella funzione JS `renderNodeRow(n)` che costruisce la riga dinamicamente

### Step 7.1 — Aggiungi nel template Jinja (server-rendered)

- [ ] In `templates/nodes.html`, nella sezione `{% for n in nodes %}`, individua il
  `</button>` che chiude "Richiedi posizione" (riga ~42 nel file corrente). Aggiungi
  immediatamente dopo di esso, e prima del `<div>` con `border-top` che contiene
  il bottone Elimina:

```html
      <button
        onclick="(function(btn){fetch('/api/traceroute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({node_id:'{{ n.id }}'})}).then(function(r){return r.json()}).then(function(d){if(d.ok){var a=btn.nextElementSibling;if(a)a.style.display='flex'}})})(this)"
        style="display:flex;align-items:center;gap:6px;background:none;border:none;padding:4px 0;cursor:pointer;color:var(--text,#ccc);font-size:12px;text-align:left;">
        <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
        </svg>
        Traceroute
      </button>
      <a href="/map?traceroute={{ n.id | urlencode }}"
         style="display:none;align-items:center;gap:4px;font-size:10px;color:var(--accent);text-decoration:none;margin-top:2px;">
        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
        </svg>
        Vedi sulla mappa
      </a>
```

### Step 7.2 — Aggiungi nella funzione JS `renderNodeRow`

- [ ] In `templates/nodes.html`, nella funzione `renderNodeRow(n)`, individua la riga:
  ```javascript
    actions.appendChild(posBtn)
  ```
  Aggiungi subito dopo (e prima della riga `// Delete button + cascade`):

```javascript
    // Traceroute button
    var trSvgNs = 'http://www.w3.org/2000/svg'
    var trBtn = document.createElement('button')
    trBtn.style.cssText = 'display:flex;align-items:center;gap:6px;background:none;border:none;padding:4px 0;cursor:pointer;color:var(--text,#ccc);font-size:12px;text-align:left;'
    var trSvg = document.createElementNS(trSvgNs, 'svg')
    trSvg.setAttribute('width', '13'); trSvg.setAttribute('height', '13')
    trSvg.setAttribute('fill', 'none'); trSvg.setAttribute('stroke', 'currentColor')
    trSvg.setAttribute('stroke-width', '2'); trSvg.setAttribute('viewBox', '0 0 24 24')
    var trPath = document.createElementNS(trSvgNs, 'path')
    trPath.setAttribute('stroke-linecap', 'round'); trPath.setAttribute('stroke-linejoin', 'round')
    trPath.setAttribute('d', 'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7')
    trSvg.appendChild(trPath)
    trBtn.appendChild(trSvg)
    trBtn.appendChild(document.createTextNode('Traceroute'))

    var trLink = document.createElement('a')
    trLink.href = '/map?traceroute=' + encodeURIComponent(n.id)
    trLink.style.cssText = 'display:none;align-items:center;gap:4px;font-size:10px;color:var(--accent);text-decoration:none;margin-top:2px;'
    var trLinkSvg = document.createElementNS(trSvgNs, 'svg')
    trLinkSvg.setAttribute('width', '10'); trLinkSvg.setAttribute('height', '10')
    trLinkSvg.setAttribute('fill', 'none'); trLinkSvg.setAttribute('stroke', 'currentColor')
    trLinkSvg.setAttribute('stroke-width', '2'); trLinkSvg.setAttribute('viewBox', '0 0 24 24')
    var trLinkPath = document.createElementNS(trSvgNs, 'path')
    trLinkPath.setAttribute('stroke-linecap', 'round'); trLinkPath.setAttribute('stroke-linejoin', 'round')
    trLinkPath.setAttribute('d', 'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7')
    trLinkSvg.appendChild(trLinkPath)
    trLink.appendChild(trLinkSvg)
    trLink.appendChild(document.createTextNode(' Vedi sulla mappa'))

    trBtn.onclick = function() {
      fetch('/api/traceroute', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ node_id: n.id }),
      })
        .then(function(r) { return r.json() })
        .then(function(data) {
          if (data.ok) {
            trLink.style.display = 'flex'
            setTimeout(function() { trLink.style.display = 'none' }, 15000)
          }
        })
    }

    actions.appendChild(trBtn)
    actions.appendChild(trLink)
```

### Step 7.3 — Verifica Jinja2

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -c "
  from jinja2 import Environment, FileSystemLoader
  env = Environment(loader=FileSystemLoader('templates'))
  env.get_template('nodes.html')
  print('nodes.html OK')
  "
  ```
  Atteso: `nodes.html OK`

### Step 7.4 — Commit

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  git add templates/nodes.html
  git commit -m "feat(yay-114): nodes.html — add Traceroute button + map link"
  ```

---

## Task 8 — Deploy, verifica e chiusura YAY-114

### Step 8.1 — Suite di test completa

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -m pytest tests/test_database.py -v
  ```
  Atteso: **13 passed, 0 failed**

  ```
  tests/test_database.py::test_init_creates_tables                         PASSED
  tests/test_database.py::test_save_and_get_message                        PASSED
  tests/test_database.py::test_save_and_get_node                           PASSED
  tests/test_database.py::test_sync_to_sd                                  PASSED
  tests/test_database.py::test_get_messages_pagination                     PASSED
  tests/test_database.py::test_prune_sensor_readings                       PASSED
  tests/test_database.py::test_save_message_stores_destination             PASSED
  tests/test_database.py::test_get_dm_threads_returns_threads_with_unread  PASSED
  tests/test_database.py::test_get_dm_messages_returns_thread              PASSED
  tests/test_database.py::test_mark_dm_read_clears_unread                  PASSED
  tests/test_database.py::test_save_and_get_marker                         PASSED
  tests/test_database.py::test_delete_marker                               PASSED
  tests/test_database.py::test_save_and_get_traceroute                     PASSED
  ```

### Step 8.2 — Verifica sintassi tutti i file

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/yay-114-map-enhancements
  python3 -m py_compile database.py meshtastic_client.py main.py && echo "Python OK"
  node --check static/app.js && echo "app.js OK"
  node --check static/map.js && echo "map.js OK"
  python3 -c "
  from jinja2 import Environment, FileSystemLoader
  env = Environment(loader=FileSystemLoader('templates'))
  for t in ['map.html', 'nodes.html']:
      env.get_template(t)
      print(t + ' OK')
  "
  ```
  Atteso:
  ```
  Python OK
  app.js OK
  map.js OK
  map.html OK
  nodes.html OK
  ```

### Step 8.3 — Merge su master

- [ ] Esegui:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh
  git merge feature/yay-114-map-enhancements --no-ff \
    -m "feat: YAY-114 map enhancements — legenda, hop lines, traceroute, marker, filtri"
  ```

### Step 8.4 — Deploy al Raspberry Pi

- [ ] Sincronizza i file:
  ```bash
  sshpass -p 'pimesh' rsync -av \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.superpowers' \
    --exclude='.worktrees' \
    --exclude='.omc' \
    --exclude='.sisyphus' \
    /Users/yayoboy/Desktop/GitHub/pi-Mesh/ \
    pimesh@192.168.1.36:/home/pimesh/pi-Mesh/
  ```

- [ ] Riavvia il servizio:
  ```bash
  sshpass -p 'pimesh' ssh pimesh@192.168.1.36 \
    "sudo systemctl restart meshtastic-pi@pimesh"
  ```

- [ ] Verifica che il servizio sia attivo (attendi 3-5 secondi dopo il restart):
  ```bash
  sshpass -p 'pimesh' ssh pimesh@192.168.1.36 \
    "sudo systemctl is-active meshtastic-pi@pimesh"
  ```
  Atteso: `active`

### Step 8.5 — Verifica endpoint sul Pi

- [ ] GET markers (lista vuota iniziale):
  ```bash
  curl -s http://192.168.1.36:8080/api/map/markers | python3 -m json.tool
  ```
  Atteso: `{"markers": []}`

- [ ] POST nuovo marker:
  ```bash
  curl -s -X POST http://192.168.1.36:8080/api/map/markers \
    -H 'Content-Type: application/json' \
    -d '{"label":"Test","icon_type":"poi","latitude":45.0,"longitude":9.0}' \
    | python3 -m json.tool
  ```
  Atteso: `{"ok": true, "id": 1}`

- [ ] GET markers (deve mostrare il marker appena creato):
  ```bash
  curl -s http://192.168.1.36:8080/api/map/markers | python3 -m json.tool
  ```
  Atteso: `{"markers": [{"id": 1, "label": "Test", "icon_type": "poi", ...}]}`

- [ ] DELETE marker:
  ```bash
  curl -s -X DELETE http://192.168.1.36:8080/api/map/markers/1 | python3 -m json.tool
  ```
  Atteso: `{"ok": true}`

- [ ] POST traceroute (risponde in base allo stato connessione):
  ```bash
  curl -s -X POST http://192.168.1.36:8080/api/traceroute \
    -H 'Content-Type: application/json' \
    -d '{"node_id":"!nonexistent"}' \
    | python3 -m json.tool
  ```
  Atteso: `{"ok": true}` se Meshtastic connesso, oppure
  `{"ok": false, "error": "Meshtastic non connesso"}` se dispositivo seriale assente.
  Entrambi sono risposte valide.

### Step 8.6 — Verifica visiva pagina mappa

- [ ] Apri `http://192.168.1.36:8080/map` nel browser. Verifica:
  - [ ] Barra legenda in fondo con pallini colorati (Locale blu, Online verde, Offline grigio)
        e swatches per linee SNR e traceroute
  - [ ] Pannello filtri in alto a destra con 5 checkbox e 1 slider
  - [ ] I checkbox riflettono i default (Online spuntato, Offline non spuntato, ecc.)
  - [ ] Sidebar marker a sinistra con titolo "MARKER" e bottone "Aggiungi"
  - [ ] Nodi con posizione GPS mostrano marker circolari sulla mappa
  - [ ] Layer switcher (Stradale / Topo / Satellite) presente in alto a sinistra
  - [ ] Long press 300ms su un marker nodo apre context menu con: Invia DM,
        Richiedi posizione, Traceroute
  - [ ] Click fuori dal context menu lo chiude
  - [ ] Click su "Aggiungi" apre la modal, click sulla mappa registra le coordinate,
        click su "Salva" crea il marker che appare su mappa e in sidebar
  - [ ] Click su "x" nella sidebar rimuove il marker

### Step 8.7 — Verifica visiva pagina nodi

- [ ] Apri `http://192.168.1.36:8080/nodes` nel browser:
  - [ ] Espandi un nodo (click sulla riga) — le azioni mostrano: Invia DM,
        Richiedi posizione, **Traceroute**, Elimina nodo
  - [ ] Click su "Traceroute" — dopo la risposta API appare il link
        "Vedi sulla mappa" con icona

### Step 8.8 — Push e chiusura issue

- [ ] Push:
  ```bash
  cd /Users/yayoboy/Desktop/GitHub/pi-Mesh
  git push origin master
  ```

- [ ] Chiudi YAY-114 in Linear via MCP (stato: Done).

---

## Riepilogo commit attesi (in ordine)

```
feat(yay-114): DB map_markers + traceroute_results tables + 5 functions
feat(yay-114): traceroute request + receive handler in meshtastic_client
feat(yay-114): 5 new endpoints — map markers + traceroute
feat(yay-114): create static/map.js with hop lines, traceroute, filters, markers
feat(yay-114): app.js — remove map section, add traceroute_result handler
feat(yay-114): rewrite map.html — sidebar, filter panel, legend bar, traceroute badge
feat(yay-114): nodes.html — add Traceroute button + map link
feat: YAY-114 map enhancements — legenda, hop lines, traceroute, marker, filtri  [merge]
```

---

## Checklist finale pre-merge

- [ ] `python3 -m pytest tests/test_database.py -v` — 13 passed, 0 failed
- [ ] `python3 -m py_compile database.py meshtastic_client.py main.py` — no errori
- [ ] `node --check static/app.js static/map.js` — no errori
- [ ] Template `map.html` e `nodes.html` parsati da Jinja2 senza errori
- [ ] Endpoint `/api/map/markers` risponde `{"markers": []}`
- [ ] Endpoint `/api/traceroute` risponde (ok o errore connessione — entrambi validi)
- [ ] Legenda visibile su `/map`
- [ ] Filtri funzionanti con persistenza localStorage
- [ ] Marker personalizzato creabile e cancellabile dalla sidebar
- [ ] Context menu long-press (300ms) appare su nodo con posizione GPS
- [ ] Bottone Traceroute presente e funzionante in `/nodes`
