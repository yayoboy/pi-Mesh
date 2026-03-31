// static/map.js — YAY-114 map enhancements
// Caricato solo da map.html, NON da base.html
'use strict'

// --- Stato globale ---

let leafletMap = null
let mapReady = false
const markerCache = new Map()
let hopLinesLayer
let tracerouteLayer
let customMarkersLayer
let customMarkersData = []
let osmLayer = null
let topoLayer = null
let satelliteLayer = null
let activeLayer = null

// --- Icone SVG Heroicons ---

const ICON_PATHS = {
  antenna:  'M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0',
  base:     'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
  obstacle: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  poi:      'M17.657 16.657L13.414 20.9a2 2 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z',
  route:    'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7',
}

function makeSvgIcon(type, size, color) {
  size = size || 16
  color = color || 'currentColor'
  const path = ICON_PATHS[type] || ICON_PATHS.poi
  return '<svg width="' + size + '" height="' + size + '" fill="none" stroke="' + color +
    '" stroke-width="2" viewBox="0 0 24 24">' +
    '<path stroke-linecap="round" stroke-linejoin="round" d="' + path + '"/></svg>'
}

// --- Filtri ---

const DEFAULT_FILTERS = {
  showOnline: true, showOffline: false,
  showHopLines: true, showCustomMarkers: true, showLocalNode: true,
  maxHops: 7,
}

function loadFilters() {
  try {
    return Object.assign({}, DEFAULT_FILTERS, JSON.parse(localStorage.getItem('mapFilters') || '{}'))
  } catch (e) {
    return Object.assign({}, DEFAULT_FILTERS)
  }
}

function saveFilters(f) {
  localStorage.setItem('mapFilters', JSON.stringify(f))
}

function applyFilters() {
  if (!mapReady) return
  var f = loadFilters()
  markerCache.forEach(function(marker, nodeId) {
    var node = nodeCache.get(nodeId)
    if (!node) return
    var ago    = Date.now() / 1000 - (node.last_heard || 0)
    var online = ago < 1800
    var isLocal = !!node.is_local
    var visible = true
    if (isLocal && !f.showLocalNode)          visible = false
    if (!isLocal && online  && !f.showOnline)  visible = false
    if (!isLocal && !online && !f.showOffline) visible = false
    if (node.hop_count != null && node.hop_count > f.maxHops) visible = false
    if (visible) marker.addTo(leafletMap)
    else         leafletMap.removeLayer(marker)
  })
  if (f.showHopLines)      hopLinesLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(hopLinesLayer)
  if (f.showCustomMarkers) customMarkersLayer.addTo(leafletMap)
  else                     leafletMap.removeLayer(customMarkersLayer)
}

function initFilters() {
  var panel = document.getElementById('filter-panel')
  if (!panel) return
  var f = loadFilters()

  function bindCheckbox(id, key) {
    var el = document.getElementById(id)
    if (!el) return
    el.checked = f[key]
    el.onchange = function() {
      var nf = loadFilters()
      nf[key] = el.checked
      saveFilters(nf)
      applyFilters()
      renderHopLines()
    }
  }

  function bindRange(id, key) {
    var el  = document.getElementById(id)
    var lbl = document.getElementById(id + '-val')
    if (!el) return
    el.value = f[key]
    if (lbl) lbl.textContent = f[key]
    el.oninput = function() {
      var nf = loadFilters()
      nf[key] = parseInt(el.value)
      saveFilters(nf)
      if (lbl) lbl.textContent = el.value
      applyFilters()
    }
  }

  bindCheckbox('filter-online',   'showOnline')
  bindCheckbox('filter-offline',  'showOffline')
  bindCheckbox('filter-hoplines', 'showHopLines')
  bindCheckbox('filter-markers',  'showCustomMarkers')
  bindCheckbox('filter-local',    'showLocalNode')
  bindRange('filter-maxhops',     'maxHops')
}

// --- Hop Lines ---

function snrColor(snr) {
  if (snr == null) return '#555'
  if (snr > 5)     return '#4caf50'
  if (snr >= 0)    return '#fb8c00'
  return '#e53935'
}

function renderHopLines() {
  if (!mapReady) return
  hopLinesLayer.clearLayers()
  var f = loadFilters()
  if (!f.showHopLines) return
  var nodes = []
  nodeCache.forEach(function(n) { if (n.latitude && n.longitude) nodes.push(n) })
  var now = Date.now() / 1000
  nodes.forEach(function(a) {
    if (now - (a.last_heard || 0) > 1800) return
    nodes.forEach(function(b) {
      if (a.id >= b.id) return
      if (now - (b.last_heard || 0) > 1800) return
      var line = L.polyline(
        [[a.latitude, a.longitude], [b.latitude, b.longitude]],
        { color: snrColor(a.snr != null ? a.snr : b.snr), weight: 2.5, opacity: 0.75 }
      )
      hopLinesLayer.addLayer(line)
    })
  })
}

// --- Traceroute path ---

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

// --- Marker personalizzati ---

function renderCustomMarkersOnMap() {
  customMarkersLayer.clearLayers()
  customMarkersData.forEach(function(m) {
    var icon = L.divIcon({
      html:       makeSvgIcon(m.icon_type, 18, '#ffd54f'),
      className:  '',
      iconSize:   [18, 18],
      iconAnchor: [9, 18],
    })
    var marker = L.marker([m.latitude, m.longitude], { icon: icon })
    marker.bindPopup('<b>' + escHtml(m.label) + '</b>')
    marker.addTo(customMarkersLayer)
    marker._markerId = m.id
  })
}

async function loadCustomMarkers() {
  var r = await fetch('/api/map/markers')
  if (!r.ok) return
  var data = await r.json()
  customMarkersData = data.markers || []
  renderCustomMarkersOnMap()
  renderMarkerSidebar()
}

async function addCustomMarker(label, iconType, latlng) {
  var r = await fetch('/api/map/markers', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ label: label, icon_type: iconType, latitude: latlng.lat, longitude: latlng.lng }),
  })
  if (r.ok) await loadCustomMarkers()
}

async function removeCustomMarker(id) {
  var r = await fetch('/api/map/markers/' + id, { method: 'DELETE' })
  if (!r.ok) return
  customMarkersData = customMarkersData.filter(function(m) { return m.id !== id })
  renderCustomMarkersOnMap()
  renderMarkerSidebar()
}

function renderMarkerSidebar() {
  var list = document.getElementById('marker-list')
  if (!list) return
  list.textContent = ''
  customMarkersData.forEach(function(m) {
    var item = document.createElement('div')
    item.style.cssText = 'background:var(--panel,#1e2535);border-radius:3px;padding:3px 5px;display:flex;align-items:center;gap:4px;font-size:11px;margin-bottom:3px;'
    item.innerHTML = makeSvgIcon(m.icon_type, 11, 'var(--accent,#5c9bd6)')
    var lbl = document.createElement('span')
    lbl.style.flex = '1'
    lbl.textContent = m.label
    var del = document.createElement('button')
    del.style.cssText = 'background:none;border:none;color:var(--danger,#c62828);cursor:pointer;padding:0;font-size:11px;line-height:1;'
    del.textContent = '\u2715'
    ;(function(markerId) {
      del.onclick = function() { removeCustomMarker(markerId) }
    })(m.id)
    item.append(lbl, del)
    list.appendChild(item)
  })
}

// --- Context menu long-press su nodo ---

var _longPressTimer = null

function initNodeContextMenu(marker, node) {
  function showMenu() {
    closeContextMenu()
    var menu = document.createElement('div')
    menu.id = 'node-ctx-menu'
    menu.style.cssText = 'position:fixed;z-index:1000;background:var(--panel,#1e2535);border:1px solid var(--border,#2a3a4a);border-radius:5px;padding:3px 0;font-size:12px;min-width:140px;box-shadow:0 4px 12px rgba(0,0,0,.5);'

    var title = document.createElement('div')
    title.style.cssText = 'padding:3px 10px;font-size:10px;color:var(--accent,#5c9bd6);border-bottom:1px solid var(--border,#2a3a4a);margin-bottom:2px;'
    title.textContent = (node.short_name || node.id) + ' \u00b7 ' + node.id
    menu.appendChild(title)

    function menuItem(iconType, label, onClick) {
      var row = document.createElement('div')
      row.style.cssText = 'padding:5px 10px;display:flex;align-items:center;gap:7px;cursor:pointer;color:var(--text,#ccc);'
      row.onmouseenter = function() { row.style.background = 'var(--border,#2a3a4a)' }
      row.onmouseleave = function() { row.style.background = '' }
      row.innerHTML = makeSvgIcon(iconType, 12)
      row.appendChild(document.createTextNode(label))
      row.onclick = function() { closeContextMenu(); onClick() }
      menu.appendChild(row)
    }

    menuItem('poi', 'Invia DM', function() {
      var text = window.prompt('Messaggio a ' + (node.short_name || node.id) + ':')
      if (text && typeof nodeActions !== 'undefined') nodeActions.sendDM(node.id, text)
    })
    menuItem('antenna', 'Richiedi posizione', function() {
      if (typeof nodeActions !== 'undefined') nodeActions.requestPosition(node.id)
    })
    menuItem('route', 'Traceroute', function() {
      if (typeof nodeActions !== 'undefined') nodeActions.traceroute(node.id)
    })

    var pt    = leafletMap.latLngToContainerPoint(marker.getLatLng())
    var mapEl = document.getElementById('map-container')
    var rect  = mapEl.getBoundingClientRect()
    menu.style.left = (rect.left + pt.x + 10) + 'px'
    menu.style.top  = (rect.top  + pt.y - 20) + 'px'
    document.body.appendChild(menu)
    setTimeout(function() {
      document.addEventListener('click', closeContextMenu, { once: true })
    }, 50)
  }

  marker.on('touchstart', function() {
    _longPressTimer = setTimeout(showMenu, 300)
  })
  marker.on('touchend touchmove', function() {
    clearTimeout(_longPressTimer)
  })
}

function closeContextMenu() {
  var m = document.getElementById('node-ctx-menu')
  if (m) m.remove()
}

function formatAgo(ts) {
  if (!ts) return 'mai'
  var sec = Math.floor(Date.now() / 1000 - ts)
  if (sec < 60)   return sec + 's fa'
  if (sec < 3600) return Math.floor(sec / 60) + ' min fa'
  return Math.floor(sec / 3600) + 'h fa'
}

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

  // Header: avatar + names + close button
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
  var svgNS = 'http://www.w3.org/2000/svg'
  var s = document.createElementNS(svgNS, 'svg')
  s.setAttribute('width', '12'); s.setAttribute('height', '12')
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none')
  s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2.5')
  var p = document.createElementNS(svgNS, 'path')
  p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round')
  p.setAttribute('d', 'M6 18L18 6M6 6l12 12')
  s.appendChild(p)
  closeBtn.appendChild(s)
  closeBtn.onclick = function(e) { e.stopPropagation(); popup.style.display = 'none' }
  header.append(avatar, names, closeBtn)

  // short_name + id row
  var meta = document.createElement('div')
  meta.style.cssText = 'color:var(--muted,#888);font-size:9px;margin-bottom:3px;'
  meta.textContent = '*' + (node.short_name || '') + '* \u00b7 ' + node.id

  // last heard row
  var heard = document.createElement('div')
  heard.style.cssText = 'color:var(--muted,#888);font-size:9px;margin-bottom:7px;'
  heard.textContent = 'Sentito ' + formatAgo(node.last_heard)

  // stat boxes: hops, SNR, battery, distance
  var stats = document.createElement('div')
  stats.style.cssText = 'display:flex;gap:5px;'
  var distLabel = node.distance_km != null ? node.distance_km.toFixed(1) + 'km' : '\u2014'
  stats.append(
    makeStatBox(node.hop_count != null ? String(node.hop_count) : '\u2014', 'Hops'),
    makeStatBox(node.snr      != null ? node.snr + ' dB'        : '\u2014', 'SNR'),
    makeStatBox(node.battery_level != null ? node.battery_level + '%' : '\u2014', 'Batt'),
    makeStatBox(distLabel, 'Dist')
  )

  popup.append(header, meta, heard, stats)

  if (!node.is_local) {
    var actions = document.createElement('div')
    actions.style.cssText = 'display:flex;gap:4px;margin-top:7px;flex-wrap:wrap;'

    var trBtn = document.createElement('button')
    trBtn.style.cssText = 'flex:1;padding:4px 6px;background:var(--panel,#12151f);border:1px solid var(--border,#2a3a4a);border-radius:3px;color:var(--text,#ccc);font-size:9px;cursor:pointer;display:flex;align-items:center;gap:3px;'
    trBtn.textContent = 'Traceroute'
    trBtn.onclick = function(e) {
      e.stopPropagation()
      popup.style.display = 'none'
      if (typeof nodeActions !== 'undefined') {
        nodeActions.traceroute(node.id).catch(function() {
          if (typeof showToast === 'function') showToast('Traceroute fallito', 'warn')
        })
      }
    }

    var posBtn = document.createElement('button')
    posBtn.style.cssText = trBtn.style.cssText
    posBtn.textContent = 'Posiz.'
    posBtn.onclick = function(e) {
      e.stopPropagation()
      popup.style.display = 'none'
      if (typeof nodeActions !== 'undefined') nodeActions.requestPosition(node.id)
    }

    var dmBtn = document.createElement('button')
    dmBtn.style.cssText = trBtn.style.cssText
    dmBtn.textContent = 'DM'
    dmBtn.onclick = function(e) {
      e.stopPropagation()
      popup.style.display = 'none'
      var text = window.prompt('Messaggio a ' + (node.short_name || node.id) + ':')
      if (text && typeof nodeActions !== 'undefined') {
        nodeActions.sendDM(node.id, text).catch(function() {
          if (typeof showToast === 'function') showToast('DM fallito', 'warn')
        })
      }
    }

    actions.append(trBtn, posBtn, dmBtn)
    popup.appendChild(actions)
  }

  // Position next to marker
  var pt    = leafletMap.latLngToContainerPoint(marker.getLatLng())
  var mapEl = document.getElementById('map-container')
  var pw    = 200
  var left  = pt.x + 20
  if (left + pw > mapEl.offsetWidth - 10) left = pt.x - pw - 10
  popup.style.left    = left + 'px'
  popup.style.top     = Math.max(6, pt.y - 60) + 'px'
  popup.style.display = 'block'

  // Close on outside click
  setTimeout(function() {
    document.addEventListener('click', function closePopup(e) {
      if (!popup.contains(e.target)) {
        popup.style.display = 'none'
        document.removeEventListener('click', closePopup)
      }
    })
  }, 50)
}

// --- Inizializzazione mappa ---

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

  // Restore saved view, or center on board node, or fall back to bounds center
  var savedView = null
  try { savedView = JSON.parse(localStorage.getItem('mapView')) } catch(e) {}
  var center, zoom
  if (savedView) {
    center = [savedView.lat, savedView.lng]
    zoom = savedView.zoom
  } else {
    // Try to center on local board node
    var localNode = null
    nodeCache.forEach(function(n) { if (n.is_local && n.latitude && n.longitude) localNode = n })
    if (localNode) {
      center = [localNode.latitude, localNode.longitude]
      zoom = 11
    } else {
      center = [(bounds.lat_min + bounds.lat_max) / 2, (bounds.lon_min + bounds.lon_max) / 2]
      zoom = 10
    }
  }

  leafletMap = L.map('map-container', {
    center: center, zoom: zoom, zoomControl: false,
    maxZoom: zoomMax,
    tap: false,
    tapTolerance: 15,
  })

  // Save view on move/zoom
  leafletMap.on('moveend', function() {
    var c = leafletMap.getCenter()
    localStorage.setItem('mapView', JSON.stringify({ lat: c.lat, lng: c.lng, zoom: leafletMap.getZoom() }))
  })

  var tileOpts       = { maxZoom: zoomMax }
  var localTiles     = document.documentElement.dataset.localTiles === '1'
  osmLayer       = localTiles
    ? L.tileLayer('/static/tiles/osm/{z}/{x}/{y}', tileOpts)
    : L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', Object.assign({ attribution: '© OSM' }, tileOpts))
  topoLayer      = localTiles
    ? L.tileLayer('/static/tiles/topo/{z}/{x}/{y}', tileOpts)
    : L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', Object.assign({ attribution: '© OpenTopoMap' }, tileOpts))
  satelliteLayer = localTiles
    ? L.tileLayer('/static/tiles/satellite/{z}/{x}/{y}', tileOpts)
    : L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', Object.assign({ attribution: '© Esri' }, tileOpts))
  activeLayer    = osmLayer
  osmLayer.addTo(leafletMap)
  L.control.zoom({ position: 'bottomright' }).addTo(leafletMap)

  hopLinesLayer.addTo(leafletMap)
  customMarkersLayer.addTo(leafletMap)

  nodeCache.forEach(function(node) { updateMapMarker(node) })
  mapReady = true

  initFilters()
  applyFilters()
  renderHopLines()
  loadCustomMarkers()

  // Invalidate size after delay to ensure container is visible
  setTimeout(function() { leafletMap.invalidateSize() }, 200)

  var trNode = new URLSearchParams(window.location.search).get('traceroute')
  if (trNode) {
    fetch('/api/nodes/' + encodeURIComponent(trNode) + '/traceroute')
      .then(function(r) { return r.json() })
      .then(function(data) {
        if (data.results && data.results[0]) renderTraceroutePath(data.results[0].hops)
      })
  }
}

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

function switchLayer(name) {
  if (!mapReady) return
  var layers = { osm: osmLayer, topo: topoLayer, satellite: satelliteLayer }
  var next = layers[name]
  if (!next || next === activeLayer) return
  leafletMap.removeLayer(activeLayer)
  next.addTo(leafletMap)
  activeLayer = next
  document.querySelectorAll('.layer-btn').forEach(function(btn) {
    var on = btn.dataset.layer === name
    btn.style.borderColor = on ? 'var(--accent,#4a9eff)' : 'rgba(42,58,74,0.5)'
    btn.style.color = on ? 'var(--accent,#4a9eff)' : 'var(--text,#ccc)'
  })
}

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
    marker.on('click', function() { showNodePopup(marker, node) })
    initNodeContextMenu(marker, node)
    marker.addTo(leafletMap)
    markerCache.set(node.id, marker)
  }
  renderHopLines()
  applyFilters()
}

// --- Listener eventi WebSocket (dispatchati da app.js) ---

window.addEventListener('node-update',       function(e) { updateMapMarker(e.detail) })
window.addEventListener('traceroute_result', function(e) { renderTraceroutePath(e.detail.hops) })
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
