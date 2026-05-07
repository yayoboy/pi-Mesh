# pi-Mesh — Qt GUI Port: Implementation Plan

> **Per Claude:** segui ogni task in ordine. Spunta `[x]` quando completato. Riferimento design: `docs/plans/2026-05-07-qt-gui-port-design.md`.

**Goal:** sostituire il client kiosk `surf` con una GUI nativa PySide6 + QtWidgets + QSS, mantenendo FastAPI per accesso remoto da LAN, e zero regressioni funzionali.

**Branch:** `claude/web-vs-gui-performance-eTgh0`

**Tech Stack:** Python 3.11+, PySide6, qasync, QtWidgets, QSS, QGraphicsView (mappa), QPainter (chart). Backend invariato: FastAPI, uvicorn, aiosqlite, meshtastic-python.

**Riprendibilità:** ogni task elenca file modificati e criteri di accettazione. Per riprendere: apri questo file, trova il primo `[ ]`.

---

## Convenzioni

- I task con `[blocking]` non possono essere skippati: bloccano i successivi.
- I task con `[parallel-ok]` possono essere portati avanti in parallelo a quello precedente da uno sviluppatore diverso.
- Tutti i path sono relativi alla root del repo.
- Prima di ogni commit: `pytest` deve passare, ed `python -m gui --self-test` deve uscire con codice 0 (dopo Fase 1).

---

## FASE 0 — Fondamenta e prova di fattibilità

Obiettivo: validare lo stack tecnico prima di scrivere UI. Se qui qualcosa non funziona, riconsideriamo l'architettura.

### Task 0.1 — Aggiungi dipendenze e verifica installazione su target [blocking]

**Files:**
- `requirements.txt`: +`PySide6-Essentials>=6.7`, +`qasync>=0.27`
- `requirements-dev.txt`: +`pytest-qt>=4.4`

**Azioni:**
1. ✅ Aggiorna i due file.
2. ✅ Validazione locale (x86_64 Ubuntu 24.04): `pip install` riuscita in 5 s (78 MB wheel). `qasync 0.28.0` + `PySide6 6.11.0`.
3. ✅ Audit wheel ARM:
   - `aarch64` (Pi 4/5 64-bit): wheel `manylinux_2_39_aarch64` esiste ma **non installabile su Bookworm** (richiede glibc 2.39, Bookworm ha 2.36).
   - `armv7l` (Pi 3 / Pi Zero 2 32-bit): **nessun wheel** disponibile su PyPI.
4. ✅ Decisione: fallback `apt install python3-pyside6.{qtcore,qtgui,qtwidgets,qtsvg}` (Bookworm v6.4) + venv con `--system-site-packages`. Documentato in design §12.
5. ⏳ **Da fare nel Task 0.2 / setup.sh**: implementare lo script che tenta pip → fallback apt automaticamente.

**Accettazione:**
- ✅ `pip install` di `PySide6-Essentials` e `qasync` riesce localmente.
- ✅ `pip list | grep -i pyside` mostra `PySide6-Essentials 6.11.0`.
- ⚠️ `python -c "from PySide6.QtWidgets import QApplication; import qasync"` richiede `libEGL.so.1` + `libxcb-cursor0`. Su Pi OS desktop presenti; in sandbox/headless da installare via apt.

**Note di follow-up:**
- Su Pi reale (Pi 4 64-bit, Pi Zero 2): la verifica di import effettiva sarà fatta nel Task 0.3.
- `setup.sh` deve essere aggiornato con la logica di fallback (Task 8.4).

### Task 0.2 — Smoke test minimale: QApplication + qasync + uvicorn nello stesso loop [blocking]

**Files:**
- `gui/__init__.py` (vuoto)
- `gui/__main__.py`
- `gui/_smoke.py`

**Codice `gui/_smoke.py`:**
- Crea `QApplication`, installa `qasync.QEventLoop`.
- Avvia un task asyncio che logga "tick" ogni secondo.
- Avvia `uvicorn` con un `FastAPI()` minimale (un endpoint `GET /ping` che torna `{"ok": True}`).
- Apre un `QWidget` con un `QLabel` "Hello pi-Mesh".
- Dopo 5 s, chiude tutto.

**Accettazione:**
- `python -m gui._smoke` mostra la finestra, `curl http://localhost:8081/ping` risponde durante l'esecuzione, esce pulitamente.
- Nessun warning su X11 / event loop conflict.

**Se fallisce:** ricalibrare §3 del design (passare a due processi separati).

### Task 0.3 — Verifica framebuffer / X11 sul display SPI

**Azioni:**
- Su Pi: lanciare `gui/_smoke.py` con `DISPLAY=:0` sotto `xinit`. Verificare che la finestra appaia sul touchscreen reale.
- Verificare touch input: `xinput list` deve mostrare il digitizer.
- Test rotazione: con `--rotation 270` (env `PIMESH_ROTATION`) la finestra deve apparire ruotata correttamente.

**Accettazione:**
- Touch su `QPushButton` produce evento `clicked`.
- Nessun tearing visibile.

---

## FASE 1 — Scheletro GUI navigabile

Obiettivo: avere la cornice (status bar + tab bar + content area) funzionante con pagine placeholder.

### Task 1.1 — Refactor `meshtasticd_client` event queue in fan-out [blocking]

**Files:**
- `meshtasticd_client.py`
- `tests/test_meshtasticd_client.py`

**Azioni:**
- Sostituire `_event_queue` singolo con `_event_queues: list[asyncio.Queue]`.
- Aggiungere `subscribe_events()` e `unsubscribe_events()`.
- Mantenere `get_event_queue()` come backward-compat (vedi design §11.1).
- Aggiornare `_enqueue_event` per fare put su tutte le code.
- Aggiungere test: due subscriber ricevono lo stesso evento; unsubscribe rimuove la coda; backward-compat funziona.

**Accettazione:**
- `pytest tests/test_meshtasticd_client.py` passa (incluso il test esistente).
- `main.py:_broadcast_task` continua a funzionare (verificato da `tests/test_ws.py`).

### Task 1.2 — Theme manager [parallel-ok]

**Files:**
- `gui/theme/__init__.py`
- `gui/theme/palettes.py` (4 palette identiche a quelle in `templates/base.html`)
- `gui/theme/qss.py`
- `gui/tests/test_palette.py`

**Accettazione:**
- `build_qss(PALETTES['dark'])` produce stringa valida.
- Test verifica che i 4 temi standard producano QSS senza placeholder non risolti.

### Task 1.3 — EventBus

**Files:**
- `gui/core/__init__.py`
- `gui/core/eventbus.py`
- `gui/tests/test_eventbus.py`

**Codice:**
- `class EventBus(QObject)` con tutti i `Signal` elencati in design §3.
- Metodo `async run(self)`: chiama `meshtasticd_client.subscribe_events()`, in loop legge la coda, `match` sul `event['type']`, emette il segnale corrispondente.
- Singleton accessibile via `get_eventbus()`.

**Accettazione:**
- Test con `pytest-qt`: enqueue di un evento `{'type': 'node', ...}` → segnale `node_updated` ricevuto.

### Task 1.4 — Settings wrapper

**Files:**
- `gui/core/settings.py`

**Codice:**
- Funzioni sync `get(key, default)` e `set(key, value)` che usano `asyncio.run_coroutine_threadsafe` per chiamare `database.get_setting/set_setting` dal qasync loop.

**Accettazione:**
- Smoke test: lettura/scrittura di una chiave fittizia.

### Task 1.5 — MainWindow + StatusBar + TabBar [blocking]

**Files:**
- `gui/window.py`
- `gui/widgets/__init__.py`
- `gui/widgets/statusbar.py`
- `gui/widgets/tabbar.py`
- `gui/pages/__init__.py`
- `gui/pages/base.py`
- `gui/resources/icons/` (8 icone SVG estratte dai template attuali)
- `gui/main.py` (entrypoint completo, sostituisce `gui/_smoke.py`)
- `gui/__main__.py` (chiama `gui.main:main`)

**Codice principale `gui/window.py`:**
- `MainWindow(QMainWindow)`: `setFixedSize(480, 320)` o `setFixedSize(320, 480)` in base a env `PIMESH_ORIENTATION`.
- Layout: `QVBoxLayout` con `StatusBar` in alto, `QStackedWidget` al centro, `TabBar` in basso.
- 8 pagine placeholder (`PlaceholderPage("Nodi")`, ...). Sostituite incrementalmente nelle fasi successive.

**`StatusBar`:**
- `QHBoxLayout` con: `QLabel` nome nodo (sx), badge batteria/segnale/tempo (dx).
- Connesso a `eventbus.rpi_telemetry` per aggiornare batteria/RAM.
- `QTimer(1000)` per ora corrente.

**`TabBar`:**
- `QButtonGroup` con 8 `QToolButton` checkable, icona SVG sopra etichetta.
- Click → `currentChanged.emit(index)` → `MainWindow` cambia `QStackedWidget.setCurrentIndex`.

**`gui/main.py`:**
- Vedi §9.1 del design.
- Avvia uvicorn nel loop solo se env `PIMESH_GUI_EMBEDDED_UVICORN=1` (default 1 in produzione, 0 quando si lancia da terminale durante dev).

**Accettazione:**
- `python -m gui` mostra la finestra fissa 480×320 con status bar + tab bar + 8 pagine placeholder navigabili.
- Cambio tab istantaneo (< 100 ms misurato).
- StatusBar mostra batteria simulata se `rpi_telemetry` non è disponibile.
- `pytest gui/tests/test_pages_smoke.py` (tutti i placeholder si istanziano).

### Task 1.6 — Apply theme + cambio runtime

**Files:**
- `gui/app.py` (`PiMeshApp(QApplication)` con `apply_theme(name)`)
- aggiornare `gui/main.py` per usare `PiMeshApp`

**Accettazione:**
- All'avvio carica tema da `database.get_setting('display.theme', 'dark')`.
- Da REPL/test: `app.apply_theme('light')` aggiorna immediatamente tutta la GUI.

### Task 1.7 — Servizio systemd dev e script di lancio

**Files:**
- `scripts/start-gui.sh` (vedi design §9.2)
- `systemd/pimesh-gui.service` (vedi design §9.2)
- `README.md`: sezione "GUI nativa (sperimentale)"

**Accettazione:**
- `sudo systemctl --user start pimesh-gui` (o equivalente system) lancia la GUI sul touchscreen.
- `Conflicts=` impedisce avvio simultaneo con `kiosk.service`.

---

## FASE 2 — Pagine semplici: Nodi, Messaggi

### Task 2.1 — Pagina Nodi

**Files:**
- `gui/pages/nodes_page.py`
- `gui/widgets/node_delegate.py` (`QStyledItemDelegate`)
- `gui/tests/test_nodes_page.py`

**Comportamento:**
- All'avvio: `nodes = meshtasticd_client.get_nodes()` → popola `QStandardItemModel`.
- Slot `on_node_updated(dict)`: upsert nel model.
- Tap su riga → mostra `NodeDetailWidget` (overlay o `QStackedWidget` interno).
- Bottoni in dettaglio: Traceroute, Richiedi posizione, Info, Elimina → `run_async(meshtasticd_client.request_traceroute(node_id))` ecc.

**Accettazione:**
- Smoke test: pagina si istanzia, model popolato.
- Test integrazione: enqueue evento `node` → riga aggiornata.
- Manuale: traceroute di un nodo reale completa e mostra hop list.

### Task 2.2 — Pagina Messaggi

**Files:**
- `gui/pages/messages_page.py`
- `gui/widgets/message_bubble.py`
- `gui/tests/test_messages_page.py`

**Comportamento:**
- Toggle Broadcast / DM threads.
- Lista DM threads da `database.get_dm_threads`.
- Lista messaggi da `database.get_dm_messages` o `database.get_messages` (broadcast).
- Input area con `QLineEdit` + bottone invia + canned messages toolbar (`QToolBar` orizzontale, fonti da `database.get_canned_messages`).
- Slot `on_message_received` aggiunge bubble; slot `on_ack_received` aggiorna stato pending → ack.

**Accettazione:**
- Invio messaggio reale a un nodo raggiungibile mostra ack entro 30 s.
- Cambio thread DM aggiorna lista.
- Canned message popola input.

---

## FASE 3 — Pagine medie: Log, Metriche, Telemetria

### Task 3.1 — Pagina Log

**Files:**
- `gui/pages/log_page.py`
- `gui/widgets/log_view.py` (model virtualizzato cap 500 righe)

**Accettazione:**
- Streaming live di pacchetti (testato con dati reali o injecting via test).
- Filtri funzionanti.
- Performance: 100 eventi/s senza freeze.

### Task 3.2 — Widget Chart custom

**Files:**
- `gui/widgets/chart.py`
- `gui/tests/test_chart.py`

**Accettazione:**
- Test: 60 valori pushati → 60 punti disegnati nel `paintEvent`.
- Test visivo manuale: linea liscia, asse colorato in `--accent`.

### Task 3.3 — Pagina Metriche

**Files:**
- `gui/pages/metrics_page.py`

**Comportamento:**
- 4 mini-card (CPU, RAM, temp, batteria) con `Chart` sparkline.
- Aggiornate da `eventbus.rpi_telemetry` (10 s).
- Alert visivo (`color: var(--danger)`) se sopra `ALERT_*` di `config.py`.

**Accettazione:**
- Card popolate entro 11 s dall'apertura pagina.
- Alert RAM > 85% verifica visiva.

### Task 3.4 — Pagina Telemetria

**Files:**
- `gui/pages/telemetry_page.py`

**Comportamento:**
- `QComboBox` selettore nodo (popolato da `meshtasticd_client.get_nodes()`).
- Tab interna: env / device / power / air quality.
- Per ogni tab: mini-card + chart con dati storici da `database.get_telemetry`.
- Aggiornamento real-time via `eventbus.telemetry`.

**Accettazione:**
- Selezione nodo carica dati storici.
- Nuovo evento telemetry aggiunge punto al chart.

---

## FASE 4 — Pagina Config (incrementale per sezione)

Ogni sub-task corrisponde a una sezione di `templates/config.html`. Ogni sezione è autonoma: la pagina Config si comporta correttamente anche con sezioni mancanti.

### Task 4.0 — Cornice Config [blocking]

**Files:**
- `gui/pages/config_page.py`
- `gui/pages/config_sections/__init__.py`
- `gui/pages/config_sections/base.py` (`BaseConfigSection(QWidget)` con `load()` e `save()` astratti)

**Comportamento:**
- Sidebar `QListWidget` con titoli sezioni; `QStackedWidget` con i widget.
- Le sezioni mancanti mostrano "In sviluppo".

### Task 4.1 — Sezione Node identity

**Files:** `gui/pages/config_sections/node.py`

**Endpoints/funzioni sostituiti:** `meshtasticd_client.get_node_config`, `set_node_config`.

**Widgets:** `QLineEdit` long_name, `QLineEdit` short_name (max 4 char), `QComboBox` role.

### Task 4.2 — Sezione LoRa
**Files:** `gui/pages/config_sections/lora.py`. Funzioni: `get_lora_config`, `set_lora_config`.

### Task 4.3 — Sezione Channels
**Files:** `gui/pages/config_sections/channels.py`. Funzioni: `get_channels`, set per indice.

### Task 4.4 — Sezione GPIO
**Files:** `gui/pages/config_sections/gpio.py`. Funzioni: `database.get_gpio_devices`, CRUD, test pin.

### Task 4.5 — Sezione WiFi
**Files:** `gui/pages/config_sections/wifi.py`. Subprocess `nmcli` come fa `config_router.py`.

### Task 4.6 — Sezione AP
**Files:** `gui/pages/config_sections/ap.py`. Subprocess (vedi `config_router.py:474`).

### Task 4.7 — Sezione RTC
**Files:** `gui/pages/config_sections/rtc.py`.

### Task 4.8 — Sezione Serial port
**Files:** `gui/pages/config_sections/serial.py`.

### Task 4.9 — Sezione MQTT
**Files:** `gui/pages/config_sections/mqtt.py`.

### Task 4.10 — Sezione External notification
**Files:** `gui/pages/config_sections/ext_notif.py`.

### Task 4.11 — Sezione Store & forward
**Files:** `gui/pages/config_sections/store_forward.py`.

### Task 4.12 — Sezione Telemetry module
**Files:** `gui/pages/config_sections/telemetry_module.py`.

### Task 4.13 — Sezione Neighbor info
**Files:** `gui/pages/config_sections/neighbor.py`.

### Task 4.13b — Sezione Range Test module
**Files:** `gui/pages/config_sections/range_test.py`. Endpoints: `GET/POST /api/config/module/range-test`.

### Task 4.13c — Sezione Detection Sensor module
**Files:** `gui/pages/config_sections/detection_sensor.py`. Endpoints: `GET/POST /api/config/module/detection-sensor`.

### Task 4.13d — Sezione Ambient Lighting module
**Files:** `gui/pages/config_sections/ambient_lighting.py`. Endpoints: `GET/POST /api/config/module/ambient-lighting`.

### Task 4.13e — Sezione Serial module (mesh)
**Files:** `gui/pages/config_sections/serial_module.py`. Endpoints: `GET/POST /api/config/module/serial`.

### Task 4.13f — Sezione Canned Message module (config Meshtastic)
**Files:** `gui/pages/config_sections/canned_message_module.py`. Endpoints: `GET/POST /api/config/module/canned-message`. Distinto da CRUD canned in app (Task 4.14).

### Task 4.14 — Sezione Canned messages
**Files:** `gui/pages/config_sections/canned.py`. CRUD via `database.*`.

### Task 4.15 — Sezione Waypoints
**Files:** `gui/pages/config_sections/waypoints.py`. CRUD via `database.*`.

### Task 4.16 — Sezione Display
**Files:** `gui/pages/config_sections/display.py`. Brightness via `scripts/backlight.sh`, rotation via env+restart, calibrazione via `scripts/calibrate-touch.sh`.

### Task 4.17 — Sezione System
**Files:** `gui/pages/config_sections/system.py`. Reboot, shutdown, factory-reset, screenshot. Endpoints: `POST /api/system/{reboot,shutdown,factory-reset}`, `POST /api/screenshot`.

### Task 4.18 — Sezione Map config
**Files:** `gui/pages/config_sections/map_config.py`. Endpoints: `GET/POST /api/config/map`. Setting: region (`MAP_REGION`), local tiles toggle (`MAP_LOCAL_TILES`).

### Task 4.19 — Sezione Alerts thresholds
**Files:** `gui/pages/config_sections/alerts.py`. Endpoints: `GET/POST /api/config/alerts`. Soglie: `ALERT_NODE_OFFLINE_MIN`, `ALERT_BATTERY_LOW`, `ALERT_RAM_HIGH`.

### Task 4.20 — Sezione USB storage
**Files:** `gui/pages/config_sections/usb_storage.py`. Endpoints: `GET /api/config/usb/status`, `POST /api/config/usb/{move,restore}-tiles`. Usa direttamente `usb_storage.py`.

### Task 4.20b — Sezione Bot config
**Files:** `gui/pages/config_sections/bot.py`. Endpoint: `GET/POST /api/bot-config`. Start/stop `bots/echo_bot.py`, selezione canale.

**Accettazione di Fase 4:**
- Ogni sezione legge/scrive correttamente.
- Restart non necessario per la maggior parte (eccetto rotation).
- Test manuale: cambia long_name → verifica con `meshtastic --info` esterno.

---

## FASE 5 — Tastiera virtuale

### Task 5.1 — Layout e widget

**Files:**
- `gui/widgets/vkbd.py`
- `gui/tests/test_vkbd.py`

**Comportamento:**
- `VirtualKeyboard(QFrame)` ancorata in basso, altezza 150 px landscape / 180 px portrait.
- 3 layout: alfabetico IT, numeri, simboli (3 pannelli swipabili o tab interni).
- Shift toggle, backspace, enter, space.

### Task 5.2 — Event filter globale

**Files:**
- `gui/widgets/vkbd.py` (estensione)
- `gui/main.py` (installazione filter)

**Comportamento:**
- `QApplication.installEventFilter(vkbd)`.
- Su `FocusIn` di `QLineEdit/QTextEdit`: anima entrata VKB e ridimensiona content area sopra di essa.
- Su `FocusOut`: anima uscita.
- Whitelist: `QListView`, `QTabBar`, `QGraphicsView` non triggherano.

**Accettazione:**
- Tap su input messaggio apre VKB.
- Digitazione produce caratteri nel campo focused.
- VKB non appare in mappa o lista nodi.

---

## FASE 6 — Mappa

Il blocco più impegnativo. Diviso in sub-task incrementali.

### Task 6.1 — Conversione coordinate + tile loader [blocking]

**Files:**
- `gui/pages/map_widget.py` (parziale: solo helpers)
- `gui/tests/test_map_widget.py`

**Accettazione:**
- Test conversione lon/lat ↔ pixel su 5 punti noti (Roma, Londra, NYC, Sydney, Polo Nord).
- Tile loader: cache LRU funziona, miss su tile inesistente ritorna `None`.

### Task 6.2 — TileLayer + viewport culling

**Files:** `gui/pages/map_widget.py` (continua)

**Comportamento:**
- `MapWidget(QGraphicsView)` con `QGraphicsScene`.
- Calcola tile visibili dal viewport, carica solo quelli, rimuove quelli fuori viewport.
- Placeholder grigio per tile mancanti.

**Accettazione:**
- Apertura mappa centrata su Roma a zoom 12 mostra tile reali (se presenti in `data/tiles/`).
- Pan a destra carica nuovi tile, libera memoria di quelli vecchi.

### Task 6.3 — Pan e zoom

**Files:** `gui/pages/map_widget.py` (continua)

**Comportamento:**
- Drag con mouse/touch per pan.
- Wheel per zoom desktop; bottoni +/− in overlay (`QPushButton` figli del view).
- Pinch via `QGestureEvent` (best effort).

**Accettazione:**
- Pan fluido (≥ 30 fps a Pi 4).
- Zoom mantiene il punto sotto il puntatore.
- Limite zoom 6–18.

### Task 6.4 — Marker nodi + waypoint

**Files:**
- `gui/pages/map_widget.py` (NodeMarker, WaypointMarker)
- icone SVG in `gui/resources/icons/`

**Comportamento:**
- Per ogni nodo con `position` valida: `NodeMarker` in scene.
- Connesso a `eventbus.position_updated` per aggiornare posizione.
- Waypoint da `database.get_waypoints()` + `eventbus.waypoint`.

**Accettazione:**
- Nodi con GPS appaiono sulla mappa.
- Nuovo evento position sposta il marker.

### Task 6.5 — Popup info + azioni

**Files:** `gui/pages/map_widget.py` (PopupOverlay)

**Comportamento:**
- Tap su marker: popup `QFrame` con nome nodo, distanza, ultimo segnale, bottoni "Dettaglio", "Traceroute".
- Tap fuori chiude popup.

**Accettazione:**
- Popup posizionato sopra il marker, leggibile.
- Bottoni funzionanti.

### Task 6.6 — Filtri mappa

**Files:** `gui/pages/map_page.py` (cornice con bottone filtri + `MapWidget` figlio)

**Comportamento:**
- Sheet di filtri: mostra/nascondi nodi offline, filtra per canale, mostra waypoint, ecc.
- Stesse opzioni di `templates/map.html`.

**Accettazione:**
- Toggle filtri aggiorna la scene immediatamente.

### Task 6.7 — Rotazione mappa con orientamento display

**Comportamento:** `MapWidget` rispetta `PIMESH_ORIENTATION`.

**Accettazione:** rotazione hardware non distorce la mappa.

---

## FASE 7 — Pagina Settings

### Task 7.1 — Settings page

**Files:** `gui/pages/settings_page.py`

**Comportamento:**
- Cambio tema (4 radio + custom con color picker per accent).
- Slider brightness → `scripts/backlight.sh`.
- Selettore rotation (con avviso "richiede restart").
- Bottone "Calibra touch" → `scripts/calibrate-touch.sh`.
- Info versione (git rev breve) + link "Apri /docs/" che apre tab `Help` (vedi 7.2 opzionale).

**Accettazione:**
- Cambio tema applicato live.
- Brightness slider muove la retroilluminazione reale.

---

## FASE 8 — Hardening, test, packaging

### Task 8.1 — Self-test mode

**Files:** `gui/main.py` (flag `--self-test`)

**Comportamento:** apre tutte le pagine in sequenza per 1 s ciascuna, esce con codice 0 se nessuna eccezione.

**Accettazione:** `python -m gui --self-test` esce con 0 in CI con Xvfb.

### Task 8.2 — CI: Xvfb + smoke

**Files:** workflow CI (se esiste; altrimenti `Makefile` target)

**Accettazione:** `make test-gui` lancia smoke + unit test in Xvfb.

### Task 8.3 — Misura RAM e fps

**Files:**
- `scripts/measure-gui-perf.sh`

**Comportamento:** lancia GUI, misura RSS dopo 30 s e dopo 5 min, log in `data/perf-gui.log`.

**Accettazione:** RSS ≤ 80 MB, drift < 5 MB / 5 min.

### Task 8.4 — Aggiornare `setup.sh` e doc

**Files:**
- `setup.sh`: aggiunta install pacchetti Qt fallback, scelta interattiva GUI vs Web.
- `README.md`: sezione GUI nativa, screenshot nuovi.
- `docs/screenshots/`: nuovi screenshot della GUI Qt.

**Accettazione:** install pulita su Pi vergine produce GUI funzionante.

### Task 8.5 — Cleanup placeholder e debug

**Comportamento:** rimuovere `--debug` con `QWebEngineView`, placeholder pages, codice sperimentale.

---

## FASE 9 — Release

### Task 9.1 — Confronto pixel-by-pixel con UI web

**Comportamento:** screenshot delle 8 pagine in entrambe le UI; tabella di confronto in `docs/qt-vs-web.md`.

### Task 9.2 — Decisione su sunset web UI

**Discussione con utente:** mantenere FastAPI + template per accesso remoto, o eliminare? Da prendere dopo aver visto le metriche reali.

### Task 9.3 — Tag e PR

**Comportamento:** tag `v2.0.0-qt` o simile. Solo dopo conferma utente.

---

## Riepilogo effort stimato

| Fase | Effort (giornate sviluppo Qt) | Note |
|---|---|---|
| 0 | 1 | Critica: se fallisce, ripensiamo architettura |
| 1 | 1.5 | Scheletro + theme Fusion + systemd (semplificato: no clone pixel-perfect) |
| 2 | 1.5 | Nodi + Messaggi |
| 3 | 1.5 | Log + Metriche + Telemetria (chart minimal o QtCharts) |
| 4 | 5.5 | 26 sezioni config (incluse 9 nuove dall'audit parity) |
| 5 | 1 | VKB |
| 6 | 3 | Mappa (semplificata: marker base, no animazioni custom) |
| 7 | 0.5 | Settings |
| 8 | 1.5 | Hardening |
| 9 | 0.5 | Release + verifica feature parity |
| **Totale** | **~17.5 giorni dev esperto Qt+Python** | escluso debug hardware-specific |

> Nota: la stima "performance-first" (no clone pixel) abbatte ~30% l'effort UI delle fasi 1, 3, 6, ma l'audit di feature parity ha aggiunto 9 sezioni Config (+1.5 gg). Saldo netto vicino al piano originale.

---

## Decisioni che richiedono input utente PRIMA di iniziare

1. ✅ **Branch separato confermato**: `claude/web-vs-gui-performance-eTgh0` (già creato).
2. ⚠️ **PySide6 (LGPL) vs PyQt6 (GPL)** — confermare PySide6.
3. ⚠️ **Mantenere FastAPI a regime?** — proposta: sì.
4. ⚠️ **Pi Zero 2 incluso nel target?** — proposta: no per la GUI nativa, sì per la web.
5. ⚠️ **Effort budget**: ~18 giornate. Confermare prima di Fase 0.
6. ⚠️ **Approccio incrementale a merge**: la branch va mergiata in main solo a Fase 9, oppure si fa merge per fase con feature flag? — proposta: merge a Fase 9 (la branch resta separata per tutto il porting).

---

**Documento di design di riferimento:** `docs/plans/2026-05-07-qt-gui-port-design.md`

**Aggiornare PROGRESS.md** (se esiste in root) man mano che le task vengono completate.
