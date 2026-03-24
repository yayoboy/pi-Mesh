import asyncio, gc, logging, os, re, signal, subprocess, sys, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config as cfg
import database, meshtastic_client, gpio_handler, sensor_handler, watchdog

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

    drivers = sensor_handler.init(cfg.I2C_SENSORS)
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

# Static files — crea le directory se non esistono
for d in ["static", "static/tiles", "templates"]:
    os.makedirs(d, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/tiles",  StaticFiles(directory="static/tiles"), name="tiles")
templates = Jinja2Templates(directory="templates")

# --- Route pagine ---

@app.get("/")
async def root():
    return RedirectResponse("/messages")

@app.get("/messages")
async def messages_page(request: Request):
    msgs = await database.get_messages(_conn, channel=0, limit=50)
    return templates.TemplateResponse("messages.html", {
        "request": request, "messages": msgs,
        "theme": cfg.UI_THEME, "active": "messages"
    })

@app.get("/nodes")
async def nodes_page(request: Request):
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse("nodes.html", {
        "request": request, "nodes": nodes,
        "theme": cfg.UI_THEME, "active": "nodes"
    })

@app.get("/map")
async def map_page(request: Request):
    return templates.TemplateResponse("map.html", {
        "request": request,
        "bounds":   cfg.MAP_BOUNDS,
        "zoom_min": cfg.MAP_ZOOM_MIN,
        "zoom_max": cfg.MAP_ZOOM_MAX,
        "theme":    cfg.UI_THEME,
        "active":   "map"
    })

@app.get("/telemetry")
async def telemetry_page(request: Request):
    nodes = await database.get_nodes(_conn)
    return templates.TemplateResponse("telemetry.html", {
        "request": request, "nodes": nodes,
        "theme": cfg.UI_THEME, "active": "telemetry"
    })

@app.get("/settings")
async def settings_page(request: Request):
    node_info = meshtastic_client.get_local_node()
    return templates.TemplateResponse("settings.html", {
        "request":          request,
        "node":             node_info,
        "theme":            cfg.UI_THEME,
        "active":           "settings",
        "enc1":             (cfg.ENC1_A, cfg.ENC1_B, cfg.ENC1_SW),
        "enc2":             (cfg.ENC2_A, cfg.ENC2_B, cfg.ENC2_SW),
        "i2c_sensors":      cfg.I2C_SENSORS,
        "display_rotation": cfg.DISPLAY_ROTATION,
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

@app.get("/api/status")
async def api_status():
    import resource
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return {
        "connected":  meshtastic_client.is_connected(),
        "node_count": len(await database.get_nodes(_conn)),
        "ram_mb":     round(rss_mb, 1),
    }

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
    if theme not in ("dark", "light", "hc"):
        return JSONResponse({"ok": False}, status_code=400)
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
