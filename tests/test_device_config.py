# tests/test_device_config.py — endpoint config device-level
# (position, power, display, network, bluetooth, security)
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

import database
import meshtasticd_client


SECTIONS = {
    'position': {'gps_mode': 'ENABLED', 'position_broadcast_secs': 900,
                 'position_broadcast_smart_enabled': True, 'fixed_position': False,
                 'gps_update_interval': 120, 'cached': False},
    'power': {'is_power_saving': True, 'on_battery_shutdown_after_secs': 0,
              'wait_bluetooth_secs': 60, 'sds_secs': 0, 'ls_secs': 300,
              'min_wake_secs': 10, 'cached': False},
    'display': {'screen_on_secs': 60, 'auto_screen_carousel_secs': 0,
                'compass_north_top': False, 'flip_screen': True, 'units': 'METRIC',
                'displaymode': 'DEFAULT', 'heading_bold': False,
                'wake_on_tap_or_motion': True, 'use_12h_clock': False, 'cached': False},
    'network': {'wifi_enabled': True, 'wifi_ssid': 'mesh', 'wifi_psk': 'secret',
                'eth_enabled': False, 'ntp_server': '', 'address_mode': 'DHCP',
                'cached': False},
    'bluetooth': {'enabled': True, 'mode': 'FIXED_PIN', 'fixed_pin': 123456,
                  'cached': False},
    'security': {'is_managed': False, 'serial_enabled': True,
                 'debug_log_api_enabled': False, 'admin_channel_enabled': True,
                 'public_key_b64': 'AAAA', 'cached': False},
}

_GETTERS = {
    'position': 'get_position_config',
    'power': 'get_power_config',
    'display': 'get_display_device_config',
    'network': 'get_network_config',
    'bluetooth': 'get_bluetooth_config',
    'security': 'get_security_config',
}

_SETTERS = {
    'position': 'set_position_config',
    'power': 'set_power_config',
    'display': 'set_display_device_config',
    'network': 'set_network_config',
    'bluetooth': 'set_bluetooth_config',
    'security': 'set_security_config',
}


@pytest.mark.asyncio
@pytest.mark.parametrize('section', SECTIONS)
async def test_get_device_config_endpoint(mock_client, section):
    from main import app
    with patch(f'meshtasticd_client.{_GETTERS[section]}', new_callable=AsyncMock,
               return_value=dict(SECTIONS[section])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get(f'/api/config/device/{section}')
    assert r.status_code == 200
    body = r.json()
    assert body['cached'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('section', SECTIONS)
async def test_post_device_config_endpoint(mock_client, section):
    from main import app
    payload = {k: v for k, v in SECTIONS[section].items()
               if k not in ('cached', 'public_key_b64')}
    with patch(f'meshtasticd_client.{_SETTERS[section]}', new_callable=AsyncMock) as m:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post(f'/api/config/device/{section}', json=payload)
    assert r.status_code == 200
    assert r.json() == {'ok': True}
    m.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('section', SECTIONS)
async def test_post_device_config_offline_returns_503(mock_client, section):
    from main import app
    payload = {k: v for k, v in SECTIONS[section].items()
               if k not in ('cached', 'public_key_b64')}
    with patch(f'meshtasticd_client.{_SETTERS[section]}', new_callable=AsyncMock,
               side_effect=RuntimeError('Board not connected')):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.post(f'/api/config/device/{section}', json=payload)
    assert r.status_code == 503
    assert 'error' in r.json()


@pytest.mark.asyncio
async def test_post_device_config_invalid_enum_returns_400(mock_client):
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        r1 = await ac.post('/api/config/device/position', json={'gps_mode': 'BOGUS'})
        r2 = await ac.post('/api/config/device/bluetooth', json={'mode': 'FIXED_PIN', 'fixed_pin': 42})
        r3 = await ac.post('/api/config/device/display', json={'units': 'FURLONGS'})
    assert r1.status_code == 400
    assert r2.status_code == 400
    assert r3.status_code == 400


@pytest.mark.asyncio
async def test_get_device_config_offline_returns_defaults(tmp_path):
    """Senza board e senza cache, il client risponde con i default."""
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    with patch.object(meshtasticd_client, '_connected', False):
        data = await meshtasticd_client.get_position_config(db_path)
    assert data['cached'] is True
    assert data['gps_mode'] == 'DISABLED'


@pytest.mark.asyncio
async def test_get_device_config_offline_returns_cache(tmp_path):
    """Con cache presente, la risposta offline è la cache marcata cached."""
    db_path = str(tmp_path / 'test.db')
    await database.init(db_path)
    await database.set_config_cache(db_path, 'bluetooth',
                                    {'enabled': True, 'mode': 'NO_PIN', 'fixed_pin': 111111})
    with patch.object(meshtasticd_client, '_connected', False):
        data = await meshtasticd_client.get_bluetooth_config(db_path)
    assert data['cached'] is True
    assert data['mode'] == 'NO_PIN'
