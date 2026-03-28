# YAY-114 — Map Enhancements: Design Spec

**Data:** 2026-03-28
**Issue:** [YAY-114](https://linear.app/yayoboy/issue/YAY-114/mappa)
**Stato:** Approvato — pronto per implementazione

---

## Problema

La mappa attuale mostra solo marker circolari per i nodi senza contesto visivo: nessuna legenda, nessuna connessione tra nodi, nessun filtro, nessun marker personalizzato, nessun traceroute.

---

## Decisioni di Design

| Domanda | Scelta |
|---------|--------|
| Hop lines | Linee colorate per qualità SNR + frecce direzionali sul percorso traceroute |
| Legenda | Barra orizzontale fissa in fondo alla mappa |
| Marker personalizzati | Pannello sidebar sinistra + persistenza DB |
| Context menu nodo | Long press (touch) — niente mouse |
| Filtri | Tutti: online/offline, linee hop, marker, nodo locale, hop count range |
| Traceroute | Incluso completo: richiesta + parsing risposta + visualizzazione |
| Icone | SVG Heroicons — nessuna emoji |
| Architettura | Nuovo `static/map.js` + estensioni backend |

---

## 1. Database

### Nuove tabelle (migrate all'avvio con `PRAGMA table_info`)

```sql
CREATE TABLE IF NOT EXISTS map_markers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  label TEXT NOT NULL,
  icon_type TEXT NOT NULL DEFAULT 'poi',
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS traceroute_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id TEXT NOT NULL,
  hops TEXT NOT NULL,  -- JSON array di node_id: ["!local","!a1b2","!dest"]
  timestamp INTEGER NOT NULL
);
```

`icon_type` valori validi: `"antenna"`, `"base"`, `"obstacle"`, `"poi"` — mappati a SVG Heroicons inline.

### Nuove funzioni in `database.py`

```python
async def save_marker(conn, label, icon_type, latitude, longitude) -> int
async def get_markers(conn) -> list
async def delete_marker(conn, marker_id: int)
async def save_traceroute(conn, node_id: str, hops: list) -> int
async def get_traceroutes(conn, node_id: str, limit: int = 10) -> list
```

---

## 2. Backend

### meshtastic_client.py

**`request_traceroute(node_id)`** — invia richiesta traceroute:
```python
self.mesh_interface.sendTraceRoute(node_id, hopLimit=7)
```

**`_on_receive_traceroute(packet)`** — riceve e processa risultato:
- Estrae lista hop da `packet["decoded"]["traceroute"]["route"]` (lista di node num interi, convertiti in `!hex`)
- Se `route` è vuoto, il nodo destinazione è raggiungibile direttamente (1 hop)
- Salva in DB via `save_traceroute()`
- Broadcast WebSocket:
```json
{"type": "traceroute_result", "data": {"node_id": "!abc123", "hops": ["!local","!a1b2","!abc123"], "timestamp": 1711636800}}
```

Registrare `_on_receive_traceroute` nel `setFilter` dell'interfaccia Meshtastic per `portnums.TRACEROUTE_APP`.

### main.py — nuovi endpoint

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/api/map/markers` | Lista marker `{"markers": [...]}` |
| `POST` | `/api/map/markers` | Crea marker `{label, icon_type, latitude, longitude}` |
| `DELETE` | `/api/map/markers/{marker_id}` | Rimuove marker |
| `POST` | `/api/traceroute` | Avvia traceroute `{node_id}` → `{"ok": true}` |
| `GET` | `/api/traceroute/{node_id}` | Ultimi N risultati `{"results": [...]}` |

---

## 3. Frontend

### Nuovo file: `static/map.js`

Contiene tutta la logica mappa estratta da `app.js` + nuove funzionalità:

**Moduli interni:**

- **`initMap()`** — inizializza Leaflet, carica tile layers (estratto da app.js)
- **`updateMapMarker(node)`** — aggiorna/crea marker nodo (estratto da app.js)
- **`renderHopLines(nodeCache)`** — disegna polyline colorate per SNR tra nodi vicini noti
- **`renderTraceroutePath(hops)`** — disegna percorso traceroute in giallo tratteggiato con frecce direzionali
- **`initLegend()`** — crea barra legenda HTML in fondo alla mappa
- **`initFilters()`** — crea pannello filtri in alto a destra
- **`applyFilters()`** — applica stato filtri a marker e linee Leaflet
- **`initMarkerSidebar()`** — crea pannello sidebar sinistra per marker personalizzati
- **`loadCustomMarkers()`** — fetch `/api/map/markers` e posiziona marker su mappa
- **`addCustomMarker(label, iconType, latlng)`** — POST + aggiungi a mappa
- **`removeCustomMarker(id)`** — DELETE + rimuovi da mappa
- **`initNodeContextMenu()`** — long press (300ms) su marker nodo → menu con azioni

**Integrazione WebSocket:**

In `app.js`, aggiungere handler per `traceroute_result` nel `switch(data.type)`:
```javascript
case 'traceroute_result':
  window.dispatchEvent(new CustomEvent('traceroute_result', { detail: data.data }))
  break
```

`map.js` ascolta `window.addEventListener('traceroute_result', ...)` e chiama `renderTraceroutePath(e.detail.hops)`.

`app.js` rimane responsabile del dispatch di tutti gli eventi WebSocket. `map.js` è caricato solo nella pagina mappa (via `<script src="/static/map.js"></script>` in `map.html`), non in `base.html`.

### Hop lines — logica colore SNR

```
SNR > 5 dB   → #4caf50 (verde)
SNR 0–5 dB   → #fb8c00 (arancio)
SNR < 0 dB   → #e53935 (rosso)
SNR unknown  → #555    (grigio)
```

Le linee sono disegnate tra nodi con coordinate note (`latitude != null`) e `last_heard` < 30 minuti. Ogni linea richiede che entrambi i nodi abbiano posizione GPS. Aggiornate ogni volta che arriva un `node-update` o `position`.

### Filtri

| Filtro | Tipo | Default |
|--------|------|---------|
| Mostra nodi online | checkbox | ✓ |
| Mostra nodi offline | checkbox | ✗ |
| Mostra linee hop | checkbox | ✓ |
| Mostra marker personalizzati | checkbox | ✓ |
| Mostra nodo locale | checkbox | ✓ |
| Hop count massimo | range 1–7 | 7 (tutti) |

Stato filtri persistito in `localStorage` chiave `mapFilters`.

### Context menu nodo (long press)

Long press 300ms su marker nodo → pannello floating con:
- Intestazione: nome nodo + ID
- "Invia DM" → naviga a `/messages?open_dm=!nodeId`
- "Richiedi posizione" → `POST /send` tipo `position_request`
- "Traceroute" → `POST /api/traceroute` con `node_id`

Dismiss: tap fuori dal menu.

### Risultato traceroute

Quando arriva `traceroute_result` via WebSocket:
1. `renderTraceroutePath(hops)` disegna linea gialla tratteggiata sopra le linee normali
2. Badge in alto a sinistra (sopra sidebar marker): "Traceroute: NomeNodo (N hop)" con link "Vedi" se si è su altra pagina

Il badge "Vedi sulla mappa" appare anche nella pagina nodi quando arriva un risultato: link a `/map?traceroute=!nodeId` che pre-carica l'ultimo traceroute.

### map.html — aggiornamenti struttura

```html
{% block content %}
<div id="map-wrapper" style="position:relative; height:100%; display:flex; flex-direction:column;">
  <!-- Sidebar marker (sinistra) -->
  <div id="marker-sidebar">...</div>
  <!-- Contenitore mappa -->
  <div id="map-container" style="flex:1; position:relative;"></div>
  <!-- Legenda (fondo) -->
  <div id="map-legend">...</div>
</div>
<script src="/static/map.js"></script>
{% endblock %}
```

---

## 4. Flusso Traceroute Completo

1. Utente long press su nodo Alpha → menu → "Traceroute"
2. Frontend: `POST /api/traceroute` `{node_id: "!a3f21b04"}`
3. Backend: `request_traceroute("!a3f21b04")` via Meshtastic
4. Rete Meshtastic: risposta traceroute torna come pacchetto
5. `_on_receive_traceroute()`: salva in DB, broadcast `traceroute_result`
6. `map.js`: `renderTraceroutePath(hops)` disegna percorso giallo
7. `nodes.html`: badge "Vedi sulla mappa" appare con link a `/map?traceroute=!a3f21b04`

---

## 5. Fuori Scope

- Animazione linee hop in tempo reale (movimento pacchetti)
- Heatmap copertura segnale
- Export mappa come immagine
- Storico posizioni nodo (breadcrumb trail)
- Cluster marker per aree dense
