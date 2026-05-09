"""Nodes page: card-list adapted for the 320×480 SPI display.

Each row is two lines:
    [short]  long_name
       ↳ snr · batt · hops · dist · age

A QListView with a custom delegate would be more efficient on a large mesh
but a QListWidget with rich-text items is plenty for the few dozen nodes
typical of pi-Mesh deployments and stays trivial to read.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.pages._node_format import fmt_age, fmt_node

log = logging.getLogger(__name__)


def _row_html(node: dict, *, now: int | None = None) -> str:
    short = node.get("short_name") or "?"
    long_name = node.get("long_name") or ""
    age = fmt_age(node.get("last_heard"), now=now)

    parts: list[str] = []
    snr = node.get("snr")
    if snr is not None:
        parts.append(f"SNR {snr:+.1f}")
    batt = node.get("battery_level")
    if batt is not None:
        parts.append(f"{batt}%")
    hops = node.get("hop_count")
    if hops is not None:
        parts.append(f"h={hops}")
    parts.append(fmt_node(node, "dist", now=now))
    parts.append(age)
    sub = " · ".join(parts)

    weight = "700" if node.get("is_local") else "500"
    short_color = "var(--accent)" if node.get("is_local") else "var(--text)"
    return (
        f'<div style="font-weight:{weight}; color:{short_color};">'
        f'  <span style="font-size:13px;">{short}</span>'
        f'  <span style="color:#9aa;font-weight:400;font-size:11px;"> {long_name}</span>'
        f'</div>'
        f'<div style="font-size:10px;color:#7a8090;">{sub}</div>'
    )


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings
        self._filter = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(4)
        self._count = QLabel("0")
        self._count.setProperty("role", "muted")
        f = self._count.font()
        f.setPointSize(9)
        self._count.setFont(f)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("filter…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_filter)
        head.addWidget(self._count)
        head.addWidget(self._search, 1)
        refresh = QPushButton("⟳")
        refresh.setFixedWidth(28)
        refresh.clicked.connect(self._refresh)
        head.addWidget(refresh)
        layout.addLayout(head)

        self._list = QListWidget(self)
        self._list.setUniformItemSizes(False)
        self._list.setSpacing(1)
        self._list.setWordWrap(True)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._list.itemActivated.connect(self._on_activate)
        layout.addWidget(self._list, 1)

        self._nodes: list[dict] = []
        self._refresh()

        if eventbus is not None:
            eventbus.node_updated.connect(self._on_node_event)
            eventbus.position_updated.connect(self._on_node_event)

    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        try:
            import meshtasticd_client
            self._nodes = list(meshtasticd_client.get_nodes())
        except Exception:
            self._nodes = []
        self._render()

    def _render(self) -> None:
        # Sort: local first, then last_heard desc.
        self._nodes.sort(
            key=lambda n: (
                0 if n.get("is_local") else 1,
                -(n.get("last_heard") or 0),
            )
        )
        self._list.clear()
        f = self._filter.lower()
        shown = 0
        for n in self._nodes:
            if f and not _matches(n, f):
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, n.get("id"))
            label = QLabel(_row_html(n))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setStyleSheet("padding:4px;")
            label.setMinimumHeight(34)
            item.setSizeHint(label.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, label)
            shown += 1
        self._count.setText(f"{shown}/{len(self._nodes)}")

    def _upsert(self, event: dict) -> None:
        node_id = event.get("id")
        if not node_id:
            return
        for i, n in enumerate(self._nodes):
            if n.get("id") == node_id:
                self._nodes[i] = {**n, **{k: v for k, v in event.items() if v is not None}}
                self._render()
                return
        self._nodes.append(dict(event))
        self._render()

    # Slots --------------------------------------------------------------

    @Slot(str)
    def _on_filter(self, text: str) -> None:
        self._filter = text or ""
        self._render()

    @Slot(dict)
    def _on_node_event(self, event: dict) -> None:
        self._upsert(event)

    @Slot(QListWidgetItem)
    def _on_activate(self, item: QListWidgetItem) -> None:
        node_id = item.data(Qt.ItemDataRole.UserRole)
        if not node_id:
            return
        # Future: open node detail view. For now, jump to telemetry page.
        win = self.window()
        if hasattr(win, "show_telemetry"):
            win.show_telemetry()


def _matches(node: dict, needle: str) -> bool:
    fields = (
        node.get("id"), node.get("short_name"), node.get("long_name"),
        node.get("hw_model"),
    )
    return any(needle in (f or "").lower() for f in fields)
