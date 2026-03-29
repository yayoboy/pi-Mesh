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

from routers import nodes, map_router, log_router, placeholders


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init(cfg.DB_PATH)
    asyncio.create_task(meshtasticd_client.connect())
    yield
    await meshtasticd_client.disconnect()


app = FastAPI(lifespan=lifespan)

app.mount('/static', StaticFiles(directory='static'), name='static')

app.include_router(nodes.router)
app.include_router(map_router.router)
app.include_router(log_router.router)
app.include_router(placeholders.router)


@app.get('/')
async def root():
    return RedirectResponse(url='/nodes')
