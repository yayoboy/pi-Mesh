# routers/nodes.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/nodes', response_class=HTMLResponse)
async def nodes_page(request: Request):
    return templates.TemplateResponse('nodes.html', {
        'request': request, 'active_tab': 'nodes'
    })


@router.get('/api/nodes')
async def api_nodes():
    return meshtasticd_client.get_nodes()
