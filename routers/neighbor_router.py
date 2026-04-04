# routers/neighbor_router.py
from fastapi import APIRouter
import database

router = APIRouter()


@router.get('/api/neighbor-info')
async def get_neighbor_info():
    return await database.get_neighbor_info()
