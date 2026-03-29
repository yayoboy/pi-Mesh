# routers/commands.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import meshtasticd_client

router = APIRouter()


class SendTextRequest(BaseModel):
    text: str
    to: str
    channel: int = 0


@router.post('/api/nodes/{node_id}/traceroute')
async def post_traceroute(node_id: str):
    if not meshtasticd_client.is_connected():
        raise HTTPException(503, detail='board not connected')
    await meshtasticd_client.request_traceroute(node_id)
    return {'status': 'requested'}


@router.get('/api/nodes/{node_id}/traceroute')
async def get_traceroute(node_id: str):
    result = meshtasticd_client.get_traceroute_result(node_id)
    if result is None:
        raise HTTPException(404, detail='no traceroute result')
    return result


@router.post('/api/nodes/{node_id}/request-position')
async def post_request_position(node_id: str):
    if not meshtasticd_client.is_connected():
        raise HTTPException(503, detail='board not connected')
    await meshtasticd_client.request_position(node_id)
    return {'status': 'requested'}


@router.post('/api/messages/send')
async def post_send_text(body: SendTextRequest):
    if not meshtasticd_client.is_connected():
        raise HTTPException(503, detail='board not connected')
    await meshtasticd_client.send_text(body.text, body.to, body.channel)
    return {'status': 'sent'}


@router.get('/api/nodes/{node_id}')
async def get_node(node_id: str):
    nodes = meshtasticd_client.get_nodes()
    for n in nodes:
        if n['id'] == node_id:
            return n
    raise HTTPException(404, detail='node not found')
