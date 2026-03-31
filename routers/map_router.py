# routers/map_router.py
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import meshtasticd_client
import database
import config as cfg

router = APIRouter()
templates = Jinja2Templates(directory='templates')


class MarkerCreate(BaseModel):
    label: str
    icon_type: str = 'poi'
    latitude: float
    longitude: float


@router.get('/map', response_class=HTMLResponse)
async def map_page(request: Request):
    nodes = meshtasticd_client.get_nodes()
    bounds = cfg.REGION_BOUNDS.get(cfg.MAP_REGION, cfg.REGION_BOUNDS['italia'])
    return templates.TemplateResponse(request, 'map.html', {
        'active_tab': 'map',
        'bounds':     bounds,
        'zoom_min':   7,
        'zoom_max':   16,
        'nodes_data': nodes,
    })


@router.get('/api/map/nodes')
async def api_map_nodes():
    return meshtasticd_client.get_nodes()


@router.get('/api/map/markers')
async def get_markers():
    markers = await database.get_markers(cfg.DB_PATH)
    return {'markers': markers}


@router.post('/api/map/markers')
async def create_marker(body: MarkerCreate):
    marker = await database.create_marker(
        cfg.DB_PATH, body.label, body.icon_type, body.latitude, body.longitude
    )
    return marker


@router.delete('/api/map/markers/{marker_id}')
async def delete_marker(marker_id: int):
    deleted = await database.delete_marker(cfg.DB_PATH, marker_id)
    if not deleted:
        raise HTTPException(404, detail='marker not found')
    return {'status': 'deleted'}
