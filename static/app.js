'use strict';

// === WEBSOCKET ===
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.addEventListener('message', ({ data }) => {
  try {
    const msg = JSON.parse(data);
    switch (msg.type) {
      case 'status':    handleStatus(msg);   break;
      case 'node':      handleNode(msg);     break;
      case 'message':   handleMessage(msg);  break;
      case 'telemetry': handleTelemetry(msg);break;
      case 'sensor':    handleSensor(msg);   break;
      case 'encoder':   handleEncoder(msg);  break;
      case 'init':      handleStatus(msg);   break;
    }
  } catch (_) {}
});

// === STATUS BAR ===
function setStatusItem(id, stateClass, valText) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'status-item ' + stateClass;
  const val = el.querySelector('.val');
  if (val && valText !== undefined) val.textContent = valText;
}

function handleStatus(msg) {
  if (msg.mesh_connected !== undefined)
    setStatusItem('st-mesh', msg.mesh_connected ? 'ok' : 'danger',
      msg.node_count ? msg.node_count + 'n' : '');
  if (msg.serial_connected !== undefined)
    setStatusItem('st-usb', msg.serial_connected ? 'ok' : 'danger');
  if (msg.gps_fix !== undefined)
    setStatusItem('st-gps',
      msg.gps_fix === 3 ? 'ok' : msg.gps_fix === 2 ? 'warn' : 'danger',
      msg.gps_sats ? msg.gps_sats + 's' : '');
  if (msg.battery_pct !== undefined)
    setStatusItem('st-bat',
      msg.battery_pct > 50 ? 'ok' : msg.battery_pct > 20 ? 'warn' : 'danger',
      msg.battery_pct + '%');
  if (msg.tx_active || msg.rx_active) {
    setStatusItem('st-txrx', msg.tx_active ? 'warn' : 'ok');
    setTimeout(() => setStatusItem('st-txrx', 'muted'), 1000);
  }
  if (document.getElementById('sys-cpu')) updateHomeStatus(msg);
}

// === HOME ===
function updateHomeStatus(msg) {
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v ?? '—'; };
  set('sys-cpu',    msg.cpu_pct  != null ? msg.cpu_pct  + '%'  : null);
  set('sys-ram',    msg.ram_used != null ? msg.ram_used + 'MB' : null);
  set('sys-temp',   msg.temp_c   != null ? msg.temp_c   + '°C' : null);
  set('sys-disk',   msg.disk_used);
  set('sys-uptime', msg.uptime);
  const tempEl = document.getElementById('sys-temp');
  if (tempEl && msg.temp_c != null)
    tempEl.className = 'stat-val' + (msg.temp_c > 70 ? ' danger' : msg.temp_c > 60 ? ' warn' : '');
  const cpuEl = document.getElementById('sys-cpu');
  if (cpuEl && msg.cpu_pct != null)
    cpuEl.className = 'stat-val' + (msg.cpu_pct > 80 ? ' warn' : '');
}

function handleNode(msg) {
  const list = document.getElementById('nodes-list');
  if (!list) return;
  let row = list.querySelector('[data-node="' + CSS.escape(msg.id) + '"]');
  if (!row) {
    row = document.createElement('div');
    row.className = 'node-row';
    row.dataset.node = msg.id;
    list.prepend(row);
  }
  row.textContent = '';
  const dot  = document.createElement('span');
  const name = document.createElement('span');
  const meta = document.createElement('span');
  const age = msg.last_heard ? Math.floor((Date.now()/1000 - msg.last_heard) / 60) : null;
  dot.className  = 'node-dot' + (age == null ? '' : age < 15 ? ' ok' : age < 120 ? ' warn' : '');
  name.className = 'node-name';
  meta.className = 'node-meta';
  name.textContent = msg.short_name || msg.id;
  meta.textContent = (msg.snr != null ? msg.snr + 'dB' : '—') + (age != null ? '  ' + age + 'min' : '');
  row.append(dot, name, meta);
}

// === CHAT ===
let currentChannel = 0;
let currentDest    = '^all';

function handleMessage(msg) {
  const list = document.getElementById('chat-messages');
  if (!list || msg.channel !== currentChannel) return;
  list.appendChild(buildBubble(msg));
  list.scrollTop = list.scrollHeight;
}

function buildBubble(msg) {
  const isOut = msg.sender === 'local';
  const wrap  = document.createElement('div');
  wrap.className = 'bubble ' + (isOut ? 'out' : 'in');
  if (!isOut) {
    const sender = document.createElement('div');
    sender.className = 'bubble-meta';
    sender.textContent = msg.sender || '';
    wrap.appendChild(sender);
  }
  const text = document.createElement('div');
  text.textContent = msg.text || '';
  const meta = document.createElement('div');
  meta.className = 'bubble-meta';
  meta.textContent = (msg.snr != null ? msg.snr + 'dB · ' : '') + fmtTime(msg.ts);
  wrap.append(text, meta);
  return wrap;
}

document.addEventListener('submit', async e => {
  if (e.target.id !== 'msg-form') return;
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const text  = input ? input.value.trim() : '';
  if (!text) return;
  const chEl = document.getElementById('ch-select');
  const ch   = parseInt(chEl ? chEl.value : '0');
  const res  = await fetch('/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, channel: ch, destination: currentDest }),
  });
  if (res.ok && input) input.value = '';
});

function handleTelemetry(msg) { /* TODO: hardware tab live update */ }
function handleSensor(msg)    { /* TODO: I2C live update */ }

// === ENCODER ===
const TABS = ['/home', '/channels', '/map', '/hardware', '/settings', '/remote'];

function handleEncoder(msg) {
  if (msg.encoder === 1 && (msg.action === 'cw' || msg.action === 'ccw')) {
    const cur  = TABS.indexOf(location.pathname);
    const next = (cur + (msg.action === 'cw' ? 1 : -1) + TABS.length) % TABS.length;
    location.href = TABS[next];
  }
  if (msg.encoder === 2) {
    if (location.pathname === '/map' && window._map) {
      msg.action === 'cw' ? window._map.zoomIn() : window._map.zoomOut();
    } else {
      const content = document.getElementById('content');
      if (content) content.scrollTop += msg.action === 'cw' ? 80 : -80;
    }
    if (msg.action === 'long_press') document.getElementById('btn-back')?.click();
  }
}

// === SETTINGS UI ===
async function saveUISetting(key, val) {
  await fetch('/settings/ui', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ [key]: val }),
  });
  const body = document.body;
  if (key === 'UI_STATUS_DENSITY') body.dataset.density = val;
  if (key === 'UI_THEME') body.className = body.className.replace(/theme-\w+/, 'theme-' + val);
  if (key === 'UI_ORIENTATION') {
    body.classList.toggle('orient-landscape', val === 'landscape');
    body.dataset.orientation = val;
  }
  if (key === 'UI_CHANNEL_LAYOUT') body.dataset.channelLayout = val;
}

// === CHANNEL NAV ===
function showChat(channelId, channelName, dest) {
  currentChannel = channelId;
  currentDest    = dest || '^all';
  const layout = document.body.dataset.channelLayout;
  if (layout === 'list') {
    const cl = document.getElementById('channel-list');
    const cv = document.getElementById('chat-view');
    if (cl) cl.style.display = 'none';
    if (cv) cv.style.display = 'flex';
    const nameEl = document.getElementById('chat-channel-name');
    if (nameEl) nameEl.textContent = channelName;
  }
  loadMessages(channelId);
}

function hideChat() {
  const cl = document.getElementById('channel-list');
  const cv = document.getElementById('chat-view');
  if (cl) cl.style.display = '';
  if (cv) cv.style.display = 'none';
}

async function loadMessages(channel) {
  const res  = await fetch('/api/messages?channel=' + channel + '&limit=50');
  const msgs = await res.json();
  const list = document.getElementById('chat-messages');
  if (!list) return;
  list.textContent = '';
  msgs.forEach(m => list.appendChild(buildBubble(m)));
  list.scrollTop = list.scrollHeight;
}

// === REMOTE NAV ===
function openRemoteNode(id, name) {
  const rl = document.getElementById('remote-list');
  const rd = document.getElementById('remote-detail');
  if (rl) rl.style.display = 'none';
  if (rd) rd.style.display = '';
  const nameEl = document.getElementById('remote-node-name');
  if (nameEl) nameEl.textContent = name;
  window._remoteNodeId = id;
}

function closeRemoteNode() {
  const rl = document.getElementById('remote-list');
  const rd = document.getElementById('remote-detail');
  if (rl) rl.style.display = '';
  if (rd) rd.style.display = 'none';
  window._remoteNodeId = null;
}

async function remoteCmd(cmd) {
  const id = window._remoteNodeId;
  if (!id) return;
  const res  = await fetch('/api/remote/' + encodeURIComponent(id) + '/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cmd }),
  });
  const data = await res.json();
  alert(data.ok ? cmd + ' inviato' : 'Errore: ' + (data.error || ''));
}

// === UTILITY ===
function fmtTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}
