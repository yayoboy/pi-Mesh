"""Vector icons for the status bar — drawn with QPainter so they survive
across distros that lack the right Unicode font glyphs.

Each icon is a small QWidget that paints a 14×14 area. The visual style is
deliberately monochromatic and matches the SVG paths in templates/base.html.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget


class _IconBase(QWidget):
    """14×14 monochrome icon. Subclasses implement ``_draw(painter)``."""

    SIZE = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(self.SIZE, self.SIZE))
        self._color = QColor("#9aa")
        self._tooltip = ""

    def set_color(self, color: str) -> None:
        if QColor(color) == self._color:
            return
        self._color = QColor(color)
        self.update()

    def set_tooltip(self, tooltip: str) -> None:
        self._tooltip = tooltip
        self.setToolTip(tooltip)

    def paintEvent(self, _event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw(p)
        finally:
            p.end()

    def _draw(self, _p: QPainter) -> None:
        raise NotImplementedError


class BatteryIcon(_IconBase):
    """Outline + variable fill from 0..1."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 1.0  # 0..1

    def set_level(self, level: float | None) -> None:
        self._level = max(0.0, min(1.0, level)) if level is not None else 0.0
        self._color = (
            QColor("#9aa") if level is None
            else QColor("#f44336") if level < 0.2
            else QColor("#ff9800") if level < 0.5
            else QColor("#4caf50")
        )
        self.update()

    def _draw(self, p: QPainter) -> None:
        pen = QPen(self._color, 1.0)
        p.setPen(pen)
        # Battery body 1..11, height 4..10 (centered).
        p.drawRect(1, 4, 10, 6)
        p.drawRect(11, 6, 1, 2)  # nub
        if self._level > 0:
            inner_w = max(1, int(8 * self._level))
            p.fillRect(2, 5, inner_w, 4, QBrush(self._color))


class SignalIcon(_IconBase):
    """Four ascending bars; ``set_strength(snr)`` fills 0..4 from SNR."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars = 0  # 0..4

    def set_strength(self, snr: float | None) -> None:
        if snr is None:
            self._bars = 0
            self._color = QColor("#9aa")
        else:
            self._bars = (
                4 if snr > 5
                else 3 if snr > 0
                else 2 if snr > -5
                else 1 if snr > -10
                else 0
            )
            self._color = (
                QColor("#4caf50") if self._bars >= 3
                else QColor("#ff9800") if self._bars == 2
                else QColor("#f44336") if self._bars == 1
                else QColor("#9aa")
            )
        self.update()

    def _draw(self, p: QPainter) -> None:
        for i in range(4):
            x = 1 + i * 3
            h = 2 + i * 3  # 2,5,8,11
            y = 12 - h
            color = self._color if i < self._bars else QColor(self._color.red(), self._color.green(), self._color.blue(), 60)
            p.fillRect(x, y, 2, h, color)


class GpsIcon(_IconBase):
    """Pin + dot inside, dimmed when no fix."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_fix = False

    def set_fix(self, has_fix: bool) -> None:
        self._has_fix = bool(has_fix)
        self._color = QColor("#4caf50") if has_fix else QColor("#9aa")
        self.update()

    def _draw(self, p: QPainter) -> None:
        pen = QPen(self._color, 1.5)
        p.setPen(pen)
        # Stylized teardrop pin: triangle below, circle on top.
        path = QPolygonF([QPointF(7, 13), QPointF(2, 6), QPointF(12, 6)])
        p.drawPolyline(path)
        p.drawEllipse(4, 1, 6, 6)
        if self._has_fix:
            p.setBrush(QBrush(self._color))
            p.drawEllipse(6, 3, 2, 2)


class ConnIcon(_IconBase):
    """Filled dot when connected, ring when offline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False

    def set_connected(self, connected: bool) -> None:
        self._connected = bool(connected)
        self._color = QColor("#4caf50") if connected else QColor("#f44336")
        self.update()

    def _draw(self, p: QPainter) -> None:
        pen = QPen(self._color, 1.5)
        p.setPen(pen)
        if self._connected:
            p.setBrush(QBrush(self._color))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(2, 2, 10, 10)
