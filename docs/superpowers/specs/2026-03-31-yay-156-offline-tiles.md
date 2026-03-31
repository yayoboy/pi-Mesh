# YAY-156 — Offline Tile Management

## Overview

Add a `scripts/manage-tiles.sh` script (cross-platform bash) that lets any user select a region, optionally download tiles, and rsync them to the Pi. Add a Mappa section in Config to toggle local vs CDN tile mode.

## Component 1 — `scripts/manage-tiles.sh`

Interactive bash script, runs on Mac/PC/Linux.

**Flow:**
1. Read Pi connection info from `config.env` (SSH_HOST, SSH_USER) or prompt if missing
2. Show numbered menu of regions, marking which have tiles already present locally
3. User selects region:
   - If tiles present locally → skip download
   - If tiles missing → download from OSM/topo/Esri tile servers (wget + rate-limit sleep)
4. `rsync -av static/tiles/ pimesh@<PI_IP>:/home/pimesh/pi-Mesh/static/tiles/`
5. SSH to Pi: update `config.env` (`MAP_LOCAL_TILES=1`, `MAP_REGION=<region>`)
6. SSH to Pi: `sudo systemctl restart pimesh`

**Predefined regions** (name → bbox → zoom levels):

| Region | lat_min | lat_max | lon_min | lon_max | zoom |
|--------|---------|---------|---------|---------|------|
| italia | 35.0 | 47.5 | 6.5 | 18.5 | 7–14 |
| francia | 41.3 | 51.1 | -5.2 | 9.6 | 7–14 |
| germania | 47.3 | 55.1 | 5.9 | 15.0 | 7–14 |
| spagna | 35.9 | 43.8 | -9.3 | 4.3 | 7–14 |
| europa | 34.0 | 72.0 | -25.0 | 45.0 | 7–11 |
| mondo | -85.0 | 85.0 | -180.0 | 180.0 | 1–8 |

**Download approach:** wget tile by tile with 100ms sleep between requests (respects OSM ToS). Downloads osm, topo, satellite layers. Skips tiles already on disk.

**Config.env variables written by script:**
```
MAP_LOCAL_TILES=1
MAP_REGION=italia
SSH_HOST=192.168.1.36
SSH_USER=pimesh
```

## Component 2 — Config UI (Mappa section)

New section in `templates/config.html`, after existing sections.

**Fields:**
- **Tile locali** toggle (ON/OFF) — saves to `MAP_LOCAL_TILES` via `POST /api/config/map`
- **Regione** — read-only, shows current `MAP_REGION` value (changed only via script)
- **Stato tile** — badge: ✓ present / ✗ missing (check if `static/tiles/` is non-empty on Pi)

No download/sync button in UI — that lives in the script only.

## Component 3 — Backend

### `config.py`
Add:
```python
MAP_LOCAL_TILES = os.getenv('MAP_LOCAL_TILES', '0') == '1'
MAP_REGION      = os.getenv('MAP_REGION', 'italia')

REGION_BOUNDS = {
    'italia':    {'lat_min': 35.0, 'lat_max': 47.5, 'lon_min': 6.5,   'lon_max': 18.5},
    'francia':   {'lat_min': 41.3, 'lat_max': 51.1, 'lon_min': -5.2,  'lon_max': 9.6},
    'germania':  {'lat_min': 47.3, 'lat_max': 55.1, 'lon_min': 5.9,   'lon_max': 15.0},
    'spagna':    {'lat_min': 35.9, 'lat_max': 43.8, 'lon_min': -9.3,  'lon_max': 4.3},
    'europa':    {'lat_min': 34.0, 'lat_max': 72.0, 'lon_min': -25.0, 'lon_max': 45.0},
    'mondo':     {'lat_min': -85.0,'lat_max': 85.0, 'lon_min':-180.0, 'lon_max':180.0},
}
```

### `map_router.py`
- Replace `DEFAULT_BOUNDS` with `cfg.REGION_BOUNDS.get(cfg.MAP_REGION, cfg.REGION_BOUNDS['italia'])`

### `base.html`
Inject JS global (avoids changing all routers):
```html
<script>window.MAP_LOCAL_TILES = "{{ map_local_tiles }}";</script>
```
Add Jinja2 global in `main.py`:
```python
templates.env.globals['map_local_tiles'] = '1' if cfg.MAP_LOCAL_TILES else '0'
```
Update `map.js`: replace `document.documentElement.dataset.localTiles === '1'` with `window.MAP_LOCAL_TILES === '1'`.

### New API endpoints in `config_router.py`
```
GET  /api/config/map   → { local_tiles: bool, region: str, tiles_present: bool }
POST /api/config/map   → body: { local_tiles: bool } → writes MAP_LOCAL_TILES to config.env
```

`tiles_present`: check if `static/tiles/osm/` directory is non-empty.

Writing to `config.env`: read file, find/replace `MAP_LOCAL_TILES=` line (or append).

## Out of Scope
- Downloading tiles from within the Pi UI
- Custom bounding box editor
- Tile storage management (delete/prune)
- Satellite layer download (large, optional)

## Files to Create/Modify
- **Create:** `scripts/manage-tiles.sh`
- **Modify:** `config.py`, `map_router.py`, `routers/config_router.py`, `templates/config.html`, `templates/base.html`
- **Add to .gitignore:** `static/tiles/satellite/` (currently tracked)
