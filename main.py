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

logging.basicConfig(level=getattr(logging, cfg.LOG_LEVEL, logging.WARNING))

from routers import nodes, map_router, log_router, placeholders, commands, ws_router, messages_router, config_router


async def _broadcast_task() -> None:
    """Read events from meshtasticd_client event queue and broadcast to all WS clients."""
    queue = meshtasticd_client.get_event_queue()
    while True:
        try:
            event = queue.get_nowait()
            await ws_router.manager.broadcast(event)
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.getLogger(__name__).warning(f'Broadcast task error: {e}')
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init(cfg.DB_PATH)
    await database.cleanup_old_messages(cfg.DB_PATH, days=30)
    await meshtasticd_client.load_nodes_from_db()    # populate cache from DB before board connects
    asyncio.create_task(meshtasticd_client.connect())
    asyncio.create_task(_broadcast_task())
    yield
    await meshtasticd_client.disconnect()


app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory='templates')
templates.env.globals['map_local_tiles'] = '1' if cfg.MAP_LOCAL_TILES else '0'

app.mount('/static', StaticFiles(directory='static'), name='static')

app.include_router(nodes.router)
app.include_router(map_router.router)
app.include_router(log_router.router)
app.include_router(messages_router.router)
app.include_router(config_router.router)
app.include_router(placeholders.router)
app.include_router(commands.router)
app.include_router(ws_router.router)


@app.get('/')
async def root():
    return RedirectResponse(url='/nodes')
