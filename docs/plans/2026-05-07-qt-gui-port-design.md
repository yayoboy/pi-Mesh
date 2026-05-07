# pi-Mesh — Qt GUI Port: Design Document

**Data:** 2026-05-07
**Branch:** `claude/web-vs-gui-performance-eTgh0`
**Stato:** Draft
**Riprendibilità:** Ogni milestone è autonoma. La GUI Qt convive con l'attuale stack web fino al cleanup finale.

---

## 1. Obiettivo

Sostituire il client kiosk attuale (`surf` + WebKit puntato a `http://localhost:8080`) con una GUI nativa **PySide6 + QtWidgets + QSS** che gira sullo stesso Raspberry Pi, riusa direttamente i moduli Python esistenti (`meshtasticd_client`, `database`, `mqtt_bridge`, `rpi_telemetry`) **senza HTTP locale**, e mantiene look-and-feel quasi identico all'UI attuale.

### Obiettivi chiave

- **Aspetto identico** alla UI attuale (palette, tab bar, status bar, layout 320×480 / 480×320, temi dark/light/hc/custom).
- **Riduzione risorse**: target RAM UI < 60 MB (oggi ~120 MB), avvio < 1 s (oggi 2–4 s), 60 fps su scroll/animazioni base.
- **Coesistenza**: il backend FastAPI resta vivo per consentire l'accesso remoto da browser sulla LAN. La GUI Qt **non** lo usa: chiama direttamente le funzioni Python.
- **Zero regressioni funzionali**: ogni pagina e ogni azione disponibile nella UI web deve essere disponibile nella GUI Qt al termine del porting.
- **Porting incrementale**: la GUI Qt è funzionale anche prima del completamento; le pagine non ancora portate mostrano un placeholder o ripiegano su `QWebEngineView` opzionale durante lo sviluppo (no per il rilascio).

### Non-obiettivi

- Riscrivere il backend (FastAPI, router, database).
- Eliminare il backend web (resta per accesso remoto).
- Cambiare modello dati o protocolli Meshtastic.
- Supportare hardware diverso dall'attuale (Pi + display SPI 320×480/480×320).

---

## 2. Stack tecnico

| Componente | Scelta | Motivazione |
|---|---|---|
| Toolkit | **PySide6** (Qt 6.x) | Licenza LGPL (PyQt6 è GPL); API ufficiale di Qt; supporto Python pieno. |
| UI paradigm | **QtWidgets + QSS** | Più leggero di QtQuick su Pi senza GPU usabile; raster engine CPU; stylesheet quasi-CSS replica la palette attuale 1:1. |
| Async | **qasync** (`asyncio` ↔ Qt event loop) | Riusa direttamente le funzioni `async` di `meshtasticd_client` e `database` senza wrapper HTTP. |
| Mappa | **QGraphicsView + tile loader custom** | Tile offline OSM già presenti in `data/tiles/{z}/{x}/{y}.png` (gestiti da `scripts/manage-tiles.sh`); zero dipendenze nuove. |
| Charts | **QPainter custom** (mini chart) o **QtCharts** | Sostituisce Chart.js. QtCharts è ufficiale ma pesa ~5 MB di binding. Custom è 100 righe e basta per le metriche attuali. **Decisione preliminare: custom**. |
| Tastiera virtuale | **Widget custom** ispirato a `static/vkbd.js` | Qt Virtual Keyboard ufficiale richiede Qt Quick → escluso. Riscriviamo i 268 righe di `vkbd.js` in QtWidgets (~300 righe). |
| Icone | SVG estratti da template, caricati con `QSvgRenderer` | Stesse icone di adesso (batteria, segnale, tab). |
| Display server | **X11 invariato** (`xinit`, `matchbox-window-manager`) | Sostituisce solo `surf` con `python -m gui.main`. Niente DRM/KMS diretto in fase 1 (aggiungibile dopo). |
| Packaging | venv esistente | Aggiunge `PySide6` e `qasync` a `requirements.txt`. |

### Dimensioni e dipendenze

- `PySide6-Essentials` su ARM64: ~80 MB su disco. Su Pi è importante: verifichiamo che esistano wheel per la nostra architettura, altrimenti ripieghiamo sul pacchetto Debian `python3-pyside6.qtwidgets` (più leggero, condivide librerie di sistema).
- `qasync`: ~30 KB.

### Cosa NON usiamo

- ~~PyQt6~~ (licenza GPL → infetterebbe il progetto).
- ~~QtQuick / QML~~ (richiede GPU funzionante; più RAM).
- ~~QWebEngineView~~ (porta Chromium ~150 MB → vanifica il porting).
- ~~Folium / Marble / MapLibre / pyqtlet~~ (analizzato in conversazione precedente, non adatti).

---

## 3. Architettura

### Coesistenza GUI ↔ backend FastAPI

```
                  ┌──────────────────────────────────────────────┐
                  │                  Raspberry Pi                │
                  │                                              │
                  │  ┌─────────────────────────┐                 │
   serial USB ◄──►│  │  meshtasticd (daemon)   │                 │
                  │  └────────────┬────────────┘                 │
                  │               │                              │
                  │       TCP loopback :4403                     │
                  │               │                              │
                  │  ┌────────────▼────────────┐                 │
                  │  │  meshtasticd_client.py  │ ◄──────┐        │
                  │  │  (singleton, asyncio)   │        │        │
                  │  └────┬────────────────┬───┘        │        │
                  │       │                │            │        │
                  │       │ event queue    │ event q.   │        │
                  │       ▼                ▼            │        │
                  │  ┌─────────┐    ┌─────────────┐     │        │
                  │  │ FastAPI │    │  Qt EventBus│     │        │
                  │  │ uvicorn │    │  (qasync)   │     │        │
                  │  │  :8080  │    └──────┬──────┘     │        │
                  │  └────┬────┘           │            │        │
                  │       │                ▼            │        │
                  │       │         ┌──────────────┐    │        │
                  │       │         │ PySide6 GUI  │────┘        │
                  │       │         │ (kiosk X11)  │ direct call │
                  │       │         └──────────────┘ to async fn │
                  │       │                                      │
                  │       ▼                                      │
                  │  remote browser (LAN)                        │
                  └──────────────────────────────────────────────┘
```

**Decisione critica**: la GUI Qt e il backend FastAPI **condividono lo stesso processo Python** oppure girano in **due processi separati**?

- **Stesso processo** (uvicorn + Qt nello stesso `python main.py`): un unico `meshtasticd_client`, una sola coda eventi distribuita a entrambi i consumatori. Più efficiente ma rischia di intrecciare i due event loop (uvicorn asyncio vs Qt+qasync).
- **Processi separati** (servizio `pimesh.service` con FastAPI, servizio `pimesh-gui.service` con Qt): isolamento, ma due connessioni a `meshtasticd` e due copie di stato.

**Scelta: stesso processo, single asyncio loop gestito da qasync**, con uvicorn avviato come task `asyncio` interno alla GUI. qasync rende il QEventLoop **identico** a un asyncio loop, quindi uvicorn e i task della GUI condividono executor, queue e cache. Risparmia RAM, evita drift di stato. Rischio gestito: ben documentato in qasync, usato in produzione altrove.

### Layout moduli

```
gui/
├── __init__.py
├── __main__.py              # python -m gui  →  main()
├── app.py                   # PiMeshApp(QApplication): theme, fonts, screens
├── main.py                  # entrypoint: qasync loop + uvicorn task + main window
├── window.py                # MainWindow: status bar + content area + tab bar
├── theme/
│   ├── __init__.py
│   ├── palettes.py          # dict identici a quelli in base.html
│   └── qss.py               # palette → stringa QSS
├── core/
│   ├── __init__.py
│   ├── eventbus.py          # consuma meshtasticd_client.get_event_queue() → segnali Qt
│   ├── settings.py          # wrapper sync su database.get_setting/set_setting
│   ├── icons.py             # QIcon cache da SVG
│   └── async_utils.py       # decoratori run_async(coro) → slot
├── widgets/
│   ├── __init__.py
│   ├── statusbar.py         # batteria, segnale, hostname, ora
│   ├── tabbar.py            # 8 tab con icone SVG
│   ├── vkbd.py              # tastiera virtuale custom
│   ├── chart.py             # mini chart QPainter
│   ├── chip.py              # badge/chip stile UI attuale
│   ├── toggle.py            # switch on/off
│   └── modal.py             # dialog stile centrale
├── pages/
│   ├── __init__.py
│   ├── base.py              # BasePage: lifecycle on_show/on_hide
│   ├── nodes_page.py
│   ├── messages_page.py
│   ├── map_page.py
│   ├── map_widget.py        # QGraphicsView mappa (vedi §6)
│   ├── log_page.py
│   ├── metrics_page.py
│   ├── config_page.py
│   ├── config_sections/     # un file per sezione (lora, gpio, wifi, ...)
│   │   ├── node.py
│   │   ├── lora.py
│   │   ├── channels.py
│   │   ├── gpio.py
│   │   ├── wifi.py
│   │   ├── mqtt.py
│   │   ├── ext_notif.py
│   │   ├── store_forward.py
│   │   ├── telemetry_module.py
│   │   ├── neighbor.py
│   │   ├── canned.py
│   │   ├── waypoints.py
│   │   ├── display.py
│   │   └── system.py
│   ├── telemetry_page.py
│   └── settings_page.py
├── resources/
│   ├── icons/               # SVG estratti dai template
│   └── style.qss            # QSS base (i temi sovrascrivono i colori a runtime)
└── tests/
    ├── __init__.py
    ├── conftest.py          # fixture QApplication condivisa, qtbot
    ├── test_palette.py
    ├── test_eventbus.py
    ├── test_pages_smoke.py
    └── test_map_widget.py
```

### Mapping eventi WebSocket → segnali Qt

L'attuale `routers/ws_router.py` distribuisce eventi a tutti i client browser. La GUI bypassa la WebSocket: si abbona alla **stessa `asyncio.Queue`** di `meshtasticd_client` tramite un secondo consumer.

| Evento (WS attuale) | Segnale Qt (`EventBus`) | Slot tipico |
|---|---|---|
| `init` | `inited(dict)` | `MainWindow.on_init` |
| `node` | `node_updated(dict)` | `NodesPage.on_node_updated` |
| `position` | `position_updated(str, float, float)` | `MapWidget.on_position` |
| `message` | `message_received(dict)` | `MessagesPage.on_message` |
| `log` | `log_line(dict)` | `LogPage.on_log` |
| `telemetry` | `telemetry(dict)` | `TelemetryPage.on_telemetry` |
| `traceroute_result` | `traceroute_result(dict)` | `NodesPage.on_traceroute` |
| `ack` | `ack_received(str)` | `MessagesPage.on_ack` |
| `waypoint` | `waypoint(dict)` | `MapWidget.on_waypoint` |
| `neighbor_info` | `neighbor_info(dict)` | `NodesPage.on_neighbor` |
| `sensor` | `sensor(dict)` | `TelemetryPage.on_sensor` |
| `paxcounter` | `paxcounter(dict)` | `TelemetryPage.on_paxcounter` |
| `rpi_telemetry` | `rpi_telemetry(dict)` | `MetricsPage.on_rpi_telemetry`, `StatusBar.on_rpi_telemetry` |
| `mqtt_*` (forwarded) | `mqtt_event(str, dict)` | router-specifici |

**Implementazione `EventBus`**:

```python
# gui/core/eventbus.py
from PySide6.QtCore import QObject, Signal
import meshtasticd_client

class EventBus(QObject):
    inited           = Signal(dict)
    node_updated     = Signal(dict)
    position_updated = Signal(str, float, float)
    message_received = Signal(dict)
    log_line         = Signal(dict)
    telemetry        = Signal(dict)
    traceroute_result = Signal(dict)
    ack_received     = Signal(str)
    waypoint         = Signal(dict)
    neighbor_info    = Signal(dict)
    sensor           = Signal(dict)
    paxcounter       = Signal(dict)
    rpi_telemetry    = Signal(dict)

    async def run(self):
        """Consume the meshtasticd_client event queue forever."""
        # ATTENZIONE: il backend FastAPI già consuma quella coda in main.py:_broadcast_task.
        # Soluzione: modificare meshtasticd_client per esporre un fan-out (lista di code) invece
        # di una sola coda, oppure in EventBus iscriversi al manager.broadcast del WS.
        # Vedi §11.1 per il design del fan-out.
        ...
```

> **Vincolo da risolvere in Task 1**: `meshtasticd_client._enqueue_event` punta a una sola `asyncio.Queue`. Va rifattorizzato in un fan-out (`list[Queue]`), così il task del WS broadcast e l'EventBus della GUI possono entrambi consumare gli eventi senza rubarli all'altro. Cambiamento minimo, retrocompatibile.

### Threading model

- **UI thread**: l'unico che tocca `QWidget*`. Tutti gli slot `@Slot` devono girare qui. qasync garantisce che `asyncio.run_coroutine_threadsafe` da thread esterni svegli il QEventLoop.
- **meshtasticd thread**: già esistente in `meshtasticd_client` (pubsub callback). Usa `loop.call_soon_threadsafe(_enqueue_event, ...)` come oggi. Nessun cambiamento.
- **uvicorn**: gira come task asyncio nello stesso loop. Single worker.
- **Qt timers**: usati per refresh status bar (1 Hz) e per pull-mode delle pagine quando non ci sono push events.

---

## 4. UI: mapping pagina-per-pagina

Per ogni pagina elenco: file template attuale → modulo Qt nuovo → endpoint REST attualmente usati → eventi WS in ingresso → widget Qt principali → criteri di accettazione visivi.

### 4.1 Status bar (sempre visibile)

- **Attuale**: `templates/base.html` (statusbar div, ~50 righe)
- **Nuovo**: `gui/widgets/statusbar.py`
- **Dati**: `rpi_telemetry` (CPU, RAM, batteria, temperatura), `meshtasticd_client.is_connected()`, hostname.
- **Widgets**: `QFrame` con `QHBoxLayout`, `QLabel` per nome nodo, badge custom per batteria (SVG dinamico) e segnale.
- **Refresh**: segnale `rpi_telemetry` (10 s) + `QTimer` 1 Hz per ora.
- **Accettazione**: confronto pixel con screenshot `docs/screenshots/landscape-*.png` — bordi, font, spacing identici al ±1px.

### 4.2 Tab bar (sempre visibile)

- **Attuale**: `templates/base.html` (footer nav)
- **Nuovo**: `gui/widgets/tabbar.py`
- **8 tab**: Nodi, Messaggi, Mappa, Log, Metriche, Config, Telemetria, Settings
- **Implementazione**: `QButtonGroup` di `QToolButton` checkable con icona SVG sopra etichetta.
- **Accettazione**: tab attivo evidenziato con `--accent`, icona SVG colorata via `QPainter` recolor o duplicato SVG.

### 4.3 Pagina Nodi

- **Attuale**: `templates/nodes.html` (690 righe), `static/app.js` (parti pertinenti)
- **Nuovo**: `gui/pages/nodes_page.py`
- **Endpoint REST sostituiti**: `GET /api/nodes`, `DELETE /api/nodes/{id}`, `POST /api/nodes/{id}/traceroute`, `GET /api/nodes/{id}/traceroute`, `POST /api/nodes/{id}/request-position`, `GET /api/nodes/{id}` → chiamate dirette a `meshtasticd_client.get_nodes()` + funzioni `request_*`.
- **Eventi WS**: `node`, `position`, `traceroute_result`, `neighbor_info`.
- **Widgets**: `QListView` + `QStyledItemDelegate` custom per riga nodo (avatar/short name, segnale, batteria, last heard); pannello dettaglio espandibile con `QStackedWidget` (lista vs dettaglio).
- **Azioni**: pulsanti "Traceroute", "Richiedi posizione", "Info", "Elimina" → `await meshtasticd_client.request_traceroute(...)` via `run_async`.
- **Accettazione**: lista popolata all'avvio; nuovo nodo appare entro 1 s dall'evento; tap su nodo apre dettaglio; traceroute mostra hop list.

### 4.4 Pagina Messaggi

- **Attuale**: `templates/messages.html` (358 righe)
- **Nuovo**: `gui/pages/messages_page.py`
- **Endpoint REST sostituiti**: `GET /api/messages`, `DELETE /api/messages`, `GET /api/dm/threads`, `GET /api/dm/messages`, `POST /api/dm/read`, `GET /api/messages/unread-count`, `POST /api/messages/send`, `GET /api/canned` → chiamate dirette a `database.*` + `meshtasticd_client.send_text`.
- **Eventi WS**: `message`, `ack`.
- **Widgets**: split tra lista thread DM (`QListView`) e canale broadcast (`QTextEdit` read-only); input text con `QLineEdit` + bottone invia + integrazione `vkbd`; canned messages come `QToolBar` orizzontale scorrevole.
- **Accettazione**: invio messaggio mostra lo stato pending → ack; nuovi messaggi in arrivo aggiornano la lista; thread DM ordinati per ultima attività.

### 4.5 Pagina Mappa

Vedi sezione **§6** dedicata.

### 4.6 Pagina Log

- **Attuale**: `templates/log.html` (197 righe)
- **Nuovo**: `gui/pages/log_page.py`
- **Endpoint REST sostituiti**: `GET /api/log` → chiamata diretta a `meshtasticd_client.get_log_queue()`.
- **Eventi WS**: `log`.
- **Widgets**: `QListView` virtualizzato (model con cap a 500 righe) per evitare crescita illimitata; filtri per tipo pacchetto in `QComboBox`; pulsante pause/clear.
- **Accettazione**: streaming pacchetti senza lag; filtri funzionanti; nessun freeze sopra 1000 eventi.

### 4.7 Pagina Metriche

- **Attuale**: `templates/metrics.html` (234 righe), Chart.js
- **Nuovo**: `gui/pages/metrics_page.py`
- **Endpoint REST sostituiti**: `GET /api/metrics/rpi`, `GET /api/metrics/board` → diretti.
- **Eventi WS**: `rpi_telemetry`.
- **Widgets**: griglia di mini-card con valore corrente + sparkline (widget `Chart` custom basato su `QPainter`); alert visivi se sopra soglia (`ALERT_*` di `config.py`).
- **Accettazione**: 4 sparkline aggiornate ogni 10 s; alert giallo/rosso secondo soglia.

### 4.8 Pagina Config (più complessa)

- **Attuale**: `templates/config.html` (2052 righe!), molti router (`config_router`, `module_config_router`, `canned_router`, `waypoints_router`, `neighbor_router`, `admin_router`).
- **Nuovo**: `gui/pages/config_page.py` con sidebar `QListWidget` di sezioni e `QStackedWidget` per il contenuto. Una **sezione = un file** in `gui/pages/config_sections/`.
- **Sezioni** (mappate 1:1 al `config.html` attuale):
  1. Node identity (long/short name, role)
  2. LoRa (region, preset)
  3. Channels (lista 8 canali, edit per indice)
  4. GPIO devices (CRUD)
  5. WiFi (scan, connect, saved, IP)
  6. AP (toggle access point)
  7. RTC (status, set time)
  8. Serial port
  9. MQTT
  10. External notification
  11. Store & forward
  12. Telemetry module
  13. Neighbor info
  14. Canned messages (CRUD)
  15. Waypoints (CRUD)
  16. Display (rotation, brightness, theme, calibration)
  17. System (reboot, shutdown, screenshot)
- **Endpoint REST sostituiti**: ~70 endpoint sotto `/api/config/*` e `/api/admin/*` → tutti chiamano già `database.*` o `meshtasticd_client.*` o subprocess locali (es. `nmcli`, `iwgetid`). La GUI chiama le **stesse funzioni** direttamente.
- **Widgets**: `QFormLayout` per ogni sezione, validazione con `QValidator`, salvataggio con feedback (`QMessageBox` o toast custom).
- **Accettazione**: tutte le 17 sezioni navigabili dalla sidebar; salvataggio persistente su DB; feedback errore visibile.

### 4.9 Pagina Telemetria

- **Attuale**: `templates/telemetry.html` (361 righe)
- **Nuovo**: `gui/pages/telemetry_page.py`
- **Endpoint REST**: `GET /api/telemetry` con filtri.
- **Eventi WS**: `telemetry`, `sensor`, `paxcounter`.
- **Widgets**: selettore nodo (`QComboBox`) + tab per categoria (env, device, power, air quality), grafici sparkline.
- **Accettazione**: dati storici da DB caricati al primo show; nuovi punti aggiunti in real-time.

### 4.10 Pagina Settings

- **Attuale**: `templates/settings.html` (779 righe)
- **Nuovo**: `gui/pages/settings_page.py`
- **Funzioni**: tema (dark/light/hc/custom), accent color, brightness, rotation, calibrazione touch, info versione, link a /docs/.
- **Widgets**: `QSlider` brightness, `QButtonGroup` tema, color picker custom per accent.
- **Accettazione**: cambio tema applicato a tutta la GUI senza riavvio; brightness chiama `scripts/backlight.sh` come oggi.

### 4.11 Pagine non portate (placeholder iniziali)

Durante lo sviluppo, le pagine non ancora portate mostrano un `QLabel` "In sviluppo" con possibilità (solo `--debug`) di aprire un `QWebEngineView` puntato all'URL FastAPI corrispondente. Rimosso prima del rilascio.

---

## 5. Tema e QSS

### 5.1 Palette

I 4 temi attuali (`dark`, `light`, `hc`, `custom`) sono già parametrizzati con CSS variables in `static/style.css` e `templates/base.html`. **Estraiamo la stessa palette in Python**:

```python
# gui/theme/palettes.py
PALETTES = {
    'dark':  {'bg': '#060810', 'panel': '#0d1017', 'border': '#1a2233',
              'text': '#c9d1e0', 'muted': '#4a5568', 'accent': '#4a9eff',
              'ok': '#4caf50', 'warn': '#ff9800', 'danger': '#f44336'},
    'light': {...},
    'hc':    {...},
    'custom': None,  # caricato da DB
}
```

### 5.2 Generazione QSS

```python
# gui/theme/qss.py
QSS_TEMPLATE = """
QWidget { background: {bg}; color: {text}; font-family: sans-serif; font-size: 14px; }
QFrame#statusbar { background: {panel}; border-bottom: 1px solid {border}; }
QPushButton { background: {panel}; border: 1px solid {border}; border-radius: 4px;
              padding: 6px 12px; color: {text}; }
QPushButton:pressed, QPushButton:checked { background: {accent}; color: white; }
QLineEdit, QTextEdit, QComboBox { background: {panel}; color: {text};
                                  border: 1px solid {border}; border-radius: 4px;
                                  padding: 4px 8px; }
QListView { background: {bg}; color: {text}; border: none; }
QListView::item:selected { background: {panel}; color: {accent}; }
QScrollBar:vertical { width: 6px; background: {bg}; }
QScrollBar::handle:vertical { background: {muted}; border-radius: 3px; }
"""

def build_qss(palette: dict) -> str:
    return QSS_TEMPLATE.format(**palette)
```

### 5.3 Cambio tema runtime

```python
def apply_theme(app: QApplication, name: str):
    palette = load_palette(name)  # da PALETTES o da DB per 'custom'
    app.setStyleSheet(build_qss(palette))
    eventbus.theme_changed.emit(palette)  # per widget custom (mappa, chart) che dipingono manualmente
```

---

## 6. Mappa: design completo

### 6.1 Requisiti

- Tile **OpenStreetMap raster** offline da `data/tiles/{z}/{x}/{y}.png` (già presenti, gestiti da `scripts/manage-tiles.sh`).
- Marker per ogni nodo Meshtastic (con posizione GPS) + waypoint utente + marker custom.
- Pan/zoom touch (pinch + drag), bottoni +/− per fallback.
- Filtri (tipo `templates/map.html`): mostra/nascondi nodi offline, filtra per canale, ecc.
- Interazione: tap su marker apre popup con info nodo + bottoni (vai a dettaglio, traceroute).

### 6.2 Architettura

```
QGraphicsView (con drag/pinch handlers)
  └── QGraphicsScene
        ├── TileLayer (QGraphicsItemGroup)
        │     └── TileItem(QGraphicsPixmapItem) × N tile visibili
        ├── PathLayer (QGraphicsItemGroup)         # tracce traceroute, ecc.
        ├── MarkerLayer (QGraphicsItemGroup)
        │     ├── NodeMarker(QGraphicsObject) × N nodi
        │     └── WaypointMarker(QGraphicsObject) × N waypoint
        └── PopupOverlay (QWidget proxy)
```

### 6.3 Conversione coordinate (Web Mercator)

```python
# gui/pages/map_widget.py
import math

TILE_SIZE = 256

def lonlat_to_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(lat)
    y = (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n * TILE_SIZE
    return x, y

def pixel_to_lonlat(x: float, y: float, zoom: int) -> tuple[float, float]:
    n = 2 ** zoom
    lon = x / (n * TILE_SIZE) * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / (n * TILE_SIZE))))
    lat = math.degrees(lat_rad)
    return lon, lat
```

### 6.4 Tile loader

```python
class TileLoader(QObject):
    tile_ready = Signal(int, int, int, QPixmap)  # z, x, y, pixmap

    def __init__(self, tiles_root: Path):
        super().__init__()
        self.tiles_root = tiles_root
        self.cache: OrderedDict[tuple, QPixmap] = OrderedDict()  # LRU
        self.cache_max = 256  # ~16 MB con tile 256×256

    def get(self, z: int, x: int, y: int) -> QPixmap | None:
        key = (z, x, y)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        path = self.tiles_root / str(z) / str(x) / f"{y}.png"
        if not path.exists():
            return None  # placeholder grigio nel TileLayer
        pix = QPixmap(str(path))
        self.cache[key] = pix
        if len(self.cache) > self.cache_max:
            self.cache.popitem(last=False)
        return pix
```

I tile non vengono scaricati a runtime: se mancano (offline + zoom non pre-cached) si mostra un placeholder grigio. Stesso comportamento di Leaflet quando `MAP_LOCAL_TILES=1`.

### 6.5 Pan/zoom touch

- **Drag**: override `mouseMoveEvent` per tradurre il movimento in `scrollContentsBy`. Su touch, `QGestureEvent` con `Qt.PinchGesture` per zoom.
- **Pinch zoom**: in caso di problemi con `QGesture` su X11 (capita), fallback a doppio-tap = +1 zoom, due-tap = -1 zoom, +/− buttons in overlay.
- **Limite zoom**: 6–18 (stesso di Leaflet attuale).

### 6.6 Marker e popup

```python
class NodeMarker(QGraphicsObject):
    clicked = Signal(str)  # node_id

    def boundingRect(self): return QRectF(-12, -24, 24, 24)
    def paint(self, painter, option, widget):
        # disegna pin SVG colorato in base al tipo nodo
        ...
    def mousePressEvent(self, event):
        self.clicked.emit(self.node_id)
```

Popup come `QFrame` figlio del `QGraphicsView` (non dentro la scene, così non scala con lo zoom), posizionato in screen coords corrispondenti al marker.

### 6.7 Performance attese

Su Pi 4 con tile cache calda: pan a ~50 fps, zoom transition fluida. Su Pi Zero 2 stimato 25–30 fps in pan, accettabile.

### 6.8 Effort

Modulo `map_widget.py` totale stimato: 700–900 righe. Coperto da test unitari (conversione coordinate, hit-test marker, LRU cache).

---

## 7. Tastiera virtuale

### 7.1 Strategia

Riscrivere `static/vkbd.js` (268 righe, layout IT con simboli) come `gui/widgets/vkbd.py` (~300 righe).

### 7.2 Comportamento

- Si attiva su `focusInEvent` di qualunque `QLineEdit` o `QTextEdit` (installiamo un `eventFilter` globale su `QApplication`).
- Posizionata in basso, altezza fissa (~150 px in landscape, ~180 px in portrait).
- Layout: alfabetico IT, shift, numeri, simboli (3 pannelli swipabili).
- Invia `QKeyEvent` al widget focused via `QApplication.sendEvent`.

### 7.3 Skip per pagine non-text

La VKB **non** appare automaticamente in pagine senza input text (es. mappa). Whitelist di tipi widget gestita nell'event filter.

---

## 8. Charts

### 8.1 Sostituto Chart.js

Custom widget `Chart` in `gui/widgets/chart.py` con `QPainter`:

```python
class Chart(QWidget):
    def __init__(self, ymin=0, ymax=100, history=60):
        ...
        self._data = collections.deque(maxlen=history)
    def push(self, value: float): ...
    def paintEvent(self, event):
        # disegna asse, line plot, fill sottostante con accent
        ...
```

Sufficiente per: CPU%, RAM%, temperatura, batteria, uptime delta. ~150 righe.

### 8.2 Charts più complessi (telemetria storica)

Se nella pagina Telemetria servono grafici multi-serie con zoom temporale, valutiamo `QtCharts` (modulo opzionale). Decisione rimandata a Fase 4 in base ai requisiti effettivi delle metriche.

---

## 9. Avvio e systemd

### 9.1 Nuovo entrypoint

```python
# gui/main.py
import asyncio
import sys
from PySide6.QtWidgets import QApplication
import qasync
import uvicorn
import main as app_main  # FastAPI app
from gui.window import MainWindow

def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    # avvia uvicorn come task asyncio nello stesso loop
    config = uvicorn.Config(app_main.app, host='0.0.0.0', port=8080,
                            log_level='warning', loop='asyncio')
    server = uvicorn.Server(config)
    loop.create_task(server.serve())

    with loop:
        loop.run_forever()

if __name__ == '__main__':
    main()
```

### 9.2 Servizio systemd nuovo

```ini
# systemd/pimesh-gui.service
[Unit]
Description=pi-Mesh Qt GUI (kiosk + FastAPI in-process)
After=network.target meshtasticd.service
Requires=meshtasticd.service
Conflicts=pimesh.service kiosk.service

[Service]
User=pimesh
PAMName=login
Environment=DISPLAY=:0
Environment=HOME=/home/pimesh
WorkingDirectory=/home/pimesh/pi-Mesh
ExecStart=/usr/bin/xinit /home/pimesh/pi-Mesh/scripts/start-gui.sh -- :0 vt1 -nolisten tcp
Restart=on-failure
RestartSec=5
EnvironmentFile=/home/pimesh/pi-Mesh/config.env

[Install]
WantedBy=multi-user.target
```

```bash
# scripts/start-gui.sh
#!/bin/bash
export DISPLAY=:0
xset -dpms
xset s off
xset s noblank
matchbox-window-manager -use_titlebar no &
exec /home/pimesh/pi-Mesh/venv/bin/python -m gui
```

`pimesh.service` e `kiosk.service` sono mutualmente esclusivi con `pimesh-gui.service` (`Conflicts=`). L'utente sceglie quale abilitare. Default per nuove installazioni: GUI Qt; le installazioni esistenti restano sul kiosk web fino a opt-in.

### 9.3 Coexistence durante porting

In fase di sviluppo l'utente può lanciare `python -m gui` da terminale SSH mentre `pimesh.service` continua a girare. Conflitto sulla porta 8080 va gestito (`EnvironmentFile` → `PIMESH_GUI_EMBEDDED_UVICORN=0` per non avviare uvicorn quando già attivo da systemd).

---

## 10. Test

### 10.1 Strategia

- **Unit test pure** (no Qt): logica di conversione coordinate, parsing eventi, palette → QSS, LRU cache tile. → `pytest` standard.
- **Widget smoke test** con `pytest-qt`: ogni pagina si istanzia senza eccezioni, segnali emessi correttamente, slot reagiscono. Non confrontiamo pixel.
- **Integration test**: launch `python -m gui --headless --self-test` che apre tutte le pagine in sequenza usando Xvfb in CI.

### 10.2 Nuove dipendenze test

```
pytest-qt>=4.4
pytest-asyncio>=0.23  # già presente
```

### 10.3 Coverage target

- ≥ 80% su `gui/core/`, `gui/theme/`, `gui/widgets/chart.py`, `gui/pages/map_widget.py` (logica pura).
- Smoke ≥ 1 per pagina.

---

## 11. Modifiche al codice esistente

### 11.1 `meshtasticd_client.py`: fan-out della event queue

**Stato attuale**:

```python
_event_queue: asyncio.Queue = asyncio.Queue()
def get_event_queue() -> asyncio.Queue: return _event_queue
def _enqueue_event(event: dict) -> None:
    _event_queue.put_nowait(event)
```

**Modifica**:

```python
_event_queues: list[asyncio.Queue] = []

def subscribe_events() -> asyncio.Queue:
    """Restituisce una nuova coda che riceverà tutti gli eventi futuri."""
    q = asyncio.Queue()
    _event_queues.append(q)
    return q

def unsubscribe_events(q: asyncio.Queue) -> None:
    if q in _event_queues:
        _event_queues.remove(q)

def _enqueue_event(event: dict) -> None:
    for q in _event_queues:
        q.put_nowait(event)

# Backward compat
def get_event_queue() -> asyncio.Queue:
    """DEPRECATO: usa subscribe_events(). Ritorna la prima coda registrata."""
    if not _event_queues:
        _event_queues.append(asyncio.Queue())
    return _event_queues[0]
```

`main.py:_broadcast_task` continua a funzionare tale e quale. La GUI chiama `subscribe_events()` per la sua coda dedicata.

### 11.2 `requirements.txt`

```diff
+PySide6-Essentials>=6.7
+qasync>=0.27
```

### 11.3 `requirements-dev.txt`

```diff
+pytest-qt>=4.4
```

### 11.4 `setup.sh`

Aggiunge `apt-get install -y python3-pyside6.qtwidgets python3-pyside6.qtsvg python3-pyside6.qtcore qml6-module-qtquick-controls` (solo se PySide6 da pip è troppo lento su ARM).

### 11.5 `README.md`

Sezione "GUI nativa Qt (opzionale)" con istruzioni per abilitare `pimesh-gui.service` invece di `kiosk.service`.

---

## 12. Rischi e mitigazioni

| Rischio | Probabilità | Impatto | Mitigazione |
|---|---|---|---|
| **PySide6 wheel non installabile su Pi (verificato 07/05/2026)**: `manylinux_2_39_aarch64` richiede glibc 2.39 (Pi OS Bookworm ha 2.36); per `armv7l` (Pi 3 / Pi Zero 2 32-bit) **nessun wheel** su PyPI | **Confermata** | Alto | Fallback **apt**: `python3-pyside6.qtcore qtgui qtwidgets qtsvg` (Bookworm v6.4) + venv con `--system-site-packages`. Setup script gestisce automaticamente entrambe le strade. Pi Zero 2 supportato solo via apt. |
| Dipendenze runtime native (`libEGL.so.1`, `libxcb-cursor0`, `libxkbcommon0`, `libfontconfig1`) assenti in installazioni headless | Media | Alto | `setup.sh` installa esplicitamente: `apt install -y libegl1 libxcb-cursor0 libxkbcommon0 libfontconfig1`. Su Pi OS desktop sono già presenti. |
| qasync conflicts con uvicorn loop | Media | Alto | Test precoce in Fase 0; se intrattabile, separiamo i processi (vedi §3 alternativa). |
| Touch pinch gestures instabili su X11 | Media | Medio | Fallback a bottoni zoom +/− nella mappa. |
| Performance map < 25 fps su Pi 3 | Media | Medio | Tile cache LRU + culling tile fuori viewport + scelta `QGraphicsView.MinimalViewportUpdate`. |
| Calibrazione touch (xinput) interagisce male con Qt | Bassa | Medio | Riusare `scripts/calibrate-touch.sh` esistente; testare da Fase 0. |
| Effort sottostimato sui form di config | Alta | Medio | Sezioni Config sono incrementali (porta una alla volta); resto della GUI funziona anche con config parziale. |
| Cambio tema runtime non aggiorna widget custom (mappa, chart) | Bassa | Basso | EventBus.theme_changed → ogni widget custom si ridipinge. |
| Memoria condivisa tra uvicorn + Qt cresce in modo imprevisto | Media | Medio | Monitor RSS in CI smoke test; threshold di alert. |

---

## 13. Successo: criteri misurabili

Al termine del porting, sul Pi 4 con display 480×320:

| Metrica | Target | Misurazione |
|---|---|---|
| RAM RSS GUI process | ≤ 80 MB (uvicorn incluso) | `ps -o rss= -p $(pidof python)` |
| Tempo dal `systemctl start` al primo frame | ≤ 1.5 s | log di `start-gui.sh` |
| FPS scroll lista nodi (50 nodi) | ≥ 50 | misura manuale con `glxgears`-style overlay |
| FPS pan mappa zoom 14 | ≥ 30 | come sopra |
| Cambio tab | ≤ 100 ms | manuale |
| Risposta tap su pulsante invia messaggio | ≤ 50 ms al feedback visivo | manuale |
| Endpoints REST attivi (per LAN browser) | tutti i 98 attuali | `pytest tests/test_api.py` |
| Test suite Qt | 0 fallimenti | `pytest gui/tests/` |

---

## 14. Decisioni aperte (da confermare prima di Task 0)

1. **Confermare PySide6 vs PyQt6**: la licenza è il driver. Se l'utente vuole distribuire commercialmente, PySide6 è obbligatoria.
2. **Stesso processo vs due processi** per FastAPI + GUI: proposta = stesso processo. Da validare con prova di Fase 0.
3. **Mantenere FastAPI a regime?** Se sì, accesso remoto da browser resta. Se no, possiamo eliminare 8000 righe di template/JS dopo il porting. Proposta = mantenere (multi-device dichiarato nel README).
4. **Display target**: confermare che l'unico target è il 320×480 SPI Waveshare. Se in futuro arrivano display più grandi, il layout fisso va rivisto.
5. **Pi Zero 2 come target supportato?** Se sì, profilo prestazioni più stringente (RAM ≤ 50 MB).
6. **Debug `QWebEngineView` durante porting**: ammesso o no? Proposta: sì in `--debug`, no in build di rilascio.

---

## 15. Riferimenti al piano di implementazione

Il documento di **implementazione passo-passo** sarà in `docs/plans/2026-05-07-qt-gui-port-implementation.md` (separato), strutturato in milestone-fase-task come gli altri piani del progetto.
