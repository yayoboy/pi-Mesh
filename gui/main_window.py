"""MainWindow: status bar (top, 24 px) + tab content + tab bar (bottom, 32 px).

Geometry matches the web UI on the 320×480 (or 480×320 rotated) Waveshare
SPI display: ``setFixedSize(320, 480)`` so dev runs on the desktop look like
the kiosk. Layout flips automatically when the system display rotation is
applied at the X server level, no Qt-side rotation needed.

Each tab is a lazily-imported page module exposing ``Page(QWidget)`` taking
``(eventbus, settings)``. Lazy import keeps heavy pages (map, metrics) out
of the startup hot path.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.status_icons import BatteryIcon, ConnIcon, GpsIcon, SignalIcon

log = logging.getLogger(__name__)


# Match the web UI: 6 tabs, the 7th (Telemetry) is reachable from the node
# detail view rather than getting its own slot. Italian labels match
# templates/base.html.
def _make_icon(draw_func, size: int = 20, color: str = "#cccccc") -> QIcon:
    """Create a QIcon by painting onto a QPixmap."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    draw_func(p, size, QColor(color))
    p.end()
    return QIcon(pm)


def _icon_nodes(p: QPainter, s: int, c: QColor) -> None:
    """Material: group/people."""
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(QBrush(c))
    p.drawEllipse(QPointF(s * 0.38, s * 0.30), s * 0.12, s * 0.12)
    path = QPainterPath()
    path.moveTo(s * 0.18, s * 0.72)
    path.quadTo(s * 0.18, s * 0.48, s * 0.38, s * 0.48)
    path.quadTo(s * 0.58, s * 0.48, s * 0.58, s * 0.72)
    p.drawPath(path)
    p.drawEllipse(QPointF(s * 0.64, s * 0.28), s * 0.11, s * 0.11)
    path2 = QPainterPath()
    path2.moveTo(s * 0.48, s * 0.68)
    path2.quadTo(s * 0.48, s * 0.45, s * 0.64, s * 0.45)
    path2.quadTo(s * 0.82, s * 0.45, s * 0.82, s * 0.68)
    p.drawPath(path2)


def _icon_map(p: QPainter, s: int, c: QColor) -> None:
    """Material: map pin."""
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(QBrush(c))
    path = QPainterPath()
    cx, top = s * 0.5, s * 0.1
    path.moveTo(cx, s * 0.9)
    path.cubicTo(cx, s * 0.9, s * 0.15, s * 0.55, s * 0.15, s * 0.38)
    path.cubicTo(s * 0.15, s * 0.15, s * 0.85, s * 0.15, s * 0.85, s * 0.38)
    path.cubicTo(s * 0.85, s * 0.55, cx, s * 0.9, cx, s * 0.9)
    p.drawPath(path)
    p.setBrush(QBrush(QColor("#1a1a2e")))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx, s * 0.37), s * 0.12, s * 0.12)


def _icon_chat(p: QPainter, s: int, c: QColor) -> None:
    """Material: chat bubble."""
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(QBrush(c))
    r = QRectF(s * 0.1, s * 0.15, s * 0.8, s * 0.55)
    p.drawRoundedRect(r, 3, 3)
    tail = QPainterPath()
    tail.moveTo(s * 0.25, s * 0.70)
    tail.lineTo(s * 0.20, s * 0.85)
    tail.lineTo(s * 0.45, s * 0.70)
    p.drawPath(tail)


def _icon_config(p: QPainter, s: int, c: QColor) -> None:
    """Material: settings gear."""
    from math import cos, sin, pi
    pen = QPen(c, 1.4)
    p.setPen(pen)
    p.setBrush(QBrush(c))
    cx, cy = s * 0.5, s * 0.5
    outer, inner = s * 0.42, s * 0.32
    teeth = 8
    pts = []
    for i in range(teeth * 2):
        angle = i * pi / teeth - pi / 2
        r = outer if i % 2 == 0 else inner
        pts.append(QPointF(cx + r * cos(angle), cy + r * sin(angle)))
    poly = QPolygonF(pts)
    p.drawPolygon(poly)
    p.setBrush(QBrush(QColor("#1a1a2e")))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx, cy), s * 0.13, s * 0.13)


def _icon_metrics(p: QPainter, s: int, c: QColor) -> None:
    """Material: bar chart."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(c))
    bar_w = s * 0.15
    bars = [(s * 0.12, 0.40), (s * 0.32, 0.70), (s * 0.52, 0.55), (s * 0.72, 0.85)]
    for bx, frac in bars:
        h = s * frac
        p.drawRect(QRectF(bx, s * 0.9 - h, bar_w, h))


def _icon_log(p: QPainter, s: int, c: QColor) -> None:
    """Material: list/subject lines."""
    pen = QPen(c, 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for i, w_frac in enumerate([0.7, 0.55, 0.7, 0.45]):
        y = s * (0.22 + i * 0.18)
        p.drawLine(QPointF(s * 0.15, y), QPointF(s * (0.15 + w_frac), y))


_TAB_ICON_FUNCS = [_icon_nodes, _icon_map, _icon_chat, _icon_config, _icon_metrics, _icon_log]

_TABS: list[tuple[str, str]] = [
    ("Nodi",     "gui.pages.nodes_page"),
    ("Mappa",    "gui.pages.map_page"),
    ("Msg",      "gui.pages.messages_page"),
    ("Config",   "gui.pages.config_page"),
    ("Metriche", "gui.pages.metrics_page"),
    ("Log",      "gui.pages.log_page"),
]

# Hidden tab — accessible programmatically via show_telemetry() but not in
# the bottom bar.
_TELEMETRY_TAB = ("Telemetria", "gui.pages.telemetry_page")


# Geometry constants — default landscape, matching the user's installed
# orientation on the Waveshare 3.5" SPI display. When the OS reports a
# different rotation we adopt that instead at startup (see __init__).
SCREEN_W_LANDSCAPE = 480
SCREEN_H_LANDSCAPE = 320
SCREEN_W_PORTRAIT  = 320
SCREEN_H_PORTRAIT  = 480
STATUS_H = 28
TABBAR_H = 48


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

class _StatusIcon(QLabel):
    """Compact icon label, used for the right-side row in the status bar."""

    def __init__(self, glyph: str = "·", *, tooltip: str = "", parent=None):
        super().__init__(glyph, parent)
        self.setToolTip(tooltip)
        self.setProperty("role", "muted")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(20, 20)
        f = self.font()
        f.setPointSize(9)
        self.setFont(f)


class StatusBar(QFrame):
    """Top status bar mirroring templates/base.html, height = 24 px.

    Left:  node short_name (or "pi-Mesh" when unknown).
    Right: row of compact icons: battery, LoRa signal, GPS, board state,
           rotation menu, screenshot, reboot, shutdown.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusbar")
        self.setFixedHeight(STATUS_H)

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 0, 4, 0)
        root.setSpacing(6)

        self._name = QLabel("pi-Mesh", self)
        self._name.setProperty("role", "muted")
        f = self._name.font()
        f.setPointSize(9)
        self._name.setFont(f)
        root.addWidget(self._name)
        root.addStretch(1)

        # Vector icons drawn with QPainter so we don't depend on font
        # glyph availability (Unicode emojis varied across distros).
        self._batt = BatteryIcon(self)
        self._batt.set_tooltip("Battery")
        self._lora = SignalIcon(self)
        self._lora.set_tooltip("LoRa signal")
        self._gps = GpsIcon(self)
        self._gps.set_tooltip("GPS")
        self._conn = ConnIcon(self)
        self._conn.set_tooltip("Board")
        self._rot  = QToolButton(self)
        self._rot.setText("R")
        self._rot.setFixedSize(22, 22)
        self._rot.setToolTip("Rotation")
        self._rot.clicked.connect(self._show_rotation_menu)

        self._shot = QToolButton(self)
        self._shot.setText("S")
        self._shot.setFixedSize(22, 22)
        self._shot.setToolTip("Screenshot")
        self._shot.clicked.connect(self._take_screenshot)

        self._reboot = QToolButton(self)
        self._reboot.setText("Re")
        self._reboot.setFixedSize(22, 22)
        self._reboot.setToolTip("Reboot")
        self._reboot.clicked.connect(lambda: self._confirm_system("reboot"))

        self._shutdown = QToolButton(self)
        self._shutdown.setText("Off")
        self._shutdown.setFixedSize(28, 22)
        self._shutdown.setToolTip("Shutdown")
        self._shutdown.clicked.connect(lambda: self._confirm_system("shutdown"))

        for w in (self._batt, self._lora, self._gps, self._conn,
                  self._rot, self._shot, self._reboot, self._shutdown):
            root.addWidget(w)

    # ------------------------------------------------------------------

    def update_state(self, *, connected: bool, node_count: int, local_id: str,
                     local_name: str | None = None,
                     battery: int | None = None,
                     snr: float | None = None,
                     gps_fix: bool | None = None) -> None:
        self._name.setText(local_name or local_id or "pi-Mesh")
        self._conn.set_connected(connected)
        self._batt.set_level(None if battery is None else battery / 100.0)
        self._lora.set_strength(snr)
        self._gps.set_fix(bool(gps_fix))

    # Slots --------------------------------------------------------------

    def _show_rotation_menu(self) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for deg in (0, 90, 180, 270):
            menu.addAction(f"{deg}°", lambda d=deg: self._set_rotation(d))
        menu.exec(self._rot.mapToGlobal(self._rot.rect().bottomLeft()))

    def _set_rotation(self, deg: int) -> None:
        if QMessageBox.question(
            self, "Rotation",
            f"Rotate to {deg}° and reboot?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._post_rotation(deg)

    def _post_rotation(self, deg: int) -> None:
        try:
            from gui import backend
            backend.set_display_config(rotation=deg)
            # OS reboot is needed for rotation to take effect.
            backend.system_reboot()
        except Exception:
            log.exception("rotation post failed")

    def _take_screenshot(self) -> None:
        from datetime import datetime
        from pathlib import Path

        from PySide6.QtGui import QPixmap

        win = self.window()
        if win is None:
            return
        pm = win.grab()
        out = Path("data/screenshots") / f"{datetime.now():%Y%m%d-%H%M%S}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        pm.save(str(out), "PNG")
        log.info("screenshot saved to %s", out)

    def _confirm_system(self, action: str) -> None:
        msg = "Riavviare il sistema?" if action == "reboot" else "Spegnere il sistema?"
        if QMessageBox.question(self, "pi-Mesh", msg) != QMessageBox.StandardButton.Yes:
            return
        self._post_system_action(action)

    def _post_system_action(self, action: str) -> None:
        try:
            from gui import backend
            backend.system_reboot()
        except Exception:
            log.exception("system action %s failed", action)


# ---------------------------------------------------------------------------
# Tab bar
# ---------------------------------------------------------------------------

class _TabButton(QToolButton):
    """Touch-friendly tab button: Material Design icon on top, label below.

    Optionally renders a small badge in the top-right corner showing an
    integer counter (used by the Messages tab for unread DM count).
    """

    def __init__(self, label: str, icon: QIcon, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._label = label
        self._badge = 0
        self.setIcon(icon)
        self.setIconSize(QSize(20, 20))
        self.setText(label)
        self.setMinimumHeight(TABBAR_H)
        f = self.font()
        f.setPointSize(8)
        self.setFont(f)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # Strong focus so Tab/Shift+Tab can iterate over tab buttons and the
        # accent-coloured focus ring (see qss.py) shows up. QToolButton
        # defaults to NoFocus once our stylesheet is applied.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"Tab {label}")

    def set_badge(self, count: int) -> None:
        if count == self._badge:
            return
        self._badge = max(0, int(count))
        self._update_text()

    def _update_text(self) -> None:
        if self._badge:
            badge = "9+" if self._badge > 9 else str(self._badge)
            self.setText(f"{self._label} ({badge})")
        else:
            self.setText(self._label)


class TabBar(QFrame):
    """Bottom bar: 6 equal-width tabs, each ~53 px wide on a 320 px screen."""

    def __init__(self, tabs: list[tuple[str, str]], on_select, parent=None):
        super().__init__(parent)
        self.setObjectName("tabbar")
        self.setFixedHeight(TABBAR_H)

        self._buttons: list[_TabButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for i, (label, _module) in enumerate(tabs):
            icon = _make_icon(_TAB_ICON_FUNCS[i])
            btn = _TabButton(label, icon, self)
            btn.clicked.connect(lambda _checked, idx=i: on_select(idx))
            layout.addWidget(btn, 1)
            self._buttons.append(btn)

    def set_active(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)

    def set_badge(self, index: int, count: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].set_badge(count)


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pi-Mesh")

        # Lock the window to the SPI display geometry. Rotation is owned by
        # the kernel/X level (dtoverlay tft35a:rotate=N + xrandr), not Qt:
        # we just adopt whichever of the two orientations the running X
        # server reports. On a desktop dev box (no SPI screen) we fall back
        # to landscape 480×320 because that's the user's installed layout.
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.size()
            if geom.height() >= geom.width():  # portrait
                w, h = SCREEN_W_PORTRAIT, SCREEN_H_PORTRAIT
            else:
                w, h = SCREEN_W_LANDSCAPE, SCREEN_H_LANDSCAPE
        else:
            w, h = SCREEN_W_LANDSCAPE, SCREEN_H_LANDSCAPE
        self.setFixedSize(QSize(w, h))
        self._screen_w, self._screen_h = w, h
        self._is_landscape = w > h

        self._eventbus = None
        self._settings = None

        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._status = StatusBar(central)
        self._stack = QStackedWidget(central)
        self._tabs = TabBar(_TABS, self._select_tab, central)

        root.addWidget(self._status)
        root.addWidget(self._stack, 1)
        root.addWidget(self._tabs)
        self.setCentralWidget(central)

        # index -> (label, module_path, instance|None) for the visible tabs.
        self._pages: list[tuple[str, str, QWidget | None]] = [
            (label, module, None) for label, module in _TABS
        ]
        # The hidden Telemetry page lives outside _pages and is added on
        # demand via show_telemetry().
        self._telemetry_page: QWidget | None = None

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        # Slower poll for the unread-message badge on the Msg tab.
        self._badge_timer = QTimer(self)
        self._badge_timer.setInterval(5000)
        self._badge_timer.timeout.connect(self._refresh_msg_badge)
        self._badge_timer.start()

    # ------------------------------------------------------------------

    def attach(self, eventbus, settings) -> None:
        self._eventbus = eventbus
        self._settings = settings

        # Software keyboard appears on text-widget focus, hides on blur.
        # Disabled when PIMESH_GUI_NO_VKB=1 (useful for desktop dev).
        import os
        self._vkb_controller = None
        if os.environ.get("PIMESH_GUI_NO_VKB", "0") != "1":
            from gui.widgets.vkb import VkbController
            self._vkb_controller = VkbController(self)

        # Toast host so any descendant can call show_toast(self, …).
        from gui.widgets.toast import ToastHost
        ToastHost.for_window(self)

        # Global keyboard shortcuts (F13..F24 + F1) — see gui/shortcuts.py
        # for the firmware contract. Pages register their own contextual
        # shortcuts on themselves.
        from gui.shortcuts import ShortcutManager
        self._shortcuts = ShortcutManager(self)

        self._select_tab(0)

    # ------------------------------------------------------------------
    # Public actions exposed for ShortcutManager (and any caller that needs
    # to trigger a system-bar action programmatically). They delegate to
    # StatusBar so the existing dialogs and confirmation flows are reused.

    def take_screenshot(self) -> None:
        self._status._take_screenshot()

    def show_rotation_menu(self) -> None:
        self._status._show_rotation_menu()

    def confirm_reboot(self) -> None:
        self._status._confirm_system("reboot")

    def confirm_shutdown(self) -> None:
        self._status._confirm_system("shutdown")

    def toggle_vkb(self) -> None:
        if self._vkb_controller is None:
            log.info("toggle_vkb: VKB disabled at startup, nothing to toggle")
            return
        new_state = self._vkb_controller.toggle()
        log.info("VKB %s", "enabled" if new_state else "disabled")

    def _select_tab(self, index: int) -> None:
        label, module_path, instance = self._pages[index]
        if instance is None:
            instance = self._build_page(module_path, label)
            self._pages[index] = (label, module_path, instance)
            self._stack.addWidget(instance)
        self._stack.setCurrentWidget(instance)
        self._tabs.set_active(index)
        # After a programmatic switch (shortcut or touch), park keyboard
        # focus on the new page so the very next Tab keypress descends into
        # its content. Pages may override `set_initial_focus()` to land on
        # a meaningful child (e.g. the message input on Msg, the node list
        # on Nodi); the fallback just focuses the page container.
        set_focus = getattr(instance, "set_initial_focus", None)
        if callable(set_focus):
            set_focus()
        else:
            instance.setFocus(Qt.FocusReason.OtherFocusReason)

    def show_telemetry(self) -> None:
        """Open the (hidden) telemetry page on demand from a node detail view."""
        if self._telemetry_page is None:
            self._telemetry_page = self._build_page(_TELEMETRY_TAB[1], _TELEMETRY_TAB[0])
            self._stack.addWidget(self._telemetry_page)
        self._stack.setCurrentWidget(self._telemetry_page)

    def _build_page(self, module_path: str, label: str) -> QWidget:
        try:
            mod = __import__(module_path, fromlist=["Page"])
            return mod.Page(self._eventbus, self._settings)
        except Exception as exc:
            log.exception("failed to build page %s", module_path)
            from gui.pages._stub import StubPage
            return StubPage(label, error=str(exc))

    def _refresh_msg_badge(self) -> None:
        try:
            from gui import backend
            count = backend.get_total_unread()
        except Exception:
            count = 0
        self._tabs.set_badge(2, count)

    def _refresh_status(self) -> None:
        try:
            import meshtasticd_client
            local = meshtasticd_client.get_local_node() or {}
            self._status.update_state(
                connected=meshtasticd_client.is_connected(),
                node_count=len(meshtasticd_client.get_nodes()),
                local_id=meshtasticd_client.get_local_id(),
                local_name=local.get("short_name"),
                battery=local.get("battery_level"),
                snr=local.get("snr"),
                gps_fix=local.get("latitude") is not None,
            )
        except Exception:
            log.debug("status refresh failed", exc_info=True)
