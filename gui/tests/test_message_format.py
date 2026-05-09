import pytest

from gui.pages._message_format import format_message


def test_incoming_message_basic():
    NOW = 1_000_000
    msg = {"ts": NOW - 30, "node_id": "!aabb", "text": "hello", "is_outgoing": False}
    assert format_message(msg, now=NOW) == "[30s] !aabb: hello"


def test_outgoing_uses_me_label():
    NOW = 1_000_000
    msg = {"ts": NOW - 90, "node_id": "!aabb", "text": "hi", "is_outgoing": True}
    assert format_message(msg, now=NOW) == "[1m] me: hi"


def test_outgoing_with_ack_appends_check():
    NOW = 1_000_000
    msg = {"ts": NOW, "text": "x", "is_outgoing": True, "ack": 1}
    assert format_message(msg, now=NOW) == "[0s] me: x · ✓"


def test_incoming_with_snr_and_hops_renders_metadata():
    NOW = 1_000_000
    msg = {"ts": NOW, "node_id": "!a", "text": "hi", "rx_snr": -5.5, "hop_count": 2}
    out = format_message(msg, now=NOW)
    assert "-5.5dB" in out
    assert "2hop" in out


def test_incoming_zero_hops_omits_hops():
    NOW = 1_000_000
    msg = {"ts": NOW, "node_id": "!a", "text": "hi", "hop_count": 0}
    assert "hop" not in format_message(msg, now=NOW)


def test_incoming_no_snr_omits_snr():
    NOW = 1_000_000
    msg = {"ts": NOW, "node_id": "!a", "text": "hi"}
    assert "dB" not in format_message(msg, now=NOW)


def test_incoming_with_ack_does_not_append_check():
    NOW = 1_000_000
    msg = {"ts": NOW, "node_id": "!a", "text": "x", "is_outgoing": False, "ack": 1}
    assert "✓" not in format_message(msg, now=NOW)


def test_missing_node_id_falls_back_to_question_mark():
    NOW = 1_000_000
    msg = {"ts": NOW, "text": "x", "is_outgoing": False}
    assert format_message(msg, now=NOW) == "[0s] ?: x"


def test_text_strips_and_collapses_newlines():
    NOW = 1_000_000
    msg = {"ts": NOW, "node_id": "!a", "text": "  one\ntwo\n  ", "is_outgoing": False}
    assert format_message(msg, now=NOW) == "[0s] !a: one two"


def test_missing_ts_renders_em_dash():
    msg = {"node_id": "!a", "text": "x", "is_outgoing": False}
    assert format_message(msg, now=1_000_000) == "[—] !a: x"


@pytest.mark.parametrize(
    "delta,expected_age",
    [(0, "0s"), (59, "59s"), (60, "1m"), (3599, "59m"), (3600, "1h"),
     (86399, "23h"), (86400, "1d"), (172800, "2d")],
)
def test_age_buckets(delta, expected_age):
    NOW = 1_000_000
    msg = {"ts": NOW - delta, "node_id": "!a", "text": "x", "is_outgoing": False}
    assert format_message(msg, now=NOW).startswith(f"[{expected_age}]")


def test_negative_delta_clamps_to_zero():
    NOW = 1_000_000
    msg = {"ts": NOW + 999, "node_id": "!a", "text": "x", "is_outgoing": False}
    assert format_message(msg, now=NOW).startswith("[0s]")
