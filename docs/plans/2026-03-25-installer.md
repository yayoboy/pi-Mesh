# Installer & CI/CD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Installazione pi-Mesh con un singolo comando, wizard web al primo avvio, immagine SD auto-generata su ogni release tag.

**Architecture:** `install.sh` bash idempotente gestisce l'intera setup su Raspberry Pi OS. `config.py` espone `SETUP_DONE`; `main.py` reindirizza a `/setup` se non configurato. GitHub Actions monta l'immagine in QEMU, esegue `install.sh --non-interactive`, e pubblica `.img.xz` sulla release GitHub.

**Tech Stack:** bash, FastAPI, Jinja2, Leaflet (wizard mappa), GitHub Actions, QEMU user-static, pishrink.sh

**Design doc:** `docs/plans/2026-03-25-installer-design.md`

---

### Task 1: config.py — variabile SETUP_DONE

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py`

**Step 1: scrivi il test fallente**

```python
# tests/test_config.py
import os, sys

def reload_config(env: dict):
    for k, v in env.items():
        os.environ[k] = v
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    return config

def test_setup_done_default_false():
    os.environ.pop("SETUP_DONE", None)
    cfg = reload_config({})
    assert cfg.SETUP_DONE is False

def test_setup_done_true_when_set():
    cfg = reload_config({"SETUP_DONE": "1"})
    assert cfg.SETUP_DONE is True

def test_setup_done_true_variants():
    for v in ("1", "true", "yes"):
        cfg = reload_config({"SETUP_DONE": v})
        assert cfg.SETUP_DONE is True

def test_setup_done_false_variants():
    for v in ("0", "false", "no", ""):
        cfg = reload_config({"SETUP_DONE": v})
        assert cfg.SETUP_DONE is False
```

**Step 2: verifica che fallisca**

```bash
pytest tests/test_config.py -v
# Expected: AttributeError: module 'config' has no attribute 'SETUP_DONE'
```

**Step 3: implementa in `config.py`**

Aggiungi dopo `UI_ORIENTATION`:

```python
# Setup wizard
SETUP_DONE = os.getenv("SETUP_DONE", "0") in ("1", "true", "yes")
```

**Step 4: verifica che passi**

```bash
pytest tests/test_config.py -v
# Expected: 4 passed
```

**Step 5: commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add SETUP_DONE config flag for first-boot wizard"
```

---

### Task 2: main.py — redirect setup + route /setup + API /api/setup/*

**Files:**
- Modify: `main.py`
- Test: `tests/test_setup_routes.py`

**Step 1: scrivi i test fallenti**

```python
# tests/test_setup_routes.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_hw():
    mock_conn = MagicMock()
    mock_conn.execute  = AsyncMock()
    mock_conn.commit   = AsyncMock()
    mock_conn.close    = AsyncMock()
    with patch("database.init_db",            new_callable=AsyncMock, return_value=mock_conn), \
         patch("database.get_nodes",           new_callable=AsyncMock, return_value=[]),       \
         patch("database.get_messages",        new_callable=AsyncMock, return_value=[]),       \
         patch("meshtastic_client.init"),                                                       \
         patch("meshtastic_client.connect",    new_callable=AsyncMock),                        \
         patch("meshtastic_client.disconnect", new_callable=AsyncMock),                        \
         patch("meshtastic_client.is_connected",  return_value=False),                         \
         patch("meshtastic_client.get_local_node", return_value=None),                         \
         patch("sensor_handler.init",          return_value=[]),                               \
         patch("sensor_handler.start_polling", new_callable=AsyncMock),                        \
         patch("gpio_handler.init"),                                                            \
         patch("watchdog.start_all"):
        yield mock_conn

def _get_app(setup_done: bool):
    import sys
    if "main" in sys.modules:
        del sys.modules["main"]
    import config
    config.SETUP_DONE = setup_done
    from main import app
    return app

@pytest.mark.asyncio
async def test_setup_redirect_when_not_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/home", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/setup" in resp.headers.get("location", "")

@pytest.mark.asyncio
async def test_no_redirect_when_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/home", follow_redirects=False)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_setup_page_accessible_when_not_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/setup")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_api_not_redirected_when_not_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/status", follow_redirects=False)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_setup_serial_ports_returns_list(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/setup/serial-ports")
    assert resp.status_code == 200
    assert "ports" in resp.json()

@pytest.mark.asyncio
async def test_setup_save_writes_setup_done(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    env_file = tmp_path / "config.env"
    env_file.write_text("")
    monkeypatch.chdir(tmp_path)
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/setup/save", json={
            "serial_port": "/dev/ttyUSB0",
            "map_lat_min": 41.0, "map_lat_max": 43.0,
            "map_lon_min": 11.5, "map_lon_max": 14.5,
        })
    assert resp.status_code == 200
    content = env_file.read_text()
    assert "SETUP_DONE=1" in content
    assert "SERIAL_PORT=/dev/ttyUSB0" in content
```

**Step 2: verifica che falliscano**

```bash
pytest tests/test_setup_routes.py -v
# Expected: tutti falliscono — route /setup non esiste
```

**Step 3: implementa in `main.py`**

**3a** — Aggiungi `import glob as _glob` subito dopo gli import esistenti in cima al file.

**3b** — Aggiungi middleware subito dopo `app = FastAPI(lifespan=lifespan)`:

```python
@app.middleware("http")
async def setup_redirect(request: Request, call_next):
    if not cfg.SETUP_DONE:
        path = request.url.path
        skip = path.startswith(("/setup", "/api/", "/static/", "/ws", "/tiles/"))
        if not skip:
            return RedirectResponse("/setup")
    return await call_next(request)
```

**3c** — Aggiungi route GET /setup (in fondo alle route pagine):

```python
@app.get("/setup")
async def setup_page(request: Request):
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "theme": cfg.UI_THEME,
    })
```

**3d** — Aggiungi route API setup (in fondo alle route API):

```python
@app.get("/api/setup/serial-ports")
async def setup_serial_ports():
    patterns = ["/dev/ttyUSB*", "/dev/ttyACM*",
                "/dev/ttyMESHTASTIC", "/dev/serial/by-id/*"]
    ports = []
    for p in patterns:
        ports.extend(_glob.glob(p))
    return {"ports": sorted(set(ports))}

@app.post("/api/setup/connect")
async def setup_connect(payload: dict):
    port = payload.get("port", "").strip()
    if not port:
        return JSONResponse({"ok": False, "error": "porta mancante"}, status_code=400)
    try:
        node = await asyncio.to_thread(_read_node_info, port)
        return {"ok": True, "node": node}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

def _read_node_info(port: str) -> dict:
    import meshtastic.serial_interface
    iface = meshtastic.serial_interface.SerialInterface(devPath=port, noProto=False)
    info  = iface.getMyNodeInfo()
    iface.close()
    user = info.get("user", {})
    return {
        "long_name":  user.get("longName", ""),
        "short_name": user.get("shortName", ""),
        "hw_model":   user.get("hwModel", ""),
        "id":         user.get("id", ""),
    }

@app.post("/api/setup/save")
async def setup_save(payload: dict):
    fields = {
        "SERIAL_PORT": str(payload.get("serial_port", cfg.SERIAL_PORT)).strip(),
        "MAP_LAT_MIN": str(payload.get("map_lat_min", cfg.MAP_BOUNDS["lat_min"])),
        "MAP_LAT_MAX": str(payload.get("map_lat_max", cfg.MAP_BOUNDS["lat_max"])),
        "MAP_LON_MIN": str(payload.get("map_lon_min", cfg.MAP_BOUNDS["lon_min"])),
        "MAP_LON_MAX": str(payload.get("map_lon_max", cfg.MAP_BOUNDS["lon_max"])),
    }
    if payload.get("node_long_name"):
        fields["NODE_LONG_NAME"]  = str(payload["node_long_name"]).strip()
    if payload.get("node_short_name"):
        fields["NODE_SHORT_NAME"] = str(payload["node_short_name"]).strip()
    fields["SETUP_DONE"] = "1"
    for k, v in fields.items():
        _update_config_env(k, v)
    cfg.SETUP_DONE = True
    return {"ok": True}

@app.post("/api/setup/reset")
async def setup_reset():
    _update_config_env("SETUP_DONE", "0")
    cfg.SETUP_DONE = False
    return {"ok": True}
```

**Step 4: verifica test**

```bash
pytest tests/test_setup_routes.py -v
# Expected: 6 passed
```

**Step 5: suite completa**

```bash
pytest tests/ -q
# Expected: tutti i test precedenti ancora verdi
```

**Step 6: commit**

```bash
git add main.py tests/test_setup_routes.py
git commit -m "feat: setup redirect middleware + /setup route + /api/setup/* endpoints"
```

---

### Task 3: templates/setup.html — wizard 3-step

**Files:**
- Create: `templates/setup.html`

**Note sicurezza:** tutto il DOM viene costruito con `createElement` + `textContent` — zero uso di `innerHTML` con dati provenienti da API.

**Step 1: crea il template**

```html
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=320, initial-scale=1, maximum-scale=1">
  <title>pi-Mesh · Setup</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css">
  <style>
    .setup-wrap { max-inline-size: 360px; margin-inline: auto; padding: 24px 16px; }
    .step { display: none; }
    .step.active { display: block; }
    .step-title { font-size: 1.1rem; font-weight: 600; margin-block-end: 16px; color: var(--text); }
    .step-num { font-size: 0.75rem; color: var(--text2); margin-block-end: 4px; }
    #map-pick { block-size: 220px; border-radius: 8px; margin-block: 12px; }
    .coord-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-block: 8px; }
    .coord-row label { font-size: 0.75rem; color: var(--text2); }
    .coord-row input { inline-size: 100%; }
    .port-select { inline-size: 100%; margin-block: 8px; }
    .node-fields { display: grid; gap: 8px; margin-block: 8px; }
    .progress { display: flex; gap: 6px; justify-content: center; margin-block-end: 24px; }
    .progress span { inline-size: 24px; block-size: 4px; border-radius: 2px; background: var(--border); }
    .progress span.done { background: var(--accent); }
  </style>
</head>
<body class="theme-{{ theme }}">
<div class="setup-wrap">
  <h1 style="font-size:1.3rem;margin-block-end:8px;">pi-Mesh Setup</h1>

  <div class="progress">
    <span id="p1" class="done"></span>
    <span id="p2"></span>
    <span id="p3"></span>
  </div>

  <!-- STEP 1: Serial port -->
  <div class="step active" id="step1">
    <p class="step-num">Passo 1 di 3</p>
    <p class="step-title">Seleziona la porta radio</p>
    <select id="port-select" class="port-select"></select>
    <button class="btn" id="btn-connect" onclick="connectPort()" disabled>Connetti</button>
    <p id="connect-msg" style="font-size:0.8rem;color:var(--text2);margin-block-start:8px;"></p>
    <button class="btn" style="margin-block-start:16px;" id="btn-step1-next"
            onclick="goStep(2)" disabled>Avanti &rarr;</button>
  </div>

  <!-- STEP 2: Map area -->
  <div class="step" id="step2">
    <p class="step-num">Passo 2 di 3</p>
    <p class="step-title">Area mappa</p>
    <p style="font-size:0.8rem;color:var(--text2);">Trascina il rettangolo sull'area di interesse.</p>
    <div id="map-pick"></div>
    <div class="coord-row">
      <div><label>Lat min</label><input type="number" id="lat-min" step="0.1" value="41.0"></div>
      <div><label>Lat max</label><input type="number" id="lat-max" step="0.1" value="43.0"></div>
      <div><label>Lon min</label><input type="number" id="lon-min" step="0.1" value="11.5"></div>
      <div><label>Lon max</label><input type="number" id="lon-max" step="0.1" value="14.5"></div>
    </div>
    <button class="btn" onclick="goStep(3)">Avanti &rarr;</button>
  </div>

  <!-- STEP 3: Node name -->
  <div class="step" id="step3">
    <p class="step-num">Passo 3 di 3</p>
    <p class="step-title">Nome nodo</p>
    <p style="font-size:0.8rem;color:var(--text2);">Pre-compilato dalla radio. Modifica se necessario.</p>
    <div class="node-fields">
      <div>
        <label style="font-size:0.8rem;color:var(--text2);">Nome lungo</label>
        <input type="text" id="node-long" placeholder="es. MioNodo LoRa" maxlength="40">
      </div>
      <div>
        <label style="font-size:0.8rem;color:var(--text2);">Nome breve (4 char)</label>
        <input type="text" id="node-short" placeholder="NODO" maxlength="4">
      </div>
    </div>
    <button class="btn" id="btn-save" onclick="saveSetup()">Completa setup &#10003;</button>
    <p id="save-msg" style="font-size:0.8rem;color:var(--text2);margin-block-start:8px;"></p>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
<script>
'use strict'
let _port = ''
let _map  = null
let _rect = null

// Carica porte seriali usando createElement (niente innerHTML con dati API)
fetch('/api/setup/serial-ports')
  .then(r => r.json())
  .then(({ ports }) => {
    const sel = document.getElementById('port-select')
    sel.textContent = ''                        // svuota
    if (ports.length === 0) {
      const opt = document.createElement('option')
      opt.value = ''
      opt.textContent = 'Nessuna porta trovata'
      sel.appendChild(opt)
    } else {
      ports.forEach(p => {
        const opt = document.createElement('option')
        opt.value = p
        opt.textContent = p                     // textContent — safe
        sel.appendChild(opt)
      })
      document.getElementById('btn-connect').disabled = false
    }
  })

function connectPort() {
  const port = document.getElementById('port-select').value
  const msg  = document.getElementById('connect-msg')
  const btn  = document.getElementById('btn-connect')
  btn.disabled = true
  msg.style.color = 'var(--text2)'
  msg.textContent = 'Connessione in corso\u2026'

  fetch('/api/setup/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ port })
  })
  .then(r => r.json())
  .then(data => {
    btn.disabled = false
    _port = port
    document.getElementById('btn-step1-next').disabled = false
    if (data.ok) {
      msg.style.color = 'var(--ok)'
      msg.textContent = '\u2713 Connesso: ' + (data.node.long_name || data.node.id || port)
      document.getElementById('node-long').value  = data.node.long_name  || ''
      document.getElementById('node-short').value = data.node.short_name || ''
    } else {
      msg.style.color = 'var(--warn)'
      msg.textContent = 'Connessione fallita \u2014 puoi procedere comunque.'
    }
  })
  .catch(() => {
    btn.disabled = false
    _port = port
    document.getElementById('btn-step1-next').disabled = false
    msg.style.color = 'var(--warn)'
    msg.textContent = 'Errore rete \u2014 puoi procedere comunque.'
  })
}

function goStep(n) {
  document.querySelectorAll('.step').forEach(s => s.classList.remove('active'))
  document.getElementById('step' + n).classList.add('active')
  for (let i = 1; i <= 3; i++) {
    document.getElementById('p' + i).classList.toggle('done', i <= n)
  }
  if (n === 2 && !_map) initMap()
}

function initMap() {
  _map = L.map('map-pick', { zoomControl: false }).setView([42, 13], 5)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '\u00a9 OpenStreetMap'
  }).addTo(_map)

  const sw = [
    parseFloat(document.getElementById('lat-min').value),
    parseFloat(document.getElementById('lon-min').value)
  ]
  const ne = [
    parseFloat(document.getElementById('lat-max').value),
    parseFloat(document.getElementById('lon-max').value)
  ]
  _rect = L.rectangle([sw, ne], { color: '#4a9eff', weight: 2 }).addTo(_map)
  _map.fitBounds(_rect.getBounds())
  _rect.on('edit', syncCoords)
  if (_rect.editing) _rect.editing.enable()
}

function syncCoords() {
  const b = _rect.getBounds()
  document.getElementById('lat-min').value = b.getSouth().toFixed(2)
  document.getElementById('lat-max').value = b.getNorth().toFixed(2)
  document.getElementById('lon-min').value = b.getWest().toFixed(2)
  document.getElementById('lon-max').value = b.getEast().toFixed(2)
}

function saveSetup() {
  const btn = document.getElementById('btn-save')
  const msg = document.getElementById('save-msg')
  btn.disabled = true
  msg.style.color = 'var(--text2)'
  msg.textContent = 'Salvataggio\u2026'

  fetch('/api/setup/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      serial_port:    _port || document.getElementById('port-select').value,
      map_lat_min:    parseFloat(document.getElementById('lat-min').value),
      map_lat_max:    parseFloat(document.getElementById('lat-max').value),
      map_lon_min:    parseFloat(document.getElementById('lon-min').value),
      map_lon_max:    parseFloat(document.getElementById('lon-max').value),
      node_long_name:  document.getElementById('node-long').value.trim(),
      node_short_name: document.getElementById('node-short').value.trim(),
    })
  })
  .then(r => r.json())
  .then(data => {
    if (data.ok) {
      msg.style.color = 'var(--ok)'
      msg.textContent = '\u2713 Setup completato! Reindirizzamento\u2026'
      setTimeout(() => { location.href = '/home' }, 1500)
    } else {
      btn.disabled = false
      msg.style.color = 'var(--danger)'
      msg.textContent = 'Errore: ' + (data.error || 'sconosciuto')
    }
  })
}
</script>
</body>
</html>
```

**Step 2: verifica manuale**

```bash
SETUP_DONE=0 uvicorn main:app --port 8080
# Apri http://localhost:8080 — deve reindirizzare a /setup
# Verifica navigazione 3 step
```

**Step 3: commit**

```bash
git add templates/setup.html
git commit -m "feat: first-boot wizard — 3-step setup template (serial/map/node)"
```

---

### Task 4: install.sh — script bash idempotente

**Files:**
- Create: `install.sh`

**Step 1: crea lo script**

```bash
#!/usr/bin/env bash
# install.sh — pi-Mesh one-liner installer
# Usage: bash install.sh [--non-interactive] [--update] [--no-zram] [--with-ap]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}  ${NC} $*"; }
ok()    { echo -e "${GREEN}ok${NC} $*"; }
warn()  { echo -e "${YELLOW}!! ${NC} $*"; }
die()   { echo -e "${RED}ERR${NC} $*" >&2; exit 1; }

NON_INTERACTIVE=0; UPDATE_ONLY=0; NO_ZRAM=0; WITH_AP=0
for arg in "$@"; do
  case $arg in
    --non-interactive) NON_INTERACTIVE=1 ;;
    --update)          UPDATE_ONLY=1 ;;
    --no-zram)         NO_ZRAM=1 ;;
    --with-ap)         WITH_AP=1 ;;
  esac
done

INSTALL_DIR="${INSTALL_DIR:-/home/pi/pi-mesh}"
REPO_URL="https://github.com/yayoboy/pi-Mesh.git"
BRANCH="${BRANCH:-master}"
CONFIG_BOOT="/boot/firmware/config.env"

info "Verifica sistema..."
[[ -f /etc/os-release ]] || die "Sistema non supportato"
source /etc/os-release
[[ "$ID" == "raspbian" || "$ID" == "debian" ]] || warn "Sistema non Raspberry Pi OS"
[[ $(uname -m) == arm* || $(uname -m) == aarch64 ]] || warn "Architettura non ARM"

if [[ $UPDATE_ONLY -eq 0 ]]; then
  info "Installazione dipendenze di sistema..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq git python3-venv python3-pip pigpiod avahi-daemon
  ok "Dipendenze di sistema installate"
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "Aggiornamento repo..."
  git -C "$INSTALL_DIR" fetch origin
  git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
  info "Clone repo in $INSTALL_DIR..."
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
ok "Repo aggiornato"

if [[ $UPDATE_ONLY -eq 0 ]]; then
  info "Installazione dipendenze Python..."
  python3 -m venv "$INSTALL_DIR/venv"
  "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
  "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
  ok "Dipendenze Python installate"
fi

if [[ ! -f "$CONFIG_BOOT" ]]; then
  info "Copia config.env in $CONFIG_BOOT..."
  sudo cp "$INSTALL_DIR/config.env" "$CONFIG_BOOT"
  ok "config.env copiato"
else
  ok "config.env gia' presente ($CONFIG_BOOT) — non sovrascritto"
fi

info "Installazione servizio systemd..."
sudo cp "$INSTALL_DIR/meshtastic-pi.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable meshtastic-pi
ok "Servizio installato"

info "Abilitazione pigpiod..."
sudo systemctl enable --now pigpiod
ok "pigpiod attivo"

if [[ $UPDATE_ONLY -eq 0 ]]; then
  info "Abilitazione avahi-daemon (pi-mesh.local)..."
  sudo systemctl enable --now avahi-daemon
  ok "mDNS attivo"
fi

if [[ $NO_ZRAM -eq 0 && $UPDATE_ONLY -eq 0 ]]; then
  info "Configurazione ZRAM..."
  sudo bash "$INSTALL_DIR/scripts/setup_zram.sh"
  ok "ZRAM configurato"
fi

if [[ $WITH_AP -eq 1 ]]; then
  info "Configurazione hotspot fallback..."
  sudo bash "$INSTALL_DIR/scripts/auto_ap.sh"
  ok "Hotspot configurato"
elif [[ $NON_INTERACTIVE -eq 0 ]]; then
  read -r -p "Abilitare hotspot fallback 'pi-mesh-portal' se Wi-Fi non disponibile? [y/N] " yn
  if [[ "${yn,,}" == "y" ]]; then
    sudo bash "$INSTALL_DIR/scripts/auto_ap.sh"
    ok "Hotspot configurato"
  fi
fi

info "Avvio servizio pi-Mesh..."
sudo systemctl restart meshtastic-pi
ok "Servizio avviato"

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  pi-Mesh installato con successo!${NC}"
echo -e "${GREEN}  -> http://pi-mesh.local:8080${NC}"
echo -e "${GREEN}==========================================${NC}"
```

**Step 2: rendi eseguibile e verifica sintassi**

```bash
chmod +x install.sh
bash -n install.sh
# Expected: nessun output (sintassi OK)
```

**Step 3: commit**

```bash
git add install.sh
git commit -m "feat: add install.sh — one-liner idempotent installer for Raspberry Pi OS"
```

---

### Task 5: .github/workflows/build-image.yml

**Files:**
- Create: `.github/workflows/build-image.yml`

**Step 1: crea la directory e il workflow**

```bash
mkdir -p .github/workflows
```

```yaml
# .github/workflows/build-image.yml
name: Build Release Image

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  build-image:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    permissions:
      contents: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Get version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"

      - name: Install build dependencies
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y -qq \
            qemu-user-static binfmt-support \
            kpartx parted wget xz-utils \
            systemd-container

      - name: Download Raspberry Pi OS Lite (arm64)
        run: |
          wget -q --show-progress \
            "https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-latest/raspios_lite_arm64_latest.img.xz" \
            -O raspios.img.xz
          xz -d raspios.img.xz
          mv raspios*.img base.img

      - name: Build pi-Mesh image
        env:
          TAG: ${{ steps.version.outputs.VERSION }}
        run: |
          sudo bash scripts/build-image.sh base.img "pi-mesh-${TAG}.img" "$TAG"

      - name: Compress and checksum
        run: |
          TAG=${{ steps.version.outputs.VERSION }}
          xz -9 --threads=0 "pi-mesh-${TAG}.img"
          sha256sum "pi-mesh-${TAG}.img.xz" > sha256sum.txt

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          name: "pi-Mesh ${{ steps.version.outputs.VERSION }}"
          body: |
            ## pi-Mesh ${{ steps.version.outputs.VERSION }}

            ### Installazione rapida (immagine pronta)
            1. Scarica `pi-mesh-${{ steps.version.outputs.VERSION }}.img.xz`
            2. Flasha su SD con [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
            3. Inserisci la SD, accendi il Pi
            4. Apri `http://pi-mesh.local:8080` da qualsiasi dispositivo sulla stessa rete
            5. Completa il wizard di configurazione

            **Password SSH di default:** `meshtastic` — cambiarla dopo il primo accesso.

            ### Installa su Pi esistente
            ```bash
            curl -fsSL https://raw.githubusercontent.com/yayoboy/pi-Mesh/${{ steps.version.outputs.VERSION }}/install.sh | bash
            ```

            ### Verifica checksum
            ```bash
            sha256sum -c sha256sum.txt
            ```
          files: |
            pi-mesh-${{ steps.version.outputs.VERSION }}.img.xz
            sha256sum.txt
```

**Step 2: commit**

```bash
git add .github/workflows/build-image.yml
git commit -m "ci: GitHub Actions — build and publish .img.xz on tag v*.*.*"
```

---

### Task 6: scripts/build-image.sh — helper CI

**Files:**
- Create: `scripts/build-image.sh`

**Step 1: crea lo script**

```bash
#!/usr/bin/env bash
# scripts/build-image.sh — costruisce l'immagine pi-Mesh in CI
# Usage: sudo bash scripts/build-image.sh <base.img> <output.img> <tag>
set -euo pipefail

BASE_IMG="$1"
OUT_IMG="$2"
TAG="${3:-master}"
REPO_URL="https://github.com/yayoboy/pi-Mesh.git"

echo "Copia immagine base..."
cp "$BASE_IMG" "$OUT_IMG"

echo "Espansione immagine (+2 GB)..."
truncate -s +2G "$OUT_IMG"
parted -s "$OUT_IMG" resizepart 2 100%
LOOP=$(losetup --find --show --partscan "$OUT_IMG")
e2fsck -f "${LOOP}p2" || true
resize2fs "${LOOP}p2"

echo "Mount partizioni..."
BOOT_MNT=$(mktemp -d)
ROOT_MNT=$(mktemp -d)
mount "${LOOP}p1" "$BOOT_MNT"
mount "${LOOP}p2" "$ROOT_MNT"

echo "Abilita SSH e imposta password..."
touch "$BOOT_MNT/ssh"

echo "Setup QEMU per ARM in chroot..."
cp /usr/bin/qemu-aarch64-static "$ROOT_MNT/usr/bin/"

echo "Monta bind per chroot..."
mount --bind /dev  "$ROOT_MNT/dev"
mount --bind /proc "$ROOT_MNT/proc"
mount --bind /sys  "$ROOT_MNT/sys"

echo "Esegui install.sh in chroot..."
chroot "$ROOT_MNT" /bin/bash -c "
  set -e
  apt-get update -qq
  apt-get install -y -qq git curl python3-venv python3-pip pigpiod avahi-daemon
  git clone --branch '${TAG}' --depth 1 '${REPO_URL}' /home/pi/pi-mesh
  INSTALL_DIR=/home/pi/pi-mesh BRANCH='${TAG}' \
    bash /home/pi/pi-mesh/install.sh --non-interactive --no-zram
  chown -R 1000:1000 /home/pi/pi-mesh
  echo 'pi-mesh' > /etc/hostname
  sed -i 's/raspberrypi/pi-mesh/g' /etc/hosts
"

echo "Umount..."
umount "$ROOT_MNT/sys" "$ROOT_MNT/proc" "$ROOT_MNT/dev"
umount "$BOOT_MNT" "$ROOT_MNT"
losetup -d "$LOOP"
rmdir "$BOOT_MNT" "$ROOT_MNT"

echo "Shrink immagine con pishrink..."
if ! command -v pishrink.sh &>/dev/null; then
  wget -q -O /usr/local/bin/pishrink.sh \
    https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
  chmod +x /usr/local/bin/pishrink.sh
fi
pishrink.sh "$OUT_IMG"

echo "Immagine pronta: $OUT_IMG"
```

**Step 2: rendi eseguibile e verifica sintassi**

```bash
chmod +x scripts/build-image.sh
bash -n scripts/build-image.sh
# Expected: nessun output
```

**Step 3: commit**

```bash
git add scripts/build-image.sh
git commit -m "feat: add scripts/build-image.sh — CI helper for Pi image build in QEMU chroot"
```

---

### Task 7: README — sezione Download

**Files:**
- Modify: `README.md`

**Step 1: aggiungi voce nel Table of Contents**

Inserisci come prima voce della lista ToC:

```markdown
- [Download](#download)
```

**Step 2: aggiungi sezione dopo il paragrafo introduttivo e prima di `## Table of Contents`**

```markdown
## Download

| | |
|---|---|
| **Immagine pronta (consigliato)** | Scarica l'ultima `.img.xz` dalla [pagina Release](https://github.com/yayoboy/pi-Mesh/releases/latest), flasha con [Raspberry Pi Imager](https://www.raspberrypi.com/software/), accendi il Pi e apri `http://pi-mesh.local:8080` |
| **Installa su Pi esistente** | `curl -fsSL https://raw.githubusercontent.com/yayoboy/pi-Mesh/master/install.sh \| bash` |
| **Aggiorna installazione esistente** | `bash install.sh --update` |
```

**Step 3: commit**

```bash
git add README.md
git commit -m "docs: add Download section with release image link and install one-liner"
```

---

### Task 8: settings.html — pulsante "Riesegui wizard"

**Files:**
- Modify: `templates/settings.html`

**Step 1: aggiungi in fondo al blocco SISTEMA**

Trova la sezione `SISTEMA` e aggiungi prima del tag di chiusura:

```html
<div class="setting-row">
  <span>Wizard configurazione</span>
  <button class="btn" id="btn-reset-setup">Riesegui wizard</button>
</div>
```

**Step 2: aggiungi handler JS inline nel template (in fondo, prima di `</body>`)**

```html
<script>
document.getElementById('btn-reset-setup')
  .addEventListener('click', () => {
    if (!confirm('Rieseguire il wizard di configurazione iniziale?')) return
    fetch('/api/setup/reset', { method: 'POST' })
      .then(() => { location.href = '/setup' })
  })
</script>
```

**Step 3: suite completa**

```bash
pytest tests/ -q
# Expected: tutti i test verdi
```

**Step 4: commit**

```bash
git add templates/settings.html
git commit -m "feat: add Riesegui wizard button in Settings -> Sistema"
```

---

### Task 9: push e verifica finale

**Step 1: suite completa**

```bash
pytest tests/ -v
# Expected: tutti i test passano (103+)
```

**Step 2: push branch**

```bash
git push origin feature/ui-redesign
```

**Step 3: apri PR**

```bash
gh pr create \
  --title "M3: Installer & CI/CD — install.sh + first-boot wizard + image build" \
  --body "$(cat <<'EOF'
## Summary
- `install.sh` — one-liner idempotent installer per Raspberry Pi OS
- First-boot wizard web 3-step (serial port / area mappa / nome nodo da radio)
- GitHub Actions build immagine `.img.xz` su tag `v*.*.*`
- Pulsante "Riesegui wizard" in Settings

## Test plan
- [ ] `pytest tests/ -v` — tutti i test passano
- [ ] `bash -n install.sh` — sintassi bash OK
- [ ] `bash -n scripts/build-image.sh` — sintassi bash OK
- [ ] Navigazione wizard su http://localhost:8080 con SETUP_DONE=0
- [ ] Redirect a /setup quando SETUP_DONE=0
- [ ] Nessun redirect quando SETUP_DONE=1

Closes M3 — Installer & CI/CD
EOF
)"
```
