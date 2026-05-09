"""Light animation helpers for dialogs.

Used by ``MainWindow`` to attach a fade-in to every modal opened by Qt
(via the ``QApplication.focusChanged`` mechanism is too late; we listen
to ``QApplication.aboutToShowDialog``-equivalent via showEvent override
on the dialog instead). Helper here keeps the trick reusable.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


def fade_in(widget: QWidget, duration_ms: int = 160) -> QPropertyAnimation:
    """Attach a graphics-effect-driven fade-in to ``widget`` and start it.

    Returns the animation so the caller can keep a reference (otherwise GC
    may collect it before completion).
    """
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start()
    return anim
