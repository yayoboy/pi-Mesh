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
    """Map-pin teardrop, dimmed when no fix.

    Path mirrors the SVG in templates/base.html (viewBox 0 0 24 24, scaled
    to 14×14): pin outline + 2.5 px center circle.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_fix = False

    def set_fix(self, has_fix: bool) -> None:
        self._has_fix = bool(has_fix)
        self._color = QColor("#4caf50") if has_fix else QColor("#9aa")
        self.update()

    def _draw(self, p: QPainter) -> None:
        from PySide6.QtGui import QPainterPath
        pen = QPen(self._color, 1.2)
        p.setPen(pen)
        # Map 24x24 viewBox to 14x14 with a 1 px margin.
        s = 12.0 / 24.0
        ox, oy = 1.0, 1.0

        def x(v: float) -> float: return ox + v * s
        def y(v: float) -> float: return oy + v * s

        # Pin outline: M12 2 C 8.13 2  5 5.13  5 9 C 5 14.25  12 22  12 22 C 12 22  19 14.25  19 9 C 19 5.13  15.87 2  12 2 z
        path = QPainterPath()
        path.moveTo(x(12), y(2))
        path.cubicTo(x(8.13), y(2),    x(5),  y(5.13), x(5),  y(9))
        path.cubicTo(x(5),    y(14.25), x(12), y(22),    x(12), y(22))
        path.cubicTo(x(12),   y(22),    x(19), y(14.25), x(19), y(9))
        path.cubicTo(x(19),   y(5.13),  x(15.87), y(2),  x(12), y(2))
        p.drawPath(path)

        # Center dot — filled when there's a fix, hollow otherwise.
        cx, cy = x(12), y(9)
        r = 2.5 * s
        if self._has_fix:
            p.setBrush(QBrush(self._color))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)


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
