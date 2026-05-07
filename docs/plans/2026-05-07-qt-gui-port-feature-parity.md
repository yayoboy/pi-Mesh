# pi-Mesh — Qt GUI Port: Feature Parity Matrix

> **Vincolo non negoziabile**: la GUI Qt deve esporre **tutte** le funzionalità presenti nella UI web attuale. Questo documento è la lista esaustiva. Ogni riga deve risultare `✅ Done` prima della release (Fase 9.1).

**Data:** 2026-05-07
**Branch:** `claude/web-vs-gui-performance-eTgh0`
**Documenti correlati:** `2026-05-07-qt-gui-port-design.md`, `2026-05-07-qt-gui-port-implementation.md`

---

## 0. Convenzioni

- **Stato**: `[ ]` da fare · `[~]` in corso · `[x]` portato + testato manualmente · `✅ Done` portato + test automatico passa.
- **Task**: riferimento al task del piano di implementazione che porta la feature.
- **Endpoint web**: l'endpoint REST/HTML attualmente usato dalla UI web (resterà attivo per accesso remoto).
- **Sostituto Qt**: come la GUI Qt fornisce la stessa funzionalità (di solito chiamata diretta a `meshtasticd_client` / `database` / subprocess).

> Se trovi una feature usata in produzione che non è in questo elenco, **aggiungila** prima di iniziare il porting. Non scartare nulla senza esplicita conferma.

---

## 1. Cornice globale (sempre visibile)

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| C1 | Status bar — nome nodo locale | `meshtasticd_client.get_local_node()` | diretto | 1.5 | [ ] |
| C2 | Status bar — badge batteria (icona dinamica con livello) | WS `rpi_telemetry` | segnale `rpi_telemetry` → `QPainter` | 1.5 | [ ] |
| C3 | Status bar — indicatore connessione meshtasticd | `meshtasticd_client.is_connected()` | polling 1 Hz | 1.5 | [ ] |
| C4 | Status bar — indicatore RAM/CPU/temp Pi | WS `rpi_telemetry` | segnale | 1.5 | [ ] |
| C5 | Status bar — orologio | (lato client) | `QTimer(1000)` | 1.5 | [ ] |
| C6 | Status bar — bottone modal sistema (reboot/shutdown/screenshot/factory-reset) | `POST /api/system/{reboot,shutdown,factory-reset}`, `POST /api/screenshot` | dialog Qt | 1.5+4.17 | [ ] |
| C7 | Status bar — selettore rotazione display (0/90/180/270) | `GET/POST /api/config/display` | salva su DB + restart | 1.5+4.16 | [ ] |
| C8 | Tab bar — 6 tab: Nodi, Mappa, Msg, Config, Metriche, Log | client-side routing | `QStackedWidget` + `QButtonGroup` | 1.5 | [ ] |
| C9 | Tab Msg — badge "non letti" (rosso, contatore) | `GET /api/messages/unread-count` | segnale `message_received` | 1.5+2.2 | [ ] |
| C10 | Cambio tema runtime (dark/light/hc/custom) | `POST /api/set-theme` (lato client localStorage) | `app.apply_theme()` | 1.6 | [ ] |
| C11 | Tastiera virtuale (auto-show su input focus) | client-side `vkbd.js` | `gui/widgets/vkbd.py` | Fase 5 | [ ] |
| C12 | Tastiera virtuale — comandi server `/api/keyboard/{show,hide}` | endpoint REST | bypass (event filter Qt) | Fase 5 | [ ] |

---

## 2. Pagina Nodi

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| N1 | Lista nodi con segnale, batteria, last heard | `GET /api/nodes` + WS `node`, `position`, `telemetry` | `meshtasticd_client.get_nodes()` + EventBus | 2.1 | [ ] |
| N2 | Filtro testuale | client-side | `QSortFilterProxyModel` | 2.1 | [ ] |
| N3 | Dettaglio nodo espandibile (info statiche + telemetria recente) | `GET /api/nodes/{id}` | diretto | 2.1 | [ ] |
| N4 | Azione: Traceroute | `POST /api/nodes/{id}/traceroute`, `GET /api/nodes/{id}/traceroute`, WS `traceroute_result` | `request_traceroute()` + segnale | 2.1 | [ ] |
| N5 | Azione: Richiedi posizione | `POST /api/nodes/{id}/request-position` | `request_position()` | 2.1 | [ ] |
| N6 | Azione: Elimina nodo | `DELETE /api/nodes/{id}` | `database.delete_node()` | 2.1 | [ ] |
| N7 | Azione admin remoto: reboot | `POST /api/admin/{id}/reboot` | `send_admin('reboot')` | 2.1 | [ ] |
| N8 | Azione admin remoto: factory-reset | `POST /api/admin/{id}/factory-reset` | `send_admin('factory_reset')` | 2.1 | [ ] |
| N9 | Azione admin remoto: request-position | `POST /api/admin/{id}/request-position` | `send_admin('request_position')` | 2.1 | [ ] |
| N10 | Azione admin remoto: request-telemetry | `POST /api/admin/{id}/request-telemetry` | `send_admin('request_telemetry')` | 2.1 | [ ] |
| N11 | Highlight nodo locale | (lato client) | `QStyledItemDelegate` | 2.1 | [ ] |
| N12 | Visualizzazione neighbor info | `GET /api/neighbor-info` + WS `neighbor_info` | `database.get_neighbor_info()` + EventBus | 2.1 | [ ] |
| N13 | Ordinamento per last heard / segnale | client-side | `QSortFilterProxyModel` | 2.1 | [ ] |

---

## 3. Pagina Messaggi

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| M1 | Lista messaggi broadcast canale 0 | `GET /api/messages` + WS `message` | `database.get_messages()` + EventBus | 2.2 | [ ] |
| M2 | Lista thread DM | `GET /api/dm/threads` | `database.get_dm_threads()` | 2.2 | [ ] |
| M3 | Apri thread DM e mostra messaggi | `GET /api/dm/messages?peer=...` | `database.get_dm_messages()` | 2.2 | [ ] |
| M4 | Marca thread come letto | `POST /api/dm/read` | `database.mark_dm_read()` | 2.2 | [ ] |
| M5 | Invia messaggio (broadcast o DM) | `POST /api/messages/send` | `meshtasticd_client.send_text()` | 2.2 | [ ] |
| M6 | Indicatore stato pending → ack | WS `ack` | EventBus | 2.2 | [ ] |
| M7 | Cancella tutti i messaggi | `DELETE /api/messages` | `database.clear_messages()` | 2.2 | [ ] |
| M8 | Selezione canale destinazione | parte di `/api/messages/send` | `QComboBox` canali | 2.2 | [ ] |
| M9 | Canned messages — lista in toolbar | `GET /api/canned-messages` | `database.get_canned_messages()` | 2.2 | [ ] |
| M10 | Canned messages — quick send | tap → fill input → send | UI Qt | 2.2 | [ ] |
| M11 | Contatore caratteri / preview lunghezza | client-side | `QLineEdit.textChanged` | 2.2 | [ ] |

---

## 4. Pagina Mappa

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| MP1 | Render tile OSM da `data/tiles/{z}/{x}/{y}.png` | static files | `TileLoader` LRU | 6.1, 6.2 | [ ] |
| MP2 | Pan touch + zoom | Leaflet | `QGraphicsView` + handlers | 6.3 | [ ] |
| MP3 | Marker per nodo con posizione GPS | `GET /api/map/nodes` + WS `position` | `NodeMarker(QGraphicsObject)` | 6.4 | [ ] |
| MP4 | Marker per waypoint Meshtastic | `GET /api/waypoints` + WS `waypoint` | `WaypointMarker` | 6.4 | [ ] |
| MP5 | Marker custom utente (CRUD) | `GET/POST/DELETE /api/map/markers` | `database.get_markers()` ecc. | 6.4 | [ ] |
| MP6 | Popup info al tap su marker | client-side | `PopupOverlay(QFrame)` | 6.5 | [ ] |
| MP7 | Filtro: nodi offline on/off | client-side | toggle Qt | 6.6 | [ ] |
| MP8 | Filtro: per canale | client-side | `QComboBox` | 6.6 | [ ] |
| MP9 | Filtro: mostra/nascondi waypoint | client-side | toggle | 6.6 | [ ] |
| MP10 | Filtro: mostra/nascondi marker custom | client-side | toggle | 6.6 | [ ] |
| MP11 | Centra su nodo locale | client-side | bottone | 6.4 | [ ] |
| MP12 | Centra sulla mia GPS (se disponibile) | client-side | bottone | 6.4 | [ ] |
| MP13 | Aggiungi waypoint da long-press | client-side | gesture | 6.4 | [ ] |
| MP14 | Invia waypoint a mesh | `POST /api/waypoints/send` | `meshtasticd_client.send_waypoint()` | 6.4 | [ ] |
| MP15 | Elimina waypoint | `DELETE /api/waypoints/{id}` | `database.delete_waypoint()` | 6.4 | [ ] |
| MP16 | Tile placeholder se assente (offline) | client-side fallback | grigio in `TileLoader` | 6.2 | [ ] |
| MP17 | Rispetto rotazione display | CSS rotate | `QTransform` su view | 6.7 | [ ] |
| MP18 | Limiti zoom 6–18 | Leaflet config | constraint Qt | 6.3 | [ ] |
| MP19 | Indicatore segnale tra nodi (linee SNR) | client-side | `PathLayer` | 6.4 | [ ] (opzionale, verificare se in uso) |
| MP20 | Modal config region/tile locali | `GET/POST /api/config/map` | dialog Qt | 4.18 (nuovo) | [ ] |

---

## 5. Pagina Log

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| L1 | Stream live pacchetti | `GET /api/log/stream` (SSE) + WS `log` | EventBus signal | 3.1 | [ ] |
| L2 | Filtro per tipo pacchetto | client-side | `QComboBox` | 3.1 | [ ] |
| L3 | Filtro per nodo origine | client-side | `QComboBox` | 3.1 | [ ] |
| L4 | Pause/resume streaming | client-side | toggle | 3.1 | [ ] |
| L5 | Clear log | client-side | bottone | 3.1 | [ ] |
| L6 | Auto-scroll su nuovo pacchetto | client-side | `scrollToBottom()` | 3.1 | [ ] |
| L7 | Cap a N righe (no memory leak) | client-side | `QStandardItemModel` virtualizzato cap 500 | 3.1 | [ ] |
| L8 | Click su pacchetto → dettaglio JSON | client-side | dialog | 3.1 | [ ] |

---

## 6. Pagina Metriche

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| ME1 | Card CPU% Pi (sparkline) | `GET /api/rpi/telemetry` + WS `rpi_telemetry` | EventBus + `Chart` | 3.3 | [ ] |
| ME2 | Card RAM% Pi | idem | idem | 3.3 | [ ] |
| ME3 | Card temperatura Pi | idem | idem | 3.3 | [ ] |
| ME4 | Card uptime Pi | idem | idem | 3.3 | [ ] |
| ME5 | Card batteria Pi (se disponibile) | idem | idem | 3.3 | [ ] |
| ME6 | Alert visivo se sopra `ALERT_RAM_HIGH` | client-side | colore widget | 3.3 | [ ] |
| ME7 | Alert visivo se batteria sotto `ALERT_BATTERY_LOW` | client-side | colore | 3.3 | [ ] |
| ME8 | Card metriche board Meshtastic (voltage, channel util, ecc.) | `GET /api/telemetry/latest?node=local` | diretto | 3.3 | [ ] |
| ME9 | Soglie configurabili | `GET/POST /api/config/alerts` | dialog | 4.19 (nuovo) | [ ] |

---

## 7. Pagina Config — sezioni

> **17 sezioni** elencate nel design + 3 nuove identificate dall'audit (Map, Alerts, USB Storage). Totale **20 sezioni**.

| # | Sezione | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| CF1 | Node identity (long_name, short_name, role) | `GET/POST /api/config/node` | `meshtasticd_client.set_node_config()` | 4.1 | [ ] |
| CF2 | LoRa (region, preset) | `GET/POST /api/config/lora` | `set_lora_config()` | 4.2 | [ ] |
| CF3 | Channels (8 canali, edit per indice) | `GET /api/config/channels`, `POST /api/config/channels/{idx}` | diretto | 4.3 | [ ] |
| CF4 | GPIO devices CRUD + test | `GET/POST/PUT/DELETE /api/config/gpio`, `POST /api/config/gpio/{id}/test` | `database.*_gpio_*()` | 4.4 | [ ] |
| CF5 | I2C scan | `GET /api/config/i2c-scan?bus=N` | subprocess `i2cdetect` | 4.4 | [ ] |
| CF6 | WiFi scan/connect/saved/delete/static-ip | `/api/config/wifi/*` (8 endpoint) | subprocess `nmcli` | 4.5 | [ ] |
| CF7 | AP toggle + status | `GET/POST /api/config/ap/*` | subprocess | 4.6 | [ ] |
| CF8 | RTC status + sync | `GET /api/config/rtc/status` (+ POST set se esiste) | subprocess | 4.7 | [ ] |
| CF9 | Serial port (ports + selezione) | `GET /api/config/serial/ports`, `POST /api/config/serial/port` | subprocess | 4.8 | [ ] |
| CF10 | MQTT bridge config + status | `GET/POST /api/config/mqtt`, `GET /api/config/mqtt/status` | `set_mqtt_config()` | 4.9 | [ ] |
| CF11 | Modulo: External Notification | `GET/POST /api/config/module/external-notification` | `set_external_notification_config()` | 4.10 | [ ] |
| CF12 | Modulo: Store & Forward | `GET/POST /api/config/module/store-forward` | `set_store_forward_config()` | 4.11 | [ ] |
| CF13 | Modulo: Telemetry | `GET/POST /api/config/module/telemetry` | `set_telemetry_module_config()` | 4.12 | [ ] |
| CF14 | Modulo: Neighbor Info | `GET/POST /api/config/module/neighbor-info` | `set_neighbor_module_config()` | 4.13 | [ ] |
| CF15 | Modulo: Range Test | `GET/POST /api/config/module/range-test` | `set_range_test_config()` (verificare esistenza) | 4.13b (nuovo) | [ ] |
| CF16 | Modulo: Detection Sensor | `GET/POST /api/config/module/detection-sensor` | idem | 4.13c (nuovo) | [ ] |
| CF17 | Modulo: Ambient Lighting | `GET/POST /api/config/module/ambient-lighting` | idem | 4.13d (nuovo) | [ ] |
| CF18 | Modulo: Serial (mesh) | `GET/POST /api/config/module/serial` | idem | 4.13e (nuovo) | [ ] |
| CF19 | Modulo: Canned Message (config modulo Meshtastic, distinto da CRUD canned in app) | `GET/POST /api/config/module/canned-message` | idem | 4.13f (nuovo) | [ ] |
| CF20 | Canned messages CRUD (app, non modulo) | `GET/POST/PUT/DELETE /api/canned-messages` | `database.*_canned_*()` | 4.14 | [ ] |
| CF21 | Waypoints CRUD (app) | `GET/DELETE /api/waypoints` | `database.*_waypoint*()` | 4.15 | [ ] |
| CF22 | Display: rotation, brightness, theme, calibrazione touch | `GET/POST /api/config/display` + `scripts/{backlight,calibrate-touch}.sh` | settings + subprocess | 4.16 | [ ] |
| CF23 | System: reboot/shutdown/factory-reset/screenshot | `POST /api/system/{reboot,shutdown,factory-reset}`, `POST /api/screenshot` | subprocess | 4.17 | [ ] |
| CF24 | **Map config**: region, local tiles toggle | `GET/POST /api/config/map` | settings DB | 4.18 (nuovo) | [ ] |
| CF25 | **Alerts config**: soglie offline/battery/RAM | `GET/POST /api/config/alerts` | settings DB | 4.19 (nuovo) | [ ] |
| CF26 | **USB storage**: status, move-tiles, restore-tiles | `GET /api/config/usb/status`, `POST /api/config/usb/{move,restore}-tiles` | `usb_storage.py` diretto | 4.20 (nuovo) | [ ] |

---

## 8. Pagina Telemetria (sotto-pagina di Metriche o stand-alone)

> Verifica: nei tab attuali Telemetria **non** c'è tra i 6 tab principali. Vive come sezione di Metriche o accessibile dal dettaglio nodo. **Decisione UI Qt**: integrarla come tab interna in Metriche o come dialog dal dettaglio nodo.

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| T1 | Selettore nodo | client | `QComboBox` | 3.4 | [ ] |
| T2 | Tab interna: Environment (temp, hum, press, lux) | `GET /api/telemetry?node=...&type=environment` | `database.get_telemetry()` | 3.4 | [ ] |
| T3 | Tab interna: Device (battery, voltage, ch_util) | idem `type=device` | idem | 3.4 | [ ] |
| T4 | Tab interna: Power (channel power, ecc.) | idem `type=power` | idem | 3.4 | [ ] |
| T5 | Tab interna: Air Quality | idem `type=airquality` | idem | 3.4 | [ ] |
| T6 | Aggiornamento real-time | WS `telemetry`, `sensor`, `paxcounter` | EventBus | 3.4 | [ ] |
| T7 | Export CSV | `GET /api/export/telemetry?...` | `QFileDialog` + write | 3.4 | [ ] |
| T8 | Range temporale (1h/24h/7d) | client-side | `QComboBox` filtro DB | 3.4 | [ ] |

---

## 9. Bot

| # | Feature | Endpoint web | Sostituto Qt | Task | Stato |
|---|---|---|---|---|---|
| B1 | Echo bot start/stop | `GET/POST /api/bot-config` | settings DB + `bots/echo_bot.start()` | 4.20b (nuovo) | [ ] |
| B2 | Configurazione canale bot | idem | UI Qt sotto Config | 4.20b (nuovo) | [ ] |

> Verificare prima di Fase 0 se ci sono altri bot oltre `echo_bot.py` o se la tassonomia è destinata a crescere.

---

## 10. Eventi WebSocket → segnali Qt

Tutti gli eventi prodotti da `meshtasticd_client._enqueue_event` e da `mqtt_bridge` devono essere consumati anche dalla GUI:

| # | Tipo evento | Segnale Qt | Consumatori | Task |
|---|---|---|---|---|
| E1 | `init` | `inited` | MainWindow | 1.3 |
| E2 | `node` | `node_updated` | Nodes, Map | 1.3 |
| E3 | `position` | `position_updated` | Map, Nodes | 1.3 |
| E4 | `message` | `message_received` | Messages, StatusBar (badge) | 1.3 |
| E5 | `log` | `log_line` | Log | 1.3 |
| E6 | `telemetry` (4 sotto-tipi) | `telemetry` | Telemetry, Metrics | 1.3 |
| E7 | `traceroute_result` | `traceroute_result` | Nodes | 1.3 |
| E8 | `ack` | `ack_received` | Messages | 1.3 |
| E9 | `waypoint` | `waypoint` | Map | 1.3 |
| E10 | `neighbor_info` | `neighbor_info` | Nodes, Map | 1.3 |
| E11 | `sensor` | `sensor` | Telemetry | 1.3 |
| E12 | `paxcounter` | `paxcounter` | Telemetry | 1.3 |
| E13 | `rpi_telemetry` | `rpi_telemetry` | StatusBar, Metrics | 1.3 |
| E14 | mqtt_* (forwarded da `mqtt_bridge`) | `mqtt_event(type, data)` | a seconda del tipo | 1.3 |

---

## 11. Settings (non in tab; oggi accessibile da bottone in status bar?)

> Audit pendente: `templates/settings.html` esiste (779 righe) ma non è nei 6 tab principali. Verificare come si raggiunge nella web UI. **Decisione preliminare**: integrare i contenuti di `settings.html` dentro la pagina Config (sezioni 7.22 Display, 7.23 System, e sotto-sezione "App settings" se ci sono altre opzioni non duplicate).

Ispezionare `templates/settings.html` per estrarre eventuali feature non già mappate sopra (es. info versione, link doc, log app).

---

## 12. Funzionalità di sistema utilizzate

| # | Funzione | Origine | Dove serve in Qt | Stato |
|---|---|---|---|---|
| S1 | `scripts/backlight.sh` | shell | Display config | [ ] |
| S2 | `scripts/calibrate-touch.sh` | shell | Display config | [ ] |
| S3 | `scripts/setup-display.sh` | shell | install (no UI) | n/a |
| S4 | `scripts/setup-rtc.sh` | shell | install (no UI) | n/a |
| S5 | `scripts/auto_ap.sh` | shell | AP config | [ ] |
| S6 | `scripts/manage-tiles.sh` | shell | USB storage / Map config | [ ] |
| S7 | `scripts/download_tiles.py` | python | Map config (opzionale) | [ ] |
| S8 | `usb_storage.py` (modulo) | python | Config USB | [ ] |
| S9 | `rpi_telemetry.py` (modulo) | python | StatusBar + Metrics | [ ] |
| S10 | `mqtt_bridge.py` (modulo) | python | bridge eventi MQTT (background, no UI) | [ ] |
| S11 | `bots/echo_bot.py` | python | Bot config | [ ] |
| S12 | `database.cleanup_*` task ricorrenti | python | task asyncio (non UI) | [ ] |

---

## 13. Cosa NON serve portare

Esplicitamente fuori scope (resta come endpoint web per accesso remoto, ma non c'è pagina dedicata in Qt):

- Endpoint `/` redirect (la GUI parte già su una pagina)
- `/api/status` endpoint generico (sostituito da accesso diretto)
- `/api/keys`, `/api/hardware-config`, `/api/remote-config` se sono usati solo per debug/dev — verificare in Fase 0.1

> **Regola**: nessun endpoint web va eliminato, anche dopo il porting. Resta a beneficio dell'accesso da browser remoto.

---

## 14. Procedura di verifica parity (Fase 9.1)

Per ogni riga di questo documento:

1. **Open Qt GUI** sulla feature corrispondente.
2. **Open browser** sull'endpoint/pagina web equivalente.
3. **Esegui la stessa azione su entrambi**.
4. **Confronta risultato** (stato DB, comportamento meshtasticd, output visibile).
5. Se identico → `[x]`. Se test automatico esiste → `✅ Done`.

**Acceptance gate**: prima di chiudere il porting (Task 9.3, tag release), il numero di righe `[ ]` deve essere zero.

---

## 15. Nuovi task da aggiungere al piano di implementazione

L'audit ha rivelato 7 task nuovi da aggiungere a `2026-05-07-qt-gui-port-implementation.md`:

- **Task 4.13b** — Sezione Range Test module
- **Task 4.13c** — Sezione Detection Sensor module
- **Task 4.13d** — Sezione Ambient Lighting module
- **Task 4.13e** — Sezione Serial module (mesh)
- **Task 4.13f** — Sezione Canned Message module config
- **Task 4.18** — Sezione Map config (region + local tiles)
- **Task 4.19** — Sezione Alerts thresholds
- **Task 4.20** — Sezione USB storage management
- **Task 4.20b** — Sezione Bot config

Effort aggiuntivo stimato: **+1.5 giornate** (Fase 4 da 4 → 5.5 gg).

**Nuovo totale piano**: ~12 giornate (era ~10–12 dopo la semplificazione da "performance-first").

---

## 16. Open issue prima di Fase 0

- [ ] Verificare endpoint `/api/keys`, `/api/hardware-config`, `/api/remote-config`, `/api/bot-config`: chi li usa, se sono attivi.
- [ ] Verificare come si raggiunge `/settings` nella UI web attuale (non in tab) e cosa contiene di unico.
- [ ] Verificare se "Telemetria" è una pagina stand-alone o solo sezione di Metriche/Nodes.
- [ ] Confermare con utente: `mqtt_bridge` deve girare anche con la GUI Qt (lifespan task condiviso) → presumibilmente sì.
- [ ] Confermare elenco completo dei moduli Meshtastic supportati (la versione meshtastic-python attuale ne supporta altri?).
