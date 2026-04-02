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
