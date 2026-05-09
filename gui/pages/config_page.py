"""Config page: device identity and LoRa region/preset.

This is the minimal first cut covering the two most-used config subsections
from the web UI. The remaining categories (channels, MQTT, modules,
external notification, store-and-forward, range test, etc.) are out of
scope for this commit and remain to be added.
"""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


def _schedule_qt(coro) -> None:
    """Schedule a coroutine on the running qasync loop, no-op if no loop."""
    loop = asyncio.get_event_loop_policy().get_event_loop()
    if loop.is_running():
        loop.create_task(coro)


# Region/preset values from the Meshtastic protobuf RegionCode / ModemPreset enums.
_REGIONS = [
    "UNSET", "US", "EU_433", "EU_868", "CN", "JP", "ANZ", "KR", "TW",
    "RU", "IN", "NZ_865", "TH", "LORA_24", "UA_433", "UA_868", "MY_433",
    "MY_919", "SG_923",
]
_PRESETS = [
    "LONG_FAST", "LONG_SLOW", "VERY_LONG_SLOW", "MEDIUM_SLOW", "MEDIUM_FAST",
    "SHORT_SLOW", "SHORT_FAST", "LONG_MODERATE", "SHORT_TURBO",
]
_ROLES = [
    "CLIENT", "CLIENT_MUTE", "ROUTER", "ROUTER_CLIENT",
    "REPEATER", "TRACKER", "SENSOR", "TAK", "CLIENT_HIDDEN", "LOST_AND_FOUND",
    "TAK_TRACKER",
]


class _DeviceSection(QGroupBox):
    def __init__(self, on_save, parent=None):
        super().__init__("Device", parent)
        self._on_save = on_save

        form = QFormLayout(self)
        self._long = QLineEdit(self)
        self._long.setMaxLength(40)
        self._short = QLineEdit(self)
        self._short.setMaxLength(4)
        self._role = QComboBox(self)
        for r in _ROLES:
            self._role.addItem(r)

        form.addRow("Long name", self._long)
        form.addRow("Short name", self._short)
        form.addRow("Role", self._role)

        save_row = QHBoxLayout()
        save = QPushButton("Save device")
        save.clicked.connect(self._save)
        save_row.addStretch(1)
        save_row.addWidget(save)
        form.addRow(save_row)

    def fill(self, data: dict) -> None:
        self._long.setText(data.get("long_name") or "")
        self._short.setText(data.get("short_name") or "")
        role = data.get("role") or "CLIENT"
        idx = self._role.findText(role)
        self._role.setCurrentIndex(idx if idx >= 0 else 0)

    def _save(self) -> None:
        self._on_save(
            long_name=self._long.text().strip(),
            short_name=self._short.text().strip(),
            role=self._role.currentText(),
        )


class _WifiSection(QGroupBox):
    """WiFi: current status, scan/connect, saved profiles, static IP.

    All hits go through the FastAPI bridge (``/api/config/wifi/*``) so the
    GUI doesn't shell out directly. Useful even before the radio is talking.
    """

    def __init__(self, parent=None):
        super().__init__("WiFi", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._status = QLabel("(unknown)")
        self._status.setProperty("role", "muted")
        layout.addWidget(self._status)

        bar = QHBoxLayout()
        scan = QPushButton("Scan")
        scan.clicked.connect(self._on_scan)
        refresh = QPushButton("Status")
        refresh.clicked.connect(self._on_refresh_status)
        saved = QPushButton("Saved")
        saved.clicked.connect(self._on_show_saved)
        ip = QPushButton("IP…")
        ip.clicked.connect(self._on_show_ip_dialog)
        bar.addWidget(scan)
        bar.addWidget(refresh)
        bar.addWidget(saved)
        bar.addWidget(ip)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._networks = QListWidget(self)
        self._networks.setMaximumHeight(120)
        self._networks.itemActivated.connect(self._on_network_activated)
        layout.addWidget(self._networks)

        # Initial state
        _schedule_qt(self._refresh_status_async())

    def _on_scan(self) -> None:
        _schedule_qt(self._scan_async())

    def _on_refresh_status(self) -> None:
        _schedule_qt(self._refresh_status_async())

    async def _scan_async(self) -> None:
        self._status.setText("scanning…")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20.0) as c:
                r = await c.get("http://127.0.0.1:8080/api/config/wifi/scan")
                networks = r.json() if r.status_code == 200 else []
        except Exception:
            log.exception("wifi scan failed")
            networks = []
            self._status.setText("scan failed")
            return

        self._networks.clear()
        for net in networks:
            ssid = net.get("ssid", "?")
            signal = net.get("signal", 0)
            sec = net.get("security", "")
            text = f"{ssid}  ({signal}%)  {sec}".strip()
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, ssid)
            self._networks.addItem(item)
        self._status.setText(f"{len(networks)} networks")

    async def _refresh_status_async(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get("http://127.0.0.1:8080/api/config/wifi/status")
                d = r.json() if r.status_code == 200 else {}
        except Exception:
            self._status.setText("status unavailable")
            return
        ssid = d.get("ssid") or ""
        ip = d.get("ip") or ""
        if ssid:
            self._status.setText(f"connected: {ssid}  {ip}")
            self._status.setProperty("role", "ok")
        else:
            self._status.setText("not connected")
            self._status.setProperty("role", "muted")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _on_network_activated(self, item: QListWidgetItem) -> None:
        from PySide6.QtWidgets import QInputDialog
        ssid = item.data(Qt.ItemDataRole.UserRole)
        if not ssid:
            return
        password, ok = QInputDialog.getText(
            self, "WiFi", f"Password for {ssid!r}:", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        _schedule_qt(self._connect_async(ssid, password))

    async def _connect_async(self, ssid: str, password: str) -> None:
        self._status.setText(f"connecting to {ssid}…")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    "http://127.0.0.1:8080/api/config/wifi/connect",
                    json={"ssid": ssid, "password": password},
                )
            if r.status_code == 200:
                self._status.setText(f"connected: {ssid}")
                self._status.setProperty("role", "ok")
            else:
                err = r.json().get("error", "unknown error") if r.headers.get("content-type", "").startswith("application/json") else r.text
                self._status.setText(f"connect failed: {err}")
                self._status.setProperty("role", "danger")
        except Exception as exc:
            self._status.setText(f"connect failed: {exc}")
            self._status.setProperty("role", "danger")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    # -- Saved profiles ------------------------------------------------

    def _on_show_saved(self) -> None:
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QListWidget as _LW,
            QListWidgetItem as _LWI,
            QVBoxLayout,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Saved WiFi profiles")
        dlg.setModal(True)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Double-tap to delete a saved profile."))
        lw = _LW()
        v.addWidget(lw, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)

        async def populate():
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as c:
                    r = await c.get("http://127.0.0.1:8080/api/config/wifi/saved")
                items = r.json() if r.status_code == 200 else []
            except Exception:
                items = []
            for it in items:
                qit = _LWI(it.get("name") or "?")
                qit.setData(Qt.ItemDataRole.UserRole, it.get("name"))
                lw.addItem(qit)

        async def delete_one(name: str):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as c:
                    await c.delete(f"http://127.0.0.1:8080/api/config/wifi/saved/{name}")
            except Exception:
                log.exception("wifi delete failed")

        def on_dbl(item):
            name = item.data(Qt.ItemDataRole.UserRole)
            if not name:
                return
            if QMessageBox.question(self, "WiFi", f"Forget {name!r}?") != QMessageBox.StandardButton.Yes:
                return
            _schedule_qt(delete_one(name))
            row = lw.row(item)
            lw.takeItem(row)

        lw.itemDoubleClicked.connect(on_dbl)
        _schedule_qt(populate())
        dlg.exec()

    # -- Static IP -----------------------------------------------------

    def _on_show_ip_dialog(self) -> None:
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QRadioButton,
            QVBoxLayout,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("WiFi IP configuration")
        dlg.setModal(True)
        v = QVBoxLayout(dlg)

        method_row = QHBoxLayout()
        auto_btn = QRadioButton("DHCP (auto)")
        auto_btn.setChecked(True)
        manual_btn = QRadioButton("Static")
        method_row.addWidget(auto_btn)
        method_row.addWidget(manual_btn)
        method_row.addStretch(1)
        v.addLayout(method_row)

        form = QFormLayout()
        addr = QLineEdit()
        addr.setPlaceholderText("192.168.1.50/24")
        gw = QLineEdit()
        gw.setPlaceholderText("192.168.1.1")
        dns = QLineEdit()
        dns.setPlaceholderText("8.8.8.8 1.1.1.1")
        form.addRow("Address", addr)
        form.addRow("Gateway", gw)
        form.addRow("DNS", dns)
        v.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        body = {
            "method": "manual" if manual_btn.isChecked() else "auto",
            "address": addr.text().strip(),
            "gateway": gw.text().strip(),
            "dns": dns.text().strip(),
        }

        async def post():
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15.0) as c:
                    r = await c.post("http://127.0.0.1:8080/api/config/wifi/ip", json=body)
                if r.status_code == 200:
                    self._status.setText("IP config applied")
                    self._status.setProperty("role", "ok")
                else:
                    err = r.text[:120]
                    self._status.setText(f"IP failed: {err}")
                    self._status.setProperty("role", "danger")
            except Exception as exc:
                self._status.setText(f"IP error: {exc}")
                self._status.setProperty("role", "danger")
            self._status.style().unpolish(self._status)
            self._status.style().polish(self._status)

        _schedule_qt(post())


class _AdminSection(QGroupBox):
    """Destructive / system-level actions."""

    def __init__(self, on_factory_reset, on_reboot, on_pi_factory_reset, parent=None):
        super().__init__("Admin", parent)
        self._on_factory_reset = on_factory_reset
        self._on_reboot = on_reboot
        self._on_pi_factory_reset = on_pi_factory_reset

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        info = QLabel(
            "Operations below affect the local radio and the Pi. "
            "Factory resets wipe configuration — confirm twice."
        )
        info.setProperty("role", "muted")
        info.setWordWrap(True)
        layout.addWidget(info)

        row1 = QHBoxLayout()
        reboot_btn = QPushButton("Reboot Pi")
        reboot_btn.clicked.connect(self._reboot_clicked)
        radio_btn = QPushButton("Factory reset radio")
        radio_btn.clicked.connect(self._factory_reset_clicked)
        row1.addWidget(reboot_btn)
        row1.addWidget(radio_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        pi_factory_btn = QPushButton("Factory reset Pi")
        pi_factory_btn.setStyleSheet("color:#ef4444;")
        pi_factory_btn.clicked.connect(self._pi_factory_clicked)
        row2.addStretch(1)
        row2.addWidget(pi_factory_btn)
        layout.addLayout(row2)

    # ------------------------------------------------------------------

    def _reboot_clicked(self) -> None:
        if QMessageBox.question(
            self, "Reboot",
            "Reboot the Raspberry Pi now? Radio and GUI will be unavailable for ~30 s.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._on_reboot()

    def _factory_reset_clicked(self) -> None:
        # Two-step confirmation since this is destructive.
        first = QMessageBox.warning(
            self, "Factory reset",
            "This will WIPE the radio configuration. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if first != QMessageBox.StandardButton.Yes:
            return
        confirm = QMessageBox.warning(
            self, "Factory reset (last chance)",
            "Are you absolutely sure? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._on_factory_reset()

    def _pi_factory_clicked(self) -> None:
        # Triple-confirmation: it wipes the local pi-Mesh state.
        first = QMessageBox.warning(
            self, "Pi factory reset",
            "This wipes the pi-Mesh database, settings and logs on this Pi. "
            "The radio configuration is NOT touched. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if first != QMessageBox.StandardButton.Yes:
            return
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "Pi factory reset",
            "Type WIPE to confirm:",
        )
        if not ok or text.strip() != "WIPE":
            return
        self._on_pi_factory_reset()


class _MqttSection(QGroupBox):
    """MQTT bridge config: enabled, address, credentials, root prefix, flags.

    Header label shows the live bridge state from
    ``/api/config/mqtt/status`` so the user can tell at a glance whether
    the bridge process is actually connected.
    """

    def __init__(self, on_save, parent=None):
        super().__init__("MQTT", parent)
        self._on_save = on_save

        # Live-status banner above the form.
        self._live_status = QLabel("…")
        self._live_status.setProperty("role", "muted")

        form = QFormLayout(self)
        form.addRow("Bridge", self._live_status)
        self._enabled = QPushButton("disabled")
        self._enabled.setCheckable(True)
        self._enabled.toggled.connect(
            lambda checked: self._enabled.setText("enabled" if checked else "disabled")
        )

        self._address = QLineEdit(self)
        self._address.setPlaceholderText("mqtt.meshtastic.org")
        self._username = QLineEdit(self)
        self._password = QLineEdit(self)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._root = QLineEdit(self)
        self._root.setPlaceholderText("msh")

        self._encryption = QPushButton("encryption")
        self._encryption.setCheckable(True)
        self._tls = QPushButton("TLS")
        self._tls.setCheckable(True)
        self._json = QPushButton("JSON")
        self._json.setCheckable(True)
        self._proxy = QPushButton("proxy")
        self._proxy.setCheckable(True)
        self._map_report = QPushButton("map report")
        self._map_report.setCheckable(True)

        form.addRow("State", self._enabled)
        form.addRow("Address", self._address)
        form.addRow("User", self._username)
        form.addRow("Pass", self._password)
        form.addRow("Root", self._root)

        flags_a = QHBoxLayout()
        for w in (self._encryption, self._tls, self._json):
            flags_a.addWidget(w)
        form.addRow("Flags", flags_a)
        flags_b = QHBoxLayout()
        for w in (self._proxy, self._map_report):
            flags_b.addWidget(w)
        form.addRow("", flags_b)

        save_row = QHBoxLayout()
        refresh = QPushButton("Refresh status")
        refresh.clicked.connect(self._refresh_status)
        save = QPushButton("Save MQTT")
        save.clicked.connect(self._save)
        save_row.addWidget(refresh)
        save_row.addStretch(1)
        save_row.addWidget(save)
        form.addRow(save_row)

        # Background poll of the bridge status so the banner stays fresh.
        from PySide6.QtCore import QTimer
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(15000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()
        self._refresh_status()

    def _refresh_status(self) -> None:
        _schedule_qt(self._refresh_status_async())

    async def _refresh_status_async(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get("http://127.0.0.1:8080/api/config/mqtt/status")
            d = r.json() if r.status_code == 200 else {}
        except Exception:
            d = {}
        if not d.get("available"):
            self._live_status.setText("paho-mqtt not installed")
            self._live_status.setProperty("role", "danger")
        elif not d.get("enabled"):
            self._live_status.setText("disabled")
            self._live_status.setProperty("role", "muted")
        elif d.get("connected"):
            self._live_status.setText(f"connected → {d.get('broker') or '?'}")
            self._live_status.setProperty("role", "ok")
        else:
            self._live_status.setText(f"disconnected (configured: {d.get('broker') or '?'})")
            self._live_status.setProperty("role", "warn")
        self._live_status.style().unpolish(self._live_status)
        self._live_status.style().polish(self._live_status)

    def fill(self, data: dict) -> None:
        self._enabled.setChecked(bool(data.get("enabled")))
        self._enabled.setText("enabled" if self._enabled.isChecked() else "disabled")
        self._address.setText(data.get("address") or "")
        self._username.setText(data.get("username") or "")
        self._password.setText(data.get("password") or "")
        self._root.setText(data.get("root") or "")
        self._encryption.setChecked(bool(data.get("encryption_enabled")))
        self._tls.setChecked(bool(data.get("tls_enabled")))
        self._json.setChecked(bool(data.get("json_enabled")))
        self._proxy.setChecked(bool(data.get("proxy_to_client_enabled")))
        self._map_report.setChecked(bool(data.get("map_reporting_enabled")))

    def _save(self) -> None:
        self._on_save({
            "enabled":                  self._enabled.isChecked(),
            "address":                  self._address.text().strip(),
            "username":                 self._username.text(),
            "password":                 self._password.text(),
            "root":                     self._root.text().strip(),
            "encryption_enabled":       self._encryption.isChecked(),
            "tls_enabled":              self._tls.isChecked(),
            "json_enabled":             self._json.isChecked(),
            "proxy_to_client_enabled":  self._proxy.isChecked(),
            "map_reporting_enabled":    self._map_report.isChecked(),
        })


class _ChannelsSection(QGroupBox):
    """List of mesh channels with edit dialogs.

    Channel 0 (PRIMARY) cannot be renamed; the others can. PSK is shown as
    base64; ``random`` generates a new 256-bit key.
    """

    def __init__(self, on_save_channel, parent=None):
        super().__init__("Channels", parent)
        self._on_save_channel = on_save_channel

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._rows: list[QWidget] = []
        self._container = QWidget(self)
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(2)
        layout.addWidget(self._container)

        self._empty = QLabel("(no channels read yet)")
        self._empty.setProperty("role", "muted")
        layout.addWidget(self._empty)

    def fill(self, channels: list[dict]) -> None:
        # Wipe rows
        for row in self._rows:
            self._container_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        if not channels:
            self._empty.show()
            return
        self._empty.hide()

        for ch in channels:
            row = self._build_row(ch)
            self._container_layout.addWidget(row)
            self._rows.append(row)

    def _build_row(self, ch: dict) -> QWidget:
        row = QWidget(self._container)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        idx = ch.get("index", 0)
        role = ch.get("role", "DISABLED")
        name = ch.get("name") or (f"Primary" if idx == 0 else f"Ch {idx}")

        label = QLabel(f"{idx}  {name}")
        label.setProperty("role", "muted" if role == "DISABLED" else None)
        rl.addWidget(label, 1)

        role_lbl = QLabel(role)
        role_lbl.setProperty("role", "muted")
        rl.addWidget(role_lbl)

        edit = QPushButton("Edit")
        edit.setFixedWidth(56)
        edit.clicked.connect(lambda: self._edit(ch))
        rl.addWidget(edit)
        return row

    def _edit(self, ch: dict) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Channel {ch.get('index', 0)}")
        dlg.setModal(True)
        form = QFormLayout(dlg)

        name_edit = QLineEdit(ch.get("name") or "")
        name_edit.setMaxLength(11)
        psk_edit = QLineEdit(ch.get("psk_b64") or "")
        psk_edit.setPlaceholderText("base64 PSK or empty")
        form.addRow("Name", name_edit)
        form.addRow("PSK", psk_edit)

        random_btn = QPushButton("Random PSK")
        random_btn.clicked.connect(lambda: psk_edit.setText(_random_psk_b64()))
        form.addRow(random_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._on_save_channel(
            index=ch.get("index", 0),
            name=name_edit.text().strip(),
            psk_b64=psk_edit.text().strip(),
        )


from gui.pages._psk import random_psk_b64 as _random_psk_b64  # noqa: E402  (kept name for backward-compat in this module)


class _DisplaySection(QGroupBox):
    """Theme picker + accent color + brightness + rotation.

    Theme/accent writes go through ``Settings.set`` which triggers the
    hot-reload subscriber in :mod:`gui.app`. Brightness and rotation POST
    to ``/api/config/display`` since they need OS-level effect (PWM on the
    backlight, dtoverlay rewrite + xrandr rotate).
    """

    def __init__(self, settings, parent=None):
        super().__init__("Display", parent)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Theme picker
        theme_row = QHBoxLayout()
        theme_row.setSpacing(4)
        theme_row.addWidget(QLabel("Theme"))
        self._theme_buttons: dict[str, QPushButton] = {}
        for name in ("dark", "light", "hc", "custom"):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, n=name: self._on_theme_clicked(n))
            theme_row.addWidget(btn)
            self._theme_buttons[name] = btn
        theme_row.addStretch(1)
        layout.addLayout(theme_row)

        # --- Accent color
        accent_row = QHBoxLayout()
        accent_row.addWidget(QLabel("Accent"))
        self._accent_swatch = QPushButton("")
        self._accent_swatch.setFixedSize(28, 22)
        self._accent_swatch.clicked.connect(self._pick_accent)
        accent_row.addWidget(self._accent_swatch)
        accent_row.addStretch(1)
        layout.addLayout(accent_row)

        # --- Brightness slider
        bri_row = QHBoxLayout()
        bri_row.addWidget(QLabel("Brightness"))
        self._brightness = QSlider(Qt.Orientation.Horizontal)
        self._brightness.setRange(0, 255)
        self._brightness.setValue(255)
        self._brightness_value = QLabel("255")
        self._brightness_value.setMinimumWidth(28)
        self._brightness.valueChanged.connect(
            lambda v: self._brightness_value.setText(str(v))
        )
        self._brightness.sliderReleased.connect(self._on_brightness_release)
        bri_row.addWidget(self._brightness, 1)
        bri_row.addWidget(self._brightness_value)
        layout.addLayout(bri_row)

        # --- Rotation buttons
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Rotation"))
        self._rotation_buttons: dict[int, QPushButton] = {}
        for deg in (0, 90, 180, 270):
            btn = QPushButton(f"{deg}°")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c, d=deg: self._on_rotation_clicked(d))
            rot_row.addWidget(btn)
            self._rotation_buttons[deg] = btn
        rot_row.addStretch(1)
        layout.addLayout(rot_row)

        self._refresh()
        # Async fetch of OS-level brightness/rotation via /api/config/display.
        _schedule_qt(self._fetch_display())

    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        if self._settings is None:
            return
        current = self._settings.get("display.theme", "dark") or "dark"
        for name, btn in self._theme_buttons.items():
            btn.setChecked(name == current)
        accent = self._settings.get("pimesh-accent") or "#4a9eff"
        self._set_swatch_color(accent)

    def _on_theme_clicked(self, name: str) -> None:
        if self._settings is None:
            return
        self._settings.set("display.theme", name)
        for n, btn in self._theme_buttons.items():
            btn.setChecked(n == name)

    def _pick_accent(self) -> None:
        if self._settings is None:
            return
        current = QColor(self._settings.get("pimesh-accent") or "#4a9eff")
        chosen = QColorDialog.getColor(current, self, "Accent color")
        if chosen.isValid():
            value = chosen.name()
            self._settings.set("pimesh-accent", value)
            self._set_swatch_color(value)

    def _set_swatch_color(self, hex_color: str) -> None:
        self._accent_swatch.setStyleSheet(
            f"background:{hex_color}; border:1px solid #444; border-radius:3px;"
        )

    # -- brightness & rotation ----------------------------------------

    async def _fetch_display(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as c:
                r = await c.get("http://127.0.0.1:8080/api/config/display")
            if r.status_code == 200:
                d = r.json()
                self._brightness.setValue(int(d.get("brightness", 255)))
                self._brightness_value.setText(str(self._brightness.value()))
                self._set_rotation_active(int(d.get("rotation", 0)))
        except Exception:
            log.debug("display fetch failed", exc_info=True)

    def _on_brightness_release(self) -> None:
        _schedule_qt(self._post_display(brightness=self._brightness.value()))

    def _on_rotation_clicked(self, deg: int) -> None:
        if QMessageBox.question(
            self, "Rotation",
            f"Set rotation to {deg}°? The Pi will reboot to apply.",
        ) != QMessageBox.StandardButton.Yes:
            self._refresh_rotation_buttons_from_settings()
            return
        self._set_rotation_active(deg)
        _schedule_qt(self._post_display(rotation=deg))

    def _refresh_rotation_buttons_from_settings(self) -> None:
        # Best-effort: re-query OS state.
        _schedule_qt(self._fetch_display())

    def _set_rotation_active(self, deg: int) -> None:
        for d, btn in self._rotation_buttons.items():
            btn.setChecked(d == deg)

    async def _post_display(self, *, brightness: int | None = None, rotation: int | None = None) -> None:
        body: dict[str, int] = {}
        if brightness is not None:
            body["brightness"] = brightness
        if rotation is not None:
            body["rotation"] = rotation
        if not body:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as c:
                await c.post("http://127.0.0.1:8080/api/config/display", json=body)
        except Exception:
            log.exception("display POST failed")
            QMessageBox.warning(self, "Display", "Failed to apply display change.")


class _LoraSection(QGroupBox):
    def __init__(self, on_save, parent=None):
        super().__init__("LoRa", parent)
        self._on_save = on_save

        form = QFormLayout(self)
        self._region = QComboBox(self)
        self._region.addItems(_REGIONS)
        self._preset = QComboBox(self)
        self._preset.addItems(_PRESETS)
        form.addRow("Region", self._region)
        form.addRow("Preset", self._preset)

        save_row = QHBoxLayout()
        save = QPushButton("Save LoRa")
        save.clicked.connect(self._save)
        save_row.addStretch(1)
        save_row.addWidget(save)
        form.addRow(save_row)

    def fill(self, data: dict) -> None:
        region = data.get("region") or "UNSET"
        preset = data.get("modem_preset") or "LONG_FAST"
        ri = self._region.findText(region)
        pi = self._preset.findText(preset)
        if ri >= 0:
            self._region.setCurrentIndex(ri)
        if pi >= 0:
            self._preset.setCurrentIndex(pi)

    def _save(self) -> None:
        self._on_save(
            region=self._region.currentText(),
            preset=self._preset.currentText(),
        )


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._status = QLabel("loading…")
        self._status.setProperty("role", "muted")
        layout.addWidget(self._status)

        # Wrap forms in a scroll area so the page works on a 320×480 portrait.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        self._device = _DeviceSection(self._save_device, body)
        self._lora = _LoraSection(self._save_lora, body)
        self._channels = _ChannelsSection(self._save_channel, body)
        self._mqtt = _MqttSection(self._save_mqtt, body)
        self._display = _DisplaySection(self._settings, body)
        self._wifi = _WifiSection(body)
        self._admin = _AdminSection(
            self._do_factory_reset, self._do_reboot, self._do_pi_factory_reset, body,
        )

        # Wrap each section in a CollapsibleSection so the whole Config page
        # fits more comfortably on a 320×480 screen. First item defaults to
        # expanded, the rest are collapsed.
        from gui.widgets.collapsible import CollapsibleSection

        sections: list[tuple[str, QWidget]] = [
            ("Device", self._device),
            ("LoRa", self._lora),
            ("Channels", self._channels),
            ("MQTT", self._mqtt),
            ("Display", self._display),
            ("WiFi", self._wifi),
            ("Admin", self._admin),
        ]

        # Module configs (telemetry, canned, range test, neighbor info,
        # store-and-forward, external notification, ambient lighting,
        # detection sensor, serial). All driven by ModuleSpec data.
        from gui.pages._module_section import ModuleSection
        from gui.pages._module_specs import ALL_MODULE_SPECS
        self._modules: list[ModuleSection] = []
        for spec in ALL_MODULE_SPECS:
            section = ModuleSection(spec, body)
            self._modules.append(section)
            sections.append((spec.title, section))

        # Hardware-side sections.
        from gui.pages._hardware_sections import (
            _AlertsSection,
            _ApSection,
            _CannedMessagesSection,
            _GpioSection,
            _I2cSection,
            _MapConfigSection,
            _RtcSection,
            _SerialSection,
            _UsbStorageSection,
        )
        sections.extend([
            ("Serial port",      _SerialSection(body)),
            ("GPIO devices",     _GpioSection(body)),
            ("I2C scan",         _I2cSection(body)),
            ("RTC",              _RtcSection(body)),
            ("AP mode",          _ApSection(body)),
            ("Alerts",           _AlertsSection(body)),
            ("Map config",       _MapConfigSection(body)),
            ("Canned messages",  _CannedMessagesSection(body)),
            ("USB storage",      _UsbStorageSection(body)),
        ])

        for i, (title, widget) in enumerate(sections):
            wrap = CollapsibleSection(title, body, expanded=(i == 0))
            wrap.add_widget(widget)
            body_layout.addWidget(wrap)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        self._reload()

    # ------------------------------------------------------------------

    def _reload(self) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._reload_async())

    async def _reload_async(self) -> None:
        try:
            import config as cfg
            import meshtasticd_client
            node = await meshtasticd_client.get_node_config(cfg.DB_PATH)
            lora = await meshtasticd_client.get_lora_config(cfg.DB_PATH)
            channels = await meshtasticd_client.get_channels(cfg.DB_PATH)
            mqtt = await meshtasticd_client.get_mqtt_config(cfg.DB_PATH)
        except Exception:
            log.exception("config reload failed")
            self._status.setText("error loading config")
            self._status.setProperty("role", "danger")
            return

        cached = node.get("cached") or lora.get("cached") or mqtt.get("cached")
        self._status.setText("cached (radio offline)" if cached else "live")
        self._status.setProperty("role", "warn" if cached else "ok")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

        self._device.fill(node)
        self._lora.fill(lora)
        self._channels.fill(channels or [])
        self._mqtt.fill(mqtt or {})

        # Refresh every generic module section in parallel.
        for section in self._modules:
            section.reload()

    # Save handlers -----------------------------------------------------

    def _save_device(self, *, long_name: str, short_name: str, role: str) -> None:
        if not long_name or not short_name:
            QMessageBox.warning(self, "Config", "Long and short name are required.")
            return
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._save_device_async(long_name, short_name, role))

    async def _save_device_async(self, long_name: str, short_name: str, role: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.set_node_config(long_name, short_name, role)
        except Exception:
            log.exception("set_node_config failed")
            QMessageBox.critical(self, "Config", "Failed to save device config.")
            return
        self._status.setText("device config queued")
        self._status.setProperty("role", "ok")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _save_lora(self, *, region: str, preset: str) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._save_lora_async(region, preset))

    async def _save_lora_async(self, region: str, preset: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.set_lora_config(region, preset)
        except Exception:
            log.exception("set_lora_config failed")
            QMessageBox.critical(self, "Config", "Failed to save LoRa config.")
            return
        self._status.setText("LoRa config queued")
        self._status.setProperty("role", "ok")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _save_mqtt(self, params: dict) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._save_mqtt_async(params))

    async def _save_mqtt_async(self, params: dict) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.set_mqtt_config(params)
        except Exception:
            log.exception("set_mqtt_config failed")
            QMessageBox.critical(self, "Config", "Failed to save MQTT config.")
            return
        self._status.setText("MQTT config queued")
        self._status.setProperty("role", "ok")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _save_channel(self, *, index: int, name: str, psk_b64: str) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._save_channel_async(index, name, psk_b64))

    def _do_reboot(self) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._reboot_pi())

    async def _reboot_pi(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient() as c:
                await c.post("http://127.0.0.1:8080/api/system/reboot")
        except Exception:
            log.exception("reboot failed")
            QMessageBox.warning(self, "Admin", "Failed to issue reboot.")

    def _do_factory_reset(self) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._factory_reset_async())

    def _do_pi_factory_reset(self) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._pi_factory_reset_async())

    async def _pi_factory_reset_async(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post("http://127.0.0.1:8080/api/system/factory-reset")
            if r.status_code != 200:
                QMessageBox.warning(self, "Admin", f"Pi factory reset failed: {r.text[:120]}")
                return
        except Exception as exc:
            QMessageBox.warning(self, "Admin", f"Pi factory reset error: {exc}")
            return
        self._status.setText("Pi factory reset queued")
        self._status.setProperty("role", "warn")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    async def _factory_reset_async(self) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.factory_reset()
        except Exception:
            log.exception("factory_reset failed")
            QMessageBox.warning(self, "Admin", "Failed to queue factory reset.")
            return
        self._status.setText("factory reset queued")
        self._status.setProperty("role", "warn")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    async def _save_channel_async(self, index: int, name: str, psk_b64: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.set_channel(index, name, psk_b64)
        except Exception:
            log.exception("set_channel failed")
            QMessageBox.critical(self, "Config", f"Failed to save channel {index}.")
            return
        self._status.setText(f"channel {index} queued")
        self._status.setProperty("role", "ok")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        # Reload channel list
        self._reload()
