# pi-Mesh

A touch-friendly web dashboard for [Meshtastic](https://meshtastic.org/) LoRa mesh radio networks, designed to run on a **Raspberry Pi** with a **Waveshare 3.5" SPI display** (480×320 px). Control your mesh network from a pocket-sized device — no internet required.

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
| Raspberry Pi 3B+ / 4 / Zero 2W | 512 MB RAM minimum |
| Waveshare 3.5" SPI Display | 480×320, XPT2046 resistive touch, ILI9486 driver |
| Heltec LoRa 32 V3 (or compatible) | Connected via USB, exposed as `/dev/ttyMESHTASTIC` |
| 2× Rotary encoders (optional) | GPIO-connected, for screen-free navigation |
| BME280 / INA219 (optional) | I2C sensors for local environment / power monitoring |
| Piezo buzzer (optional) | GPIO, for audio alerts on new messages |

---

## Installation Guide

> **Key concept:** This guide has two types of steps:
> - Steps marked **[PC/Mac]** — run these on your personal computer
> - Steps marked **[Raspberry Pi]** — run these on the Pi, via SSH from your PC

---

### Step 0 — Prepare the Raspberry Pi

> **[PC/Mac]** Do this before touching the Pi.

1. Download and install **Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Insert the microSD card into your PC
3. In Raspberry Pi Imager:
   - Choose your Pi model
   - Choose **Raspberry Pi OS Lite (64-bit)** (no desktop needed)
   - Click the gear icon (⚙️) before writing to pre-configure:
     - **Hostname:** `pi-mesh`
     - **Username/Password:** e.g. `pi` / `yourpassword`
     - **Wi-Fi SSID and password** (your home network)
     - **Enable SSH** → "Use password authentication"
4. Write the image to the SD card, then insert it into the Pi and power it on
5. Wait ~60 seconds for first boot

---

### Step 1 — Connect to the Pi via SSH

> **[PC/Mac]** You'll do all the following steps by remote-controlling the Pi from your PC.

Open a terminal on your PC (Terminal on Mac, PowerShell or Git Bash on Windows) and run:

```bash
ssh pi@pi-mesh.local
```

> If `pi-mesh.local` doesn't work, find the Pi's IP address from your router's admin panel (usually at `192.168.1.1`) and use that instead:
> ```bash
> ssh pi@192.168.1.42
> ```

You'll be prompted for the password you set in Step 0. Once logged in, you'll see the Pi's command prompt — **all commands from here on run on the Pi unless noted otherwise.**

---

### Step 2 — Install system dependencies

> **[Raspberry Pi]** Run this after logging in via SSH.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git python3-lgpio
```

> `python3-lgpio` is the system GPIO library used by pi-Mesh to control rotary encoders and the buzzer. It must be installed via `apt` (not `pip`) because it is not available as a standard PyPI package on Raspberry Pi OS Trixie (Debian 13).
>
> **Note:** On older Raspberry Pi OS (Bullseye or earlier) you may use `pigpiod` instead — see [Troubleshooting](#troubleshooting).

---

### Step 3 — Install the Waveshare display driver

> **[Raspberry Pi]** Skip this if you're not using the physical display (e.g. testing headlessly).

The Waveshare 3.5" SPI display requires a custom driver. Follow [Waveshare's official guide](https://www.waveshare.com/wiki/3.5inch_RPi_LCD_(A)) to install `LCD-show`, then come back here.

After installing, set the display rotation in `config.env` (Step 5).

---

### Step 4 — Clone the repository

> **[Raspberry Pi]**

```bash
cd ~
git clone https://github.com/<your-username>/pi-Mesh.git
cd pi-Mesh
```

Create and activate a Python virtual environment, then install dependencies:

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

> The `--system-site-packages` flag lets the venv access `python3-lgpio` (installed via `apt` in Step 2) alongside the packages installed via `pip`. Without this flag, GPIO would not work.
>
> You need to activate the venv (`source venv/bin/activate`) each time you open a new SSH session and want to run the app manually.

---

### Step 5 — Configure

> **[Raspberry Pi]**

Copy the default config file and open it for editing:

```bash
cp config.env config.env.local
nano config.env.local
```

Key settings to check:

```env
# USB serial port of the Heltec radio — find it with: ls /dev/ttyUSB* /dev/ttyACM*
SERIAL_PORT=/dev/ttyMESHTASTIC

# Path where the database is saved permanently on the SD card
DB_PERSISTENT=/home/pi/pi-Mesh/data/mesh.db

# Map bounding box — set to your geographic area
MAP_LAT_MIN=41.0
MAP_LAT_MAX=43.0
MAP_LON_MIN=11.5
MAP_LON_MAX=14.5
```

Save and exit nano: press `Ctrl+X`, then `Y`, then `Enter`.

> **Finding the radio's serial port:** Plug the Heltec into the Pi's USB port, then run:
> ```bash
> ls /dev/ttyUSB* /dev/ttyACM*
> ```
> You'll see something like `/dev/ttyUSB0` or `/dev/ttyACM0`. Set `SERIAL_PORT` to that value.
> To make it permanent, you can also create a udev rule — see [Troubleshooting](#troubleshooting).

---

### Step 6 — Run (manual test)

> **[Raspberry Pi]**

Make sure you're in the project directory with the venv active, then start the server:

```bash
cd ~/pi-Mesh
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8080 --env-file config.env.local
```

You should see output like:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8080
```

**Access the dashboard:**
- From the Pi's touchscreen: the browser should open automatically
- From your PC browser: go to `http://pi-mesh.local:8080` (or `http://192.168.1.42:8080`)

Press `Ctrl+C` to stop the server.

---

### Step 7 — Install as a system service (auto-start on boot)

> **[Raspberry Pi]** Do this once you've confirmed the app works.

```bash
cd ~/pi-Mesh
sudo cp meshtastic-pi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meshtastic-pi
```

The app will now start automatically every time the Pi boots. To check its status:

```bash
sudo systemctl status meshtastic-pi
```

To view live logs:

```bash
journalctl -u meshtastic-pi -f
```

---

### Step 8 — Optional: set up offline maps

> **[Raspberry Pi]** Skip if you don't need the Map tab.

The map works entirely offline — no internet needed. You just need to provide map tiles.

**Option A: MBTiles file (recommended)**

Download a `.mbtiles` file for your region from a tool like [MapTiler](https://www.maptiler.com/) or [mbutil](https://github.com/mapbox/mbutil), then copy it to the Pi:

```bash
# Run this on your PC, replacing the path and IP as needed
scp /path/to/osm.mbtiles pi@pi-mesh.local:~/pi-Mesh/static/tiles/
```

**Option B: PNG tile cache**

Organize tiles as individual files on the Pi:

```
~/pi-Mesh/static/tiles/osm/{z}/{x}/{y}.png
```

The tile server tries MBTiles first and falls back to PNG automatically.

---

## Project Structure

```
pi-Mesh/
├── main.py                  # FastAPI app — routes, WebSocket, lifespan
├── meshtastic_client.py     # Meshtastic serial interface + pubsub bridge
├── database.py              # SQLite via aiosqlite — messages, nodes, telemetry
├── watchdog.py              # Background tasks: DB sync, reconnect, maintenance
├── gpio_handler.py          # Rotary encoders, button gestures, piezo buzzer
├── sensor_handler.py        # I2C sensor drivers (BME280, INA219, etc.)
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

All variables can be set in `config.env.local` (or as environment variables via the systemd `EnvironmentFile`).

| Variable | Default | Description |
|----------|---------|-------------|
| `SERIAL_PORT` | `/dev/ttyMESHTASTIC` | USB serial device for the radio |
| `DB_PERSISTENT` | `/home/pi/pi-Mesh/data/mesh.db` | SD-card path for database persistence |
| `DB_SYNC_INTERVAL` | `300` | Seconds between RAM→SD database syncs |
| `ENC1_A/B/SW` | `23/24/22` | GPIO BCM pins for encoder 1 (tab navigation) |
| `ENC2_A/B/SW` | `5/6/13` | GPIO pins for encoder 2 (scroll/zoom) |
| `BUZZER_PIN` | `0` (disabled) | GPIO pin for piezo buzzer; `0` = off. GPIO 12 (pin 32) recommended — PWM-capable and free |
| `I2C_SENSORS` | `` (empty) | Comma-separated sensor list, e.g. `bme280:0x76,ina219:0x40` |
| `MAP_LAT_MIN/MAX` | `41.0/43.0` | Map bounding box latitude |
| `MAP_LON_MIN/MAX` | `11.5/14.5` | Map bounding box longitude |
| `MAP_ZOOM_MIN/MAX` | `8/12` | Leaflet zoom level limits |
| `DISPLAY_ROTATION` | `0` | Display rotation (0, 90, 180, 270) |
| `UI_THEME` | `dark` | UI theme: `dark`, `light`, or `hc` |

---

## Troubleshooting

**Radio not detected**

```bash
# [Raspberry Pi] Find the actual device name
ls /dev/ttyUSB* /dev/ttyACM*

# Give the pi user serial access (then log out and back in)
sudo usermod -aG dialout pi

# To make the port name stable across reboots, create a udev rule:
# Find the vendor/product ID first:
lsusb   # e.g. "ID 10c4:ea60 Silicon Labs CP210x"

# Then create the rule:
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="ttyMESHTASTIC"' | sudo tee /etc/udev/rules.d/99-meshtastic.rules
sudo udevadm control --reload && sudo udevadm trigger
```

**Display not working**

The Waveshare 3.5" SPI display requires the `LCD-show` driver. Follow [Waveshare's official guide](https://www.waveshare.com/wiki/3.5inch_RPi_LCD_(A)) to install it, then set `DISPLAY_ROTATION` in `config.env.local`.

**Map shows blank tiles**

```bash
# [Raspberry Pi] Verify tile files are in place
ls ~/pi-Mesh/static/tiles/osm.mbtiles        # MBTiles
ls ~/pi-Mesh/static/tiles/osm/10/            # or PNG files at zoom level 10
```

**Out of memory / process killed**

```bash
# [Raspberry Pi] Add compressed swap (run once)
sudo bash ~/pi-Mesh/scripts/setup_zram.sh
```

**No GPIO / encoder input**

```bash
# [Raspberry Pi] Verify python3-lgpio is installed
python3 -c "import lgpio; print('lgpio OK')"

# If that fails, install it:
sudo apt install -y python3-lgpio

# Then recreate the venv so it can see the system package:
cd ~/pi-Mesh
rm -rf venv
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

> **On Raspberry Pi OS Bullseye or older only:** pigpiod is still used. Enable it with:
> ```bash
> sudo systemctl enable --now pigpiod
> ```

**App not starting after reboot**

```bash
# [Raspberry Pi] Check the service logs
journalctl -u meshtastic-pi -n 50 --no-pager
```

**Connect from a location with no Wi-Fi**

```bash
# [Raspberry Pi] Set up the auto-hotspot (requires hostapd + dnsmasq)
sudo apt install -y hostapd dnsmasq
sudo bash ~/pi-Mesh/scripts/auto_ap.sh
```
The Pi will create a Wi-Fi hotspot named `pi-mesh-portal` if it can't connect to a known network within 60 seconds. Connect your phone or PC to it, then open `http://10.42.0.1:8080`.

---

## Optional Features

### I2C Sensors

Connect a supported sensor to the Pi's I2C pins (SDA = GPIO 2 / pin 3, SCL = GPIO 3 / pin 5), then set `I2C_SENSORS` in `config.env.local`:

```env
I2C_SENSORS=bme280:0x76,ina219:0x40
```

Live readings appear in the **Telemetry** tab and are saved to the database.

#### Supported local sensor drivers

| Name | Address | Measures | Python library |
|------|---------|----------|----------------|
| `bme280` | `0x76` / `0x77` | Temp, humidity, pressure | `RPi.bme280` |
| `bme680` | `0x76` / `0x77` | Temp, humidity, pressure, VOC | `bme680` |
| `bmp280` | `0x76` / `0x77` | Temp, pressure | `adafruit-circuitpython-bmp280` |
| `bmp085` / `bmp180` | `0x77` | Temp, pressure (legacy) | `adafruit-circuitpython-bmp085` |
| `sht31` | `0x44` / `0x45` | Temp, humidity | `adafruit-circuitpython-sht31d` |
| `shtc3` | `0x70` | Temp, humidity | `adafruit-circuitpython-shtc3` |
| `mcp9808` | `0x18`–`0x1F` | Temperature (±0.0625 °C) | `adafruit-circuitpython-mcp9808` |
| `lps22hb` | `0x5C` / `0x5D` | Pressure, temp | `adafruit-circuitpython-lps2x` |
| `pmsa003i` | `0x12` | PM1.0, PM2.5, PM10 | `adafruit-circuitpython-pm25` |
| `sen5x` | `0x69` | PM, NOx, VOC, temp, humidity | `sensirion-i2c-sen5x` |
| `veml7700` | `0x10` | Ambient lux | `adafruit-circuitpython-veml7700` |
| `tsl2591` | `0x29` | Lux, IR, visible | `adafruit-circuitpython-tsl2591` |
| `rcwl9620` | `0x13` | Distance (cm) | `adafruit-circuitpython-rcwl9620` |
| `ina219` | `0x40`–`0x4F` | Voltage, current, power | `pi-ina219` |
| `ina260` | `0x40`–`0x4F` | Voltage, current, power | `adafruit-circuitpython-ina260` |
| `ina3221` | `0x40`–`0x43` | 3-channel voltage/current | `adafruit-circuitpython-ina3221` |
| `max17048` | `0x36` | LiPo voltage, state of charge % | `adafruit-circuitpython-max1704x` |

> **Adafruit drivers** (all except `bme280`, `bme680`, `ina219`) require `adafruit-blinka`. See `requirements.txt`.

#### Sensor data from remote nodes

The Meshtastic radio firmware natively supports many of the same sensors. The telemetry it sends over the mesh (visible in the Telemetry tab as `deviceMetrics` / `environmentMetrics`) is received and stored automatically — **no driver needed on the Pi** for remote nodes.

### Piezo Buzzer

Set `BUZZER_PIN` to a GPIO BCM pin number. The buzzer emits:

- **1 short beep** — new text message received
- **2 short beeps** — new node joined the mesh

### Bot Framework

Enable the echo bot from the **Settings** tab or write your own in `bots/`:

```python
# bots/my_bot.py
def start(interface):
    from pubsub import pub
    def on_message(packet, interface):
        if packet["decoded"]["text"].startswith("!"):
            interface.sendText("Received your command!", destinationId=packet["fromId"])
    pub.subscribe(on_message, "meshtastic.receive.text")
```

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

**Free BCM pins** available for encoders, buzzer, and other peripherals:

```
4 (pin 7)   5 (pin 29)  6 (pin 31)  12 (pin 32) ← PWM
13 (pin 33) ← PWM       16 (pin 36) 19 (pin 35) 20 (pin 38)
21 (pin 40) 22 (pin 15) 23 (pin 16) 24 (pin 18) 26 (pin 37)
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

> **[PC/Mac]** Tests run entirely on your PC — no hardware needed.

```bash
git clone https://github.com/<your-username>/pi-Mesh.git
cd pi-Mesh
python3 -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
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

## Creating Custom Themes

The theme system is based on **CSS custom properties**. Each theme is a single CSS class that defines 9 variables.

### Step 1 — Define the CSS variables in `static/style.css`

```css
.theme-forest {
  --bg:       #1b2a1b;   /* main background */
  --bg2:      #243324;   /* cards, inputs, status bar, tab bar */
  --border:   #3a5c3a;   /* dividers and borders */
  --text:     #d4edda;   /* primary text */
  --muted:    #7aab7a;   /* secondary / dimmed text, icons */
  --accent:   #56c56a;   /* active tab, buttons, outgoing message bubbles */
  --ok:       #4caf50;   /* connected badge, online node dot */
  --warn:     #ffc107;   /* recent node dot */
  --danger:   #f44336;   /* disconnected badge, send error */
}
```

### Step 2 — Allow the theme name in `main.py`

```python
# main.py  ~line 203
if theme not in ("dark", "light", "hc", "forest"):   # ← add your theme name here
```

### Step 3 — Set it as default (optional)

```env
# config.env.local
UI_THEME=forest
```

### Step 4 — Add a button in Settings (optional)

```html
<!-- templates/settings.html  ~line 54 -->
<button onclick="setTheme('forest')" style="flex:1; min-height:36px; font-size:12px;">🌲 Forest</button>
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
