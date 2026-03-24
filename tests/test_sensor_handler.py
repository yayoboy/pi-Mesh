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


# ── Driver registry completeness ──────────────────────────────────────────────

def test_all_expected_drivers_registered():
    """Every driver documented in the README must appear in _DRIVER_MAP."""
    import sensor_handler
    expected = {
        "bme280", "bme680",
        "bmp280", "bmp085", "bmp180",
        "sht31", "shtc3", "mcp9808", "lps22hb",
        "pmsa003i", "sen5x",
        "veml7700", "tsl2591", "rcwl9620",
        "ina219", "ina260", "ina3221", "max17048",
    }
    missing = expected - set(sensor_handler._DRIVER_MAP.keys())
    assert not missing, f"Missing from _DRIVER_MAP: {missing}"


def test_bmp180_alias_maps_to_bmp085_driver():
    import sensor_handler
    assert sensor_handler._DRIVER_MAP["bmp180"] is sensor_handler._DRIVER_MAP["bmp085"]


# ── Structural contract for all drivers ───────────────────────────────────────

_ADAFRUIT_DRIVERS = [
    "BMP280Driver", "BMP085Driver", "SHT31Driver", "SHTC3Driver",
    "MCP9808Driver", "LPS22HBDriver", "PMSA003IDriver",
    "VEML7700Driver", "TSL2591Driver", "RCWL9620Driver",
    "INA260Driver", "INA3221Driver", "MAX17048Driver",
]

import pytest
@pytest.mark.parametrize("cls_name", _ADAFRUIT_DRIVERS)
def test_adafruit_driver_caches_in_init(cls_name):
    """Each Adafruit driver must cache its hardware object in self._driver inside __init__."""
    import inspect, sensor_handler
    cls = getattr(sensor_handler, cls_name)
    src = inspect.getsource(cls.__init__)
    assert "self._driver" in src, f"{cls_name}.__init__ must assign self._driver"


@pytest.mark.parametrize("cls_name", _ADAFRUIT_DRIVERS)
def test_adafruit_driver_read_guards_on_driver(cls_name):
    """Each Adafruit driver's read() must guard on self._driver before doing any I/O."""
    import inspect, sensor_handler
    cls = getattr(sensor_handler, cls_name)
    src = inspect.getsource(cls.read)
    assert "self._driver" in src, f"{cls_name}.read() must reference self._driver"


@pytest.mark.parametrize("cls_name", _ADAFRUIT_DRIVERS + ["BME680Driver", "INA219Driver"])
def test_driver_has_name_property(cls_name):
    import sensor_handler
    cls = getattr(sensor_handler, cls_name)
    # name must be a string (not raise NotImplementedError)
    assert isinstance(cls.__dict__.get("name") or getattr(cls, "name"), property)
