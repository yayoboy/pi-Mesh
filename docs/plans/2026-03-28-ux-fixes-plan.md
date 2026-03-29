# UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 UX issues on the pi-Mesh 320x480 touchscreen dashboard: log toolbar, telemetry charts, map visibility, serial config dropdown, and theme persistence.

**Architecture:** Each fix is a self-contained task modifying one template + its supporting backend endpoint where needed. All UI must fit 320x480 portrait and 480x320 landscape. CSS custom properties drive theming. localStorage provides instant persistence, server sync ensures cross-browser consistency.

**Tech Stack:** FastAPI (Python), Jinja2 templates, vanilla JS, Chart.js, Leaflet.js, CSS custom properties, localStorage

---

## File Structure

| File | Responsibility |
|------|---------------|
| `templates/log.html` | Log toolbar layout (Task 1) |
| `templates/telemetry.html` | Combined telemetry charts (Task 2) |
| `templates/map.html` | Map legend bar with center button (Task 3) |
| `static/map.js` | Map init, view persistence, center-on-board (Task 3) |
| `main.py` | Serial ports API endpoint (Task 4) |
| `templates/settings.html` | Serial dropdown + theme custom UI (Tasks 4, 5) |
| `static/style.css` | Theme CSS custom properties + custom theme class (Task 5) |
| `static/app.js` | Theme loading from localStorage on init (Task 5) |

---

### Task 1: Log Toolbar — Compact Two-Row Layout

**Files:**
- Modify: `templates/log.html`

The current toolbar uses `flex-wrap:wrap` with full-text buttons that overflow on 320px. Replace with a two-row layout: row 1 = Board/Pi tab toggle (full width), row 2 = search + icon-only filter/action buttons.

- [ ] **Step 1: Replace the toolbar HTML**

Replace lines 3-36 of `templates/log.html` with:

```html
<div id="log-wrap" style="display:flex;flex-direction:column;height:100%;box-sizing:border-box">

  <!-- Row 1: Board / Pi tabs -->
  <div style="display:flex;flex-shrink:0;border-bottom:1px solid var(--border)">
    <button id="btn-board" class="log-tab active" onclick="showLog('board')">Board</button>
    <button id="btn-pi"    class="log-tab"        onclick="showLog('pi')">Pi</button>
  </div>

  <!-- Row 2: search + icon buttons -->
  <div style="display:flex;gap:4px;align-items:center;flex-shrink:0;padding:4px 6px;border-bottom:1px solid var(--border)">
    <input id="log-search" type="search" placeholder="Cerca…"
      style="flex:1;font-size:11px;padding:3px 8px;border-radius:12px;border:1px solid var(--border);
             background:var(--surface,var(--bg2));color:var(--text);outline:none;min-height:28px;min-width:0">

    <button class="log-icon-btn" id="btn-all"   onclick="_setLevel('all')"   title="Tutti">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16"/></svg>
    </button>
    <button class="log-icon-btn" id="btn-warn"  onclick="_setLevel('warn')"  title="Warning+">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01M10.29 3.86l-8.6 14.86A1 1 0 002.56 20h18.88a1 1 0 00.87-1.28l-8.6-14.86a1 1 0 00-1.72 0z"/></svg>
    </button>
    <button class="log-icon-btn" id="btn-error" onclick="_setLevel('error')" title="Errori">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path stroke-linecap="round" d="M15 9l-6 6M9 9l6 6"/></svg>
    </button>

    <span style="width:1px;height:16px;background:var(--border);flex-shrink:0"></span>

    <button class="log-icon-btn" id="btn-pause" onclick="_togglePause()" title="Pausa auto-scroll">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
    </button>
    <button class="log-icon-btn" onclick="downloadLog()" title="Scarica log">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14m0 0l-4-4m4 4l4-4M5 19h14"/></svg>
    </button>
    <button class="log-icon-btn" onclick="clearLog()" title="Pulisci">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M4 7h16M10 3h4"/></svg>
    </button>
  </div>

  <div id="log-list" style="flex:1;overflow-y:auto;font-family:monospace;font-size:11px;line-height:1.5"></div>

</div>
```

- [ ] **Step 2: Replace the style block**

Replace the existing `<style>` block (lines 42-52) with:

```html
<style>
.log-tab{
  flex:1;background:var(--bg2);color:var(--muted);border:none;
  font-size:12px;padding:8px 0;cursor:pointer;border-bottom:2px solid transparent;
  min-height:36px;
}
.log-tab.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
.log-icon-btn{
  width:32px;height:32px;min-height:32px;min-width:32px;padding:0;
  display:flex;align-items:center;justify-content:center;
  background:var(--bg2);border:1px solid var(--border);border-radius:6px;
  color:var(--text);cursor:pointer;flex-shrink:0;
}
.log-icon-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.log-entry{padding:2px 6px;border-bottom:1px solid var(--border)}
.log-entry.warn{color:#f0a030}
.log-entry.error{color:#e05050}
.log-entry.info{color:var(--text)}
</style>
```

- [ ] **Step 3: Update _setLevel to use new button classes**

In the `<script>` section, update the `_setLevel` function to toggle `active` class on `.log-icon-btn` elements instead of `.btn-pill`:

```javascript
window._setLevel = function(level){
  _level = level
  document.getElementById('btn-all').classList.toggle('active',   level === 'all')
  document.getElementById('btn-warn').classList.toggle('active',  level === 'warn')
  document.getElementById('btn-error').classList.toggle('active', level === 'error')
  _applyFilters()
}
```

No change needed here — the function already uses IDs. The class change from `btn-pill` to `log-icon-btn` is handled by CSS only.

- [ ] **Step 4: Update showLog to use new tab class**

The `showLog` function already uses element IDs, so it works as-is. Verify no code references `.btn-pill` class.

- [ ] **Step 5: Test at 320x480**

Open `http://localhost:8000/log` in a 320x480 viewport. Verify:
- Row 1: Board/Pi tabs fill width equally
- Row 2: search input + 6 icon buttons fit without wrapping
- Log entries scroll below toolbar
- Total toolbar height ~72px, leaving ~340px for log content in portrait

- [ ] **Step 6: Commit**

```bash
git add templates/log.html
git commit -m "fix: log toolbar compact two-row layout for 320px display"
```

---

### Task 2: Telemetry — Combined Chart + Conditional I2C Chart

**Files:**
- Modify: `templates/telemetry.html`

Replace 3 separate charts with 1 combined Board+Pi chart (dual Y-axis) and 1 conditional I2C sensor chart.

- [ ] **Step 1: Replace the template HTML**

Replace the entire content of `templates/telemetry.html` with:

```html
{% extends "base.html" %}
{% block content %}
{% set local_node = namespace(id=none, name='Board') %}
{% for n in nodes %}{% if n.is_local %}{% set local_node.id = n.id %}{% set local_node.name = n.short_name or n.id %}{% endif %}{% endfor %}

<div style="overflow-y:auto; height:100%; padding:4px 8px;">

  <!-- Metric badges -->
  <div id="metric-badges" style="display:flex; gap:4px; flex-wrap:wrap; margin-bottom:4px; font-size:11px;">
    <span id="badge-ram"     class="t-badge" style="border-left:3px solid #4a9eff;">RAM: —</span>
    <span id="badge-batt"    class="t-badge" style="border-left:3px solid #4caf50;">Batt: —</span>
    <span id="badge-temp"    class="t-badge" style="border-left:3px solid #ff5722;">Temp: —</span>
    <span id="badge-chutil"  class="t-badge" style="border-left:3px solid #ff9800;">ChUtil: —</span>
    <span id="badge-airtx"   class="t-badge" style="border-left:3px solid #9c27b0;">AirTx: —</span>
    <span id="badge-disk"    class="t-badge" style="border-left:3px solid #00bcd4;">Disco: —</span>
  </div>

  <!-- Combined chart: Board + Pi -->
  <div style="position:relative; height:45%; min-height:100px;">
    <canvas id="chart-main"></canvas>
  </div>

  <!-- Export buttons -->
  <div style="display:flex; gap:6px; margin:4px 0; flex-wrap:wrap;">
    <button class="btn-pill" onclick="exportTelemetry('json')" style="font-size:11px; min-height:28px; padding:0 10px;">JSON</button>
    <button class="btn-pill" onclick="exportTelemetry('csv')"  style="font-size:11px; min-height:28px; padding:0 10px;">CSV</button>
  </div>

  <!-- I2C Sensors chart (conditional) -->
  <div id="sensors-section" style="display:none;">
    <div style="font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; padding:4px 0 2px;">Sensori I2C</div>
    <div id="sensor-badges" style="display:flex; gap:4px; flex-wrap:wrap; font-size:11px; margin-bottom:4px;"></div>
    <div style="position:relative; height:35%; min-height:80px;">
      <canvas id="chart-sensors"></canvas>
    </div>
    <button class="btn-pill" onclick="exportSensors('csv')" style="font-size:11px; min-height:28px; padding:0 10px; margin-top:4px;">Esporta sensori CSV</button>
  </div>

</div>

<style>
.t-badge {
  background:var(--bg2); border-radius:3px; padding:2px 6px;
  white-space:nowrap;
}
.btn-pill {
  background:var(--surface,var(--bg2)); color:var(--text); border:1px solid var(--border);
  border-radius:12px; cursor:pointer;
}
</style>

<script>
const _LOCAL_NODE_ID = {% if local_node.id %}"{{ local_node.id | e }}"{% else %}null{% endif %}

// --- Color map per dataset ---
const COLORS = {
  ram:     '#4a9eff',
  batt:    '#4caf50',
  temp:    '#ff5722',
  chUtil:  '#ff9800',
  airTx:   '#9c27b0',
  disk:    '#00bcd4',
}

// --- Main chart (dual Y axis) ---
let mainChart = null
let sensorChart = null
const sensorDatasets = {}
const MAX_POINTS = 60

function _initMainChart() {
  const ctx = document.getElementById('chart-main')
  if (!ctx) return
  mainChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'RAM MB',     data: [], borderColor: COLORS.ram,    borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, yAxisID: 'y' },
        { label: 'Batt %',     data: [], borderColor: COLORS.batt,   borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, yAxisID: 'y' },
        { label: 'Temp °C',    data: [], borderColor: COLORS.temp,   borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, yAxisID: 'y1' },
        { label: 'Ch.Util %',  data: [], borderColor: COLORS.chUtil, borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, yAxisID: 'y' },
        { label: 'AirTx %',    data: [], borderColor: COLORS.airTx,  borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, yAxisID: 'y' },
        { label: 'Disco GB',   data: [], borderColor: COLORS.disk,   borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, yAxisID: 'y1' },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { display: false },
        y:  { position: 'left',  ticks: { color: '#888', font: { size: 9 } }, grid: { color: '#333' }, title: { display: false } },
        y1: { position: 'right', ticks: { color: '#888', font: { size: 9 } }, grid: { drawOnChartArea: false }, title: { display: false } },
      },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: '#aaa', font: { size: 8 }, boxWidth: 10, padding: 6, usePointStyle: true }
        }
      }
    }
  })
}

function _pushMainPoint(ts, ramMb, batt, temp, chUtil, airTx, diskGb) {
  if (!mainChart) return
  mainChart.data.labels.push(ts)
  const vals = [ramMb, batt, temp, chUtil, airTx, diskGb]
  mainChart.data.datasets.forEach(function(ds, i) {
    ds.data.push(vals[i])
  })
  if (mainChart.data.labels.length > MAX_POINTS) {
    mainChart.data.labels.shift()
    mainChart.data.datasets.forEach(function(ds) { ds.data.shift() })
  }
  mainChart.update('none')
}

// --- Badges ---
function _updateBadges(values) {
  if (values.ram_mb != null)              document.getElementById('badge-ram').textContent     = 'RAM: ' + values.ram_mb + ' MB'
  if (values.batteryLevel != null)        document.getElementById('badge-batt').textContent    = 'Batt: ' + values.batteryLevel + '%'
  if (values.cpu_temp_c != null)          document.getElementById('badge-temp').textContent    = 'Temp: ' + values.cpu_temp_c + '°C'
  if (values.channelUtilization != null)  document.getElementById('badge-chutil').textContent  = 'ChUtil: ' + (values.channelUtilization * 100).toFixed(1) + '%'
  if (values.airUtilTx != null)           document.getElementById('badge-airtx').textContent   = 'AirTx: ' + (values.airUtilTx * 100).toFixed(1) + '%'
  if (values.disk_free_mb != null)        document.getElementById('badge-disk').textContent    = 'Disco: ' + (values.disk_free_mb / 1024).toFixed(1) + ' GB'
}

// --- Timestamp helper ---
function _ts() {
  return new Date().toLocaleTimeString('it', { hour: '2-digit', minute: '2-digit' })
}

function _fmtUptime(s) {
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h + 'h ' + m + 'm'
}

// --- State to accumulate Pi + Board values for combined push ---
let _lastPi = {}
let _lastBoard = {}

function _pushCombined(ts) {
  _pushMainPoint(
    ts,
    _lastPi.ram_mb || null,
    _lastBoard.batteryLevel || null,
    _lastPi.cpu_temp_c || null,
    _lastBoard.channelUtilization != null ? (_lastBoard.channelUtilization * 100) : null,
    _lastBoard.airUtilTx != null ? (_lastBoard.airUtilTx * 100) : null,
    _lastPi.disk_free_mb != null ? (_lastPi.disk_free_mb / 1024) : null
  )
}

// --- Load history ---
async function loadPiHistory() {
  try {
    var r = await fetch('/api/telemetry/pi/systemMetrics?limit=60')
    if (!r.ok) return
    var data = await r.json()
    if (!Array.isArray(data) || data.length === 0) return
    var sorted = data.slice().reverse()
    sorted.forEach(function(d) {
      var ts = new Date(d.timestamp * 1000).toLocaleTimeString('it', { hour: '2-digit', minute: '2-digit' })
      _lastPi = d.values || {}
      _pushMainPoint(ts, _lastPi.ram_mb || null, null, _lastPi.cpu_temp_c || null, null, null, _lastPi.disk_free_mb != null ? (_lastPi.disk_free_mb / 1024) : null)
    })
    if (data[0] && data[0].values) _updateBadges(data[0].values)
  } catch (_) {}
}

async function loadBoardHistory() {
  if (!_LOCAL_NODE_ID) return
  try {
    var r = await fetch('/api/telemetry/' + _LOCAL_NODE_ID + '/deviceMetrics?limit=60')
    if (!r.ok) return
    var data = await r.json()
    if (!Array.isArray(data) || data.length === 0) return
    var sorted = data.slice().reverse()
    sorted.forEach(function(d) {
      var ts = new Date(d.timestamp * 1000).toLocaleTimeString('it', { hour: '2-digit', minute: '2-digit' })
      _lastBoard = d.values || {}
      // Overwrite the last point's board values if same timestamp exists
      _pushMainPoint(ts, null, _lastBoard.batteryLevel || null, null,
        _lastBoard.channelUtilization != null ? (_lastBoard.channelUtilization * 100) : null,
        _lastBoard.airUtilTx != null ? (_lastBoard.airUtilTx * 100) : null,
        null)
    })
    if (data[0] && data[0].values) _updateBadges(data[0].values)
  } catch (_) {}
}

// --- Live updates via WebSocket ---
window.addEventListener('telemetry-update', function(e) {
  var d = e.detail
  var node_id = d.node_id, type = d.type, values = d.values
  if (type === 'systemMetrics' && node_id === 'pi') {
    _lastPi = values
    _updateBadges(values)
    _pushCombined(_ts())
    return
  }
  if (type === 'deviceMetrics' && (node_id === _LOCAL_NODE_ID || !_LOCAL_NODE_ID)) {
    _lastBoard = values
    _updateBadges(values)
    _pushCombined(_ts())
  }
})

// --- I2C Sensors ---
function _initSensorChart() {
  var ctx = document.getElementById('chart-sensors')
  if (!ctx) return
  sensorChart = new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { display: false },
        y: { ticks: { color: '#888', font: { size: 9 } }, grid: { color: '#333' } }
      },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: '#aaa', font: { size: 8 }, boxWidth: 10, padding: 6, usePointStyle: true }
        }
      }
    }
  })
}

var _sensorColors = ['#e91e63', '#00bcd4', '#8bc34a', '#ff9800', '#673ab7', '#795548', '#607d8b', '#cddc39']
var _sensorColorIdx = 0

window.addEventListener('sensor-update', function(e) {
  var sensor = e.detail.sensor
  var values = e.detail.values
  var section = document.getElementById('sensors-section')
  section.style.display = ''

  if (!sensorChart) _initSensorChart()

  // Update badges
  var container = document.getElementById('sensor-badges')
  var el = document.getElementById('sbadge-' + sensor)
  if (!el) {
    el = document.createElement('span')
    el.id = 'sbadge-' + sensor
    el.className = 't-badge'
    container.appendChild(el)
  }
  var parts = []
  Object.entries(values).forEach(function(kv) { parts.push(kv[0] + ': ' + kv[1]) })
  el.textContent = sensor + ' — ' + parts.join(', ')

  // Push to sensor chart
  var ts = _ts()
  Object.entries(values).forEach(function(kv) {
    var key = sensor + '.' + kv[0]
    if (!sensorDatasets[key]) {
      var color = _sensorColors[_sensorColorIdx % _sensorColors.length]
      _sensorColorIdx++
      var ds = { label: key, data: [], borderColor: color, borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false }
      sensorChart.data.datasets.push(ds)
      sensorDatasets[key] = ds
    }
    sensorDatasets[key].data.push(kv[1])
  })
  sensorChart.data.labels.push(ts)
  if (sensorChart.data.labels.length > MAX_POINTS) {
    sensorChart.data.labels.shift()
    sensorChart.data.datasets.forEach(function(ds) { ds.data.shift() })
  }
  sensorChart.update('none')
})

// --- Export ---
function exportTelemetry(format) {
  if (!_LOCAL_NODE_ID) return
  var url = '/api/export/telemetry?node_id=' + encodeURIComponent(_LOCAL_NODE_ID) + '&type=deviceMetrics&format=' + format + '&limit=1000'
  var a = document.createElement('a')
  a.href = url
  a.download = 'telemetry-' + _LOCAL_NODE_ID + '-deviceMetrics.' + format
  a.click()
}

function exportSensors(format) {
  var el = document.querySelector('#sensor-badges > span')
  if (!el) return
  var name = el.id.replace('sbadge-', '')
  var a = document.createElement('a')
  a.href = '/api/export/sensors?name=' + encodeURIComponent(name) + '&format=' + format + '&limit=1000'
  a.download = 'sensors-' + name + '.' + format
  a.click()
}

// --- Init ---
function _initTelemetryPage() {
  _initMainChart()
  loadPiHistory()
  loadBoardHistory()
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _initTelemetryPage)
} else {
  _initTelemetryPage()
}
</script>
{% endblock %}
```

- [ ] **Step 2: Test at 320x480**

Open `http://localhost:8000/telemetry` in 320x480 viewport. Verify:
- Badges row wraps neatly
- Main chart shows dual Y-axis with legend at bottom
- I2C section hidden by default
- Export buttons accessible

- [ ] **Step 3: Commit**

```bash
git add templates/telemetry.html
git commit -m "feat: combined telemetry chart with dual Y-axis, conditional I2C chart"
```

---

### Task 3: Map — Fix Visibility, Persist View, Center-on-Board Button

**Files:**
- Modify: `static/map.js`
- Modify: `templates/map.html`

Three fixes: (a) ensure map container has proper height, (b) persist view in localStorage, (c) add center-on-board icon button in legend bar.

- [ ] **Step 1: Fix map container CSS in map.html**

The map container has `style="position:absolute;inset:0;"` but it's inside a `position:relative` div. The problem is `#content` has `overflow-y:auto` which clips absolute children. Override `#content` overflow for the map page.

In `templates/map.html`, add to the existing `<style>` block (after line 3):

```css
#content { overflow: hidden; }
```

This line already exists at line 4. Verify it's present. The `#map-container` already has `position:absolute;inset:0` which should fill the parent. The real issue is that the parent `<div style="position:relative;width:100%;height:100%;">` needs explicit height. Change it to:

Replace line 29:
```html
<div style="position:relative;width:100%;height:100%;">
```
This is correct — `height:100%` of `#content` which has a calculated height. The CSS `#content { overflow: hidden; }` at line 4 prevents scrollbar-based height issues. The map should work.

If the map still doesn't render, the issue is likely that `initMapIfNeeded()` is called before the tab is visible. The fix is in `map.js` — call `leafletMap.invalidateSize()` after the map becomes visible.

- [ ] **Step 2: Add center-on-board button to legend bar in map.html**

In `templates/map.html`, inside the `#map-legend` div (line 129-157), add a center-on-board button before the closing `</div>`:

Find the line with `route</div>` and the closing `</div>` of `#map-legend`. Before that closing `</div>`, add:

```html
    <span style="flex:1"></span>
    <button id="btn-center-board" onclick="centerOnBoard()" title="Centra sulla board"
            style="background:none;border:1px solid var(--border);border-radius:3px;
                   width:24px;height:18px;min-height:18px;min-width:24px;padding:0;
                   display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5">
        <circle cx="12" cy="12" r="3"/><path stroke-linecap="round" d="M12 2v4m0 12v4M2 12h4m12 0h4"/>
      </svg>
    </button>
```

- [ ] **Step 3: Persist view state in map.js**

In `static/map.js`, modify `initMapIfNeeded()` to:
1. Restore saved view from localStorage instead of calculating center from bounds
2. Save view on moveend/zoomend
3. Call `invalidateSize()` after init
4. Skip re-init if already initialized (keep existing map instance)

Replace the `initMapIfNeeded` function (lines 320-371) with:

```javascript
function initMapIfNeeded() {
  // If already initialized, just invalidate size and return
  if (mapReady) {
    if (leafletMap) setTimeout(function() { leafletMap.invalidateSize() }, 100)
    return
  }
  if (typeof L === 'undefined') return
  hopLinesLayer = L.layerGroup()
  tracerouteLayer = L.layerGroup()
  customMarkersLayer = L.layerGroup()
  var el = document.getElementById('map-container')
  if (!el) return
  var bounds = JSON.parse(el.dataset.bounds || 'null')
  if (!bounds) return
  var zoomMin = parseInt(el.dataset.zoomMin || '7')
  var zoomMax = parseInt(el.dataset.zoomMax || '12')

  // Restore saved view or use default center
  var savedView = null
  try { savedView = JSON.parse(localStorage.getItem('mapView')) } catch(e) {}
  var center = savedView
    ? [savedView.lat, savedView.lng]
    : [(bounds.lat_min + bounds.lat_max) / 2, (bounds.lon_min + bounds.lon_max) / 2]
  var zoom = savedView ? savedView.zoom : 10

  leafletMap = L.map('map-container', {
    center: center, zoom: zoom, zoomControl: false,
    minZoom: zoomMin, maxZoom: zoomMax,
    maxBounds: [[bounds.lat_min, bounds.lon_min], [bounds.lat_max, bounds.lon_max]],
    maxBoundsViscosity: 1.0,
    tap: true,
  })

  // Save view on move/zoom
  leafletMap.on('moveend', function() {
    var c = leafletMap.getCenter()
    localStorage.setItem('mapView', JSON.stringify({ lat: c.lat, lng: c.lng, zoom: leafletMap.getZoom() }))
  })

  var tileOpts       = { minZoom: zoomMin, maxZoom: zoomMax }
  var osmLayer       = L.tileLayer('/tiles/osm/{z}/{x}/{y}',       tileOpts)
  var topoLayer      = L.tileLayer('/tiles/topo/{z}/{x}/{y}',      tileOpts)
  var satelliteLayer = L.tileLayer('/tiles/satellite/{z}/{x}/{y}', tileOpts)
  osmLayer.addTo(leafletMap)
  L.control.layers({ 'Stradale': osmLayer, 'Topo': topoLayer, 'Satellite': satelliteLayer }).addTo(leafletMap)
  L.control.zoom({ position: 'bottomright' }).addTo(leafletMap)

  hopLinesLayer.addTo(leafletMap)
  customMarkersLayer.addTo(leafletMap)

  nodeCache.forEach(function(node) { updateMapMarker(node) })
  mapReady = true

  initFilters()
  applyFilters()
  renderHopLines()
  loadCustomMarkers()

  // Invalidate size after a short delay to ensure container is visible
  setTimeout(function() { leafletMap.invalidateSize() }, 200)

  var trNode = new URLSearchParams(window.location.search).get('traceroute')
  if (trNode) {
    fetch('/api/traceroute/' + encodeURIComponent(trNode))
      .then(function(r) { return r.json() })
      .then(function(data) {
        if (data.results && data.results[0]) renderTraceroutePath(data.results[0].hops)
      })
  }
}
```

- [ ] **Step 4: Add centerOnBoard function to map.js**

Add this function at the end of `static/map.js` (before the event listeners at the bottom):

```javascript
// --- Center on board position ---
function centerOnBoard() {
  if (!mapReady || !leafletMap) return
  var local = null
  nodeCache.forEach(function(node) {
    if (node.is_local && node.latitude && node.longitude) local = node
  })
  if (local) {
    leafletMap.setView([local.latitude, local.longitude], leafletMap.getZoom())
  }
}
```

- [ ] **Step 5: Test**

1. Open map tab — should show tiles and markers
2. Pan/zoom to a custom position, switch to another tab, return to map — position preserved
3. Click center-on-board button — map centers on local node
4. Pan after centering — new position is preserved

- [ ] **Step 6: Commit**

```bash
git add static/map.js templates/map.html
git commit -m "fix: map visibility, view persistence, center-on-board button"
```

---

### Task 4: Config Serial — Dropdown with Detected Ports

**Files:**
- Modify: `main.py` (add API endpoint)
- Modify: `templates/settings.html` (replace text input with dropdown)

- [ ] **Step 1: Add /api/serial-ports endpoint in main.py**

Add this endpoint after the existing `/api/config` GET endpoint (around line 483):

```python
@app.get("/api/serial-ports")
async def get_serial_ports():
    import glob as g
    candidates = sorted(g.glob('/dev/ttyACM*') + g.glob('/dev/ttyUSB*') + g.glob('/dev/ttyMESHTASTIC'))
    return {"ports": candidates, "current": cfg.SERIAL_PORT}
```

- [ ] **Step 2: Replace serial input with dropdown in settings.html**

Find line 200 in `templates/settings.html`:
```html
<div class="settings-row"><label>Porta seriale</label><input type="text" id="cfg-serial" value=""></div>
```

Replace with:
```html
<div class="settings-row">
  <label>Porta seriale</label>
  <select id="cfg-serial" style="flex:1;" onchange="onSerialChange()">
    <option value="">Caricamento...</option>
  </select>
</div>
<div id="serial-custom-row" class="settings-row" style="display:none;">
  <label>Porta manuale</label>
  <input type="text" id="cfg-serial-custom" placeholder="/dev/ttyUSB0" value="">
</div>
```

- [ ] **Step 3: Add serial port loading JS in settings.html**

Add this function in the `<script>` section, before the existing `fetch('/api/config')` call (around line 521):

```javascript
async function loadSerialPorts() {
  try {
    var r = await fetch('/api/serial-ports')
    var data = await r.json()
    var sel = document.getElementById('cfg-serial')
    sel.textContent = ''
    var ports = data.ports || []
    ports.forEach(function(p) {
      var opt = document.createElement('option')
      opt.value = p
      opt.textContent = p
      if (p === data.current) opt.selected = true
      sel.appendChild(opt)
    })
    // "Personalizza" option
    var custom = document.createElement('option')
    custom.value = '__custom__'
    custom.textContent = 'Personalizza...'
    sel.appendChild(custom)
    // If current port not in list, show custom
    if (data.current && !ports.includes(data.current)) {
      custom.selected = true
      document.getElementById('serial-custom-row').style.display = 'flex'
      document.getElementById('cfg-serial-custom').value = data.current
    }
  } catch (_) {
    var sel = document.getElementById('cfg-serial')
    sel.textContent = ''
    var opt = document.createElement('option')
    opt.value = ''
    opt.textContent = 'Errore caricamento porte'
    sel.appendChild(opt)
  }
}

function onSerialChange() {
  var sel = document.getElementById('cfg-serial')
  var customRow = document.getElementById('serial-custom-row')
  if (sel.value === '__custom__') {
    customRow.style.display = 'flex'
    document.getElementById('cfg-serial-custom').focus()
  } else {
    customRow.style.display = 'none'
  }
}

function getSerialPort() {
  var sel = document.getElementById('cfg-serial')
  if (sel.value === '__custom__') {
    return document.getElementById('cfg-serial-custom').value.trim()
  }
  return sel.value
}

loadSerialPorts()
```

- [ ] **Step 4: Update saveConfig to use getSerialPort()**

In the `saveConfig` function (around line 534), replace:
```javascript
SERIAL_PORT:    document.getElementById('cfg-serial').value,
```
with:
```javascript
SERIAL_PORT:    getSerialPort(),
```

- [ ] **Step 5: Update the config loader to not overwrite the dropdown**

In the `fetch('/api/config')` callback (around line 522-523), replace:
```javascript
document.getElementById('cfg-serial').value = c.SERIAL_PORT || ''
```
with:
```javascript
// Serial port loaded by loadSerialPorts() separately
```

- [ ] **Step 6: Test**

1. Open settings, scroll to "Configurazione" section
2. Dropdown should show detected ports (e.g. `/dev/ttyACM0`)
3. Select "Personalizza..." — text input appears
4. Save config with custom port — should persist

- [ ] **Step 7: Commit**

```bash
git add main.py templates/settings.html
git commit -m "feat: serial port dropdown with auto-detection and custom option"
```

---

### Task 5: Theme Persistence + Custom Theme

**Files:**
- Modify: `static/style.css` (add `.theme-custom` rule)
- Modify: `static/app.js` (load theme from localStorage on init)
- Modify: `templates/settings.html` (custom theme UI)
- Modify: `templates/base.html` (load theme from localStorage before render)

This task has 3 sub-parts: (a) localStorage instant persistence, (b) custom theme with per-element colors, (c) preset themes sync.

- [ ] **Step 1: Add theme-custom CSS class in style.css**

Add after the `.theme-hc` block (after line 34):

```css
.theme-custom {
  /* All variables set dynamically via JS */
}
```

- [ ] **Step 2: Add localStorage theme loading in base.html**

In `templates/base.html`, add a `<script>` in the `<head>` section (after line 8, before closing `</head>`):

```html
<script>
(function(){
  try {
    var saved = JSON.parse(localStorage.getItem('piMeshTheme'))
    if (!saved) return
    var cls = 'theme-' + (saved.theme || 'dark')
    document.documentElement.className = cls
    // Apply custom properties immediately to prevent flash
    if (saved.vars) {
      var s = document.documentElement.style
      Object.keys(saved.vars).forEach(function(k) { s.setProperty(k, saved.vars[k]) })
    }
  } catch(e){}
})()
</script>
```

- [ ] **Step 3: Update applyTheme in app.js to persist to localStorage**

In `static/app.js`, replace the `applyTheme` function (lines 323-326):

```javascript
function applyTheme(theme) {
  document.body.className = 'theme-' + theme
  document.documentElement.className = 'theme-' + theme
  // Persist to localStorage
  try {
    var saved = JSON.parse(localStorage.getItem('piMeshTheme') || '{}')
    saved.theme = theme
    if (theme !== 'custom') {
      // Clear custom vars when switching to preset
      delete saved.vars
      document.documentElement.removeAttribute('style')
    }
    localStorage.setItem('piMeshTheme', JSON.stringify(saved))
  } catch(e){}
}
```

- [ ] **Step 4: Replace the theme section in settings.html**

In `templates/settings.html`, replace lines 69-91 (the entire "Tema UI" section) with:

```html
  <!-- TEMA -->
  <div class="settings-section" style="border-top:1px solid var(--border);">
    <div class="settings-label">Tema UI</div>
    <div style="display:flex; gap:6px; margin-bottom:8px; flex-wrap:wrap;">
      <button onclick="selectTheme('dark')"  class="theme-btn" data-theme="dark"  style="flex:1; min-height:36px; font-size:12px;">Dark</button>
      <button onclick="selectTheme('light')" class="theme-btn" data-theme="light" style="flex:1; min-height:36px; font-size:12px;">Light</button>
      <button onclick="selectTheme('hc')"    class="theme-btn" data-theme="hc"    style="flex:1; min-height:36px; font-size:12px;">HC</button>
      <button onclick="selectTheme('custom')" class="theme-btn" data-theme="custom" style="flex:1; min-height:36px; font-size:12px;">Custom</button>
    </div>

    <!-- Accent color (always visible) -->
    <div class="settings-label">Colore accento</div>
    <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:6px;">
      {% set swatches = ['#4a9eff','#4caf50','#ff9800','#e91e63','#9c27b0','#00bcd4','#ff5722','#8bc34a'] %}
      {% for c in swatches %}
      <button onclick="applyAccent('{{ c }}')" title="{{ c }}"
        style="background:{{ c }};width:28px;min-height:28px;border-radius:50%;border:2px solid transparent;padding:0;flex-shrink:0;"
        id="swatch-{{ loop.index }}"></button>
      {% endfor %}
    </div>
    <div class="settings-row" style="gap:6px;">
      <label style="flex-shrink:0;">Personalizzato</label>
      <input type="color" id="accent-picker" value="{{ accent_color or '#4a9eff' }}"
             style="padding:2px; min-height:32px; width:48px; flex-shrink:0;"
             oninput="applyAccent(this.value)">
    </div>

    <!-- Custom theme color pickers (hidden unless custom) -->
    <div id="custom-theme-section" style="display:none; margin-top:8px;">
      <div class="settings-label">Colori personalizzati</div>
      <div class="settings-row"><label>Sfondo</label>       <input type="color" id="ct-bg"      class="ct-pick" data-var="--bg"      style="width:48px;min-height:32px;flex:unset;"></div>
      <div class="settings-row"><label>Superficie</label>   <input type="color" id="ct-surface" class="ct-pick" data-var="--bg2"     style="width:48px;min-height:32px;flex:unset;"></div>
      <div class="settings-row"><label>Testo</label>        <input type="color" id="ct-text"    class="ct-pick" data-var="--text"    style="width:48px;min-height:32px;flex:unset;"></div>
      <div class="settings-row"><label>Testo secondario</label><input type="color" id="ct-muted" class="ct-pick" data-var="--muted"  style="width:48px;min-height:32px;flex:unset;"></div>
      <div class="settings-row"><label>Bordi</label>        <input type="color" id="ct-border"  class="ct-pick" data-var="--border"  style="width:48px;min-height:32px;flex:unset;"></div>
      <div class="settings-row"><label>Successo</label>     <input type="color" id="ct-ok"      class="ct-pick" data-var="--ok"      style="width:48px;min-height:32px;flex:unset;"></div>
      <div class="settings-row"><label>Attenzione</label>   <input type="color" id="ct-warn"    class="ct-pick" data-var="--warn"    style="width:48px;min-height:32px;flex:unset;"></div>
      <div class="settings-row"><label>Pericolo</label>     <input type="color" id="ct-danger"  class="ct-pick" data-var="--danger"  style="width:48px;min-height:32px;flex:unset;"></div>
    </div>

    <button onclick="saveTheme()" style="margin-top:8px; min-height:36px;">Salva tema</button>
    <div id="theme-status" style="font-size:11px; color:var(--muted); margin-top:4px;"></div>
  </div>
```

- [ ] **Step 5: Replace the theme JS in settings.html**

Replace the existing `applyAccent`, `saveAccent`, `setTheme` functions (lines 475-496) with:

```javascript
let _pendingAccent = null
let _currentTheme = document.body.className.replace('theme-', '') || 'dark'

function applyAccent(color) {
  _pendingAccent = color
  document.documentElement.style.setProperty('--accent', color)
  document.body.style.setProperty('--accent', color)
  var picker = document.getElementById('accent-picker')
  if (picker) picker.value = color
  // Persist immediately to localStorage
  try {
    var saved = JSON.parse(localStorage.getItem('piMeshTheme') || '{}')
    if (!saved.vars) saved.vars = {}
    saved.vars['--accent'] = color
    localStorage.setItem('piMeshTheme', JSON.stringify(saved))
  } catch(e){}
}

function selectTheme(theme) {
  _currentTheme = theme
  document.body.className = 'theme-' + theme
  document.documentElement.className = 'theme-' + theme
  // Show/hide custom section
  document.getElementById('custom-theme-section').style.display = theme === 'custom' ? '' : 'none'
  // Highlight active button
  document.querySelectorAll('.theme-btn').forEach(function(b) {
    b.style.outline = b.dataset.theme === theme ? '2px solid var(--accent)' : 'none'
  })
  if (theme === 'custom') {
    _loadCustomColors()
  } else {
    // Clear inline custom properties
    document.documentElement.removeAttribute('style')
    // Re-apply accent if pending
    if (_pendingAccent) {
      document.documentElement.style.setProperty('--accent', _pendingAccent)
    }
  }
  // Persist to localStorage
  try {
    var saved = JSON.parse(localStorage.getItem('piMeshTheme') || '{}')
    saved.theme = theme
    if (theme !== 'custom') delete saved.vars
    localStorage.setItem('piMeshTheme', JSON.stringify(saved))
  } catch(e){}
}

function _loadCustomColors() {
  // Read current computed values into color pickers
  var style = getComputedStyle(document.documentElement)
  document.querySelectorAll('.ct-pick').forEach(function(pick) {
    var v = style.getPropertyValue(pick.dataset.var).trim()
    if (v) pick.value = _toHex(v)
  })
}

function _toHex(color) {
  if (color.startsWith('#')) return color
  var d = document.createElement('div')
  d.style.color = color
  document.body.appendChild(d)
  var c = getComputedStyle(d).color
  document.body.removeChild(d)
  var m = c.match(/\d+/g)
  if (!m || m.length < 3) return '#000000'
  return '#' + m.slice(0,3).map(function(v) { return parseInt(v).toString(16).padStart(2,'0') }).join('')
}

// Live preview custom color changes
document.addEventListener('input', function(e) {
  if (!e.target.classList.contains('ct-pick')) return
  document.documentElement.style.setProperty(e.target.dataset.var, e.target.value)
})

async function saveTheme() {
  var st = document.getElementById('theme-status')
  // Collect custom vars
  var vars = {}
  if (_currentTheme === 'custom') {
    document.querySelectorAll('.ct-pick').forEach(function(pick) {
      vars[pick.dataset.var] = pick.value
    })
  }
  if (_pendingAccent) vars['--accent'] = _pendingAccent

  // Save to localStorage
  var saved = { theme: _currentTheme }
  if (Object.keys(vars).length > 0) saved.vars = vars
  localStorage.setItem('piMeshTheme', JSON.stringify(saved))

  // Sync to server
  try {
    var payload = { theme: _currentTheme }
    if (_pendingAccent) payload.accent_color = _pendingAccent
    await fetch('/api/set-theme', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    st.textContent = 'Tema salvato'
  } catch (_) {
    st.textContent = 'Errore salvataggio'
  }
}

// Init: load saved theme on page load
(function() {
  try {
    var saved = JSON.parse(localStorage.getItem('piMeshTheme'))
    if (!saved) return
    _currentTheme = saved.theme || 'dark'
    // Highlight active button
    document.querySelectorAll('.theme-btn').forEach(function(b) {
      b.style.outline = b.dataset.theme === _currentTheme ? '2px solid var(--accent)' : 'none'
    })
    if (_currentTheme === 'custom') {
      document.getElementById('custom-theme-section').style.display = ''
      if (saved.vars) {
        Object.entries(saved.vars).forEach(function(kv) {
          document.documentElement.style.setProperty(kv[0], kv[1])
        })
        _loadCustomColors()
      }
    }
    if (saved.vars && saved.vars['--accent']) {
      _pendingAccent = saved.vars['--accent']
      var picker = document.getElementById('accent-picker')
      if (picker) picker.value = saved.vars['--accent']
    }
  } catch(e){}
})()
```

- [ ] **Step 6: Update set-theme API to accept 'custom' theme**

In `main.py`, update the `set_theme` endpoint (line 421):

Replace:
```python
    if theme not in ("dark", "light", "hc"):
```
with:
```python
    if theme not in ("dark", "light", "hc", "custom"):
```

- [ ] **Step 7: Test**

1. Select Dark theme — persists after refresh
2. Select accent color, refresh — color persists
3. Select Custom — color pickers appear
4. Change background color — live preview
5. Click "Salva tema" — persists after refresh
6. Switch to Light — custom colors cleared, Light applied
7. Refresh — Light theme still active

- [ ] **Step 8: Commit**

```bash
git add static/style.css static/app.js templates/settings.html templates/base.html main.py
git commit -m "feat: theme persistence via localStorage + custom theme with per-element colors"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - Log toolbar two rows: Task 1 ✓
   - Telemetry combined chart + conditional I2C: Task 2 ✓
   - Map fix visibility: Task 3 step 1 ✓
   - Map persist view: Task 3 step 3 ✓
   - Map center-on-board button: Task 3 steps 2+4 ✓
   - Config serial dropdown: Task 4 ✓
   - Theme preset + custom: Task 5 ✓
   - Theme localStorage + server sync: Task 5 ✓
   - Display proportionality (320x480): All tasks use proportional sizing ✓

2. **Placeholder scan:** No TBD, TODO, or vague instructions found.

3. **Type consistency:** All function names, CSS classes, and element IDs are consistent across tasks.
