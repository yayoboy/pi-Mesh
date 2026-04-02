// static/app.js

// ===== STATO GLOBALE =====
let ws = null
let wsReady = false
const activeTab = { name: document.querySelector('.tab.active')?.dataset.tab || 'messages' }
const nodeCache = new Map()
const messageCache = []

// ===== NODE ACTIONS (page-agnostic, shared by nodes.html and map.js) =====
const nodeActions = {
  traceroute: (nodeId) =>
    fetch(`/api/nodes/${encodeURIComponent(nodeId)}/traceroute`, { method: 'POST' })
      .then(r => r.json()),

  requestPosition: (nodeId) =>
    fetch(`/api/nodes/${encodeURIComponent(nodeId)}/request-position`, { method: 'POST' })
      .then(r => r.json()),

  sendDM: (nodeId, text) =>
    fetch('/api/messages/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: nodeId, text: text, channel: 0 }),
    }).then(r => r.json()),

  focusOnMap: (nodeId) => {
    window.location.href = `/map?focus=${encodeURIComponent(nodeId)}`
  },
}

// ===== TOAST =====
let _lastConnected = null

function showToast(msg, type, duration) {
  if (duration === undefined) duration = 3000
  const container = document.getElementById('toast-container')
  if (!container) return
  const el = document.createElement('div')
  el.className = 'toast' + (type ? ' toast-' + type : '')
  el.textContent = msg
  container.appendChild(el)
  // trigger animation on next frame
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { el.classList.add('show') })
  })
  setTimeout(() => {
    el.classList.remove('show')
    setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el) }, 300)
  }, duration)
}

// ===== UTILITY =====
function reexecScripts(container) {
  const scripts = Array.from(container.querySelectorAll('script'))
  let chain = Promise.resolve()
  scripts.forEach(oldScript => {
    chain = chain.then(() => new Promise(resolve => {
      const s = document.createElement('script')
      if (oldScript.src) {
        s.src = oldScript.src
        s.onload = resolve
        s.onerror = resolve
      } else {
        s.textContent = oldScript.textContent
      }
      oldScript.parentNode.replaceChild(s, oldScript)
      if (!oldScript.src) resolve()
    }))
  })
  return chain
}

// ===== WEBSOCKET =====
function initWS() {
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${wsProto}//${window.location.host}/ws`)

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
      init:              handleInit,
      message:           handleMessage,
      node:              handleNode,
      position:          handlePosition,
      telemetry:         handleTelemetry,
      rpi_telemetry:     handleRpiTelemetry,
      sensor:            handleSensor,
      encoder:           handleEncoder,
      status:            handleStatus,
      log:               handleLog,
      ack:               handleAck,
      traceroute_result: handleTracerouteResult,
    }
    handlers[msg.type]?.(msg)
    if (msg.type === 'telemetry') {
      window.dispatchEvent(new CustomEvent('ws-message', { detail: msg }))
    }
  }

}

// ===== HANDLER MESSAGGI WS =====
function handleInit(msg) {
  const nodes = msg.nodes || []
  nodes.forEach(n => nodeCache.set(n.id, n))
  const local = nodes.find(n => n.is_local)
  if (local) {
    const el = document.getElementById('node-name')
    if (el) el.textContent = local.short_name || local.id
    updateGpsBadge(local.latitude != null && local.longitude != null)
    updateBatteryBadge(local.battery_level)
    updateLoraBadge(local.snr)
  }
  window.dispatchEvent(new CustomEvent('ws-init', { detail: msg }))
  fetch('/api/wifi/status').then(r => r.json()).then(s => {
    updateWifiBadge(s.state === 'connected')
  }).catch(() => {})
}

function handleMessage(msg) {
  messageCache.unshift(msg)
  if (messageCache.length > 200) messageCache.pop()
  window.dispatchEvent(new CustomEvent('message-new', { detail: msg }))
  const prefix = (msg.destination && msg.destination !== '^all') ? 'DM ' : ''
  const sender = nodeCache.get(msg.node_id)?.short_name || msg.node_id
  if (typeof showToast === 'function') showToast(prefix + sender + ': ' + (msg.text || '').slice(0, 30))
  if (activeTab.name !== 'messages') {
    _unreadCount++
    updateMsgBadge(_unreadCount)
  }
}

function handleNode(msg) {
  // msg = { type: 'node', id, short_name, long_name, hw_model, ... }
  const isNew = !nodeCache.has(msg.id)
  nodeCache.set(msg.id, msg)
  if (isNew && !msg.is_local) showToast('Nuovo nodo: ' + (msg.short_name || msg.id))
  window.dispatchEvent(new CustomEvent('node-update', { detail: msg }))
  if (msg.is_local) {
    const el = document.getElementById('node-name')
    if (el) el.textContent = msg.short_name || msg.id
    updateGpsBadge(msg.latitude != null && msg.longitude != null)
    updateBatteryBadge(msg.battery_level)
    updateLoraBadge(msg.snr)
  }
}

function handlePosition(msg) {
  // msg = { type: 'position', id, latitude, longitude, altitude, last_heard }
  const node = nodeCache.get(msg.id)
  if (node) {
    node.latitude   = msg.latitude
    node.longitude  = msg.longitude
    if (msg.altitude != null) node.altitude = msg.altitude
    node.last_heard = msg.last_heard
    if (node.is_local) updateGpsBadge(true)
    window.dispatchEvent(new CustomEvent('node-update', { detail: node }))
  }
  window.dispatchEvent(new CustomEvent('position-update', { detail: msg }))
}

function handleTelemetry(msg) {
  // msg = { type: 'telemetry', id, battery_level, snr }
  const node = nodeCache.get(msg.id)
  if (node) {
    if (msg.battery_level != null) node.battery_level = msg.battery_level
    if (msg.snr != null) node.snr = msg.snr
  }
  // Update status bar for local node
  if (node && node.is_local && msg.ttype === 'device' && msg.data) {
    if (msg.data.battery_level != null) updateBatteryBadge(msg.data.battery_level)
  }
  // Battery low alert
  if (msg.ttype === 'device' && msg.data && msg.data.battery_level != null) {
    const lvl = msg.data.battery_level
    if (lvl > 0 && lvl <= _alertConfig.battery_low) {
      const name = nodeCache.get(msg.id)?.short_name || msg.id
      if (shouldAlert('bat-' + msg.id, 600000)) {
        showToast(name + ': batteria ' + lvl + '%', 'warn', 5000)
      }
    }
  }
  window.dispatchEvent(new CustomEvent('telemetry-update', { detail: msg }))
}

function handleSensor(msg) {
  window.dispatchEvent(new CustomEvent('sensor-update', { detail: msg }))
}

function handleLog(msg) {
  window.dispatchEvent(new CustomEvent('log-entry', { detail: msg }))
}

function handleAck(msg) {
  window.dispatchEvent(new CustomEvent('msg-ack', { detail: msg }))
}

function handleTracerouteResult(msg) {
  // msg = { type: 'traceroute_result', node_id, hops: [...] }
  window.dispatchEvent(new CustomEvent('traceroute_result', { detail: msg }))
}

function handleRpiTelemetry(msg) {
  window.dispatchEvent(new CustomEvent('ws-message', { detail: msg }))
  if (msg.data && msg.data.ram_percent != null && msg.data.ram_percent > _alertConfig.ram_high) {
    if (shouldAlert('ram-high', 300000)) {
      showToast('RAM: ' + msg.data.ram_percent.toFixed(0) + '%', 'warn', 5000)
    }
  }
}

function handleStatus(msg) {
  if (msg.connected !== undefined) updateConnectionStatus(msg.connected)
  if (msg.ram_mb) {
    const el = document.getElementById('ram-badge')
    if (el) el.textContent = msg.ram_mb + 'MB'
  }
}

function updateConnectionStatus(connected) {
  updateConnectionBadge(connected)
  if (_lastConnected !== connected) {
    if (_lastConnected !== null) {
      showToast(connected ? 'Connesso' : 'Disconnesso', connected ? 'ok' : 'warn')
    }
    _lastConnected = connected
  }
}

function updateGpsBadge(hasFix) {
  const el = document.getElementById('gps-badge')
  if (el) el.style.color = hasFix ? '#4caf50' : 'var(--muted)'
}

function updateBatteryBadge(level) {
  const badge = document.getElementById('battery-badge')
  const fill = document.getElementById('batt-fill')
  if (!badge || !fill) return
  if (level == null) { badge.style.color = 'var(--muted)'; fill.setAttribute('width', '0'); return }
  var w = Math.max(0, Math.min(14, Math.round(level / 100 * 14)))
  fill.setAttribute('width', String(w))
  if (level > 60) badge.style.color = '#4caf50'
  else if (level > 20) badge.style.color = '#ff9800'
  else badge.style.color = '#f44336'
}

function updateLoraBadge(snr) {
  const badge = document.getElementById('lora-badge')
  if (!badge) return
  // SNR quality: >5=excellent, 0-5=good, -5-0=fair, <-5=poor
  var bars = 0
  var color = 'var(--muted)'
  if (snr != null) {
    if (snr > 5) { bars = 4; color = '#4caf50' }
    else if (snr > 0) { bars = 3; color = '#8bc34a' }
    else if (snr > -5) { bars = 2; color = '#ff9800' }
    else { bars = 1; color = '#f44336' }
  }
  badge.style.color = color
  for (var i = 1; i <= 4; i++) {
    var r = document.getElementById('sig' + i)
    if (r) r.setAttribute('opacity', i <= bars ? '1' : '0.25')
  }
}

function updateConnectionBadge(connected) {
  const el = document.getElementById('connection-badge')
  if (el) el.style.color = connected ? '#4caf50' : 'var(--muted)'
}

// ===== BADGE MESSAGGI NON LETTI =====
let _unreadCount = 0

function updateMsgBadge(count) {
  _unreadCount = count
  const badge = document.getElementById('msg-badge')
  if (!badge) return
  if (count > 0) {
    badge.textContent = count > 99 ? '99+' : count
    badge.style.display = ''
  } else {
    badge.style.display = 'none'
  }
}

function fetchUnreadCount() {
  fetch('/api/messages/unread-count')
    .then(r => r.json())
    .then(d => updateMsgBadge(d.count))
    .catch(() => {})
}

// ===== ALERT SYSTEM =====
const _alertConfig = { node_offline_min: 30, battery_low: 20, ram_high: 85 }
const _alertSent = new Map()

function loadAlertConfig() {
  fetch('/api/config/alerts')
    .then(r => r.json())
    .then(d => {
      _alertConfig.node_offline_min = d.node_offline_min
      _alertConfig.battery_low = d.battery_low
      _alertConfig.ram_high = d.ram_high
    })
    .catch(() => {})
}

function shouldAlert(key, cooldownMs) {
  const last = _alertSent.get(key) || 0
  if (Date.now() - last < cooldownMs) return false
  _alertSent.set(key, Date.now())
  return true
}

function checkNodesOffline() {
  const now = Math.floor(Date.now() / 1000)
  const threshold = _alertConfig.node_offline_min * 60
  nodeCache.forEach((node, id) => {
    if (node.is_local || !node.last_heard) return
    const age = now - node.last_heard
    if (age > threshold && age < threshold + 120) {
      if (shouldAlert('offline-' + id, 1800000)) {
        const name = node.short_name || id
        showToast(name + ' offline da ' + Math.round(age / 60) + 'min', 'warn', 5000)
      }
    }
  })
}

// ===== ENCODER =====
function handleEncoder(msg) {
  const { encoder, action } = msg
  if (encoder === 1) {
    const tabs = ['messages', 'nodes', 'map', 'telemetry', 'settings', 'log']
    const current = tabs.indexOf(activeTab.name)
    if (action === 'cw' && current < tabs.length - 1) navigateTo(tabs[current + 1])
    else if (action === 'ccw' && current > 0) navigateTo(tabs[current - 1])
    else if (action === 'long_press') navigateTo('messages')
    return
  }
  if (encoder === 2) {
    const enc2handlers = {
      messages: enc2Messages, nodes: enc2Nodes, map: enc2Map,
      telemetry: enc2Telemetry, settings: enc2Settings, log: enc2Log,
    }
    enc2handlers[activeTab.name]?.(action)
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
  if (typeof mapReady === 'undefined' || !mapReady) return
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
function enc2Log(action) {
  const el = document.getElementById('log-list')
  if (el) el.scrollTop += (action === 'cw' ? 48 : -48)
}

// ===== NAVIGAZIONE SENZA RELOAD =====
async function navigateTo(tabName) {
  if (tabName === activeTab.name) return
  activeTab.name = tabName
  if (tabName === 'messages') updateMsgBadge(0)

  try {
    const response  = await fetch('/' + tabName)
    const html      = await response.text()
    const parser    = new DOMParser()
    const doc       = parser.parseFromString(html, 'text/html')
    // Inject missing <link rel=stylesheet> from fetched page's <head>
    doc.querySelectorAll('head link[rel=stylesheet]').forEach(link => {
      if (!document.querySelector(`link[href="${link.getAttribute('href')}"]`)) {
        document.head.appendChild(link.cloneNode(true))
      }
    })

    // Inject missing <script src> from fetched page's <head> (e.g. Leaflet)
    await new Promise(resolve => {
      const headScripts = Array.from(doc.querySelectorAll('head script[src]'))
        .filter(s => !document.querySelector(`script[src="${s.getAttribute('src')}"]`))
      if (!headScripts.length) { resolve(); return }
      let loaded = 0
      headScripts.forEach(oldS => {
        const s = document.createElement('script')
        s.src = oldS.src
        s.onload = s.onerror = () => { if (++loaded === headScripts.length) resolve() }
        document.head.appendChild(s)
      })
    })

    const newContent = doc.getElementById('content')
    if (newContent) {
      const container = document.getElementById('content')
      container.innerHTML = newContent.innerHTML
      await reexecScripts(container)
      // Tell Alpine to initialize new x-data components after SPA navigation
      if (window.Alpine) {
        container.querySelectorAll('[x-data]').forEach(function(el) {
          Alpine.initTree(el)
        })
      }
    }
  } catch (e) {
    console.error('navigateTo error:', e)
  }

  document.querySelectorAll('.tab').forEach(t => {
    const isActive = t.dataset.tab === tabName
    t.classList.toggle('active', isActive)
    t.classList.toggle('tab-active', isActive)
    t.style.color = isActive ? 'var(--accent)' : 'var(--muted)'
    const svg = t.querySelector('svg')
    if (svg) svg.setAttribute('stroke', isActive ? 'var(--accent)' : 'var(--muted)')
  })

  if (tabName === 'map') {
    // Reset map state — old DOM was destroyed by SPA navigation
    if (typeof mapReady !== 'undefined') { mapReady = false; leafletMap = null; markerCache.clear() }
    setTimeout(() => { if (typeof initMapIfNeeded === 'function') initMapIfNeeded() }, 100)
  }
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
  // Filtra per canale selezionato
  const chSel = document.getElementById('ch-select')
  if (chSel && parseInt(chSel.value) !== m.channel) return

  const div = document.createElement('div')
  div.className = 'msg-row' + (m.is_outgoing ? ' outgoing' : '')
  div.dataset.msgId = m.id

  const bubble = document.createElement('div')
  bubble.className = 'msg-bubble'
  bubble.textContent = m.text

  const meta = document.createElement('div')
  meta.className = 'msg-meta'
  const name = nodeCache.get(m.node_id)?.short_name || m.node_id
  const ts   = new Date((m.ts || m.timestamp) * 1000).toLocaleTimeString('it', { hour: '2-digit', minute: '2-digit' })
  meta.textContent = (m.is_outgoing ? '' : name + ' \u00b7 ') + ts + (m.rx_snr != null ? ' \u00b7 ' + m.rx_snr + 'dB' : '') + (m.hop_count != null && m.hop_count > 0 ? ' \u00b7 ' + m.hop_count + 'hop' : '')

  if (m.is_outgoing) {
    const ackEl = document.createElement('span')
    ackEl.className = 'msg-ack' + (m.ack ? ' delivered' : '')
    ackEl.textContent = m.ack ? ' \u2713\u2713' : ' \u2713'
    ackEl.title = m.ack ? 'Consegnato' : 'Inviato'
    meta.appendChild(ackEl)
  }

  div.append(bubble, meta)
  // Inserisci prima del sentinel load-more se presente
  const sentinel = document.getElementById('load-more')
  list.insertBefore(div, sentinel || null)
  list.scrollTop = list.scrollHeight
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

// ===== TEMA =====
function applyTheme(theme) {
  document.body.className = 'theme-' + theme
  document.documentElement.className = 'theme-' + theme
  try {
    var saved = JSON.parse(localStorage.getItem('piMeshTheme') || '{}')
    saved.theme = theme
    if (theme !== 'custom') {
      delete saved.vars
      document.documentElement.removeAttribute('style')
    }
    localStorage.setItem('piMeshTheme', JSON.stringify(saved))
  } catch(e){}
}

// ===== GRAFICI (stub, completato in Task telemetry) =====
function initChartsIfNeeded() { /* implementato in telemetry.html inline */ }

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
  if (!document.getElementById('toast-container')) {
    const tc = document.createElement('div')
    tc.id = 'toast-container'
    document.body.appendChild(tc)
  }
  initWS()
  fetchUnreadCount()
  loadAlertConfig()
  setInterval(checkNodesOffline, 60000)
  setInterval(() => { if (wsReady && ws.readyState === WebSocket.OPEN) ws.send('ping') }, 20000)
  attachKeyboardListeners()
  // link tab bar a navigateTo
  document.getElementById('tabbar')?.addEventListener('click', e => {
    const tab = e.target.closest('.tab[data-tab]')
    if (!tab) return
    e.preventDefault()
    navigateTo(tab.dataset.tab)
  })
  // se la pagina è stata caricata direttamente sul tab mappa
  if (document.getElementById('map-container')) initMapIfNeeded()
})
