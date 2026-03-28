// static/app.js

// ===== STATO GLOBALE =====
let ws = null
let wsReady = false
const activeTab = { name: document.querySelector('.tab.active')?.dataset.tab || 'messages' }
const nodeCache = new Map()
const messageCache = []

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
  container.querySelectorAll('script').forEach(oldScript => {
    const s = document.createElement('script')
    s.textContent = oldScript.textContent
    oldScript.parentNode.replaceChild(s, oldScript)
  })
}

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
      init:              handleInit,
      message:           handleMessage,
      node:              handleNode,
      position:          handlePosition,
      telemetry:         handleTelemetry,
      sensor:            handleSensor,
      encoder:           handleEncoder,
      status:            handleStatus,
      log:               handleLog,
      ack:               handleAck,
      traceroute_result: handleTracerouteResult,
    }
    handlers[msg.type]?.(msg.data)
  }

}

// ===== HANDLER MESSAGGI WS =====
function handleInit(data) {
  updateConnectionStatus(data.connected)
  data.nodes.forEach(n => nodeCache.set(n.id, n))
  if (activeTab.name === 'messages') renderMessages(data.messages)
  if (data.theme) applyTheme(data.theme)
  const local = data.nodes.find(n => n.is_local)
  if (local) {
    const el = document.getElementById('node-name')
    if (el) el.textContent = local.short_name || local.id
    updateGpsBadge(local.latitude != null && local.longitude != null)
  }
  fetch('/api/wifi/status').then(r => r.json()).then(s => {
    updateWifiBadge(s.state === 'connected')
  }).catch(() => {})
}

function handleMessage(data) {
  messageCache.unshift(data)
  if (messageCache.length > 200) messageCache.pop()
  window.dispatchEvent(new CustomEvent('message-new', { detail: data }))
  const prefix = (data.destination && data.destination !== '^all') ? 'DM ' : 'MSG '
  if (typeof showToast === 'function') showToast(prefix + (data.node_id || '') + ': ' + (data.text || '').slice(0, 30))
}

function handleNode(data) {
  const isNew = !nodeCache.has(data.id)
  nodeCache.set(data.id, data)
  if (isNew && !data.is_local) showToast('Nuovo nodo: ' + (data.short_name || data.id))
  if (activeTab.name === 'nodes') updateNodeRow(data)
  if (activeTab.name === 'map' && mapReady) updateMapMarker(data)
  if (data.is_local) {
    const el = document.getElementById('node-name')
    if (el) el.textContent = data.short_name || data.id
    updateGpsBadge(data.latitude != null && data.longitude != null)
  }
}

function handlePosition(data) {
  const node = nodeCache.get(data.node_id)
  if (node) {
    node.latitude  = data.latitude
    node.longitude = data.longitude
    if (activeTab.name === 'map' && mapReady) updateMapMarker(node)
    if (node.is_local) updateGpsBadge(true)
  }
}

function handleTelemetry(data) {
  if (activeTab.name === 'telemetry') updateTelemetryChart(data)
  if (data.node_id === 'pi' && data.type === 'systemMetrics' && data.values) {
    const v = data.values
    const ram = document.getElementById('ram-badge')
    if (ram && v.ram_mb) ram.textContent = v.ram_mb + 'MB'
    const temp = document.getElementById('temp-badge')
    if (temp && v.cpu_temp_c != null) temp.textContent = v.cpu_temp_c + '°C'
  }
}

function handleSensor(data) {
  if (activeTab.name === 'telemetry') updateSensorDisplay(data)
}

function handleLog(data) {
  window.dispatchEvent(new CustomEvent('log-entry', { detail: data }))
}

function handleAck(data) {
  window.dispatchEvent(new CustomEvent('msg-ack', { detail: data }))
}

function handleTracerouteResult(data) {
  window.dispatchEvent(new CustomEvent('traceroute_result', { detail: data }))
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
  if (_lastConnected !== connected) {
    if (_lastConnected !== null) {
      showToast(connected ? 'Connesso' : 'Disconnesso', connected ? 'ok' : 'warn')
    }
    _lastConnected = connected
  }
}

function updateGpsBadge(hasFix) {
  const el = document.getElementById('gps-badge')
  if (el) el.style.color = hasFix ? 'var(--ok)' : 'var(--muted)'
}

function updateWifiBadge(connected) {
  const el = document.getElementById('wifi-badge')
  if (el) el.style.color = connected ? 'var(--ok)' : 'var(--muted)'
}

// ===== ENCODER =====
function handleEncoder(data) {
  const { encoder, action } = data
  if (encoder === 1) {
    const tabs = ['messages', 'nodes', 'map', 'telemetry', 'settings', 'log']
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
      log:       enc2Log,
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
function enc2Log(action) {
  const el = document.getElementById('log-list')
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
    if (newContent) {
      document.getElementById('content').innerHTML = newContent.innerHTML
      reexecScripts(document.getElementById('content'))
    }
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
  const ts   = new Date(m.timestamp * 1000).toLocaleTimeString('it', { hour: '2-digit', minute: '2-digit' })
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
}

// ===== GRAFICI (stub, completato in Task telemetry) =====
function initChartsIfNeeded() { /* implementato in telemetry.html inline */ }
function updateTelemetryChart(data) { window.dispatchEvent(new CustomEvent('telemetry-update', { detail: data })) }
function updateSensorDisplay(data) { window.dispatchEvent(new CustomEvent('sensor-update', { detail: data })) }
function updateNodeRow(data) { window.dispatchEvent(new CustomEvent('node-update', { detail: data })) }

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
  if (!document.getElementById('toast-container')) {
    const tc = document.createElement('div')
    tc.id = 'toast-container'
    document.body.appendChild(tc)
  }
  initWS()
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
