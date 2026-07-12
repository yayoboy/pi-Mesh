# tests/test_ui_config.py
"""Tests for server-side UI settings persistence (/api/config/ui)."""
import pytest
from httpx import AsyncClient, ASGITransport

import database


@pytest.fixture
async def db(tmp_path):
    await database.init(str(tmp_path / 'test.db'))
    yield


@pytest.mark.asyncio
async def test_ui_config_defaults(mock_client, db):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/api/config/ui')
    assert r.status_code == 200
    data = r.json()
    assert data['theme'] == 'b1'
    assert data['map_style'] == 'osm'
    assert data['accent'] is None
    assert data['custom_theme'] is None


@pytest.mark.asyncio
async def test_ui_config_roundtrip(mock_client, db):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.post('/api/config/ui', json={
            'theme': 'b2', 'map_style': 'satellite', 'accent': '#d84545',
            'custom_theme': {'--bg': '#000000'},
        })
        assert r.status_code == 200
        r = await ac.get('/api/config/ui')
    data = r.json()
    assert data['theme'] == 'b2'
    assert data['map_style'] == 'satellite'
    assert data['accent'] == '#d84545'
    assert data['custom_theme'] == {'--bg': '#000000'}


@pytest.mark.asyncio
async def test_ui_config_partial_update(mock_client, db):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        await ac.post('/api/config/ui', json={'theme': 'b5'})
        await ac.post('/api/config/ui', json={'map_style': 'satellite'})
        r = await ac.get('/api/config/ui')
    data = r.json()
    assert data['theme'] == 'b5'          # not clobbered by second POST
    assert data['map_style'] == 'satellite'


@pytest.mark.asyncio
async def test_ui_config_rejects_bad_map_style(mock_client, db):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.post('/api/config/ui', json={'map_style': 'radar'})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_map_page_carries_saved_style(mock_client, db):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        await ac.post('/api/config/ui', json={'map_style': 'satellite'})
        r = await ac.get('/map')
    assert r.status_code == 200
    assert 'data-map-style="satellite"' in r.text
