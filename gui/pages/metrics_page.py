"""Metrics page: 4 RPi telemetry cards (CPU%, RAM%, Temp, Uptime) + sparklines.

Subscribes to EventBus.rpi_telemetry. Also polls ``rpi_telemetry.collect()``
every second on its own so the cards update before the WS-broadcast tick.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.sparkline import Sparkline

log = logging.getLogger(__name__)


def _fmt_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    days = s // 86400
    hours = (s % 86400) // 3600
    minutes = (s % 3600) // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class MetricCard(QFrame):
    """Single metric: label, big value, sparkline of recent samples."""

    def __init__(self, title: str, *, suffix: str = "", color: str = "#4a9eff", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._suffix = suffix

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "muted")
        layout.addWidget(title_lbl)

        self._value = QLabel("—")
        f = self._value.font()
        f.setPointSize(20)
        f.setBold(True)
        self._value.setFont(f)
        layout.addWidget(self._value)

        self._spark = Sparkline(capacity=60, color=color, parent=self)
        layout.addWidget(self._spark)

    def update_value(self, value, *, formatter=None) -> None:
        if value is None:
            self._value.setText("—")
            return
        if formatter is not None:
            self._value.setText(formatter(value))
        else:
            self._value.setText(f"{value:.0f}{self._suffix}")
        try:
            self._spark.push(float(value))
        except (TypeError, ValueError):
            self._spark.push(None)


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Raspberry Pi telemetry")
        f = title.font()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._cpu = MetricCard("CPU",  suffix=" %", color="#4caf50")
        self._ram = MetricCard("RAM",  suffix=" %", color="#ff9800")
        self._tmp = MetricCard("Temp", suffix=" °C", color="#f44336")
        self._upt = MetricCard("Uptime")
        grid.addWidget(self._cpu, 0, 0)
        grid.addWidget(self._ram, 0, 1)
        grid.addWidget(self._tmp, 1, 0)
        grid.addWidget(self._upt, 1, 1)
        layout.addLayout(grid, 1)

        # 1-second polling loop directly into rpi_telemetry; it's cheap.
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._poll()

        if eventbus is not None:
            eventbus.rpi_telemetry.connect(self._on_event)

    # ------------------------------------------------------------------

    def _poll(self) -> None:
        try:
            import rpi_telemetry
            data = rpi_telemetry.collect()
        except Exception:
            log.exception("rpi_telemetry.collect failed")
            return
        self._apply(data)

    @Slot(dict)
    def _on_event(self, event: dict) -> None:
        # Backend wraps the payload in {'type': 'rpi_telemetry', 'data': {...}}
        data = event.get("data") if "data" in event else event
        self._apply(data)

    def _apply(self, data: dict) -> None:
        self._cpu.update_value(data.get("cpu_percent"))
        self._ram.update_value(data.get("ram_percent"))
        self._tmp.update_value(data.get("cpu_temp"), formatter=lambda v: f"{v:.1f} °C")
        self._upt.update_value(
            data.get("uptime_seconds"),
            formatter=lambda v: _fmt_uptime(v),
        )
