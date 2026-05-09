"""Sparkline widget: thin wrapper over ``SparklineBuffer`` that paints a polyline.

The math (sample buffer, gap handling, autoscale, x/y mapping) lives in
``sparkline_buffer.py``; this widget owns only the QPainter calls.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from gui.widgets.sparkline_buffer import SparklineBuffer


class Sparkline(QWidget):
    def __init__(self, capacity: int = 60, color: str = "#4a9eff", parent=None):
        super().__init__(parent)
        self._buffer = SparklineBuffer(capacity=capacity)
        self._color = QColor(color)
        self.setMinimumHeight(28)

    def push(self, value: float | None) -> None:
        self._buffer.push(value)
        self.update()

    def latest(self) -> float | None:
        return self._buffer.latest()

    def clear(self) -> None:
        self._buffer.clear()
        self.update()

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event):
        w = max(2, self.width())
        h = max(2, self.height())
        runs = self._buffer.polylines(w, h)
        if not runs:
            return
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(self._color)
            pen.setWidthF(1.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for run in runs:
                if len(run) < 2:
                    continue
                for i in range(len(run) - 1):
                    x1, y1 = run[i]
                    x2, y2 = run[i + 1]
                    p.drawLine(int(x1), int(y1), int(x2), int(y2))
        finally:
            p.end()
