# routers/commands.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import meshtasticd_client
import database
import config as cfg
import time
import os
import re
import asyncio as _asyncio
import subprocess
import usb_storage

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
    local_id = meshtasticd_client._local_id or '!local'
    try:
        await database.save_message(
            cfg.DB_PATH, local_id, body.channel, body.text,
            int(time.time()), True, None, None, body.to
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Failed to persist outgoing message: {e}')
    return {'status': 'sent'}


@router.get('/api/nodes/{node_id}')
async def get_node(node_id: str):
    nodes = meshtasticd_client.get_nodes()
    for n in nodes:
        if n['id'] == node_id:
            return n
    raise HTTPException(404, detail='node not found')


SCREENSHOT_SUBDIR = 'pi-mesh/screenshots'
SCREENSHOT_SD_DIR = '/boot/firmware/screenshots'


@router.post('/api/screenshot')
async def take_screenshot():
    # Determine destination directory
    usb = usb_storage.get_usb_status()
    if usb['connected']:
        mount = None
        for dev in usb['devices']:
            if dev['mountpoint']:
                mount = dev['mountpoint']
                break
        if mount:
            dest_dir = os.path.join(mount, SCREENSHOT_SUBDIR)
            location = 'usb'
        else:
            dest_dir = SCREENSHOT_SD_DIR
            location = 'sd'
    else:
        dest_dir = SCREENSHOT_SD_DIR
        location = 'sd'

    os.makedirs(dest_dir, exist_ok=True)

    # Find next incremental number
    existing = []
    for f in os.listdir(dest_dir):
        m = re.match(r'screenshot_(\d+)\.png$', f)
        if m:
            existing.append(int(m.group(1)))
    next_num = max(existing) + 1 if existing else 1
    filename = f'screenshot_{next_num:03d}.png'
    filepath = os.path.join(dest_dir, filename)

    # Capture framebuffer
    try:
        result = subprocess.run(
            ['sudo', 'fbgrab', filepath],
            capture_output=True, text=True, timeout=10
        )
    except FileNotFoundError:
        return {'ok': False, 'error': 'fbgrab non installato (sudo apt install fbgrab)'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': 'fbgrab timeout'}

    if result.returncode != 0:
        return {'ok': False, 'error': result.stderr.strip() or 'cattura fallita'}

    return {'ok': True, 'path': filename, 'location': location}
