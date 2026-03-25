# pi-Mesh

A touch-friendly web dashboard for [Meshtastic](https://meshtastic.org/) LoRa mesh radio networks, designed to run on a **Raspberry Pi 3 A+** with a **Waveshare 3.5" SPI display** (320×480 px portrait). Control your mesh network from a pocket-sized device — fully offline, no internet required.

---

## Download

| | |
|---|---|
| **Immagine pronta (consigliato)** | Scarica l'ultima `.img.xz` dalla [pagina Release](https://github.com/yayoboy/pi-Mesh/releases/latest), flasha con [Raspberry Pi Imager](https://www.raspberrypi.com/software/), accendi il Pi e apri `http://pi-mesh.local:8080` |
| **Installa su Pi esistente** | `curl -fsSL https://raw.githubusercontent.com/yayoboy/pi-Mesh/master/install.sh \| bash` |
| **Aggiorna installazione esistente** | `bash install.sh --update` |

---

## Table of Contents

- [Download](#download)
- [What It Does](#what-it-does)
- [Hardware Requirements](#hardware-requirements)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [UI Overview](#ui-overview)
  - [Status Bar](#status-bar)
  - [Tabs](#tabs)
  - [Encoder Navigation](#encoder-navigation)
  - [Themes](#themes)
  - [Screen Orientation](#screen-orientation)
- [Configuration Reference](#configuration-reference)
- [API Endpoints](#api-endpoints)
  - [WebSocket Events](#websocket-events)
- [Offline Maps](#offline-maps)
- [Optional Features](#optional-features)
  - [I2C Sensors](#i2c-sensors)
  - [Piezo Buzzer](#piezo-buzzer)
  - [Bot Framework](#bot-framework)
  - [System Optimizations](#system-optimizations)
- [Creating Custom Themes](#creating-custom-themes)
- [GPIO Pinout](#gpio-pinout)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What It Does

pi-Mesh connects to a Heltec LoRa radio via USB serial and exposes a real-time web UI accessible from the local touchscreen or any device on the same Wi-Fi network. It lets you:

- **Send and receive messages** — channel-based chat with infinite scroll and per-channel selection
- **Monitor the mesh** — all visible nodes with signal quality, battery level, and time-since-heard
- **View nodes on an offline map** — OpenStreetMap, satellite, and topo layers served from local cache
- **Monitor hardware** — live GPIO state grid, I2C sensor values, encoder status
- **Administer remote nodes** — reboot, mute, ping, and reconfigure any node over the admin channel
- **Navigate hands-free** — two rotary encoders switch tabs and scroll content without touching the screen
- **Persist across reboots** — database runs in RAM (`/tmp/`), synced to SD every 5 minutes

---

## Hardware Requirements

| Component | Details |
|-----------|---------|
| Raspberry Pi 3 A+ | 512 MB RAM, ARM Cortex-A53 |
| Waveshare 3.5" SPI Display | 320×480 portrait, XPT2046 resistive touch, ILI9486 driver |
| Heltec LoRa 32 V3 (or compatible) | Connected via USB, exposed as `/dev/ttyMESHTASTIC` |
| 2× Rotary encoders (optional) | GPIO-connected, for screen-free navigation |
| BME280 / INA219 (optional) | I2C sensors for local environment / power monitoring |
| Piezo buzzer (optional) | GPIO, for audio alerts on new messages |

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/yayoboy/pi-Mesh.git
cd pi-Mesh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.env.example config.env   # or edit config.env directly
```

Key settings:

```env
# Serial port where the Heltec radio appears
SERIAL_PORT=/dev/ttyMESHTASTIC

# Where to persist the database on the SD card
DB_PERSISTENT=/home/pi/meshtastic-pi/data/mesh.db

# Map bounding box (default: Central Italy — change to your area)
MAP_LAT_MIN=41.0
MAP_LAT_MAX=43.0
MAP_LON_MIN=11.5
MAP_LON_MAX=14.5
```

### 3. Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8080
```

Open `http://<raspberry-pi-ip>:8080` in any browser.

### 4. Auto-start on boot

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
├── sensor_handler.py        # I2C sensor drivers (BME280, INA219, …)
├── sensor_detect.py         # Auto-scan I2C bus at startup
├── config.py                # Configuration — reads from environment / config.env
├── config.env               # Default values for all config variables
│
├── bots/
│   └── echo_bot.py          # Example: auto-echo received messages
│
├── templates/               # Jinja2 HTML templates (server-side rendered)
│   ├── base.html            # Shell: status bar, 6-tab nav, SVG icon sprite
│   ├── icons.svg            # Inline MDI SVG sprite (offline-safe, no CDN)
│   ├── home.html            # Local node card, Pi system stats, recent nodes
│   ├── channels.html        # Chat — 3 layout modes (list / tabs / unified)
│   ├── map.html             # Leaflet offline map — OSM / SAT / TOPO layers
│   ├── hardware.html        # GPIO grid, I2C sensor list, encoder status
│   ├── settings.html        # UI prefs, radio config, GPIO config, map cache
│   └── remote.html          # Remote node admin — commands and config
│
├── static/
│   ├── style.css            # Tiny-CSS — design tokens, 3 themes, grid layout
│   ├── app.js               # WebSocket client, encoder nav, all UI logic
│   ├── manifest.json        # PWA app manifest
│   ├── sw.js                # Service worker — caches CSS/JS for offline use
│   └── tiles/               # Offline map tiles (OSM PNG or .mbtiles SQLite)
│
├── scripts/
│   ├── setup_zram.sh        # Configures ZRAM compressed swap (~700 MB effective)
│   └── auto_ap.sh           # Falls back to hotspot "pi-mesh-portal" if no Wi-Fi
│
├── tests/                   # pytest suite — 103 tests, all hardware-free mocks
├── meshtastic-pi.service    # systemd unit file
└── requirements.txt         # Python dependencies
```

---

## UI Overview

The interface targets a **320×480 px portrait touchscreen** (landscape 480×320 also supported). Each tab is a full server-side render — JavaScript is kept minimal and the page stays fast on the Pi's limited CPU.

### Status Bar

A persistent bar across the top shows 5 live indicators, each color-coded green / yellow / red:

| # | Indicator | Green | Yellow | Red |
|---|-----------|-------|--------|-----|
| 1 | **Meshtastic** | Connected | Connecting | Disconnected |
| 2 | **USB Serial** | Port open | — | Error / absent |
| 3 | **GPS** | 3D fix | 2D fix | No fix |
| 4 | **Battery** | > 50 % | 20 – 50 % | < 20 % |
| 5 | **TX / RX** | Idle | — | Active |

Three **density modes**, selectable in Settings:

| Mode | Height | Content |
|------|--------|---------|
| `compact` | 20 px | Colored dots only |
| `icons` | 24 px | MDI icons, no text (default) |
| `full` | 32 px | Icons + live values (node count, satellite count, battery %) |

### Tabs

Six fixed tabs at the bottom (portrait) or left side (landscape):

| Tab | Route | Description |
|-----|-------|-------------|
| **Home** | `/home` | Local node info, Pi system stats (CPU, RAM, temp), recent nodes |
| **Chat** | `/channels` | Channel and DM messages — 3 selectable layout modes |
| **Mappa** | `/map` | Offline map with node markers, OSM / SAT / TOPO layer switcher |
| **HW** | `/hardware` | GPIO state grid, I2C sensor list with live rescan, encoder status |
| **Set** | `/settings` | All configuration — UI prefs, radio, hardware, map cache |
| **RMT** | `/remote` | Remote node administration — commands, config, telemetry |

### Encoder Navigation

| Encoder | Action | Effect |
|---------|--------|--------|
| Encoder 1 | CW | Next tab |
| Encoder 1 | CCW | Previous tab |
| Encoder 1 | Long press | Return to Home |
| Encoder 2 | CW | Scroll down / zoom in (map) |
| Encoder 2 | CCW | Scroll up / zoom out (map) |
| Encoder 2 | Long press | Back (from chat detail or remote node detail) |

### Themes

Three themes switchable live from **Settings → Display**:

| Theme | Description |
|-------|-------------|
| `dark` | Dark grey background, blue accent (default) |
| `light` | Light grey background, blue accent |
| `hc` | High-contrast black/white/cyan — bright sunlight or accessibility |

See [Creating Custom Themes](#creating-custom-themes) to add your own.

### Screen Orientation

**Settings → Display → Orientamento** switches between portrait (320×480, default) and landscape (480×320). In landscape mode the tab bar moves to the left side. The preference persists via `config.env`.

---

## Configuration Reference

All variables can be set in `config.env` or as environment variables (e.g. via the systemd `EnvironmentFile` directive).

| Variable | Default | Description |
|----------|---------|-------------|
| `SERIAL_PORT` | `/dev/ttyMESHTASTIC` | USB serial device for the radio |
| `DB_PERSISTENT` | `/home/pi/meshtastic-pi/data/mesh.db` | SD-card path for database persistence |
| `DB_SYNC_INTERVAL` | `300` | Seconds between RAM → SD database syncs |
| `ENC1_A/B/SW` | `23/24/22` | GPIO BCM pins for Encoder 1 (tab navigation) |
| `ENC2_A/B/SW` | `5/6/13` | GPIO BCM pins for Encoder 2 (scroll / zoom) |
| `BUZZER_PIN` | `0` (disabled) | GPIO BCM pin for piezo buzzer (`0` = off). GPIO 12 recommended |
| `I2C_SENSORS` | `` (empty) | Comma-separated sensor list, e.g. `bme280:0x76,ina219:0x40` |
| `I2C_AUTOSCAN` | `1` | Scan I2C bus at startup and merge with `I2C_SENSORS` |
| `MAP_LAT_MIN/MAX` | `41.0 / 43.0` | Map bounding box latitude |
| `MAP_LON_MIN/MAX` | `11.5 / 14.5` | Map bounding box longitude |
| `MAP_ZOOM_MIN/MAX` | `8 / 12` | Leaflet zoom level limits |
| `DISPLAY_ROTATION` | `0` | Physical display rotation: `0` / `1` / `2` / `3` = 0° / 90° / 180° / 270° |
| `UI_THEME` | `dark` | UI color theme: `dark`, `light`, `hc` |
| `UI_STATUS_DENSITY` | `icons` | Status bar density: `compact`, `icons`, `full` |
| `UI_CHANNEL_LAYOUT` | `list` | Channel tab layout: `list`, `tabs`, `unified` |
| `UI_ORIENTATION` | `portrait` | Screen orientation: `portrait`, `landscape` |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/nodes` | All known nodes |
| `GET` | `/api/messages?channel=0&limit=50` | Messages with optional `before_id` cursor |
| `GET` | `/api/telemetry/{node_id}/{type}` | Telemetry history (`deviceMetrics`, `environmentMetrics`) |
| `GET` | `/api/sensor/{sensor_name}` | Local I2C sensor readings history |
| `GET` | `/api/status` | Connection status + RAM usage |
| `GET` | `/api/i2c/scan?live=false` | Detected I2C sensors (startup list or live rescan) |
| `GET` | `/api/tile/cache/info` | Tile cache size in bytes and MB |
| `POST` | `/api/tile/cache/clear` | Delete all cached tiles and MBTiles files |
| `POST` | `/send` | Send a text message `{"text": "…", "channel": 0}` |
| `POST` | `/settings` | Apply radio config via Meshtastic API |
| `POST` | `/settings/ui` | Persist a UI preference key/value to `config.env` |
| `POST` | `/api/remote-config` | Configure a remote node `{"remote_node_id": "!abc", "device": {…}}` |
| `POST` | `/api/remote/{node_id}/command` | Send a command to a remote node (`reboot`, `mute`, `ping`, …) |
| `POST` | `/api/hardware-config` | Update encoder pins, I2C sensors, display rotation |
| `POST` | `/api/set-theme` | Change UI theme `{"theme": "dark"}` |
| `GET` | `/tiles/{source}/{z}/{x}/{y}` | Serve an offline map tile (`osm`, `topo`, `sat`) |
| `WS` | `/ws` | WebSocket — real-time events |

### WebSocket Events

All messages follow the envelope `{ "type": "…", "data": {…} }`.

```json
{ "type": "init",     "data": { "connected": true, "nodes": [], "messages": [], "theme": "dark" } }
{ "type": "status",   "data": { "mesh_connected": true, "node_count": 4, "battery_pct": 87 } }
{ "type": "node",     "data": { "id": "!abc123", "short_name": "NODE", "snr": 7.5, "last_heard": 1700000000 } }
{ "type": "message",  "data": { "node_id": "!abc123", "channel": 0, "text": "Hello", "timestamp": 1700000000 } }
{ "type": "position", "data": { "node_id": "!abc123", "latitude": 41.9, "longitude": 12.5 } }
{ "type": "telemetry","data": { "node_id": "!abc123", "type": "deviceMetrics", "values": {} } }
{ "type": "sensor",   "data": { "sensor": "bme280", "values": { "temp": 22.1, "humidity": 45.0 } } }
{ "type": "encoder",  "data": { "encoder": 1, "action": "cw" } }
```

---

## Offline Maps

Tiles are served entirely from the Pi — no internet connection needed during use.

### Option A — MBTiles (recommended)

Place a single SQLite file in `static/tiles/`:

```
static/tiles/osm.mbtiles    ← OpenStreetMap tiles
static/tiles/topo.mbtiles   ← Topographic tiles (optional)
static/tiles/sat.mbtiles    ← Satellite imagery (optional)
```

MBTiles files can be created with [TileMill](https://tilemill-project.github.io/tilemill/), [mbutil](https://github.com/mapbox/mbutil), or [MapTiler](https://www.maptiler.com/).

### Option B — PNG tile cache

```
static/tiles/osm/{z}/{x}/{y}.png
static/tiles/topo/{z}/{x}/{y}.png
```

The server tries MBTiles first; falls back to PNG files automatically.

### Managing cache

**Settings → Mappa** shows the current cache size. **Elimina cache** calls `POST /api/tile/cache/clear` to free the space.

---

## Optional Features

### I2C Sensors

Set `I2C_SENSORS` in `config.env` to poll sensors wired to the Pi:

```env
I2C_SENSORS=bme280:0x76,ina219:0x40
```

With `I2C_AUTOSCAN=1` (default) the bus is scanned at startup and discovered devices are merged automatically. Live readings appear in **HW → Sensori I2C**.

#### Supported drivers

| Name | I2C address | Measures |
|------|-------------|----------|
| `bme280` | `0x76` / `0x77` | Temperature, humidity, pressure |
| `bme680` | `0x76` / `0x77` | Temperature, humidity, pressure, VOC |
| `bmp280` | `0x76` / `0x77` | Temperature, pressure |
| `bmp085` / `bmp180` | `0x77` | Temperature, pressure (legacy) |
| `sht31` | `0x44` / `0x45` | Temperature, humidity |
| `shtc3` | `0x70` | Temperature, humidity |
| `mcp9808` | `0x18`–`0x1F` | Temperature (±0.0625 °C) |
| `lps22hb` | `0x5C` / `0x5D` | Pressure, temperature |
| `pmsa003i` | `0x12` | PM1.0, PM2.5, PM10 |
| `sen5x` | `0x69` | PM, NOx, VOC, temperature, humidity |
| `veml7700` | `0x10` | Ambient lux |
| `tsl2591` | `0x29` | Lux (high dynamic range) |
| `rcwl9620` | `0x13` | Distance (cm) |
| `ina219` | `0x40`–`0x4F` | Voltage, current, power |
| `ina260` | `0x40`–`0x4F` | Voltage, current, power |
| `ina3221` | `0x40`–`0x43` | 3-channel voltage / current |
| `max17048` | `0x36` | LiPo state of charge % |

> Most drivers require `adafruit-blinka`. See `requirements.txt`.

#### Adding a new driver

The architecture requires exactly two changes: a class in `sensor_handler.py` and an entry in `_DRIVER_MAP`:

```python
class SHT31Driver(BaseSensor):
    @property
    def name(self): return "sht31"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        if _SMBUS_AVAILABLE:
            try:
                import adafruit_sht31d, board
                self._driver = adafruit_sht31d.SHT31D(board.I2C(), address=self.address)
            except Exception as e:
                logging.error(f"SHT31 init: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {"temp": round(self._driver.temperature, 1),
                    "humidity": round(self._driver.relative_humidity, 1)}
        except Exception as e:
            logging.error(f"SHT31 read: {e}")
            return None
```

Then register it:

```python
_DRIVER_MAP = {
    ...
    "sht31": SHT31Driver,
}
```

### Piezo Buzzer

Set `BUZZER_PIN` to a GPIO BCM pin. The buzzer emits:

- **1 short beep** — new text message received
- **2 short beeps** — new node joined the mesh

GPIO 12 (pin 32) is recommended — PWM-capable and free from the SPI display.

### Bot Framework

Enable the built-in echo bot from **Settings → Bot**, or write your own:

```python
# bots/my_bot.py
def start(interface):
    from pubsub import pub
    def on_message(packet, interface):
        if packet["decoded"]["text"].startswith("!ping"):
            interface.sendText("pong", destinationId=packet["fromId"])
    pub.subscribe(on_message, "meshtastic.receive.text")
```

### System Optimizations

The `scripts/` directory contains helpers for the Pi 3 A+:

```bash
# ZRAM: ~300 MB of compressed swap without wearing the SD card
sudo bash scripts/setup_zram.sh

# Auto-AP: creates "pi-mesh-portal" hotspot if no Wi-Fi is found after 60 s
# (requires hostapd + dnsmasq)
sudo bash scripts/auto_ap.sh
```

---

## Creating Custom Themes

Add a CSS class that overrides 10 custom properties, then register the name in `main.py`.

### 1 — CSS variables (`static/style.css`)

```css
.theme-forest {
  --bg:      #1b2a1b;   /* main background */
  --bg2:     #243324;   /* cards, inputs, status bar, tab bar */
  --bg3:     #2e3d2e;   /* input fields, GPIO pin cells */
  --border:  #3a5c3a;   /* dividers and borders */
  --text:    #d4edda;   /* primary text */
  --text2:   #7aab7a;   /* secondary / dimmed text and icons */
  --accent:  #56c56a;   /* active tab, buttons, outgoing bubbles */
  --ok:      #4caf50;   /* connected, online node */
  --warn:    #ffc107;   /* recent node, yellow status */
  --danger:  #f44336;   /* disconnected, error */
}
```

### 2 — Allow the name in `main.py`

```python
# In the /api/set-theme endpoint
if theme not in ("dark", "light", "hc", "forest"):   # ← add here
```

### 3 — Set as default (optional)

```env
UI_THEME=forest
```

### Tips for the 320×480 display

- Keep `--bg` and `--bg2` close in lightness — harsh contrast strains the LCD panel
- `--ok`, `--warn`, `--danger` appear as 8 px dots against `--bg2`; verify readability at small size
- For outdoor use, prefer high `--text` / `--bg` contrast (≥ 4.5:1) and fully saturated `--accent`

---

## GPIO Pinout

The Waveshare 3.5" SPI display occupies the following BCM pins — **do not use them for other peripherals**:

| BCM | Function | Physical pin |
|-----|----------|-------------|
| 7 | Touch CS (CE1) | 26 |
| 8 | LCD CS (CE0) | 24 |
| 9 | SPI MISO | 21 |
| 10 | SPI MOSI | 19 |
| 11 | SPI SCLK | 23 |
| 17 | Touch IRQ | 11 |
| 18 | Backlight PWM | 12 |
| 25 | LCD DC | 22 |
| 27 | LCD RST | 13 |

**Free BCM pins** available for encoders, buzzer, and sensors:

```
4  (pin 7)   5  (pin 29)  6  (pin 31)  12 (pin 32) ← PWM
13 (pin 33) ← PWM         16 (pin 36)  19 (pin 35)  20 (pin 38)
21 (pin 40)  22 (pin 15)  23 (pin 16)  24 (pin 18)  26 (pin 37)
```

I2C (GPIO 2/3, pins 3/5) is reserved for sensors. UART (GPIO 14/15, pins 8/10) is reserved for the serial console.

**Default wiring** (as configured in `config.env`):

```
Encoder 1 (tab nav)  → A=GPIO23  B=GPIO24  SW=GPIO22
Encoder 2 (scroll)   → A=GPIO5   B=GPIO6   SW=GPIO13
Buzzer (optional)    → GPIO12  (PWM hardware)
I2C sensors          → SDA=GPIO2  SCL=GPIO3
```

---

## Development

### Run tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

103 tests run without real hardware — GPIO, serial, and I2C are fully mocked.

### Project conventions

- **Database** — runs from `/tmp/` (RAM), synced to SD every 5 minutes; never write directly to the SD-backed path
- **Blocking I/O** — all serial / I2C calls are wrapped in `asyncio.to_thread()` to keep the event loop free
- **DOM security** — `app.js` uses `textContent` and `createElement` exclusively; no `innerHTML` with user-controlled data
- **Templates** — Jinja2 autoescape is active; `{{ variable }}` is XSS-safe by default
- **CSS** — design tokens only; all spacing on a 4 px grid; no framework dependency

---

## Troubleshooting

**Radio not detected**

```bash
ls /dev/ttyUSB* /dev/ttyACM*   # find the actual device name
sudo usermod -aG dialout pi    # give the pi user serial access
# then set SERIAL_PORT in config.env
```

**Display not working**

The Waveshare 3.5" SPI display requires the `LCD-show` driver. Follow the [official Waveshare guide](https://www.waveshare.com/wiki/3.5inch_RPi_LCD_(A)), then set `DISPLAY_ROTATION` in `config.env`.

**Map shows blank tiles**

```bash
ls static/tiles/osm.mbtiles        # MBTiles
ls static/tiles/osm/10/            # or PNG files at zoom level 10
```

**Out of memory / process killed**

Run `scripts/setup_zram.sh` to add compressed swap. Verify `MemoryMax=200M` in the systemd unit is appropriate for your workload.

**No GPIO / encoder input**

The `pigpiod` daemon must be running:

```bash
sudo systemctl enable --now pigpiod
```

**UI settings not persisting after reboot**

Settings are written to `config.env` in the project root. The systemd unit must reference it:

```ini
[Service]
EnvironmentFile=/home/pi/pi-Mesh/config.env
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
