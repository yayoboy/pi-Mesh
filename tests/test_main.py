# tests/test_main.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture(autouse=True)
def mock_hardware():
    """Mock tutto l'hardware per i test su Mac"""
    mock_conn = MagicMock()
    mock_conn.execute  = AsyncMock()
    mock_conn.commit   = AsyncMock()
    mock_conn.close    = AsyncMock()
    with patch("database.init_db",          new_callable=AsyncMock, return_value=mock_conn), \
         patch("database.get_nodes",         new_callable=AsyncMock, return_value=[]), \
         patch("database.get_messages",      new_callable=AsyncMock, return_value=[]), \
         patch("meshtastic_client.init"), \
         patch("meshtastic_client.connect",  new_callable=AsyncMock), \
         patch("meshtastic_client.disconnect", new_callable=AsyncMock), \
         patch("meshtastic_client.is_connected", return_value=False), \
         patch("meshtastic_client.get_local_node", return_value=None), \
         patch("sensor_handler.init",        return_value=[]), \
         patch("sensor_handler.start_polling", new_callable=AsyncMock), \
         patch("gpio_handler.init"), \
         patch("watchdog.start_all"):
        yield mock_conn

@pytest.mark.asyncio
async def test_root_redirects_to_home(mock_hardware):
    from httpx import AsyncClient, ASGITransport
    # Deve importare DOPO i mock
    import importlib, sys, config
    if 'main' in sys.modules:
        del sys.modules['main']
    config.SETUP_DONE = True
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/", follow_redirects=False)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers.get("location", "").endswith("/home")

@pytest.mark.asyncio
async def test_api_status_returns_json(mock_hardware):
    from httpx import AsyncClient, ASGITransport
    import importlib, sys, config
    if 'main' in sys.modules:
        del sys.modules['main']
    config.SETUP_DONE = True
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data
    assert "ram_mb" in data

@pytest.mark.asyncio
async def test_send_empty_text_returns_400(mock_hardware):
    from httpx import AsyncClient, ASGITransport
    import sys, config
    if 'main' in sys.modules:
        del sys.modules['main']
    config.SETUP_DONE = True
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/send", json={"text": "", "channel": 0})
    assert resp.status_code == 400
