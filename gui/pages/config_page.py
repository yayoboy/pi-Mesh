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
from PySide6.QtWidgets import (
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
        body_layout.addWidget(self._device)
        body_layout.addWidget(self._lora)
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
        except Exception:
            log.exception("config reload failed")
            self._status.setText("error loading config")
            self._status.setProperty("role", "danger")
            return

        cached = node.get("cached") or lora.get("cached")
        self._status.setText("cached (radio offline)" if cached else "live")
        self._status.setProperty("role", "warn" if cached else "ok")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

        self._device.fill(node)
        self._lora.fill(lora)

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
