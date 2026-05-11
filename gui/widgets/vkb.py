"""On-screen virtual keyboard for the touchscreen kiosk.

Mirrors the layout in ``static/vkbd.js``: three pages (alpha, sym, sym2),
shift toggle, backspace, bottom row of comma/space/period/done. Sized for
a 480 px width landscape display.

Usage:
    vkb = VirtualKeyboard(parent=main_window)
    vkb.attach_to(main_window)   # auto show/hide on QLineEdit / QPlainTextEdit focus
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.widgets._vkb_layout import ROWS_ALPHA as _ROWS_ALPHA
from gui.widgets._vkb_layout import ROWS_SYM as _ROWS_SYM
from gui.widgets._vkb_layout import ROWS_SYM2 as _ROWS_SYM2

log = logging.getLogger(__name__)


_KEY_QSS = """
QPushButton {
    background: #2d2d44;
    color: #c9d1e0;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    min-width: 26px;
    min-height: 30px;
}
QPushButton:pressed { background: #4a9eff; color: #ffffff; }
QPushButton[modkey="true"] { background: #1f2a40; }
QPushButton[modkey="true"]:checked { background: #4a9eff; color: #ffffff; }
"""


class VirtualKeyboard(QFrame):
    """Three-page software keyboard. Emits ``key_pressed(str)`` for chars,
    ``backspace`` for backspace, and ``done`` when the user dismisses it."""

    key_pressed = Signal(str)
    backspace = Signal()
    done = Signal()

    PAGE_ALPHA = 0
    PAGE_SYM = 1
    PAGE_SYM2 = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("vkb")
        self.setStyleSheet(_KEY_QSS + "QFrame#vkb { background: #1a1a2e; }")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # never steal focus

        self._page = self.PAGE_ALPHA
        self._shift = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 4)
        outer.setSpacing(2)

        self._rows_host = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        outer.addWidget(self._rows_host)

        self._render()

    # ------------------------------------------------------------------
    # Render

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            row_item = self._rows_layout.takeAt(0)
            row_w = row_item.widget()
            if row_w is not None:
                row_w.deleteLater()

    def _render(self) -> None:
        self._clear_rows()
        rows = (
            _ROWS_ALPHA if self._page == self.PAGE_ALPHA
            else _ROWS_SYM if self._page == self.PAGE_SYM
            else _ROWS_SYM2
        )
        for r, row_chars in enumerate(rows):
            row_w = QWidget(self._rows_host)
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            # Shift key on last alpha row
            if r == 2 and self._page == self.PAGE_ALPHA:
                shift = QPushButton("⇧", row_w)
                shift.setProperty("modkey", True)
                shift.setCheckable(True)
                shift.setChecked(self._shift)
                shift.setMinimumWidth(34)
                shift.clicked.connect(self._toggle_shift)
                row_layout.addWidget(shift)

            for ch in row_chars:
                display = ch.upper() if (self._shift and self._page == self.PAGE_ALPHA) else ch
                btn = QPushButton(display, row_w)
                btn.clicked.connect(lambda _checked=False, c=display: self._press_char(c))
                row_layout.addWidget(btn)

            # Backspace on last row
            if r == len(rows) - 1:
                bs = QPushButton("⌫", row_w)
                bs.setProperty("modkey", True)
                bs.setMinimumWidth(34)
                bs.clicked.connect(self._press_backspace)
                row_layout.addWidget(bs)

            self._rows_layout.addWidget(row_w)

        # Bottom row: sym toggle, comma, space, period, done.
        bottom = QWidget(self._rows_host)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(2)

        sym = QPushButton(
            "123" if self._page == self.PAGE_ALPHA
            else "#+=" if self._page == self.PAGE_SYM
            else "ABC",
            bottom,
        )
        sym.setProperty("modkey", True)
        sym.setMinimumWidth(40)
        sym.clicked.connect(self._toggle_sym)
        bl.addWidget(sym)

        comma = QPushButton(",", bottom)
        comma.clicked.connect(lambda: self._press_char(","))
        bl.addWidget(comma)

        space = QPushButton(" ", bottom)
        space.setMinimumWidth(120)
        space.clicked.connect(lambda: self._press_char(" "))
        bl.addWidget(space, 1)

        period = QPushButton(".", bottom)
        period.clicked.connect(lambda: self._press_char("."))
        bl.addWidget(period)

        done = QPushButton("✓", bottom)
        done.setProperty("modkey", True)
        done.setMinimumWidth(40)
        done.clicked.connect(self.done.emit)
        bl.addWidget(done)

        self._rows_layout.addWidget(bottom)

    # ------------------------------------------------------------------
    # Slots

    def _toggle_shift(self) -> None:
        self._shift = not self._shift
        self._render()

    def _toggle_sym(self) -> None:
        # Cycle ALPHA → SYM → SYM2 → ALPHA
        self._page = (self._page + 1) % 3
        self._render()

    def _press_char(self, ch: str) -> None:
        self.key_pressed.emit(ch)
        # auto-release shift after one keypress, like the web vkbd.
        if self._shift and self._page == self.PAGE_ALPHA:
            self._shift = False
            self._render()

    def _press_backspace(self) -> None:
        self.backspace.emit()


# ---------------------------------------------------------------------------
# Auto-attach helper
# ---------------------------------------------------------------------------

class VkbController(QObject):
    """Watches focus changes and shows the keyboard when a text widget is focused.

    Install once on the main window:
        controller = VkbController(main_window)
    """

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._target: QWidget | None = None
        # When False, focus on a text widget will NOT auto-show the keyboard.
        # Toggled by F24 shortcut so a user with a physical keyboard can
        # suppress the on-screen one without setting PIMESH_GUI_NO_VKB.
        self._enabled: bool = True

        self._kbd = VirtualKeyboard(parent=host)
        self._kbd.hide()
        # Position at the bottom of the host; resizes track the host.
        self._reposition()
        host.installEventFilter(self)
        self._kbd.key_pressed.connect(self._on_char)
        self._kbd.backspace.connect(self._on_backspace)
        self._kbd.done.connect(self.hide_keyboard)

        # Listen to focusChanged on the QApplication.
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)

    # ------------------------------------------------------------------

    def _reposition(self) -> None:
        # Anchor to bottom edge, full width minus a 2 px margin.
        host_w = self._host.width()
        kbd_h = max(140, host_w // 3)
        self._kbd.setGeometry(0, self._host.height() - kbd_h, host_w, kbd_h)
        self._kbd.raise_()

    def eventFilter(self, obj, event):
        if obj is self._host and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def _on_focus_changed(self, old: QWidget | None, new: QWidget | None) -> None:
        if isinstance(new, (QLineEdit, QPlainTextEdit, QTextEdit)):
            self._target = new
            if self._enabled:
                self._reposition()
                self._kbd.show()
        else:
            # Hide only if focus left a text widget (clicking on the VKB
            # itself transfers focus to a button, but the buttons have
            # NoFocus — handled via FocusPolicy on the keyboard).
            self.hide_keyboard()

    def hide_keyboard(self) -> None:
        self._target = None
        self._kbd.hide()

    def toggle(self) -> bool:
        """Enable/disable the auto-show-on-focus behavior. Returns new state.

        When disabling, any currently visible keyboard is hidden right away
        so the user gets immediate feedback. When re-enabling, the keyboard
        will reappear on the next text-widget focus.
        """
        self._enabled = not self._enabled
        if not self._enabled:
            self._kbd.hide()
        return self._enabled

    def is_enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------

    def _on_char(self, ch: str) -> None:
        t = self._target
        if t is None:
            return
        if isinstance(t, QLineEdit):
            t.insert(ch)
        elif isinstance(t, (QPlainTextEdit, QTextEdit)):
            t.insertPlainText(ch)

    def _on_backspace(self) -> None:
        t = self._target
        if t is None:
            return
        if isinstance(t, QLineEdit):
            t.backspace()
        elif isinstance(t, (QPlainTextEdit, QTextEdit)):
            cursor = t.textCursor()
            if cursor.hasSelection():
                cursor.removeSelectedText()
            else:
                cursor.deletePreviousChar()
