# YAY-115 WiFi Network Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere gestione reti WiFi salvate (SSID/password persistenti, richiamabili) e toggle DHCP/IP statico nella sezione WiFi di /config.

**Architecture:** Backend usa `nmcli` connection profiles (già presenti su Pi con NetworkManager). Ogni `nmcli dev wifi connect` crea automaticamente un profilo salvato. Aggiungiamo endpoint per listare profili salvati, eliminare, ottenere stato corrente, e configurare IP statico/DHCP. Frontend estende la sezione WiFi esistente in config.html.

**Tech Stack:** Python 3.11, FastAPI, nmcli (NetworkManager), Alpine.js

---

## File Structure

| File | Responsabilità |
|------|---------------|
| `routers/config_router.py` | Nuovi endpoint WiFi: saved networks, delete, status, IP config |
| `templates/config.html` | UI WiFi estesa: stato, reti salvate, IP config |

---

### Task 1: Backend — endpoint stato WiFi e reti salvate

**Files:**
- Modify: `routers/config_router.py`

- [ ] **Step 1: Aggiungere endpoint GET /api/config/wifi/status**

In `config_router.py`, dopo l'endpoint `wifi_connect` (circa riga 291), aggiungere:

```python
@router.get('/api/config/wifi/status')
async def wifi_status():
    """Return current WiFi connection status: SSID, IP, signal, method."""
    try:
        # Active connection info
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,DEVICE,TYPE', 'con', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )
        active_ssid = ''
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 3 and parts[2] == '802-11-wireless':
                active_ssid = parts[0]
                break

        # IP and method
        ip_addr = ''
        method = 'auto'
        if active_ssid:
            r2 = subprocess.run(
                ['nmcli', '-t', '-f', 'IP4.ADDRESS,ipv4.method', 'con', 'show', active_ssid],
                capture_output=True, text=True, timeout=10
            )
            for line in r2.stdout.splitlines():
                if line.startswith('IP4.ADDRESS'):
                    ip_addr = line.split(':', 1)[1].strip()
                elif line.startswith('ipv4.method'):
                    method = line.split(':', 1)[1].strip()

        return {
            'connected': bool(active_ssid),
            'ssid': active_ssid,
            'ip': ip_addr,
            'method': method,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {'connected': False, 'ssid': '', 'ip': '', 'method': 'auto'}
```

- [ ] **Step 2: Aggiungere endpoint GET /api/config/wifi/saved**

Dopo `wifi_status`, aggiungere:

```python
@router.get('/api/config/wifi/saved')
async def wifi_saved():
    """Return list of saved WiFi connection profiles."""
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'],
            capture_output=True, text=True, timeout=10
        )
        saved = []
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and parts[1] == '802-11-wireless':
                saved.append(parts[0])
        return saved
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
```

- [ ] **Step 3: Aggiungere endpoint DELETE /api/config/wifi/saved/{name}**

```python
@router.delete('/api/config/wifi/saved/{name}')
async def wifi_delete_saved(name: str):
    """Delete a saved WiFi connection profile."""
    try:
        result = subprocess.run(
            ['nmcli', 'con', 'delete', name],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return {'ok': True}
        return JSONResponse({'error': result.stderr.strip()}, status_code=500)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return JSONResponse({'error': str(e)}, status_code=500)
```

- [ ] **Step 4: Aggiungere endpoint POST /api/config/wifi/ip**

```python
class WifiIpRequest(BaseModel):
    method: str  # 'auto' or 'manual'
    address: str = ''  # e.g. '192.168.1.100/24'
    gateway: str = ''  # e.g. '192.168.1.1'
    dns: str = ''      # e.g. '8.8.8.8'


@router.post('/api/config/wifi/ip')
async def wifi_set_ip(body: WifiIpRequest):
    """Set IP configuration (DHCP or static) on active WiFi connection."""
    try:
        # Find active wifi connection name
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )
        con_name = ''
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and parts[1] == '802-11-wireless':
                con_name = parts[0]
                break
        if not con_name:
            return JSONResponse({'error': 'No active WiFi connection'}, status_code=400)

        if body.method == 'auto':
            subprocess.run(
                ['nmcli', 'con', 'mod', con_name, 'ipv4.method', 'auto',
                 'ipv4.addresses', '', 'ipv4.gateway', '', 'ipv4.dns', ''],
                capture_output=True, text=True, timeout=10
            )
        else:
            if not body.address or not body.gateway:
                return JSONResponse({'error': 'Address and gateway required for static IP'}, status_code=400)
            cmd = ['nmcli', 'con', 'mod', con_name,
                   'ipv4.method', 'manual',
                   'ipv4.addresses', body.address,
                   'ipv4.gateway', body.gateway]
            if body.dns:
                cmd += ['ipv4.dns', body.dns]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        # Reapply connection to activate changes
        subprocess.run(
            ['nmcli', 'con', 'up', con_name],
            capture_output=True, text=True, timeout=15
        )
        return {'ok': True}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return JSONResponse({'error': str(e)}, status_code=500)
```

- [ ] **Step 5: Commit**

```bash
git add routers/config_router.py
git commit -m "feat(wifi): add status, saved networks, delete, IP config endpoints (YAY-115)"
```

---

### Task 2: Frontend — UI stato WiFi, reti salvate, IP config

**Files:**
- Modify: `templates/config.html`

- [ ] **Step 1: Estendere Alpine.js state per WiFi**

In `templates/config.html`, trovare il blocco WiFi state (circa riga 970-974):

```javascript
    // WiFi
    wifiNetworks: [],
    wifiScanning: false,
    wifiConnecting: false,
    wifi: { ssid: '', password: '' },
```

Sostituire con:

```javascript
    // WiFi
    wifiNetworks: [],
    wifiScanning: false,
    wifiConnecting: false,
    wifi: { ssid: '', password: '' },
    wifiStatus: { connected: false, ssid: '', ip: '', method: 'auto' },
    wifiSaved: [],
    wifiIp: { method: 'auto', address: '', gateway: '', dns: '' },
    wifiIpSaving: false,
```

- [ ] **Step 2: Aggiungere metodi loadWifiStatus, loadWifiSaved, deleteWifiSaved, saveWifiIp**

Dopo il metodo `connectWifi()` (circa riga 999-1001), prima della chiusura `}` di `configPage()`, aggiungere:

```javascript
    async loadWifiStatus() {
      try {
        const r = await fetch('/api/config/wifi/status')
        if (r.ok) {
          this.wifiStatus = await r.json()
          this.wifiIp.method = this.wifiStatus.method === 'manual' ? 'manual' : 'auto'
        }
      } catch(e) {}
    },

    async loadWifiSaved() {
      try {
        const r = await fetch('/api/config/wifi/saved')
        if (r.ok) this.wifiSaved = await r.json()
      } catch(e) {}
    },

    async deleteWifiSaved(name) {
      try {
        const r = await fetch('/api/config/wifi/saved/' + encodeURIComponent(name), { method: 'DELETE' })
        if (r.ok) {
          this.wifiSaved = this.wifiSaved.filter(n => n !== name)
          this.status.wifi = '✓ Rete rimossa'
        }
      } catch(e) {}
    },

    async saveWifiIp() {
      this.wifiIpSaving = true
      try {
        const r = await fetch('/api/config/wifi/ip', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.wifiIp)
        })
        const data = await r.json()
        this.status.wifi = r.ok ? '✓ IP aggiornato' : '✗ ' + (data.error || 'Errore')
        if (r.ok) await this.loadWifiStatus()
      } finally {
        this.wifiIpSaving = false
      }
    },
```

- [ ] **Step 3: Aggiornare connectWifi per ricaricare stato dopo connessione**

Trovare il metodo `connectWifi()`:

```javascript
    async connectWifi() {
      this.wifiConnecting = true
      this.status.wifi = ''
      try {
        const r = await fetch('/api/config/wifi/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.wifi)
        })
        const data = await r.json()
        this.status.wifi = r.ok ? '✓ Connesso a ' + this.wifi.ssid : '✗ ' + (data.error || 'Errore')
      } finally {
        this.wifiConnecting = false
      }
    },
```

Sostituire con:

```javascript
    async connectWifi() {
      this.wifiConnecting = true
      this.status.wifi = ''
      try {
        const r = await fetch('/api/config/wifi/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.wifi)
        })
        const data = await r.json()
        this.status.wifi = r.ok ? '✓ Connesso a ' + this.wifi.ssid : '✗ ' + (data.error || 'Errore')
        if (r.ok) {
          await this.loadWifiStatus()
          await this.loadWifiSaved()
        }
      } finally {
        this.wifiConnecting = false
      }
    },
```

- [ ] **Step 4: Sostituire template HTML WiFi con versione estesa**

Trovare l'intero blocco `<!-- WIFI -->`:

```html
    <!-- WIFI -->
    <template x-if="section === 'wifi'">
      <div>
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:10px;">WiFi Pi</div>
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <button @click="scanWifi()" style="flex:1;padding:8px;font-size:11px;background:#1a3a5c;color:var(--accent);border:1px solid #2a5a8a;border-radius:4px;cursor:pointer;"
                  x-text="wifiScanning ? 'Scansione...' : '📡 Scan reti'">
          </button>
        </div>
        <template x-if="wifiNetworks.length > 0">
          <div style="background:var(--panel);border:1px solid var(--border);border-radius:6px;max-height:100px;overflow-y:auto;margin-bottom:8px;">
            <template x-for="net in wifiNetworks" :key="net.ssid">
              <div @click="wifi.ssid = net.ssid"
                   style="padding:6px 10px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;border-bottom:1px solid var(--border);"
                   :style="wifi.ssid === net.ssid ? 'background:#1a3a5c;' : ''">
                <span style="font-size:11px;color:var(--text);" x-text="net.ssid"></span>
                <span style="font-size:10px;color:var(--muted);" x-text="net.signal + '% · ' + net.security"></span>
              </div>
            </template>
          </div>
        </template>
        <div style="display:flex;flex-direction:column;gap:6px;">
          <input x-model="wifi.ssid" placeholder="SSID" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
          <input x-model="wifi.password" type="password" placeholder="Password" autocomplete="new-password"
                 style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
          <button @click="connectWifi()" style="padding:10px;font-size:12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:600;"
                  x-text="wifiConnecting ? 'Connessione...' : 'Connetti'">
          </button>
          <div x-show="status.wifi" x-text="status.wifi" style="font-size:10px;"
               :style="status.wifi && status.wifi.startsWith('✓') ? 'color:#4caf50' : 'color:#ef4444'"></div>
        </div>
      </div>
    </template>
```

Sostituire con:

```html
    <!-- WIFI -->
    <template x-if="section === 'wifi'">
      <div x-init="loadWifiStatus(); loadWifiSaved()">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:10px;">WiFi Pi</div>

        <!-- Current status -->
        <div style="padding:8px 10px;background:var(--panel);border:1px solid var(--border);border-radius:6px;margin-bottom:10px;">
          <template x-if="wifiStatus.connected">
            <div>
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
                <div style="width:8px;height:8px;border-radius:50%;background:#4caf50;flex-shrink:0;"></div>
                <span style="font-size:11px;color:var(--text);font-weight:600;" x-text="wifiStatus.ssid"></span>
              </div>
              <div style="font-size:10px;color:var(--muted);" x-text="'IP: ' + wifiStatus.ip + ' (' + (wifiStatus.method === 'manual' ? 'Statico' : 'DHCP') + ')'"></div>
            </div>
          </template>
          <template x-if="!wifiStatus.connected">
            <div style="display:flex;align-items:center;gap:6px;">
              <div style="width:8px;height:8px;border-radius:50%;background:#374151;flex-shrink:0;"></div>
              <span style="font-size:11px;color:var(--muted);">Non connesso</span>
            </div>
          </template>
        </div>

        <!-- Scan + connect -->
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <button @click="scanWifi()" style="flex:1;padding:8px;font-size:11px;background:#1a3a5c;color:var(--accent);border:1px solid #2a5a8a;border-radius:4px;cursor:pointer;"
                  x-text="wifiScanning ? 'Scansione...' : 'Scan reti'">
          </button>
        </div>
        <template x-if="wifiNetworks.length > 0">
          <div style="background:var(--panel);border:1px solid var(--border);border-radius:6px;max-height:100px;overflow-y:auto;margin-bottom:8px;">
            <template x-for="net in wifiNetworks" :key="net.ssid">
              <div @click="wifi.ssid = net.ssid"
                   style="padding:6px 10px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;border-bottom:1px solid var(--border);"
                   :style="wifi.ssid === net.ssid ? 'background:#1a3a5c;' : ''">
                <span style="font-size:11px;color:var(--text);" x-text="net.ssid"></span>
                <span style="font-size:10px;color:var(--muted);" x-text="net.signal + '% · ' + net.security"></span>
              </div>
            </template>
          </div>
        </template>
        <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:14px;">
          <input x-model="wifi.ssid" placeholder="SSID" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
          <input x-model="wifi.password" type="password" placeholder="Password" autocomplete="new-password"
                 style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
          <button @click="connectWifi()" style="padding:10px;font-size:12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:600;"
                  x-text="wifiConnecting ? 'Connessione...' : 'Connetti'">
          </button>
        </div>

        <!-- Saved networks -->
        <template x-if="wifiSaved.length > 0">
          <div>
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:6px;">Reti salvate</div>
            <div style="background:var(--panel);border:1px solid var(--border);border-radius:6px;max-height:90px;overflow-y:auto;margin-bottom:14px;">
              <template x-for="name in wifiSaved" :key="name">
                <div style="padding:6px 10px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);">
                  <span style="font-size:11px;color:var(--text);" x-text="name"></span>
                  <button @click="deleteWifiSaved(name)" style="background:none;border:none;color:#ef4444;font-size:10px;cursor:pointer;padding:2px 6px;">Rimuovi</button>
                </div>
              </template>
            </div>
          </div>
        </template>

        <!-- IP Configuration -->
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:6px;">Configurazione IP</div>
        <div style="display:flex;flex-direction:column;gap:6px;">
          <div style="display:flex;gap:10px;align-items:center;">
            <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--text);cursor:pointer;">
              <input type="radio" value="auto" x-model="wifiIp.method" style="accent-color:var(--accent);">
              DHCP
            </label>
            <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--text);cursor:pointer;">
              <input type="radio" value="manual" x-model="wifiIp.method" style="accent-color:var(--accent);">
              IP Statico
            </label>
          </div>
          <template x-if="wifiIp.method === 'manual'">
            <div style="display:flex;flex-direction:column;gap:6px;">
              <input x-model="wifiIp.address" placeholder="Indirizzo (es. 192.168.1.100/24)"
                     style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
              <input x-model="wifiIp.gateway" placeholder="Gateway (es. 192.168.1.1)"
                     style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
              <input x-model="wifiIp.dns" placeholder="DNS (es. 8.8.8.8)"
                     style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
            </div>
          </template>
          <button @click="saveWifiIp()" :disabled="wifiIpSaving || !wifiStatus.connected"
                  style="padding:10px;font-size:12px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:600;"
                  :style="(!wifiStatus.connected || wifiIpSaving) ? 'opacity:0.5;cursor:not-allowed;' : ''"
                  x-text="wifiIpSaving ? 'Salvataggio...' : 'Applica IP'">
          </button>
        </div>

        <!-- Status message -->
        <div x-show="status.wifi" x-text="status.wifi" style="font-size:10px;margin-top:6px;"
             :style="status.wifi && status.wifi.startsWith('✓') ? 'color:#4caf50' : 'color:#ef4444'"></div>
      </div>
    </template>
```

- [ ] **Step 5: Commit**

```bash
git add templates/config.html
git commit -m "feat(wifi): saved networks list, DHCP/static IP toggle in config UI (YAY-115)"
```

---

### Task 3: Deploy e test

**Files:** Nessun file da modificare

- [ ] **Step 1: Deploy sul Pi**

```bash
sshpass -p pimesh rsync -avz --relative \
  routers/config_router.py templates/config.html \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Verificare con Playwright**

- Navigare a `http://192.168.1.36:8080/config`
- Cliccare su sezione "WiFi"
- Screenshot a 320x480 portrait
- Verificare: status connessione visibile (SSID + IP + DHCP/Statico), lista reti salvate con pulsante Rimuovi, radio DHCP/Statico, campi IP statico compaiono quando si seleziona "IP Statico"
- Verificare che "Scan reti" funziona
- Screenshot a 480x320 landscape

- [ ] **Step 3: Commit finale se necessario**
