"""Log page: scrollable view of incoming radio packets, capped to N lines.

Two sources are merged:
- ``meshtasticd_client._log_queue`` for the historical buffer (loaded on
  page open).
- ``EventBus.log_line`` for live updates after that.
"""

from __future__ import annotations

import json
import logging
from typing import Iterable

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QTextCursor, QTextOption
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


_MAX_LINES = 2000


def format_log_line(event: dict) -> str:
    """Render a log event dict as a single human-readable line.

    Mirrors the columns shown in the existing web UI: time placeholder
    delegated to the GUI clock, then "from • SNR • portnum • details".
    """
    src = event.get("from") or event.get("id") or "?"
    snr = event.get("snr")
    snr_s = f"SNR {snr:+.1f}" if isinstance(snr, (int, float)) else "SNR ?"
    port = event.get("portnum") or event.get("decoded_portnum") or "?"
    extra = ""
    if event.get("hop_limit") is not None:
        extra += f" hops={event['hop_limit']}"
    if event.get("text"):
        extra += f" \"{event['text']}\""
    return f"{src} · {snr_s} · {port}{extra}"


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings
        self._paused = False
        self._filter = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Toolbar
        bar = QHBoxLayout()
        self._auto = QCheckBox("Auto-scroll")
        self._auto.setChecked(True)
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.toggled.connect(self._on_pause)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._on_clear)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter (substring)…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_filter)
        self._count = QLabel("0 lines")
        self._count.setProperty("role", "muted")

        bar.addWidget(self._auto)
        bar.addWidget(self._pause_btn)
        bar.addWidget(clear)
        bar.addStretch(1)
        bar.addWidget(self._search)
        bar.addWidget(self._count)
        layout.addLayout(bar)

        # The log view
        self._view = QPlainTextEdit(self)
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(_MAX_LINES)
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._view.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        f = self._view.font()
        f.setFamily("monospace")
        self._view.setFont(f)
        layout.addWidget(self._view, 1)

        self._load_history()

        if eventbus is not None:
            eventbus.log_line.connect(self._on_event)

    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        try:
            import meshtasticd_client
            history = list(meshtasticd_client.get_log_queue())
        except Exception:
            log.exception("could not load log history")
            history = []
        for entry in history:
            self._append(entry)

    def _append(self, event: dict | str) -> None:
        if self._paused:
            return
        if isinstance(event, dict):
            line = format_log_line(event)
        else:
            line = str(event)
        if self._filter and self._filter.lower() not in line.lower():
            return
        self._view.appendPlainText(line)
        if self._auto.isChecked():
            cursor = self._view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._view.setTextCursor(cursor)
        self._update_count()

    def _update_count(self) -> None:
        n = self._view.blockCount()
        self._count.setText(f"{n} line{'s' if n != 1 else ''}")

    # Slots --------------------------------------------------------------

    @Slot(dict)
    def _on_event(self, event: dict) -> None:
        self._append(event)

    @Slot(bool)
    def _on_pause(self, paused: bool) -> None:
        self._paused = paused
        self._pause_btn.setText("Resume" if paused else "Pause")

    @Slot()
    def _on_clear(self) -> None:
        self._view.clear()
        self._update_count()

    @Slot(str)
    def _on_filter(self, text: str) -> None:
        self._filter = text or ""
