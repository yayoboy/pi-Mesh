# main.py
import asyncio
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config as cfg
import database
import meshtasticd_client
import mqtt_bridge
import rpi_telemetry

logging.basicConfig(level=getattr(logging, cfg.LOG_LEVEL, logging.WARNING))

from routers import nodes, map_router, log_router, commands, ws_router, messages_router, config_router, metrics_router, canned_router, module_config_router, waypoints_router, neighbor_router, admin_router


async def _broadcast_task() -> None:
    """Read events from meshtasticd_client event queue and broadcast to all WS clients."""
    queue = meshtasticd_client.get_event_queue()
    while True:
        try:
            event = await queue.get()
            await ws_router.manager.broadcast(event)
        except Exception as e:
            logging.getLogger(__name__).warning(f'Broadcast task error: {e}')
            await asyncio.sleep(0.1)


async def _rpi_telemetry_task() -> None:
    """Collect RPi system metrics every 10s and broadcast via WS."""
    while True:
        try:
            data = rpi_telemetry.collect()
            await ws_router.manager.broadcast({'type': 'rpi_telemetry', 'data': data})
        except Exception as e:
            logging.getLogger(__name__).warning(f'RPi telemetry error: {e}')
        await asyncio.sleep(10)


async def _telemetry_cleanup_task() -> None:
    """Clean up old telemetry data daily (keep 7 days)."""
    while True:
        await asyncio.sleep(86400)
        try:
            await database.cleanup_telemetry(cfg.DB_PATH, max_age_hours=168)
        except Exception as e:
            logging.getLogger(__name__).warning(f'Telemetry cleanup error: {e}')


async def _mqtt_ws_dispatch(event_type: str, data: dict):
    """Forward MQTT events to all connected WebSocket clients."""
    await ws_router.manager.broadcast({'type': event_type, **data})


async def _apply_saved_brightness() -> None:
    import subprocess
    import os
    script = os.path.join(os.path.dirname(__file__), 'scripts', 'backlight.sh')
    val = await database.get_setting('display.brightness', '255')
    try:
        await asyncio.to_thread(
            subprocess.run,
            ['bash', script, str(val)],
            capture_output=True, text=True, timeout=5
        )
    except Exception as e:
        logging.getLogger(__name__).warning(f'Backlight restore error: {e}')


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init(cfg.DB_PATH)
    await database.cleanup_old_messages(cfg.DB_PATH, days=30)
    await _apply_saved_brightness()
    await meshtasticd_client.load_nodes_from_db()    # populate cache from DB before board connects
    _tasks = [
        asyncio.create_task(meshtasticd_client.connect()),
        asyncio.create_task(_broadcast_task()),
        asyncio.create_task(_rpi_telemetry_task()),
        asyncio.create_task(_telemetry_cleanup_task()),
    ]
    # Start MQTT bridge if configured
    mqtt_cfg = await meshtasticd_client.get_mqtt_config(cfg.DB_PATH)
    if mqtt_cfg.get('enabled'):
        mqtt_bridge.set_ws_dispatch(_mqtt_ws_dispatch)
        _tasks.append(asyncio.create_task(mqtt_bridge.start(mqtt_cfg)))
    yield
    for t in _tasks:
        t.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    await mqtt_bridge.stop()
    await meshtasticd_client.disconnect()
    await database.close()


app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory='templates')
templates.env.globals['map_local_tiles'] = '1' if cfg.MAP_LOCAL_TILES else '0'

app.mount('/static', StaticFiles(directory='static'), name='static')

app.include_router(nodes.router)
app.include_router(map_router.router)
app.include_router(log_router.router)
app.include_router(messages_router.router)
app.include_router(config_router.router)
app.include_router(metrics_router.router)
app.include_router(commands.router)
app.include_router(ws_router.router)
app.include_router(canned_router.router)
app.include_router(module_config_router.router)
app.include_router(waypoints_router.router)
app.include_router(neighbor_router.router)
app.include_router(admin_router.router)


@app.get('/')
async def root():
    return RedirectResponse(url='/nodes')
