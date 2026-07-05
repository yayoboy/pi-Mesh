# tests/test_full_protocol.py — copertura protocollo completa:
# canali estesi + URL/QR, LoRa avanzata, moduli audio/paxcounter/remote-hw,
# utilità nodo (favoriti/ignorati, orario, NodeDB) e config remota.
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_post_channel_full_fields(mock_client):
    from main import app
    with patch('meshtasticd_client.set_channel', new_callable=AsyncMock) as m:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post('/api/config/channels/1', json={
                'name': 'privato', 'psk_b64': 'AQ==', 'role': 'SECONDARY',
                'uplink_enabled': True, 'downlink_enabled': False,
                'position_precision': 16,
            })
    assert r.status_code == 200
    idx, params = m.await_args.args
    assert idx == 1 and params['role'] == 'SECONDARY'
    assert params['position_precision'] == 16


@pytest.mark.asyncio
async def test_post_channel_invalid_role_and_precision(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r1 = await ac.post('/api/config/channels/0', json={'name': 'x', 'role': 'BOGUS'})
        r2 = await ac.post('/api/config/channels/0', json={'name': 'x', 'position_precision': 99})
    assert r1.status_code == 400
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_get_channels_url(mock_client):
    from main import app
    with patch('meshtasticd_client.get_channel_url', new_callable=AsyncMock,
               return_value='https://meshtastic.org/e/#abc'):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/config/channels/url')
    assert r.status_code == 200
    assert r.json()['url'].startswith('https://meshtastic.org/e/#')


@pytest.mark.asyncio
async def test_post_channels_url_import_and_validation(mock_client):
    from main import app
    with patch('meshtasticd_client.set_channel_url', new_callable=AsyncMock) as m:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            ok = await ac.post('/api/config/channels/url',
                               json={'url': 'https://meshtastic.org/e/#abc', 'add_only': True})
            bad = await ac.post('/api/config/channels/url', json={'url': 'http://example.com'})
    assert ok.status_code == 200
    m.assert_awaited_once_with('https://meshtastic.org/e/#abc', True)
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_get_channels_qr_svg(mock_client):
    from main import app
    with patch('meshtasticd_client.get_channel_url', new_callable=AsyncMock,
               return_value='https://meshtastic.org/e/#abc'):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/config/channels/qr')
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('image/svg')
    assert b'<svg' in r.content


@pytest.mark.asyncio
async def test_post_lora_advanced_fields(mock_client):
    from main import app
    with patch('meshtasticd_client.set_lora_config', new_callable=AsyncMock) as m:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post('/api/config/lora', json={
                'region': 'EU_868', 'modem_preset': 'LONG_FAST',
                'hop_limit': 5, 'tx_power': 14, 'override_duty_cycle': True,
            })
            bad = await ac.post('/api/config/lora', json={
                'region': 'EU_868', 'modem_preset': 'LONG_FAST', 'hop_limit': 9})
    assert r.status_code == 200
    assert m.await_args.args[0]['hop_limit'] == 5
    assert bad.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint,setter', [
    ('/api/config/module/audio', 'set_audio_config'),
    ('/api/config/module/paxcounter', 'set_paxcounter_config'),
    ('/api/config/module/remote-hardware', 'set_remote_hardware_config'),
])
async def test_new_modules_roundtrip(mock_client, endpoint, setter):
    from main import app
    getter = setter.replace('set_', 'get_')
    with patch(f'meshtasticd_client.{getter}', new_callable=AsyncMock,
               return_value={'enabled': False, 'cached': True}), \
         patch(f'meshtasticd_client.{setter}', new_callable=AsyncMock) as m:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            g = await ac.get(endpoint)
            p = await ac.post(endpoint, json={'enabled': True})
    assert g.status_code == 200
    assert p.status_code == 200
    m.assert_awaited_once()


@pytest.mark.asyncio
async def test_node_favorite_and_ignore(mock_client):
    from main import app
    with patch('meshtasticd_client.set_node_favorite', new_callable=AsyncMock) as fav, \
         patch('meshtasticd_client.set_node_ignored', new_callable=AsyncMock) as ign:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r1 = await ac.post('/api/nodes/!aabbccdd/favorite?on=true')
            r2 = await ac.post('/api/nodes/!aabbccdd/ignore?on=false')
    assert r1.status_code == 200 and r2.status_code == 200
    fav.assert_awaited_once_with('!aabbccdd', True)
    ign.assert_awaited_once_with('!aabbccdd', False)


@pytest.mark.asyncio
async def test_sync_time_and_reset_nodedb(mock_client):
    from main import app
    with patch('meshtasticd_client.sync_time', new_callable=AsyncMock) as st, \
         patch('meshtasticd_client.reset_nodedb', new_callable=AsyncMock) as rn:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r1 = await ac.post('/api/system/sync-time')
            r2 = await ac.post('/api/system/reset-nodedb')
    assert r1.status_code == 200 and r2.status_code == 200
    st.assert_awaited_once()
    rn.assert_awaited_once()


@pytest.mark.asyncio
async def test_remote_config_get_and_post(mock_client):
    from main import app
    with patch('meshtasticd_client.get_remote_config', new_callable=AsyncMock,
               return_value={'region': 'EU_868'}) as g, \
         patch('meshtasticd_client.set_remote_config', new_callable=AsyncMock) as s:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r1 = await ac.get('/api/admin/!11223344/config/lora')
            r2 = await ac.post('/api/admin/!11223344/config/lora',
                               json={'region': 'EU_433', 'cached': False})
    assert r1.status_code == 200 and r1.json()['region'] == 'EU_868'
    assert r2.status_code == 200
    g.assert_awaited_once_with('!11223344', 'lora')
    # 'cached' viene scartato prima della scrittura
    assert 'cached' not in s.await_args.args[2]


@pytest.mark.asyncio
async def test_remote_config_unknown_section_and_timeout(mock_client):
    from main import app
    with patch('meshtasticd_client.get_remote_config', new_callable=AsyncMock,
               side_effect=TimeoutError()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            bad = await ac.get('/api/admin/!11223344/config/bogus')
            slow = await ac.get('/api/admin/!11223344/config/lora')
    assert bad.status_code == 400
    assert slow.status_code == 504


@pytest.mark.asyncio
async def test_apply_updates_converts_enums_and_skips_unknown():
    import meshtasticd_client
    from meshtastic.protobuf import config_pb2
    cfg = config_pb2.Config.LoRaConfig()
    meshtasticd_client._apply_updates(cfg, {
        'region': 'EU_868', 'hop_limit': 5, 'sconosciuto': 1, 'cached': False,
    })
    assert cfg.region == config_pb2.Config.LoRaConfig.RegionCode.Value('EU_868')
    assert cfg.hop_limit == 5
