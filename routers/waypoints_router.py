# routers/waypoints_router.py
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import database
import meshtasticd_client

router = APIRouter()


@router.get('/api/waypoints')
async def get_waypoints():
    return await database.get_waypoints(active_only=True)


@router.delete('/api/waypoints/{wp_id}')
async def delete_waypoint(wp_id: int):
    await database.delete_waypoint(wp_id)
    return {'ok': True}


class WaypointSend(BaseModel):
    name: str
    lat: float
    lon: float
    icon: str = 'default'
    description: str = ''
    expire_hours: int = 24


@router.post('/api/waypoints/send')
async def send_waypoint(body: WaypointSend):
    if not meshtasticd_client.is_connected():
        raise HTTPException(503, detail='board not connected')
    expire_ts = int(time.time()) + body.expire_hours * 3600 if body.expire_hours > 0 else 0
    await meshtasticd_client.send_waypoint(
        name=body.name, lat=body.lat, lon=body.lon,
        icon=body.icon, description=body.description, expire=expire_ts,
    )
    return {'ok': True}
