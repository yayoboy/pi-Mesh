# pi-Mesh: Funzionalità Meshtastic mancanti — Design Spec

**Data:** 2026-04-04  
**Linear:** YAY-168, YAY-169, YAY-170, YAY-171  
**Approccio architetturale:** B — nuovi router per feature area (pattern esistente)

---

## Contesto

Il progetto pi-Mesh v2 gestisce i portnums principali di Meshtastic (NODEINFO, POSITION, TELEMETRY, TEXT_MESSAGE, ROUTING, TRACEROUTE). Questa spec definisce le 4 milestone per coprire le funzionalità mancanti, ordinate per complessità crescente.

---

## Architettura generale

### Nuovi file

```
routers/canned_router.py          ← M7
routers/module_config_router.py   ← M8
routers/waypoints_router.py       ← M9
routers/neighbor_router.py        ← M9
routers/admin_router.py           ← M10
```

### File modificati

| File | Modifiche |
|---|---|
| `meshtasticd_client.py` | +6 handler portnum, +6 WS event types |
| `database.py` | +4 tabelle |
| `main.py` | +5 router include |
| `templates/config.html` | +9 sezioni moduli, +sezione Canned Messages |
| `templates/messages.html` | +pulsante ⚡ + modal canned messages |
| `templates/nodes.html` | +tab Remote Admin nel popup nodo |
| `templates/map.html` | +tab Topology nel pannello laterale |
| `static/map.js` | +waypoints layer, +neighbor topology overlay, +grafo SVG |

### Nuove tabelle DB

```sql
-- M7
CREATE TABLE canned_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);

-- M9
CREATE TABLE waypoints (
    id INTEGER PRIMARY KEY,          -- waypoint ID da pacchetto
    name TEXT,
    lat REAL,
    lon REAL,
    icon TEXT,
    description TEXT,
    expire INTEGER,                  -- Unix timestamp scadenza
    from_id TEXT,
    ts INTEGER
);

CREATE TABLE neighbor_info (
    from_id TEXT,
    neighbor_id TEXT,
    snr REAL,
    ts INTEGER,
    PRIMARY KEY (from_id, neighbor_id)
);

CREATE TABLE sensor_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER,
    from_id TEXT,
    type TEXT,                       -- 'detection' | 'paxcounter'
    data_json TEXT
);
```

---

## M7 — Canned Messages (YAY-168)

**Stima:** ~150 righe | **Priorità:** più veloce da implementare

### Funzionalità

- Pulsante ⚡ (icona) nella barra messaggi, apre modal Alpine.js
- Tap su un messaggio nel modal → inviato al canale/DM corrente → modal chiuso
- Lista configurabile in `/config` nuova sezione "Canned Messages"
- CRUD: aggiungi, modifica, riordina (drag o frecce), elimina

### API

```
GET  /api/canned-messages           → [{id, text, sort_order}]
POST /api/canned-messages           → {text}
PUT  /api/canned-messages/{id}      → {text, sort_order}
DELETE /api/canned-messages/{id}
```

### UI — messages.html

- Pulsante ⚡ accanto al campo testo (solo icona, no label)
- Modal Alpine.js inline (no `confirm()` nativo) con lista scrollabile
- Tap su item → chiama `sendMessage(text)` esistente

### UI — config.html

- Nuova sezione accordion "Canned Messages"
- Lista con pulsanti +/- e campo testo inline
- Salvataggio immediato su modifica (POST/PUT/DELETE singolo item)

---

## M8 — Configurazione moduli board (YAY-169)

**Stima:** ~600 righe | **Pattern:** identico a sezioni LoRa/WiFi/MQTT esistenti

### Moduli e campi

| Modulo | Campi principali |
|---|---|
| External Notifications | enabled, output_pin, active_high, alert_message, alert_bell |
| Store & Forward | enabled, history_return_max, history_return_window, heartbeat |
| Telemetry | device_update_interval, environment_update_interval, environment_measurement_enabled, air_quality_enabled, power_measurement_enabled |
| Canned Messages (board) | rotary1_enabled, free_text_sms_enabled, send_bell |
| Range Test | enabled, sender, save |
| Detection Sensor | enabled, minimum_broadcast_secs, state_broadcast_secs, name, monitor_pin, use_pullup |
| Ambient Lighting | led_state, current, red, green, blue, led_count, pin |
| Neighbor Info | update_interval |
| Serial | enabled, echo, rxd, txd, timeout, mode, override_console_serial_port |

### API pattern (per ogni modulo)

```
GET  /api/config/module/{module_name}    → {fields...}
POST /api/config/module/{module_name}    → {fields...}
```

Usa `meshtastic_client.localNode.getModuleConfig(name)` e `setModuleConfig(name, cfg)`.

### UI

- 9 nuove sezioni accordion in `config.html` dopo le sezioni esistenti
- Form fields: toggle switch per `enabled`, input numerico per intervalli, input testo per nomi/pin
- Pulsante "Salva" per sezione (pattern identico a LoRa/WiFi)

---

## M9 — Nuovi pacchetti (YAY-170)

**Stima:** ~500 righe | **Portnums:** WAYPOINT_APP, NEIGHBOR_INFO_APP, DETECTION_SENSOR_APP, PAXCOUNTER_APP

### WAYPOINT_APP

**Handler `meshtasticd_client.py`:**
- Estrae: `waypoint.id`, `name`, `latitudeI`/`longitudeI` (÷1e7), `icon`, `description`, `expire`
- Salva in tabella `waypoints` (upsert per ID)
- Emette WS event type: `waypoint`

**Router `waypoints_router.py`:**
```
GET  /api/waypoints              → lista waypoint attivi (expire > now)
POST /api/waypoints/send         → {name, lat, lon, icon, description, expire_hours}
DELETE /api/waypoints/{id}
```

**Map layer (`map.js`):**
- Layer Leaflet separato "Waypoints" (toggle nel pannello filtri esistente)
- Marker con emoji icona, popup con nome/descrizione/scadenza
- Click su mappa vuota → form modal "Aggiungi waypoint" con campi: nome, descrizione, icona (select emoji), scade (ore)
- Tab "Waypoints" nel pannello laterale mappa con lista

**WS handling:** evento `waypoint` aggiorna layer real-time

### NEIGHBOR_INFO_APP

**Handler `meshtasticd_client.py`:**
- Estrae `neighbors[]` (node_id, snr)
- Upsert in tabella `neighbor_info`
- Emette WS event type: `neighbor_info`

**Router `neighbor_router.py`:**
```
GET  /api/neighbor-info          → [{from_id, neighbor_id, snr, ts}]
```

**Map overlay (`map.js`):**
- Layer "Neighbor Links": linee colorate per SNR (verde >5dB, arancione 0-5dB, rosso <0dB)
- Toggle nel pannello filtri (checkbox esistente)
- Aggiornamento real-time via WS

**Tab Topology (pannello laterale mappa):**
- Nuova tab "Topology" nel pannello laterale esistente
- Grafo SVG generato client-side: nodi = cerchi, link = linee con label SNR
- Nodo locale evidenziato in blu
- Auto-layout semplice (force-directed manuale, no librerie esterne — RAM tight)

### DETECTION_SENSOR_APP

**Handler:**
- Estrae: `detectionSensor.triggered` (bool), nome sensore
- Salva in `sensor_events` (type='detection')
- Emette WS event type: `sensor`

**Log summary:** `_build_log_summary` esteso — "⚡ Triggered" / "✓ Cleared" + nome sensore

**Display:** evento colorato nel log (rosso=triggered, verde=cleared)

### PAXCOUNTER_APP

**Handler:**
- Estrae: `paxcounter.ble`, `paxcounter.wifi`
- Salva in `sensor_events` (type='paxcounter')
- Emette WS event type: `paxcounter`

**Log summary:** "BLE: N · WiFi: M"

**Metrics:** se nodo ha eventi paxcounter, mostra contatori nell'espansione nodo nella pagina metrics

---

## M10 — Remote Admin (YAY-171)

**Stima:** ~300 righe | **Complessità:** più alta — richiede test su hardware reale

### Sicurezza

- meshtastic-python espone `localNode.sendAdmin(destNum, adminMessage)` per admin autenticato
- Admin key configurabile in `/config → Device` (campo esistente o nuovo)
- UI mostra warning se admin key non configurata (operazioni base funzionano via canale condiviso)
- Factory Reset protetto da modal doppia conferma

### Operazioni

| Operazione | Tipo | API |
|---|---|---|
| Request Position | diagnostica | `POST /api/admin/{node_id}/request-position` |
| Request Telemetry | diagnostica | `POST /api/admin/{node_id}/request-telemetry` |
| Reboot | moderata | `POST /api/admin/{node_id}/reboot` |
| Set Config | moderata | `POST /api/admin/{node_id}/set-config` + body |
| Factory Reset | distruttiva | `POST /api/admin/{node_id}/factory-reset` |

### UI — tab Admin nel popup nodo (`nodes.html`)

- Nuova tab "🔧 Admin" (ultima tab nel popup nodo)
- Sezioni:
  - **Diagnostica:** Request Position, Request Telemetry (sempre disponibili)
  - **Controllo:** Reboot, Set Config (arancione, con conferma modal)
  - **Distruttivo:** Factory Reset (rosso, doppia conferma: "Sei sicuro?" → "Scrivi RESET")
- Warning banner se admin key non configurata con link a /config
- Area feedback: mostra ACK ricevuto o timeout (10s) via WS

### Router `admin_router.py`

```python
POST /api/admin/{node_id}/request-position
POST /api/admin/{node_id}/request-telemetry
POST /api/admin/{node_id}/reboot
POST /api/admin/{node_id}/set-config       # body: {config_type, fields}
POST /api/admin/{node_id}/factory-reset
```

Tutti usano `await meshtasticd_client.send_admin(node_id, operation, payload)`.

---

## Ordine di implementazione

1. **M7** — Canned Messages (~1 sessione)
2. **M8** — Module configs (~2 sessioni, ripetitivo)
3. **M9** — Nuovi pacchetti (~2-3 sessioni)
4. **M10** — Remote Admin (~1-2 sessioni + test hardware)

---

## Vincoli e note

- **RAM:** Pi 3A+ 416MB, swap 64% — evitare librerie JS pesanti (no D3.js per topology, grafo SVG custom)
- **DB:** colonna messaggi è `ts` (non `timestamp`) — attenzione nelle query
- **Modal:** mai `confirm()` nativo — sempre modal Alpine.js inline (feedback_pinesui_no_native_dialogs)
- **Deploy:** rsync + systemctl restart pimesh, cache-busting ?v=N su asset statici
- **SPA:** tab navigation con innerHTML replace + reexecScripts + Alpine.initTree()
