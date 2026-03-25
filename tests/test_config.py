# tests/test_config.py
import os, pytest

def test_serial_port_default(monkeypatch):
    monkeypatch.delenv("SERIAL_PORT", raising=False)
    import importlib, config
    importlib.reload(config)
    assert config.SERIAL_PORT == "/dev/ttyMESHTASTIC"

def test_serial_port_override(monkeypatch):
    monkeypatch.setenv("SERIAL_PORT", "/dev/ttyUSB0")
    import importlib, config
    importlib.reload(config)
    assert config.SERIAL_PORT == "/dev/ttyUSB0"

def test_parse_sensor_config_empty():
    from config import parse_sensor_config
    assert parse_sensor_config("") == []

def test_parse_sensor_config_valid():
    from config import parse_sensor_config
    result = parse_sensor_config("bme280:0x76,ina219:0x40")
    assert result == [
        {"name": "bme280", "address": 0x76},
        {"name": "ina219", "address": 0x40},
    ]

def test_parse_sensor_config_invalid_skips():
    from config import parse_sensor_config
    result = parse_sensor_config("bme280:0x76,badentry,ina219:0x40")
    assert len(result) == 2


def test_setup_done_default_false(monkeypatch):
    monkeypatch.delenv("SETUP_DONE", raising=False)
    import importlib, config
    importlib.reload(config)
    assert config.SETUP_DONE is False


def test_setup_done_true_when_set(monkeypatch):
    monkeypatch.setenv("SETUP_DONE", "1")
    import importlib, config
    importlib.reload(config)
    assert config.SETUP_DONE is True


def test_setup_done_true_variants(monkeypatch):
    import importlib, config
    for v in ("1", "true", "yes"):
        monkeypatch.setenv("SETUP_DONE", v)
        importlib.reload(config)
        assert config.SETUP_DONE is True


def test_setup_done_false_variants(monkeypatch):
    import importlib, config
    for v in ("0", "false", "no", ""):
        monkeypatch.setenv("SETUP_DONE", v)
        importlib.reload(config)
        assert config.SETUP_DONE is False
