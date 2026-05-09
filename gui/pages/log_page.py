"""Log page: scrollable view of incoming radio packets, capped to N lines.

Two sources are merged:
- ``meshtasticd_client._log_queue`` for the historical buffer (loaded on
  page open).
- ``EventBus.log_line`` for live updates after that.

Toolbar provides Pause/Resume, Clear, Auto-scroll, substring filter, a
row of portnum toggle pills (auto-populated as new types are seen) and
a TSV export button.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QTextCursor, QTextOption
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
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
        self._portnum_filters: set[str] = set()    # active filter set; empty = no filter
        self._known_portnums: set[str] = set()
        self._lines: list[dict] = []                # raw events kept for TSV export

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Top toolbar — Pause / Clear / Auto-scroll / search / count.
        bar = QHBoxLayout()
        self._auto = QCheckBox("Auto")
        self._auto.setChecked(True)
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.toggled.connect(self._on_pause)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._on_clear)
        export_btn = QPushButton("TSV")
        export_btn.setToolTip("Export filtered lines as TSV")
        export_btn.clicked.connect(self._on_export)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_filter)
        self._count = QLabel("0")
        self._count.setProperty("role", "muted")

        bar.addWidget(self._auto)
        bar.addWidget(self._pause_btn)
        bar.addWidget(clear)
        bar.addWidget(export_btn)
        bar.addStretch(1)
        bar.addWidget(self._search)
        bar.addWidget(self._count)
        layout.addLayout(bar)

        # Portnum filter pills row (populates dynamically).
        self._pills_row = QHBoxLayout()
        self._pills_row.setSpacing(2)
        layout.addLayout(self._pills_row)

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
            portnum = event.get("portnum") or event.get("decoded_portnum") or ""
            if portnum:
                self._maybe_add_pill(portnum)
            self._lines.append(event)
        else:
            line = str(event)
            portnum = ""
            self._lines.append({"text": line})

        if self._filter and self._filter.lower() not in line.lower():
            return
        if self._portnum_filters and (portnum not in self._portnum_filters):
            return
        self._view.appendPlainText(line)
        if self._auto.isChecked():
            cursor = self._view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._view.setTextCursor(cursor)
        self._update_count()

    def _maybe_add_pill(self, portnum: str) -> None:
        if portnum in self._known_portnums:
            return
        self._known_portnums.add(portnum)
        btn = QToolButton(self)
        # Shorten APP_TEXT_MESSAGE → TEXT, etc., for the pill label.
        short = portnum.replace("_APP", "").replace("APP", "").lstrip("_")
        btn.setText(short or portnum[:6])
        btn.setToolTip(portnum)
        btn.setCheckable(True)
        btn.toggled.connect(lambda checked, p=portnum: self._on_pill(p, checked))
        f = btn.font()
        f.setPointSize(8)
        btn.setFont(f)
        self._pills_row.addWidget(btn)

    def _on_pill(self, portnum: str, checked: bool) -> None:
        if checked:
            self._portnum_filters.add(portnum)
        else:
            self._portnum_filters.discard(portnum)
        self._rerender()

    def _rerender(self) -> None:
        # Re-apply current filters against the cached lines.
        self._view.clear()
        was_auto = self._auto.isChecked()
        self._auto.setChecked(False)
        try:
            for ev in self._lines:
                line = format_log_line(ev) if isinstance(ev, dict) else ev.get("text", "")
                if self._filter and self._filter.lower() not in line.lower():
                    continue
                if self._portnum_filters:
                    portnum = ev.get("portnum") or ev.get("decoded_portnum") or ""
                    if portnum not in self._portnum_filters:
                        continue
                self._view.appendPlainText(line)
        finally:
            self._auto.setChecked(was_auto)
        if was_auto:
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
        self._rerender()

    def _on_export(self) -> None:
        out_dir = Path("data/exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"log-{datetime.now():%Y%m%d-%H%M%S}.tsv"
        try:
            with out_path.open("w", encoding="utf-8") as f:
                f.write("ts\tfrom\tportnum\tsnr\thops\ttext\n")
                for ev in self._lines:
                    if not isinstance(ev, dict):
                        continue
                    if self._filter and self._filter.lower() not in format_log_line(ev).lower():
                        continue
                    portnum = ev.get("portnum") or ev.get("decoded_portnum") or ""
                    if self._portnum_filters and portnum not in self._portnum_filters:
                        continue
                    f.write(
                        f"{ev.get('ts', '')}\t"
                        f"{ev.get('from') or ev.get('id') or '?'}\t"
                        f"{portnum}\t"
                        f"{ev.get('snr', '')}\t"
                        f"{ev.get('hop_limit', '')}\t"
                        f"{(ev.get('text') or '').replace(chr(9), ' ')}\n"
                    )
        except Exception as exc:
            QMessageBox.warning(self, "Log", f"Export failed: {exc}")
            return
        QMessageBox.information(self, "Log", f"Saved to {out_path}")
