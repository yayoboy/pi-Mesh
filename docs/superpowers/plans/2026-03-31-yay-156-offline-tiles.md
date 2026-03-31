# YAY-156 Offline Tile Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `scripts/manage-tiles.sh` cross-platform script to select a region, optionally download tiles, and rsync them to the Pi; add a Config → Mappa section to toggle local vs CDN tile mode.

**Architecture:** Three components: (1) a bash script that handles tile selection/download/transfer; (2) a new `GET/POST /api/config/map` endpoint that reads/writes `MAP_LOCAL_TILES` and `MAP_REGION` in `config.env`; (3) a Mappa section in Config UI. `MAP_LOCAL_TILES` is surfaced as a JS global injected in `base.html` via Jinja2 globals, so map.js can read it without changing all routers.

**Tech Stack:** Python/FastAPI, Jinja2, Alpine.js, pytest-anyio, bash

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `config.py` | Modify | Add `MAP_LOCAL_TILES`, `MAP_REGION`, `REGION_BOUNDS` |
| `routers/map_router.py` | Modify | Use `cfg.REGION_BOUNDS[cfg.MAP_REGION]` for bounds |
| `main.py` | Modify | Set `templates.env.globals['map_local_tiles']` |
| `templates/base.html` | Modify | Inject `window.MAP_LOCAL_TILES` JS global |
| `static/map.js` | Modify | Read `window.MAP_LOCAL_TILES` instead of dataset attribute |
| `routers/config_router.py` | Modify | Add `_write_env()`, `GET/POST /api/config/map` |
| `templates/config.html` | Modify | Add Mappa section (Alpine.js) |
| `config.env` | Modify | Add `MAP_LOCAL_TILES=0`, `MAP_REGION=italia` |
| `scripts/manage-tiles.sh` | Create | Interactive tile selection/download/rsync script |
| `tests/test_api.py` | Modify | Add tests for `/api/config/map` |

---

### Task 1: config.py — region bounds and map config vars

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add MAP vars and REGION_BOUNDS to config.py**

Open `config.py` and add after the existing constants:

```python
MAP_LOCAL_TILES = os.getenv('MAP_LOCAL_TILES', '0') == '1'
MAP_REGION      = os.getenv('MAP_REGION', 'italia')

REGION_BOUNDS: dict[str, dict[str, float]] = {
    'italia':   {'lat_min': 35.0,  'lat_max': 47.5, 'lon_min':   6.5, 'lon_max':  18.5},
    'francia':  {'lat_min': 41.3,  'lat_max': 51.1, 'lon_min':  -5.2, 'lon_max':   9.6},
    'germania': {'lat_min': 47.3,  'lat_max': 55.1, 'lon_min':   5.9, 'lon_max':  15.0},
    'spagna':   {'lat_min': 35.9,  'lat_max': 43.8, 'lon_min':  -9.3, 'lon_max':   4.3},
    'europa':   {'lat_min': 34.0,  'lat_max': 72.0, 'lon_min': -25.0, 'lon_max':  45.0},
    'mondo':    {'lat_min': -85.0, 'lat_max': 85.0, 'lon_min':-180.0, 'lon_max': 180.0},
}
```

- [ ] **Step 2: Verify import works**

```bash
cd /path/to/pi-Mesh
python3 -c "import config; print(config.MAP_REGION, config.REGION_BOUNDS['italia'])"
```

Expected: `italia {'lat_min': 35.0, 'lat_max': 47.5, 'lon_min': 6.5, 'lon_max': 18.5}`

- [ ] **Step 3: Add MAP_LOCAL_TILES and MAP_REGION to config.env**

Open `config.env`, find the `# Mappa` section and append:

```
MAP_LOCAL_TILES=0
MAP_REGION=italia
```

- [ ] **Step 4: Commit**

```bash
git add config.py config.env
git commit -m "feat(config): add MAP_LOCAL_TILES, MAP_REGION, REGION_BOUNDS (YAY-156)"
```

---

### Task 2: map_router.py — use config-driven bounds

**Files:**
- Modify: `routers/map_router.py`

- [ ] **Step 1: Write failing test**

In `tests/test_api.py`, add:

```python
@pytest.mark.anyio
async def test_map_page_uses_region_bounds(client):
    import config as cfg
    resp = await client.get('/map')
    assert resp.status_code == 200
    expected_lat = str(cfg.REGION_BOUNDS[cfg.MAP_REGION]['lat_min'])
    assert expected_lat in resp.text
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_api.py::test_map_page_uses_region_bounds -v
```

Expected: FAIL (map page returns hardcoded DEFAULT_BOUNDS, not config bounds)

- [ ] **Step 3: Update map_router.py**

Open `routers/map_router.py`. Replace the `DEFAULT_BOUNDS` constant and its usage:

```python
# Remove:
DEFAULT_BOUNDS = {
    'lat_min': 35.0, 'lat_max': 47.5,
    'lon_min': 6.5,  'lon_max': 18.5,
}

# In the route function, replace:
#   'bounds': DEFAULT_BOUNDS,
# With:
#   'bounds': cfg.REGION_BOUNDS.get(cfg.MAP_REGION, cfg.REGION_BOUNDS['italia']),
```

Full updated route:

```python
import config as cfg  # add this import at top if not present

@router.get('/map', response_class=HTMLResponse)
async def map_page(request: Request):
    nodes = await _get_nodes_with_coords()
    bounds = cfg.REGION_BOUNDS.get(cfg.MAP_REGION, cfg.REGION_BOUNDS['italia'])
    return templates.TemplateResponse(request, 'map.html', {
        'active_tab': 'map',
        'bounds':     bounds,
        'zoom_min':   7,
        'zoom_max':   16,
        'nodes_data': nodes,
    })
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api.py::test_map_page_uses_region_bounds -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add routers/map_router.py tests/test_api.py
git commit -m "feat(map): use config-driven region bounds (YAY-156)"
```

---

### Task 3: Inject MAP_LOCAL_TILES as JS global

**Files:**
- Modify: `main.py`, `templates/base.html`, `static/map.js`

- [ ] **Step 1: Set Jinja2 global in main.py**

In `main.py`, find where `templates` is instantiated:

```python
templates = Jinja2Templates(directory='templates')
```

Add immediately after:

```python
templates.env.globals['map_local_tiles'] = '1' if cfg.MAP_LOCAL_TILES else '0'
```

Make sure `import config as cfg` is present at the top.

- [ ] **Step 2: Inject JS global in base.html**

In `templates/base.html`, inside `<head>` after the existing `<style>` block (before `{% block head %}`), add:

```html
<script>window.MAP_LOCAL_TILES = "{{ map_local_tiles }}";</script>
```

- [ ] **Step 3: Update map.js to read JS global**

In `static/map.js`, find line:

```js
var localTiles     = document.documentElement.dataset.localTiles === '1'
```

Replace with:

```js
var localTiles     = window.MAP_LOCAL_TILES === '1'
```

- [ ] **Step 4: Write test**

In `tests/test_api.py`, add:

```python
@pytest.mark.anyio
async def test_base_html_injects_map_local_tiles(client):
    resp = await client.get('/nodes')
    assert resp.status_code == 200
    assert 'window.MAP_LOCAL_TILES' in resp.text
```

- [ ] **Step 5: Run test**

```bash
pytest tests/test_api.py::test_base_html_injects_map_local_tiles -v
```

Expected: PASS

- [ ] **Step 6: Bump map.js version in map.html**

In `templates/map.html`, update `?v=12` to `?v=13` on the map.js script tag.

- [ ] **Step 7: Commit**

```bash
git add main.py templates/base.html static/map.js templates/map.html tests/test_api.py
git commit -m "feat(map): inject MAP_LOCAL_TILES as JS global via Jinja2 (YAY-156)"
```

---

### Task 4: config_router.py — GET/POST /api/config/map

**Files:**
- Modify: `routers/config_router.py`, `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_api.py`, add:

```python
@pytest.mark.anyio
async def test_get_map_config_returns_fields(client):
    resp = await client.get('/api/config/map')
    assert resp.status_code == 200
    data = resp.json()
    assert 'local_tiles' in data
    assert 'region' in data
    assert 'tiles_present' in data
    assert isinstance(data['local_tiles'], bool)

@pytest.mark.anyio
async def test_post_map_config_updates_local_tiles(client, tmp_path, monkeypatch):
    import routers.config_router as cr
    env_file = tmp_path / 'config.env'
    env_file.write_text('MAP_LOCAL_TILES=0\nMAP_REGION=italia\n')
    monkeypatch.setattr(cr, 'CONFIG_ENV_PATH', str(env_file))
    resp = await client.post('/api/config/map', json={'local_tiles': True})
    assert resp.status_code == 200
    assert 'MAP_LOCAL_TILES=1' in env_file.read_text()
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_api.py::test_get_map_config_returns_fields tests/test_api.py::test_post_map_config_updates_local_tiles -v
```

Expected: FAIL (endpoints don't exist)

- [ ] **Step 3: Implement in config_router.py**

Add at the top of `routers/config_router.py`:

```python
import os
import config as cfg

CONFIG_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.env')

def _write_env(key: str, value: str) -> None:
    """Write or update a KEY=value line in config.env."""
    path = CONFIG_ENV_PATH
    try:
        lines = open(path).readlines()
    except FileNotFoundError:
        lines = []
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f'{key}=') or line.startswith(f'{key} ='):
            new_lines.append(f'{key}={value}\n')
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f'{key}={value}\n')
    with open(path, 'w') as f:
        f.writelines(new_lines)
```

Add request model and endpoints:

```python
from pydantic import BaseModel

class MapConfigRequest(BaseModel):
    local_tiles: bool

@router.get('/api/config/map')
async def get_map_config():
    tiles_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'tiles', 'osm')
    tiles_present = os.path.isdir(tiles_dir) and bool(os.listdir(tiles_dir))
    return {
        'local_tiles':  cfg.MAP_LOCAL_TILES,
        'region':       cfg.MAP_REGION,
        'tiles_present': tiles_present,
    }

@router.post('/api/config/map')
async def post_map_config(body: MapConfigRequest):
    _write_env('MAP_LOCAL_TILES', '1' if body.local_tiles else '0')
    cfg.MAP_LOCAL_TILES = body.local_tiles
    return {'local_tiles': cfg.MAP_LOCAL_TILES, 'region': cfg.MAP_REGION}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api.py::test_get_map_config_returns_fields tests/test_api.py::test_post_map_config_updates_local_tiles -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add routers/config_router.py tests/test_api.py
git commit -m "feat(config): add GET/POST /api/config/map endpoint (YAY-156)"
```

---

### Task 5: config.html — Mappa section

**Files:**
- Modify: `templates/config.html`

- [ ] **Step 1: Add Mappa section Alpine.js state**

In `templates/config.html`, find the main Alpine.js `x-data` object initialization (the `data()` function or inline object). Add `mappa` state alongside existing sections (lora, node, etc.):

```js
mappa: { local_tiles: false, region: 'italia', tiles_present: false, cached: false, saving: false },
```

Add `loadMappa` method in the methods object:

```js
async loadMappa() {
  if (this.mappa.cached) return
  const r = await fetch('/api/config/map')
  const d = await r.json()
  this.mappa.local_tiles  = d.local_tiles
  this.mappa.region       = d.region
  this.mappa.tiles_present = d.tiles_present
  this.mappa.cached = true
},
async saveMappa() {
  this.mappa.saving = true
  await fetch('/api/config/map', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ local_tiles: this.mappa.local_tiles })
  })
  this.mappa.saving = false
},
```

Trigger load when section opens — add to the `openSection` or equivalent handler:

```js
if (s === 'mappa') await this.loadMappa()
```

- [ ] **Step 2: Add Mappa section HTML**

Add a new section block in the config sections list (after the existing sections):

```html
<!-- MAPPA -->
<div x-show="section === 'mappa'">
  <button @click="section = section === 'mappa' ? '' : 'mappa'; if(section==='mappa') loadMappa()"
          class="w-full flex items-center justify-between px-3 py-2 text-left"
          style="font-size:11px;font-weight:600;color:var(--text);border-bottom:1px solid var(--border);">
    <span>Mappa</span>
    <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
         :style="section==='mappa' ? 'transform:rotate(180deg)' : ''">
      <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>
    </svg>
  </button>
  <div x-show="section === 'mappa'" x-cloak class="px-3 py-3 space-y-3">

    <!-- Tile locali toggle -->
    <div class="flex items-center justify-between">
      <div>
        <div style="font-size:11px;font-weight:600">Tile locali</div>
        <div style="font-size:10px;color:var(--muted)">Usa tile offline invece del CDN</div>
      </div>
      <button @click="mappa.local_tiles = !mappa.local_tiles; saveMappa()"
              :disabled="!mappa.tiles_present"
              :style="mappa.local_tiles ? 'background:#1a3a2a;border-color:#22c55e;color:#22c55e' : 'background:var(--panel);border-color:var(--border);color:var(--muted)'"
              style="border:1px solid;border-radius:12px;padding:3px 10px;font-size:10px;cursor:pointer"
              x-text="mappa.local_tiles ? 'ON' : 'OFF'"></button>
    </div>

    <!-- Regione -->
    <div class="flex items-center justify-between">
      <span style="font-size:11px;color:var(--muted)">Regione</span>
      <span style="font-size:11px" x-text="mappa.region || '—'"></span>
    </div>

    <!-- Stato tile -->
    <div class="flex items-center justify-between">
      <span style="font-size:11px;color:var(--muted)">Tile locali</span>
      <span style="font-size:10px;padding:2px 8px;border-radius:4px"
            :style="mappa.tiles_present ? 'background:#1a3a2a;color:#22c55e' : 'background:var(--panel);color:var(--muted)'"
            x-text="mappa.tiles_present ? '✓ presenti' : '✗ assenti'"></span>
    </div>

    <p x-show="!mappa.tiles_present" style="font-size:10px;color:var(--muted)">
      Esegui <code>scripts/manage-tiles.sh</code> dal Mac/PC per trasferire le tile al Pi.
    </p>
  </div>
</div>
```

- [ ] **Step 3: Verify manually**

Deploy to Pi and open Config page. Navigate to Mappa section. Verify:
- Toggle shows ON/OFF
- Region shows "italia"
- Tile status shows ✓ or ✗ based on actual tile presence

- [ ] **Step 4: Commit**

```bash
git add templates/config.html
git commit -m "feat(config-ui): add Mappa section with local tiles toggle (YAY-156)"
```

---

### Task 6: scripts/manage-tiles.sh

**Files:**
- Create: `scripts/manage-tiles.sh`

- [ ] **Step 1: Create the script**

```bash
#!/usr/bin/env bash
# manage-tiles.sh — Select region, download tiles if needed, rsync to Pi
# Usage: bash scripts/manage-tiles.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TILES_DIR="$PROJECT_DIR/static/tiles"
CONFIG_ENV="$PROJECT_DIR/config.env"

# ─── Region definitions ─────────────────────────────────────────────────────
declare -A REGION_NAMES=(
  [italia]="🇮🇹  Italia"
  [francia]="🇫🇷  Francia"
  [germania]="🇩🇪  Germania"
  [spagna]="🇪🇸  Spagna"
  [europa]="🌍  Europa"
  [mondo]="🌐  Mondo (z1-z8)"
)
declare -A REGION_LAT_MIN=([italia]=35.0 [francia]=41.3 [germania]=47.3 [spagna]=35.9 [europa]=34.0 [mondo]=-85.0)
declare -A REGION_LAT_MAX=([italia]=47.5 [francia]=51.1 [germania]=55.1 [spagna]=43.8 [europa]=72.0 [mondo]=85.0)
declare -A REGION_LON_MIN=([italia]=6.5  [francia]=-5.2 [germania]=5.9  [spagna]=-9.3 [europa]=-25.0 [mondo]=-180.0)
declare -A REGION_LON_MAX=([italia]=18.5 [francia]=9.6  [germania]=15.0 [spagna]=4.3  [europa]=45.0  [mondo]=180.0)
declare -A REGION_ZOOM=([italia]="7 8 9 10 11 12" [francia]="7 8 9 10 11 12" [germania]="7 8 9 10 11 12" [spagna]="7 8 9 10 11 12" [europa]="7 8 9 10 11" [mondo]="1 2 3 4 5 6 7 8")
REGION_KEYS=(italia francia germania spagna europa mondo)

# ─── Read Pi SSH settings ────────────────────────────────────────────────────
PI_HOST=$(grep '^SSH_HOST=' "$CONFIG_ENV" 2>/dev/null | cut -d= -f2 || true)
PI_USER=$(grep '^SSH_USER=' "$CONFIG_ENV" 2>/dev/null | cut -d= -f2 || echo "pimesh")
PI_PATH="/home/${PI_USER}/pi-Mesh/static/tiles"

if [[ -z "$PI_HOST" ]]; then
  read -r -p "Pi IP address [192.168.1.36]: " PI_HOST
  PI_HOST="${PI_HOST:-192.168.1.36}"
fi

# ─── Menu ────────────────────────────────────────────────────────────────────
echo ""
echo "  🗺  pi-Mesh Tile Manager"
echo "  Pi: ${PI_USER}@${PI_HOST}"
echo ""
echo "  Seleziona regione:"
echo ""
i=1
for key in "${REGION_KEYS[@]}"; do
  local_status=""
  if [[ -d "$TILES_DIR/osm/$( echo "${REGION_ZOOM[$key]}" | awk '{print $1}' )" ]]; then
    size=$(du -sh "$TILES_DIR" 2>/dev/null | cut -f1 || echo "?")
    local_status=" \033[32m✓ tile presenti ($size)\033[0m"
  else
    local_status=" \033[90m— non scaricate\033[0m"
  fi
  printf "  %d) %s%b\n" "$i" "${REGION_NAMES[$key]}" "$local_status"
  ((i++))
done
echo ""
read -r -p "  > " choice
echo ""

# Validate input
if ! [[ "$choice" =~ ^[1-6]$ ]]; then
  echo "Scelta non valida." && exit 1
fi
REGION="${REGION_KEYS[$((choice-1))]}"
echo "  Regione selezionata: ${REGION_NAMES[$REGION]}"
echo ""

# ─── Download tiles if missing ───────────────────────────────────────────────
LAYERS=(osm topo satellite)
LAYER_URLS=(
  "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
  "https://tile.opentopomap.org/{z}/{x}/{y}.png"
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

_lon2x() { echo "scale=0; (($1 + 180) / 360 * 2^$2) / 1" | bc; }
_lat2y() {
  python3 -c "
import math, sys
lat,z = float('$1'), int('$2')
lat_r = math.radians(lat)
n = 2**z
y = int((1 - math.log(math.tan(lat_r) + 1/math.cos(lat_r))/math.pi) / 2 * n)
print(y)
"
}

for idx in 0 1 2; do
  LAYER="${LAYERS[$idx]}"
  URL_TMPL="${LAYER_URLS[$idx]}"
  LAYER_DIR="$TILES_DIR/$LAYER"

  missing=false
  for z in ${REGION_ZOOM[$REGION]}; do
    [[ ! -d "$LAYER_DIR/$z" ]] && missing=true && break
  done

  if $missing; then
    echo "  📥 Download layer: $LAYER"
    for z in ${REGION_ZOOM[$REGION]}; do
      x_min=$(_lon2x "${REGION_LON_MIN[$REGION]}" "$z")
      x_max=$(_lon2x "${REGION_LON_MAX[$REGION]}" "$z")
      y_min=$(_lat2y "${REGION_LAT_MAX[$REGION]}" "$z")
      y_max=$(_lat2y "${REGION_LAT_MIN[$REGION]}" "$z")
      echo "    z=$z: x=$x_min-$x_max y=$y_min-$y_max"
      for ((x=x_min; x<=x_max; x++)); do
        mkdir -p "$LAYER_DIR/$z/$x"
        for ((y=y_min; y<=y_max; y++)); do
          dest="$LAYER_DIR/$z/$x/$y.png"
          [[ -f "$dest" ]] && continue
          url="${URL_TMPL//\{z\}/$z}"
          url="${url//\{x\}/$x}"
          url="${url//\{y\}/$y}"
          curl -sf -A "pi-Mesh/1.0 tile-download" -o "$dest" "$url" || true
          sleep 0.15  # respect rate limits
        done
      done
    done
    echo "  ✓ Layer $LAYER scaricato"
    echo ""
  else
    echo "  ✓ Layer $LAYER già presente"
  fi
done

# ─── rsync to Pi ────────────────────────────────────────────────────────────
echo "  📡 Trasferisco tile al Pi..."
rsync -av --progress "$TILES_DIR/" "${PI_USER}@${PI_HOST}:${PI_PATH}/"
echo "  ✓ Tile copiate"
echo ""

# ─── Update Pi config ────────────────────────────────────────────────────────
echo "  ⚙️  Aggiorno configurazione Pi..."
ssh "${PI_USER}@${PI_HOST}" "
  cd ~/pi-Mesh
  grep -q '^MAP_LOCAL_TILES=' config.env && sed -i 's/^MAP_LOCAL_TILES=.*/MAP_LOCAL_TILES=1/' config.env || echo 'MAP_LOCAL_TILES=1' >> config.env
  grep -q '^MAP_REGION=' config.env && sed -i 's/^MAP_REGION=.*/MAP_REGION=${REGION}/' config.env || echo 'MAP_REGION=${REGION}' >> config.env
  grep -q '^SSH_HOST=' config.env || echo 'SSH_HOST=${PI_HOST}' >> config.env
  sudo systemctl restart pimesh
  echo '✓ Config aggiornata e pimesh riavviato'
"
echo ""
echo "  ✅ Done! pi-Mesh ora usa tile locali per: ${REGION_NAMES[$REGION]}"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/manage-tiles.sh
```

- [ ] **Step 3: Test dry run (no rsync)**

```bash
bash scripts/manage-tiles.sh
```

Select region 1 (Italia). Verify it detects existing tiles in `static/tiles/osm/` and proceeds to rsync step. Confirm rsync prompt (or Ctrl+C before rsync if Pi unavailable).

- [ ] **Step 4: Commit**

```bash
git add scripts/manage-tiles.sh
git commit -m "feat: add scripts/manage-tiles.sh for offline tile management (YAY-156)"
```

---

### Task 7: .gitignore and final push

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add satellite tiles to .gitignore**

`static/tiles/satellite/` is currently tracked. Add to `.gitignore`:

```
static/tiles/satellite/
```

Remove from git tracking:

```bash
git rm -r --cached static/tiles/satellite/ 2>/dev/null || true
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Push and deploy**

```bash
git add .gitignore
git commit -m "chore: gitignore satellite tiles (YAY-156)"
git push origin rework/v2-rewrite
ssh pimesh@192.168.1.36 "cd ~/pi-Mesh && git pull && sudo systemctl restart pimesh"
```

- [ ] **Step 4: Transfer tiles via manage-tiles.sh**

```bash
bash scripts/manage-tiles.sh
```

Select Italia. Confirm rsync completes and Pi config is updated.

- [ ] **Step 5: Verify on Pi**

```bash
ssh pimesh@192.168.1.36 "grep MAP_ ~/pi-Mesh/config.env && ls ~/pi-Mesh/static/tiles/osm/ | head"
```

Expected:
```
MAP_LOCAL_TILES=1
MAP_REGION=italia
7
8
9
...
```

- [ ] **Step 6: Mark YAY-156 as Done in Linear**

Update issue status to Done.
