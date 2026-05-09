"""Config-page section for the Meshtastic bots framework.

Lists every registered bot with a toggle button, plus a top-row prefix
field. All hits go through the FastAPI bridge (``/api/bots*``); the
backend handles persistence + reload of the in-process runner.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class _BotRow(QWidget):
    """One row per bot: name + toggle + ? help."""

    def __init__(self, bot: dict, on_toggle, parent=None):
        super().__init__(parent)
        self._bot = bot
        self._on_toggle = on_toggle

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._toggle = QPushButton(self)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(bool(bot.get("enabled")))
        self._toggle.setMinimumWidth(46)
        self._toggle.toggled.connect(self._on_toggled)
        self._update_toggle_text()
        layout.addWidget(self._toggle)

        name_label = QLabel(f"<b>{bot.get('name', '?')}</b>")
        name_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(name_label)
        layout.addStretch(1)

        help_btn = QToolButton(self)
        help_btn.setText("?")
        help_btn.setToolTip("Description")
        help_btn.clicked.connect(self._show_help)
        layout.addWidget(help_btn)

    def _update_toggle_text(self) -> None:
        self._toggle.setText("on" if self._toggle.isChecked() else "off")

    def _on_toggled(self, checked: bool) -> None:
        self._update_toggle_text()
        self._on_toggle(self._bot.get("name"), checked)

    def _show_help(self) -> None:
        QMessageBox.information(
            self, self._bot.get("name", "bot"),
            self._bot.get("description") or "(no description)",
        )

    def update_from(self, bot: dict) -> None:
        self._bot = bot
        was = self._toggle.blockSignals(True)
        self._toggle.setChecked(bool(bot.get("enabled")))
        self._update_toggle_text()
        self._toggle.blockSignals(was)


class _BotsSection(QGroupBox):
    """Outer container — config for the whole bots framework."""

    def __init__(self, parent=None):
        super().__init__("Bots", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Prefix row
        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel("Prefix"))
        self._prefix = QLineEdit(self)
        self._prefix.setMaxLength(8)
        self._prefix.setFixedWidth(80)
        self._prefix.editingFinished.connect(self._on_prefix_committed)
        prefix_row.addWidget(self._prefix)
        prefix_row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        prefix_row.addWidget(refresh)
        layout.addLayout(prefix_row)

        self._status = QLabel("loading…")
        self._status.setProperty("role", "muted")
        layout.addWidget(self._status)

        # Rows host
        self._rows_host = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout.addWidget(self._rows_host)

        self._rows: dict[str, _BotRow] = {}
        self._refresh()

    # -- HTTP -----------------------------------------------------------

    def _refresh(self) -> None:
        try:
            from gui import backend
            data = backend.get_bots()
        except Exception:
            self._status.setText("runner not reachable")
            self._status.setProperty("role", "danger")
            return

        prefix = data.get("prefix") or "!"
        if self._prefix.text() != prefix:
            blocked = self._prefix.blockSignals(True)
            self._prefix.setText(prefix)
            self._prefix.blockSignals(blocked)

        bots = data.get("bots") or []
        running = data.get("running")
        self._status.setText(
            f"{sum(1 for b in bots if b.get('enabled'))}/{len(bots)} attivi"
            + (" · runner stopped" if not running else "")
        )
        self._status.setProperty("role", "ok" if running else "warn")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

        # Reconcile rows.
        seen = set()
        for bot in bots:
            name = bot.get("name")
            if not name:
                continue
            seen.add(name)
            row = self._rows.get(name)
            if row is None:
                row = _BotRow(bot, self._on_toggle, self._rows_host)
                self._rows_layout.addWidget(row)
                self._rows[name] = row
            else:
                row.update_from(bot)
        for name in list(self._rows.keys()):
            if name not in seen:
                row = self._rows.pop(name)
                self._rows_layout.removeWidget(row)
                row.deleteLater()

    # -- callbacks ------------------------------------------------------

    def _on_prefix_committed(self) -> None:
        prefix = self._prefix.text().strip()
        if not prefix:
            return
        self._post_prefix(prefix)

    def _post_prefix(self, prefix: str) -> None:
        try:
            from gui import backend
            r = backend.set_bot_prefix(prefix)
            if r.get("error"):
                from gui.widgets.toast import show_toast
                show_toast(self, "Prefix update failed", role="danger")
                return
        except Exception:
            log.exception("set prefix failed")

    def _on_toggle(self, name: str, enabled: bool) -> None:
        self._post_toggle(name, enabled)

    def _post_toggle(self, name: str, enabled: bool) -> None:
        try:
            from gui import backend
            r = backend.toggle_bot(name, enabled)
        except Exception:
            log.exception("toggle bot failed")
            return
        from gui.widgets.toast import show_toast
        if r.get("ok"):
            show_toast(self, f"{name}: {'on' if enabled else 'off'}", role="ok")
        else:
            show_toast(self, f"{name}: failed", role="danger")
        # Re-pull the runner state to reflect any cascading changes.
        self._refresh()
