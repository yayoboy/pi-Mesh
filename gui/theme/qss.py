"""Generate a QSS stylesheet from a palette dict.

The Qt port is "performance-first" rather than "pixel-clone-of-web", so this
sheet sets only the colors and a handful of touch-friendly defaults. The bulk
of the visual style comes from the Fusion style applied at QApplication
construction time; this stylesheet only overrides what Fusion + QPalette
cannot express.
"""

from __future__ import annotations

from gui.theme.palettes import _REQUIRED_KEYS


_QSS_TEMPLATE = """\
/* Auto-generated. Do not hand-edit. */

QWidget {{
    background: {bg};
    color: {text};
    font-family: sans-serif;
    font-size: 14px;
}}

QFrame#statusbar {{
    background: {panel};
    border-bottom: 1px solid {border};
}}

QFrame#tabbar {{
    background: {panel};
    border-top: 1px solid {border};
}}

QPushButton {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 32px;
}}
QPushButton:pressed,
QPushButton:checked {{
    background: {accent};
    color: white;
    border-color: {accent};
}}
QPushButton:disabled {{
    color: {muted};
    background: {bg};
}}

QToolButton {{
    background: transparent;
    color: {muted};
    border: none;
    padding: 2px 4px;
}}
QToolButton:checked {{
    color: {accent};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 36px;
    selection-background-color: {accent};
}}

QListView, QTreeView, QTableView {{
    background: {bg};
    color: {text};
    border: none;
    alternate-background-color: {panel};
}}
QListView::item:selected,
QTreeView::item:selected,
QTableView::item:selected {{
    background: rgba(74, 158, 255, 0.20);
    color: {accent};
}}

QHeaderView::section {{
    background: {panel};
    color: {muted};
    border: none;
    border-bottom: 1px solid {border};
    padding: 4px 8px;
}}

QScrollBar:vertical {{
    background: {bg};
    width: 14px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {muted};
    border-radius: 7px;
    min-height: 32px;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {bg};
    height: 14px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {muted};
    border-radius: 7px;
    min-width: 32px;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QLabel[role="muted"] {{
    color: {muted};
}}
QLabel[role="ok"] {{
    color: {ok};
}}
QLabel[role="warn"] {{
    color: {warn};
}}
QLabel[role="danger"] {{
    color: {danger};
}}

QToolTip {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    padding: 4px 6px;
}}

/* Keyboard focus indicators — needed because the GUI is fully navigable
   from a QMK keyboard. Qt's `outline` QSS property is unreliable across
   widget types (it works on QLineEdit-like widgets but not on QListView,
   QToolButton, etc.), so we explicitly set a coloured border on focus for
   each widget class that the user can actually focus. Widgets that have
   `border: none` by default (lists, tool buttons) get a 1px accent border
   that costs no layout because we reserve the same 1px in their default
   rule. */
QPushButton:focus,
QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {{
    border: 1px solid {accent};
}}
QListView:focus,
QListWidget:focus,
QTreeView:focus,
QTableView:focus {{
    border: 1px solid {accent};
}}
QToolButton:focus {{
    border: 1px solid {accent};
    border-radius: 3px;
}}
"""


def build_qss(palette: dict[str, str]) -> str:
    """Render the QSS stylesheet for the given palette.

    Raises ``KeyError`` if any required color is missing.
    """
    return _QSS_TEMPLATE.format(**{k: palette[k] for k in _REQUIRED_KEYS})
