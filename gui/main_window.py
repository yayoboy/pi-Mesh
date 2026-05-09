"""MainWindow: status bar (top) + tab content stack + tab bar (bottom).

Each tab is a lazily-imported page module exposing a ``Page(QWidget)`` class
that takes ``(eventbus, settings)`` in its constructor. Lazy import lets
heavier pages (map, metrics) defer their work until the tab is first opened.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


# (label, module path). Module must define a ``Page`` class.
_TABS: list[tuple[str, str]] = [
    ("Nodes",     "gui.pages.nodes_page"),
    ("Map",       "gui.pages.map_page"),
    ("Messages",  "gui.pages.messages_page"),
    ("Config",    "gui.pages.config_page"),
    ("Metrics",   "gui.pages.metrics_page"),
    ("Log",       "gui.pages.log_page"),
    ("Telemetry", "gui.pages.telemetry_page"),
]


class StatusBar(QFrame):
    """Top bar: connection state, node count, local node id."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statusbar")
        self.setFixedHeight(28)

        self._connection = QLabel("…")
        self._connection.setProperty("role", "muted")
        self._nodes = QLabel("")
        self._nodes.setProperty("role", "muted")
        self._local = QLabel("")
        self._local.setProperty("role", "muted")
        self._local.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(12)
        layout.addWidget(self._connection)
        layout.addWidget(self._nodes)
        layout.addStretch(1)
        layout.addWidget(self._local)

    def update_state(self, *, connected: bool, node_count: int, local_id: str) -> None:
        if connected:
            self._connection.setText("● connected")
            self._connection.setProperty("role", "ok")
        else:
            self._connection.setText("○ offline")
            self._connection.setProperty("role", "danger")
        # Re-polish so the property change re-applies the role-dependent QSS.
        self._connection.style().unpolish(self._connection)
        self._connection.style().polish(self._connection)

        self._nodes.setText(f"{node_count} node{'s' if node_count != 1 else ''}")
        self._local.setText(local_id or "")


class TabBar(QFrame):
    """Bottom tab bar: row of touch-friendly buttons, one per page."""

    def __init__(self, labels: list[str], on_select, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tabbar")
        self.setFixedHeight(44)

        self._buttons: list[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(60)
            btn.clicked.connect(lambda _checked, idx=i: on_select(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

    def set_active(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pi-Mesh")
        self.resize(QSize(800, 480))

        self._eventbus = None
        self._settings = None

        # Layout
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._status = StatusBar(central)
        self._stack = QStackedWidget(central)
        self._tabs = TabBar([label for label, _ in _TABS], self._select_tab, central)

        root.addWidget(self._status)
        root.addWidget(self._stack, 1)
        root.addWidget(self._tabs)
        self.setCentralWidget(central)

        # Page registry: index -> (label, module_path, instance|None)
        self._pages: list[tuple[str, str, QWidget | None]] = [
            (label, module, None) for label, module in _TABS
        ]

        # Periodic status refresh — cheap, drives the offline → online transition.
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

    def attach(self, eventbus, settings) -> None:
        """Wire the event bus and settings cache into the window."""
        self._eventbus = eventbus
        self._settings = settings
        # Lazy: pages are constructed on first activation.
        self._select_tab(0)

    def _select_tab(self, index: int) -> None:
        label, module_path, instance = self._pages[index]
        if instance is None:
            instance = self._build_page(module_path, label)
            self._pages[index] = (label, module_path, instance)
            self._stack.addWidget(instance)
        self._stack.setCurrentWidget(instance)
        self._tabs.set_active(index)

    def _build_page(self, module_path: str, label: str) -> QWidget:
        try:
            mod = __import__(module_path, fromlist=["Page"])
            page = mod.Page(self._eventbus, self._settings)
            return page
        except Exception as exc:
            log.exception("failed to build page %s", module_path)
            from gui.pages._stub import StubPage
            return StubPage(label, error=str(exc))

    def _refresh_status(self) -> None:
        try:
            import meshtasticd_client
            self._status.update_state(
                connected=meshtasticd_client.is_connected(),
                node_count=len(meshtasticd_client.get_nodes()),
                local_id=meshtasticd_client.get_local_id(),
            )
        except Exception:
            log.debug("status refresh failed", exc_info=True)
