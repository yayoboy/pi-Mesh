"""Hardware-side Config sections: I2C scan, RTC, AP toggle, GPIO devices.

All hits go through the running FastAPI bridge (``/api/config/*``) so the
GUI process never shells out to ``i2cdetect``, ``nmcli``, ``hwclock`` etc.
itself — that work continues to live behind the existing routers.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# I2C scan
# ---------------------------------------------------------------------------

class _I2cSection(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("I2C scan", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Bus"))
        self._bus = QSpinBox(self)
        self._bus.setRange(0, 7)
        self._bus.setValue(1)
        bar.addWidget(self._bus)
        scan = QPushButton("Scan")
        scan.clicked.connect(self._on_scan)
        bar.addWidget(scan)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._results = QLabel("(idle)")
        self._results.setProperty("role", "muted")
        self._results.setWordWrap(True)
        layout.addWidget(self._results)

    def _on_scan(self) -> None:
        from gui import backend
        self._results.setText("scanning…")
        bus = self._bus.value()
        try:
            data = backend.i2c_scan(bus=bus)
        except Exception as exc:
            self._results.setText(f"scan failed: {exc}")
            return
        # backend returns either a list of addresses or a parsed structure.
        if isinstance(data, list):
            self._results.setText(", ".join(str(d) for d in data) if data else "no devices")
        elif isinstance(data, dict) and "devices" in data:
            devs = data["devices"]
            self._results.setText(", ".join(str(d) for d in devs) if devs else "no devices")
        else:
            self._results.setText(json.dumps(data, separators=(",", ":")))


# ---------------------------------------------------------------------------
# RTC status
# ---------------------------------------------------------------------------

class _RtcSection(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("RTC", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._status = QLabel("loading…")
        self._status.setProperty("role", "muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        bar = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        bar.addStretch(1)
        bar.addWidget(refresh)
        layout.addLayout(bar)

        self._refresh()

    def _refresh(self) -> None:
        from gui import backend
        try:
            d = backend.rtc_status()
        except Exception:
            self._status.setText("status unavailable")
            return
        configured = d.get("configured")
        model = d.get("model") or "—"
        device = d.get("device") or "—"
        time_str = d.get("time") or "—"
        text = (
            f"configured: {'yes' if configured else 'no'}\n"
            f"model: {model}\n"
            f"device: {device}\n"
            f"time: {time_str}"
        )
        self._status.setText(text)
        self._status.setProperty("role", "ok" if configured else "muted")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)


# ---------------------------------------------------------------------------
# AP toggle
# ---------------------------------------------------------------------------

class _ApSection(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("AP mode", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._status = QLabel("…")
        self._status.setProperty("role", "muted")
        layout.addWidget(self._status)

        bar = QHBoxLayout()
        self._toggle = QPushButton("Toggle AP")
        self._toggle.clicked.connect(self._on_toggle)
        bar.addWidget(self._toggle)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        bar.addWidget(refresh)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._refresh()

    def _refresh(self) -> None:
        from gui import backend
        try:
            d = backend.ap_status()
        except Exception:
            self._status.setText("status unavailable")
            return
        if d.get("active"):
            self._status.setText(f"AP active ({d.get('name', '?')})")
            self._status.setProperty("role", "ok")
        else:
            self._status.setText("AP not active")
            self._status.setProperty("role", "muted")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _on_toggle(self) -> None:
        if QMessageBox.question(
            self, "AP", "Toggle AP mode now?",
        ) != QMessageBox.StandardButton.Yes:
            return
        from gui import backend
        try:
            d = backend.ap_toggle()
            self._status.setText(d.get("message") or ("AP active" if d.get("active") else "AP off"))
        except Exception as exc:
            self._status.setText(f"toggle failed: {exc}")


# ---------------------------------------------------------------------------
# GPIO devices
# ---------------------------------------------------------------------------

GPIO_TYPES = ["button", "led", "rotary", "i2c_sensor", "rtc"]


class _GpioDeviceDialog(QDialog):
    """Add or edit a GPIO device entry."""

    def __init__(self, dev: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GPIO device" if dev is None else "Edit device")
        self.setModal(True)

        d = dev or {}
        form = QFormLayout(self)
        self._type = QComboBox(self)
        self._type.addItems(GPIO_TYPES)
        idx = self._type.findText(d.get("type", "button"))
        if idx >= 0:
            self._type.setCurrentIndex(idx)
        self._name = QLineEdit(d.get("name") or "")
        self._enabled = QPushButton("enabled")
        self._enabled.setCheckable(True)
        self._enabled.setChecked(bool(d.get("enabled", 1)))
        self._enabled.toggled.connect(
            lambda c: self._enabled.setText("enabled" if c else "disabled")
        )
        self._enabled.setText("enabled" if self._enabled.isChecked() else "disabled")
        self._pin_a = QSpinBox(self); self._pin_a.setRange(0, 64); self._pin_a.setValue(int(d.get("pin_a") or 0))
        self._pin_b = QSpinBox(self); self._pin_b.setRange(0, 64); self._pin_b.setValue(int(d.get("pin_b") or 0))
        self._pin_sw = QSpinBox(self); self._pin_sw.setRange(0, 64); self._pin_sw.setValue(int(d.get("pin_sw") or 0))
        self._i2c_bus = QSpinBox(self); self._i2c_bus.setRange(0, 7); self._i2c_bus.setValue(int(d.get("i2c_bus") or 1))
        self._i2c_addr = QLineEdit(d.get("i2c_address") or "")
        self._sensor_type = QLineEdit(d.get("sensor_type") or "")
        self._action = QLineEdit(d.get("action") or "")
        self._config_json = QTextEdit()
        self._config_json.setPlainText(d.get("config_json") or "{}")
        self._config_json.setFixedHeight(50)

        form.addRow("Type", self._type)
        form.addRow("Name", self._name)
        form.addRow("State", self._enabled)
        form.addRow("Pin A", self._pin_a)
        form.addRow("Pin B", self._pin_b)
        form.addRow("Pin SW", self._pin_sw)
        form.addRow("I2C bus", self._i2c_bus)
        form.addRow("I2C addr", self._i2c_addr)
        form.addRow("Sensor type", self._sensor_type)
        form.addRow("Action", self._action)
        form.addRow("Config JSON", self._config_json)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def to_payload(self) -> dict:
        return {
            "type":         self._type.currentText(),
            "name":         self._name.text().strip(),
            "enabled":      1 if self._enabled.isChecked() else 0,
            "pin_a":        self._pin_a.value() or None,
            "pin_b":        self._pin_b.value() or None,
            "pin_sw":       self._pin_sw.value() or None,
            "i2c_bus":      self._i2c_bus.value(),
            "i2c_address":  self._i2c_addr.text().strip() or None,
            "sensor_type":  self._sensor_type.text().strip() or None,
            "action":       self._action.text().strip() or None,
            "config_json":  self._config_json.toPlainText().strip() or "{}",
        }


class _GpioSection(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("GPIO devices", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self._on_add)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        bar.addWidget(add)
        bar.addWidget(refresh)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._list = QListWidget(self)
        self._list.setMaximumHeight(140)
        self._list.itemDoubleClicked.connect(self._on_edit)
        layout.addWidget(self._list)

        row_btns = QHBoxLayout()
        edit = QPushButton("Edit")
        delete = QPushButton("Delete")
        test = QPushButton("Test")
        edit.clicked.connect(lambda: self._on_edit(self._list.currentItem()))
        delete.clicked.connect(self._on_delete)
        test.clicked.connect(self._on_test)
        row_btns.addWidget(edit)
        row_btns.addWidget(delete)
        row_btns.addWidget(test)
        row_btns.addStretch(1)
        layout.addLayout(row_btns)

        self._refresh()

    def _refresh(self) -> None:
        from gui import backend
        try:
            devices = backend.get_gpio_devices()
        except Exception:
            log.exception("gpio refresh failed")
            devices = []
        self._list.clear()
        for d in devices:
            label = f"#{d.get('id')}  {d.get('type', '?')}  {d.get('name', '?')}"
            if not d.get("enabled"):
                label += "  (disabled)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, d)
            self._list.addItem(item)

    def _on_add(self) -> None:
        dlg = _GpioDeviceDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            from gui import backend
            try:
                backend.add_gpio_device(dlg.to_payload())
            except Exception:
                log.exception("gpio add failed")
                QMessageBox.warning(self, "GPIO", "Add failed.")
            self._refresh()

    def _on_edit(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        dev = item.data(Qt.ItemDataRole.UserRole)
        if not dev:
            return
        dlg = _GpioDeviceDialog(dev, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            from gui import backend
            try:
                backend.update_gpio_device(dev["id"], dlg.to_payload())
            except Exception:
                log.exception("gpio update failed")
                QMessageBox.warning(self, "GPIO", "Update failed.")
            self._refresh()

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        dev = item.data(Qt.ItemDataRole.UserRole)
        if not dev:
            return
        if QMessageBox.question(
            self, "GPIO", f"Delete device #{dev.get('id')} ({dev.get('name')})?",
        ) != QMessageBox.StandardButton.Yes:
            return
        from gui import backend
        try:
            backend.delete_gpio_device(dev["id"])
        except Exception:
            log.exception("gpio delete failed")
            QMessageBox.warning(self, "GPIO", "Delete failed.")
        self._refresh()

    def _on_test(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        dev = item.data(Qt.ItemDataRole.UserRole)
        if not dev:
            return
        from gui import backend
        result = backend.test_gpio(dev["id"])
        if result.get("ok"):
            QMessageBox.information(self, "GPIO test", result.get("result", "OK"))
        else:
            QMessageBox.warning(self, "GPIO test", result.get("error", "Test failed"))


# ---------------------------------------------------------------------------
# USB storage
# ---------------------------------------------------------------------------

class _SerialSection(QGroupBox):
    """Serial port selection for the Meshtastic board.

    Lists available ports and writes the choice via backend.set_serial_port
    (persists in config.env).
    """

    def __init__(self, parent=None):
        super().__init__("Serial port", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Port"))
        self._combo = QComboBox(self)
        bar.addWidget(self._combo, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        save = QPushButton("Apply")
        save.clicked.connect(self._on_save)
        bar.addWidget(refresh)
        bar.addWidget(save)
        layout.addLayout(bar)

        self._info = QLabel("…")
        self._info.setProperty("role", "muted")
        layout.addWidget(self._info)

        self._refresh()

    def _refresh(self) -> None:
        from gui import backend
        try:
            data = backend.list_serial_ports()
        except Exception:
            data = {}
        ports = data.get("ports") if isinstance(data, dict) else data
        ports = ports or []
        current = data.get("current") if isinstance(data, dict) else None

        self._combo.clear()
        for p in ports:
            self._combo.addItem(p)
        if current:
            idx = self._combo.findText(current)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
            self._info.setText(f"current: {current}")
        else:
            self._info.setText(f"{len(ports)} ports detected")

    def _on_save(self) -> None:
        port = self._combo.currentText().strip()
        if not port:
            return
        if QMessageBox.question(
            self, "Serial",
            f"Switch to {port}? meshtasticd will be restarted.",
        ) != QMessageBox.StandardButton.Yes:
            return
        from gui import backend
        try:
            r = backend.set_serial_port(port)
            if r.get("ok", True):
                self._info.setText(f"applied: {port}")
            else:
                self._info.setText(f"failed: {r.get('error', '')}")
        except Exception as exc:
            self._info.setText(f"error: {exc}")


class _AlertsSection(QGroupBox):
    """Threshold values for the alerts system (offline/battery/RAM)."""

    def __init__(self, parent=None):
        super().__init__("Alerts thresholds", parent)
        form = QFormLayout(self)

        self._offline = QSpinBox(self)
        self._offline.setRange(1, 24 * 60)
        self._offline.setSuffix(" min")
        self._battery = QSpinBox(self)
        self._battery.setRange(0, 100)
        self._battery.setSuffix(" %")
        self._ram = QSpinBox(self)
        self._ram.setRange(0, 100)
        self._ram.setSuffix(" %")

        form.addRow("Node offline after", self._offline)
        form.addRow("Battery low below", self._battery)
        form.addRow("RAM high above", self._ram)

        save_row = QHBoxLayout()
        save = QPushButton("Save thresholds")
        save.clicked.connect(self._on_save)
        save_row.addStretch(1)
        save_row.addWidget(save)
        form.addRow(save_row)

        self._refresh()

    def _refresh(self) -> None:
        from gui import backend
        try:
            d = backend.get_alert_config()
        except Exception:
            d = {}
        self._offline.setValue(int(d.get("node_offline_min", 30)))
        self._battery.setValue(int(d.get("battery_low", 20)))
        self._ram.setValue(int(d.get("ram_high", 90)))

    def _on_save(self) -> None:
        from gui import backend
        body = {
            "node_offline_min": self._offline.value(),
            "battery_low": self._battery.value(),
            "ram_high": self._ram.value(),
        }
        try:
            r = backend.set_alert_config(body)
            if not r.get("ok", True):
                QMessageBox.warning(self, "Alerts", f"Save failed: {r.get('error', '')}")
        except Exception:
            log.exception("alerts save failed")
            QMessageBox.warning(self, "Alerts", "Save failed.")


class _MapConfigSection(QGroupBox):
    """Map config: local tiles toggle + region readout (read-only)."""

    def __init__(self, parent=None):
        super().__init__("Map config", parent)
        form = QFormLayout(self)

        self._local_tiles = QPushButton("local tiles off")
        self._local_tiles.setCheckable(True)
        self._local_tiles.toggled.connect(
            lambda c: self._local_tiles.setText(
                "local tiles on" if c else "local tiles off"
            )
        )
        self._region = QLabel("—")
        self._region.setProperty("role", "muted")
        self._tiles_present = QLabel("—")
        self._tiles_present.setProperty("role", "muted")

        form.addRow("Use local tiles", self._local_tiles)
        form.addRow("Region", self._region)
        form.addRow("Tiles present", self._tiles_present)

        save_row = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self._on_save)
        save_row.addStretch(1)
        save_row.addWidget(save)
        form.addRow(save_row)

        self._refresh()

    def _refresh(self) -> None:
        from gui import backend
        try:
            d = backend.get_map_config()
        except Exception:
            d = {}
        self._local_tiles.setChecked(bool(d.get("local_tiles")))
        self._region.setText(str(d.get("region") or "—"))
        self._tiles_present.setText("yes" if d.get("tiles_present") else "no")

    def _on_save(self) -> None:
        from gui import backend
        body = {"local_tiles": self._local_tiles.isChecked()}
        try:
            backend.set_map_config(body)
        except Exception:
            log.exception("map config save failed")
            QMessageBox.warning(self, "Map", "Save failed.")


class _CannedMessagesSection(QGroupBox):
    """CRUD list of pre-canned message texts. The Messages page reads this
    list to populate its quick-insert menu.
    """

    def __init__(self, parent=None):
        super().__init__("Canned messages", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self._on_add)
        edit = QPushButton("Edit")
        edit.clicked.connect(self._on_edit)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._on_delete)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        for b in (add, edit, delete, refresh):
            bar.addWidget(b)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._list = QListWidget(self)
        self._list.setMaximumHeight(140)
        self._list.itemDoubleClicked.connect(lambda _it: self._on_edit())
        layout.addWidget(self._list)

        self._refresh()

    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        from gui import backend
        try:
            items = backend.get_canned_messages()
        except Exception:
            items = []
        self._list.clear()
        for it in items:
            text = it.get("text") or ""
            short = text if len(text) <= 60 else text[:58] + "…"
            label = f"{it.get('sort_order', 0):02d}  {short}"
            qit = QListWidgetItem(label)
            qit.setData(Qt.ItemDataRole.UserRole, it)
            self._list.addItem(qit)

    def _prompt_text(self, current: str = "", current_order: int = 0) -> tuple[str, int] | None:
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QLineEdit,
            QSpinBox,
            QTextEdit,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Canned message")
        dlg.setModal(True)
        form = QFormLayout(dlg)
        text_edit = QTextEdit(current)
        text_edit.setFixedHeight(80)
        order_edit = QSpinBox()
        order_edit.setRange(0, 999)
        order_edit.setValue(current_order)
        form.addRow("Text", text_edit)
        form.addRow("Order", order_edit)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        text = text_edit.toPlainText().strip()
        if not text:
            return None
        return text, order_edit.value()

    def _on_add(self) -> None:
        result = self._prompt_text()
        if result is None:
            return
        text, order = result
        from gui import backend
        try:
            backend.add_canned_message(text, order)
        except Exception:
            log.exception("canned POST failed")
            QMessageBox.warning(self, "Canned", "Add failed.")
        self._refresh()

    def _on_edit(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        result = self._prompt_text(data.get("text") or "", int(data.get("sort_order") or 0))
        if result is None:
            return
        text, order = result
        from gui import backend
        try:
            backend.update_canned_message(int(data.get("id")), text, order)
        except Exception:
            log.exception("canned PUT failed")
            QMessageBox.warning(self, "Canned", "Edit failed.")
        self._refresh()

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        if QMessageBox.question(
            self, "Canned", f"Delete canned message {data.get('id')}?",
        ) != QMessageBox.StandardButton.Yes:
            return
        from gui import backend
        try:
            backend.delete_canned_message(int(data.get("id")))
        except Exception:
            log.exception("canned DELETE failed")
            QMessageBox.warning(self, "Canned", "Delete failed.")
        self._refresh()


class _UsbStorageSection(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("USB storage (tiles)", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._status = QLabel("…")
        self._status.setProperty("role", "muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        bar = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        self._move = QPushButton("Move tiles to USB")
        self._move.clicked.connect(self._on_move)
        self._restore = QPushButton("Restore from USB")
        self._restore.clicked.connect(self._on_restore)
        bar.addWidget(refresh)
        bar.addWidget(self._move)
        bar.addWidget(self._restore)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._refresh()

    def _refresh(self) -> None:
        from gui import backend
        try:
            d = backend.usb_status()
        except Exception:
            self._status.setText("status unavailable")
            return
        text_parts = []
        if d.get("mounted"):
            text_parts.append(f"mounted at {d.get('mountpoint', '?')}")
        else:
            text_parts.append("no USB mounted")
        if d.get("free_mb") is not None:
            text_parts.append(f"{d['free_mb']} MB free")
        if d.get("tiles_on_usb"):
            text_parts.append("tiles on USB")
        self._status.setText("  ·  ".join(text_parts))

    def _on_move(self) -> None:
        if QMessageBox.question(self, "USB", "Move map tiles to USB?") != QMessageBox.StandardButton.Yes:
            return
        self._usb_action("move-tiles")

    def _on_restore(self) -> None:
        if QMessageBox.question(self, "USB", "Restore tiles from USB to internal storage?") != QMessageBox.StandardButton.Yes:
            return
        self._usb_action("restore-tiles")

    def _usb_action(self, action: str) -> None:
        import os
        tiles_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static", "tiles",
        )
        try:
            import usb_storage
            if action == "move-tiles":
                r = usb_storage.move_tiles_to_usb(tiles_dir)
            else:
                r = usb_storage.restore_tiles_to_sd(tiles_dir)
            if not r.get("ok", True):
                QMessageBox.warning(self, "USB", f"{action} failed: {r.get('error', '')}")
                return
        except Exception as exc:
            QMessageBox.warning(self, "USB", f"{action} error: {exc}")
            return
        self._refresh()
