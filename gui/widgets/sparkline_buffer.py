"""Pure-Python sparkline data buffer.

Backs the metric cards on the Metrics page (CPU%, RAM%, temperature, …).
The Qt-side widget (paintEvent) is a thin wrapper that asks this buffer for
the polyline points to draw; keeping the math here means we can unit-test
autoscale, gap handling and value-to-pixel mapping without a display server.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Iterable


class SparklineBuffer:
    """Fixed-capacity ring of float samples, with cached min/max for autoscale.

    None values are accepted and rendered as gaps (they don't enter min/max).
    """

    def __init__(self, capacity: int = 60):
        if capacity < 2:
            raise ValueError("capacity must be >= 2 to draw a line")
        self._capacity = capacity
        self._values: deque[float | None] = deque(maxlen=capacity)

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._values)

    def push(self, value: float | None) -> None:
        if value is not None and not math.isfinite(value):
            value = None  # NaN / inf are gaps, not data points
        self._values.append(value)

    def extend(self, values: Iterable[float | None]) -> None:
        for v in values:
            self.push(v)

    def clear(self) -> None:
        self._values.clear()

    def values(self) -> tuple[float | None, ...]:
        return tuple(self._values)

    def latest(self) -> float | None:
        for v in reversed(self._values):
            if v is not None:
                return v
        return None

    def auto_range(self, fallback: tuple[float, float] = (0.0, 1.0)) -> tuple[float, float]:
        """Return (min, max) of finite values; pad zero-range with 1.0 below/above.

        Useful so a flat line still gets a visible chart area.
        """
        finite = [v for v in self._values if v is not None]
        if not finite:
            return fallback
        lo, hi = min(finite), max(finite)
        if lo == hi:
            return lo - 1.0, hi + 1.0
        return lo, hi

    def normalize_points(
        self,
        width: int,
        height: int,
        y_range: tuple[float, float] | None = None,
    ) -> list[tuple[float, float] | None]:
        """Return one (x, y) per sample (or ``None`` for gaps).

        - x advances uniformly so the newest sample lands at ``width - 1``.
        - y is inverted (Qt origin at top-left): ``y = (1 - norm) * (height - 1)``.
        - Empty / single-sample buffers return an empty list (nothing to draw).
        """
        if width < 2 or height < 2:
            raise ValueError("width and height must be >= 2")
        n = len(self._values)
        if n < 2:
            return []
        lo, hi = y_range if y_range is not None else self.auto_range()
        span = (hi - lo) or 1.0
        # Map sample index 0..n-1 onto x [0..width-1].
        x_step = (width - 1) / (n - 1)
        out: list[tuple[float, float] | None] = []
        for i, v in enumerate(self._values):
            if v is None:
                out.append(None)
                continue
            norm = (v - lo) / span
            # Clamp values outside y_range so we never draw outside the widget.
            norm = max(0.0, min(1.0, norm))
            x = i * x_step
            y = (1.0 - norm) * (height - 1)
            out.append((x, y))
        return out

    def polylines(
        self,
        width: int,
        height: int,
        y_range: tuple[float, float] | None = None,
    ) -> list[list[tuple[float, float]]]:
        """Split ``normalize_points`` on gaps and return drawable polylines.

        A polyline is a list of ≥2 points; runs of length 1 (a lone sample
        between two gaps) are dropped because there's nothing to draw.
        """
        points = self.normalize_points(width, height, y_range)
        runs: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        for p in points:
            if p is None:
                if len(current) >= 2:
                    runs.append(current)
                current = []
            else:
                current.append(p)
        if len(current) >= 2:
            runs.append(current)
        return runs
