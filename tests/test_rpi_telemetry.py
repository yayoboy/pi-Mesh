# tests/test_rpi_telemetry.py
"""Tests for power-status fields in rpi_telemetry."""
import rpi_telemetry as rt


def _reset_power_state():
    rt._power_events = 0
    rt._power_last_event_ts = None
    rt._power_prev_active = False


def test_parse_throttled_all_clear():
    p = rt._parse_throttled(0x0)
    assert p['throttled'] == 0
    assert p['undervolt_now'] is False
    assert p['throttle_now'] is False
    assert p['undervolt_boot'] is False
    assert p['throttle_boot'] is False


def test_parse_throttled_sticky_only():
    # 0x50000 = undervoltage + throttling occurred since boot, nothing active
    p = rt._parse_throttled(0x50000)
    assert p['undervolt_now'] is False
    assert p['throttle_now'] is False
    assert p['undervolt_boot'] is True
    assert p['throttle_boot'] is True


def test_parse_throttled_active():
    # 0x50005 = undervoltage + throttling active now, sticky set
    p = rt._parse_throttled(0x50005)
    assert p['undervolt_now'] is True
    assert p['throttle_now'] is True
    assert p['undervolt_boot'] is True
    assert p['throttle_boot'] is True


def test_parse_throttled_unavailable():
    p = rt._parse_throttled(None)
    assert p['throttled'] is None
    assert p['undervolt_now'] is None
    assert p['throttle_now'] is None
    assert p['undervolt_boot'] is None
    assert p['throttle_boot'] is None


def test_collect_counts_power_event_transitions(monkeypatch):
    _reset_power_state()
    seq = iter([0x50005, 0x50005, 0x50000, 0x50005])
    monkeypatch.setattr(rt, '_read_throttled', lambda: next(seq))

    d1 = rt.collect()
    assert d1['power_events'] == 1          # 0 -> active: new event
    assert d1['power_last_event_ts'] == d1['ts']
    d2 = rt.collect()
    assert d2['power_events'] == 1          # still active: no new event
    d3 = rt.collect()
    assert d3['power_events'] == 1          # back to normal
    d4 = rt.collect()
    assert d4['power_events'] == 2          # active again: second event


def test_collect_power_unavailable(monkeypatch):
    _reset_power_state()
    monkeypatch.setattr(rt, '_read_throttled', lambda: None)
    d = rt.collect()
    assert d['throttled'] is None
    assert d['power_events'] == 0
    assert d['power_last_event_ts'] is None
