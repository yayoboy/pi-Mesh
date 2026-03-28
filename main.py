import asyncio, gc, logging, os, re, signal, subprocess, sys, time
import aiosqlite as _aiosqlite
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config as cfg
import database, meshtastic_client, gpio_handler, sensor_handler, sensor_detect, watchdog

gc.set_threshold(100, 5, 5)

ws_clients: set[WebSocket] = set()

async def _enrich_nodes_hop_count(nodes):
    """Attach latest hop_count from messages to each node dict."""
    for n in nodes:
        cur = await _conn.execute(
            "SELECT hop_count FROM messages WHERE node_id=? AND hop_count IS NOT NULL ORDER BY id DESC LIMIT 1",
            (n["id"],)
        )
        row = await cur.fetchone()
        n["hop_count"] = row[0] if row else None
_conn = None
_keyboard_proc = None

def get_conn():
    return _conn

async def broadcast(data: dict):
    dead = set()
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn
    logging.basicConfig(level=logging.INFO)

    _conn = await database.init_db()
    loop  = asyncio.get_event_loop()

    meshtastic_client.init(loop, broadcast, get_conn)
    asyncio.create_task(meshtastic_client.connect())

    if cfg.I2C_AUTOSCAN:
        scanned = await asyncio.to_thread(sensor_detect.scan)
        sensor_list = sensor_detect.merge(scanned, cfg.I2C_SENSORS)
    else:
        sensor_list = cfg.I2C_SENSORS
    app.state.i2c_sensors = sensor_list

    drivers = sensor_handler.init(sensor_list)
    asyncio.create_task(sensor_handler.start_polling(drivers, _conn, broadcast))

    try:
        gpio_handler.init(
            (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
            (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
            broadcast,
            db_conn=_conn
        )
    except Exception as e:
        logging.warning(f"GPIO non disponibile, encoder disabilitati: {e}")

    watchdog.start_all(_conn, broadcast)

    def handle_sigterm(sig, frame):
        asyncio.create_task(_shutdown())
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT,  handle_sigterm)

    yield

    await _shutdown()

async def _shutdown():
    logging.info("Shutdown in corso...")
    await meshtastic_client.disconnect()
    if _conn:
        await database.sync_to_sd(_conn)
        await _conn.close()
    logging.info("Shutdown completato")

app = FastAPI(lifespan=lifespan)

# Static files — crea le directory se non esistono
for d in ["static", "static/tiles", "templates"]:
    os.makedirs(d, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Route pagine ---

@app.get("/")
async def root():
    return RedirectResponse("/messages")

@app.get("/messages")
async def messages_page(request: Request):
    msgs = await database.get_messages(_conn, channel=0, limit=50)
    return templates.TemplateResponse(request, "messages.html", {
        "messages": msgs,
        "theme": cfg.UI_THEME, "accent_color": cfg.UI_ACCENT, "active": "messages"
    })

@app.get("/nodes")
async def nodes_page(request: Request):
    nodes = await database.get_nodes(_conn)
    await _enrich_nodes_hop_count(nodes)
    return templates.TemplateResponse(request, "nodes.html", {
        "nodes": nodes,
        "theme": cfg.UI_THEME, "accent_color": cfg.UI_ACCENT, "active": "nodes"
    })

@app.get("/map")
async def map_page(request: Request):
    return templates.TemplateResponse(request, "map.html", {
        "bounds":   cfg.MAP_BOUNDS,
        "zoom_min": cfg.MAP_ZOOM_MIN,
        "zoom_max": cfg.MAP_ZOOM_MAX,
        "theme":        cfg.UI_THEME,
        "accent_color": cfg.UI_ACCENT,
        "active":       "map"
    })

@app.get("/telemetry")
async def telemetry_page(request: Request):
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse(request, "telemetry.html", {
        "nodes": nodes,
        "theme": cfg.UI_THEME, "accent_color": cfg.UI_ACCENT, "active": "telemetry"
    })

@app.get("/log")
async def log_page(request: Request):
    return templates.TemplateResponse(request, "log.html", {
        "theme": cfg.UI_THEME, "accent_color": cfg.UI_ACCENT, "active": "log"
    })

@app.get("/settings")
async def settings_page(request: Request):
    node_info = meshtastic_client.get_local_node()
    return templates.TemplateResponse(request, "settings.html", {
        "node":             node_info,
        "theme":            cfg.UI_THEME,
        "accent_color":     cfg.UI_ACCENT,
        "active":           "settings",
        "enc1":             (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        "enc2":             (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        "i2c_sensors":      cfg.I2C_SENSORS,
        "display_rotation": cfg.DISPLAY_ROTATION,
        "buzzer_pin":       cfg.BUZZER_PIN,
    })

# --- Route API JSON ---

@app.post("/send")
async def send_message(payload: dict):
    text        = payload.get("text", "").strip()
    channel     = int(payload.get("channel", 0))
    destination = payload.get("destination", "^all")
    if not text:
        return JSONResponse({"ok": False, "error": "testo vuoto"}, status_code=400)
    try:
        await meshtastic_client.send_message(text, channel, destination)
        await database.save_message(_conn, "local", channel, text, int(time.time()), 1, None, None, destination=destination)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/settings")
async def apply_settings(payload: dict):
    try:
        await meshtastic_client.set_config(payload)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/api/nodes")
async def api_nodes():
    nodes = await database.get_nodes(_conn)
    await _enrich_nodes_hop_count(nodes)
    return nodes

@app.delete("/api/nodes/{node_id}")
async def delete_node(node_id: str, cascade: bool = False):
    await database.delete_node(_conn, node_id, cascade)
    return {"ok": True}

@app.get("/api/messages")
async def api_messages(channel: int = 0, limit: int = 50, before_id: int = None):
    return await database.get_messages(_conn, channel, limit, before_id)

@app.get("/api/dm/threads")
async def api_dm_threads():
    threads = await database.get_dm_threads(_conn)
    return JSONResponse({"threads": threads})


@app.get("/api/dm/messages")
async def api_dm_messages(peer: str, limit: int = 50, before_id: int = None):
    if not peer:
        return JSONResponse({"ok": False, "error": "peer mancante"}, status_code=400)
    msgs = await database.get_dm_messages(_conn, peer, limit=limit, before_id=before_id)
    return JSONResponse({"messages": msgs})


@app.post("/api/dm/read")
async def api_dm_read(payload: dict):
    peer = payload.get("peer", "")
    if not peer:
        return JSONResponse({"ok": False, "error": "peer mancante"}, status_code=400)
    await database.mark_dm_read(_conn, peer)
    return JSONResponse({"ok": True})


# --- YAY-114: Map markers ---

@app.get("/api/map/markers")
async def api_map_markers():
    markers = await database.get_markers(_conn)
    return JSONResponse({"markers": markers})

@app.post("/api/map/markers")
async def api_map_markers_create(payload: dict):
    label     = payload.get("label", "").strip()
    icon_type = payload.get("icon_type", "poi")
    latitude  = payload.get("latitude")
    longitude = payload.get("longitude")
    if not label or latitude is None or longitude is None:
        return JSONResponse(
            {"ok": False, "error": "label, latitude e longitude obbligatori"},
            status_code=400
        )
    if icon_type not in ("antenna", "base", "obstacle", "poi"):
        icon_type = "poi"
    marker_id = await database.save_marker(
        _conn, label, icon_type, float(latitude), float(longitude)
    )
    return JSONResponse({"ok": True, "id": marker_id})

@app.delete("/api/map/markers/{marker_id}")
async def api_map_markers_delete(marker_id: int):
    await database.delete_marker(_conn, marker_id)
    return JSONResponse({"ok": True})

# --- YAY-114: Traceroute ---

@app.post("/api/traceroute")
async def api_traceroute_start(payload: dict):
    node_id = payload.get("node_id", "").strip()
    if not node_id:
        return JSONResponse(
            {"ok": False, "error": "node_id obbligatorio"},
            status_code=400
        )
    try:
        await meshtastic_client.request_traceroute(node_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/api/traceroute/{node_id}")
async def api_traceroute_get(node_id: str):
    results = await database.get_traceroutes(_conn, node_id, limit=10)
    return JSONResponse({"results": results})


@app.get("/api/telemetry/{node_id}/{type_}")
async def api_telemetry(node_id: str, type_: str, limit: int = 100):
    return await database.get_telemetry(_conn, node_id, type_, limit)

@app.get("/api/sensor/{sensor_name}")
async def api_sensor(sensor_name: str, limit: int = 100):
    return await database.get_sensor_readings(_conn, sensor_name, limit)

@app.get("/api/export/telemetry")
async def export_telemetry(
    node_id: str,
    type: str,
    format: str = "json",
    limit: int = 1000
):
    import csv, io
    from fastapi.responses import StreamingResponse
    rows = await database.get_telemetry(_conn, node_id, type, limit)
    if format == "csv":
        output = io.StringIO()
        if rows:
            # Flatten: timestamp + tutti i campi di values
            fieldnames = ["node_id", "type", "timestamp"] + list(rows[0]["values"].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for r in rows:
                row_flat = {"node_id": r["node_id"], "type": r["type"], "timestamp": r["timestamp"]}
                row_flat.update(r.get("values", {}))
                writer.writerow(row_flat)
        filename = f"telemetry-{node_id}-{type}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    # default: JSON
    return rows

@app.get("/api/export/sensors")
async def export_sensors(
    name: str,
    format: str = "json",
    limit: int = 1000
):
    import csv, io
    from fastapi.responses import StreamingResponse
    rows = await database.get_sensor_readings(_conn, name, limit)
    if format == "csv":
        output = io.StringIO()
        if rows:
            fieldnames = ["sensor_name", "timestamp"] + list(rows[0]["values"].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for r in rows:
                row_flat = {"sensor_name": r["sensor_name"], "timestamp": r["timestamp"]}
                row_flat.update(r.get("values", {}))
                writer.writerow(row_flat)
        filename = f"sensors-{name}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    return rows

@app.get("/api/i2c/scan")
async def api_i2c_scan(live: bool = False):
    """
    Return detected I2C sensors.
    - ``live=false`` (default): return the list resolved at startup.
    - ``live=true``: re-run the bus scan now (takes ~50 ms on a Pi).
    """
    if live:
        sensors = await asyncio.to_thread(sensor_detect.scan)
        merged  = sensor_detect.merge(sensors, cfg.I2C_SENSORS)
        return JSONResponse({"sensors": merged, "source": "live"})
    sensors = getattr(app.state, "i2c_sensors", [])
    return JSONResponse({"sensors": sensors, "source": "startup"})

@app.get("/api/logs/{source}")
async def api_logs(source: str):
    if source == "board":
        return meshtastic_client.get_board_log()
    if source == "pi":
        import watchdog as wd
        return wd.get_pi_log()
    return JSONResponse({"error": "source non valida"}, status_code=400)

@app.get("/api/status")
async def api_status():
    import resource
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return {
        "connected":  meshtastic_client.is_connected(),
        "node_count": len(await database.get_nodes(_conn)),
        "ram_mb":     round(rss_mb, 1),
    }

@app.get("/tiles/{source}/{z}/{x}/{y}")
async def serve_tile(source: str, z: int, x: int, y: int):
    from fastapi.responses import Response
    # Validate source to prevent path traversal
    if source not in ("osm", "topo", "satellite"):
        return JSONResponse({"error": "invalid source"}, status_code=400)
    mbtiles_path = f"static/tiles/{source}.mbtiles"
    if os.path.isfile(mbtiles_path):
        tms_y = (1 << z) - 1 - y  # flip Y: MBTiles uses TMS convention (Y from bottom)
        try:
            async with _aiosqlite.connect(mbtiles_path) as db:
                cur = await db.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                    (z, x, tms_y)
                )
                row = await cur.fetchone()
                if row:
                    return Response(content=row[0], media_type="image/png")
        except Exception as e:
            logging.warning(f"MBTiles error {mbtiles_path}: {e}")
    # Fallback: file-based tile
    tile_path = f"static/tiles/{source}/{z}/{x}/{y}.png"
    if os.path.isfile(tile_path):
        with open(tile_path, "rb") as f:
            return Response(content=f.read(), media_type="image/png")
    return Response(status_code=204)  # No content — transparent tile

@app.post("/api/keyboard/show")
async def keyboard_show():
    global _keyboard_proc
    if _keyboard_proc is None or _keyboard_proc.poll() is not None:
        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        _keyboard_proc = subprocess.Popen(["matchbox-keyboard"], env=env)
    return {"ok": True}

@app.post("/api/keyboard/hide")
async def keyboard_hide():
    global _keyboard_proc
    if _keyboard_proc and _keyboard_proc.poll() is None:
        _keyboard_proc.terminate()
        _keyboard_proc = None
    return {"ok": True}

@app.post("/api/set-theme")
async def set_theme(payload: dict):
    theme = payload.get("theme", "dark")
    if theme not in ("dark", "light", "hc", "custom"):
        return JSONResponse({"ok": False}, status_code=400)
    await _update_config_env("UI_THEME", theme)
    cfg.UI_THEME = theme
    accent = payload.get("accent_color", "").strip()
    import re
    if accent and re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", accent):
        await _update_config_env("UI_ACCENT", accent)
        cfg.UI_ACCENT = accent
    return {"ok": True}

_ALLOWED_REMOTE_CONFIG_SECTIONS = {"device", "display", "network", "telemetry", "lora", "bluetooth", "position"}

@app.post("/api/remote-config")
async def remote_config(payload: dict):
    node_id = payload.pop("remote_node_id", None)
    if not node_id:
        return JSONResponse({"ok": False, "error": "node_id mancante"}, status_code=400)
    iface = meshtastic_client._interface
    if not iface:
        return JSONResponse({"ok": False, "error": "Non connesso"}, status_code=503)
    try:
        node = await asyncio.to_thread(iface.getNode, node_id)
        for section, values in payload.items():
            if section not in _ALLOWED_REMOTE_CONFIG_SECTIONS:
                logging.warning(f"remote-config: sezione '{section}' non permessa, ignorata")
                continue
            if not isinstance(values, dict):
                continue
            cfg_section = getattr(node.localConfig, section, None) or getattr(node.moduleConfig, section, None)
            if cfg_section:
                for k, v in values.items():
                    setattr(cfg_section, k, v)
                await asyncio.to_thread(node.writeConfig, section)  # non-blocking
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/api/hardware-config")
async def hardware_config(payload: dict):
    try:
        if "enc1_pins" in payload:
            pins = [int(p.strip()) for p in payload["enc1_pins"].split(",")]
            await _update_config_env("ENC1_A",  str(pins[0]))
            await _update_config_env("ENC1_B",  str(pins[1]))
            await _update_config_env("ENC1_SW", str(pins[2]))
        if "enc2_pins" in payload:
            pins = [int(p.strip()) for p in payload["enc2_pins"].split(",")]
            await _update_config_env("ENC2_A",  str(pins[0]))
            await _update_config_env("ENC2_B",  str(pins[1]))
            await _update_config_env("ENC2_SW", str(pins[2]))
        if "i2c_sensors" in payload:
            await _update_config_env("I2C_SENSORS", payload["i2c_sensors"])
        if "display_rotation" in payload:
            await _update_config_env("DISPLAY_ROTATION", str(payload["display_rotation"]))
        if "buzzer_pin" in payload:
            await _update_config_env("BUZZER_PIN", str(int(payload["buzzer_pin"])))
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/api/serial-ports")
async def get_serial_ports():
    import glob as g
    candidates = sorted(g.glob('/dev/ttyACM*') + g.glob('/dev/ttyUSB*') + g.glob('/dev/ttyMESHTASTIC'))
    return {"ports": candidates, "current": cfg.SERIAL_PORT}

@app.get("/api/config")
async def api_config():
    return {
        "SERIAL_PORT": cfg.SERIAL_PORT,
        "MAP_LAT_MIN": cfg.MAP_BOUNDS["lat_min"],
        "MAP_LAT_MAX": cfg.MAP_BOUNDS["lat_max"],
        "MAP_LON_MIN": cfg.MAP_BOUNDS["lon_min"],
        "MAP_LON_MAX": cfg.MAP_BOUNDS["lon_max"],
        "MAP_ZOOM_MIN": cfg.MAP_ZOOM_MIN,
        "MAP_ZOOM_MAX": cfg.MAP_ZOOM_MAX,
        "DB_SYNC_INTERVAL": cfg.DB_SYNC_INTERVAL,
        "I2C_AUTOSCAN": cfg.I2C_AUTOSCAN,
    }

@app.post("/api/config")
async def api_config_save(payload: dict):
    try:
        for key, value in payload.items():
            await _update_config_env(key, str(value))
        # Update live cfg values
        if "SERIAL_PORT" in payload:
            cfg.SERIAL_PORT = payload["SERIAL_PORT"]
        if "MAP_LAT_MIN" in payload:
            cfg.MAP_BOUNDS["lat_min"] = float(payload["MAP_LAT_MIN"])
        if "MAP_LAT_MAX" in payload:
            cfg.MAP_BOUNDS["lat_max"] = float(payload["MAP_LAT_MAX"])
        if "MAP_LON_MIN" in payload:
            cfg.MAP_BOUNDS["lon_min"] = float(payload["MAP_LON_MIN"])
        if "MAP_LON_MAX" in payload:
            cfg.MAP_BOUNDS["lon_max"] = float(payload["MAP_LON_MAX"])
        if "MAP_ZOOM_MIN" in payload:
            cfg.MAP_ZOOM_MIN = int(payload["MAP_ZOOM_MIN"])
        if "MAP_ZOOM_MAX" in payload:
            cfg.MAP_ZOOM_MAX = int(payload["MAP_ZOOM_MAX"])
        if "DB_SYNC_INTERVAL" in payload:
            cfg.DB_SYNC_INTERVAL = int(payload["DB_SYNC_INTERVAL"])
        if "I2C_AUTOSCAN" in payload:
            cfg.I2C_AUTOSCAN = str(payload["I2C_AUTOSCAN"]) not in ("0", "false", "no", "False")
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/api/bot-config")
async def bot_config(payload: dict):
    echo = payload.get("echo", False)
    if echo:
        try:
            from bots import echo_bot
            echo_bot.start(meshtastic_client._interface)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    return {"ok": True}

def _update_config_env_sync(key: str, value: str):
    env_path = "config.env.local" if os.path.exists("config.env.local") else "config.env"
    try:
        with open(env_path) as f:
            content = f.read()
        pattern = rf'^{key}=.*$'
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f'{key}={value}', content, flags=re.MULTILINE)
        else:
            content += f'\n{key}={value}'
        with open(env_path, 'w') as f:
            f.write(content)
    except Exception as e:
        logging.error(f"_update_config_env fallito: {e}")

async def _update_config_env(key: str, value: str):
    await asyncio.to_thread(_update_config_env_sync, key, value)

@app.get("/api/wifi/status")
async def wifi_status():
    try:
        r = await asyncio.to_thread(
            subprocess.run,
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"],
            capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.strip().split('\n'):
            if ':wifi:' in line:
                parts = line.split(':')
                return {"device": parts[0], "state": parts[2], "connection": parts[3] if len(parts) > 3 else ""}
        return {"device": None, "state": "unavailable", "connection": ""}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/wifi/scan")
async def wifi_scan():
    try:
        r = await asyncio.to_thread(
            subprocess.run,
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"],
            capture_output=True, text=True, timeout=15
        )
        networks, seen = [], set()
        for line in r.stdout.strip().split('\n'):
            if not line: continue
            parts = line.split(':')
            ssid = parts[0]
            if ssid and ssid not in seen:
                seen.add(ssid)
                networks.append({
                    "ssid": ssid,
                    "signal": parts[1] if len(parts) > 1 else "",
                    "security": parts[2] if len(parts) > 2 else ""
                })
        return networks
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/wifi/connect")
async def wifi_connect(payload: dict):
    ssid       = str(payload.get("ssid",     "")).strip()
    password   = str(payload.get("password", "")).strip()
    use_dhcp   = payload.get("use_dhcp", True)
    ip_address = str(payload.get("ip_address", "")).strip()
    gateway    = str(payload.get("gateway", "")).strip()
    dns        = str(payload.get("dns", "")).strip()
    if not ssid:
        return JSONResponse({"ok": False, "error": "SSID mancante"}, status_code=400)
    try:
        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return JSONResponse({"ok": False, "error": r.stderr.strip() or r.stdout.strip()}, status_code=500)
        # Static IP configuration
        if not use_dhcp and ip_address:
            conn_name = ssid
            cmds = [
                ["nmcli", "con", "mod", conn_name, "ipv4.method", "manual",
                 "ipv4.addresses", ip_address + "/24"],
            ]
            if gateway:
                cmds.append(["nmcli", "con", "mod", conn_name, "ipv4.gateway", gateway])
            if dns:
                cmds.append(["nmcli", "con", "mod", conn_name, "ipv4.dns", dns])
            cmds.append(["nmcli", "con", "up", conn_name])
            for c in cmds:
                await asyncio.to_thread(subprocess.run, c, capture_output=True, text=True, timeout=15)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# --- YAY-115: Saved WiFi networks ---

@app.get("/api/wifi/networks")
async def wifi_networks_list():
    networks = await database.get_wifi_networks(_conn)
    # Mask passwords: show only first 2 chars + ****
    for n in networks:
        pw = n.get("password", "")
        n["password"] = pw[:2] + "****" if len(pw) >= 2 else "****"
    return JSONResponse({"networks": networks})

@app.post("/api/wifi/networks")
async def wifi_networks_save(payload: dict):
    ssid = str(payload.get("ssid", "")).strip()
    if not ssid:
        return JSONResponse({"ok": False, "error": "SSID mancante"}, status_code=400)
    password   = str(payload.get("password", "")).strip()
    use_dhcp   = payload.get("use_dhcp", True)
    ip_address = str(payload.get("ip_address", "")).strip() or None
    gateway    = str(payload.get("gateway", "")).strip() or None
    dns        = str(payload.get("dns", "")).strip() or None
    net_id = await database.save_wifi_network(
        _conn, ssid, password, use_dhcp, ip_address, gateway, dns
    )
    return JSONResponse({"ok": True, "id": net_id})

@app.delete("/api/wifi/networks/{network_id}")
async def wifi_networks_delete(network_id: int):
    await database.delete_wifi_network(_conn, network_id)
    return JSONResponse({"ok": True})

@app.get("/api/keys")
async def api_keys():
    """Return local node key info."""
    return meshtastic_client.get_keys_info()

@app.get("/api/keys/{node_id}")
async def api_node_key(node_id: str):
    """Return public key of a specific node."""
    key = meshtastic_client.get_node_public_key(node_id)
    return {"node_id": node_id, "public_key": key}

@app.get("/api/channels")
async def get_channels():
    import base64
    iface = meshtastic_client._interface
    if not iface:
        return []
    try:
        channels = await asyncio.to_thread(iface.localNode.getChannels)
        result = []
        for ch in channels:
            psk_b64 = base64.b64encode(bytes(ch.settings.psk)).decode() if ch.settings.psk else ""
            result.append({"index": ch.index, "name": ch.settings.name or "", "psk": psk_b64, "role": ch.role})
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/channels/{index}")
async def set_channel_psk(index: int, payload: dict):
    import base64
    iface = meshtastic_client._interface
    if not iface:
        return JSONResponse({"ok": False, "error": "Non connesso"}, status_code=503)
    try:
        psk_b64 = payload.get("psk", "").strip()
        psk     = base64.b64decode(psk_b64) if psk_b64 else None
        channels = await asyncio.to_thread(iface.localNode.getChannels)
        ch = next((c for c in channels if c.index == index), None)
        if ch is None:
            return JSONResponse({"ok": False, "error": "Canale non trovato"}, status_code=404)
        if psk is not None:
            ch.settings.psk = psk
            await asyncio.to_thread(iface.localNode.writeChannel, index)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# --- System power ---

@app.post("/api/system/reboot")
async def system_reboot():
    try:
        await database.sync_to_sd(_conn)
        subprocess.Popen(["sudo", "reboot"])
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/api/system/shutdown")
async def system_shutdown():
    try:
        await database.sync_to_sd(_conn)
        subprocess.Popen(["sudo", "shutdown", "-h", "now"])
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# --- WebSocket ---

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        init_nodes = await database.get_nodes(_conn)
        await _enrich_nodes_hop_count(init_nodes)
        await websocket.send_json({
            "type": "init",
            "data": {
                "connected": meshtastic_client.is_connected(),
                "nodes":     init_nodes,
                "messages":  await database.get_messages(_conn, 0, 50),
                "theme":     cfg.UI_THEME,
            }
        })
        while True:
            await asyncio.wait_for(websocket.receive_text(), timeout=30)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        pass
    except Exception as e:
        logging.debug(f"WS disconnesso: {e}")
    finally:
        ws_clients.discard(websocket)
