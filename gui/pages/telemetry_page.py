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
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.pages._telemetry_format import format_telemetry_row

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

        # Right: telemetry rows
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_label = QLabel("Select a node")
        self._right_label.setProperty("role", "muted")
        right_layout.addWidget(self._right_label)
        self._rows = QPlainTextEdit(right)
        self._rows.setReadOnly(True)
        self._rows.setMaximumBlockCount(500)
        f = self._rows.font()
        f.setFamily("monospace")
        self._rows.setFont(f)
        right_layout.addWidget(self._rows, 1)
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
            rows = await database.get_telemetry(cfg.DB_PATH, node_id=node_id, limit=100)
        except Exception:
            log.exception("get_telemetry failed")
            rows = []
        self._rows.clear()
        for r in rows:
            self._rows.appendPlainText(format_telemetry_row(r))

    @Slot(dict)
    def _on_telemetry_event(self, event: dict) -> None:
        if event.get("id") != self._selected_node:
            return
        # Synthesize a row so format matches.
        row = {
            "ts": event.get("ts") or int(time.time()),
            "ttype": event.get("ttype") or "?",
            "data": event.get("data") or {},
        }
        # Insert at top.
        cursor = self._rows.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self._rows.setTextCursor(cursor)
        self._rows.insertPlainText(format_telemetry_row(row) + "\n")
