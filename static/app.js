// static/app.js

// ===== STATO GLOBALE =====
let ws = null
let wsReady = false
const activeTab = { name: document.querySelector('.tab.active')?.dataset.tab || 'messages' }
const nodeCache = new Map()
const messageCache = []

// ===== WEBSOCKET =====
function initWS() {
  ws = new WebSocket(`ws://${window.location.host}/ws`)

  ws.onopen = () => {
    wsReady = true
    document.getElementById('connection-badge').classList.add('connected')
  }

  ws.onclose = () => {
    wsReady = false
    document.getElementById('connection-badge').classList.remove('connected')
    setTimeout(initWS, 3000)
  }

  ws.onmessage = (event) => {
    let msg
    try {
      msg = JSON.parse(event.data)
    } catch (e) {
      return
    }
    const handlers = {
      init:      handleInit,
      message:   handleMessage,
      node:      handleNode,
      position:  handlePosition,
      telemetry: handleTelemetry,
      sensor:    handleSensor,
      encoder:   handleEncoder,
      status:    handleStatus,
    }
    handlers[msg.type]?.(msg.data)
  }

  setInterval(() => { if (wsReady && ws.readyState === WebSocket.OPEN) ws.send('ping') }, 20000)
}

// ===== HANDLER MESSAGGI WS =====
function handleInit(data) {
  updateConnectionStatus(data.connected)
  data.nodes.forEach(n => nodeCache.set(n.id, n))
  if (activeTab.name === 'messages') renderMessages(data.messages)
  if (data.theme) applyTheme(data.theme)
}

function handleMessage(data) {
  messageCache.unshift(data)
  if (messageCache.length > 200) messageCache.pop()
  if (activeTab.name === 'messages') appendMessage(data)
}

function handleNode(data) {
  nodeCache.set(data.id, data)
  if (activeTab.name === 'nodes') updateNodeRow(data)
  if (activeTab.name === 'map' && mapReady) updateMapMarker(data)
}

function handlePosition(data) {
  const node = nodeCache.get(data.node_id)
  if (node) {
    node.latitude  = data.latitude
    node.longitude = data.longitude
    if (activeTab.name === 'map' && mapReady) updateMapMarker(node)
  }
}

function handleTelemetry(data) {
  if (activeTab.name === 'telemetry') updateTelemetryChart(data)
}

function handleSensor(data) {
  if (activeTab.name === 'telemetry') updateSensorDisplay(data)
}

function handleStatus(data) {
  if (data.connected !== undefined) updateConnectionStatus(data.connected)
  if (data.ram_mb) {
    const el = document.getElementById('ram-badge')
    if (el) el.textContent = data.ram_mb + 'MB'
  }
}

function updateConnectionStatus(connected) {
  const badge = document.getElementById('connection-badge')
  if (!badge) return
  badge.classList.toggle('connected', connected)
}

// ===== ENCODER =====
function handleEncoder(data) {
  const { encoder, action } = data
  if (encoder === 1) {
    const tabs = ['messages', 'nodes', 'map', 'telemetry', 'settings']
    const current = tabs.indexOf(activeTab.name)
    if (action === 'cw' && current < tabs.length - 1) navigateTo(tabs[current + 1])
    else if (action === 'ccw' && current > 0) navigateTo(tabs[current - 1])
    else if (action === 'long_press') navigateTo('messages')
    return
  }
  if (encoder === 2) {
    const handlers = {
      messages:  enc2Messages,
      nodes:     enc2Nodes,
      map:       enc2Map,
      telemetry: enc2Telemetry,
      settings:  enc2Settings,
    }
    handlers[activeTab.name]?.(action)
  }
}

function enc2Messages(action) {
  const list = document.getElementById('msg-list')
  if (list) list.scrollTop += (action === 'cw' ? 48 : -48)
}
function enc2Nodes(action) {
  const list = document.getElementById('node-list')
  if (list) list.scrollTop += (action === 'cw' ? 48 : -48)
}
function enc2Map(action) {
  if (!mapReady) return
  if (action === 'cw') leafletMap.zoomIn()
  if (action === 'ccw') leafletMap.zoomOut()
}
function enc2Telemetry(action) {
  const el = document.getElementById('content')
  if (el) el.scrollTop += (action === 'cw' ? 48 : -48)
}
function enc2Settings(action) {
  const el = document.getElementById('content')
  if (el) el.scrollTop += (action === 'cw' ? 48 : -48)
}

// ===== NAVIGAZIONE SENZA RELOAD =====
async function navigateTo(tabName) {
  if (tabName === activeTab.name) return
  activeTab.name = tabName

  try {
    const response  = await fetch('/' + tabName)
    const html      = await response.text()
    const parser    = new DOMParser()
    const doc       = parser.parseFromString(html, 'text/html')
    const newContent = doc.getElementById('content')
    if (newContent) document.getElementById('content').innerHTML = newContent.innerHTML
  } catch (e) {
    console.error('navigateTo error:', e)
  }

  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabName)
  })

  if (tabName === 'map')       initMapIfNeeded()
  if (tabName === 'telemetry') initChartsIfNeeded()
  attachKeyboardListeners()
}

// ===== TASTIERA =====
function attachKeyboardListeners() {
  document.querySelectorAll('input[type=text], input[type=number], textarea').forEach(el => {
    el.addEventListener('focus', () => fetch('/api/keyboard/show', { method: 'POST' }))
    el.addEventListener('blur', () => {
      setTimeout(() => fetch('/api/keyboard/hide', { method: 'POST' }), 200)
    })
  })
}

// ===== MESSAGGI =====
function renderMessages(messages) {
  const list = document.getElementById('msg-list')
  if (!list) return
  list.innerHTML = ''
  ;[...messages].reverse().forEach(m => appendMessage(m))
}

function appendMessage(m) {
  const list = document.getElementById('msg-list')
  if (!list) return
  const div = document.createElement('div')
  div.className = 'msg-row' + (m.is_outgoing ? ' outgoing' : '')
  div.dataset.msgId = m.id
  const name = nodeCache.get(m.node_id)?.short_name || m.node_id
  const ts   = new Date(m.timestamp * 1000).toLocaleTimeString('it', { hour: '2-digit', minute: '2-digit' })
  div.innerHTML = `
    <div class="msg-bubble">${escHtml(m.text)}</div>
    <div class="msg-meta">${m.is_outgoing ? '' : escHtml(name) + ' · '}${ts}${m.rx_snr != null ? ' · ' + m.rx_snr + 'dB' : ''}</div>
  `
  list.appendChild(div)
  list.scrollTop = list.scrollHeight
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

// ===== TEMA =====
function applyTheme(theme) {
  document.body.className = 'theme-' + theme
  document.documentElement.className = 'theme-' + theme
}

// ===== MAPPA =====
let leafletMap = null
let mapReady = false
const markerCache = new Map()

function initMapIfNeeded() {
  if (mapReady || typeof L === 'undefined') return
  const bounds = window.MAP_BOUNDS
  if (!bounds) return
  const center = [(bounds.lat_min + bounds.lat_max) / 2, (bounds.lon_min + bounds.lon_max) / 2]

  leafletMap = L.map('map-container', {
    center, zoom: 10, zoomControl: false,
    maxBounds: [[bounds.lat_min, bounds.lon_min], [bounds.lat_max, bounds.lon_max]],
    maxBoundsViscosity: 1.0,
  })

  const osmLayer  = L.tileLayer('/tiles/osm/{z}/{x}/{y}.png',  { maxZoom: window.MAP_ZOOM_MAX })
  const topoLayer = L.tileLayer('/tiles/topo/{z}/{x}/{y}.png', { maxZoom: window.MAP_ZOOM_MAX })
  osmLayer.addTo(leafletMap)
  L.control.layers({ 'Stradale': osmLayer, 'Topo': topoLayer }).addTo(leafletMap)

  nodeCache.forEach(node => updateMapMarker(node))
  mapReady = true
}

function updateMapMarker(node) {
  if (!node.latitude || !node.longitude || !mapReady) return
  const color = node.is_local ? '#4a9eff' : '#4caf50'
  const existing = markerCache.get(node.id)
  if (existing) {
    existing.setLatLng([node.latitude, node.longitude])
  } else {
    const marker = L.circleMarker([node.latitude, node.longitude], {
      radius: 8, color, fillColor: color, fillOpacity: 0.8
    })
    marker.bindPopup(`<b>${node.short_name || node.id}</b><br>${node.long_name || ''}<br>SNR: ${node.snr ?? '—'} dB<br>Batt: ${node.battery_level ?? '—'}%`)
    marker.addTo(leafletMap)
    markerCache.set(node.id, marker)
  }
}

// ===== GRAFICI (stub, completato in Task telemetry) =====
function initChartsIfNeeded() { /* implementato in telemetry.html inline */ }
function updateTelemetryChart(data) { window.dispatchEvent(new CustomEvent('telemetry-update', { detail: data })) }
function updateSensorDisplay(data) { window.dispatchEvent(new CustomEvent('sensor-update', { detail: data })) }
function updateNodeRow(data) { window.dispatchEvent(new CustomEvent('node-update', { detail: data })) }

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
  initWS()
  attachKeyboardListeners()
  // link tab bar a navigateTo
  document.getElementById('tabbar')?.addEventListener('click', e => {
    const tab = e.target.closest('.tab[data-tab]')
    if (!tab) return
    e.preventDefault()
    navigateTo(tab.dataset.tab)
  })
})
