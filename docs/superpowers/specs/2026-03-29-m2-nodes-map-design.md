# M2 — Nodes + Map: Design Spec

**Issue:** YAY-147
**Branch:** rework/v2-rewrite
**Date:** 2026-03-29
**Status:** Approved

---

## Obiettivo

Lista nodi completa con azioni sui nodi, mappa Leaflet con marker, popup info nodo, WebSocket per aggiornamenti live. Architettura API flessibile e page-agnostic per tutte le azioni meshtastic, riutilizzabile da M3/M4/M5.

---

## Architettura Backend

### meshtasticd_client.py — modifiche

**Typed event dispatcher (asyncio.Queue):**
- `_event_queue: asyncio.Queue` — module-level, importata da ws_router via `from meshtasticd_client import _event_queue`
- `_loop: asyncio.AbstractEventLoop` — salvato in `connect()` con `asyncio.get_event_loop()`
- `_on_receive()` classifica i pacchetti per portnum e inserisce eventi tipizzati via `_loop.call_soon_threadsafe(_event_queue.put_nowait, event)`
- Tipi evento: `node`, `position`, `telemetry`, `traceroute_result`, `log`

**Command worker (asyncio.Queue):**
- `_command_queue: asyncio.Queue` — comandi da asyncio verso la board
- `_command_worker()` task asyncio consuma in sequenza, esegue via `loop.run_in_executor(None, sync_fn)` — serializza tutti i comandi, zero race conditions

**Commands layer (nuove funzioni pubbliche):**
```python
async def send_text(text: str, destination_id: str, channel: int = 0) -> None
    # interface.sendText(text, destinationId=dest, channelIndex=channel)

async def request_traceroute(node_id: str) -> None
    # interface.sendTraceRoute(dest=node_id, hopLimit=3)

async def request_position(node_id: str) -> None
    # interface.sendPosition(destinationId=node_id) oppure
    # interface.localNode.requestPosition(node_id) — verificare
    # con meshtastic Python lib installata sul Pi
```

**Distanza:**
- `_haversine(lat1, lon1, lat2, lon2) -> float` — inline, no dipendenze esterne
- `_refresh_node_cache()` aggiunge `distance_km: float | None` a ogni nodo calcolando da nodo locale
- Se nodo locale o target non hanno GPS → `None`

**Node persistence — write-batching SQLite WAL:**
- `_dirty_nodes: set[str]` — nodi modificati dall'ultimo flush
- `_refresh_node_cache()` marca nodi modified come dirty
- `_flush_task()` — task asyncio avviato in `connect()` via `asyncio.create_task(_flush_task())`, scrive batch dirty ogni 60s → SQLite (WAL mode già attivo da M1)
- Al boot: `database.load_nodes()` chiamato in `lifespan()` in `main.py` popola `_node_cache` prima che la board risponda
- Scrive su SD card solo ogni 60s — preserva durata SD

**Traceroute cache:**
- `_traceroute_cache: dict[str, dict]` — risultati per node_id
- Popolato da `_on_receive()` quando arriva `TRACEROUTE_APP`
- Accessibile via `GET /api/nodes/{node_id}/traceroute`

---

## Architettura Backend — Nuovi Router

### routers/commands.py — page-agnostic

Tutti i comandi meshtastic in un router dedicato. Riutilizzato da ogni pagina e milestone futuro.

```
POST /api/nodes/{node_id}/traceroute      → request_traceroute(node_id)
POST /api/nodes/{node_id}/request-position → request_position(node_id)
POST /api/messages/send                   → send_text(text, to, channel)
GET  /api/nodes/{node_id}/traceroute      → _traceroute_cache[node_id]
GET  /api/nodes/{node_id}                 → singolo nodo da _node_cache
```

Risposta su board disconnessa: `503 Service Unavailable` con body `{"detail": "board not connected"}`.

### routers/ws_router.py — WebSocket broadcaster

```python
class ConnectionManager:
    _connections: set[WebSocket]
    async def connect(ws: WebSocket)
    def disconnect(ws: WebSocket)
    async def broadcast(msg: dict)  # json.dumps, skip failed
```

**Endpoint:** `GET /ws` (upgrade WebSocket)

**Ciclo di vita connessione:**
1. `connect()` → invia `{"type": "init", "nodes": get_nodes()}` al nuovo client
2. Si registra come consumer dell'`_event_queue`
3. Su disconnect: `disconnect()` + rimozione dal set

**Messaggi WS → client:**
| type | payload |
|------|---------|
| `init` | `{"nodes": [...]}` |
| `node` | dict nodo completo |
| `position` | `{"id", "latitude", "longitude", "last_heard"}` |
| `telemetry` | `{"id", "battery_level", "snr"}` |
| `traceroute_result` | `{"node_id", "hops": [...]}` |
| `log` | `{"ts", "from", "type", "snr", "hop_limit"}` |

**Broadcast a tutti i client connessi** — ogni tab aperto (nodes, map, messages, metrics, log) riceve gli stessi eventi.

### routers/map_router.py — aggiunte

```
GET    /api/map/markers        → lista custom markers da SQLite
POST   /api/map/markers        → crea marker {label, icon_type, latitude, longitude}
DELETE /api/map/markers/{id}   → elimina marker
```

### database.py — nuova tabella

```sql
CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,
    short_name  TEXT,
    long_name   TEXT,
    hw_model    TEXT,
    latitude    REAL,
    longitude   REAL,
    last_heard  INTEGER,
    snr         REAL,
    hop_count   INTEGER,
    battery_level INTEGER,
    is_local    INTEGER DEFAULT 0,
    distance_km REAL,
    updated_at  INTEGER
);

CREATE TABLE IF NOT EXISTS custom_markers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,
    icon_type   TEXT NOT NULL DEFAULT 'poi',
    latitude    REAL NOT NULL,
    longitude   REAL NOT NULL
);
```

### main.py

```python
app.include_router(commands.router)
app.include_router(ws_router.router)
```

---

## Architettura Frontend

### static/app.js — nodeActions object condiviso

Oggetto JS globale utilizzato da tutte le pagine. Zero duplicazioni.

```javascript
const nodeActions = {
  traceroute:      (nodeId) => fetch(`/api/nodes/${nodeId}/traceroute`, { method: 'POST' }),
  requestPosition: (nodeId) => fetch(`/api/nodes/${nodeId}/request-position`, { method: 'POST' }),
  sendDM:          (nodeId, text) => fetch('/api/messages/send', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({ to: nodeId, text, channel: 0 })
                   }),
  focusOnMap:      (nodeId) => { window.location.href = `/map?focus=${encodeURIComponent(nodeId)}` },
}
```

WS handler aggiornato per gestire tutti i tipi: `node`, `position`, `telemetry`, `traceroute_result`, `log`.

### templates/nodes.html

**Portrait — expand row:**
- Click riga → espande in-place
- Mostra: stat boxes (hops, SNR, battery, distanza, node ID, stato)
- Mini toolbar: [Traceroute] [Richiedi Pos.] [Invia DM] [Vedi su Mappa] — SVG Heroicons
- `last_heard` mostrato come "Xm fa" / "Xh fa" usando `formatAgo()`

**Landscape — 2 colonne (`@media (orientation: landscape)`):**
- Colonna sx (200px): lista nodi, riga selezionata evidenziata con border-left accent
- Colonna dx: detail panel con header nodo, stat grid 4 box (hops/SNR/batt/dist), grid azioni 2×2
- Stesse azioni, stesso Alpine.js state, layout diverso

### static/map.js — modifiche

**Tile URLs:** `'/static/tiles/osm/{z}/{x}/{y}'` (e topo, satellite) — fix da `/tiles/` a `/static/tiles/`

**Popup nodo — aggiunte:**
- 4° stat box: `distance_km` formattato come "2.4km" (o "—" se null)
- Action buttons sotto le stat boxes: [Traceroute] [Richiedi Pos.] [DM] — chiamano `nodeActions`
- Refactor context menu esistente per usare `nodeActions` invece di fetch dirette

**Traceroute timeout frontend:** attende `traceroute_result` via WS per 30s, poi mostra "timeout". Risultato disponibile anche via `GET /api/nodes/{id}/traceroute` se cambia tab.

---

## Responsive Orientation

Tutte le pagine si adattano con `@media (orientation: landscape)`:

| Pagina | Portrait | Landscape |
|--------|----------|-----------|
| `/nodes` | expand row in-place | lista sx + detail panel dx |
| `/map` | mappa full-screen, popup overlay | mappa + right-panel già esistente |

Alpine.js state unico — `selectedNodeId` — pilota entrambe le viste.

---

## File modificati / creati

| File | Tipo | Modifiche |
|------|------|-----------|
| `meshtasticd_client.py` | modifica | + typed event queue, + command queue/worker, + commands layer, + haversine/distance_km, + dirty flush SQLite |
| `database.py` | modifica | + tabelle `nodes`, `custom_markers` |
| `main.py` | modifica | + include commands_router, ws_router |
| `routers/map_router.py` | modifica | + `/api/map/markers` CRUD |
| `static/app.js` | modifica | + nodeActions, + WS handlers tipizzati |
| `static/map.js` | modifica | fix tile URLs, + distanza popup, + action buttons popup, refactor context menu |
| `templates/nodes.html` | modifica | + last_heard, + expand row, + landscape layout |
| `routers/commands.py` | nuovo | tutti i comandi meshtastic |
| `routers/ws_router.py` | nuovo | ConnectionManager + `/ws` |

---

## Decisioni architetturali chiave

- **Dual asyncio.Queue** — eventi (board→UI) e comandi (UI→board) su code separate, command worker serializza tutto
- **Write-batching 60s** — preserva SD card, nodi disponibili subito al boot da SQLite
- **nodeActions globale** — zero duplicazioni tra map, nodes, messages, futuro
- **Tile locali** — `/static/tiles/` senza route intermedia, Pi offline
- **Distance haversine in backend** — campo `distance_km` nel payload, disponibile ovunque
- **Commands page-agnostic** — `routers/commands.py` riusabile da M3/M4/M5 senza modifiche
