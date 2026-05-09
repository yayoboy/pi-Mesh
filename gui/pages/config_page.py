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
    QColorDialog,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


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


class _MqttSection(QGroupBox):
    """MQTT bridge config: enabled, address, credentials, root prefix, flags."""

    def __init__(self, on_save, parent=None):
        super().__init__("MQTT", parent)
        self._on_save = on_save

        form = QFormLayout(self)
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
        save = QPushButton("Save MQTT")
        save.clicked.connect(self._save)
        save_row.addStretch(1)
        save_row.addWidget(save)
        form.addRow(save_row)

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
    """Theme picker + accent color. Writes to Settings, which fires the
    hot-reload subscriber wired up in :mod:`gui.app`."""

    def __init__(self, settings, parent=None):
        super().__init__("Display", parent)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Theme picker — radio-button-style buttons row.
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

        # Accent color picker.
        accent_row = QHBoxLayout()
        accent_row.addWidget(QLabel("Accent"))
        self._accent_swatch = QPushButton("")
        self._accent_swatch.setFixedSize(28, 22)
        self._accent_swatch.clicked.connect(self._pick_accent)
        accent_row.addWidget(self._accent_swatch)
        accent_row.addStretch(1)
        layout.addLayout(accent_row)

        self._refresh()

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
        body_layout.addWidget(self._device)
        body_layout.addWidget(self._lora)
        body_layout.addWidget(self._channels)
        body_layout.addWidget(self._mqtt)
        body_layout.addWidget(self._display)
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
