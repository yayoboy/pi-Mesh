# Rework v2 — Milestone 1: Foundation

## Obiettivo

Costruire la struttura base del rewrite: meshtasticd come layer di connessione board, FastAPI multi-page, SQLite WAL con cache, layout base PinesUI + Alpine.js + Heroicons. Al termine di questa milestone l'app è funzionante con dati reali dalla board ma senza feature specifiche (quelle arrivano nelle milestone successive).

---

## Stack

| Layer | Tecnologia | Note |
|---|---|---|
| Board | `meshtasticd` via USB serial `/dev/ttyACM0`, espone TCP `:4403` | Installato come servizio systemd separato |
| Backend | FastAPI + uvicorn 1 worker | Async, ASGI |
| DB | SQLite WAL mode | File `data/mesh.db` |
| Cache | `dict` Python in memoria (module-level) | Evita query ripetute |
| Frontend | PinesUI + Alpine.js (CDN) + Tailwind CSS (CDN) | No build step |
| Icone | Heroicons SVG inline | No emoji, no icon font |
| Aggiornamenti | Polling JS (nodi 10s, telemetria 5s) + SSE (log board) | No WebSocket |
| Logging | `WARNING` level, logger per modulo | Niente DEBUG continuo |

---

## Struttura progetto

```
pi-Mesh/
├── main.py                  # FastAPI app, route mounting, lifespan
├── config.py                # Env vars (MESHTASTICD_HOST, PORT, DB_PATH, ecc.)
├── meshtasticd_client.py    # Client TCP meshtasticd — connessione, polling, cache
├── database.py              # SQLite WAL, schema, query helpers
├── routers/
│   ├── nodes.py             # /nodes page + /api/nodes
│   ├── map.py               # /map page + /api/map/*
│   ├── messages.py          # /messages page + /api/messages/*
│   ├── config_fw.py         # /config page + /api/config/*
│   ├── metrics.py           # /metrics page + /api/metrics/*
│   └── log.py               # /log page + GET /api/log/stream (SSE)
├── templates/
│   ├── base.html            # Layout comune: tabbar, head, heroicons helpers
│   ├── nodes.html
│   ├── map.html
│   ├── messages.html
│   ├── config.html
│   ├── metrics.html
│   └── log.html
└── static/
    ├── map.js               # Leaflet logic (ottimizzata dal branch master)
    └── tiles/               # Tile cache OSM/topo/satellite (invariata)
```

---

## meshtasticd_client.py

**Responsabilità:** unico punto di contatto con meshtasticd. Espone funzioni async per leggere nodi, inviare messaggi, richiedere config, ecc.

**Connessione:** `meshtastic.tcp_interface.TCPInterface(hostname='localhost', portNumber=4403)` — modalità TCP ufficialmente supportata dalla libreria meshtastic-python. meshtasticd deve essere installato via `apt install meshtasticd` (disponibile da Meshtastic 2.5+).

**Cache in memoria:**
```python
_node_cache: dict[str, dict] = {}      # nodeId → node data
_last_node_fetch: float = 0.0          # timestamp ultimo fetch
NODE_CACHE_TTL = 8.0                   # secondi
```

Ogni richiesta `/api/nodes` controlla il TTL: se scaduto, interroga meshtasticd e aggiorna la cache. Altrimenti ritorna la cache diretta.

**Reconnect:** tentativo ogni 15s con backoff esponenziale fino a 120s. Stato connessione esposto via `is_connected() -> bool`.

**API esposta:**
- `get_nodes() -> list[dict]` — tutti i nodi dalla cache
- `get_local_node() -> dict | None` — nodo locale
- `send_message(text, channel, destination) -> bool`
- `send_traceroute(node_id) -> bool`
- `get_config() -> dict` — configurazione firmware locale
- `set_config(section, payload) -> bool`
- `subscribe_packets(callback)` — callback per SSE log

---

## database.py

**WAL mode:** attivato alla prima connessione con `PRAGMA journal_mode=WAL`.

**Schema minimo (Foundation):**
```sql
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    short_name TEXT, long_name TEXT,
    latitude REAL, longitude REAL,
    last_heard INTEGER,
    snr REAL, battery_level INTEGER,
    hop_count INTEGER, hw_model TEXT,
    is_local INTEGER DEFAULT 0,
    raw_json TEXT  -- payload completo per future feature
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel INTEGER DEFAULT 0,
    from_id TEXT, to_id TEXT,
    text TEXT, ts INTEGER,
    ack INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, from_id TEXT,
    packet_type TEXT, raw_json TEXT
);
```

**Connection:** singola connessione SQLite con `check_same_thread=False`, `timeout=10`.

---

## Frontend — base.html

Layout comune a tutte le pagine:

- **Head:** Tailwind CSS CDN, Alpine.js CDN, meta viewport `width=320`
- **Tabbar fissa in basso** (6 tab: Nodi, Mappa, Msg, Config, Metriche, Log) — Heroicons SVG inline, altezza 48px
- **Content area** sopra la tabbar, `height: calc(100vh - 48px)`, `overflow-y: auto`
- **Status bar in alto** (opzionale): indicatore connessione meshtasticd, temperatura Pi

**Heroicons:** inclusi come snippet SVG inline nei template Jinja2. Nessun icon font, nessuna emoji.

**PinesUI:** componenti usati per toggle, card, badge, modal. Importati via CDN Alpine.js. Nessun build step.

---

## Polling e SSE

**Polling (Alpine.js):**
```javascript
// In ogni pagina che ha dati aggiornabili
Alpine.data('nodesPage', () => ({
  nodes: [],
  async init() {
    await this.fetchNodes()
    setInterval(() => this.fetchNodes(), 10000)
  },
  async fetchNodes() {
    const r = await fetch('/api/nodes')
    this.nodes = await r.json()
  }
}))
```

**SSE (log board):**
```javascript
const es = new EventSource('/api/log/stream')
es.onmessage = e => { /* append log entry */ }
```

Server-side: `StreamingResponse` FastAPI con `text/event-stream`.

---

## Config

```python
# config.py
MESHTASTICD_HOST = os.getenv('MESHTASTICD_HOST', 'localhost')
MESHTASTICD_PORT = int(os.getenv('MESHTASTICD_PORT', '4403'))
DB_PATH          = os.getenv('DB_PATH', 'data/mesh.db')
LOG_LEVEL        = os.getenv('LOG_LEVEL', 'WARNING')
```

---

## Systemd

Due servizi separati:

**meshtasticd.service** — gestisce la board:
```ini
[Service]
ExecStart=/usr/sbin/meshtasticd --port /dev/ttyACM0
Restart=always
RestartSec=5
```

**pimesh.service** — app FastAPI:
```ini
[Service]
ExecStart=/home/pimesh/pi-Mesh/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1 --log-level warning
Restart=always
After=meshtasticd.service
```

---

## Deliverable della milestone

Al termine la milestone è completa quando:
- [ ] meshtasticd si connette alla board e riconnette automaticamente
- [ ] FastAPI serve tutte le 6 pagine (anche se vuote/placeholder)
- [ ] `/api/nodes` ritorna dati reali dalla board
- [ ] SQLite WAL inizializzato con lo schema base
- [ ] Cache in memoria funzionante con TTL
- [ ] SSE `/api/log/stream` emette eventi dalla board
- [ ] Layout PinesUI con tabbar, heroicons, Tailwind visibile su 320×480
- [ ] Due servizi systemd operativi e con dipendenza corretta
