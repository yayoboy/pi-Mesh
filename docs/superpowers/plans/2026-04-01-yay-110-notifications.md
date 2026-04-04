# YAY-110 Notifiche Visive e Sistema di Alert — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare sistema di notifiche toast, badge messaggi non letti, e alert configurabili per nodo offline, batteria scarica, e RAM alta.

**Architecture:** Alert thresholds salvati in config.env e esposti via API. Badge unread messaggi nel tab bar con contatore aggiornato via WS. Alert checker client-side in app.js che controlla telemetria e stato nodi in arrivo via WS. Nessun nuovo background task server-side — tutti i check avvengono al ricevimento degli eventi WS esistenti. Sezione Alert in config.html per configurare soglie.

**Tech Stack:** Python/FastAPI, Alpine.js, CSS, WebSocket events

**Scope esclusioni:** LED GPIO (hardware-specific, sarà issue separata)

---

## File Structure

| File | Responsabilità |
|------|---------------|
| `config.py` | Aggiungere variabili ALERT_* |
| `routers/config_router.py` | Aggiungere GET/POST /api/config/alerts |
| `templates/config.html` | Aggiungere sezione Alert con soglie configurabili |
| `database.py` | Aggiungere funzione `get_total_unread()` |
| `routers/messages_router.py` | Aggiungere GET /api/messages/unread-count |
| `templates/base.html` | Aggiungere badge unread nel tab Msg |
| `static/app.js` | Alert checker su eventi WS, aggiornamento badge, toast migliorati |

---

### Task 1: Config alert thresholds e API

**Files:**
- Modify: `config.py`
- Modify: `routers/config_router.py`

- [ ] **Step 1: Aggiungere variabili alert a config.py**

In `config.py`, aggiungere dopo la riga `MAP_REGION`:

```python
# Alert thresholds
ALERT_NODE_OFFLINE_MIN = int(os.getenv('ALERT_NODE_OFFLINE_MIN', '30'))
ALERT_BATTERY_LOW      = int(os.getenv('ALERT_BATTERY_LOW', '20'))
ALERT_RAM_HIGH         = int(os.getenv('ALERT_RAM_HIGH', '85'))
```

- [ ] **Step 2: Aggiungere API endpoints alert in config_router.py**

In `routers/config_router.py`, aggiungere dopo la classe `MapConfigRequest` e relative routes:

```python
class AlertConfigRequest(BaseModel):
    node_offline_min: int
    battery_low: int
    ram_high: int


@router.get('/api/config/alerts')
async def get_alert_config():
    return {
        'node_offline_min': cfg.ALERT_NODE_OFFLINE_MIN,
        'battery_low': cfg.ALERT_BATTERY_LOW,
        'ram_high': cfg.ALERT_RAM_HIGH,
    }


@router.post('/api/config/alerts')
async def post_alert_config(body: AlertConfigRequest):
    _write_env('ALERT_NODE_OFFLINE_MIN', str(body.node_offline_min))
    _write_env('ALERT_BATTERY_LOW', str(body.battery_low))
    _write_env('ALERT_RAM_HIGH', str(body.ram_high))
    cfg.ALERT_NODE_OFFLINE_MIN = body.node_offline_min
    cfg.ALERT_BATTERY_LOW = body.battery_low
    cfg.ALERT_RAM_HIGH = body.ram_high
    return {'ok': True}
```

- [ ] **Step 3: Verificare**

Run: `cd /Users/yayoboy/Desktop/GitHub/pi-Mesh && python -c "import config as cfg; print(cfg.ALERT_NODE_OFFLINE_MIN, cfg.ALERT_BATTERY_LOW, cfg.ALERT_RAM_HIGH)"`
Expected: `30 20 85`

- [ ] **Step 4: Commit**

```bash
git add config.py routers/config_router.py
git commit -m "feat(alerts): add alert threshold config vars and API (YAY-110)"
```

---

### Task 2: Sezione Alert in config.html

**Files:**
- Modify: `templates/config.html`

- [ ] **Step 1: Aggiungere 'alert' alla lista sections**

Nel blocco `sections:` dell'Alpine.js data (circa riga 588), aggiungere:

```javascript
sections: [
  { id: 'node',     label: 'Nodo' },
  { id: 'lora',     label: 'LoRa' },
  { id: 'channels', label: 'Canali' },
  { id: 'gpio',     label: 'GPIO' },
  { id: 'theme',    label: 'Tema' },
  { id: 'wifi',     label: 'WiFi' },
  { id: 'rtc',      label: 'RTC' },
  { id: 'mappa',    label: 'Mappa' },
  { id: 'usb',      label: 'USB' },
  { id: 'alert',    label: 'Alert' },
],
```

- [ ] **Step 2: Aggiungere stato alert nell'Alpine.js data**

Dopo l'oggetto `usb: { ... }`, aggiungere:

```javascript
alert: { node_offline_min: 30, battery_low: 20, ram_high: 85, saving: false },
```

- [ ] **Step 3: Aggiungere loadAlert() e saveAlert() methods**

Dopo il metodo `restoreTilesToSd()`, aggiungere:

```javascript
async loadAlert() {
  try {
    const r = await fetch('/api/config/alerts')
    if (r.ok) {
      const d = await r.json()
      this.alert.node_offline_min = d.node_offline_min
      this.alert.battery_low = d.battery_low
      this.alert.ram_high = d.ram_high
    }
  } catch(e) {}
},

async saveAlert() {
  this.alert.saving = true
  try {
    await fetch('/api/config/alerts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        node_offline_min: this.alert.node_offline_min,
        battery_low: this.alert.battery_low,
        ram_high: this.alert.ram_high,
      })
    })
  } catch(e) {}
  this.alert.saving = false
},
```

- [ ] **Step 4: Aggiungere handler selectSection per alert**

Nel metodo `selectSection(s)`, aggiungere:

```javascript
if (s === 'alert') await this.loadAlert()
```

- [ ] **Step 5: Aggiungere template sezione Alert**

Prima del tag `</div>` che chiude il pannello destro (dopo la sezione USB template), aggiungere:

```html
<!-- ===== ALERT ===== -->
<div x-show="section === 'alert'" style="display:none;">
  <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:10px;">Soglie Alert</div>

  <div style="display:flex;flex-direction:column;gap:10px;">
    <div style="background:var(--panel);border-radius:6px;padding:10px;">
      <label style="font-size:11px;color:var(--muted);display:block;margin-bottom:4px;">Nodo offline dopo (minuti)</label>
      <input type="number" x-model.number="alert.node_offline_min" min="5" max="1440" step="5"
             style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:12px;color:var(--text);">
      <div style="font-size:9px;color:var(--muted);margin-top:2px;">Notifica se un nodo non è più sentito dopo N minuti</div>
    </div>

    <div style="background:var(--panel);border-radius:6px;padding:10px;">
      <label style="font-size:11px;color:var(--muted);display:block;margin-bottom:4px;">Batteria scarica sotto (%)</label>
      <input type="number" x-model.number="alert.battery_low" min="5" max="50" step="5"
             style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:12px;color:var(--text);">
      <div style="font-size:9px;color:var(--muted);margin-top:2px;">Notifica quando la batteria di un nodo scende sotto questa soglia</div>
    </div>

    <div style="background:var(--panel);border-radius:6px;padding:10px;">
      <label style="font-size:11px;color:var(--muted);display:block;margin-bottom:4px;">RAM alta sopra (%)</label>
      <input type="number" x-model.number="alert.ram_high" min="50" max="95" step="5"
             style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:12px;color:var(--text);">
      <div style="font-size:9px;color:var(--muted);margin-top:2px;">Notifica quando la RAM del Raspberry supera questa soglia</div>
    </div>

    <button @click="saveAlert()"
            :disabled="alert.saving"
            style="background:var(--accent);color:#fff;border:none;border-radius:6px;padding:8px;font-size:12px;font-weight:600;cursor:pointer;opacity:1;"
            :style="alert.saving && 'opacity:0.5;cursor:wait;'"
            x-text="alert.saving ? 'Salvataggio...' : 'Salva'"></button>
  </div>
</div>
```

- [ ] **Step 6: Commit**

```bash
git add templates/config.html
git commit -m "feat(alerts): add Alert config section in settings UI (YAY-110)"
```

---

### Task 3: Badge messaggi non letti nel tab bar

**Files:**
- Modify: `database.py`
- Modify: `routers/messages_router.py`
- Modify: `templates/base.html`
- Modify: `static/app.js`

- [ ] **Step 1: Aggiungere get_total_unread() in database.py**

In `database.py`, dopo la funzione `mark_dm_read()`, aggiungere:

```python
async def get_total_unread(db_path: str, local_id: str) -> int:
    """Return total unread DM count across all peers."""
    async with aiosqlite.connect(db_path) as db:
        c = await db.execute('''
            SELECT COALESCE(SUM(cnt), 0) FROM (
                SELECT COUNT(*) as cnt
                FROM messages m
                LEFT JOIN dm_reads dr ON dr.peer_id = m.node_id
                WHERE m.destination = ?
                  AND m.node_id != ?
                  AND m.timestamp > COALESCE(dr.last_read_ts, 0)
            )
        ''', (local_id, local_id))
        row = await c.fetchone()
        return row[0] if row else 0
```

- [ ] **Step 2: Aggiungere endpoint unread-count in messages_router.py**

In `routers/messages_router.py`, aggiungere:

```python
@router.get('/api/messages/unread-count')
async def unread_count():
    local_id = meshtasticd_client.get_local_id()
    if not local_id:
        return {'count': 0}
    count = await database.get_total_unread(cfg.DB_PATH, local_id)
    return {'count': count}
```

Nota: verificare che `meshtasticd_client` e `cfg` e `database` siano già importati nel file. Se `get_local_id()` non esiste, controllare come ottenere il local node id.

- [ ] **Step 3: Verificare che get_local_id esista in meshtasticd_client.py**

Cercare `get_local_id` o `_local_id` in `meshtasticd_client.py`. Se non esiste una funzione pubblica, aggiungere:

```python
def get_local_id() -> str | None:
    """Return the local node ID, or None if not yet known."""
    return _local_id
```

- [ ] **Step 4: Aggiungere badge nel tab Msg in base.html**

Nel template `base.html`, trovare il loop `{% for key, href, label, icon_path in tabs %}` e modificare il contenuto dell'`<a>` tag per aggiungere il badge. Sostituire:

```html
      {{ label }}
    </a>
```

con:

```html
      <span style="position:relative;">{{ label }}{% if key == 'messages' %}<span id="msg-badge"
        style="display:none;position:absolute;top:-6px;right:-10px;min-width:14px;height:14px;border-radius:7px;background:#ef4444;color:#fff;font-size:8px;font-weight:700;line-height:14px;text-align:center;padding:0 3px;"></span>{% endif %}</span>
    </a>
```

- [ ] **Step 5: Aggiungere logica badge in app.js**

In `static/app.js`, aggiungere dopo la funzione `updateWifiBadge()`:

```javascript
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
```

- [ ] **Step 6: Chiamare fetchUnreadCount su init e su nuovi messaggi**

In `DOMContentLoaded` (circa riga 398), aggiungere dopo `initWS()`:

```javascript
fetchUnreadCount()
```

Nella funzione `handleMessage(msg)`, aggiungere alla fine:

```javascript
  // Update unread badge if not on messages tab
  if (activeTab.name !== 'messages') {
    _unreadCount++
    updateMsgBadge(_unreadCount)
  }
```

Nella funzione `navigateTo(tabName)`, dopo `activeTab.name = tabName`, aggiungere:

```javascript
  if (tabName === 'messages') {
    updateMsgBadge(0)
  }
```

- [ ] **Step 7: Commit**

```bash
git add database.py routers/messages_router.py templates/base.html static/app.js
git commit -m "feat(alerts): add unread message badge on Msg tab (YAY-110)"
```

---

### Task 4: Alert checker client-side in app.js

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Aggiungere stato alert e config fetch**

In `static/app.js`, dopo il blocco `_unreadCount`, aggiungere:

```javascript
// ===== ALERT SYSTEM =====
const _alertConfig = { node_offline_min: 30, battery_low: 20, ram_high: 85 }
const _alertSent = new Map()  // key -> timestamp, debounce alerts

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
```

- [ ] **Step 2: Aggiungere check batteria nel handleTelemetry**

Nella funzione `handleTelemetry(msg)`, dopo l'update del nodeCache, aggiungere:

```javascript
  // Battery low alert
  if (msg.ttype === 'device' && msg.data?.battery_level != null) {
    const lvl = msg.data.battery_level
    if (lvl > 0 && lvl <= _alertConfig.battery_low) {
      const name = nodeCache.get(msg.id)?.short_name || msg.id
      if (shouldAlert('bat-' + msg.id, 600000)) {
        showToast('⚡ ' + name + ': batteria ' + lvl + '%', 'warn', 5000)
      }
    }
  }
```

- [ ] **Step 3: Aggiungere check RAM nel WS handler**

Nel `ws.onmessage`, il blocco che gestisce `rpi_telemetry` (riga 110-112), modificare per aggiungere il check RAM. Dopo la riga `window.dispatchEvent(new CustomEvent('ws-message', { detail: msg }))`, aggiungere un nuovo handler dedicato. In alternativa, aggiungere nell'handler map:

Aggiungere una nuova funzione e registrarla nel handlers map:

```javascript
function handleRpiTelemetry(msg) {
  window.dispatchEvent(new CustomEvent('ws-message', { detail: msg }))
  // RAM high alert
  if (msg.data?.ram_percent != null && msg.data.ram_percent > _alertConfig.ram_high) {
    if (shouldAlert('ram-high', 300000)) {
      showToast('⚠ RAM: ' + msg.data.ram_percent.toFixed(0) + '%', 'warn', 5000)
    }
  }
}
```

Registrare nel handlers map:

```javascript
const handlers = {
  ...existing handlers...
  rpi_telemetry: handleRpiTelemetry,
}
```

E rimuovere il vecchio blocco `if (msg.type === 'telemetry' || msg.type === 'rpi_telemetry')` sostituendo con:

```javascript
if (msg.type === 'telemetry') {
  window.dispatchEvent(new CustomEvent('ws-message', { detail: msg }))
}
```

(Poiché `rpi_telemetry` ora è gestito dal suo handler che già fa il dispatch.)

- [ ] **Step 4: Aggiungere node offline checker periodico**

Aggiungere funzione e timer:

```javascript
function checkNodesOffline() {
  const now = Math.floor(Date.now() / 1000)
  const threshold = _alertConfig.node_offline_min * 60
  nodeCache.forEach((node, id) => {
    if (node.is_local || !node.last_heard) return
    const age = now - node.last_heard
    if (age > threshold && age < threshold + 120) {
      // Only alert once near the threshold crossing (within 2 min window)
      if (shouldAlert('offline-' + id, 1800000)) {
        const name = node.short_name || id
        showToast('📡 ' + name + ' offline da ' + Math.round(age / 60) + 'min', 'warn', 5000)
      }
    }
  })
}
```

In `DOMContentLoaded`, aggiungere dopo `fetchUnreadCount()`:

```javascript
loadAlertConfig()
setInterval(checkNodesOffline, 60000)
```

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(alerts): add client-side alert checks for battery, RAM, node offline (YAY-110)"
```

---

### Task 5: Integrazione main.py e deploy

**Files:**
- Nessun file da modificare (le modifiche sono tutte client-side e in router già registrati)

- [ ] **Step 1: Verificare che meshtasticd_client.get_local_id() esista**

Se è stato aggiunto in Task 3, verificare. Altrimenti aggiungerlo.

- [ ] **Step 2: Deploy e test sul Pi**

```bash
sshpass -p pimesh rsync -avz --relative \
  config.py routers/config_router.py routers/messages_router.py \
  meshtasticd_client.py database.py \
  templates/config.html templates/base.html static/app.js \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 3: Verificare con Playwright**

1. Navigare a `http://192.168.1.36:8080/config`, selezionare sezione "Alert"
2. Verificare che i campi soglia siano visibili con valori default (30, 20, 85)
3. Modificare un valore e premere "Salva"
4. Ricaricare pagina — verificare che il valore persiste
5. Navigare a `/messages` — verificare che il badge non appare se non ci sono unread
6. Navigare a `/nodes` — verificare che lo status bar è invariato
7. Testare in portrait (320x480) e landscape (480x320)

- [ ] **Step 4: Commit finale**

```bash
git add -A
git commit -m "feat: visual notifications and alert system (YAY-110)"
```
