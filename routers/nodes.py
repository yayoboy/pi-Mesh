"""Pagina e API dei nodi mesh.

  GET    /nodes                — pagina HTML (templates/nodes.html)
  GET    /api/nodes            — lista nodi dalla cache del client
  DELETE /api/nodes/{node_id}  — dimentica un nodo (con ?purge=1 elimina
                                 anche messaggi e telemetria associati)
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import meshtasticd_client
import config as cfg
import database
from templating import templates

router = APIRouter()


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


@router.post('/api/nodes/{node_id}/favorite')
async def set_favorite(node_id: str, on: bool = True):
    """Marca (?on=true, default) o smarca (?on=false) un nodo come preferito."""
    try:
        await meshtasticd_client.set_node_favorite(node_id, on)
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


@router.post('/api/nodes/{node_id}/ignore')
async def set_ignored(node_id: str, on: bool = True):
    """Ignora (?on=true, default) o de-ignora (?on=false) un nodo."""
    try:
        await meshtasticd_client.set_node_ignored(node_id, on)
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)
