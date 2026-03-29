# routers/map_router.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')

DEFAULT_BOUNDS = {
    'lat_min': 35.0, 'lat_max': 47.5,
    'lon_min': 6.5,  'lon_max': 18.5,
}


@router.get('/map', response_class=HTMLResponse)
async def map_page(request: Request):
    nodes = meshtasticd_client.get_nodes()
    return templates.TemplateResponse(request, 'map.html', {
        'active_tab': 'map',
        'bounds':     DEFAULT_BOUNDS,
        'zoom_min':   7,
        'zoom_max':   16,
        'nodes_data': nodes,
    })


@router.get('/api/map/nodes')
async def api_map_nodes():
    return meshtasticd_client.get_nodes()
