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


@pytest.mark.asyncio
async def test_get_single_node_returns_node(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/api/nodes/!aabbccdd')
    assert r.status_code == 200
    data = r.json()
    assert data['id'] == '!aabbccdd'
    assert data['short_name'] == 'TEST'


@pytest.mark.asyncio
async def test_get_single_node_404_when_missing(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.get('/api/nodes/!nonexistent')
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_traceroute_returns_requested(mock_client):
    from main import app
    from unittest.mock import AsyncMock, patch
    with patch('meshtasticd_client.request_traceroute', new_callable=AsyncMock) as mock_tr:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post('/api/nodes/!aabbccdd/traceroute')
    assert r.status_code == 200
    assert r.json()['status'] == 'requested'
    mock_tr.assert_called_once_with('!aabbccdd')


@pytest.mark.asyncio
async def test_post_traceroute_503_when_disconnected(mock_client):
    from main import app
    mock_client['connected'].return_value = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.post('/api/nodes/!aabbccdd/traceroute')
    assert r.status_code == 503
    assert r.json()['detail'] == 'board not connected'


@pytest.mark.asyncio
async def test_get_traceroute_result_404_when_missing(mock_client):
    from main import app
    from unittest.mock import patch
    with patch('meshtasticd_client.get_traceroute_result', return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/nodes/!aabbccdd/traceroute')
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_traceroute_result_returns_cached(mock_client):
    from main import app
    from unittest.mock import patch
    cached = {'node_id': '!aabbccdd', 'hops': ['!00000001'], 'ts': 1700000000}
    with patch('meshtasticd_client.get_traceroute_result', return_value=cached):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/nodes/!aabbccdd/traceroute')
    assert r.status_code == 200
    assert r.json()['hops'] == ['!00000001']


@pytest.mark.asyncio
async def test_post_request_position_returns_requested(mock_client):
    from main import app
    from unittest.mock import AsyncMock, patch
    with patch('meshtasticd_client.request_position', new_callable=AsyncMock) as mock_rp:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post('/api/nodes/!aabbccdd/request-position')
    assert r.status_code == 200
    assert r.json()['status'] == 'requested'
    mock_rp.assert_called_once_with('!aabbccdd')


@pytest.mark.asyncio
async def test_post_send_text_returns_sent(mock_client):
    from main import app
    from unittest.mock import AsyncMock, patch
    with patch('meshtasticd_client.send_text', new_callable=AsyncMock) as mock_st:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post('/api/messages/send', json={
                'text': 'Hello',
                'to': '!aabbccdd',
                'channel': 0,
            })
    assert r.status_code == 200
    assert r.json()['status'] == 'sent'
    mock_st.assert_called_once_with('Hello', '!aabbccdd', 0)


@pytest.mark.asyncio
async def test_post_send_text_503_when_disconnected(mock_client):
    from main import app
    mock_client['connected'].return_value = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r = await ac.post('/api/messages/send', json={
            'text': 'Hello',
            'to': '!aabbccdd',
            'channel': 0,
        })
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_get_markers_returns_empty_list(mock_client):
    from main import app
    from unittest.mock import patch, AsyncMock
    with patch('database.get_markers', new_callable=AsyncMock, return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/map/markers')
    assert r.status_code == 200
    assert r.json() == {'markers': []}


@pytest.mark.asyncio
async def test_post_marker_creates_and_returns(mock_client):
    from main import app
    from unittest.mock import patch, AsyncMock
    created = {'id': 1, 'label': 'HQ', 'icon_type': 'poi', 'latitude': 41.9, 'longitude': 12.5}
    with patch('database.create_marker', new_callable=AsyncMock, return_value=created):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post('/api/map/markers', json={
                'label': 'HQ',
                'icon_type': 'poi',
                'latitude': 41.9,
                'longitude': 12.5,
            })
    assert r.status_code == 200
    data = r.json()
    assert data['label'] == 'HQ'
    assert data['id'] == 1


@pytest.mark.asyncio
async def test_delete_marker_returns_deleted(mock_client):
    from main import app
    from unittest.mock import patch, AsyncMock
    with patch('database.delete_marker', new_callable=AsyncMock, return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.delete('/api/map/markers/1')
    assert r.status_code == 200
    assert r.json()['status'] == 'deleted'


@pytest.mark.asyncio
async def test_delete_marker_404_when_not_found(mock_client):
    from main import app
    from unittest.mock import patch, AsyncMock
    with patch('database.delete_marker', new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.delete('/api/map/markers/9999')
    assert r.status_code == 404
