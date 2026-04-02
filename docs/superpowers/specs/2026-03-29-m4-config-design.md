# M4 — Config: Design Spec

**Issue:** YAY-149
**Branch:** rework/v2-rewrite
**Date:** 2026-03-29
**Status:** Draft

---

## Obiettivo

Pagina `/config` completa con lettura/scrittura configurazione firmware Meshtastic (nodo, LoRa, canali), gestione periferiche GPIO (I2C sensori, RTC, buzzer, encoder, LED, pulsanti), tema UI e WiFi Pi. Sostituisce il placeholder attuale.

---

## Layout

Sidebar fissa 80px (sinistra) + area contenuto (destra). Funziona su entrambi gli orientamenti senza media query — stesso pattern di `messages.html`.

```
┌────────────────────────────────────────┐
│ statusbar                              │
├─────────┬──────────────────────────────┤
│ Config  │ NODO LOCALE                  │
│ ─────── │ Long name  [pi-mesh-01     ] │
│ Nodo ◀  │ Short name [PM01]            │
│ LoRa    │ Ruolo      [Client        ▾] │
│ Canali  │                              │
│ GPIO    │ [  Salva nodo  ]             │
│ Tema    │ ✓ Salvato · board online     │
│ WiFi    │                              │
├─────────┴──────────────────────────────┤
│ tabbar                                 │
└────────────────────────────────────────┘
```

---

## Database Schema

### Tabella `config_cache` (nuova)

```sql
CREATE TABLE IF NOT EXISTS config_cache (
    section    TEXT NOT NULL,   -- 'node', 'lora', 'channels'
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,   -- JSON serialized
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (section, key)
);
```

### Tabella `gpio_devices` (nuova)

```sql
CREATE TABLE IF NOT EXISTS gpio_devices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type         TEXT NOT NULL,    -- 'i2c_sensor'|'rtc'|'encoder'|'buzzer'|'led'|'button'
    name         TEXT NOT NULL,
    enabled      INTEGER DEFAULT 1,
    pin_a        INTEGER,          -- GPIO BCM pin A (o SDA per I2C)
    pin_b        INTEGER,          -- GPIO BCM pin B (SCL per I2C, DT per encoder)
    pin_sw       INTEGER,          -- GPIO pulsante encoder (opzionale)
    i2c_bus      INTEGER DEFAULT 1,-- bus I2C (default 1)
    i2c_address  TEXT,             -- es. '0x76'
    sensor_type  TEXT,             -- 'BME280'|'BMP180'|'SHT31'|'DS3231'|'SSD1306'|…
    action       TEXT,             -- azione encoder: 'scroll_messages'|'change_channel'|…
    config_json  TEXT DEFAULT '{}'
);
```

### Funzioni database (`database.py`)

```python
async def get_config_cache(db_path, section) -> dict
async def set_config_cache(db_path, section, data: dict) -> None
async def get_gpio_devices(db_path) -> list[dict]
async def add_gpio_device(db_path, device: dict) -> int
async def update_gpio_device(db_path, device_id: int, device: dict) -> None
async def delete_gpio_device(db_path, device_id: int) -> None
```

---

## Backend — `meshtasticd_client.py`

### Lettura config (live + cache)

```python
async def get_node_config(db_path: str) -> dict:
    """Legge da board se connessa, aggiorna cache, ritorna cache se offline."""

async def get_lora_config(db_path: str) -> dict:
    """Idem per config LoRa."""

async def get_channels(db_path: str) -> list[dict]:
    """Idem per lista canali."""
```

Lettura board via `run_in_executor`: `_interface.localNode.localConfig.device`, `.lora`, e `_interface.localNode.channels`. Se `_connected` è False o eccezione → ritorna `config_cache`.

Risposta include flag `"cached": true` se la board è offline.

### Scrittura config (command queue)

```python
async def set_node_config(long_name: str, short_name: str, role: str) -> None:
    await _command_queue.put(lambda: (
        _interface.localNode.setOwner(long_name, short_name),
        _interface.localNode.setConfig(...)
    ))

async def set_lora_config(region: str, preset: str) -> None:
async def set_channel(idx: int, name: str, psk_hex: str) -> None:
```

---

## Backend — `routers/config_router.py` (nuovo)

```
GET  /config                          → TemplateResponse('config.html')
GET  /api/config/node                 → get_node_config()
POST /api/config/node                 → set_node_config()
GET  /api/config/lora                 → get_lora_config()
POST /api/config/lora                 → set_lora_config()
GET  /api/config/channels             → get_channels()
POST /api/config/channels/{idx}       → set_channel()

GET  /api/config/gpio                 → get_gpio_devices()
POST /api/config/gpio                 → add_gpio_device()
PUT  /api/config/gpio/{id}            → update_gpio_device()
DELETE /api/config/gpio/{id}          → delete_gpio_device()
POST /api/config/gpio/{id}/test       → test_gpio_device() — live
GET  /api/config/i2c-scan             → i2cdetect -y {bus} → lista indirizzi

GET  /api/config/wifi/scan            → nmcli dev wifi list
POST /api/config/wifi/connect         → {"ssid", "password"} → nmcli connect
```

### `/api/config/gpio/i2c-scan`

```python
import subprocess
result = subprocess.run(['i2cdetect', '-y', str(bus)], capture_output=True, text=True)
# parsing output → lista {"address": "0x76", "known_device": "BME280"}
```

Lookup table indirizzi noti:
- `0x76` / `0x77` → BME280 / BMP280
- `0x68` / `0x6F` → DS3231 / DS1307
- `0x3C` / `0x3D` → SSD1306
- `0x44` / `0x45` → SHT31
- `0x38` → AHT20
- `0x40` → HTU21D

### `/api/config/gpio/{id}/test`

- **buzzer**: `GPIO.output(pin, HIGH)`, sleep 0.2s, `GPIO.output(pin, LOW)`
- **led**: toggle ON/OFF
- **i2c_sensor / rtc**: legge un registro via smbus2, ritorna `{"ok": true, "value": ...}`
- **encoder**: ritorna stato pin A/B corrente

### Pin riservati sistema (non bloccanti, solo warning)

- 2/3 → I2C1 (SDA/SCL)
- 14/15 → UART (TX/RX)
- 9/10/11 → SPI

---

## Backend — `routers/placeholders.py`

Rimuovere la route `/config` (ora gestita da `config_router`).

---

## Backend — `main.py`

```python
from routers import config_router
app.include_router(config_router.router)
```

---

## Frontend — `templates/config.html`

### Alpine.js component `configPage()`

```javascript
{
  section: 'node',          // sezione attiva sidebar
  node: {},                 // dati nodo
  lora: {},                 // dati LoRa
  channels: [],             // lista canali
  gpio: [],                 // lista dispositivi GPIO
  nodeCached: false,        // true se dati da cache (board offline)
  loraCached: false,

  // GPIO modal
  showAddGpio: false,
  gpioStep: 'type',         // 'type' | 'form'
  gpioForm: {},             // dati form nuovo dispositivo
  i2cScanResults: [],       // risultati scan I2C
  i2cScanning: false,

  // Pin selector
  get usedPins() { ... },   // set di pin già usati da altri dispositivi

  saving: {},               // { node: false, lora: false, ... }
  status: {},               // { node: '', lora: '', ... }

  async init() { await this.loadSection('node') },
  async loadSection(s) { ... },
  async saveNode() { ... },
  async saveLora() { ... },
  async saveChannel(idx) { ... },
  async scanI2C(bus) { ... },
  async saveGpioDevice() { ... },
  async testGpioDevice(id) { ... },
  async deleteGpioDevice(id) { ... },
  async scanWifi() { ... },
  async connectWifi() { ... },
}
```

### Pin selector custom

Dropdown Alpine.js (non `<select>` nativo) con lista GPIO BCM 2–27:
- Pin libero → colore normale
- Pin usato → sfondo rosso scuro, etichetta con nome dispositivo, cliccabile con warning
- Pin riservato sistema → sfondo arancione, etichetta "riservato"
- Pin selezionato → sfondo blu, checkmark

### I2C Scan flow

1. Utente preme "🔍 Scan" → `POST /api/config/gpio/i2c-scan?bus=1`
2. Risultati mostrati come chip cliccabili: `0x76 BME280`
3. Click chip → popola campo address + seleziona modello nel dropdown
4. Utente può comunque digitare address manualmente

### Tema UI

Gestito interamente in `localStorage` — nessuna chiamata backend. Stessa logica già presente in `settings.html`, portata in Alpine.js.

### Stato board offline

Ogni sezione Meshtastic (Nodo, LoRa, Canali) mostra badge:
- `● board online` (verde) — dati live
- `◌ dati dalla cache` (grigio) — board disconnessa, input abilitati ma salvataggio disabilitato con tooltip "Board non connessa"

---

## Testing

### `tests/test_config.py` (nuovo)

```python
test_config_cache_set_and_get()        # set + get per sezione 'node'
test_config_cache_overwrites()         # doppio set → ultimo valore
test_gpio_device_crud()                # add, get, update, delete
test_gpio_used_pins()                  # verifica pin conflict detection lato DB
```

### `tests/test_api.py` (aggiunta)

```python
test_get_node_config_endpoint()        # GET /api/config/node → 200
test_post_node_config_endpoint()       # POST con board mockkata
test_get_lora_config_endpoint()        # GET /api/config/lora → 200
test_get_gpio_devices_endpoint()       # GET /api/config/gpio → lista
test_add_gpio_device_endpoint()        # POST /api/config/gpio → 201
test_delete_gpio_device_endpoint()     # DELETE → 204
test_i2c_scan_endpoint()               # GET /api/config/i2c-scan — subprocess mockato
```

Nessun test hardware per GPIO fisico, WiFi nmcli — troppo dipendenti dall'ambiente reale.

---

## File modificati / creati

| File | Tipo | Note |
|------|------|------|
| `database.py` | modifica | + `config_cache`, `gpio_devices`, 6 funzioni async |
| `meshtasticd_client.py` | modifica | + get/set node/lora/channels config |
| `routers/config_router.py` | nuovo | tutti gli endpoint config |
| `routers/placeholders.py` | modifica | rimuovi route `/config` |
| `main.py` | modifica | include config_router |
| `templates/config.html` | nuovo | Alpine.js configPage(), sidebar + sezioni |
| `tests/test_config.py` | nuovo | 4 test DB |
| `tests/test_api.py` | modifica | + 7 test endpoint |

`settings.html` viene **mantenuto** per ora (non collegato a nessuna route attiva) — può essere rimosso dopo M4 completato e testato.

---

## Decisioni chiave

- Config board (nodo/LoRa/canali) cached in SQLite — pagina funziona anche offline
- `cached: true` flag nella risposta API — frontend mostra badge diverso e disabilita salvataggio
- GPIO config in `gpio_devices` SQLite — struttura dati ricca, facile da evolvere per M5 (metriche sensori)
- I2C scan via `i2cdetect -y 1` (subprocess) + lookup table indirizzi noti → UX semplificata
- Pin selector custom (non `<select>`) — unico modo per colorare le opzioni con conflitti
- Pin riservati sistema (I2C/UART/SPI) mostrati in arancione, warning non bloccante
- Tema UI in `localStorage` — zero backend, zero DB
- WiFi via `nmcli` — richiede NetworkManager sul Pi (standard su Bookworm)
