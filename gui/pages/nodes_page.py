"""Nodes page: sortable list of mesh nodes with live updates from EventBus."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QSortFilterProxyModel,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui.pages._node_format import fmt_node


# Columns in the order they appear in the table.
_COLUMNS = [
    ("short", "Short"),
    ("long",  "Long name"),
    ("snr",   "SNR"),
    ("batt",  "Batt"),
    ("hops",  "Hops"),
    ("dist",  "Dist km"),
    ("seen",  "Last seen"),
]


class NodesModel(QAbstractTableModel):
    """Holds the list of node dicts; one row per node."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_nodes(self, nodes: list[dict]) -> None:
        # Local node first, then sort by last_heard descending.
        sorted_nodes = sorted(
            nodes,
            key=lambda n: (
                0 if n.get("is_local") else 1,
                -(n.get("last_heard") or 0),
            ),
        )
        self.beginResetModel()
        self._rows = sorted_nodes
        self.endResetModel()

    def upsert_node(self, node: dict) -> None:
        node_id = node.get("id")
        if not node_id:
            return
        for i, existing in enumerate(self._rows):
            if existing.get("id") == node_id:
                merged = {**existing, **{k: v for k, v in node.items() if v is not None}}
                self._rows[i] = merged
                top = self.index(i, 0)
                bottom = self.index(i, len(_COLUMNS) - 1)
                self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole])
                return
        # New node: append.
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(node)
        self.endInsertRows()

    def node_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    # Qt model API ----------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        if not (0 <= row < len(self._rows)):
            return None
        node = self._rows[row]
        col_key, _ = _COLUMNS[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            return fmt_node(node, col_key)
        if role == Qt.ItemDataRole.FontRole and node.get("is_local"):
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ItemDataRole.UserRole:
            return node.get("id")
        return None

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section][1]
        return None


class Page(QWidget):
    """Nodes page widget."""

    node_double_clicked = Signal(str)

    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header: search + count
        header = QHBoxLayout()
        self._count = QLabel("0 nodes")
        self._count.setProperty("role", "muted")
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by name or id…")
        self._search.setClearButtonEnabled(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        header.addWidget(self._count)
        header.addStretch(1)
        header.addWidget(self._search)
        header.addWidget(refresh)
        layout.addLayout(header)

        # Model + sortable proxy + table
        self._model = NodesModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # all columns
        self._search.textChanged.connect(self._proxy.setFilterFixedString)

        self._table = QTableView(self)
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table, 1)

        self._refresh()

        # Wire eventbus
        if self._eventbus is not None:
            self._eventbus.node_updated.connect(self._on_node_event)
            self._eventbus.position_updated.connect(self._on_node_event)

    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        try:
            import meshtasticd_client
            nodes = meshtasticd_client.get_nodes()
        except Exception:
            nodes = []
        self._model.set_nodes(nodes)
        self._update_count()

    def _update_count(self) -> None:
        n = self._model.rowCount()
        self._count.setText(f"{n} node{'s' if n != 1 else ''}")

    @Slot(dict)
    def _on_node_event(self, event: dict) -> None:
        self._model.upsert_node(event)
        self._update_count()

    @Slot(QModelIndex)
    def _on_double_click(self, idx: QModelIndex) -> None:
        source = self._proxy.mapToSource(idx)
        node = self._model.node_at(source.row())
        if node and node.get("id"):
            self.node_double_clicked.emit(node["id"])
