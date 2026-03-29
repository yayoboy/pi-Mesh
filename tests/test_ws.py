# tests/test_ws.py
import pytest
import json
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_ws_router_has_required_attributes():
    from routers import ws_router
    assert hasattr(ws_router, 'router')
    assert hasattr(ws_router, 'manager')


@pytest.mark.asyncio
async def test_connection_manager_connect_accepts_websocket():
    from routers.ws_router import ConnectionManager

    manager = ConnectionManager()
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()

    await manager.connect(mock_ws)
    mock_ws.accept.assert_called_once()
    assert mock_ws in manager._connections


@pytest.mark.asyncio
async def test_connection_manager_disconnect_removes_websocket():
    from routers.ws_router import ConnectionManager

    manager = ConnectionManager()
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()

    await manager.connect(mock_ws)
    manager.disconnect(mock_ws)
    assert mock_ws not in manager._connections


@pytest.mark.asyncio
async def test_connection_manager_broadcast_sends_json():
    from routers.ws_router import ConnectionManager

    manager = ConnectionManager()
    ws1 = AsyncMock()
    ws1.accept = AsyncMock()
    ws1.send_text = AsyncMock()
    ws2 = AsyncMock()
    ws2.accept = AsyncMock()
    ws2.send_text = AsyncMock()

    await manager.connect(ws1)
    await manager.connect(ws2)

    await manager.broadcast({'type': 'test', 'value': 42})

    ws1.send_text.assert_called_once_with('{"type": "test", "value": 42}')
    ws2.send_text.assert_called_once_with('{"type": "test", "value": 42}')


@pytest.mark.asyncio
async def test_connection_manager_broadcast_removes_dead_connections():
    from routers.ws_router import ConnectionManager

    manager = ConnectionManager()
    dead_ws = AsyncMock()
    dead_ws.accept = AsyncMock()
    dead_ws.send_text = AsyncMock(side_effect=Exception('connection closed'))

    await manager.connect(dead_ws)
    await manager.broadcast({'type': 'ping'})

    assert dead_ws not in manager._connections
