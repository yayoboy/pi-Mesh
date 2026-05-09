"""Telemetry page: per-node history of incoming telemetry packets.

Two-pane layout:
- Left: list of nodes that have ever sent telemetry, sorted by last_heard.
- Right: the recent telemetry rows for the selected node, latest first.
"""

from __future__ import annotations

import asyncio
import logging
import time

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.pages._telemetry_format import format_telemetry_row
from gui.widgets.sparkline import Sparkline

log = logging.getLogger(__name__)


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings
        self._selected_node: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        layout.addWidget(splitter, 1)

        # Left: node list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Nodes"))
        self._nodes = QListWidget(left)
        self._nodes.itemSelectionChanged.connect(self._on_node_selected)
        left_layout.addWidget(self._nodes, 1)
        splitter.addWidget(left)

        # Right: telemetry rows + battery sparkline + export
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        self._right_label = QLabel("Select a node")
        self._right_label.setProperty("role", "muted")
        head.addWidget(self._right_label, 1)
        csv_btn = QPushButton("CSV")
        json_btn = QPushButton("JSON")
        csv_btn.setFixedWidth(46)
        json_btn.setFixedWidth(46)
        csv_btn.clicked.connect(lambda: self._export("csv"))
        json_btn.clicked.connect(lambda: self._export("json"))
        head.addWidget(csv_btn)
        head.addWidget(json_btn)
        right_layout.addLayout(head)

        self._rows = QPlainTextEdit(right)
        self._rows.setReadOnly(True)
        self._rows.setMaximumBlockCount(500)
        f = self._rows.font()
        f.setFamily("monospace")
        self._rows.setFont(f)
        right_layout.addWidget(self._rows, 1)

        spark_row = QHBoxLayout()
        spark_lbl = QLabel("Battery")
        spark_lbl.setProperty("role", "muted")
        spark_row.addWidget(spark_lbl)
        self._spark = Sparkline(capacity=120, color="#4caf50", parent=right)
        self._spark.setMinimumHeight(28)
        spark_row.addWidget(self._spark, 1)
        right_layout.addLayout(spark_row)

        splitter.addWidget(right)
        # ~1/3 nodes list, 2/3 telemetry rows on a 480 px landscape display.
        splitter.setSizes([160, 320])

        self._refresh_nodes()

        if eventbus is not None:
            eventbus.telemetry.connect(self._on_telemetry_event)
            eventbus.node_updated.connect(lambda _e: self._refresh_nodes())

    # ------------------------------------------------------------------

    def _refresh_nodes(self) -> None:
        try:
            import meshtasticd_client
            nodes = meshtasticd_client.get_nodes()
        except Exception:
            nodes = []
        self._nodes.clear()
        for n in sorted(nodes, key=lambda x: -(x.get("last_heard") or 0)):
            label = f"{n.get('short_name') or '?'}  ({n.get('id') or ''})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, n.get("id"))
            self._nodes.addItem(item)

    def _on_node_selected(self) -> None:
        items = self._nodes.selectedItems()
        if not items:
            return
        node_id = items[0].data(Qt.ItemDataRole.UserRole)
        self._selected_node = node_id
        self._right_label.setText(node_id or "")
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._reload_history(node_id))

    async def _reload_history(self, node_id: str) -> None:
        try:
            import config as cfg
            import database
            rows = await database.get_telemetry(cfg.DB_PATH, node_id=node_id, limit=200)
        except Exception:
            log.exception("get_telemetry failed")
            rows = []
        self._rows.clear()
        # Re-populate the battery sparkline from oldest → newest so the
        # rightmost sample is the latest reading.
        self._spark.clear()
        battery_samples: list[tuple[int, float]] = []
        for r in rows:
            self._rows.appendPlainText(format_telemetry_row(r))
            data = r.get("data") or {}
            if r.get("ttype") == "device" and data.get("battery_level") is not None:
                try:
                    battery_samples.append((int(r.get("ts") or 0), float(data["battery_level"])))
                except (TypeError, ValueError):
                    pass
        battery_samples.sort(key=lambda x: x[0])
        for _, v in battery_samples:
            self._spark.push(v)

    @Slot(dict)
    def _on_telemetry_event(self, event: dict) -> None:
        if event.get("id") != self._selected_node:
            return
        row = {
            "ts": event.get("ts") or int(time.time()),
            "ttype": event.get("ttype") or "?",
            "data": event.get("data") or {},
        }
        # Insert at top of the rows view.
        cursor = self._rows.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self._rows.setTextCursor(cursor)
        self._rows.insertPlainText(format_telemetry_row(row) + "\n")
        # Live battery sparkline append.
        if row["ttype"] == "device":
            v = (row.get("data") or {}).get("battery_level")
            if v is not None:
                try:
                    self._spark.push(float(v))
                except (TypeError, ValueError):
                    pass

    # -- Export ---------------------------------------------------------

    def _export(self, fmt: str) -> None:
        if not self._selected_node:
            from gui.widgets.toast import show_toast
            show_toast(self, "Select a node first", role="warn")
            return
        self._do_export(self._selected_node, fmt)

    def _do_export(self, node_id: str, fmt: str) -> None:
        from datetime import datetime
        from pathlib import Path
        out_dir = Path("data/exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_id = node_id.replace("/", "_").replace("!", "")
        out_path = out_dir / f"telemetry-{safe_id}-{datetime.now():%Y%m%d-%H%M%S}.{fmt}"
        try:
            from gui import backend
            content = backend.export_telemetry(fmt, limit=2000)
            out_path.write_text(content, encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"Export error: {exc}")
            return
        from gui.widgets.toast import show_toast
        show_toast(self, f"Saved {out_path.name}", role="ok")
