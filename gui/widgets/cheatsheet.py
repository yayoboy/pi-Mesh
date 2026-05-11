"""Translucent overlay listing the current keymap.

Triggered by F1 (or whichever combo the user binds to ``cheatsheet`` via
Config > Tasti). Reads live bindings from ``ShortcutManager`` so a user
who has rebound, say, F4 → page Msg sees their custom combo here too.

Dismissed by any non-modifier keypress or click — no explicit close
button, the whole UI is the close target.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from gui.keymap import ACTIONS


_MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock,
}


class CheatsheetOverlay(QFrame):
    """Full-window semi-transparent panel showing action → combo pairs."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("cheatsheetOverlay")
        # Inline style: keeps the overlay self-contained, doesn't pollute
        # the project-wide QSS palette with overlay-specific colours.
        self.setStyleSheet(
            "QFrame#cheatsheetOverlay {"
            "  background: rgba(8, 12, 24, 235);"
            "  border: 1px solid #4a9eff;"
            "}"
            "QLabel { color: #e6edf3; }"
            "QLabel[role=\"muted\"] { color: #4a9eff; }"
        )
        # Cover the entire parent, including the tab/status bars, so any
        # click or key dismisses without users hunting for a close glyph.
        self.setGeometry(parent.rect())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Tasti pi-Mesh")
        tf = title.font()
        tf.setPointSize(11)
        tf.setBold(True)
        title.setFont(tf)
        layout.addWidget(title)

        hint = QLabel("Premi un tasto qualsiasi per chiudere.")
        hint.setProperty("role", "muted")
        layout.addWidget(hint)

        # Look up the live binding for each action — falls back to the
        # default if the singleton hasn't been initialised (e.g. test
        # harness instantiates the overlay alone).
        from gui.shortcuts import get_instance
        mgr = get_instance()

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(2)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for action_id, label, default in ACTIONS:
            seq = mgr.get_binding(action_id) if mgr else QKeySequence(default)
            combo = QLabel(seq.toString() or "—")
            combo.setProperty("role", "muted")
            form.addRow(label, combo)
        layout.addLayout(form)
        layout.addStretch(1)

        self.raise_()
        self.show()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------

    def keyPressEvent(self, ev) -> None:
        # Modifier-only presses don't dismiss: the user might be reaching
        # for a chord and we don't want to vanish under their fingers.
        if ev.key() not in _MODIFIER_KEYS:
            self._dismiss()
            ev.accept()
        else:
            super().keyPressEvent(ev)

    def mousePressEvent(self, ev) -> None:
        self._dismiss()
        ev.accept()

    def _dismiss(self) -> None:
        self.hide()
        self.deleteLater()
