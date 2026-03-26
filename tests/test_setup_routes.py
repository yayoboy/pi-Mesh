import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_hw():
    mock_conn = MagicMock()
    mock_conn.execute  = AsyncMock()
    mock_conn.commit   = AsyncMock()
    mock_conn.close    = AsyncMock()
    with patch("database.init_db",            new_callable=AsyncMock, return_value=mock_conn), \
         patch("database.get_nodes",           new_callable=AsyncMock, return_value=[]),       \
         patch("database.get_messages",        new_callable=AsyncMock, return_value=[]),       \
         patch("meshtastic_client.init"),                                                       \
         patch("meshtastic_client.connect",    new_callable=AsyncMock),                        \
         patch("meshtastic_client.disconnect", new_callable=AsyncMock),                        \
         patch("meshtastic_client.is_connected",  return_value=False),                         \
         patch("meshtastic_client.get_local_node", return_value=None),                         \
         patch("sensor_handler.init",          return_value=[]),                               \
         patch("sensor_handler.start_polling", new_callable=AsyncMock),                        \
         patch("gpio_handler.init"),                                                            \
         patch("watchdog.start_all"):
        yield mock_conn


def _get_app(setup_done: bool):
    import sys
    if "main" in sys.modules:
        del sys.modules["main"]
    import config
    config.SETUP_DONE = setup_done
    from main import app
    return app


@pytest.mark.asyncio
async def test_setup_redirect_when_not_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/home", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/setup" in resp.headers.get("location", "")


@pytest.mark.asyncio
async def test_no_redirect_when_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/home", follow_redirects=False)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_setup_page_accessible_when_not_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/setup")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_not_redirected_when_not_done(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/status", follow_redirects=False)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_setup_serial_ports_returns_list(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/setup/serial-ports")
    assert resp.status_code == 200
    assert "ports" in resp.json()


@pytest.mark.asyncio
async def test_setup_save_writes_setup_done(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    env_file = tmp_path / "config.env"
    env_file.write_text("")
    monkeypatch.chdir(tmp_path)
    app = _get_app(setup_done=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/setup/save", json={
            "serial_port": "/dev/ttyUSB0",
            "map_lat_min": 41.0, "map_lat_max": 43.0,
            "map_lon_min": 11.5, "map_lon_max": 14.5,
        })
    assert resp.status_code == 200
    content = env_file.read_text()
    assert "SETUP_DONE=1" in content
    assert "SERIAL_PORT=/dev/ttyUSB0" in content
