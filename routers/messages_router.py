# routers/messages_router.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config as cfg
import database
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/messages', response_class=HTMLResponse)
async def messages_page(request: Request):
    nodes = meshtasticd_client.get_nodes()
    local_id = meshtasticd_client._local_id
    messages = await database.get_messages(cfg.DB_PATH, channel=0, limit=50)
    dm_threads = await database.get_dm_threads(cfg.DB_PATH, local_id)
    return templates.TemplateResponse(request, 'messages.html', {
        'active_tab': 'messages',
        'nodes': nodes,
        'messages': messages,
        'dm_threads': dm_threads,
    })


@router.get('/api/messages')
async def get_messages(channel: int = 0, limit: int = 50, before_id: int | None = None):
    return await database.get_messages(cfg.DB_PATH, channel=channel,
                                       limit=limit, before_id=before_id)


@router.delete('/api/messages')
async def delete_messages():
    await database.clear_messages(cfg.DB_PATH)
    return {'ok': True}


@router.get('/api/dm/threads')
async def get_dm_threads():
    local_id = meshtasticd_client._local_id
    return await database.get_dm_threads(cfg.DB_PATH, local_id)


@router.get('/api/dm/messages')
async def get_dm_messages(peer: str, limit: int = 50, before_id: int | None = None):
    local_id = meshtasticd_client._local_id
    return await database.get_dm_messages(cfg.DB_PATH, peer_id=peer,
                                          local_id=local_id, limit=limit,
                                          before_id=before_id)


class MarkReadRequest(BaseModel):
    peer_id: str


@router.post('/api/dm/read')
async def mark_dm_read(body: MarkReadRequest):
    await database.mark_dm_read(cfg.DB_PATH, body.peer_id)
    return {'ok': True}
