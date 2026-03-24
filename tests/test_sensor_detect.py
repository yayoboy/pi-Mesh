# tests/test_sensor_detect.py
from unittest.mock import MagicMock, patch
import pytest
import sensor_detect


def _make_bus(responsive: dict[int, None] | None = None, reg_data: dict = None):
    """
    Build a mock smbus2.SMBus.

    ``responsive``: set of I2C addresses that ACK read_byte().
    ``reg_data``:   dict mapping (addr, reg, length) → bytes returned by
                    read_i2c_block_data().
    """
    responsive = responsive or set()
    reg_data   = reg_data or {}
    bus = MagicMock()

    def _read_byte(addr):
        if addr not in responsive:
            raise OSError("NACK")

    def _read_i2c_block_data(addr, reg, length):
        key = (addr, reg, length)
        if key in reg_data:
            return reg_data[key]
        raise OSError("no data")

    bus.read_byte.side_effect = _read_byte
    bus.read_i2c_block_data.side_effect = _read_i2c_block_data
    return bus


# ── scan() basic behaviour ────────────────────────────────────────────────────

def test_scan_empty_bus():
    bus = _make_bus(responsive=set())
    result = sensor_detect.scan(bus)
    assert result == []


def test_scan_returns_empty_for_unknown_address():
    """A device at an address not in _ADDR_TABLE must be silently skipped."""
    bus = _make_bus(responsive={0x3C})  # OLED display — not in our table
    result = sensor_detect.scan(bus)
    assert result == []


def test_scan_unambiguous_sensor():
    """VEML7700 lives only at 0x10 — no disambiguation needed."""
    bus = _make_bus(responsive={0x10})
    result = sensor_detect.scan(bus)
    assert result == [{"name": "veml7700", "address": 0x10}]


def test_scan_mcp9808_range():
    """MCP9808 is configurable across 0x18-0x1F."""
    bus = _make_bus(responsive={0x18, 0x1C})
    result = sensor_detect.scan(bus)
    names = [r["name"] for r in result]
    assert all(n == "mcp9808" for n in names)
    assert {r["address"] for r in result} == {0x18, 0x1C}


# ── Bosch BME/BMP disambiguation ─────────────────────────────────────────────

@pytest.mark.parametrize("chip_id,expected", [
    (0x60, "bme280"),
    (0x61, "bme680"),
    (0x58, "bmp280"),
    (0x56, "bmp280"),
    (0x57, "bmp280"),
    (0x55, "bmp085"),
])
def test_bosch_disambiguation_by_chip_id(chip_id, expected):
    bus = _make_bus(
        responsive={0x76},
        reg_data={(0x76, 0xD0, 1): [chip_id]},
    )
    result = sensor_detect.scan(bus)
    assert result == [{"name": expected, "address": 0x76}]


def test_bosch_unknown_chip_id_falls_back_to_bme280():
    bus = _make_bus(
        responsive={0x76},
        reg_data={(0x76, 0xD0, 1): [0x00]},  # unknown
    )
    result = sensor_detect.scan(bus)
    assert result[0]["name"] == "bme280"


def test_bosch_chip_id_read_failure_falls_back_to_bme280():
    """If the chip-ID register can't be read, fall back gracefully."""
    bus = _make_bus(responsive={0x76})  # no reg_data → OSError on chip-ID read
    result = sensor_detect.scan(bus)
    assert result[0]["name"] == "bme280"


# ── INA family disambiguation ─────────────────────────────────────────────────

@pytest.mark.parametrize("die_id,addr,expected", [
    (0x2270, 0x40, "ina260"),
    (0x3220, 0x40, "ina3221"),
    (0x3220, 0x43, "ina3221"),  # INA3221 valid at 0x40-0x43
    (0x3220, 0x46, "ina260"),   # INA3221 not valid above 0x43 → reported as ina260
    (0x1999, 0x40, "ina219"),   # unrecognised die_id → fallback
])
def test_ina_disambiguation(die_id, addr, expected):
    hi, lo = (die_id >> 8) & 0xFF, die_id & 0xFF
    bus = _make_bus(
        responsive={addr},
        reg_data={(addr, 0xFF, 2): [hi, lo]},
    )
    result = sensor_detect.scan(bus)
    assert result == [{"name": expected, "address": addr}]


def test_ina_no_die_id_falls_back_to_ina219():
    bus = _make_bus(responsive={0x40})  # no reg_data → OSError
    result = sensor_detect.scan(bus)
    assert result == [{"name": "ina219", "address": 0x40}]


# ── SHT31 vs INA at 0x44/0x45 ────────────────────────────────────────────────

def test_sht31_detected_at_0x44_when_no_ina_die_id():
    bus = _make_bus(responsive={0x44})  # die_id read fails → SHT31
    result = sensor_detect.scan(bus)
    assert result == [{"name": "sht31", "address": 0x44}]


def test_ina260_wins_at_0x44_when_die_id_matches():
    bus = _make_bus(
        responsive={0x44},
        reg_data={(0x44, 0xFF, 2): [0x22, 0x70]},
    )
    result = sensor_detect.scan(bus)
    assert result == [{"name": "ina260", "address": 0x44}]


# ── merge() ───────────────────────────────────────────────────────────────────

def test_merge_explicit_overrides_scan():
    scanned  = [{"name": "bme280", "address": 0x76}]
    explicit = [{"name": "bme680", "address": 0x76}]
    result = sensor_detect.merge(scanned, explicit)
    assert result == [{"name": "bme680", "address": 0x76}]


def test_merge_combines_non_overlapping():
    scanned  = [{"name": "bme280", "address": 0x76}]
    explicit = [{"name": "ina219", "address": 0x40}]
    result = sensor_detect.merge(scanned, explicit)
    assert {"name": "bme280", "address": 0x76} in result
    assert {"name": "ina219", "address": 0x40} in result


def test_merge_empty_inputs():
    assert sensor_detect.merge([], []) == []


def test_merge_result_sorted_by_address():
    scanned  = [{"name": "bme280", "address": 0x76}, {"name": "veml7700", "address": 0x10}]
    result = sensor_detect.merge(scanned, [])
    assert result[0]["address"] < result[1]["address"]


# ── no smbus2 ─────────────────────────────────────────────────────────────────

def test_scan_returns_empty_when_smbus_unavailable():
    with patch.object(sensor_detect, "_SMBUS_AVAILABLE", False):
        assert sensor_detect.scan() == []
