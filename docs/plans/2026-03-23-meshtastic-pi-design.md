# Meshtastic Pi — Design Document

**Data:** 2026-03-23
**Stato:** Approvato
**Riprendibilità:** Ogni milestone e ogni step è autonomo. Consulta `PROGRESS.md` nella root del progetto per sapere esattamente dove sei.

---

## 1. Panoramica del progetto

Applicazione Python/FastAPI per Raspberry Pi che funge da nodo Meshtastic con interfaccia web locale. Parità funzionale con l'app Meshtastic per iOS/Android, ottimizzata per display touchscreen SPI 3.5" e controllo fisico tramite rotary encoder.

**Obiettivi chiave:**
- Funzionamento completamente offline (nessuna connessione internet richiesta)
- Bassa RAM (target < 150MB), SD card protetta da scritture excessive
- Riavvio automatico garantito da systemd
- Riprendibilità totale: il lavoro può essere interrotto e ripreso in qualsiasi momento

---

## 2. Hardware target

| Componente | Dettagli |
|---|---|
| SBC | Raspberry Pi 3B+ / 4 / Zero 2W |
| Radio LoRa | Heltec V3 → USB seriale `/dev/ttyMESHTASTIC` (udev symlink) |
| Display | Waveshare 3.5" Type B SPI, 480×320 landscape / 320×480 portrait |
| Touch | XPT2046 resistive touch → `/dev/input/eventX` (calibrato con `xinput_calibrator`) |
| Encoder 1 | Rotary encoder GPIO (17, 27) + button (22) → navigazione tab globale |
| Encoder 2 | Rotary encoder GPIO (5, 6) + button (13) → azione contestuale al tab attivo |
| Sensori I2C | BME280 (temp/umidità/pressione), INA219 (corrente/tensione), BMP390, SHT31 (opzionali) |

### Display — orientamento doppio

Il display Waveshare 3.5" supporta entrambe le orientazioni configurabili via `/boot/config.txt`:

```
# Landscape (default): display_rotate=0  → viewport 480×320
# Portrait:            display_rotate=1  → viewport 320×480
```

Il CSS si adatta automaticamente con `@media (orientation: landscape/portrait)`. L'orientamento è impostato in `config.env` (`DISPLAY_ROTATION=0|90`) e applicato al boot.

---

## 3. Architettura software

### Struttura file

```
meshtastic-pi/
├── main.py                  # FastAPI app, orchestratore
├── config.py                # Configurazione da config.env
├── database.py              # SQLite aiosqlite su tmpfs
├── meshtastic_client.py     # Bridge seriale → asyncio
├── gpio_handler.py          # Rotary encoder gpiozero/pigpio
├── sensor_handler.py        # Driver sensori I2C
├── watchdog.py              # Task background (sync DB, RAM, reconnect)
├── templates/
│   ├── base.html            # Layout base + tab bar
│   ├── messages.html        # Chat (parità app mobile)
│   ├── nodes.html           # Lista nodi mesh
│   ├── map.html             # Mappa Leaflet offline
│   ├── telemetry.html       # Grafici Chart.js telemetria + sensori
│   └── settings.html        # Config nodo + temi + GPIO/I2C + admin remoto
├── static/
│   ├── app.js               # WebSocket client, encoder handler, navigazione
│   ├── style.css            # CSS responsive dual-orientation + temi
│   ├── leaflet.min.js       # Mappa offline
│   ├── chart.min.js         # Grafici telemetria
│   └── tiles/
│       ├── osm/             # Tile stradali pre-scaricate
│       └── topo/            # Tile topografiche pre-scaricate
├── data/
│   └── mesh.db              # DB persistente sulla SD (mai aperto direttamente)
├── config.env               # Configurazione (letta da systemd e da config.py)
├── meshtastic-pi.service    # Unit systemd
├── PROGRESS.md              # Stato avanzamento lavoro (aggiornato manualmente)
└── requirements.txt         # Dipendenze Python
```

### Flusso dati

```
[Heltec V3 seriale]
        │ meshtastic-python pubsub callbacks (thread separati)
        │ run_coroutine_threadsafe()
        ▼
[event loop asyncio uvicorn]
        │
        ├──► database.py  → aiosqlite → /tmp/mesh_runtime.db
        │                               └── sync periodica → SD/mesh.db
        │
        └──► broadcast() → WebSocket → [Surf browser /dev/fb1]
                                              │
                                    [app.js handler]
                                              │
                                    ┌─────────┴──────────┐
                              touch XPT2046        encoder WebSocket events
                              (input HTML5)        {"type":"encoder",...}
```

### Modello di concorrenza

- **Event loop asyncio** (uvicorn, single thread): tutto il codice `await`
- **Thread meshtastic-python**: callback pubsub → bridge con `asyncio.run_coroutine_threadsafe()`
- **Thread gpiozero/pigpio**: callback encoder → stesso bridge
- **ws_clients (set)**: modificato solo nell'event loop → no lock necessari
- **Regola fondamentale**: mai chiamare `asyncio.run()` in un callback — crea un loop separato incompatibile con uvicorn

---

## 4. Database

### Strategia SD-safe

Il DB sulla SD (`data/mesh.db`) è la copia persistente. **Non viene mai aperto direttamente durante l'esecuzione.**

Al boot: `shutil.copy2(DB_PERSISTENT, /tmp/mesh_runtime.db)`
Durante l'uso: tutte le operazioni su `/tmp/mesh_runtime.db` (tmpfs, RAM)
Sync periodica (ogni 300s) e a shutdown: copia atomica con `os.replace()` (ext4-safe)

### Schema

**messages** — messaggi testo ricevuti e inviati
**nodes** — nodi mesh conosciuti (INSERT OR REPLACE su id)
**telemetry** — telemetria nodi (max 500 righe per nodo per tipo, pruning orario)
**sensor_readings** — letture sensori I2C locali

Tutte le SELECT usano LIMIT esplicito. SQLite configurato con WAL + 4MB cache + temp_store=MEMORY.

---

## 5. API

### HTTP

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/` | Redirect → `/messages` |
| GET | `/messages` | Pagina messaggi |
| GET | `/nodes` | Pagina nodi |
| GET | `/map` | Pagina mappa |
| GET | `/telemetry` | Pagina telemetria |
| GET | `/settings` | Pagina impostazioni |
| POST | `/send` | Invia messaggio mesh |
| POST | `/settings` | Applica configurazione nodo |
| GET | `/api/nodes` | JSON lista nodi |
| GET | `/api/messages` | JSON messaggi (paginati) |
| GET | `/api/telemetry/{node_id}/{type}` | JSON telemetria |
| GET | `/api/status` | JSON stato sistema (RAM, connessione) |
| POST | `/api/keyboard/show` | Mostra matchbox-keyboard |
| POST | `/api/keyboard/hide` | Nascondi tastiera |

### WebSocket `/ws`

**Server → Client (tipi messaggi):**

| type | payload | quando |
|------|---------|--------|
| `init` | `{connected, nodes[], messages[]}` | Al connect |
| `message` | oggetto messaggio | Nuovo messaggio ricevuto |
| `node` | oggetto nodo | Aggiornamento nodeinfo |
| `position` | `{node_id, lat, lon, alt}` | Aggiornamento posizione |
| `telemetry` | `{node_id, type, values}` | Telemetria nodo |
| `sensor` | `{sensor, values}` | Lettura sensore I2C |
| `encoder` | `{encoder, action, ts}` | Evento rotary encoder |
| `status` | `{connected, ram_mb, warning?}` | Stato sistema |

---

## 6. Frontend

### CSS — dual-orientation responsive

```css
/* Landscape 480×320 (default) */
body { width: 480px; height: 320px; }
#content { height: calc(320px - 20px - 48px); }  /* 252px */

@media (orientation: portrait) {
  /* Portrait 320×480 */
  body { width: 320px; height: 480px; }
  #content { height: calc(480px - 20px - 48px); }  /* 412px */
}
```

### Temi UI

Variabili CSS in `:root` per tema dark (default), light, e opzionalmente high-contrast. Il tema attivo viene salvato in `config.env` (`UI_THEME=dark|light|hc`) e applicato via classe `<body class="theme-dark">`.

### Navigazione

- **Encoder 1** (globale): CW/CCW → cambio tab, long_press → torna a messages
- **Encoder 2** (contestuale): scroll in messages/nodes, zoom in map, selezione in settings
- **Touch XPT2046**: tap su tab bar, scroll lista, zoom mappa (pinch non supportato su 3.5")
- **Navigazione senza reload**: `fetch()` + innerHTML swap — WebSocket rimane connesso

### Mappa Leaflet

- Tile URL: `/tiles/osm/{z}/{x}/{y}.png` e `/tiles/topo/{z}/{x}/{y}.png`
- `zoomControl: false` — zoom via encoder/touch buttons
- `maxBounds` da `config.MAP_BOUNDS` — nessun pan fuori dall'area con tile scaricate
- Lazy init: Leaflet viene inizializzato solo quando il tab mappa diventa visibile

---

## 7. Funzionalità — parità app mobile

Le seguenti funzionalità corrispondono a quelle dell'app Meshtastic iOS/Android:

| Funzionalità | Tab | Note |
|---|---|---|
| Chat canali | Messages | Scroll infinito, input + invio |
| DM nodo specifico | Messages | Select destinatario |
| Lista nodi + dettaglio | Nodes | Last heard, battery, SNR, posizione |
| Mappa nodi | Map | Tile offline, marker colorati |
| Telemetria nodi | Telemetry | Grafici SNR, battery, uptime |
| Impostazioni nodo | Settings | Nome, ruolo (Client/Router/Repeater/RepeaterClient) |
| Config LoRa | Settings | Regione, preset modem |
| Gestione canali | Settings | Nome, abilitato, visibilità |
| Admin nodi remoti | Settings → Remote | Invia config a nodo remoto via mesh |
| Config GPIO/I2C | Settings → Hardware | Pin encoder, sensori I2C, orientamento display |

---

## 8. Feature aggiuntive Pi-specific

- **Sensori I2C locali**: BME280/BMP390/INA219/SHT31 — polling ogni 30s, grafici in Telemetry
- **Rotary encoder**: navigazione fisica senza touchscreen
- **Shutdown sicuro**: press lungo simultaneo encoder 1+2 per 3s → sync DB + `shutdown -h now`
- **Matchbox keyboard**: appare automaticamente al focus su input text
- **Framework bot**: architettura plugin — un bot è un modulo Python con `on_message(packet)`. Bot echo incluso come esempio. Attivabili da settings.

---

## 9. Milestone e step

### Come riprendere il lavoro

1. Apri `PROGRESS.md` nella root del progetto
2. Trova l'ultimo step marcato come `[ ]` (non completato)
3. Ogni step ha: obiettivo, file da creare/modificare, test verificabile
4. Completa il test → metti `[x]` nello step → passa al successivo

---

### M1 — Core Backend

**Goal:** Backend funzionante. Dati dalla radio Heltec V3 salvati nel DB.

| ID | Step | File | Test |
|----|------|------|------|
| M1-S1 | `config.py` + `config.env` + `requirements.txt` | `config.py`, `config.env` | `python -c "import config; print(config.SERIAL_PORT)"` stampa il valore corretto |
| M1-S2 | `database.py` — schema + CRUD + sync | `database.py` | Script standalone: crea DB su tmpfs, INSERT messaggio, lettura, `sync_to_sd()`, verifica file sulla SD |
| M1-S3 | `meshtastic_client.py` — connessione seriale + bridge asyncio | `meshtastic_client.py` | Script standalone: pacchetti Heltec V3 stampati su console. Stacca USB → riconnette entro 10s |
| M1-S4 | `watchdog.py` — sync DB, watchdog connessione, RAM, manutenzione | `watchdog.py` | Sync DB: verifica timestamp SD cambia ogni 5min. SIGTERM: sync immediata. RAM > 150MB: processo si riavvia |

---

### M2 — UI Base (parità app mobile core)

**Goal:** App usabile su Surf. Messaggi, nodi, mappa funzionanti su display 480×320 e 320×480.

| ID | Step | File | Test |
|----|------|------|------|
| M2-S1 | `main.py` scheletro + WebSocket + route HTTP base | `main.py` | `websocat ws://localhost:8080/ws` riceve snapshot `{type:"init",...}` con nodi e messaggi |
| M2-S2 | `static/style.css` + `base.html` — layout dual-orientation + temi | `static/style.css`, `templates/base.html` | Apri su Surf landscape e portrait: tab bar visibile, status bar visibile, nessun overflow |
| M2-S3 | `static/app.js` — WebSocket client, handler messaggi, navigazione | `static/app.js` | Messaggi arrivano in tempo reale nel browser. WS si riconnette da solo se cade |
| M2-S4 | `templates/messages.html` — lista messaggi + form invio + tastiera matchbox | `templates/messages.html` | Su Surf: messaggi ricevuti appaiono, focus su input → matchbox appare, invio → messaggio nella mesh |
| M2-S5 | `templates/nodes.html` — lista nodi live + dettaglio | `templates/nodes.html` | Lista aggiornata quando arriva nodeinfo. Tap nodo → dettaglio con hardware/posizione/battery |
| M2-S6 | `templates/map.html` + tile offline Leaflet | `templates/map.html`, `static/tiles/` | Mappa carica senza internet. Marker nodi nelle posizioni corrette. Zoom funziona via touch |

---

### M3 — UI Estesa

**Goal:** Telemetria, settings, temi, config hardware da UI.

| ID | Step | File | Test |
|----|------|------|------|
| M3-S1 | `gpio_handler.py` — encoder CW/CCW/press/long_press + bridge asyncio | `gpio_handler.py` | Script standalone: tutti gli eventi encoder stampati su console. Integrato: CW/CCW cambiano tab nel browser |
| M3-S2 | `sensor_handler.py` — driver I2C + polling | `sensor_handler.py` | `i2cdetect -y 1` mostra i sensori. Script standalone: valori stampati. Integrato: dati arrivano via WebSocket |
| M3-S3 | `templates/telemetry.html` — grafici Chart.js nodi + sensori | `templates/telemetry.html` | Grafici SNR e battery si aggiornano live. Sezione sensori I2C mostra valori numerici. Funziona in entrambe le orientazioni |
| M3-S4 | `templates/settings.html` — config nodo base (nome, ruolo, LoRa, canali) | `templates/settings.html` | Modifica nome nodo → Heltec aggiornata. Cambio ruolo → confermato in nodeinfo |
| M3-S5 | Temi UI — light/dark/high-contrast | `static/style.css`, `templates/settings.html`, `config.py` | Switch tema da settings → cambia istantaneamente. Persiste dopo riavvio (salvato in `config.env`) |
| M3-S6 | Config GPIO/I2C da UI — form in settings | `templates/settings.html`, `gpio_handler.py`, `sensor_handler.py` | Cambia pin encoder da UI → riavvia handler GPIO senza restart uvicorn. Aggiungi sensore I2C → polling parte |

---

### M4 — Feature Avanzate

**Goal:** Admin remoto, configurazioni avanzate nodo, framework bot.

| ID | Step | File | Test |
|----|------|------|------|
| M4-S1 | Admin nodi remoti — invia config a nodo remoto via mesh | `templates/settings.html`, `meshtastic_client.py` | Seleziona nodo remoto da lista → invia `set_config` → ricevi ACK o timeout |
| M4-S2 | Configurazioni nodo avanzate — Client/Router/Repeater/RepeaterClient + preset LoRa | `templates/settings.html`, `meshtastic_client.py` | Tutti i ruoli configurabili come nell'app mobile. Preset LoRa aggiornano la radio |
| M4-S3 | Framework bot — architettura plugin + bot echo | `bots/`, `bots/echo_bot.py`, `main.py` | Bot echo risponde a ogni messaggio ricevuto su canale configurato. Attivabile/disattivabile da settings |
| M4-S4 | Collaudo completo | tutti | Boot autonomo senza SSH. Stacco corrente → DB integro alla ripresa. Tutti i tab funzionanti. Entrambe le orientazioni. Gesture shutdown encoder |

---

## 10. Dipendenze Python (`requirements.txt`)

```
fastapi
uvicorn[standard]
meshtastic
pypubsub
aiosqlite
gpiozero
smbus2
```

Dipendenze sistema (installate via apt):
```
pigpio         # backend GPIO preciso
matchbox-keyboard  # tastiera on-screen
surf           # browser WebKit leggero per display SPI
xinput         # calibrazione touch XPT2046
```

---

## 11. Deployment (`meshtastic-pi.service`)

```ini
[Unit]
Description=Meshtastic Pi Backend
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
User=pi
Group=pi
WorkingDirectory=/home/pi/meshtastic-pi
ExecStart=/home/pi/meshtastic-pi/venv/bin/uvicorn main:app \
    --host 127.0.0.1 \
    --port 8080 \
    --workers 1 \
    --log-level warning
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=10
EnvironmentFile=/boot/firmware/config.env
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPYCACHEPREFIX=/tmp/pycache
Environment=XDG_CACHE_HOME=/tmp/cache
MemoryMax=200M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
```

`--host 127.0.0.1`: il servizio è raggiungibile solo da localhost (Surf), non dall'esterno.
`MemoryMax=200M`: backstop finale (watchdog interno interviene a 150MB).
`Restart=always`: riavvio automatico in entrambi i casi (watchdog interno + systemd).

---

## 12. File `PROGRESS.md` (template iniziale)

```markdown
# Meshtastic Pi — Progress

Aggiorna questo file dopo ogni step completato.
Formato: [x] completato, [ ] da fare, [~] in corso

## M1 — Core Backend
- [ ] M1-S1 config.py + config.env + requirements.txt
- [ ] M1-S2 database.py
- [ ] M1-S3 meshtastic_client.py
- [ ] M1-S4 watchdog.py

## M2 — UI Base
- [ ] M2-S1 main.py scheletro + WebSocket
- [ ] M2-S2 style.css + base.html dual-orientation
- [ ] M2-S3 app.js WebSocket client
- [ ] M2-S4 messages.html
- [ ] M2-S5 nodes.html
- [ ] M2-S6 map.html + tile offline

## M3 — UI Estesa
- [ ] M3-S1 gpio_handler.py
- [ ] M3-S2 sensor_handler.py
- [ ] M3-S3 telemetry.html
- [ ] M3-S4 settings.html base
- [ ] M3-S5 temi UI
- [ ] M3-S6 config GPIO/I2C da UI

## M4 — Feature Avanzate
- [ ] M4-S1 admin nodi remoti
- [ ] M4-S2 config nodo avanzata
- [ ] M4-S3 framework bot
- [ ] M4-S4 collaudo completo
```
