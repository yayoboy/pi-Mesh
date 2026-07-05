"""Admin remoto via mesh (richiede firmware con PKC o canale admin).

  POST /api/admin/{id}/request-position   — chiede la posizione
  POST /api/admin/{id}/request-telemetry  — chiede la telemetria
  POST /api/admin/{id}/reboot             — riavvia il nodo remoto
  POST /api/admin/{id}/factory-reset      — reset di fabbrica (distruttivo)
"""
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


# ─── Config remota: leggi/scrivi le sezioni config di un nodo via mesh ──

# Sezioni ammesse (protobuf LocalConfig + ModuleConfig)
_REMOTE_SECTIONS = frozenset({
    'device', 'position', 'power', 'network', 'display', 'lora', 'bluetooth',
    'security', 'mqtt', 'serial', 'external_notification', 'store_forward',
    'range_test', 'telemetry', 'canned_message', 'audio', 'remote_hardware',
    'neighbor_info', 'ambient_lighting', 'detection_sensor', 'paxcounter',
})


@router.get('/api/admin/{node_id}/config/{section}')
async def get_remote_config(node_id: str, section: str):
    """Legge una sezione config dal nodo remoto (roundtrip mesh: lento)."""
    if section not in _REMOTE_SECTIONS:
        raise HTTPException(status_code=400, detail=f'sezione sconosciuta: {section}')
    try:
        data = await meshtasticd_client.get_remote_config(node_id, section)
        data['cached'] = False
        return data
    except TimeoutError:
        return JSONResponse({'error': 'timeout: il nodo non ha risposto'}, status_code=504)
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


@router.post('/api/admin/{node_id}/config/{section}')
async def set_remote_config(node_id: str, section: str, body: dict):
    """Scrive una sezione config sul nodo remoto (rilegge, applica, riscrive)."""
    if section not in _REMOTE_SECTIONS:
        raise HTTPException(status_code=400, detail=f'sezione sconosciuta: {section}')
    body.pop('cached', None)
    try:
        await meshtasticd_client.set_remote_config(node_id, section, body)
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)
