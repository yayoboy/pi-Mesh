"""Metrics page: RPi telemetry cards + per-node board telemetry + exports.

Two stacked sections:
- Raspberry Pi: CPU%, RAM%, Temp, Uptime (sparklines), plus disk usage bar.
- Board Meshtastic: per-node summary cards (battery, voltage, temp,
  humidity, pressure …) populated from /api/telemetry/latest.

CSV / JSON export buttons hit /api/export/telemetry and stash the file
under ``data/exports/`` for retrieval over the LAN.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.sparkline import Sparkline

log = logging.getLogger(__name__)


def _schedule(coro) -> None:
    loop = asyncio.get_event_loop_policy().get_event_loop()
    if loop.is_running():
        loop.create_task(coro)


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


class _NodeTelemetryCard(QFrame):
    """One row per node: short name + battery / voltage / env metrics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(2)

        self._title = QLabel("?")
        f = self._title.font()
        f.setBold(True)
        self._title.setFont(f)
        self._layout.addWidget(self._title)

        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(8)
        self._layout.addLayout(self._metrics_row)
        self._labels: list[QLabel] = []

    def _ensure_labels(self, count: int) -> None:
        while len(self._labels) < count:
            l = QLabel("")
            l.setProperty("role", "muted")
            f = l.font()
            f.setPointSize(8)
            l.setFont(f)
            self._labels.append(l)
            self._metrics_row.addWidget(l)
        for extra in self._labels[count:]:
            extra.setText("")

    def fill(self, info: dict) -> None:
        self._title.setText(info.get("short_name") or "?")
        device = (info.get("device") or {}).get("data") or {}
        env = (info.get("environment") or {}).get("data") or {}

        cells: list[str] = []
        if device.get("battery_level") is not None:
            cells.append(f"🔋 {device['battery_level']}%")
        if device.get("voltage") is not None:
            cells.append(f"⚡ {device['voltage']:.2f}V")
        if env.get("temperature") is not None:
            cells.append(f"🌡 {env['temperature']:.1f}°C")
        if env.get("relative_humidity") is not None:
            cells.append(f"💧 {env['relative_humidity']:.0f}%")
        if env.get("barometric_pressure") is not None:
            cells.append(f"📶 {env['barometric_pressure']:.0f}hPa")
        self._ensure_labels(len(cells))
        for lbl, text in zip(self._labels, cells):
            lbl.setText(text)


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings
        self._node_cards: dict[str, _NodeTelemetryCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # ---- Raspberry Pi section
        rpi_title = QLabel("Raspberry Pi")
        f = rpi_title.font()
        f.setPointSize(11); f.setBold(True)
        rpi_title.setFont(f)
        rpi_title.setProperty("role", "muted")
        layout.addWidget(rpi_title)

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
        layout.addLayout(grid)

        # Disk bar
        disk_row = QFrame()
        disk_row.setFrameShape(QFrame.Shape.StyledPanel)
        dr = QVBoxLayout(disk_row)
        dr.setContentsMargins(8, 4, 8, 4)
        dr.setSpacing(2)
        head = QHBoxLayout()
        head.addWidget(QLabel("Disk"))
        self._disk_value = QLabel("—")
        self._disk_value.setProperty("role", "muted")
        head.addStretch(1)
        head.addWidget(self._disk_value)
        dr.addLayout(head)
        self._disk_bar = QProgressBar()
        self._disk_bar.setRange(0, 100)
        self._disk_bar.setValue(0)
        self._disk_bar.setTextVisible(False)
        self._disk_bar.setFixedHeight(6)
        dr.addWidget(self._disk_bar)
        layout.addWidget(disk_row)

        # ---- Board Meshtastic section
        board_head = QHBoxLayout()
        board_title = QLabel("Board Meshtastic")
        f = board_title.font()
        f.setPointSize(11); f.setBold(True)
        board_title.setFont(f)
        board_title.setProperty("role", "muted")
        board_head.addWidget(board_title)
        board_head.addStretch(1)
        csv_btn = QPushButton("CSV")
        json_btn = QPushButton("JSON")
        csv_btn.setFixedWidth(48)
        json_btn.setFixedWidth(48)
        csv_btn.clicked.connect(lambda: self._export("csv"))
        json_btn.clicked.connect(lambda: self._export("json"))
        board_head.addWidget(csv_btn)
        board_head.addWidget(json_btn)
        layout.addLayout(board_head)

        self._node_cards_host = QWidget()
        self._node_cards_layout = QVBoxLayout(self._node_cards_host)
        self._node_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._node_cards_layout.setSpacing(4)
        layout.addWidget(self._node_cards_host)

        self._empty_label = QLabel("No telemetry yet")
        self._empty_label.setProperty("role", "muted")
        layout.addWidget(self._empty_label)

        layout.addStretch(1)

        # 1-second polling loop for rpi telemetry; cheap.
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._poll()

        # Less frequent pull for /api/telemetry/latest (board side).
        self._board_timer = QTimer(self)
        self._board_timer.setInterval(5000)
        self._board_timer.timeout.connect(lambda: _schedule(self._refresh_board()))
        self._board_timer.start()
        _schedule(self._refresh_board())

        if eventbus is not None:
            eventbus.rpi_telemetry.connect(self._on_event)
            eventbus.telemetry.connect(lambda _e: _schedule(self._refresh_board()))

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
        disk_pct = data.get("disk_percent")
        if disk_pct is not None:
            self._disk_bar.setValue(int(disk_pct))
        if data.get("disk_used_mb") is not None and data.get("disk_total_mb"):
            self._disk_value.setText(
                f"{data['disk_used_mb']} / {data['disk_total_mb']} MB"
            )

    async def _refresh_board(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get("http://127.0.0.1:8080/api/telemetry/latest")
            data = r.json() if r.status_code == 200 else {}
        except Exception:
            log.debug("board telemetry refresh failed", exc_info=True)
            return

        # Reuse / create / drop cards keyed by node id.
        seen = set()
        for nid, info in data.items():
            seen.add(nid)
            card = self._node_cards.get(nid)
            if card is None:
                card = _NodeTelemetryCard(self._node_cards_host)
                self._node_cards_layout.addWidget(card)
                self._node_cards[nid] = card
            card.fill(info)
        for nid in list(self._node_cards.keys()):
            if nid not in seen:
                w = self._node_cards.pop(nid)
                self._node_cards_layout.removeWidget(w)
                w.deleteLater()
        self._empty_label.setVisible(len(self._node_cards) == 0)

    # ------------------------------------------------------------------

    def _export(self, fmt: str) -> None:
        _schedule(self._export_async(fmt))

    async def _export_async(self, fmt: str) -> None:
        from datetime import datetime
        out_dir = Path("data/exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"telemetry-{datetime.now():%Y%m%d-%H%M%S}.{fmt}"
        url = f"http://127.0.0.1:8080/api/export/telemetry?format={fmt}&limit=1000"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.get(url)
            if r.status_code != 200:
                QMessageBox.warning(self, "Export", f"Export failed: {r.status_code}")
                return
            out_path.write_bytes(r.content)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"Export error: {exc}")
            return
        from gui.widgets.toast import show_toast
        show_toast(self, f"Saved {out_path.name}", role="ok")
