# tests/test_config.py
import pytest
import database


@pytest.fixture
async def db(tmp_path):
    path = str(tmp_path / 'test.db')
    await database.init(path)
    return path


@pytest.mark.asyncio
async def test_config_cache_set_and_get(db):
    await database.set_config_cache(db, 'node', {'long_name': 'pi-mesh', 'short_name': 'PM'})
    result = await database.get_config_cache(db, 'node')
    assert result['long_name'] == 'pi-mesh'
    assert result['short_name'] == 'PM'


@pytest.mark.asyncio
async def test_config_cache_overwrites(db):
    await database.set_config_cache(db, 'node', {'long_name': 'old'})
    await database.set_config_cache(db, 'node', {'long_name': 'new'})
    result = await database.get_config_cache(db, 'node')
    assert result['long_name'] == 'new'


@pytest.mark.asyncio
async def test_config_cache_missing_returns_none(db):
    result = await database.get_config_cache(db, 'lora')
    assert result is None


@pytest.mark.asyncio
async def test_gpio_device_crud(db):
    device = {
        'type': 'i2c_sensor', 'name': 'BME280', 'enabled': 1,
        'pin_a': None, 'pin_b': None, 'pin_sw': None,
        'i2c_bus': 1, 'i2c_address': '0x76', 'sensor_type': 'BME280',
        'action': None, 'config_json': '{}'
    }
    dev_id = await database.add_gpio_device(db, device)
    assert dev_id == 1

    devices = await database.get_gpio_devices(db)
    assert len(devices) == 1
    assert devices[0]['name'] == 'BME280'
    assert devices[0]['i2c_address'] == '0x76'

    await database.update_gpio_device(db, dev_id, {**device, 'name': 'BME280 esterno'})
    devices = await database.get_gpio_devices(db)
    assert devices[0]['name'] == 'BME280 esterno'

    await database.delete_gpio_device(db, dev_id)
    devices = await database.get_gpio_devices(db)
    assert devices == []
