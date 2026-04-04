# routers/canned_router.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import database

router = APIRouter()


class CannedMessageCreate(BaseModel):
    text: str
    sort_order: int = 0


class CannedMessageUpdate(BaseModel):
    text: str
    sort_order: int = 0


@router.get('/api/canned-messages')
async def get_canned_messages():
    return await database.get_canned_messages()


@router.post('/api/canned-messages', status_code=201)
async def add_canned_message(body: CannedMessageCreate):
    if not body.text.strip():
        raise HTTPException(400, detail='text cannot be empty')
    msg_id = await database.add_canned_message(body.text.strip(), body.sort_order)
    return {'id': msg_id, 'text': body.text.strip(), 'sort_order': body.sort_order}


@router.put('/api/canned-messages/{msg_id}')
async def update_canned_message(msg_id: int, body: CannedMessageUpdate):
    if not body.text.strip():
        raise HTTPException(400, detail='text cannot be empty')
    await database.update_canned_message(msg_id, body.text.strip(), body.sort_order)
    return {'ok': True}


@router.delete('/api/canned-messages/{msg_id}')
async def delete_canned_message(msg_id: int):
    await database.delete_canned_message(msg_id)
    return {'ok': True}
