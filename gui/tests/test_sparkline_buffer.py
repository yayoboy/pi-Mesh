import math

import pytest

from gui.widgets.sparkline_buffer import SparklineBuffer


# --- basics -----------------------------------------------------------------

def test_capacity_must_be_at_least_two():
    with pytest.raises(ValueError):
        SparklineBuffer(capacity=1)
    with pytest.raises(ValueError):
        SparklineBuffer(capacity=0)


def test_push_appends_and_caps_at_capacity():
    buf = SparklineBuffer(capacity=3)
    buf.push(1.0)
    buf.push(2.0)
    buf.push(3.0)
    buf.push(4.0)  # evicts 1.0
    assert buf.values() == (2.0, 3.0, 4.0)


def test_extend_pushes_each_value():
    buf = SparklineBuffer(capacity=4)
    buf.extend([10.0, 20.0, 30.0])
    assert buf.values() == (10.0, 20.0, 30.0)


def test_clear_empties_the_buffer():
    buf = SparklineBuffer()
    buf.extend([1.0, 2.0])
    buf.clear()
    assert len(buf) == 0
    assert buf.values() == ()


def test_len_reflects_filled_count():
    buf = SparklineBuffer(capacity=10)
    buf.extend([1.0] * 4)
    assert len(buf) == 4


# --- gaps and bad values ----------------------------------------------------

def test_none_value_is_a_gap():
    buf = SparklineBuffer(capacity=4)
    buf.extend([1.0, None, 3.0])
    assert buf.values() == (1.0, None, 3.0)


def test_nan_and_inf_are_treated_as_gaps():
    buf = SparklineBuffer(capacity=4)
    buf.push(float("nan"))
    buf.push(float("inf"))
    buf.push(float("-inf"))
    assert buf.values() == (None, None, None)


def test_latest_skips_gaps():
    buf = SparklineBuffer()
    buf.extend([1.0, 2.0, None, None])
    assert buf.latest() == 2.0


def test_latest_returns_none_when_only_gaps():
    buf = SparklineBuffer()
    buf.extend([None, None])
    assert buf.latest() is None


def test_latest_returns_none_when_empty():
    assert SparklineBuffer().latest() is None


# --- auto_range -------------------------------------------------------------

def test_auto_range_returns_min_max_of_finite_values():
    buf = SparklineBuffer()
    buf.extend([3.0, 1.0, None, 9.0, 5.0])
    assert buf.auto_range() == (1.0, 9.0)


def test_auto_range_pads_zero_span():
    buf = SparklineBuffer()
    buf.extend([7.0, 7.0, 7.0])
    lo, hi = buf.auto_range()
    assert lo < 7.0 < hi


def test_auto_range_returns_fallback_when_no_finite():
    buf = SparklineBuffer()
    buf.extend([None, None])
    assert buf.auto_range(fallback=(2.0, 8.0)) == (2.0, 8.0)


def test_auto_range_returns_fallback_when_empty():
    assert SparklineBuffer().auto_range() == (0.0, 1.0)


# --- normalize_points -------------------------------------------------------

def test_normalize_points_empty_returns_empty():
    assert SparklineBuffer().normalize_points(100, 50) == []


def test_normalize_points_single_sample_returns_empty():
    buf = SparklineBuffer()
    buf.push(5.0)
    assert buf.normalize_points(100, 50) == []


def test_normalize_points_x_spans_full_width():
    buf = SparklineBuffer()
    buf.extend([0.0, 1.0])
    pts = buf.normalize_points(100, 50)
    assert pts[0][0] == pytest.approx(0.0)
    assert pts[-1][0] == pytest.approx(99.0)


def test_normalize_points_y_inverted_origin():
    buf = SparklineBuffer()
    buf.extend([0.0, 1.0])  # auto_range → (0, 1)
    pts = buf.normalize_points(100, 50)
    # Lowest value -> bottom of widget (y = height-1)
    assert pts[0][1] == pytest.approx(49.0)
    # Highest value -> top of widget (y = 0)
    assert pts[1][1] == pytest.approx(0.0)


def test_normalize_points_clamps_outside_explicit_range():
    buf = SparklineBuffer()
    buf.extend([-100.0, 999.0])  # explicit y_range = (0, 100)
    pts = buf.normalize_points(50, 100, y_range=(0.0, 100.0))
    # Both values out of range, clamped: lowest=49 (bottom), highest=0 (top)
    assert pts[0][1] == pytest.approx(99.0)
    assert pts[1][1] == pytest.approx(0.0)


def test_normalize_points_preserves_gaps_as_none():
    buf = SparklineBuffer()
    buf.extend([0.0, None, 1.0])
    pts = buf.normalize_points(100, 50)
    assert pts[0] is not None
    assert pts[1] is None
    assert pts[2] is not None


def test_normalize_points_invalid_size_raises():
    buf = SparklineBuffer()
    buf.extend([1.0, 2.0])
    with pytest.raises(ValueError):
        buf.normalize_points(0, 50)
    with pytest.raises(ValueError):
        buf.normalize_points(100, 1)


# --- polylines (gap-aware) --------------------------------------------------

def test_polylines_no_gaps_returns_one_run():
    buf = SparklineBuffer()
    buf.extend([1.0, 2.0, 3.0])
    runs = buf.polylines(100, 50)
    assert len(runs) == 1
    assert len(runs[0]) == 3


def test_polylines_splits_on_gap():
    buf = SparklineBuffer()
    buf.extend([1.0, 2.0, None, 3.0, 4.0])
    runs = buf.polylines(100, 50)
    assert len(runs) == 2
    assert len(runs[0]) == 2
    assert len(runs[1]) == 2


def test_polylines_drops_orphan_singletons():
    buf = SparklineBuffer()
    # 1 alone between two gaps -> nothing drawable for that point
    buf.extend([None, 1.0, None, 2.0, 3.0])
    runs = buf.polylines(100, 50)
    assert len(runs) == 1
    assert len(runs[0]) == 2


def test_polylines_handles_all_gaps():
    buf = SparklineBuffer()
    buf.extend([None, None, None])
    assert buf.polylines(100, 50) == []
