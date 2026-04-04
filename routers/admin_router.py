# routers/admin_router.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import meshtasticd_client

router = APIRouter()


def _check_connected():
    if not meshtasticd_client.is_connected():
        raise HTTPException(503, detail='board not connected')


@router.post('/api/admin/{node_id}/request-position')
async def admin_request_position(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'request_position')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)


@router.post('/api/admin/{node_id}/request-telemetry')
async def admin_request_telemetry(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'request_telemetry')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)


@router.post('/api/admin/{node_id}/reboot')
async def admin_reboot(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'reboot')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)


@router.post('/api/admin/{node_id}/factory-reset')
async def admin_factory_reset(node_id: str):
    _check_connected()
    try:
        await meshtasticd_client.send_admin(node_id, 'factory_reset')
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=400)
