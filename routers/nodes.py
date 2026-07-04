"""Pagina e API dei nodi mesh.

  GET    /nodes                — pagina HTML (templates/nodes.html)
  GET    /api/nodes            — lista nodi dalla cache del client
  DELETE /api/nodes/{node_id}  — dimentica un nodo (con ?purge=1 elimina
                                 anche messaggi e telemetria associati)
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import meshtasticd_client
import config as cfg
import database

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/nodes', response_class=HTMLResponse)
async def nodes_page(request: Request):
    return templates.TemplateResponse(request, 'nodes.html', {
        'active_tab': 'nodes'
    })


@router.get('/api/nodes')
async def api_nodes():
    return meshtasticd_client.get_nodes()


@router.delete('/api/nodes/{node_id}')
async def delete_node(node_id: str, purge: bool = False):
    await database.delete_node(cfg.DB_PATH, node_id, purge=purge)
    return {'ok': True}
