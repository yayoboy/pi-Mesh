"""Non-modal toast notifications.

A toast is a small, briefly-visible label that floats at the bottom of the
main window for ~3 seconds before fading out. Used for low-criticality
feedback ("✓ marker added", "✗ network error") that doesn't need the user
to dismiss it the way a QMessageBox does.

Mirrors the ``showToast`` helper invoked across templates/*.html.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


_TOAST_QSS = """
QFrame#toast {
    background: rgba(20, 20, 32, 220);
    border: 1px solid #444;
    border-radius: 6px;
}
QLabel#toastLabel {
    color: #ffffff;
    font-size: 11px;
    padding: 6px 12px;
}
QFrame#toast[role="ok"]      { border-color: #4caf50; }
QFrame#toast[role="warn"]    { border-color: #ff9800; }
QFrame#toast[role="danger"]  { border-color: #f44336; }
"""


class _ToastWidget(QWidget):
    """One toast row. Removes itself when the fade-out finishes."""

    HEIGHT = 28

    def __init__(self, message: str, role: str = "info", *, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(_TOAST_QSS)

        from PySide6.QtWidgets import QFrame
        frame = QFrame(self)
        frame.setObjectName("toast")
        frame.setProperty("role", role if role in ("ok", "warn", "danger") else None)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)

        f_layout = QHBoxLayout(frame)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(0)
        label = QLabel(message, frame)
        label.setObjectName("toastLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f_layout.addWidget(label)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

    def play(self, duration_ms: int) -> None:
        # Fade in.
        self._anim_in = QPropertyAnimation(self._opacity, b"opacity")
        self._anim_in.setDuration(180)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_in.start()

        # Fade out after ``duration_ms``.
        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self) -> None:
        self._anim_out = QPropertyAnimation(self._opacity, b"opacity")
        self._anim_out.setDuration(220)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_out.finished.connect(self._cleanup)
        self._anim_out.start()

    def _cleanup(self) -> None:
        host = self.parent()
        if isinstance(host, QWidget):
            mgr = ToastHost.find_for(host)
            if mgr is not None:
                mgr._remove(self)
        self.deleteLater()


class ToastHost(QObject):
    """One per main window. Stack toasts above the bottom tab bar."""

    _instances: "dict[int, ToastHost]" = {}

    DEFAULT_DURATION_MS = 3000
    BOTTOM_OFFSET = 40   # leave room for the 32 px tab bar.

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._toasts: list[_ToastWidget] = []
        ToastHost._instances[id(host)] = self
        host.destroyed.connect(lambda: ToastHost._instances.pop(id(host), None))

    @classmethod
    def for_window(cls, host: QWidget) -> "ToastHost":
        """Lazily attach a host. Idempotent."""
        existing = cls._instances.get(id(host))
        if existing is not None:
            return existing
        return cls(host)

    @classmethod
    def find_for(cls, child: QWidget) -> "ToastHost | None":
        w: QWidget | None = child
        while w is not None:
            mgr = cls._instances.get(id(w))
            if mgr is not None:
                return mgr
            w = w.parentWidget() if hasattr(w, "parentWidget") else None
        return None

    # Public API --------------------------------------------------------

    def show(self, message: str, *, role: str = "info",
             duration_ms: int | None = None) -> None:
        toast = _ToastWidget(message, role=role, parent=self._host)
        # Size based on text length, capped to the host width.
        toast.adjustSize()
        max_w = max(160, self._host.width() - 24)
        w = min(max_w, max(160, toast.sizeHint().width() + 24))
        h = _ToastWidget.HEIGHT
        toast.resize(w, h)
        self._toasts.append(toast)
        self._reflow()
        toast.show()
        toast.raise_()
        toast.play(duration_ms or self.DEFAULT_DURATION_MS)

    def _remove(self, toast: _ToastWidget) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reflow()

    def _reflow(self) -> None:
        host = self._host
        host_w = host.width()
        host_h = host.height()
        y = host_h - self.BOTTOM_OFFSET - _ToastWidget.HEIGHT
        for toast in reversed(self._toasts):  # newest on bottom
            x = (host_w - toast.width()) // 2
            toast.move(max(0, x), y)
            y -= _ToastWidget.HEIGHT + 4


def show_toast(widget: QWidget, message: str, *,
               role: str = "info", duration_ms: int | None = None) -> None:
    """Module-level helper used across pages.

    Walks up the widget tree to find a ``MainWindow``-attached :class:`ToastHost`,
    then forwards the call. No-op if no host is attached (e.g. unit tests).
    """
    mgr = ToastHost.find_for(widget)
    if mgr is None:
        return
    mgr.show(message, role=role, duration_ms=duration_ms)
