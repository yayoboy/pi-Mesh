"""Config > Tasti — rebind any global shortcut at runtime.

Each row pairs an action description with a button showing the current
key combo. Clicking the button enters *capture mode*: the next physical
keypress (or chord with modifiers) replaces the binding immediately and
gets persisted to ``~/.config/pimesh/keymap.json``. Esc cancels capture
without changing anything.

The button itself is the keypress sink: while in capture mode it keeps
focus, intercepts ``keyPressEvent``, and ignores bare modifier presses so
the user has time to hold Shift before tapping the final key.

Conflicts (combo already assigned to another action) surface as a toast
and the rebind is rejected.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.keymap import ACTIONS


_MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock,
}


class _BindingButton(QPushButton):
    """Shows the current QKeySequence; captures the next chord on click."""

    def __init__(self, action_id: str, get_seq, on_change, on_conflict, parent=None):
        super().__init__(parent)
        self._action_id = action_id
        self._get_seq = get_seq
        self._on_change = on_change
        self._on_conflict = on_conflict
        self._capturing = False
        self.setMinimumHeight(36)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self._start_capture)
        self._refresh_text()

    def _refresh_text(self) -> None:
        if self._capturing:
            self.setText("premi un tasto… (Esc annulla)")
            return
        seq = self._get_seq(self._action_id)
        self.setText(seq.toString() or "<non assegnato>")

    def _start_capture(self) -> None:
        self._capturing = True
        self._refresh_text()
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def _finish(self, seq: QKeySequence | None) -> None:
        self._capturing = False
        if seq is not None:
            accepted = self._on_change(self._action_id, seq)
            if not accepted:
                self._on_conflict(seq)
        self._refresh_text()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._finish(None)
            return
        if key in _MODIFIER_KEYS:
            # Wait for the non-modifier key; the user is still composing
            # the chord.
            return
        mods = int(event.modifiers())
        self._finish(QKeySequence(mods | key))


class Section(QWidget):
    """The Config > Tasti body. Constructed with no extra args so it
    fits the same protocol as the other ``_*Section`` widgets used by
    ``config_page.Page``."""

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        hint = QLabel("Clicca un binding e premi la nuova combo; Esc annulla.")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        self._buttons: dict[str, _BindingButton] = {}
        for action_id, label, _default in ACTIONS:
            btn = _BindingButton(
                action_id,
                get_seq=self._get_seq,
                on_change=self._on_change,
                on_conflict=self._on_conflict,
                parent=self,
            )
            self._buttons[action_id] = btn
            form.addRow(label, btn)
        outer.addLayout(form)

        reset = QPushButton("Ripristina default", self)
        reset.setMinimumHeight(36)
        reset.clicked.connect(self._on_reset)
        outer.addWidget(reset)

    # ------------------------------------------------------------------
    # ShortcutManager bridge — looked up lazily so this widget can be
    # constructed before MainWindow.attach() has wired the manager (the
    # Config page is built on first navigation, by which point the
    # singleton exists, but keeping it lazy makes import order resilient).

    def _mgr(self):
        from gui.shortcuts import get_instance
        return get_instance()

    def _get_seq(self, action_id: str) -> QKeySequence:
        mgr = self._mgr()
        return mgr.get_binding(action_id) if mgr else QKeySequence()

    def _on_change(self, action_id: str, seq: QKeySequence) -> bool:
        mgr = self._mgr()
        if mgr is None:
            return False
        # Conflict: the combo is already bound to another action.
        for aid in self._buttons:
            if aid == action_id:
                continue
            if mgr.get_binding(aid) == seq:
                return False
        mgr.set_binding(action_id, seq)
        return True

    def _on_conflict(self, seq: QKeySequence) -> None:
        try:
            from gui.widgets.toast import show_toast
            show_toast(self, f"Combo '{seq.toString()}' già usata", role="warn")
        except Exception:
            # Toast is nice-to-have; silently degrade if the helper API
            # signature changes.
            pass

    def _on_reset(self) -> None:
        mgr = self._mgr()
        if mgr is None:
            return
        mgr.reset_to_defaults()
        for btn in self._buttons.values():
            btn._refresh_text()
