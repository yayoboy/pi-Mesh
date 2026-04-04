# YAY-98 Telemetria — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare pagina Metriche con telemetria completa della board Meshtastic e del Raspberry Pi, con chart storici real-time.

**Architecture:** Nuova tabella `telemetry` per storicizzare tutti i dati ricevuti via TELEMETRY_APP. Nuovo modulo `rpi_telemetry.py` per raccogliere metriche del Raspberry (CPU temp, RAM, disk, uptime). Router dedicato `/metrics` con API REST. Frontend con chart Canvas leggeri (no librerie esterne — troppo pesanti per il Pi). Aggiornamento real-time via WebSocket (già presente). Due sezioni nella pagina: Board Meshtastic (device + environment metrics) e Raspberry Pi.

**Tech Stack:** Python/FastAPI, SQLite/aiosqlite, Jinja2, Alpine.js, Canvas API per chart

---

## File Structure

| File | Responsabilita |
|------|---------------|
| `database.py` | Aggiungere tabella `telemetry`, funzioni save/query |
| `meshtasticd_client.py` | Espandere handler `TELEMETRY_APP` per catturare tutti i campi |
| `rpi_telemetry.py` | **Nuovo** — raccolta metriche RPi (CPU temp, RAM, disk, uptime, CPU%) |
| `routers/metrics_router.py` | **Nuovo** — sostituisce placeholder, API + pagina metriche |
| `routers/placeholders.py` | Rimuovere route `/metrics` (spostata) |
| `templates/metrics.html` | **Nuovo** — pagina metriche con chart e dati real-time |
| `main.py` | Registrare nuovo router, avviare task raccolta RPi |
| `static/app.js` | Gestire eventi WS `telemetry` e `rpi_telemetry` |

---

### Task 1: Schema DB telemetria

**Files:**
- Modify: `database.py` — aggiungere tabella e funzioni

- [ ] **Step 1: Aggiungere tabella telemetry allo schema**

In `database.py`, aggiungere alla stringa `_SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS telemetry (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,
    node_id   TEXT NOT NULL,
    ttype     TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_node_ts ON telemetry(node_id, ts DESC);
```

`ttype` puo essere: `device`, `environment`, `power`, `air_quality`.
`data_json` contiene il dict JSON con tutti i campi del tipo specifico.

- [ ] **Step 2: Aggiungere funzione save_telemetry**

```python
async def save_telemetry(db_path: str, node_id: str, ttype: str, data: dict) -> int:
    ts = int(time.time())
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            'INSERT INTO telemetry (ts, node_id, ttype, data_json) VALUES (?,?,?,?)',
            (ts, node_id, ttype, json.dumps(data))
        )
        await db.commit()
        return cursor.lastrowid
```

- [ ] **Step 3: Aggiungere funzione get_telemetry**

```python
async def get_telemetry(db_path: str, node_id: str | None = None,
                        ttype: str | None = None, limit: int = 100,
                        since: int | None = None) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        where = []
        params = []
        if node_id:
            where.append('node_id = ?')
            params.append(node_id)
        if ttype:
            where.append('ttype = ?')
            params.append(ttype)
        if since:
            where.append('ts > ?')
            params.append(since)
        clause = ('WHERE ' + ' AND '.join(where)) if where else ''
        cursor = await db.execute(
            f'SELECT * FROM telemetry {clause} ORDER BY ts DESC LIMIT ?',
            params + [limit]
        )
        rows = await cursor.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['data'] = json.loads(d.pop('data_json'))
        result.append(d)
    return result
```

- [ ] **Step 4: Aggiungere funzione cleanup_telemetry**

```python
async def cleanup_telemetry(db_path: str, max_age_hours: int = 72) -> None:
    cutoff = int(time.time()) - (max_age_hours * 3600)
    async with aiosqlite.connect(db_path) as db:
        await db.execute('DELETE FROM telemetry WHERE ts < ?', (cutoff,))
        await db.commit()
```

- [ ] **Step 5: Commit**

```bash
git add database.py
git commit -m "feat(db): add telemetry table and query functions (YAY-98)"
```

---

### Task 2: Espandere handler TELEMETRY_APP

**Files:**
- Modify: `meshtasticd_client.py:356-366`

- [ ] **Step 1: Espandere _on_receive per catturare tutti i campi telemetria**

Sostituire il blocco `elif portnum == 'TELEMETRY_APP':` con:

```python
elif portnum == 'TELEMETRY_APP':
    telemetry = decoded.get('telemetry', {})

    # Device metrics
    device_metrics = telemetry.get('deviceMetrics', {})
    if device_metrics:
        tdata = {
            'battery_level': device_metrics.get('batteryLevel'),
            'voltage': device_metrics.get('voltage'),
            'channel_utilization': device_metrics.get('channelUtilization'),
            'air_util_tx': device_metrics.get('airUtilTx'),
            'uptime_seconds': device_metrics.get('uptimeSeconds'),
        }
        typed_event = {
            'type': 'telemetry',
            'ttype': 'device',
            'id': from_id,
            'data': tdata,
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)
            fut = asyncio.run_coroutine_threadsafe(
                database.save_telemetry(cfg.DB_PATH, from_id, 'device', tdata), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_telemetry failed: %s', f.exception())
                if f.exception() else None
            )

    # Environment metrics
    env_metrics = telemetry.get('environmentMetrics', {})
    if env_metrics:
        tdata = {
            'temperature': env_metrics.get('temperature'),
            'relative_humidity': env_metrics.get('relativeHumidity'),
            'barometric_pressure': env_metrics.get('barometricPressure'),
            'gas_resistance': env_metrics.get('gasResistance'),
            'iaq': env_metrics.get('iaq'),
        }
        typed_event = {
            'type': 'telemetry',
            'ttype': 'environment',
            'id': from_id,
            'data': tdata,
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)
            fut = asyncio.run_coroutine_threadsafe(
                database.save_telemetry(cfg.DB_PATH, from_id, 'environment', tdata), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_telemetry failed: %s', f.exception())
                if f.exception() else None
            )

    # Power metrics
    power_metrics = telemetry.get('powerMetrics', {})
    if power_metrics:
        tdata = dict(power_metrics)
        typed_event = {
            'type': 'telemetry',
            'ttype': 'power',
            'id': from_id,
            'data': tdata,
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)
            fut = asyncio.run_coroutine_threadsafe(
                database.save_telemetry(cfg.DB_PATH, from_id, 'power', tdata), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_telemetry failed: %s', f.exception())
                if f.exception() else None
            )

    # Air quality metrics
    air_quality = telemetry.get('airQualityMetrics', {})
    if air_quality:
        tdata = dict(air_quality)
        typed_event = {
            'type': 'telemetry',
            'ttype': 'air_quality',
            'id': from_id,
            'data': tdata,
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)
            fut = asyncio.run_coroutine_threadsafe(
                database.save_telemetry(cfg.DB_PATH, from_id, 'air_quality', tdata), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_telemetry failed: %s', f.exception())
                if f.exception() else None
            )
```

- [ ] **Step 2: Commit**

```bash
git add meshtasticd_client.py
git commit -m "feat(telemetry): capture all meshtastic telemetry types (YAY-98)"
```

---

### Task 3: Modulo RPi telemetry

**Files:**
- Create: `rpi_telemetry.py`

- [ ] **Step 1: Creare rpi_telemetry.py**

```python
# rpi_telemetry.py
"""Raspberry Pi system telemetry collection."""
import logging
import os
import time

logger = logging.getLogger(__name__)

_last: dict = {}


def collect() -> dict:
    """Collect current RPi system metrics. Returns dict with all fields."""
    global _last
    data = {
        'ts': int(time.time()),
        'cpu_temp': _cpu_temp(),
        'cpu_percent': _cpu_percent(),
        'ram_total_mb': 0,
        'ram_used_mb': 0,
        'ram_percent': 0.0,
        'disk_total_mb': 0,
        'disk_used_mb': 0,
        'disk_percent': 0.0,
        'uptime_seconds': _uptime(),
    }
    # RAM from /proc/meminfo
    try:
        with open('/proc/meminfo') as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(':')] = int(parts[1])
            total = meminfo.get('MemTotal', 0) // 1024
            available = meminfo.get('MemAvailable', 0) // 1024
            data['ram_total_mb'] = total
            data['ram_used_mb'] = total - available
            data['ram_percent'] = round((total - available) / total * 100, 1) if total else 0
    except (OSError, ValueError, ZeroDivisionError):
        pass

    # Disk usage
    try:
        import shutil
        usage = shutil.disk_usage('/')
        data['disk_total_mb'] = round(usage.total / (1024 * 1024))
        data['disk_used_mb'] = round(usage.used / (1024 * 1024))
        data['disk_percent'] = round(usage.used / usage.total * 100, 1)
    except OSError:
        pass

    _last = data
    return data


def get_last() -> dict:
    """Return last collected metrics without re-collecting."""
    return _last


def _cpu_temp() -> float | None:
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def _cpu_percent() -> float | None:
    try:
        with open('/proc/stat') as f:
            line = f.readline()
        vals = [int(x) for x in line.split()[1:]]
        idle = vals[3]
        total = sum(vals)
        if hasattr(_cpu_percent, '_prev'):
            d_idle = idle - _cpu_percent._prev[0]
            d_total = total - _cpu_percent._prev[1]
            pct = round((1 - d_idle / d_total) * 100, 1) if d_total else 0
        else:
            pct = 0.0
        _cpu_percent._prev = (idle, total)
        return pct
    except (OSError, ValueError, ZeroDivisionError):
        return None


def _uptime() -> int:
    try:
        with open('/proc/uptime') as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError):
        return 0
```

- [ ] **Step 2: Commit**

```bash
git add rpi_telemetry.py
git commit -m "feat: add rpi_telemetry module for system metrics (YAY-98)"
```

---

### Task 4: Router metriche

**Files:**
- Create: `routers/metrics_router.py`
- Modify: `routers/placeholders.py` — rimuovere route `/metrics`
- Modify: `main.py` — registrare nuovo router, task RPi telemetry

- [ ] **Step 1: Creare routers/metrics_router.py**

```python
# routers/metrics_router.py
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import config as cfg
import database
import rpi_telemetry
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/metrics', response_class=HTMLResponse)
async def metrics_page(request: Request):
    return templates.TemplateResponse(request, 'metrics.html', {
        'active_tab': 'metrics',
    })


@router.get('/api/telemetry')
async def get_telemetry(node_id: str | None = None, ttype: str | None = None,
                        limit: int = 100, since: int | None = None):
    return await database.get_telemetry(
        cfg.DB_PATH, node_id=node_id, ttype=ttype, limit=limit, since=since
    )


@router.get('/api/telemetry/latest')
async def get_latest_telemetry():
    """Return latest telemetry for each node, grouped by type."""
    nodes = meshtasticd_client.get_nodes()
    result = {}
    for node in nodes:
        nid = node['id']
        device = await database.get_telemetry(cfg.DB_PATH, node_id=nid, ttype='device', limit=1)
        env = await database.get_telemetry(cfg.DB_PATH, node_id=nid, ttype='environment', limit=1)
        if device or env:
            result[nid] = {
                'short_name': node.get('short_name', nid),
                'device': device[0] if device else None,
                'environment': env[0] if env else None,
            }
    return result


@router.get('/api/rpi/telemetry')
async def get_rpi_telemetry():
    return rpi_telemetry.get_last() or rpi_telemetry.collect()
```

- [ ] **Step 2: Rimuovere /metrics da placeholders.py**

In `routers/placeholders.py`, rimuovere la route `/metrics` e il relativo import se non serve piu. Se placeholders.py resta vuoto, eliminare il file e deregistrare il router da `main.py`.

- [ ] **Step 3: Registrare router e task in main.py**

In `main.py`, aggiungere:

```python
from routers import metrics_router
app.include_router(metrics_router.router)
```

Aggiungere task background per raccolta RPi e cleanup telemetria:

```python
import rpi_telemetry

async def _rpi_telemetry_task():
    """Collect RPi metrics every 30s and broadcast via WS."""
    from routers.ws_router import manager
    while True:
        await asyncio.sleep(30)
        data = rpi_telemetry.collect()
        await manager.broadcast({'type': 'rpi_telemetry', 'data': data})

async def _telemetry_cleanup_task():
    """Remove telemetry older than 72h every hour."""
    while True:
        await asyncio.sleep(3600)
        await database.cleanup_telemetry(cfg.DB_PATH)
```

Nel `lifespan` o `startup`:

```python
asyncio.create_task(_rpi_telemetry_task())
asyncio.create_task(_telemetry_cleanup_task())
```

- [ ] **Step 4: Commit**

```bash
git add routers/metrics_router.py routers/placeholders.py main.py
git commit -m "feat: add metrics router with telemetry API + RPi task (YAY-98)"
```

---

### Task 5: Template metriche con chart

**Files:**
- Create: `templates/metrics.html`

- [ ] **Step 1: Creare pagina metriche**

Layout: due sezioni scrollabili.

**Sezione 1 — Board Meshtastic:**
- Card per ogni nodo con telemetria recente
- Stat boxes: batteria, voltage, ch utilization, air util TX, uptime
- Se presenti environment metrics: temperatura, umidita, pressione
- Mini chart canvas (ultime 24h) per batteria e temperatura

**Sezione 2 — Raspberry Pi:**
- CPU temp con chart
- CPU% con chart
- RAM usage bar
- Disk usage bar
- Uptime

Il template estende `base.html`, usa `x-data="metricsPage()"`, polling ogni 30s + aggiornamento WS.

Chart: canvas 2D semplice, linea con fill gradient, nessuna libreria esterna. Funzione helper `drawMiniChart(canvas, data, color, unit)` che disegna un mini sparkline chart.

```html
{% extends "base.html" %}
{% block content %}
<div x-data="metricsPage()" x-init="init()" style="height:100%;overflow-y:auto;padding:10px 12px;">

  <!-- RPi Section -->
  <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Raspberry Pi</div>
  <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:16px;">

    <!-- CPU Temp -->
    <div style="background:var(--panel);border-radius:6px;padding:8px 10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-size:11px;color:var(--muted);">CPU Temp</span>
        <span style="font-size:14px;font-weight:700;" x-text="rpi.cpu_temp != null ? rpi.cpu_temp + ' C' : '—'"></span>
      </div>
      <canvas x-ref="chartCpuTemp" height="40" style="width:100%;margin-top:4px;"></canvas>
    </div>

    <!-- CPU % -->
    <div style="background:var(--panel);border-radius:6px;padding:8px 10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-size:11px;color:var(--muted);">CPU</span>
        <span style="font-size:14px;font-weight:700;" x-text="rpi.cpu_percent != null ? rpi.cpu_percent + '%' : '—'"></span>
      </div>
      <canvas x-ref="chartCpuPct" height="40" style="width:100%;margin-top:4px;"></canvas>
    </div>

    <!-- RAM bar -->
    <div style="background:var(--panel);border-radius:6px;padding:8px 10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <span style="font-size:11px;color:var(--muted);">RAM</span>
        <span style="font-size:11px;" x-text="rpi.ram_used_mb + ' / ' + rpi.ram_total_mb + ' MB'"></span>
      </div>
      <div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden;">
        <div style="height:100%;border-radius:3px;transition:width 0.5s;"
             :style="'width:' + rpi.ram_percent + '%;background:' + (rpi.ram_percent > 85 ? '#ef4444' : 'var(--accent)')"></div>
      </div>
    </div>

    <!-- Disk bar -->
    <div style="background:var(--panel);border-radius:6px;padding:8px 10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <span style="font-size:11px;color:var(--muted);">Disco</span>
        <span style="font-size:11px;" x-text="rpi.disk_used_mb + ' / ' + rpi.disk_total_mb + ' MB'"></span>
      </div>
      <div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden;">
        <div style="height:100%;border-radius:3px;transition:width 0.5s;"
             :style="'width:' + rpi.disk_percent + '%;background:' + (rpi.disk_percent > 85 ? '#ef4444' : 'var(--accent)')"></div>
      </div>
    </div>

    <!-- Uptime -->
    <div style="background:var(--panel);border-radius:6px;padding:8px 10px;display:flex;justify-content:space-between;">
      <span style="font-size:11px;color:var(--muted);">Uptime</span>
      <span style="font-size:11px;" x-text="formatUptime(rpi.uptime_seconds)"></span>
    </div>
  </div>

  <!-- Board Meshtastic Section -->
  <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Board Meshtastic</div>

  <div x-show="Object.keys(nodesTelemetry).length === 0" style="font-size:11px;color:var(--muted);padding:10px 0;">
    Nessuna telemetria ricevuta
  </div>

  <template x-for="(info, nid) in nodesTelemetry" :key="nid">
    <div style="background:var(--panel);border-radius:6px;padding:10px;margin-bottom:8px;">
      <div style="font-size:12px;font-weight:600;margin-bottom:6px;" x-text="info.short_name || nid"></div>

      <!-- Device metrics -->
      <template x-if="info.device">
        <div class="stat-grid" style="display:flex;gap:6px;flex-wrap:wrap;">
          <div style="flex:1;min-width:60px;background:var(--bg);border-radius:4px;padding:6px;text-align:center;">
            <div style="font-size:12px;font-weight:700;" x-text="info.device.data.battery_level != null ? info.device.data.battery_level + '%' : '—'"></div>
            <div style="font-size:9px;color:var(--muted);">Batt</div>
          </div>
          <div style="flex:1;min-width:60px;background:var(--bg);border-radius:4px;padding:6px;text-align:center;">
            <div style="font-size:12px;font-weight:700;" x-text="info.device.data.voltage != null ? info.device.data.voltage.toFixed(2) + 'V' : '—'"></div>
            <div style="font-size:9px;color:var(--muted);">Volt</div>
          </div>
          <div style="flex:1;min-width:60px;background:var(--bg);border-radius:4px;padding:6px;text-align:center;">
            <div style="font-size:12px;font-weight:700;" x-text="info.device.data.channel_utilization != null ? info.device.data.channel_utilization.toFixed(1) + '%' : '—'"></div>
            <div style="font-size:9px;color:var(--muted);">ChUtil</div>
          </div>
          <div style="flex:1;min-width:60px;background:var(--bg);border-radius:4px;padding:6px;text-align:center;">
            <div style="font-size:12px;font-weight:700;" x-text="info.device.data.air_util_tx != null ? info.device.data.air_util_tx.toFixed(1) + '%' : '—'"></div>
            <div style="font-size:9px;color:var(--muted);">AirTX</div>
          </div>
        </div>
      </template>

      <!-- Environment metrics -->
      <template x-if="info.environment">
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
          <div style="flex:1;min-width:60px;background:var(--bg);border-radius:4px;padding:6px;text-align:center;">
            <div style="font-size:12px;font-weight:700;" x-text="info.environment.data.temperature != null ? info.environment.data.temperature.toFixed(1) + ' C' : '—'"></div>
            <div style="font-size:9px;color:var(--muted);">Temp</div>
          </div>
          <div style="flex:1;min-width:60px;background:var(--bg);border-radius:4px;padding:6px;text-align:center;">
            <div style="font-size:12px;font-weight:700;" x-text="info.environment.data.relative_humidity != null ? info.environment.data.relative_humidity.toFixed(0) + '%' : '—'"></div>
            <div style="font-size:9px;color:var(--muted);">Umid</div>
          </div>
          <div style="flex:1;min-width:60px;background:var(--bg);border-radius:4px;padding:6px;text-align:center;">
            <div style="font-size:12px;font-weight:700;" x-text="info.environment.data.barometric_pressure != null ? info.environment.data.barometric_pressure.toFixed(0) + ' hPa' : '—'"></div>
            <div style="font-size:9px;color:var(--muted);">Press</div>
          </div>
        </div>
      </template>
    </div>
  </template>
</div>

<script>
function metricsPage() {
  return {
    rpi: { cpu_temp: null, cpu_percent: null, ram_total_mb: 0, ram_used_mb: 0, ram_percent: 0,
           disk_total_mb: 0, disk_used_mb: 0, disk_percent: 0, uptime_seconds: 0 },
    nodesTelemetry: {},
    _rpiHistory: { cpu_temp: [], cpu_pct: [] },
    _interval: null,
    _wsHandler: null,

    async init() {
      await this.loadRpi()
      await this.loadNodeTelemetry()
      this._interval = setInterval(() => { this.loadRpi(); this.loadNodeTelemetry() }, 30000)

      this._wsHandler = (e) => {
        const msg = e.detail
        if (msg.type === 'rpi_telemetry') {
          this.rpi = msg.data
          this._pushRpiHistory(msg.data)
        }
        if (msg.type === 'telemetry') {
          this._updateNodeTelemetry(msg)
        }
      }
      window.addEventListener('ws-message', this._wsHandler)
    },

    destroy() {
      clearInterval(this._interval)
      if (this._wsHandler) window.removeEventListener('ws-message', this._wsHandler)
    },

    async loadRpi() {
      try {
        const r = await fetch('/api/rpi/telemetry')
        if (r.ok) {
          this.rpi = await r.json()
          this._pushRpiHistory(this.rpi)
        }
      } catch(e) {}
    },

    async loadNodeTelemetry() {
      try {
        const r = await fetch('/api/telemetry/latest')
        if (r.ok) this.nodesTelemetry = await r.json()
      } catch(e) {}
    },

    _updateNodeTelemetry(msg) {
      const nid = msg.id
      if (!this.nodesTelemetry[nid]) {
        this.nodesTelemetry[nid] = { short_name: nid }
      }
      if (msg.ttype === 'device') {
        this.nodesTelemetry[nid].device = { data: msg.data }
      } else if (msg.ttype === 'environment') {
        this.nodesTelemetry[nid].environment = { data: msg.data }
      }
    },

    _pushRpiHistory(data) {
      const max = 60
      if (data.cpu_temp != null) {
        this._rpiHistory.cpu_temp.push(data.cpu_temp)
        if (this._rpiHistory.cpu_temp.length > max) this._rpiHistory.cpu_temp.shift()
        this.$nextTick(() => this._drawChart(this.$refs.chartCpuTemp, this._rpiHistory.cpu_temp, '#4a9eff'))
      }
      if (data.cpu_percent != null) {
        this._rpiHistory.cpu_pct.push(data.cpu_percent)
        if (this._rpiHistory.cpu_pct.length > max) this._rpiHistory.cpu_pct.shift()
        this.$nextTick(() => this._drawChart(this.$refs.chartCpuPct, this._rpiHistory.cpu_pct, '#22c55e'))
      }
    },

    _drawChart(canvas, data, color) {
      if (!canvas || data.length < 2) return
      const ctx = canvas.getContext('2d')
      const w = canvas.width = canvas.offsetWidth * (window.devicePixelRatio || 1)
      const h = canvas.height = 40 * (window.devicePixelRatio || 1)
      ctx.clearRect(0, 0, w, h)
      const min = Math.min(...data) - 1
      const max = Math.max(...data) + 1
      const range = max - min || 1
      const step = w / (data.length - 1)

      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.lineWidth = 1.5
      data.forEach((v, i) => {
        const x = i * step
        const y = h - ((v - min) / range) * h * 0.85
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      })
      ctx.stroke()

      // Fill gradient
      ctx.lineTo((data.length - 1) * step, h)
      ctx.lineTo(0, h)
      ctx.closePath()
      const grad = ctx.createLinearGradient(0, 0, 0, h)
      grad.addColorStop(0, color + '33')
      grad.addColorStop(1, color + '05')
      ctx.fillStyle = grad
      ctx.fill()
    },

    formatUptime(seconds) {
      if (!seconds) return '—'
      const d = Math.floor(seconds / 86400)
      const h = Math.floor((seconds % 86400) / 3600)
      const m = Math.floor((seconds % 3600) / 60)
      if (d > 0) return d + 'g ' + h + 'h'
      if (h > 0) return h + 'h ' + m + 'm'
      return m + 'm'
    },
  }
}
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/metrics.html
git commit -m "feat: add metrics page with RPi + board telemetry charts (YAY-98)"
```

---

### Task 6: Integrare WS events in app.js

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Aggiungere dispatch per telemetry e rpi_telemetry nel handler WS**

Nel handler WebSocket di `app.js`, dove vengono gestiti i vari `msg.type`, aggiungere:

```javascript
if (msg.type === 'telemetry' || msg.type === 'rpi_telemetry') {
  window.dispatchEvent(new CustomEvent('ws-message', { detail: msg }))
}
```

Questo permette alla pagina metriche di ricevere aggiornamenti real-time senza duplicare la logica WS.

- [ ] **Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat(ws): dispatch telemetry events for metrics page (YAY-98)"
```

---

### Task 7: Registrazione in main.py e cleanup

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Verificare che main.py registri il nuovo router e avvii i task**

Controllare che `main.py` includa:
- Import e registrazione `metrics_router`
- Task `_rpi_telemetry_task`
- Task `_telemetry_cleanup_task`
- Rimozione del vecchio router placeholder per `/metrics`

- [ ] **Step 2: Deploy e test sul Pi**

```bash
# rsync dei file modificati
sshpass -p pimesh rsync -avz --relative \
  database.py meshtasticd_client.py rpi_telemetry.py \
  routers/metrics_router.py routers/placeholders.py main.py \
  templates/metrics.html static/app.js \
  pimesh@192.168.1.36:~/pi-Mesh/

# restart servizio
sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 3: Verificare con Playwright**

- Navigare a `http://192.168.1.36:8080/metrics`
- Verificare sezione RPi con dati reali (CPU temp, RAM, disk)
- Verificare sezione Board con nodi e telemetria
- Verificare chart canvas funzionanti
- Testare in portrait (320x480) e landscape (480x320)

- [ ] **Step 4: Commit finale**

```bash
git add -A
git commit -m "feat: complete telemetry page with RPi + board metrics (YAY-98)"
```

---

## Telemetry Types Reference

| Type | Protobuf Field | Campi |
|------|---------------|-------|
| `device` | `deviceMetrics` | batteryLevel, voltage, channelUtilization, airUtilTx, uptimeSeconds |
| `environment` | `environmentMetrics` | temperature, relativeHumidity, barometricPressure, gasResistance, iaq |
| `power` | `powerMetrics` | ch1Voltage, ch1Current, ch2Voltage, ch2Current, ch3Voltage, ch3Current |
| `air_quality` | `airQualityMetrics` | pm10, pm25, pm100, particles03, particles05, particles10, particles25, particles50, particles100 |
