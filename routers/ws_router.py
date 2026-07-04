"""WebSocket /ws — canale eventi real-time verso la UI.

All'accept invia ``{type:'init', nodes:[...]}``; da lì in poi il client
riceve gli eventi che i task di main.py pescano dalle code di
meshtasticd_client e passano a ``manager.broadcast``. Tipi principali:
message, node, position, telemetry, log, traceroute_result, ack,
waypoint, neighbor_info, sensor, paxcounter, rpi_telemetry.

Il ``ConnectionManager`` tiene il set dei client connessi; i socket che
falliscono in send vengono scartati al volo (kiosk e browser LAN vanno
e vengono).
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import meshtasticd_client

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, msg: dict) -> None:
        text = json.dumps(msg)
        dead: set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)


manager = ConnectionManager()


@router.websocket('/ws')
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    logger.info('WebSocket client connected')
    try:
        # Send init payload with current node list
        await websocket.send_text(json.dumps({
            'type': 'init',
            'nodes': meshtasticd_client.get_nodes(),
        }))
        # Keep connection alive — read loop discards incoming messages (ping frames)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info('WebSocket client disconnected')
    finally:
        manager.disconnect(websocket)
