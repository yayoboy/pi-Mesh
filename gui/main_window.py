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

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen
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

log = logging.getLogger(__name__)


# Match the web UI: 6 tabs, the 7th (Telemetry) is reachable from the node
# detail view rather than getting its own slot. Italian labels match
# templates/base.html.
_TABS: list[tuple[str, str, str]] = [
    # (label_it, module_path, single-glyph icon)
    ("Nodi",     "gui.pages.nodes_page",    "👥"),
    ("Mappa",    "gui.pages.map_page",      "🗺"),
    ("Msg",      "gui.pages.messages_page", "💬"),
    ("Config",   "gui.pages.config_page",   "⚙"),
    ("Metriche", "gui.pages.metrics_page",  "📊"),
    ("Log",      "gui.pages.log_page",      "≡"),
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
STATUS_H = 24
TABBAR_H = 32


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
        self.setFixedSize(14, 14)
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

        # Icons (right side). Glyphs chosen from common Unicode symbols
        # available in the default Pi OS sans-serif font; replaced by SVG
        # in a follow-up commit.
        self._batt = _StatusIcon("▮", tooltip="Battery")
        self._lora = _StatusIcon("∿", tooltip="LoRa signal")
        self._gps  = _StatusIcon("◉", tooltip="GPS")
        self._conn = _StatusIcon("○", tooltip="Board")
        self._rot  = QToolButton(self)
        self._rot.setText("⟳")
        self._rot.setFixedSize(14, 14)
        self._rot.setToolTip("Rotation")
        self._rot.clicked.connect(self._show_rotation_menu)

        self._shot = QToolButton(self)
        self._shot.setText("⌖")
        self._shot.setFixedSize(14, 14)
        self._shot.setToolTip("Screenshot")
        self._shot.clicked.connect(self._take_screenshot)

        self._reboot = QToolButton(self)
        self._reboot.setText("↻")
        self._reboot.setFixedSize(14, 14)
        self._reboot.setToolTip("Reboot")
        self._reboot.clicked.connect(lambda: self._confirm_system("reboot"))

        self._shutdown = QToolButton(self)
        self._shutdown.setText("⏻")
        self._shutdown.setFixedSize(14, 14)
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
        self._conn.setProperty("role", "ok" if connected else "danger")
        self._conn.setText("●" if connected else "○")
        if battery is None:
            self._batt.setText("▯")
        elif battery > 75:
            self._batt.setText("▮▮▮▮")
        elif battery > 50:
            self._batt.setText("▮▮▮ ")
        elif battery > 25:
            self._batt.setText("▮▮  ")
        else:
            self._batt.setText("▮   ")
        if snr is not None:
            self._lora.setProperty("role", "ok" if snr > 0 else "warn")
        self._gps.setProperty("role", "ok" if gps_fix else "muted")
        # Re-polish role-dependent QSS.
        for w in (self._conn, self._lora, self._gps):
            w.style().unpolish(w)
            w.style().polish(w)

    # Slots --------------------------------------------------------------

    def _show_rotation_menu(self) -> None:
        # Minimal: confirm and POST to /api/config/display.
        # Full menu (with current rotation indicator) lives in Config page.
        QMessageBox.information(
            self, "Rotation",
            "Open Config → Display to change rotation.",
        )

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
        import asyncio
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._post_system_action(action))

    async def _post_system_action(self, action: str) -> None:
        try:
            import httpx
            async with httpx.AsyncClient() as c:
                await c.post(f"http://127.0.0.1:8080/api/system/{action}")
        except Exception:
            log.exception("system action %s failed", action)


# ---------------------------------------------------------------------------
# Tab bar
# ---------------------------------------------------------------------------

class _TabButton(QToolButton):
    """Touch-friendly tab button: icon glyph on top, tiny label below."""

    def __init__(self, label: str, glyph: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setText(f"{glyph}\n{label}")
        self.setMinimumHeight(TABBAR_H)
        f = self.font()
        f.setPointSize(7)  # web UI uses 9 px CSS, we go a touch smaller for Qt metrics.
        self.setFont(f)
        self.setSizePolicy(self.sizePolicy().Expanding, self.sizePolicy().Preferred)


class TabBar(QFrame):
    """Bottom bar: 6 equal-width tabs, each ~53 px wide on a 320 px screen."""

    def __init__(self, tabs: list[tuple[str, str, str]], on_select, parent=None):
        super().__init__(parent)
        self.setObjectName("tabbar")
        self.setFixedHeight(TABBAR_H)

        self._buttons: list[_TabButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for i, (label, _module, glyph) in enumerate(tabs):
            btn = _TabButton(label, glyph, self)
            btn.clicked.connect(lambda _checked, idx=i: on_select(idx))
            layout.addWidget(btn, 1)  # stretch=1 → flex-1 equivalent
            self._buttons.append(btn)

    def set_active(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)


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
            (label, module, None) for label, module, _icon in _TABS
        ]
        # The hidden Telemetry page lives outside _pages and is added on
        # demand via show_telemetry().
        self._telemetry_page: QWidget | None = None

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

    # ------------------------------------------------------------------

    def attach(self, eventbus, settings) -> None:
        self._eventbus = eventbus
        self._settings = settings
        self._select_tab(0)

    def _select_tab(self, index: int) -> None:
        label, module_path, instance = self._pages[index]
        if instance is None:
            instance = self._build_page(module_path, label)
            self._pages[index] = (label, module_path, instance)
            self._stack.addWidget(instance)
        self._stack.setCurrentWidget(instance)
        self._tabs.set_active(index)

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
