# YAY-159 MQTT Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere supporto MQTT completo: leggere/scrivere la config MQTT del dispositivo Meshtastic, client MQTT locale (paho-mqtt) che fa bridge bidirezionale mesh↔MQTT, e sezione UI nella pagina Config.

**Architecture:** 3 layer — (1) `meshtasticd_client.py` legge/scrive moduleConfig.mqtt del dispositivo via serial, (2) nuovo modulo `mqtt_bridge.py` gestisce il client paho-mqtt come background task, sottoscrive ai topic JSON del dispositivo e inoltra eventi via WebSocket, (3) sezione "MQTT" in config.html per gestire tutti i parametri + stato connessione.

**Tech Stack:** Python (paho-mqtt, asyncio), FastAPI, Alpine.js, Meshtastic protobuf API

---

## File Structure

| File | Responsabilità |
|------|---------------|
| `meshtasticd_client.py` | Nuove funzioni `get_mqtt_config()` / `set_mqtt_config()` per leggere/scrivere moduleConfig.mqtt dal dispositivo |
| `mqtt_bridge.py` | Client paho-mqtt: connect, subscribe, publish, event dispatch via WebSocket |
| `routers/config_router.py` | Endpoint API `GET/POST /api/config/mqtt` + `GET /api/config/mqtt/status` |
| `templates/config.html` | Sezione MQTT nella UI config con form parametri + stato connessione |
| `main.py` | Avvio background task mqtt_bridge |
| `config.py` | Variabili MQTT_* default |
| `requirements.txt` | Aggiunta paho-mqtt |

---

### Task 1: Aggiungere get/set MQTT config al client Meshtastic

**Files:**
- Modify: `meshtasticd_client.py`

Seguire il pattern esistente di `get_lora_config()` / `set_lora_config()` per leggere/scrivere `moduleConfig.mqtt`.

- [ ] **Step 1: Aggiungere `get_mqtt_config()` in meshtasticd_client.py**

Dopo la funzione `get_channels()` (circa riga 169), aggiungere:

```python
async def get_mqtt_config(db_path: str) -> dict:
    """Read MQTT module config from board, cache result."""
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.mqtt
                return {
                    'enabled': mc.enabled,
                    'address': mc.address or 'mqtt.meshtastic.org',
                    'username': mc.username or 'meshdev',
                    'password': mc.password or 'large4cats',
                    'encryption_enabled': mc.encryption_enabled,
                    'json_enabled': mc.json_enabled,
                    'tls_enabled': mc.tls_enabled,
                    'root': mc.root or 'msh',
                    'proxy_to_client_enabled': mc.proxy_to_client_enabled,
                    'map_reporting_enabled': mc.map_reporting_enabled,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'mqtt', data)
            return data
        except Exception as e:
            logger.error('get_mqtt_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'mqtt')
    if cached:
        cached['cached'] = True
        return cached
    return {
        'enabled': False, 'address': 'mqtt.meshtastic.org', 'username': 'meshdev',
        'password': 'large4cats', 'encryption_enabled': False, 'json_enabled': False,
        'tls_enabled': False, 'root': 'msh', 'proxy_to_client_enabled': False,
        'map_reporting_enabled': False, 'cached': True,
    }
```

- [ ] **Step 2: Aggiungere `_do_set_mqtt_config()` e `set_mqtt_config()`**

Dopo `set_lora_config()` (circa riga 203), aggiungere:

```python
def _do_set_mqtt_config(params: dict) -> None:
    """Sync helper — runs in command queue thread."""
    from meshtastic.protobuf import module_config_pb2
    mqtt_cfg = module_config_pb2.ModuleConfig.MQTTConfig(
        enabled=params.get('enabled', False),
        address=params.get('address', ''),
        username=params.get('username', ''),
        password=params.get('password', ''),
        encryption_enabled=params.get('encryption_enabled', False),
        json_enabled=params.get('json_enabled', False),
        tls_enabled=params.get('tls_enabled', False),
        root=params.get('root', ''),
        proxy_to_client_enabled=params.get('proxy_to_client_enabled', False),
        map_reporting_enabled=params.get('map_reporting_enabled', False),
    )
    _interface.localNode.setConfig(
        module_config_pb2.ModuleConfig(mqtt=mqtt_cfg)
    )


async def set_mqtt_config(params: dict) -> None:
    """Queue MQTT config write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    p = dict(params)
    await _command_queue.put(lambda: _do_set_mqtt_config(p))
```

- [ ] **Step 3: Verificare sintassi**

```bash
python3 -c "import ast; ast.parse(open('meshtasticd_client.py').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add meshtasticd_client.py
git commit -m "feat(mqtt): add get/set MQTT module config via serial interface (YAY-159)"
```

---

### Task 2: Creare mqtt_bridge.py — client MQTT bridge

**Files:**
- Create: `mqtt_bridge.py`

Modulo standalone che gestisce la connessione paho-mqtt. Sottoscrive ai topic JSON del dispositivo Meshtastic e inoltra i messaggi ricevuti come eventi WebSocket. Supporta anche il publish (downlink) verso il mesh.

- [ ] **Step 1: Creare mqtt_bridge.py**

```python
"""MQTT Bridge — connects to MQTT broker and bridges messages to/from WebSocket."""
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# paho-mqtt is optional — bridge is disabled if not installed
try:
    import paho.mqtt.client as paho_mqtt
    HAS_PAHO = True
except ImportError:
    HAS_PAHO = False
    logger.info('paho-mqtt not installed — MQTT bridge disabled')

_client: 'paho_mqtt.Client | None' = None
_loop: asyncio.AbstractEventLoop | None = None
_connected = False
_config: dict = {}

# Callback for dispatching MQTT events to WebSocket
_ws_dispatch = None


def set_ws_dispatch(fn):
    """Set the function used to dispatch events to WebSocket clients.
    Expected signature: fn(event_type: str, data: dict)"""
    global _ws_dispatch
    _ws_dispatch = fn


def _on_connect(client, userdata, flags, rc):
    global _connected
    if rc == 0:
        _connected = True
        logger.info('MQTT connected to %s', _config.get('address', '?'))
        # Subscribe to JSON topics
        root = _config.get('root', 'msh')
        topic = f"{root}/+/2/json/#"
        client.subscribe(topic)
        logger.info('MQTT subscribed to %s', topic)
        if _ws_dispatch and _loop:
            _loop.call_soon_threadsafe(
                _loop.create_task,
                _dispatch('mqtt-status', {'connected': True, 'broker': _config.get('address', '')})
            )
    else:
        _connected = False
        logger.error('MQTT connect failed rc=%d', rc)


def _on_disconnect(client, userdata, rc):
    global _connected
    _connected = False
    logger.warning('MQTT disconnected rc=%d', rc)
    if _ws_dispatch and _loop:
        _loop.call_soon_threadsafe(
            _loop.create_task,
            _dispatch('mqtt-status', {'connected': False, 'broker': _config.get('address', '')})
        )


def _on_message(client, userdata, msg):
    """Handle incoming MQTT message — parse JSON and dispatch to WS."""
    try:
        payload = json.loads(msg.payload.decode('utf-8', errors='replace'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    event_data = {
        'topic': msg.topic,
        'payload': payload,
        'type': payload.get('type', 'unknown'),
    }
    if _ws_dispatch and _loop:
        _loop.call_soon_threadsafe(
            _loop.create_task,
            _dispatch('mqtt-message', event_data)
        )


async def _dispatch(event_type: str, data: dict):
    """Async wrapper for WS dispatch."""
    if _ws_dispatch:
        try:
            await _ws_dispatch(event_type, data)
        except Exception as e:
            logger.error('MQTT dispatch error: %s', e)


async def start(config: dict):
    """Start MQTT bridge with given config. Non-blocking."""
    global _client, _loop, _config
    if not HAS_PAHO:
        logger.warning('Cannot start MQTT bridge: paho-mqtt not installed')
        return
    if not config.get('enabled'):
        logger.info('MQTT bridge disabled in config')
        return
    _config = config
    _loop = asyncio.get_event_loop()

    address = config.get('address', 'mqtt.meshtastic.org')
    username = config.get('username', 'meshdev')
    password = config.get('password', 'large4cats')
    tls = config.get('tls_enabled', False)
    port = 8883 if tls else 1883

    _client = paho_mqtt.Client(client_id='pimesh-bridge', protocol=paho_mqtt.MQTTv311)
    _client.on_connect = _on_connect
    _client.on_disconnect = _on_disconnect
    _client.on_message = _on_message

    if username:
        _client.username_pw_set(username, password)
    if tls:
        _client.tls_set()

    try:
        _client.connect_async(address, port, keepalive=60)
        _client.loop_start()
        logger.info('MQTT bridge starting → %s:%d', address, port)
    except Exception as e:
        logger.error('MQTT bridge start failed: %s', e)


async def stop():
    """Stop MQTT bridge gracefully."""
    global _client, _connected
    if _client:
        _client.loop_stop()
        _client.disconnect()
        _client = None
        _connected = False
        logger.info('MQTT bridge stopped')


async def restart(config: dict):
    """Restart bridge with new config."""
    await stop()
    await start(config)


def publish(topic: str, payload: str | dict) -> bool:
    """Publish a message to MQTT broker. Returns True on success."""
    if not _client or not _connected:
        return False
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    result = _client.publish(topic, payload, qos=0)
    return result.rc == 0


def publish_downlink(text: str, from_id: int, to_id: int | None = None, channel: int = 0) -> bool:
    """Send a text message to the mesh via MQTT downlink.
    Requires json_enabled on the device and downlink_enabled on the channel."""
    if not _client or not _connected:
        return False
    root = _config.get('root', 'msh')
    # Build topic: msh/REGION/2/json/CHANNELNAME/USERID
    # We use a simplified topic — the device's own MQTT module handles routing
    from_hex = f'!{from_id:08x}'
    topic = f"{root}/2/json/mqtt/{from_hex}"
    msg = {'from': from_id, 'type': 'sendtext', 'payload': text}
    if to_id:
        msg['to'] = to_id
    if channel:
        msg['channel'] = channel
    return publish(topic, msg)


def is_connected() -> bool:
    return _connected


def get_status() -> dict:
    return {
        'available': HAS_PAHO,
        'connected': _connected,
        'broker': _config.get('address', '') if _config else '',
        'enabled': _config.get('enabled', False) if _config else False,
    }
```

- [ ] **Step 2: Verificare sintassi**

```bash
python3 -c "import ast; ast.parse(open('mqtt_bridge.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add mqtt_bridge.py
git commit -m "feat(mqtt): add MQTT bridge module with paho-mqtt client (YAY-159)"
```

---

### Task 3: Aggiungere endpoint API MQTT in config_router.py

**Files:**
- Modify: `routers/config_router.py`

Aggiungere 3 endpoint: GET config, POST config (salva su device + riavvia bridge), GET status bridge.

- [ ] **Step 1: Aggiungere import mqtt_bridge in config_router.py**

All'inizio del file, dopo `import usb_storage`, aggiungere:

```python
import mqtt_bridge
```

- [ ] **Step 2: Aggiungere Pydantic model per MQTT config**

Dopo l'ultimo `BaseModel` esistente nel file, aggiungere:

```python
class MqttConfigRequest(BaseModel):
    enabled: bool = False
    address: str = 'mqtt.meshtastic.org'
    username: str = 'meshdev'
    password: str = 'large4cats'
    encryption_enabled: bool = False
    json_enabled: bool = False
    tls_enabled: bool = False
    root: str = 'msh'
    proxy_to_client_enabled: bool = False
    map_reporting_enabled: bool = False
```

- [ ] **Step 3: Aggiungere GET /api/config/mqtt**

```python
@router.get('/api/config/mqtt')
async def get_mqtt_config():
    data = await meshtasticd_client.get_mqtt_config(cfg.DB_PATH)
    return JSONResponse(data)
```

- [ ] **Step 4: Aggiungere POST /api/config/mqtt**

```python
@router.post('/api/config/mqtt')
async def save_mqtt_config(req: MqttConfigRequest):
    try:
        params = req.model_dump()
        await meshtasticd_client.set_mqtt_config(params)
        # Restart bridge with new config
        await mqtt_bridge.restart(params)
        return JSONResponse({'ok': True})
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)
```

- [ ] **Step 5: Aggiungere GET /api/config/mqtt/status**

```python
@router.get('/api/config/mqtt/status')
async def get_mqtt_status():
    return JSONResponse(mqtt_bridge.get_status())
```

- [ ] **Step 6: Verificare sintassi**

```bash
python3 -c "import ast; ast.parse(open('routers/config_router.py').read()); print('OK')"
```

- [ ] **Step 7: Commit**

```bash
git add routers/config_router.py
git commit -m "feat(mqtt): add MQTT config and status API endpoints (YAY-159)"
```

---

### Task 4: Integrare mqtt_bridge nel lifespan di main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Aggiungere import e startup task**

In `main.py`, aggiungere l'import di `mqtt_bridge` in cima (dopo gli altri import):

```python
import mqtt_bridge
```

Nella funzione `lifespan()`, dopo `asyncio.create_task(_telemetry_cleanup_task())`, aggiungere:

```python
    # Start MQTT bridge if configured
    mqtt_cfg = await meshtasticd_client.get_mqtt_config(cfg.DB_PATH)
    if mqtt_cfg.get('enabled'):
        mqtt_bridge.set_ws_dispatch(_mqtt_ws_dispatch)
        asyncio.create_task(mqtt_bridge.start(mqtt_cfg))
```

- [ ] **Step 2: Aggiungere _mqtt_ws_dispatch helper**

Prima della funzione `lifespan()`, aggiungere:

```python
async def _mqtt_ws_dispatch(event_type: str, data: dict):
    """Forward MQTT events to all connected WebSocket clients."""
    from routers.ws_router import broadcast
    await broadcast(event_type, data)
```

- [ ] **Step 3: Aggiungere stop nel lifespan yield**

Nel `lifespan()`, prima di `await meshtasticd_client.disconnect()`, aggiungere:

```python
    await mqtt_bridge.stop()
```

- [ ] **Step 4: Verificare sintassi**

```bash
python3 -c "import ast; ast.parse(open('main.py').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat(mqtt): start MQTT bridge as background task on startup (YAY-159)"
```

---

### Task 5: Aggiungere sezione MQTT nella UI config.html

**Files:**
- Modify: `templates/config.html`

- [ ] **Step 1: Aggiungere 'mqtt' alla lista sections**

In config.html, nella definizione di `sections` (circa riga 697), aggiungere dopo la riga `{ id: 'alert', label: 'Alert' },`:

```javascript
      { id: 'mqtt',     label: 'MQTT' },
```

- [ ] **Step 2: Aggiungere stato Alpine per MQTT**

Dopo la riga `alert: { ... }` (circa riga 711), aggiungere:

```javascript
    mqtt: { enabled: false, address: 'mqtt.meshtastic.org', username: 'meshdev', password: 'large4cats',
            encryption_enabled: false, json_enabled: false, tls_enabled: false, root: 'msh',
            proxy_to_client_enabled: false, map_reporting_enabled: false, cached: true },
    mqttStatus: { available: false, connected: false, broker: '', enabled: false },
    mqttSaving: false,
```

- [ ] **Step 3: Aggiungere load nel selectSection**

Nel metodo `selectSection()`, dopo `if (s === 'alert') await this.loadAlert()`, aggiungere:

```javascript
      if (s === 'mqtt') { await this.loadMqtt(); await this.loadMqttStatus() }
```

- [ ] **Step 4: Aggiungere metodi loadMqtt, loadMqttStatus, saveMqtt**

Dopo il metodo `saveAlert()` (o l'ultimo metodo prima della chiusura di `configPage()`), aggiungere:

```javascript
    async loadMqtt() {
      const r = await fetch('/api/config/mqtt')
      if (r.ok) this.mqtt = await r.json()
    },

    async loadMqttStatus() {
      const r = await fetch('/api/config/mqtt/status')
      if (r.ok) this.mqttStatus = await r.json()
    },

    async saveMqtt() {
      this.mqttSaving = true
      this.status.mqtt = ''
      try {
        const r = await fetch('/api/config/mqtt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            enabled: this.mqtt.enabled,
            address: this.mqtt.address,
            username: this.mqtt.username,
            password: this.mqtt.password,
            encryption_enabled: this.mqtt.encryption_enabled,
            json_enabled: this.mqtt.json_enabled,
            tls_enabled: this.mqtt.tls_enabled,
            root: this.mqtt.root,
            proxy_to_client_enabled: this.mqtt.proxy_to_client_enabled,
            map_reporting_enabled: this.mqtt.map_reporting_enabled,
          })
        })
        const data = await r.json()
        this.status.mqtt = r.ok ? '✓ Salvato — bridge riavviato' : '✗ ' + (data.error || 'Errore')
        if (r.ok) await this.loadMqttStatus()
      } finally {
        this.mqttSaving = false
      }
    },
```

- [ ] **Step 5: Aggiungere template HTML sezione MQTT**

Prima del commento `<!-- chiusura content area -->` o dopo l'ultimo `</template>` di una sezione (dopo la sezione 'alert'), aggiungere:

```html
    <!-- MQTT -->
    <template x-if="section === 'mqtt'">
      <div x-init="loadMqtt(); loadMqttStatus()">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <span style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);">MQTT</span>
          <span style="font-size:9px;" :style="mqtt.cached ? 'color:var(--muted)' : 'color:#4caf50'"
                x-text="mqtt.cached ? '◌ dalla cache' : '● board online'"></span>
        </div>

        <!-- Bridge status -->
        <div style="padding:8px 10px;background:var(--panel);border:1px solid var(--border);border-radius:6px;margin-bottom:10px;">
          <div style="display:flex;align-items:center;gap:6px;">
            <div style="width:8px;height:8px;border-radius:50%;flex-shrink:0;"
                 :style="mqttStatus.connected ? 'background:#4caf50' : 'background:#374151'"></div>
            <span style="font-size:11px;" :style="mqttStatus.connected ? 'color:var(--text);font-weight:600;' : 'color:var(--muted);'"
                  x-text="mqttStatus.connected ? 'Connesso a ' + mqttStatus.broker : (mqttStatus.available ? 'Non connesso' : 'paho-mqtt non installato')"></span>
          </div>
        </div>

        <!-- Enable toggle -->
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text);cursor:pointer;">
            <input type="checkbox" x-model="mqtt.enabled" style="accent-color:var(--accent);">
            Abilita MQTT
          </label>
        </div>

        <template x-if="mqtt.enabled">
          <div style="display:flex;flex-direction:column;gap:8px;">
            <!-- Broker -->
            <div style="display:flex;flex-direction:column;gap:2px;">
              <label style="font-size:10px;color:var(--muted);">Server</label>
              <input x-model="mqtt.address" placeholder="mqtt.meshtastic.org"
                     style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
            </div>

            <!-- Credentials -->
            <div style="display:flex;gap:6px;">
              <div style="flex:1;display:flex;flex-direction:column;gap:2px;">
                <label style="font-size:10px;color:var(--muted);">Username</label>
                <input x-model="mqtt.username" placeholder="meshdev"
                       style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
              </div>
              <div style="flex:1;display:flex;flex-direction:column;gap:2px;">
                <label style="font-size:10px;color:var(--muted);">Password</label>
                <input x-model="mqtt.password" type="password" placeholder="large4cats" autocomplete="new-password"
                       style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
              </div>
            </div>

            <!-- Root topic -->
            <div style="display:flex;flex-direction:column;gap:2px;">
              <label style="font-size:10px;color:var(--muted);">Root Topic</label>
              <input x-model="mqtt.root" placeholder="msh"
                     style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
            </div>

            <!-- Toggle options -->
            <div style="display:flex;flex-direction:column;gap:6px;padding:8px 10px;background:var(--panel);border:1px solid var(--border);border-radius:6px;">
              <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text);cursor:pointer;">
                <input type="checkbox" x-model="mqtt.json_enabled" style="accent-color:var(--accent);">
                JSON abilitato
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text);cursor:pointer;">
                <input type="checkbox" x-model="mqtt.encryption_enabled" style="accent-color:var(--accent);">
                Crittografia pacchetti
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text);cursor:pointer;">
                <input type="checkbox" x-model="mqtt.tls_enabled" style="accent-color:var(--accent);">
                TLS
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text);cursor:pointer;">
                <input type="checkbox" x-model="mqtt.map_reporting_enabled" style="accent-color:var(--accent);">
                Map reporting
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text);cursor:pointer;">
                <input type="checkbox" x-model="mqtt.proxy_to_client_enabled" style="accent-color:var(--accent);">
                Proxy to client
              </label>
            </div>

            <!-- Save button -->
            <button @click="saveMqtt()" :disabled="mqttSaving || mqtt.cached"
                    style="padding:10px;font-size:12px;border:none;border-radius:6px;cursor:pointer;font-weight:600;"
                    :style="(mqttSaving || mqtt.cached) ? 'background:var(--border);color:var(--muted);cursor:not-allowed;' : 'background:var(--accent);color:#fff;'"
                    x-text="mqttSaving ? 'Salvataggio...' : 'Salva e riavvia bridge'">
            </button>
          </div>
        </template>

        <!-- Status message -->
        <div x-show="status.mqtt" x-text="status.mqtt" style="font-size:10px;margin-top:6px;"
             :style="status.mqtt && status.mqtt.startsWith('✓') ? 'color:#4caf50' : 'color:#ef4444'"></div>
      </div>
    </template>
```

- [ ] **Step 6: Aggiungere 'mqtt' al status object**

Nella riga `status: { node: '', lora: '', channels: '', gpio: '', wifi: '' },`, aggiungere `mqtt: ''`:

```javascript
    status: { node: '', lora: '', channels: '', gpio: '', wifi: '', mqtt: '' },
```

- [ ] **Step 7: Verificare che il template è valido**

Controllare visivamente che i tag template siano bilanciati e il JSON Alpine sia valido.

- [ ] **Step 8: Commit**

```bash
git add templates/config.html
git commit -m "feat(mqtt): add MQTT configuration section to config UI (YAY-159)"
```

---

### Task 6: Aggiungere paho-mqtt a requirements.txt e config defaults

**Files:**
- Modify: `requirements.txt` (se esiste) o documentare la dipendenza
- Modify: `config.py`

- [ ] **Step 1: Verificare e aggiornare requirements.txt**

Verificare se esiste `requirements.txt`. Se sì, aggiungere `paho-mqtt>=2.0.0`. Se no, creare.

- [ ] **Step 2: Aggiungere defaults MQTT a config.py**

In `config.py`, alla fine, aggiungere:

```python
# MQTT bridge defaults (override via config.env)
MQTT_ENABLED = os.getenv('MQTT_ENABLED', '0') == '1'
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt config.py
git commit -m "chore(mqtt): add paho-mqtt dependency and MQTT config defaults (YAY-159)"
```

---

### Task 7: Deploy e test

**Files:** Nessun file da modificare

- [ ] **Step 1: Installare paho-mqtt sul Pi**

```bash
sshpass -p pimesh ssh pimesh@192.168.1.36 "pip3 install paho-mqtt"
```

- [ ] **Step 2: Deploy sul Pi**

```bash
sshpass -p pimesh rsync -avz --relative \
  meshtasticd_client.py mqtt_bridge.py main.py config.py \
  routers/config_router.py templates/config.html \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 3: Verificare con Playwright**

- Navigare a `http://192.168.1.36:8080/config`
- Cliccare sulla sezione "MQTT" nella sidebar
- Verificare che la pagina carica senza errori
- Verificare che i campi mostrano i valori default
- Verificare lo stato del bridge (dovrebbe mostrare "Non connesso" o "paho-mqtt non installato")
- Testare in portrait (320x480) e landscape (480x320)

- [ ] **Step 4: Test funzionale MQTT**

- Abilitare MQTT nel form
- Impostare server mqtt.meshtastic.org
- Abilitare JSON
- Cliccare "Salva e riavvia bridge"
- Verificare che lo stato passa a "Connesso a mqtt.meshtastic.org"
- Verificare nei log: `sudo journalctl -u pimesh --since "1 min ago" | grep -i mqtt`
