# routers/log.py
import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import meshtasticd_client

router = APIRouter()
templates = Jinja2Templates(directory='templates')


@router.get('/log', response_class=HTMLResponse)
async def log_page(request: Request):
    return templates.TemplateResponse('log.html', {
        'request': request, 'active_tab': 'log'
    })


@router.get('/api/log/stream')
async def log_stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    def on_packet(entry: dict):
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            pass

    meshtasticd_client.subscribe_log(on_packet)

    async def event_generator():
        # Send last 20 entries on connect
        for entry in list(meshtasticd_client.get_log_queue())[-20:]:
            yield f'data: {json.dumps(entry)}\n\n'
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f'data: {json.dumps(entry)}\n\n'
                except asyncio.TimeoutError:
                    yield ': keepalive\n\n'
        finally:
            meshtasticd_client.unsubscribe_log(on_packet)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
