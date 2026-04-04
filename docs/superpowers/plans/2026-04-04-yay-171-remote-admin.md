# Remote Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inviare comandi di amministrazione a nodi remoti via mesh (ADMIN_APP): request position/telemetry, reboot, set config, factory reset.

**Architecture:** Approccio B. Nuovo `admin_router.py` con 5 endpoint POST. Funzione `send_admin` in `meshtasticd_client.py` usa `_interface.sendAdmin()` via `_command_queue`. Pulsante "Admin" aggiunto alla griglia azioni del nodo in `nodes.html`; apre modal Alpine.js inline con sezioni Diagnostica/Controllo/Distruttivo. Factory reset protetto da doppia conferma. Warning se admin key non configurata.

**Tech Stack:** FastAPI, meshtastic-python, Alpine.js, Jinja2

---

### Task 1: send_admin in meshtasticd_client.py

**Files:**
- Modify: `meshtasticd_client.py`

- [ ] **Step 1: Aggiungi funzione `send_admin`**

Aggiungi dopo `send_waypoint`:

```python
async def send_admin(dest_node_id: str, operation: str, payload: dict | None = None) -> None:
    """Send an admin command to a remote node via mesh.

    Supported operations:
      'request_position'  — ask node to send its GPS position
      'request_telemetry' — ask node to send device telemetry
      'reboot'            — reboot the remote node
      'factory_reset'     — factory reset the remote node (DESTRUCTIVE)
    """
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _dest = dest_node_id
    _op = operation

    def _do():
        from meshtastic.protobuf import admin_pb2, portnums_pb2
        try:
            dest_num = int(_dest.lstrip('!'), 16)
        except ValueError:
            raise RuntimeError(f'Invalid node id: {_dest}')

        if _op == 'request_position':
            _interface.localNode.sendPosition(destinationId=_dest, wantResponse=True)
        elif _op == 'request_telemetry':
            # Send empty admin message to trigger telemetry response
            admin_msg = admin_pb2.AdminMessage()
            admin_msg.get_device_metadata_request = True
            _interface.sendData(
                admin_msg.SerializeToString(),
                destinationId=_dest,
                portNum=portnums_pb2.PortNum.ADMIN_APP,
                wantAck=True,
            )
        elif _op == 'reboot':
            admin_msg = admin_pb2.AdminMessage()
            admin_msg.reboot_seconds = 2
            _interface.sendData(
                admin_msg.SerializeToString(),
                destinationId=_dest,
                portNum=portnums_pb2.PortNum.ADMIN_APP,
                wantAck=True,
            )
        elif _op == 'factory_reset':
            admin_msg = admin_pb2.AdminMessage()
            admin_msg.factory_reset = 1
            _interface.sendData(
                admin_msg.SerializeToString(),
                destinationId=_dest,
                portNum=portnums_pb2.PortNum.ADMIN_APP,
                wantAck=True,
            )
        else:
            raise RuntimeError(f'Unknown admin operation: {_op}')

    await _command_queue.put(_do)
```

- [ ] **Step 2: Commit**

```bash
git add meshtasticd_client.py
git commit -m "feat(admin): add send_admin function to meshtasticd_client"
```

---

### Task 2: Router admin_router.py

**Files:**
- Create: `routers/admin_router.py`
- Modify: `main.py`

- [ ] **Step 1: Crea `routers/admin_router.py`**

```python
# routers/admin_router.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import meshtasticd_client

router = APIRouter()


def _check_connected():
    if not meshtasticd_client.is_connected():
        raise HTTPException(503, detail='board not connected')


@router.post('/api/admin/{node_id}/request-position')
async def admin_request_position(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'request_position')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)


@router.post('/api/admin/{node_id}/request-telemetry')
async def admin_request_telemetry(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'request_telemetry')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)


@router.post('/api/admin/{node_id}/reboot')
async def admin_reboot(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'reboot')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)


@router.post('/api/admin/{node_id}/factory-reset')
async def admin_factory_reset(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'factory_reset')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)
```

- [ ] **Step 2: Registra in `main.py`**

Aggiorna l'import dei router:
```python
from routers import nodes, map_router, log_router, commands, ws_router, messages_router, config_router, metrics_router, canned_router, module_config_router, waypoints_router, neighbor_router, admin_router
```

Aggiungi dopo gli altri `app.include_router(...)`:
```python
app.include_router(admin_router.router)
```

- [ ] **Step 3: Commit**

```bash
git add routers/admin_router.py main.py
git commit -m "feat(admin): add admin_router with 4 remote operation endpoints"
```

---

### Task 3: UI — pulsante Admin e modal in nodes.html

**Files:**
- Modify: `templates/nodes.html`

I nodi hanno una `action-grid` sia nella vista portrait (riga espansa) sia in quella landscape (pannello dettaglio). Aggiungere il pulsante Admin in entrambe le viste e un modal condiviso.

- [ ] **Step 1: Aggiungi stato Alpine al componente `x-data` principale**

Nel componente `x-data` di `nodes.html`, aggiungi queste proprietà nel blocco `data`:

```javascript
adminModal: false,
adminNodeId: null,
adminNodeName: '',
adminStatus: '',
adminLoading: false,
confirmReset: false,
confirmResetText: '',
```

Aggiungi questi metodi:

```javascript
openAdmin(node) {
  this.adminNodeId = node.id
  this.adminNodeName = node.long_name || node.short_name || node.id
  this.adminModal = true
  this.adminStatus = ''
  this.confirmReset = false
  this.confirmResetText = ''
},

closeAdmin() {
  this.adminModal = false
  this.adminNodeId = null
  this.adminStatus = ''
  this.confirmReset = false
},

async doAdmin(operation) {
  if (!this.adminNodeId) return
  this.adminLoading = true
  this.adminStatus = '...'
  try {
    const r = await fetch(`/api/admin/${encodeURIComponent(this.adminNodeId)}/${operation}`, {method: 'POST'})
    const data = await r.json()
    this.adminStatus = r.ok ? '✓ Comando inviato' : ('✗ ' + (data.error || data.detail || 'Errore'))
  } catch (e) {
    this.adminStatus = '✗ Errore di rete'
  }
  this.adminLoading = false
},

async doFactoryReset() {
  if (this.confirmResetText !== 'RESET') {
    this.adminStatus = 'Scrivi RESET per confermare'
    return
  }
  await this.doAdmin('factory-reset')
  this.confirmReset = false
  this.confirmResetText = ''
},
```

- [ ] **Step 2: Aggiungi pulsante Admin nella vista portrait (action-grid)**

Trova nella sezione portrait (riga ~177) la `action-grid` con i bottoni Traceroute, Posiz., DM, Mappa, Dimentica. Aggiungi prima del pulsante "Dimentica":

```html
<button class="action-btn" @click.stop="openAdmin(node)"
        style="color:#e53935;border-color:#7f1d1d;">
  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
    <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
  </svg>
  Admin
</button>
```

- [ ] **Step 3: Aggiungi pulsante Admin nella vista landscape**

Trova la sezione landscape (riga ~303) con la sua `action-grid` e aggiungi lo stesso pulsante (con `@click="openAdmin(selectedNode)"` invece di `@click.stop="openAdmin(node)"`):

```html
<button class="action-btn" @click="openAdmin(selectedNode)"
        style="flex-basis:calc(50% - 3px);color:#e53935;border-color:#7f1d1d;">
  <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
    <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
  </svg>
  Admin
</button>
```

- [ ] **Step 4: Aggiungi modal Admin**

Prima del tag `</div>` finale che chiude il componente `x-data` principale, aggiungi:

```html
<!-- ADMIN MODAL -->
<div x-show="adminModal" @click.self="closeAdmin()"
     style="position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:300;
            display:flex;align-items:center;justify-content:center;padding:16px;">
  <div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;
              width:100%;max-width:320px;padding:14px;">

    <!-- Header -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
      <div>
        <div style="font-size:12px;font-weight:700;color:var(--text);">Admin remoto</div>
        <div style="font-size:10px;color:var(--muted);" x-text="adminNodeName"></div>
      </div>
      <button @click="closeAdmin()"
              style="background:none;border:none;color:var(--muted);font-size:18px;cursor:pointer;line-height:1;">✕</button>
    </div>

    <!-- Diagnostica -->
    <div style="font-size:9px;font-weight:700;text-transform:uppercase;color:var(--muted);margin-bottom:6px;">
      Diagnostica
    </div>
    <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;">
      <button @click="doAdmin('request-position')" :disabled="adminLoading"
              style="font-size:10px;padding:6px 10px;background:none;border:1px solid var(--border);
                     border-radius:4px;color:var(--text);cursor:pointer;">
        📍 Posizione
      </button>
      <button @click="doAdmin('request-telemetry')" :disabled="adminLoading"
              style="font-size:10px;padding:6px 10px;background:none;border:1px solid var(--border);
                     border-radius:4px;color:var(--text);cursor:pointer;">
        📊 Telemetria
      </button>
    </div>

    <!-- Controllo -->
    <div style="font-size:9px;font-weight:700;text-transform:uppercase;color:var(--muted);margin-bottom:6px;">
      Controllo
    </div>
    <div style="display:flex;gap:6px;margin-bottom:12px;">
      <button @click="doAdmin('reboot')" :disabled="adminLoading"
              style="font-size:10px;padding:6px 10px;background:none;border:1px solid #ff9800;
                     border-radius:4px;color:#ff9800;cursor:pointer;">
        🔄 Reboot
      </button>
    </div>

    <!-- Distruttivo -->
    <div style="font-size:9px;font-weight:700;text-transform:uppercase;color:var(--muted);margin-bottom:6px;">
      Distruttivo
    </div>
    <template x-if="!confirmReset">
      <button @click="confirmReset=true"
              style="font-size:10px;padding:6px 10px;background:none;border:1px solid #e53935;
                     border-radius:4px;color:#e53935;cursor:pointer;">
        💥 Factory Reset
      </button>
    </template>
    <template x-if="confirmReset">
      <div style="background:#1a0000;border:1px solid #e53935;border-radius:4px;padding:10px;">
        <div style="font-size:10px;color:#e53935;margin-bottom:6px;">
          Operazione irreversibile. Scrivi <b>RESET</b> per confermare:
        </div>
        <input x-model="confirmResetText" placeholder="RESET"
               style="width:100%;background:var(--panel);color:var(--text);border:1px solid #e53935;
                      border-radius:4px;padding:6px 8px;font-size:12px;margin-bottom:6px;">
        <div style="display:flex;gap:6px;">
          <button @click="doFactoryReset()" :disabled="adminLoading"
                  style="font-size:10px;padding:5px 10px;background:#e53935;color:#fff;
                         border:none;border-radius:4px;cursor:pointer;">
            Conferma
          </button>
          <button @click="confirmReset=false;confirmResetText=''"
                  style="font-size:10px;padding:5px 10px;background:none;border:1px solid var(--border);
                         border-radius:4px;color:var(--muted);cursor:pointer;">
            Annulla
          </button>
        </div>
      </div>
    </template>

    <!-- Status feedback -->
    <div x-show="adminStatus" x-text="adminStatus"
         style="margin-top:10px;font-size:10px;padding:6px 8px;background:var(--panel);
                border-radius:4px;font-family:monospace;"
         :style="adminStatus.startsWith('✓') ? 'color:#4caf50' : 'color:#ef4444'">
    </div>

  </div>
</div>
```

- [ ] **Step 5: Commit**

```bash
git add templates/nodes.html
git commit -m "feat(admin): add Admin button and modal to nodes page"
```

---

### Task 4: Deploy e verifica su Pi

- [ ] **Step 1: Deploy**

```bash
sshpass -p pimesh rsync -avz --relative \
  meshtasticd_client.py routers/admin_router.py \
  main.py templates/nodes.html \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Verifica UI**

Apri `http://192.168.1.36:8080/nodes` → seleziona un nodo remoto → verifica che il pulsante "Admin" (ingranaggio) appaia nella griglia azioni → tap → modal si apre con nome nodo e sezioni Diagnostica/Controllo/Distruttivo.

- [ ] **Step 3: Verifica API**

```bash
# Request position (richiede board connessa)
curl -X POST http://192.168.1.36:8080/api/admin/!aabbccdd/request-position
# Expected: {"ok": true} oppure {"detail": "board not connected"}
```

- [ ] **Step 4: Verifica Factory Reset double-confirm**

Nel modal Admin → "💥 Factory Reset" → appare input testo → scrivi "SBAGLIATO" → premi Conferma → status mostra errore di validazione → scrivi "RESET" → conferma → status "✓ Comando inviato".

- [ ] **Step 5: Commit finale**

```bash
git add -A
git commit -m "feat: M10 complete — remote admin (YAY-171)"
```
