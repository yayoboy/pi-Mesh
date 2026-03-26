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
    app = _get_app()
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/themes")
    data = resp.json()
    ids = [t["id"] for t in data["themes"]]
    assert "my-theme" in ids


@pytest.mark.asyncio
async def test_post_theme_creates_entry(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    app = _get_app()
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    monkeypatch.setattr("main.FONTS_PATH", str(tmp_path / "fonts"))
    payload = {
        "id": "my-theme", "name": "My Theme", "font": "system-ui",
        "vars": {"--bg": "#111111", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/themes", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    saved = _json.loads(themes_file.read_text())
    assert saved[0]["id"] == "my-theme"


@pytest.mark.asyncio
async def test_post_theme_rejects_invalid_color(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    app = _get_app()
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    monkeypatch.setattr("main.FONTS_PATH", str(tmp_path / "fonts"))
    payload = {
        "id": "bad", "name": "Bad", "font": "system-ui",
        "vars": {"--bg": "red", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/themes", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_theme(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    themes_file.write_text(_json.dumps([{
        "id": "to-delete", "name": "Del", "font": "system-ui",
        "vars": {"--bg": "#111111", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }]))
    app = _get_app()
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/themes/to-delete")
    assert resp.status_code == 200
    saved = _json.loads(themes_file.read_text())
    assert len(saved) == 0


@pytest.mark.asyncio
async def test_delete_builtin_rejected(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    app = _get_app()
    monkeypatch.setattr("main.THEMES_PATH", str(tmp_path / "themes.json"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/themes/dark")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_fonts_returns_list(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "MyFont.ttf").write_bytes(b"")
    (fonts_dir / "Other.woff2").write_bytes(b"")
    app = _get_app()
    monkeypatch.setattr("main.FONTS_PATH", str(fonts_dir))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/themes/fonts")
    assert resp.status_code == 200
    data = resp.json()
    assert "system_fonts" in data
    assert "custom_fonts" in data
    names = [f["name"] for f in data["custom_fonts"]]
    assert "MyFont" in names
