# tests/test_sensor_handler.py
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

def test_init_returns_empty_list_for_no_sensors():
    import sensor_handler
    result = sensor_handler.init([])
    assert result == []

def test_init_skips_unavailable_sensor():
    import sensor_handler
    with patch.object(sensor_handler, '_make_driver') as mock_make:
        mock_driver = MagicMock()
        mock_driver.available.return_value = False
        mock_make.return_value = mock_driver
        result = sensor_handler.init([{"name": "bme280", "address": 0x76}])
        assert result == []

@pytest.mark.asyncio
async def test_polling_calls_broadcast(tmp_path):
    import sensor_handler, database
    conn = await database.init_db(runtime_path=str(tmp_path / "t.db"))
    mock_driver = MagicMock()
    mock_driver.name = "bme280"
    mock_driver.read.return_value = {"temp": 22.0}
    broadcast = AsyncMock()
    task = asyncio.create_task(
        sensor_handler.start_polling([mock_driver], conn, broadcast, interval=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    assert broadcast.called
    await conn.close()

def test_ina219_driver_init_called_once():
    """INA219 driver must be instantiated in __init__, not in read()."""
    import inspect
    from sensor_handler import INA219Driver
    source = inspect.getsource(INA219Driver.__init__)
    assert '_driver' in source, "INA219Driver.__init__ must cache driver in self._driver"

def test_ina219_read_does_not_reimport():
    """read() must use self._driver, not create a new INA219 instance."""
    import inspect
    from sensor_handler import INA219Driver
    source = inspect.getsource(INA219Driver.read)
    assert 'INA219(' not in source, "read() must not instantiate INA219 — use self._driver"
