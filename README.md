# pi-Mesh

A touch-friendly web dashboard for [Meshtastic](https://meshtastic.org/) LoRa mesh radio networks, designed to run on a **Raspberry Pi 3 A+** with a **Waveshare 3.5" SPI display** (480×320 px). Control your mesh network from a pocket-sized device — no internet required.

![Dashboard preview: 5 tabs — Messages, Nodes, Map, Telemetry, Settings]

---

## What It Does

pi-Mesh connects to a Heltec LoRa radio via USB serial and exposes a real-time web UI accessible from the local touchscreen or any device on the same Wi-Fi (or its own auto-created hotspot). It lets you:

- **Send and receive text messages** across the mesh network
- **Monitor all nodes** seen by the radio with signal quality and battery level
- **View nodes on an offline map** (no internet required — tiles served from local cache)
- **Read sensor telemetry** — device metrics from remote nodes plus local I2C sensors
- **Configure the radio** — LoRa presets, node roles, remote node admin
- **Navigate hands-free** — two rotary encoders scroll tabs and content without touching the screen

---

## Hardware Requirements

| Component | Details |
|-----------|---------|
| Raspberry Pi 3 A+ | 512 MB RAM, ARM Cortex-A53 |
| Waveshare 3.5" SPI Display | 480×320, XPT2046 resistive touch, ILI9486 driver |
| Heltec LoRa 32 V3 (or compatible) | Connected via USB, exposed as `/dev/ttyMESHTASTIC` |
| 2× Rotary encoders (optional) | GPIO-connected, for screen-free navigation |
| BME280 / INA219 (optional) | I2C sensors for local environment / power monitoring |
| Piezo buzzer (optional) | GPIO, for audio alerts on new messages |

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/pi-Mesh.git
cd pi-Mesh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.env /boot/firmware/config.env   # or keep it in the project root
```

Edit the key settings:

```env
# Serial port where the Heltec radio appears
SERIAL_PORT=/dev/ttyMESHTASTIC

# Where to persist the database on the SD card
DB_PERSISTENT=/home/pi/meshtastic-pi/data/mesh.db

# Map bounding box (default: Central Italy)
MAP_LAT_MIN=41.0
MAP_LAT_MAX=43.0
MAP_LON_MIN=11.5
MAP_LON_MAX=14.5
```

### 3. Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8080
```

Open `http://<raspberry-pi-ip>:8080` in a browser.

### 4. Install as a system service (auto-start on boot)

```bash
sudo cp meshtastic-pi.service /etc/systemd/system/
sudo systemctl enable --now meshtastic-pi
```

---

## Project Structure

```
pi-Mesh/
├── main.py                  # FastAPI app — routes, WebSocket, lifespan
├── meshtastic_client.py     # Meshtastic serial interface + pubsub bridge
├── database.py              # SQLite via aiosqlite — messages, nodes, telemetry
├── watchdog.py              # Background tasks: DB sync, reconnect, maintenance
├── gpio_handler.py          # Rotary encoders, button gestures, piezo buzzer
├── sensor_handler.py        # I2C sensor drivers (BME280, INA219)
├── config.py                # Configuration — reads from environment / config.env
├── config.env               # Default values for all config variables
│
├── bots/                    # Bot framework
│   └── echo_bot.py          # Example: auto-echo received messages
│
├── templates/               # Jinja2 HTML templates (server-side rendered)
│   ├── base.html            # Shell: status bar, tab bar, PWA meta tags
│   ├── messages.html        # Chat view with infinite scroll
│   ├── nodes.html           # Node list with signal badges
│   ├── map.html             # Leaflet.js offline map
│   ├── telemetry.html       # Chart.js graphs + I2C sensor display
│   └── settings.html        # Radio config, GPIO config, theme selector
│
├── static/
│   ├── style.css            # CSS variables for 3 themes, 480×320 layout
│   ├── app.js               # WebSocket client, SPA navigation, all UI logic
│   ├── chart.min.js         # Chart.js (vendored, no CDN dependency)
│   ├── manifest.json        # PWA app manifest
│   ├── sw.js                # Service worker — caches CSS/JS for offline use
│   └── tiles/               # Offline map tiles (OSM PNG or .mbtiles SQLite)
│
├── scripts/
│   ├── setup_zram.sh        # Configures ZRAM compressed swap (~700 MB effective)
│   └── auto_ap.sh           # Falls back to local hotspot "pi-mesh-portal" if no Wi-Fi
│
├── tests/                   # pytest test suite (35 tests, hardware-free mocks)
├── meshtastic-pi.service    # systemd unit file
└── requirements.txt         # Python dependencies
```

---

## UI Overview

The interface is a **Single-Page App** with 5 tabs. Navigation never reloads the page — tab content is fetched and injected via the WebSocket-aware SPA router.

| Tab | What it shows |
|-----|--------------|
| **Messages** | Chat log with infinite scroll, channel selector (0–2), send form |
| **Nodes** | All nodes seen by the radio — short name, last heard, SNR, battery %, coordinates |
| **Map** | Leaflet offline map with circle markers per node (blue = local, green = remote) |
| **Telemetry** | SNR and battery % charts for any selected node + live I2C sensor readings |
| **Settings** | LoRa presets, node role, remote node admin, GPIO pin config, theme, bot toggle |

### Encoder navigation

| Encoder | Action | Effect |
|---------|--------|--------|
| Encoder 1 | Rotate CW/CCW | Switch to next/previous tab |
| Encoder 1 | Long press | Return to Messages tab |
| Encoder 2 | Rotate CW/CCW | Scroll content / zoom map |
| Both | Long press (3 s) | Graceful shutdown (syncs DB, then `shutdown -h now`) |

### Themes

Three themes switchable from Settings or via `UI_THEME` in config:

- **dark** (default) — dark grey, blue accent
- **light** — light grey, navy accent
- **hc** — high-contrast black/white/yellow for visibility in bright sunlight

---

## Configuration Reference

All variables can be set in `config.env` (or as environment variables via the systemd `EnvironmentFile`).

| Variable | Default | Description |
|----------|---------|-------------|
| `SERIAL_PORT` | `/dev/ttyMESHTASTIC` | USB serial device for the radio |
| `DB_PERSISTENT` | `/home/pi/meshtastic-pi/data/mesh.db` | SD-card path for database persistence |
| `DB_SYNC_INTERVAL` | `300` | Seconds between RAM→SD database syncs |
| `ENC1_A/B/SW` | `17/27/22` | GPIO BCM pins for encoder 1 (tab navigation) |
| `ENC2_A/B/SW` | `5/6/13` | GPIO pins for encoder 2 (scroll/zoom) |
| `BUZZER_PIN` | `0` (disabled) | GPIO pin for piezo buzzer; `0` = off |
| `I2C_SENSORS` | `` (empty) | Comma-separated sensor list, e.g. `bme280:0x76,ina219:0x40` |
| `MAP_LAT_MIN/MAX` | `41.0/43.0` | Map bounding box latitude |
| `MAP_LON_MIN/MAX` | `11.5/14.5` | Map bounding box longitude |
| `MAP_ZOOM_MIN/MAX` | `8/12` | Leaflet zoom level limits |
| `DISPLAY_ROTATION` | `0` | Display rotation (0, 90, 180, 270) |
| `UI_THEME` | `dark` | UI theme: `dark`, `light`, or `hc` |

---

## Offline Maps

Tiles are served locally — no internet connection needed during use.

### Option A: MBTiles (recommended)

Place a single SQLite file in `static/tiles/`:

```
static/tiles/osm.mbtiles    ← OpenStreetMap tiles
static/tiles/topo.mbtiles   ← Topographic tiles (optional)
```

MBTiles files can be downloaded with tools like [TileMill](https://tilemill-project.github.io/tilemill/), [mbutil](https://github.com/mapbox/mbutil), or [MapTiler](https://www.maptiler.com/).

### Option B: PNG tile cache

Organize tiles as individual files:

```
static/tiles/osm/{z}/{x}/{y}.png
static/tiles/topo/{z}/{x}/{y}.png
```

The tile server tries MBTiles first; falls back to PNG files automatically.

---

## Optional Features

### I2C Sensors

Set `I2C_SENSORS` in `config.env` to auto-detect and poll sensors. Supported drivers:

| Sensor | Address | Measures |
|--------|---------|----------|
| BME280 | `0x76` or `0x77` | Temperature, humidity, pressure |
| INA219 | `0x40`–`0x4F` | Voltage, current, power |

Live readings appear in the **Telemetry** tab and are saved to the database.

### Piezo Buzzer

Set `BUZZER_PIN` to a GPIO BCM pin number. The buzzer emits:

- **1 short beep** — new text message received
- **2 short beeps** — new node joined the mesh

### Bot Framework

Enable the echo bot from the **Settings** tab or write your own:

```python
# bots/my_bot.py
def start(interface):
    from pubsub import pub
    def on_message(packet, interface):
        if packet["decoded"]["text"].startswith("!"):
            interface.sendText("Received your command!", destinationId=packet["fromId"])
    pub.subscribe(on_message, "meshtastic.receive.text")
```

### Optimizations for Raspberry Pi 3 A+

The `scripts/` directory contains deployment helpers:

```bash
# ZRAM: adds ~300 MB of compressed swap without touching the SD card
sudo bash scripts/setup_zram.sh

# Auto-AP: creates "pi-mesh-portal" hotspot if no Wi-Fi is found after 60s
# (requires hostapd + dnsmasq)
sudo bash scripts/auto_ap.sh
```

---

## Development

### Run tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

All 35 tests run without real hardware (GPIO, serial, and I2C are fully mocked).

### Project conventions

- **Database**: runs from `/tmp/` (RAM), synced to SD every 5 minutes — never write to SD directly
- **Blocking I/O**: all serial/I2C calls are wrapped in `asyncio.to_thread()` to avoid stalling the event loop
- **Templates**: Jinja2 autoescape is active — `{{ variable }}` is XSS-safe
- **Frontend**: `escHtml()` is used for all dynamic `innerHTML` insertions in `app.js`

---

## API Endpoints

The FastAPI backend exposes these JSON endpoints (used internally by the UI and available for scripting):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/nodes` | All known nodes |
| `GET` | `/api/messages?channel=0&limit=50` | Messages with optional pagination (`before_id`) |
| `GET` | `/api/telemetry/{node_id}/{type}` | Telemetry history (`deviceMetrics`, `environmentMetrics`) |
| `GET` | `/api/sensor/{sensor_name}` | Local I2C sensor history |
| `GET` | `/api/status` | Connection status + RAM usage |
| `POST` | `/send` | Send a text message `{"text": "...", "channel": 0}` |
| `POST` | `/settings` | Apply radio config changes |
| `POST` | `/api/remote-config` | Configure a remote node `{"remote_node_id": "!abc", "device": {...}}` |
| `POST` | `/api/set-theme` | Change UI theme `{"theme": "dark"}` |
| `GET` | `/tiles/{source}/{z}/{x}/{y}` | Serve offline map tile (MBTiles or PNG) |
| `WS` | `/ws` | WebSocket — real-time events (messages, nodes, telemetry, sensor, encoder, status) |

### WebSocket message types

```json
{ "type": "init",      "data": { "connected": true, "nodes": [...], "messages": [...], "theme": "dark" } }
{ "type": "message",   "data": { "node_id": "!abc123", "text": "Hello", "timestamp": 1700000000 } }
{ "type": "node",      "data": { "id": "!abc123", "short_name": "NODE", "snr": 7.5, "battery_level": 85 } }
{ "type": "position",  "data": { "node_id": "!abc123", "latitude": 41.9, "longitude": 12.5 } }
{ "type": "telemetry", "data": { "node_id": "!abc123", "type": "deviceMetrics", "values": {...} } }
{ "type": "sensor",    "data": { "sensor": "bme280", "values": { "temp": 22.1, "humidity": 45.0 } } }
{ "type": "encoder",   "data": { "encoder": 1, "action": "cw" } }
{ "type": "status",    "data": { "connected": true, "ram_mb": 87.4 } }
```

---

## Troubleshooting

**Radio not detected**

```bash
ls /dev/ttyUSB* /dev/ttyACM*   # find the actual device name
sudo usermod -aG dialout pi    # give the pi user serial access
# then set SERIAL_PORT in config.env
```

**Display not working**

The Waveshare 3.5" SPI display requires the `LCD-show` driver. Follow [Waveshare's official guide](https://www.waveshare.com/wiki/3.5inch_RPi_LCD_(A)) to install it, then set `DISPLAY_ROTATION` in config.env.

**Map shows blank tiles**

Verify your tile files are in place:

```bash
ls static/tiles/osm.mbtiles        # MBTiles
ls static/tiles/osm/10/            # or PNG files at zoom level 10
```

**Out of memory / process killed**

Run `scripts/setup_zram.sh` to add compressed swap. Also ensure `MemoryMax=200M` in the systemd unit is appropriate for your workload.

**No GPIO / encoder input**

The `pigpiod` daemon must be running:

```bash
sudo systemctl enable --now pigpiod
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
