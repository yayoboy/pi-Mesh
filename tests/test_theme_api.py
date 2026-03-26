import json as _json
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


def _get_app():
    import sys
    if "main" in sys.modules:
        del sys.modules["main"]
    import config
    config.SETUP_DONE = True
    from main import app
    return app


@pytest.mark.asyncio
async def test_get_themes_includes_builtins(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/themes")
    assert resp.status_code == 200
    data = resp.json()
    ids = [t["id"] for t in data["themes"]]
    assert "dark" in ids
    assert "light" in ids
    assert "hc" in ids


@pytest.mark.asyncio
async def test_get_themes_includes_custom(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    themes_file.write_text(_json.dumps([{
        "id": "my-theme", "name": "My Theme", "font": "system-ui",
        "vars": {"--bg": "#111111", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }]))
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/themes")
    data = resp.json()
    ids = [t["id"] for t in data["themes"]]
    assert "my-theme" in ids
