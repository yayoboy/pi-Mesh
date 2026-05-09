"""Stub page used as a fallback when a real page module fails to import."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StubPage(QWidget):
    def __init__(self, title: str, error: str | None = None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel(title)
        f = title_lbl.font()
        f.setPointSize(16)
        f.setBold(True)
        title_lbl.setFont(f)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        sub = QLabel("not yet implemented" if not error else f"error: {error}")
        sub.setProperty("role", "muted" if not error else "danger")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)
