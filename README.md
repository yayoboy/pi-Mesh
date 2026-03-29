# pi-Mesh

A touch-friendly web dashboard for [Meshtastic](https://meshtastic.org/) LoRa mesh radio networks, designed to run on a **Raspberry Pi** with a **320×480 touchscreen**. Monitor and control your mesh network from a pocket-sized device.

---

## What It Does

pi-Mesh connects to a Meshtastic radio via USB serial and exposes a real-time web UI accessible from the local touchscreen or any browser on the same Wi-Fi network. It lets you:

- **Monitor all nodes** seen by the radio — signal quality (SNR), battery level, distance, last heard
- **Send commands** — traceroute, position request, direct message to any node
- **View nodes on a map** — Leaflet with popup info and action buttons per marker
- **Real-time updates** — WebSocket pushes node, position, telemetry, and traceroute events live
- **Custom map markers** — add/delete your own POI markers on the map
- **Read incoming packets** — live log of all received radio packets

---

## Hardware

| Component | Details |
|-----------|---------|
| Raspberry Pi 3 A+ (or newer) | 512 MB RAM minimum |
| Meshtastic radio | Connected via USB — Heltec V3, T-Beam, etc. |
| 320×480 touchscreen (optional) | Portrait/landscape responsive layout |

---

## Installation

### Step 1 — Clone and set up the Python environment

```bash
cd ~
git clone https://github.com/yayoboy/pi-Mesh.git
cd pi-Mesh
git checkout rework/v2-rewrite

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2 — Configure

```bash
cp config.env config.env.local
nano config.env.local
```

Key settings:

```env
# USB serial port of the Meshtastic radio
SERIAL_PATH=/dev/ttyACM0

# Path where the SQLite database is stored
DB_PATH=/home/pimesh/pi-Mesh/data/mesh.db

# Map bounding box — set to your geographic area
MAP_LAT_MIN=41.0
MAP_LAT_MAX=43.0
MAP_LON_MIN=11.5
MAP_LON_MAX=14.5
```

> **Finding the radio's serial port:**
> ```bash
> ls /dev/ttyUSB* /dev/ttyACM*
> ```
> For Heltec V3 / ESP32-based boards, the port is typically `/dev/ttyACM0` or `/dev/ttyUSB0`.
> Meshtastic's `meshtasticd` daemon is **not required** for ESP32 boards — pi-Mesh talks directly via `SerialInterface`.

### Step 3 — Run manually (test)

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8080 --env-file config.env.local
```

Open `http://<pi-ip>:8080` in a browser.

### Step 4 — Install as a system service

```bash
sudo cp pimesh.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pimesh
```

Check status and logs:

```bash
sudo systemctl status pimesh
journalctl -u pimesh -f
```

### Step 5 — Map tiles

The map defaults to **OSM and Esri CDN tiles** if the Pi has internet access.

For **offline use**, place tiles at:
```
static/tiles/osm/{z}/{x}/{y}.png
static/tiles/topo/{z}/{x}/{y}.png
static/tiles/satellite/{z}/{x}/{y}.png
```

Then add `data-local-tiles="1"` to the `<html>` tag in `templates/base.html` to enable local serving.

---

## Project Structure

```
pi-Mesh/
├── main.py                      # FastAPI app — lifespan, routers, broadcast task
├── meshtasticd_client.py        # Serial interface, event queue, command queue, node cache
├── database.py                  # SQLite via aiosqlite — nodes, custom_markers, messages
├── config.py                    # Configuration — reads from environment / config.env
│
├── routers/
│   ├── nodes.py                 # GET /api/nodes, GET /nodes (page)
│   ├── commands.py              # POST/GET /api/nodes/{id}/traceroute, request-position, DM
│   ├── map_router.py            # GET/POST/DELETE /api/map/markers, GET /map (page)
│   ├── ws_router.py             # WebSocket /ws — ConnectionManager + broadcast
│   ├── log_router.py            # GET /log (page), SSE log stream
│   └── placeholders.py          # Stub routes for unimplemented tabs
│
├── templates/
│   ├── base.html                # Shell: status bar, tab bar, Alpine.js + Tailwind
│   ├── nodes.html               # Node list — portrait expand-row / landscape 2-column
│   ├── map.html                 # Leaflet map with popup, context menu, custom markers
│   └── log.html                 # Live packet log
│
├── static/
│   ├── app.js                   # WebSocket client, nodeActions, SPA navigation
│   ├── map.js                   # Leaflet init, markers, traceroute lines, popups
│   └── tiles/                   # Optional offline map tiles (OSM PNG format)
│
└── tests/                       # pytest test suite — 52 tests, hardware-free mocks
```

---

## API Reference

### Nodes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/nodes` | All known nodes (from cache + DB) |
| `GET` | `/api/nodes/{node_id}` | Single node |

### Commands

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/nodes/{node_id}/traceroute` | Send traceroute request |
| `GET`  | `/api/nodes/{node_id}/traceroute` | Get cached traceroute result |
| `POST` | `/api/nodes/{node_id}/request-position` | Request GPS position update |
| `POST` | `/api/messages/send` | Send direct message `{"to": "!abc", "text": "hi", "channel": 0}` |

All command endpoints return `503` if the board is not connected.

### Map Markers

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/map/markers` | List custom map markers |
| `POST` | `/api/map/markers` | Create marker `{"label": "Base", "icon_type": "poi", "latitude": 41.9, "longitude": 12.5}` |
| `DELETE` | `/api/map/markers/{id}` | Delete marker |

### WebSocket

`WS /ws` — real-time events broadcast to all connected clients.

**Message types:**

```json
{ "type": "init",             "nodes": [...] }
{ "type": "node",             "id": "!abc", "short_name": "NODE", "snr": -8, ... }
{ "type": "position",         "id": "!abc", "latitude": 41.9, "longitude": 12.5, "last_heard": 1711700000 }
{ "type": "telemetry",        "id": "!abc", "battery_level": 85, "snr": -8 }
{ "type": "traceroute_result","node_id": "!abc", "hops": ["!111", "!222"] }
{ "type": "log",              "ts": 1711700000, "from": "!abc", "portnum": "TEXT_MESSAGE_APP", "snr": -8, "hop_limit": 3 }
```

---

## Node Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Node ID (e.g. `!a1b2c3d4`) |
| `short_name` | `string` | Short callsign (≤4 chars) |
| `long_name` | `string` | Full name |
| `hw_model` | `string` | Hardware model |
| `latitude` | `float\|null` | GPS latitude |
| `longitude` | `float\|null` | GPS longitude |
| `last_heard` | `int\|null` | Unix timestamp of last packet |
| `snr` | `float\|null` | Signal-to-noise ratio (dB) |
| `hop_count` | `int\|null` | Hops away from local node |
| `battery_level` | `int\|null` | Battery percentage |
| `is_local` | `bool` | True for the Pi's own radio |
| `distance_km` | `float\|null` | Haversine distance from local node |

---

## Architecture Notes

- **Dual asyncio.Queue**: `_event_queue` (board→UI, thread-safe via `call_soon_threadsafe`) and `_command_queue` (UI→board, executed via `run_in_executor` to avoid blocking the event loop)
- **Write-batching**: node cache is flushed to SQLite every 60 seconds (preserves SD card write cycles); also flushed on shutdown
- **DB boot preload**: node cache is populated from SQLite before the board connects, so the UI shows last-known state immediately
- **`nodeActions` global**: shared JS object (`traceroute`, `requestPosition`, `sendDM`, `focusOnMap`) used by both `nodes.html` and `map.js` — no duplication
- **Responsive layout**: `@media (orientation: portrait/landscape)` CSS — portrait shows expand-row, landscape shows 2-column list+detail panel

---

## Development

### Run tests

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

52 tests, no hardware required (serial, meshtastic, and DB are mocked).

### Deploy to Pi

```bash
git push
ssh pimesh@192.168.1.36 "cd ~/pi-Mesh && git pull origin rework/v2-rewrite && sudo systemctl restart pimesh"
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
