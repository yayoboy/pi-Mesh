# UI Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactorizzare completamente l'interfaccia web di pi-Mesh con 6 tab, status bar multi-density, Material Design Icons SVG inline, supporto portrait/landscape e layout canali selezionabile.

**Architecture:** Refactor completo (Approccio A) — nuovo `base.html` + `style.css` + `app.js`, 6 template Jinja2, nuove route FastAPI. Nessun framework JS/CSS aggiunto: vanilla JS + CSS custom properties (tiny-css principles). MDI via SVG sprite inline (offline-safe).

**Tech Stack:** FastAPI, Jinja2, vanilla JS, CSS custom properties, Leaflet (mappa), Material Design Icons SVG sprite, WebSocket (già presente), SQLite/aiosqlite (già presente).

**Design doc:** `docs/plans/2026-03-25-ui-redesign-design.md`

**Security note:** Tutto il contenuto testuale proveniente dalla rete o da input utente DEVE passare per `esc()` prima di qualsiasi inserimento DOM. Preferire `textContent` per testo puro e `createElement` + `appendChild` per strutture HTML dinamiche — evitare `innerHTML` con dati non sanitizzati.

---

## Task 1: Estendi config.py con le nuove preferenze UI

**Files:**
- Modify: `config.py`

**Step 1: Aggiungi le 3 nuove variabili UI dopo `UI_THEME` (riga 50)**

```python
UI_THEME             = os.getenv("UI_THEME", "dark")
UI_STATUS_DENSITY    = os.getenv("UI_STATUS_DENSITY", "icons")   # compact | icons | full
UI_CHANNEL_LAYOUT    = os.getenv("UI_CHANNEL_LAYOUT", "list")    # list | tabs | unified
UI_ORIENTATION       = os.getenv("UI_ORIENTATION", "portrait")   # portrait | landscape
```

**Step 2: Verifica import config**

```bash
python -m pytest tests/test_config.py -v
```
Expected: PASS

**Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add UI_STATUS_DENSITY, UI_CHANNEL_LAYOUT, UI_ORIENTATION to config"
```

---

## Task 2: Aggiungi nuove route e API in main.py

**Files:**
- Modify: `main.py`

**Step 1: Sostituisci il redirect radice e aggiungi le 4 nuove pagine**

Dopo la route `GET /settings` esistente, aggiungi:

```python
@app.get("/")
async def root():
    return RedirectResponse("/home")

@app.get("/home")
async def home_page(request: Request):
    nodes    = await database.get_nodes(_conn)
    node_info = meshtastic_client.get_local_node()
    return templates.TemplateResponse("home.html", {
        "request": request, "nodes": nodes, "node": node_info,
        "theme": cfg.UI_THEME, "density": cfg.UI_STATUS_DENSITY,
        "orientation": cfg.UI_ORIENTATION, "channel_layout": cfg.UI_CHANNEL_LAYOUT,
        "active": "home",
    })

@app.get("/channels")
async def channels_page(request: Request):
    msgs  = await database.get_messages(_conn, channel=0, limit=50)
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse("channels.html", {
        "request": request, "messages": msgs, "nodes": nodes,
        "theme": cfg.UI_THEME, "density": cfg.UI_STATUS_DENSITY,
        "orientation": cfg.UI_ORIENTATION, "channel_layout": cfg.UI_CHANNEL_LAYOUT,
        "active": "channels",
    })

@app.get("/hardware")
async def hardware_page(request: Request):
    sensors = getattr(app.state, "i2c_sensors", [])
    return templates.TemplateResponse("hardware.html", {
        "request": request, "i2c_sensors": sensors,
        "enc1": (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        "enc2": (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        "theme": cfg.UI_THEME, "density": cfg.UI_STATUS_DENSITY,
        "orientation": cfg.UI_ORIENTATION, "channel_layout": cfg.UI_CHANNEL_LAYOUT,
        "active": "hardware",
    })

@app.get("/remote")
async def remote_page(request: Request):
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse("remote.html", {
        "request": request, "nodes": nodes,
        "theme": cfg.UI_THEME, "density": cfg.UI_STATUS_DENSITY,
        "orientation": cfg.UI_ORIENTATION, "channel_layout": cfg.UI_CHANNEL_LAYOUT,
        "active": "remote",
    })
```

**Step 2: Aggiorna le route /map e /settings aggiungendo i 3 nuovi campi al context**

In `map_page` e `settings_page` aggiungi:
```python
"density": cfg.UI_STATUS_DENSITY,
"orientation": cfg.UI_ORIENTATION,
"channel_layout": cfg.UI_CHANNEL_LAYOUT,
```

**Step 3: Aggiungi API UI settings**

```python
@app.post("/settings/ui")
async def apply_ui_settings(payload: dict):
    import pathlib
    allowed = {"UI_STATUS_DENSITY", "UI_CHANNEL_LAYOUT", "UI_ORIENTATION", "UI_THEME"}
    env_path = pathlib.Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updated = {}
    for key, val in payload.items():
        if key not in allowed:
            continue
        val = str(val).strip()
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={val}"
                found = True
        if not found:
            lines.append(f"{key}={val}")
        updated[key] = val
    env_path.write_text("\n".join(lines) + "\n")
    return {"ok": True, "updated": updated}

@app.get("/api/tile/cache/info")
async def tile_cache_info():
    import pathlib
    tiles_dir = pathlib.Path("static/tiles")
    total = sum(f.stat().st_size for f in tiles_dir.rglob("*") if f.is_file())
    return {"size_bytes": total, "size_mb": round(total / 1024 / 1024, 1)}

@app.post("/api/remote/{node_id}/command")
async def remote_command(node_id: str, payload: dict):
    cmd = payload.get("cmd")
    if cmd not in ("reboot", "mute", "ping", "set_config", "request_telemetry"):
        return JSONResponse({"ok": False, "error": "cmd non valido"}, status_code=400)
    try:
        await meshtastic_client.send_admin(node_id, cmd, payload.get("params", {}))
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
```

**Step 4: Aggiungi redirect legacy**

```python
@app.get("/messages")
async def legacy_messages(): return RedirectResponse("/channels")

@app.get("/nodes")
async def legacy_nodes(): return RedirectResponse("/home")

@app.get("/telemetry")
async def legacy_telemetry(): return RedirectResponse("/hardware")
```

**Step 5: Aggiungi stub send_admin in meshtastic_client.py**

```python
async def send_admin(node_id: str, cmd: str, params: dict):
    """Invia comando admin via Meshtastic admin channel. TODO: implementazione reale."""
    raise NotImplementedError(f"send_admin({cmd}) non ancora implementato")
```

**Step 6: Aggiungi "sat" agli allowed sources nel tile server (riga ~211)**

```python
if source not in ("osm", "topo", "sat"):
```

**Step 7: Verifica**

```bash
python -c "import main; print('OK')"
```

**Step 8: Commit**

```bash
git add main.py meshtastic_client.py
git commit -m "feat: nuove route /home /channels /hardware /remote + API settings/ui + tile sat"
```

---

## Task 3: Crea SVG sprite Material Design Icons

**Files:**
- Create: `static/icons.svg`
- Create: `templates/icons.svg` (copia per Jinja2 include)

**Step 1: Crea static/icons.svg**

Il file SVG sprite contiene tutti i symbol MDI necessari con `style="display:none"` sul root svg.
Simboli richiesti (ID → icona MDI):

| ID symbol | Icona MDI | Uso |
|-----------|-----------|-----|
| `i-router` | router | Meshtastic connection |
| `i-usb` | usb | USB Serial |
| `i-gps-fixed` | gps_fixed | GPS fix |
| `i-gps-not-fixed` | gps_not_fixed | GPS no fix |
| `i-battery` | battery_5_bar | Batteria |
| `i-bolt` | bolt | Carica |
| `i-sync` | sync_alt | TX/RX |
| `i-home` | home | Tab Home |
| `i-forum` | forum | Tab Chat |
| `i-map` | map | Tab Mappa |
| `i-memory` | memory | Tab HW |
| `i-settings` | settings | Tab Settings |
| `i-remote` | cloud_sync | Tab Remote |
| `i-temp` | thermostat | Temperatura |
| `i-storage` | storage | Disco |
| `i-clock` | schedule | Orologio |
| `i-back` | arrow_back | Indietro |
| `i-send` | send | Invia |
| `i-refresh` | refresh | Aggiorna |
| `i-layers` | layers | Layer mappa |
| `i-location` | my_location | Posizione |
| `i-check` | check_circle | OK |
| `i-warn` | warning | Warning |
| `i-error` | error | Errore |

I path SVG reali di ogni icona si trovano su https://fonts.google.com/icons
oppure nel pacchetto npm `@mdi/svg/svg/*.svg`.

Struttura file:
```xml
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">
  <symbol id="i-router" viewBox="0 0 24 24"><path d="..."/></symbol>
  <!-- ... altri symbol ... -->
</svg>
```

**Step 2: Copia in templates/**

```bash
cp static/icons.svg templates/icons.svg
```

**Step 3: Verifica XML valido**

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('static/icons.svg'); print('OK')"
```

**Step 4: Commit**

```bash
git add static/icons.svg templates/icons.svg
git commit -m "feat: MDI SVG sprite inline (offline-safe, 24 icone)"
```

---

## Task 4: Riscrivi style.css

**Files:**
- Modify: `static/style.css`

**Step 1: Sostituisci l'intero file con il nuovo CSS**

Il file implementa (in ordine):
1. Reset minimale (`box-sizing`, `margin`, `padding`)
2. Design tokens in `:root` (colori stato, layout, superfici dark)
3. Varianti tema: `body.theme-light`, `body.theme-hc`
4. Status bar density: `body[data-density="compact/icons/full"]`
5. Layout grid `#app`: `grid-template-rows: var(--status-h) 1fr var(--tabbar-h)`
6. Layout landscape: `body.orient-landscape #app` con colonne invece di righe
7. Componenti: `.card`, `.stat-row`, `.node-row`, `.bubble`, `.gpio-pin`, `.setting-row`, `.btn`, `.pill-btn`, `.badge`
8. Accessibility: `:focus-visible`, `forced-colors`, `prefers-reduced-motion`

Valori token principali:
```
--ok: #4caf50  --warn: #ff9800  --danger: #f44336
--accent: #2196f3  --muted: #888
--bg: #121212  --bg2: #1e1e1e  --bg3: #2a2a2a  (dark)
--bg: #f5f5f5  --bg2: #fff     --bg3: #e8e8e8  (light)
--status-h: 20px (compact) | 24px (icons) | 32px (full)
--tabbar-h: 48px
```

**Step 2: Commit**

```bash
git add static/style.css
git commit -m "feat: riscrittura style.css — tiny-css, design tokens, 6-tab layout, density modes"
```

---

## Task 5: Riscrivi base.html

**Files:**
- Modify: `templates/base.html`

**Step 1: Sostituisci il contenuto**

```html
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=320, initial-scale=1, maximum-scale=1">
  <title>pi-Mesh</title>
  <link rel="stylesheet" href="/static/style.css">
  {% include 'icons.svg' %}
</head>
<body
  class="theme-{{ theme }}{% if orientation == 'landscape' %} orient-landscape{% endif %}"
  data-density="{{ density }}"
  data-orientation="{{ orientation }}"
  data-channel-layout="{{ channel_layout }}"
>
<div id="app">

  <div id="status-bar" role="status" aria-label="Stato sistema">
    <span class="status-item muted" id="st-mesh" title="Meshtastic">
      <svg aria-hidden="true"><use href="#i-router"/></svg>
      <span class="val" id="st-mesh-val"></span>
    </span>
    <span class="status-item muted" id="st-usb" title="USB Serial">
      <svg aria-hidden="true"><use href="#i-usb"/></svg>
    </span>
    <span class="status-item muted" id="st-gps" title="GPS">
      <svg aria-hidden="true"><use href="#i-gps-not-fixed"/></svg>
      <span class="val" id="st-gps-val"></span>
    </span>
    <span class="status-item muted" id="st-bat" title="Batteria">
      <svg aria-hidden="true"><use href="#i-battery"/></svg>
      <span class="val" id="st-bat-val"></span>
    </span>
    <span class="status-item muted" id="st-txrx" title="TX/RX">
      <svg aria-hidden="true"><use href="#i-sync"/></svg>
    </span>
  </div>

  <main id="content" role="main">
    {% block content %}{% endblock %}
  </main>

  <nav id="tabbar" role="navigation" aria-label="Navigazione principale">
    <a href="/home"     class="tab-btn {% if active=='home'     %}active{% endif %}" aria-label="Home">
      <svg aria-hidden="true"><use href="#i-home"/></svg><span>Home</span>
    </a>
    <a href="/channels" class="tab-btn {% if active=='channels' %}active{% endif %}" aria-label="Chat">
      <svg aria-hidden="true"><use href="#i-forum"/></svg><span>Chat</span>
    </a>
    <a href="/map"      class="tab-btn {% if active=='map'      %}active{% endif %}" aria-label="Mappa">
      <svg aria-hidden="true"><use href="#i-map"/></svg><span>Mappa</span>
    </a>
    <a href="/hardware" class="tab-btn {% if active=='hardware' %}active{% endif %}" aria-label="Hardware">
      <svg aria-hidden="true"><use href="#i-memory"/></svg><span>HW</span>
    </a>
    <a href="/settings" class="tab-btn {% if active=='settings' %}active{% endif %}" aria-label="Impostazioni">
      <svg aria-hidden="true"><use href="#i-settings"/></svg><span>Set</span>
    </a>
    <a href="/remote"   class="tab-btn {% if active=='remote'   %}active{% endif %}" aria-label="Remote">
      <svg aria-hidden="true"><use href="#i-remote"/></svg><span>RMT</span>
    </a>
  </nav>

</div>
<script src="/static/app.js"></script>
</body>
</html>
```

**Step 2: Commit**

```bash
git add templates/base.html
git commit -m "feat: nuovo base.html — status bar MDI 5 indicatori + 6-tab nav"
```

---

## Task 6: Riscrivi app.js (DOM sicuro, no innerHTML con dati utente)

**Files:**
- Modify: `static/app.js`

**Step 1: Sostituisci con il nuovo app.js**

Regole sicurezza applicate nel codice:
- `textContent` per tutti i testi derivati da dati di rete
- `createElement + appendChild` per strutture DOM dinamiche
- `esc()` usato solo come difesa aggiuntiva nei rari casi di HTML composito

```javascript
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
  let row = list.querySelector('[data-node="' + msg.id + '"]');
  if (!row) { row = document.createElement('div'); row.className = 'node-row'; row.dataset.node = msg.id; list.prepend(row); }
  // Costruisci DOM senza innerHTML per sicurezza
  row.textContent = '';
  const dot  = document.createElement('span'); dot.className = 'node-dot';
  const name = document.createElement('span'); name.className = 'node-name';
  const meta = document.createElement('span'); meta.className = 'node-meta';
  const age = msg.last_heard ? Math.floor((Date.now()/1000 - msg.last_heard) / 60) : null;
  dot.classList.add(age == null ? '' : age < 15 ? 'ok' : age < 120 ? 'warn' : '');
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
    sender.textContent = msg.sender;
    wrap.appendChild(sender);
  }
  const text = document.createElement('div');
  text.textContent = msg.text;
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
  const text  = input.value.trim();
  if (!text) return;
  const ch = parseInt(document.getElementById('ch-select')?.value ?? '0');
  const res = await fetch('/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, channel: ch, destination: currentDest }),
  });
  if (res.ok) input.value = '';
});

function handleTelemetry(msg) { /* TODO: aggiornamento tab Hardware */ }
function handleSensor(msg) { /* TODO: aggiornamento I2C live */ }

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
}

// === CHANNEL LAYOUT ===
function showChat(channelId, channelName, dest) {
  currentChannel = channelId;
  currentDest    = dest || '^all';
  if (document.body.dataset.channelLayout === 'list') {
    document.getElementById('channel-list')?.style.setProperty('display', 'none');
    document.getElementById('chat-view')?.style.setProperty('display', 'flex');
    const el = document.getElementById('chat-channel-name');
    if (el) el.textContent = channelName;
  }
  loadMessages(channelId);
}

function hideChat() {
  document.getElementById('channel-list')?.style.setProperty('display', '');
  document.getElementById('chat-view')?.style.setProperty('display', 'none');
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

// === UTILITY ===
function fmtTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}
```

**Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat: riscrivi app.js — DOM sicuro (textContent/createElement), encoder, chat, UI settings"
```

---

## Task 7: Crea template home.html

**Files:**
- Create: `templates/home.html`

**Step 1: Crea il file**

Il template estende `base.html` e contiene:
- Card "Nodo locale": nome, ID, batteria, canale (dati da `{{ node }}`)
- Card "Raspberry Pi": CPU, RAM, temperatura, disco, uptime (ID `sys-cpu`, `sys-ram`, `sys-temp`, `sys-disk`, `sys-uptime` — aggiornati via WebSocket)
- Sezione "Nodi recenti": loop Jinja2 su `{{ nodes[:4] }}` con `.node-row` e `.node-dot`

Struttura card con `.stat-row` per ogni metrica, icone MDI via `<svg><use href="#i-xxx"/></svg>`.

**Step 2: Commit**

```bash
git add templates/home.html
git commit -m "feat: template home.html — card nodo locale, sistema RPi, nodi recenti"
```

---

## Task 8: Crea template channels.html

**Files:**
- Create: `templates/channels.html`

**Step 1: Crea il file**

Il template usa `{{ channel_layout }}` per scegliere tra 3 strutture:

**layout `list`** (default):
- `div#channel-list`: lista CH 0–7 + nodi privati, ogni riga `onclick="showChat(ch, nome, dest)"`
- `div#chat-view` nascosto (`display:none`): header con `button#btn-back onclick="hideChat()"`, `div#chat-messages`, `form#msg-form` con `select#ch-select` + `input#chat-input`

**layout `tabs`**:
- Due pill button `Canali | Privati` che mostrano/nascondono `div#tab-broadcast` e `div#tab-private`
- Chat view sotto

**layout `unified`**:
- Lista unica con emoji 📢/👤 come prefisso testuale (in `textContent`, non HTML)

Tutti i testi da `{{ n.short_name }}` usano il filtro Jinja2 `{{ n.short_name | e }}` (escape automatico Jinja2).

**Step 2: Commit**

```bash
git add templates/channels.html
git commit -m "feat: template channels.html — 3 layout chat selezionabili via data-channel-layout"
```

---

## Task 9: Aggiorna template map.html

**Files:**
- Modify: `templates/map.html`

**Step 1: Aggiungi extends base.html e aggiorna i parametri template**

Sostituisci l'header del template per estendere il nuovo base:
```html
{% extends "base.html" %}
{% block content %}
<div style="position:relative;height:100%">
  <div id="map"></div>
  <!-- overlay layer switcher -->
  <div class="map-overlay map-overlay-tr">
    <div class="pill-group">
      <button class="pill-btn active" id="btn-osm"  onclick="setLayer('osm',this)">OSM</button>
      <button class="pill-btn"        id="btn-sat"  onclick="setLayer('sat',this)">SAT</button>
      <button class="pill-btn"        id="btn-topo" onclick="setLayer('topo',this)">TOPO</button>
    </div>
  </div>
  <!-- overlay bottom -->
  <div class="map-overlay map-overlay-bl" style="display:flex;gap:8px">
    <button class="btn btn-secondary" style="padding:6px 10px;font-size:12px" onclick="centerMap()">
      <svg style="width:16px;height:16px"><use href="#i-location"/></svg>
    </button>
  </div>
</div>
{% endblock %}
```

**Step 2: Nel blocco script Leaflet, aggiungi il terzo layer SAT**

```javascript
window._layers = {
  osm:  L.tileLayer('/tiles/osm/{z}/{x}/{y}',  { maxZoom: {{ zoom_max }} }),
  sat:  L.tileLayer('/tiles/sat/{z}/{x}/{y}',  { maxZoom: {{ zoom_max }} }),
  topo: L.tileLayer('/tiles/topo/{z}/{x}/{y}', { maxZoom: {{ zoom_max }} }),
};
window._map = L.map('map', { zoomControl: false }).setView([42, 12], 9);
window._layers.osm.addTo(window._map);

function setLayer(name, btn) {
  Object.values(window._layers).forEach(l => window._map.removeLayer(l));
  window._layers[name].addTo(window._map);
  document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}
function centerMap() {
  if (window._myPos) window._map.setView(window._myPos, 13);
}
```

**Step 3: Commit**

```bash
git add templates/map.html
git commit -m "feat: map.html aggiunge layer SAT + pill switcher OSM/SAT/TOPO + overlay bottom"
```

---

## Task 10: Crea template hardware.html

**Files:**
- Create: `templates/hardware.html`

**Step 1: Crea il file**

Struttura con 3 card:

**Card GPIO**:
- `.gpio-grid` con celle `.gpio-pin` generate via Jinja2 loop su pin BCM standard
- Legenda testuale colori (LOW/HIGH/PWM)

**Card Sensori I2C**:
- Loop `{% for s in i2c_sensors %}` con `.stat-row` per indirizzo (monospace) + nome
- Pulsante rescan che chiama `fetch('/api/i2c/scan?live=true')` e ricostruisce la lista via `createElement` + `textContent`

**Card Encoder**:
- Stato posizione ENC1 e ENC2 (valori aggiornati via WebSocket handler futuro)
- Pin A/B/SW mostrati da template Jinja2

**Step 2: Commit**

```bash
git add templates/hardware.html
git commit -m "feat: template hardware.html — GPIO grid, I2C list, encoder status"
```

---

## Task 11: Aggiorna template settings.html

**Files:**
- Modify: `templates/settings.html`

**Step 1: Aggiungi extends base.html e le nuove sezioni in cima**

Sezione **DISPLAY** (prima di tutto):
- Select tema → `onchange="saveUISetting('UI_THEME',this.value)"`
- Select orientamento → `onchange="saveUISetting('UI_ORIENTATION',this.value)"`
- Select barra stato → `onchange="saveUISetting('UI_STATUS_DENSITY',this.value)"`

Sezione **INTERFACCIA**:
- Select layout canali → `onchange="saveUISetting('UI_CHANNEL_LAYOUT',this.value)"`

Sezione **MAPPA**:
- Info dimensione cache (caricata via `fetch('/api/tile/cache/info')`)
- Button scarica area corrente (stub con `alert`)
- Button elimina cache

Le sezioni esistenti (CONNESSIONE, MESHTASTIC, SISTEMA) restano invariate nella logica, adattate al nuovo CSS (`.setting-row`, `.section-header`, `.btn`).

**Step 2: Commit**

```bash
git add templates/settings.html
git commit -m "feat: settings.html — sezioni DISPLAY/INTERFACCIA/MAPPA + UI_* settings"
```

---

## Task 12: Crea template remote.html

**Files:**
- Create: `templates/remote.html`

**Step 1: Crea il file**

Struttura con navigazione in-place (lista → dettaglio):

**`div#remote-list`**: loop Jinja2 su `{{ nodes }}` con `.node-row`, `.node-dot`, testo via `{{ n.short_name | e }}`, `onclick="openRemoteNode('{{ n.id | e }}', '{{ n.short_name | e }}')"`.

**`div#remote-detail`** (nascosto):
- Header con `button#btn-back onclick="closeRemoteNode()"`
- Card STATO: SNR, batteria, hop, ultimo contatto (ID `r-snr`, `r-bat`, `r-hop`, `r-last`)
- Card COMANDI: button Ping, Mute, Reboot (con `confirm()` per Reboot)
- Card CONFIGURAZIONE: input nome, select TX power, select GPS — button "Applica" con `confirm()` obbligatorio
- Card TELEMETRIA: temperatura, uptime — button "Richiedi aggiornamento"

Script inline per `openRemoteNode`, `closeRemoteNode`, `remoteCmd`, `applyRemoteConfig`, `requestTelemetry`. Tutti i testi da dati di rete impostati via `textContent`.

**Step 2: Commit**

```bash
git add templates/remote.html
git commit -m "feat: template remote.html — selezione nodo, comandi, config, telemetria remota"
```

---

## Task 13: Test integrazione finale

**Step 1: Avvia il server**

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

**Step 2: Verifica che tutte le route rispondano**

```bash
for path in / /home /channels /map /hardware /settings /remote /messages /nodes /telemetry; do
  echo "$path → $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080$path)"
done
```

Expected:
- `/` → 307
- `/home /channels /map /hardware /settings /remote` → 200
- `/messages /nodes /telemetry` → 307 (redirect legacy)

**Step 3: Verifica SVG sprite caricato**

```bash
curl -s http://localhost:8080/home | grep -c "symbol id="
```
Expected: ≥ 20

**Step 4: Verifica API**

```bash
curl -s http://localhost:8080/api/status
curl -s http://localhost:8080/api/tile/cache/info
curl -s http://localhost:8080/api/i2c/scan
```
Expected: JSON validi, nessun 500

**Step 5: Rimuovi template obsoleti**

```bash
git rm templates/nodes.html templates/telemetry.html
```

**Step 6: Commit finale**

```bash
git add -A
git commit -m "chore: rimuovi template obsoleti nodes.html telemetry.html"
```

---

## Riepilogo commit attesi

| # | Commit |
|---|--------|
| 1 | feat: add UI_STATUS_DENSITY, UI_CHANNEL_LAYOUT, UI_ORIENTATION to config |
| 2 | feat: nuove route /home /channels /hardware /remote + API settings/ui + tile sat |
| 3 | feat: MDI SVG sprite inline (offline-safe, 24 icone) |
| 4 | feat: riscrittura style.css — tiny-css, design tokens, 6-tab layout, density modes |
| 5 | feat: nuovo base.html — status bar MDI 5 indicatori + 6-tab nav |
| 6 | feat: riscrivi app.js — DOM sicuro, encoder, chat, UI settings |
| 7 | feat: template home.html — card nodo locale, sistema RPi, nodi recenti |
| 8 | feat: template channels.html — 3 layout chat selezionabili |
| 9 | feat: map.html aggiunge layer SAT + pill switcher OSM/SAT/TOPO |
| 10 | feat: template hardware.html — GPIO grid, I2C list, encoder status |
| 11 | feat: settings.html — sezioni DISPLAY/INTERFACCIA/MAPPA + UI_* settings |
| 12 | feat: template remote.html — selezione nodo, comandi, config, telemetria remota |
| 13 | chore: rimuovi template obsoleti nodes.html telemetry.html |
