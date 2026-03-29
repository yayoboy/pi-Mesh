# tests/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_nodes_page_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/nodes')
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']


@pytest.mark.asyncio
async def test_api_nodes_returns_json(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/api/nodes')
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]['short_name'] == 'TEST'


@pytest.mark.asyncio
async def test_map_page_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/map')
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_log_page_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/log')
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_messages_placeholder_returns_200(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/messages')
    assert r.status_code == 200
