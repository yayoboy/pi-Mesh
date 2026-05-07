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
    background: {panel};
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
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {muted};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {bg};
    height: 6px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {muted};
    border-radius: 3px;
    min-width: 24px;
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
"""


def build_qss(palette: dict[str, str]) -> str:
    """Render the QSS stylesheet for the given palette.

    Raises ``KeyError`` if any required color is missing.
    """
    return _QSS_TEMPLATE.format(**{k: palette[k] for k in _REQUIRED_KEYS})
