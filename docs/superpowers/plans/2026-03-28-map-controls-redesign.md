# Map Controls Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix map pan/zoom blocking, replace oversized layer switcher with compact SVG icon buttons, group all controls to the right side, and show nodes with their short_name label.

**Architecture:** All changes are frontend-only. `map.js` handles Leaflet logic (bounds, markers). `map.html` handles the DOM layout (controls, layer switcher). No new files needed. Cache busting via service worker version bump.

**Tech Stack:** Leaflet.js (map), vanilla JS, Jinja2 templates, service worker cache

---

## File Map

- Modify: `static/map.js` — remove maxBounds, remove L.control.layers(), rewrite updateMapMarker() to use divIcon with label
- Modify: `templates/map.html` — add custom layer switcher, move btn-center-board to bottom-right, set opacity 0.55 on all overlay buttons
- Modify: `static/sw.js` — bump CACHE_VERSION to invalidate browser cache
- Modify: `static/app.js` — bump sw version string if present (check first)

---

### Task 1: Remove map pan/zoom restriction

**Files:**
- Modify: `static/map.js:357-363`

- [ ] **Step 1: Remove maxBounds and minZoom from L.map constructor**

In `static/map.js`, find the `L.map('map-container', {...})` call (around line 357) and remove `maxBounds`, `maxBoundsViscosity`, and `minZoom` from the options object. Keep only `center`, `zoom`, `zoomControl: false`, `maxZoom`, and `tap: true`.

Replace this block:
```javascript
  leafletMap = L.map('map-container', {
    center: center, zoom: zoom, zoomControl: false,
    minZoom: zoomMin, maxZoom: zoomMax,
    maxBounds: [[bounds.lat_min, bounds.lon_min], [bounds.lat_max, bounds.lon_max]],
    maxBoundsViscosity: 1.0,
    tap: true,
  })
```

With:
```javascript
  leafletMap = L.map('map-container', {
    center: center, zoom: zoom, zoomControl: false,
    maxZoom: zoomMax,
    tap: true,
  })
```

- [ ] **Step 2: Remove minZoom from tileOpts**

Same file, find:
```javascript
  var tileOpts       = { minZoom: zoomMin, maxZoom: zoomMax }
```
Replace with:
```javascript
  var tileOpts       = { maxZoom: zoomMax }
```

- [ ] **Step 3: Remove L.control.layers() call**

Find and delete this line:
```javascript
  L.control.layers({ 'Stradale': osmLayer, 'Topo': topoLayer, 'Satellite': satelliteLayer }).addTo(leafletMap)
```

- [ ] **Step 4: Expose tile layers as module-level variables**

The custom layer switcher buttons in map.html will need to call `leafletMap.removeLayer()` / `.addTo()`. Promote the three layer variables to module scope by changing their declarations from `var` to assignments on pre-declared variables.

At the top of `static/map.js`, after the existing global declarations (after line 13), add:
```javascript
let osmLayer = null
let topoLayer = null
let satelliteLayer = null
let activeLayer = null
```

Then inside `initMapIfNeeded()`, change the three `var` declarations:
```javascript
  // BEFORE:
  var osmLayer       = L.tileLayer('/tiles/osm/{z}/{x}/{y}',       tileOpts)
  var topoLayer      = L.tileLayer('/tiles/topo/{z}/{x}/{y}',      tileOpts)
  var satelliteLayer = L.tileLayer('/tiles/satellite/{z}/{x}/{y}', tileOpts)
  osmLayer.addTo(leafletMap)

  // AFTER:
  osmLayer       = L.tileLayer('/tiles/osm/{z}/{x}/{y}',       tileOpts)
  topoLayer      = L.tileLayer('/tiles/topo/{z}/{x}/{y}',      tileOpts)
  satelliteLayer = L.tileLayer('/tiles/satellite/{z}/{x}/{y}', tileOpts)
  activeLayer    = osmLayer
  osmLayer.addTo(leafletMap)
```

- [ ] **Step 5: Add switchLayer global function**

After the `centerOnBoard()` function in `static/map.js`, add:
```javascript
function switchLayer(name) {
  if (!mapReady) return
  var layers = { osm: osmLayer, topo: topoLayer, satellite: satelliteLayer }
  var next = layers[name]
  if (!next || next === activeLayer) return
  leafletMap.removeLayer(activeLayer)
  next.addTo(leafletMap)
  activeLayer = next
  // Update button highlight
  document.querySelectorAll('.layer-btn').forEach(function(btn) {
    var on = btn.dataset.layer === name
    btn.style.borderColor = on ? 'var(--accent,#4a9eff)' : 'rgba(42,58,74,0.5)'
    btn.style.color = on ? 'var(--accent,#4a9eff)' : 'var(--text,#ccc)'
  })
}
```

- [ ] **Step 6: Commit**

```bash
git add static/map.js
git commit -m "fix: remove map maxBounds restriction and expose layer switching"
```

---

### Task 2: Rewrite node markers with short_name label

**Files:**
- Modify: `static/map.js` — `updateMapMarker()` function (~line 414)

- [ ] **Step 1: Replace circleMarker with labeled divIcon**

Find the `updateMapMarker` function. Replace the marker creation block (inside the `else` branch) with:

```javascript
    var online  = (Date.now() / 1000 - (node.last_heard || 0)) < 1800
    var bgColor = node.is_local ? '#4a9eff' : (online ? '#4caf50' : '#555')
    var glow    = node.is_local ? 'box-shadow:0 0 8px #4a9eff;' : ''
    var label   = escHtml(String(node.short_name || node.id).slice(0, 6))
    var icon = L.divIcon({
      html: '<div style="width:34px;height:34px;background:' + bgColor +
            ';border-radius:50%;border:2px solid #fff;' + glow +
            'display:flex;align-items:center;justify-content:center;' +
            'font-size:9px;font-weight:700;color:#fff;font-family:monospace;' +
            'box-sizing:border-box;">' + label + '</div>',
      className: '',
      iconSize:   [34, 34],
      iconAnchor: [17, 17],
    })
    var marker = L.marker([node.latitude, node.longitude], { icon: icon })
    marker.bindPopup(
      '<b>' + escHtml(String(node.short_name || node.id)) + '</b><br>' +
      escHtml(String(node.long_name || '')) + '<br>' +
      'SNR: ' + escHtml(String(node.snr != null ? node.snr : '\u2014')) + ' dB<br>' +
      'Batt: ' + escHtml(String(node.battery_level != null ? node.battery_level : '\u2014')) + '%'
    )
    initNodeContextMenu(marker, node)
    marker.addTo(leafletMap)
    markerCache.set(node.id, marker)
```

The full updated function should be:
```javascript
function updateMapMarker(node) {
  if (!node.latitude || !node.longitude || !mapReady) return
  var existing = markerCache.get(node.id)
  if (existing) {
    existing.setLatLng([node.latitude, node.longitude])
  } else {
    var online  = (Date.now() / 1000 - (node.last_heard || 0)) < 1800
    var bgColor = node.is_local ? '#4a9eff' : (online ? '#4caf50' : '#555')
    var glow    = node.is_local ? 'box-shadow:0 0 8px #4a9eff;' : ''
    var label   = escHtml(String(node.short_name || node.id).slice(0, 6))
    var icon = L.divIcon({
      html: '<div style="width:34px;height:34px;background:' + bgColor +
            ';border-radius:50%;border:2px solid #fff;' + glow +
            'display:flex;align-items:center;justify-content:center;' +
            'font-size:9px;font-weight:700;color:#fff;font-family:monospace;' +
            'box-sizing:border-box;">' + label + '</div>',
      className: '',
      iconSize:   [34, 34],
      iconAnchor: [17, 17],
    })
    var marker = L.marker([node.latitude, node.longitude], { icon: icon })
    marker.bindPopup(
      '<b>' + escHtml(String(node.short_name || node.id)) + '</b><br>' +
      escHtml(String(node.long_name || '')) + '<br>' +
      'SNR: ' + escHtml(String(node.snr != null ? node.snr : '\u2014')) + ' dB<br>' +
      'Batt: ' + escHtml(String(node.battery_level != null ? node.battery_level : '\u2014')) + '%'
    )
    initNodeContextMenu(marker, node)
    marker.addTo(leafletMap)
    markerCache.set(node.id, marker)
  }
  renderHopLines()
  applyFilters()
}
```

- [ ] **Step 2: Commit**

```bash
git add static/map.js
git commit -m "feat: node markers now show short_name label via divIcon"
```

---

### Task 3: Redesign map.html controls layout

**Files:**
- Modify: `templates/map.html`

- [ ] **Step 1: Update panel toggle button opacity**

Find the `#panel-toggle` button in `map.html`. Change its background from `rgba(10,12,20,0.92)` to `rgba(10,12,20,0.55)` and its border from `1px solid var(--border)` to `1px solid rgba(42,58,74,0.5)`:

```html
  <button id="panel-toggle"
          style="position:absolute;top:6px;right:6px;z-index:1000;
                 width:32px;height:32px;padding:0;
                 display:flex;align-items:center;justify-content:center;
                 background:rgba(10,12,20,0.55);border:1px solid rgba(42,58,74,0.5);
                 border-radius:4px;color:var(--text,#ccc);
                 -webkit-tap-highlight-color:transparent;">
```

- [ ] **Step 2: Add compact layer switcher below panel toggle**

Immediately after the closing `</button>` of `#panel-toggle`, add the layer switcher widget. Uses SVG icons — no emoji:

```html
  <!-- Layer switcher compatto (sotto panel toggle) -->
  <div style="position:absolute;top:46px;right:6px;z-index:1000;
              background:rgba(10,12,20,0.55);border:1px solid rgba(42,58,74,0.5);
              border-radius:4px;overflow:hidden;width:32px;">
    <button class="layer-btn" data-layer="osm" onclick="switchLayer('osm')"
            title="Stradale"
            style="width:100%;height:28px;padding:0;border:none;border-bottom:1px solid rgba(42,58,74,0.4);
                   background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
                   color:var(--accent,#4a9eff);border-color:var(--accent,#4a9eff);
                   -webkit-tap-highlight-color:transparent;">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
      </svg>
    </button>
    <button class="layer-btn" data-layer="topo" onclick="switchLayer('topo')"
            title="Topo"
            style="width:100%;height:28px;padding:0;border:none;border-bottom:1px solid rgba(42,58,74,0.4);
                   background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
                   color:var(--text,#ccc);
                   -webkit-tap-highlight-color:transparent;">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 21l5-10 5 5 4-7 4 12"/>
      </svg>
    </button>
    <button class="layer-btn" data-layer="satellite" onclick="switchLayer('satellite')"
            title="Satellite"
            style="width:100%;height:28px;padding:0;border:none;
                   background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
                   color:var(--text,#ccc);
                   -webkit-tap-highlight-color:transparent;">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="3"/>
        <path stroke-linecap="round" stroke-linejoin="round" d="M6.3 6.3l11.4 11.4M17.7 6.3L6.3 17.7"/>
      </svg>
    </button>
  </div>
```

- [ ] **Step 3: Move btn-center-board to bottom-right, above zoom**

Find the `#btn-center-board` button. Change its position from `bottom:6px;left:6px` to `bottom:70px;right:6px` (above Leaflet zoom which occupies ~60px from bottom). Also update opacity to 0.55:

```html
  <button id="btn-center-board" onclick="centerOnBoard()" title="Centra sulla board"
          style="position:absolute;bottom:70px;right:6px;z-index:1000;
                 width:32px;height:32px;min-height:32px;padding:0;
                 display:flex;align-items:center;justify-content:center;
                 background:rgba(10,12,20,0.55);border:1px solid rgba(42,58,74,0.5);
                 border-radius:4px;cursor:pointer;color:var(--text,#ccc);
                 -webkit-tap-highlight-color:transparent;">
```

- [ ] **Step 4: Override Leaflet zoom control opacity**

In the `<style>` block at the top of `map.html`, add CSS to override the default Leaflet zoom control appearance:

```css
  .leaflet-control-zoom a {
    background: rgba(10,12,20,0.55) !important;
    border-color: rgba(42,58,74,0.5) !important;
    color: var(--text,#ccc) !important;
  }
  .leaflet-control-zoom a:hover {
    background: rgba(10,12,20,0.8) !important;
  }
```

- [ ] **Step 5: Commit**

```bash
git add templates/map.html
git commit -m "feat: redesign map controls — compact layer switcher, grouped right-side layout, opacity 0.55"
```

---

### Task 4: Bump cache version and deploy

**Files:**
- Modify: `static/sw.js` — bump CACHE_VERSION
- Modify: `templates/map.html` — bump `?v=` query string on map.js script tag

- [ ] **Step 1: Check current cache version in sw.js**

Read `static/sw.js` and find the `CACHE_VERSION` or `CACHE_NAME` constant. Note current version number.

- [ ] **Step 2: Bump sw.js cache version by 1**

In `static/sw.js`, increment the version number by 1 (e.g. `v6` → `v7`). This forces all clients to re-fetch assets.

- [ ] **Step 3: Bump map.js script tag version in map.html**

In `templates/map.html`, find:
```html
<script src="/static/map.js?v=4"></script>
```
Increment the version number by 1:
```html
<script src="/static/map.js?v=5"></script>
```

- [ ] **Step 4: Deploy to Pi**

```bash
rsync -av --exclude='.git' --exclude='__pycache__' \
  static/map.js static/sw.js templates/map.html \
  pimesh@raspberrypi.local:/home/pimesh/pi-Mesh/static/ 2>/dev/null || \
rsync -av static/map.js static/sw.js templates/map.html \
  pi@raspberrypi.local:/home/pi/pi-Mesh/static/
```

Verify service is running:
```bash
ssh pimesh@raspberrypi.local "sudo systemctl status pimesh --no-pager -l | tail -5"
```

- [ ] **Step 5: Commit**

```bash
git add static/sw.js templates/map.html
git commit -m "chore: bump cache version to v7 for map controls redesign"
```

---

### Task 5: Node info popup (stile Meshtastic.org)

**Files:**
- Modify: `static/map.js` — aggiungere formatAgo(), showNodePopup(), collegare al click marker
- Modify: `templates/map.html` — aggiungere #node-popup nel DOM

**Comportamento:** click su nodo → popup flottante posizionato accanto al marker, con avatar colorato, nome, hardware, last heard, hops, SNR, battery. Chiusura su ✕ o click fuori. Popup costruito con metodi DOM (createElement/textContent) per sicurezza XSS.

- [ ] **Step 1: Aggiungere #node-popup al DOM in map.html**

Subito prima del tag `<script src="/static/map.js?v=...">`, inserire:

```html
<div id="node-popup"
     style="display:none;position:absolute;z-index:900;
            background:rgba(10,12,20,0.96);border:1px solid var(--border,#2a3a4a);
            border-radius:6px;padding:10px;width:190px;
            box-shadow:0 4px 16px rgba(0,0,0,0.6);font-size:10px;pointer-events:auto;">
</div>
```

- [ ] **Step 2: Aggiungere formatAgo() in map.js**

Aggiungere dopo `closeContextMenu()`:

```javascript
function formatAgo(ts) {
  if (!ts) return 'mai'
  var sec = Math.floor(Date.now() / 1000 - ts)
  if (sec < 60)   return sec + 's fa'
  if (sec < 3600) return Math.floor(sec / 60) + ' min fa'
  return Math.floor(sec / 3600) + 'h fa'
}
```

- [ ] **Step 3: Aggiungere showNodePopup() in map.js**

Aggiungere subito dopo `formatAgo()`. Usa createElement/textContent per sicurezza XSS:

```javascript
function makeStatBox(value, label) {
  var box = document.createElement('div')
  box.style.cssText = 'background:var(--panel,#12151f);border-radius:3px;padding:4px 6px;text-align:center;flex:1;'
  var v = document.createElement('div')
  v.style.cssText = 'color:var(--text,#ccc);font-weight:700;font-size:11px;'
  v.textContent = value
  var l = document.createElement('div')
  l.style.cssText = 'color:var(--muted,#666);font-size:8px;'
  l.textContent = label
  box.append(v, l)
  return box
}

function showNodePopup(marker, node) {
  var popup = document.getElementById('node-popup')
  if (!popup) return
  popup.textContent = ''

  var online  = (Date.now() / 1000 - (node.last_heard || 0)) < 1800
  var bgColor = node.is_local ? '#4a9eff' : (online ? '#4caf50' : '#555')
  var glow    = node.is_local ? 'box-shadow:0 0 8px #4a9eff;' : ''
  var label   = String(node.short_name || node.id).slice(0, 6)

  // Header: avatar + nomi + close
  var header = document.createElement('div')
  header.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:7px;'

  var avatar = document.createElement('div')
  avatar.style.cssText = 'width:32px;height:32px;background:' + bgColor + ';border-radius:50%;' +
    'border:2px solid #fff;' + glow + 'display:flex;align-items:center;justify-content:center;' +
    'font-size:9px;font-weight:700;color:#fff;flex-shrink:0;font-family:monospace;box-sizing:border-box;'
  avatar.textContent = label

  var names = document.createElement('div')
  names.style.cssText = 'flex:1;min-width:0;'
  var longName = document.createElement('div')
  longName.style.cssText = 'color:var(--text,#ccc);font-weight:600;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
  longName.textContent = node.long_name || node.short_name || node.id
  names.appendChild(longName)
  if (node.hw_model || node.hardware) {
    var hw = document.createElement('div')
    hw.style.cssText = 'color:var(--accent,#4a9eff);font-size:9px;'
    hw.textContent = node.hw_model || node.hardware
    names.appendChild(hw)
  }

  var closeBtn = document.createElement('button')
  closeBtn.style.cssText = 'background:none;border:none;color:var(--muted,#666);cursor:pointer;padding:2px;flex-shrink:0;display:flex;'
  closeBtn.title = 'Chiudi'
  closeBtn.appendChild((function() {
    var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    s.setAttribute('width', '12'); s.setAttribute('height', '12')
    s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none')
    s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2.5')
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round')
    p.setAttribute('d', 'M6 18L18 6M6 6l12 12')
    s.appendChild(p); return s
  })())
  closeBtn.onclick = function(e) { e.stopPropagation(); popup.style.display = 'none' }
  header.append(avatar, names, closeBtn)

  // Riga short_name + id
  var meta = document.createElement('div')
  meta.style.cssText = 'color:var(--muted,#888);font-size:9px;margin-bottom:3px;'
  meta.textContent = '*' + (node.short_name || '') + '* \u00b7 ' + node.id

  // Last heard
  var heard = document.createElement('div')
  heard.style.cssText = 'color:var(--muted,#888);font-size:9px;margin-bottom:7px;'
  heard.textContent = 'Sentito ' + formatAgo(node.last_heard)

  // Stat boxes
  var stats = document.createElement('div')
  stats.style.cssText = 'display:flex;gap:5px;'
  stats.append(
    makeStatBox(node.hop_count != null ? node.hop_count : '\u2014', 'Hops'),
    makeStatBox(node.snr      != null ? node.snr + ' dB'           : '\u2014', 'SNR'),
    makeStatBox(node.battery_level != null ? node.battery_level + '%' : '\u2014', 'Batt')
  )

  popup.append(header, meta, heard, stats)

  // Posiziona accanto al marker
  var pt    = leafletMap.latLngToContainerPoint(marker.getLatLng())
  var mapEl = document.getElementById('map-container')
  var pw    = 200
  var left  = pt.x + 20
  if (left + pw > mapEl.offsetWidth - 10) left = pt.x - pw - 10
  popup.style.left    = left + 'px'
  popup.style.top     = Math.max(6, pt.y - 60) + 'px'
  popup.style.display = 'block'

  // Chiudi cliccando fuori
  setTimeout(function() {
    document.addEventListener('click', function closePopup(e) {
      if (!popup.contains(e.target)) {
        popup.style.display = 'none'
        document.removeEventListener('click', closePopup)
      }
    })
  }, 50)
}
```

- [ ] **Step 4: Collegare showNodePopup al click marker in updateMapMarker**

In `updateMapMarker()`, rimuovere la chiamata `marker.bindPopup(...)` e aggiungere:
```javascript
    marker.on('click', function() { showNodePopup(marker, node) })
```

- [ ] **Step 5: Commit**

```bash
git add static/map.js templates/map.html
git commit -m "feat: node info popup with avatar, hardware, hops, SNR, last heard"
```
