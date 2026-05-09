"""Endpoint smoke tests for ``routers.bots_router``.

We don't start the runner (no radio, no DB writes); we just patch the
runner state with a minimal fake so the route handlers exercise their
HTTP-level contract.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


class _FakeCfg:
    def __init__(self):
        self._enabled = {"ping": True, "help": False}
        self.prefix = "!"

    def is_enabled(self, name: str) -> bool:
        return self._enabled.get(name, False)

    async def set_enabled(self, name: str, enabled: bool) -> None:
        self._enabled[name] = bool(enabled)

    async def set_prefix(self, prefix: str) -> None:
        self.prefix = prefix


@pytest.fixture
def runner_state(monkeypatch):
    from bots import runner
    cfg = _FakeCfg()
    monkeypatch.setattr(runner._state, "config", cfg, raising=False)
    monkeypatch.setattr(runner._state, "started", True, raising=False)

    class _StubBot:
        def __init__(self, name: str, desc: str, default: bool):
            self.name = name
            self.description = desc
            self.default_enabled = default

    monkeypatch.setattr(runner._state, "bots", [
        _StubBot("ping", "p", True),
        _StubBot("help", "h", True),
    ], raising=False)

    async def _noop_reload():
        return None
    monkeypatch.setattr(runner, "reload_config", _noop_reload)
    return cfg


@pytest.fixture
async def client(runner_state):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_api_bots_returns_state(client):
    r = await client.get("/api/bots")
    assert r.status_code == 200
    data = r.json()
    assert data["prefix"] == "!"
    names = [b["name"] for b in data["bots"]]
    assert names == ["ping", "help"]


@pytest.mark.asyncio
async def test_toggle_unknown_bot_returns_404(client):
    r = await client.post("/api/bots/nonexistent/toggle", json={"enabled": True})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_toggle_known_bot_persists(client, runner_state):
    r = await client.post("/api/bots/help/toggle", json={"enabled": True})
    assert r.status_code == 200
    assert runner_state.is_enabled("help") is True


@pytest.mark.asyncio
async def test_set_prefix_validates_non_empty(client):
    r = await client.post("/api/bots/prefix", json={"prefix": "  "})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_set_prefix_persists(client, runner_state):
    r = await client.post("/api/bots/prefix", json={"prefix": "?"})
    assert r.status_code == 200
    assert runner_state.prefix == "?"


@pytest.mark.asyncio
async def test_reload_endpoint_ok(client):
    r = await client.post("/api/bots/reload")
    assert r.status_code == 200
    assert r.json()["ok"] is True
