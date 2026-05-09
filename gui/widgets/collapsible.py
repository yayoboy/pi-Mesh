"""``CollapsibleSection`` — a QGroupBox-like container with a header
button that hides/shows its body.

Used in the long Config page so users on a 320×480 screen can collapse
sections they're not editing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleSection(QFrame):
    """Header (clickable) + body (hidden when collapsed)."""

    def __init__(self, title: str, parent=None, *, expanded: bool = False):
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Plain)

        self._toggle = QToolButton(self)
        self._toggle.setStyleSheet(
            "QToolButton { border: none; padding: 4px 6px; font-weight: 600; "
            "color: var(--text); }"
        )
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.toggled.connect(self._on_toggled)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 4, 8, 8)
        self._body_layout.setSpacing(4)
        self._body.setVisible(expanded)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._toggle)
        outer.addWidget(self._body)

        self._on_toggled(expanded)

    # ------------------------------------------------------------------

    def add_widget(self, w: QWidget) -> None:
        self._body_layout.addWidget(w)

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    # ------------------------------------------------------------------

    def _on_toggled(self, expanded: bool) -> None:
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._body.setVisible(expanded)
