# YAY-108 Mappa Percorsi Multi-Hop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migliorare la mappa con popup avanzati (RSSI, altitudine, ruolo, firmware), breadcrumb trail posizioni, linee traceroute colorate per qualità, e pannello filtri visibile per toggle routing/trail.

**Architecture:** Modifiche solo client-side in map.js (popup enhancement, breadcrumb rendering, filter panel UI) + piccola aggiunta in map.html per il pannello filtri. Nessuna modifica backend — i dati (rssi, altitude, role, firmware_version) sono già serviti dall'API /api/map/nodes grazie a YAY-107.

**Tech Stack:** Leaflet.js, JavaScript vanilla, CSS

---

## File Structure

| File | Responsabilità |
|------|---------------|
| `static/map.js` | Enhanced popup, breadcrumb trail, traceroute per-hop color, filter panel binding |
| `templates/map.html` | Filter panel HTML visibile nel right sidebar |

---

### Task 1: Enhanced node popup con campi avanzati

**Files:**
- Modify: `static/map.js`

- [ ] **Step 1: Aggiungere seconda riga stat box nel popup**

In `static/map.js`, nella funzione `showNodePopup()`, dopo il blocco stat boxes (circa riga 404, dopo `stats.append(...)`), aggiungere una seconda riga. Trovare:

```javascript
  popup.append(header, meta, heard, stats)
```

Sostituire con:

```javascript
  // Advanced stat boxes: RSSI, altitude, role, firmware
  var stats2 = document.createElement('div')
  stats2.style.cssText = 'display:flex;gap:5px;margin-top:4px;'
  stats2.append(
    makeStatBox(node.rssi != null ? node.rssi + ' dBm' : '\u2014', 'RSSI'),
    makeStatBox(node.altitude != null ? Math.round(node.altitude) + 'm' : '\u2014', 'Alt'),
    makeStatBox(node.role || '\u2014', 'Ruolo'),
    makeStatBox(node.firmware_version || '\u2014', 'FW')
  )

  popup.append(header, meta, heard, stats, stats2)
```

- [ ] **Step 2: Commit**

```bash
git add static/map.js
git commit -m "feat(map): add RSSI, altitude, role, firmware to node popup (YAY-108)"
```

---

### Task 2: Breadcrumb trail posizioni nodo

**Files:**
- Modify: `static/map.js`

La breadcrumb trail memorizza le ultime N posizioni per nodo e le disegna come una polyline sfumata. Nessun backend necessario — salviamo in memoria client-side (si resetta al reload pagina).

- [ ] **Step 1: Aggiungere stato breadcrumb e layer**

In `static/map.js`, dopo la riga `let customMarkersData = []` (riga 13), aggiungere:

```javascript
let breadcrumbLayer
const breadcrumbHistory = new Map()  // node_id → [{lat, lon, ts}, ...]
const BREADCRUMB_MAX = 20            // Max trail points per node
```

- [ ] **Step 2: Inizializzare breadcrumbLayer in initMapIfNeeded**

In `initMapIfNeeded()`, dopo `customMarkersLayer = L.layerGroup()` (riga 484), aggiungere:

```javascript
  breadcrumbLayer = L.layerGroup()
```

E dopo `customMarkersLayer.addTo(leafletMap)` (riga 543), aggiungere:

```javascript
  breadcrumbLayer.addTo(leafletMap)
```

- [ ] **Step 3: Aggiungere funzione per registrare posizione e renderizzare trail**

Dopo la funzione `renderHopLines()` (circa riga 151), aggiungere:

```javascript
function recordBreadcrumb(nodeId, lat, lon) {
  if (!lat || !lon) return
  var history = breadcrumbHistory.get(nodeId)
  if (!history) {
    history = []
    breadcrumbHistory.set(nodeId, history)
  }
  // Skip if same position as last point
  var last = history[history.length - 1]
  if (last && last.lat === lat && last.lon === lon) return
  history.push({ lat: lat, lon: lon, ts: Date.now() / 1000 })
  if (history.length > BREADCRUMB_MAX) history.shift()
}

function renderBreadcrumbs() {
  if (!mapReady || !breadcrumbLayer) return
  breadcrumbLayer.clearLayers()
  var f = loadFilters()
  if (!f.showBreadcrumbs) return
  breadcrumbHistory.forEach(function(history, nodeId) {
    if (history.length < 2) return
    var node = nodeCache.get(nodeId)
    if (!node || node.is_local) return
    // Draw trail segments with fading opacity
    for (var i = 0; i < history.length - 1; i++) {
      var opacity = 0.2 + (0.6 * (i / (history.length - 1)))
      var line = L.polyline(
        [[history[i].lat, history[i].lon], [history[i + 1].lat, history[i + 1].lon]],
        { color: '#4a9eff', weight: 2, opacity: opacity, dashArray: '4,4' }
      )
      breadcrumbLayer.addLayer(line)
    }
    // Circle at each trail point
    history.forEach(function(pt, idx) {
      var r = idx === history.length - 1 ? 4 : 2
      var circle = L.circleMarker([pt.lat, pt.lon], {
        radius: r, color: '#4a9eff', fillColor: '#4a9eff',
        fillOpacity: 0.2 + (0.6 * (idx / (history.length - 1))),
        weight: 1
      })
      breadcrumbLayer.addLayer(circle)
    })
  })
}
```

- [ ] **Step 4: Registrare posizioni negli event handler**

Nell'event listener `position-update` (alla fine del file, circa riga 633-641), aggiungere la registrazione breadcrumb. Trovare:

```javascript
window.addEventListener('position-update', function(e) {
  var d = e.detail
  var node = nodeCache.get(d.id)
  if (node) {
    node.latitude   = d.latitude
    node.longitude  = d.longitude
    node.last_heard = d.last_heard
    updateMapMarker(node)
  }
})
```

Sostituire con:

```javascript
window.addEventListener('position-update', function(e) {
  var d = e.detail
  var node = nodeCache.get(d.id)
  if (node) {
    node.latitude   = d.latitude
    node.longitude  = d.longitude
    node.last_heard = d.last_heard
    if (d.altitude != null) node.altitude = d.altitude
    recordBreadcrumb(d.id, d.latitude, d.longitude)
    updateMapMarker(node)
    renderBreadcrumbs()
  }
})
```

- [ ] **Step 5: Aggiungere showBreadcrumbs ai filtri di default**

In `DEFAULT_FILTERS`, aggiungere la nuova opzione. Trovare:

```javascript
const DEFAULT_FILTERS = {
  showOnline: true, showOffline: false,
  showHopLines: true, showCustomMarkers: true, showLocalNode: true,
  maxHops: 7,
}
```

Sostituire con:

```javascript
const DEFAULT_FILTERS = {
  showOnline: true, showOffline: false,
  showHopLines: true, showCustomMarkers: true, showLocalNode: true,
  showBreadcrumbs: true,
  maxHops: 7,
}
```

- [ ] **Step 6: Aggiungere breadcrumb layer toggle in applyFilters()**

In `applyFilters()`, dopo il blocco `showCustomMarkers`, aggiungere. Trovare:

```javascript
  if (f.showCustomMarkers) customMarkersLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(customMarkersLayer)
```

Aggiungere dopo:

```javascript
  if (breadcrumbLayer) {
    if (f.showBreadcrumbs) breadcrumbLayer.addTo(leafletMap)
    else                   leafletMap.removeLayer(breadcrumbLayer)
  }
```

- [ ] **Step 7: Inizializzare breadcrumb dai dati iniziali**

In `initMapIfNeeded()`, dopo `nodeCache.forEach(function(node) { updateMapMarker(node) })` (riga 545), aggiungere:

```javascript
  // Seed breadcrumb with current positions
  nodeCache.forEach(function(node) {
    if (node.latitude && node.longitude) {
      recordBreadcrumb(node.id, node.latitude, node.longitude)
    }
  })
```

- [ ] **Step 8: Commit**

```bash
git add static/map.js
git commit -m "feat(map): add breadcrumb trail for node position history (YAY-108)"
```

---

### Task 3: Traceroute linee colorate per qualità hop

**Files:**
- Modify: `static/map.js`

- [ ] **Step 1: Migliorare renderTraceroutePath con colori per-hop**

In `static/map.js`, sostituire l'intera funzione `renderTraceroutePath`. Trovare:

```javascript
function renderTraceroutePath(hops) {
  if (!mapReady) return
  tracerouteLayer.clearLayers()
  var latlngs = []
  hops.forEach(function(nodeId) {
    var n = nodeCache.get(nodeId)
    if (n && n.latitude && n.longitude) latlngs.push([n.latitude, n.longitude])
  })
  if (latlngs.length < 2) return
  L.polyline(latlngs, {
    color: '#ffd54f', weight: 4, opacity: 0.85, dashArray: '10,6'
  }).addTo(tracerouteLayer)
  for (var i = 0; i < latlngs.length - 1; i++) {
    var mid = [
      (latlngs[i][0] + latlngs[i + 1][0]) / 2,
      (latlngs[i][1] + latlngs[i + 1][1]) / 2,
    ]
    L.circleMarker(mid, {
      radius: 3, color: '#ffd54f', fillColor: '#ffd54f', fillOpacity: 1
    }).addTo(tracerouteLayer)
  }
  tracerouteLayer.addTo(leafletMap)
  var badge    = document.getElementById('traceroute-badge')
  var badgeTxt = document.getElementById('traceroute-badge-text')
  if (badge && badgeTxt) {
    var last = nodeCache.get(hops[hops.length - 1])
    var name = (last && last.short_name) ? last.short_name : hops[hops.length - 1]
    badgeTxt.textContent = 'Traceroute: ' + name + ' (' + (latlngs.length - 1) + ' hop)'
    badge.style.display = 'flex'
  }
}
```

Sostituire con:

```javascript
function renderTraceroutePath(hops) {
  if (!mapReady) return
  tracerouteLayer.clearLayers()
  // Build array of {latlng, node} for each hop
  var hopNodes = []
  hops.forEach(function(nodeId) {
    var n = nodeCache.get(nodeId)
    if (n && n.latitude && n.longitude) {
      hopNodes.push({ latlng: [n.latitude, n.longitude], node: n })
    }
  })
  if (hopNodes.length < 2) return

  // Draw per-hop segments colored by SNR of destination node
  for (var i = 0; i < hopNodes.length - 1; i++) {
    var destNode = hopNodes[i + 1].node
    var color = snrColor(destNode.snr)
    L.polyline(
      [hopNodes[i].latlng, hopNodes[i + 1].latlng],
      { color: color, weight: 4, opacity: 0.85, dashArray: '10,6' }
    ).addTo(tracerouteLayer)

    // Midpoint marker with hop number
    var mid = [
      (hopNodes[i].latlng[0] + hopNodes[i + 1].latlng[0]) / 2,
      (hopNodes[i].latlng[1] + hopNodes[i + 1].latlng[1]) / 2,
    ]
    var hopLabel = L.divIcon({
      html: '<div style="width:16px;height:16px;background:' + color +
            ';border-radius:50%;border:1px solid #fff;display:flex;align-items:center;' +
            'justify-content:center;font-size:8px;font-weight:700;color:#fff;">' +
            (i + 1) + '</div>',
      className: '',
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    })
    L.marker(mid, { icon: hopLabel, interactive: false }).addTo(tracerouteLayer)
  }

  // Node markers at hop endpoints with SNR tooltip
  hopNodes.forEach(function(hp, idx) {
    if (idx === 0) return  // skip source
    var tip = (hp.node.short_name || hp.node.id) +
      (hp.node.snr != null ? ' · SNR ' + hp.node.snr + 'dB' : '') +
      (hp.node.rssi != null ? ' · RSSI ' + hp.node.rssi + 'dBm' : '')
    L.circleMarker(hp.latlng, {
      radius: 5, color: snrColor(hp.node.snr), fillColor: snrColor(hp.node.snr),
      fillOpacity: 0.9, weight: 2
    }).bindTooltip(tip, { permanent: false, direction: 'top', offset: [0, -8] })
      .addTo(tracerouteLayer)
  })

  tracerouteLayer.addTo(leafletMap)
  var badge    = document.getElementById('traceroute-badge')
  var badgeTxt = document.getElementById('traceroute-badge-text')
  if (badge && badgeTxt) {
    var last = nodeCache.get(hops[hops.length - 1])
    var name = (last && last.short_name) ? last.short_name : hops[hops.length - 1]
    badgeTxt.textContent = 'Traceroute: ' + name + ' (' + (hopNodes.length - 1) + ' hop)'
    badge.style.display = 'flex'
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add static/map.js
git commit -m "feat(map): color traceroute segments by per-hop SNR quality (YAY-108)"
```

---

### Task 4: Pannello filtri visibile nella UI mappa

**Files:**
- Modify: `templates/map.html`
- Modify: `static/map.js`

- [ ] **Step 1: Aggiungere HTML pannello filtri in map.html**

In `templates/map.html`, trovare il right panel (è un div collassabile con id `right-panel`). Il pannello attualmente contiene la lista marker personalizzati. Aggiungere i filtri sopra. Trovare il contenuto del pannello (cercando `id="right-panel"` o il primo `<div>` dentro il pannello laterale che contiene `marker-list`).

Se il right panel è vuoto o contiene solo il marker sidebar, aggiungere prima del marker list il seguente blocco filtri. Aggiungere subito dopo l'apertura del right-panel:

```html
        <!-- Filtri mappa -->
        <div id="filter-panel" style="padding:8px;border-bottom:1px solid var(--border,#2a3a4a);">
          <div style="font-size:9px;font-weight:700;text-transform:uppercase;color:var(--accent,#4a9eff);margin-bottom:6px;">Filtri</div>
          <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
            <input type="checkbox" id="filter-online" style="accent-color:var(--accent,#4a9eff);"> Online
          </label>
          <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
            <input type="checkbox" id="filter-offline" style="accent-color:var(--accent,#4a9eff);"> Offline
          </label>
          <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
            <input type="checkbox" id="filter-hoplines" style="accent-color:var(--accent,#4a9eff);"> Linee hop
          </label>
          <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
            <input type="checkbox" id="filter-breadcrumbs" style="accent-color:var(--accent,#4a9eff);"> Tracce GPS
          </label>
          <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
            <input type="checkbox" id="filter-markers" style="accent-color:var(--accent,#4a9eff);"> Marker
          </label>
          <label style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-bottom:4px;cursor:pointer;">
            <input type="checkbox" id="filter-local" style="accent-color:var(--accent,#4a9eff);"> Nodo locale
          </label>
          <div style="display:flex;align-items:center;gap:5px;font-size:10px;color:var(--text,#ccc);margin-top:4px;">
            <span>Max hops:</span>
            <input type="range" id="filter-maxhops" min="1" max="10" style="flex:1;accent-color:var(--accent,#4a9eff);">
            <span id="filter-maxhops-val" style="min-width:14px;text-align:right;">7</span>
          </div>
        </div>
```

- [ ] **Step 2: Aggiungere binding filtro breadcrumbs in initFilters()**

In `static/map.js`, nella funzione `initFilters()`, dopo `bindCheckbox('filter-markers',  'showCustomMarkers')` (riga 117), aggiungere:

```javascript
  bindCheckbox('filter-breadcrumbs', 'showBreadcrumbs')
```

E nella callback `onchange` dei checkbox, aggiungere `renderBreadcrumbs()`. Trovare:

```javascript
    el.onchange = function() {
      var nf = loadFilters()
      nf[key] = el.checked
      saveFilters(nf)
      applyFilters()
      renderHopLines()
    }
```

Sostituire con:

```javascript
    el.onchange = function() {
      var nf = loadFilters()
      nf[key] = el.checked
      saveFilters(nf)
      applyFilters()
      renderHopLines()
      renderBreadcrumbs()
    }
```

- [ ] **Step 3: Commit**

```bash
git add templates/map.html static/map.js
git commit -m "feat(map): add visible filter panel with hop lines, breadcrumbs, markers toggles (YAY-108)"
```

---

### Task 5: Deploy e test

**Files:** Nessun file da modificare

- [ ] **Step 1: Deploy sul Pi**

```bash
sshpass -p pimesh rsync -avz --relative \
  static/map.js templates/map.html \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Verificare con Playwright**

- Navigare a `http://192.168.1.36:8080/map`
- Screenshot a 320x480 portrait
- Cliccare su un nodo marker e verificare che il popup mostra RSSI/Alt/Ruolo/FW
- Aprire il pannello laterale e verificare che i filtri sono visibili
- Toggle "Linee hop" off e verificare che le linee spariscono
- Screenshot a 480x320 landscape

- [ ] **Step 3: Commit finale se necessario**
