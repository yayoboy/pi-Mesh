import pytest

from gui.pages._telemetry_format import fmt_age, format_telemetry_row


def test_fmt_age_buckets():
    NOW = 1_000_000
    assert fmt_age(NOW - 30, now=NOW) == "30s"
    assert fmt_age(NOW - 90, now=NOW) == "1m"
    assert fmt_age(NOW - 3600, now=NOW) == "1h"
    assert fmt_age(NOW - 86400, now=NOW) == "1d"
    assert fmt_age(None) == "—"
    assert fmt_age(0) == "—"


def test_format_telemetry_row_basic():
    NOW = 1_000_000
    row = {
        "ts": NOW - 60,
        "ttype": "device",
        "data": {"battery_level": 87, "voltage": 3.8},
    }
    out = format_telemetry_row(row, now=NOW)
    assert out.startswith("[1m] device  ")
    assert "battery_level=87" in out
    assert "voltage=3.8" in out


def test_format_telemetry_row_unknown_ttype_falls_back_to_question_mark():
    out = format_telemetry_row({"ts": 1, "data": {}}, now=2)
    assert "[1s] ?" in out


def test_format_telemetry_row_inlines_nested_dict_as_json():
    out = format_telemetry_row(
        {"ts": 100, "ttype": "x", "data": {"loc": {"lat": 1.0, "lon": 2.0}}},
        now=101,
    )
    assert 'loc={"lat":1.0,"lon":2.0}' in out


def test_format_telemetry_row_caps_pairs():
    data = {f"k{i}": i for i in range(20)}
    out = format_telemetry_row({"ts": 100, "ttype": "t", "data": data}, now=100, max_pairs=3)
    assert out.count("=") == 3
    assert "k0=0" in out and "k2=2" in out and "k3=3" not in out


def test_format_telemetry_row_empty_data():
    out = format_telemetry_row({"ts": 100, "ttype": "t", "data": {}}, now=100)
    assert out.startswith("[0s] t  ")


def test_format_telemetry_row_missing_ts_renders_em_dash():
    out = format_telemetry_row({"ttype": "t", "data": {"k": 1}})
    assert out.startswith("[—]")
