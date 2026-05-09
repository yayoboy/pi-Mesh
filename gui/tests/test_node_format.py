import pytest

from gui.pages._node_format import fmt_age, fmt_node


# --- fmt_age ----------------------------------------------------------------

@pytest.mark.parametrize(
    "delta_seconds,expected",
    [
        (0,        "0s"),
        (45,       "45s"),
        (60,       "1m"),
        (599,      "9m"),
        (3600,     "1h"),
        (3600 * 5, "5h"),
        (86400,    "1d"),
        (86400 * 3, "3d"),
    ],
)
def test_fmt_age_buckets(delta_seconds, expected):
    NOW = 1_000_000
    assert fmt_age(NOW - delta_seconds, now=NOW) == expected


def test_fmt_age_clamps_negative_delta_to_zero():
    NOW = 1_000_000
    assert fmt_age(NOW + 999, now=NOW) == "0s"


def test_fmt_age_none_or_zero_returns_dash():
    assert fmt_age(None) == "—"
    assert fmt_age(0) == "—"


# --- fmt_node ---------------------------------------------------------------

def test_fmt_node_short_falls_back_to_question_mark():
    assert fmt_node({}, "short") == "?"
    assert fmt_node({"short_name": ""}, "short") == "?"
    assert fmt_node({"short_name": "ABC"}, "short") == "ABC"


def test_fmt_node_long_returns_empty_when_missing():
    assert fmt_node({}, "long") == ""
    assert fmt_node({"long_name": "Big Node"}, "long") == "Big Node"


def test_fmt_node_snr_one_decimal():
    assert fmt_node({"snr": 8.456}, "snr") == "8.5"
    assert fmt_node({"snr": -3.1}, "snr") == "-3.1"
    assert fmt_node({}, "snr") == "—"


def test_fmt_node_battery_percent():
    assert fmt_node({"battery_level": 75}, "batt") == "75%"
    assert fmt_node({}, "batt") == "—"


def test_fmt_node_hops_integer():
    assert fmt_node({"hop_count": 0}, "hops") == "0"
    assert fmt_node({"hop_count": 3}, "hops") == "3"
    assert fmt_node({}, "hops") == "—"


def test_fmt_node_distance_km_or_meters():
    assert fmt_node({"distance_km": 0.5},  "dist") == "500 m"
    assert fmt_node({"distance_km": 0.05}, "dist") == "50 m"
    assert fmt_node({"distance_km": 1.0},  "dist") == "1.0"
    assert fmt_node({"distance_km": 12.34}, "dist") == "12.3"
    assert fmt_node({}, "dist") == "—"


def test_fmt_node_last_heard_uses_now_kw():
    assert fmt_node({"last_heard": 999_999_900}, "seen", now=1_000_000_000) == "1m"
    assert fmt_node({"last_heard": None}, "seen") == "—"


def test_fmt_node_unknown_key_returns_empty():
    assert fmt_node({"short_name": "X"}, "nonsense") == ""
