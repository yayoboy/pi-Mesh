import asyncio, gc, glob as _glob, json as _json, logging, os, re, signal, subprocess, sys, time
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
_conn = None
_keyboard_proc = None

def get_conn():
    return _conn

async def broadcast(data: dict):
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    ws_clients -= dead

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

    gpio_handler.init(
        (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        broadcast,
        db_conn=_conn
    )

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

@app.middleware("http")
async def setup_redirect(request: Request, call_next):
    if not cfg.SETUP_DONE:
        path = request.url.path
        skip = path.startswith(("/setup", "/api/", "/static/", "/ws", "/tiles/"))
        if not skip:
            return RedirectResponse("/setup")
    return await call_next(request)

# Static files — crea le directory se non esistono
for d in ["static", "static/tiles", "templates"]:
    os.makedirs(d, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/tiles",  StaticFiles(directory="static/tiles"), name="tiles")
templates = Jinja2Templates(directory="templates")

# --- Route pagine ---

@app.get("/")
async def root():
    return RedirectResponse("/home")

@app.get("/map")
async def map_page(request: Request):
    return templates.TemplateResponse(request, "map.html", _base_ctx({
        "bounds":   cfg.MAP_BOUNDS,
        "zoom_min": cfg.MAP_ZOOM_MIN,
        "zoom_max": cfg.MAP_ZOOM_MAX,
        "active":   "map",
    }))

@app.get("/settings")
async def settings_page(request: Request):
    node_info = meshtastic_client.get_local_node()
    return templates.TemplateResponse(request, "settings.html", _base_ctx({
        "node":             node_info,
        "active":           "settings",
        "enc1":             (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        "enc2":             (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        "i2c_sensors":      cfg.I2C_SENSORS,
        "display_rotation": cfg.DISPLAY_ROTATION,
    }))


@app.get("/home")
async def home_page(request: Request):
    nodes    = await database.get_nodes(_conn)
    node_info = meshtastic_client.get_local_node()
    return templates.TemplateResponse(request, "home.html", _base_ctx({
        "nodes": nodes, "node": node_info,
        "active": "home", "now": int(time.time()),
    }))

@app.get("/channels")
async def channels_page(request: Request):
    msgs  = await database.get_messages(_conn, channel=0, limit=50)
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse(request, "channels.html", _base_ctx({
        "messages": msgs, "nodes": nodes,
        "active": "channels",
    }))

@app.get("/hardware")
async def hardware_page(request: Request):
    sensors = getattr(app.state, "i2c_sensors", [])
    return templates.TemplateResponse(request, "hardware.html", _base_ctx({
        "i2c_sensors": sensors,
        "enc1": (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        "enc2": (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        "active": "hardware",
    }))

@app.get("/remote")
async def remote_page(request: Request):
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse(request, "remote.html", _base_ctx({
        "nodes": nodes,
        "active": "remote", "now": int(time.time()),
    }))

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
        await database.save_message(_conn, "local", channel, text, int(time.time()), 1, None, None)
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
    return await database.get_nodes(_conn)

@app.get("/api/messages")
async def api_messages(channel: int = 0, limit: int = 50, before_id: int = None):
    return await database.get_messages(_conn, channel, limit, before_id)

@app.get("/api/telemetry/{node_id}/{type_}")
async def api_telemetry(node_id: str, type_: str, limit: int = 100):
    return await database.get_telemetry(_conn, node_id, type_, limit)

@app.get("/api/sensor/{sensor_name}")
async def api_sensor(sensor_name: str, limit: int = 100):
    return await database.get_sensor_readings(_conn, sensor_name, limit)

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
    if source not in ("osm", "topo", "sat"):
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
    _valid_theme_ids = {"dark", "light", "hc"} | {t["id"] for t in _load_themes()}
    if theme not in _valid_theme_ids:
        return JSONResponse({"ok": False, "error": "tema non trovato"}, status_code=400)
    _update_config_env("UI_THEME", theme)
    cfg.UI_THEME = theme
    return {"ok": True}

_ALLOWED_REMOTE_CONFIG_SECTIONS = {"device", "display", "network", "telemetry", "lora", "bluetooth", "position"}

@app.post("/api/remote-config")
async def remote_config(payload: dict):
    node_id = payload.pop("remote_node_id", None)
    if not node_id:
        return JSONResponse({"ok": False, "error": "node_id mancante"}, status_code=400)
    try:
        node = meshtastic_client._interface.getNode(node_id)
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
            _update_config_env("ENC1_A",  str(pins[0]))
            _update_config_env("ENC1_B",  str(pins[1]))
            _update_config_env("ENC1_SW", str(pins[2]))
        if "enc2_pins" in payload:
            pins = [int(p.strip()) for p in payload["enc2_pins"].split(",")]
            _update_config_env("ENC2_A",  str(pins[0]))
            _update_config_env("ENC2_B",  str(pins[1]))
            _update_config_env("ENC2_SW", str(pins[2]))
        if "i2c_sensors" in payload:
            _update_config_env("I2C_SENSORS", payload["i2c_sensors"])
        if "display_rotation" in payload:
            _update_config_env("DISPLAY_ROTATION", str(payload["display_rotation"]))
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

_ALLOWED_UI_SETTINGS = {"UI_STATUS_DENSITY", "UI_CHANNEL_LAYOUT", "UI_ORIENTATION", "UI_THEME"}

@app.post("/settings/ui")
async def apply_ui_settings(payload: dict):
    updated = {}
    for key, val in payload.items():
        if key not in _ALLOWED_UI_SETTINGS:
            continue
        val = str(val).strip()
        _update_config_env(key, val)
        setattr(cfg, key, val)
        updated[key] = val
    return {"ok": True, "updated": updated}

@app.get("/api/tile/cache/info")
async def tile_cache_info():
    import pathlib
    tiles_dir = pathlib.Path("static/tiles")
    total = sum(f.stat().st_size for f in tiles_dir.rglob("*") if f.is_file())
    return {"size_bytes": total, "size_mb": round(total / 1024 / 1024, 1)}

@app.post("/api/tile/cache/clear")
async def tile_cache_clear():
    import pathlib, shutil
    tiles_dir = pathlib.Path("static/tiles")
    for item in tiles_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        elif item.suffix == ".mbtiles":
            item.unlink()
    return {"ok": True}

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

@app.get("/messages")
async def legacy_messages(): return RedirectResponse("/channels")

@app.get("/nodes")
async def legacy_nodes(): return RedirectResponse("/home")

@app.get("/telemetry")
async def legacy_telemetry(): return RedirectResponse("/hardware")

@app.get("/setup")
async def setup_page(request: Request):
    return templates.TemplateResponse(request, "setup.html", _base_ctx())


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
    if not _valid_port(port):
        return JSONResponse({"ok": False, "error": "porta non valida"}, status_code=400)
    try:
        node = await asyncio.to_thread(_read_node_info, port)
        return {"ok": True, "node": node}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


_PORT_RE = re.compile(r'^(/dev/tty[A-Za-z0-9]+|/dev/serial/by-id/[\w\-:.@]+)$')

def _valid_port(port: str) -> bool:
    return bool(_PORT_RE.match(port))


THEMES_PATH = "static/themes.json"
FONTS_PATH  = "static/fonts"

_BUILTIN_THEMES = [
    {"id": "dark",  "name": "Scuro",         "builtin": True},
    {"id": "light", "name": "Chiaro",         "builtin": True},
    {"id": "hc",    "name": "Alto contrasto", "builtin": True},
]

_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_ID_RE    = re.compile(r'^[a-z0-9-]{1,32}$')
_SYSTEM_FONTS = ["system-ui", "monospace", "Georgia", '"Courier New"']


def _load_themes() -> list:
    try:
        with open(THEMES_PATH) as f:
            return _json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.error(f"_load_themes: {e}")
        return []


def _save_themes(themes: list) -> None:
    import os
    os.makedirs(os.path.dirname(THEMES_PATH) or ".", exist_ok=True)
    with open(THEMES_PATH, "w") as f:
        _json.dump(themes, f, indent=2)


def _get_custom_theme(theme_id: str) -> dict | None:
    """Returns the custom theme dict if found, None if built-in or not found."""
    if theme_id in ("dark", "light", "hc"):
        return None
    for t in _load_themes():
        if t["id"] == theme_id:
            return t
    return None


def _base_ctx(extra: dict = None) -> dict:
    """Shared context for all templates: theme, font, custom theme injection."""
    ct = _get_custom_theme(cfg.UI_THEME)
    cf = {}
    for p in sorted(_glob.glob(f"{FONTS_PATH}/*.ttf") + _glob.glob(f"{FONTS_PATH}/*.woff2")):
        name = os.path.splitext(os.path.basename(p))[0]
        cf[name] = os.path.basename(p)
    ctx = {
        "theme":          cfg.UI_THEME,
        "density":        cfg.UI_STATUS_DENSITY,
        "orientation":    cfg.UI_ORIENTATION,
        "channel_layout": cfg.UI_CHANNEL_LAYOUT,
        "custom_theme":   ct,
        "custom_fonts":   cf,
    }
    if extra:
        ctx.update(extra)
    return ctx


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
    serial_port = str(payload.get("serial_port", cfg.SERIAL_PORT)).strip()
    if serial_port and not _valid_port(serial_port):
        return JSONResponse({"ok": False, "error": "porta seriale non valida"}, status_code=400)
    fields = {
        "SERIAL_PORT": serial_port,
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


@app.get("/api/themes")
async def list_themes():
    custom = _load_themes()
    return {"themes": _BUILTIN_THEMES + [dict(t, builtin=False) for t in custom]}


_REQUIRED_VARS = {"--bg","--bg2","--bg3","--border","--text","--text2",
                  "--accent","--ok","--warn","--danger"}


@app.post("/api/themes")
async def save_theme(payload: dict):
    theme_id = str(payload.get("id", "")).strip().lower()
    if not _ID_RE.match(theme_id):
        return JSONResponse({"ok": False, "error": "id non valido"}, status_code=400)
    if theme_id in ("dark", "light", "hc"):
        return JSONResponse({"ok": False, "error": "id riservato"}, status_code=400)
    name = str(payload.get("name", theme_id))[:40]
    font = str(payload.get("font", "system-ui"))
    allowed_fonts = set(_SYSTEM_FONTS)
    for p in _glob.glob(f"{FONTS_PATH}/*.ttf") + _glob.glob(f"{FONTS_PATH}/*.woff2"):
        allowed_fonts.add(os.path.splitext(os.path.basename(p))[0])
    if font not in allowed_fonts:
        return JSONResponse({"ok": False, "error": "font non valido"}, status_code=400)
    vars_raw = payload.get("vars", {})
    if not isinstance(vars_raw, dict) or not _REQUIRED_VARS.issubset(vars_raw.keys()):
        return JSONResponse({"ok": False, "error": "vars incompleto"}, status_code=400)
    for k, v in vars_raw.items():
        if k not in _REQUIRED_VARS:
            return JSONResponse({"ok": False, "error": f"variabile sconosciuta: {k}"}, status_code=400)
        if not _COLOR_RE.match(str(v)):
            return JSONResponse({"ok": False, "error": f"colore non valido: {k}={v}"}, status_code=400)
    themes = [t for t in _load_themes() if t["id"] != theme_id]
    themes.append({"id": theme_id, "name": name, "font": font, "vars": vars_raw})
    _save_themes(themes)
    return {"ok": True}


@app.get("/api/themes/fonts")
async def list_fonts():
    custom = []
    for p in sorted(_glob.glob(f"{FONTS_PATH}/*.ttf") + _glob.glob(f"{FONTS_PATH}/*.woff2")):
        name = os.path.splitext(os.path.basename(p))[0]
        ext  = os.path.splitext(p)[1].lstrip(".")
        custom.append({"name": name, "file": os.path.basename(p), "format": ext})
    return {"system_fonts": _SYSTEM_FONTS, "custom_fonts": custom}


@app.delete("/api/themes/{theme_id}")
async def delete_theme(theme_id: str):
    if theme_id in ("dark", "light", "hc"):
        return JSONResponse({"ok": False, "error": "tema built-in non eliminabile"}, status_code=400)
    themes = [t for t in _load_themes() if t["id"] != theme_id]
    _save_themes(themes)
    return {"ok": True}


def _update_config_env(key: str, value: str):
    env_path = "config.env"
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

# --- WebSocket ---

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "init",
            "data": {
                "connected": meshtastic_client.is_connected(),
                "nodes":     await database.get_nodes(_conn),
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
