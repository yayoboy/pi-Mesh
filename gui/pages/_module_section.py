"""Generic ``QGroupBox`` that renders + saves a Meshtastic module config.

Driven by a :class:`ModuleSpec` (see :mod:`gui.pages._module_specs`). Reads
the current values from ``meshtasticd_client.<getter>(db_path)`` and writes
back via ``meshtasticd_client.<setter>(params)``.
"""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

from gui.pages._module_specs import Field, ModuleSpec

log = logging.getLogger(__name__)


def _schedule(coro) -> None:
    loop = asyncio.get_event_loop_policy().get_event_loop()
    if loop.is_running():
        loop.create_task(coro)


class ModuleSection(QGroupBox):
    """Renders a form for one module config + Save button."""

    def __init__(self, spec: ModuleSpec, parent=None):
        super().__init__(spec.title, parent)
        self._spec = spec
        self._editors: dict[str, QWidget] = {}

        form = QFormLayout(self)
        for field in spec.fields:
            editor = self._make_editor(field)
            self._editors[field.key] = editor
            form.addRow(field.label, editor)

        save_row = QHBoxLayout()
        save = QPushButton("Save")
        save.clicked.connect(self._on_save)
        save_row.addStretch(1)
        save_row.addWidget(save)
        form.addRow(save_row)

    # ------------------------------------------------------------------

    def _make_editor(self, field: Field) -> QWidget:
        if field.kind == "bool":
            btn = QPushButton("off")
            btn.setCheckable(True)
            btn.toggled.connect(lambda checked, b=btn: b.setText("on" if checked else "off"))
            return btn
        if field.kind == "int":
            sp = QSpinBox()
            lo, hi = (field.extra or (0, 999_999))
            sp.setRange(int(lo), int(hi))
            return sp
        if field.kind == "str":
            return QLineEdit()
        if field.kind == "enum":
            combo = QComboBox()
            for v in (field.extra or []):
                combo.addItem(v)
            return combo
        raise ValueError(f"unknown field kind: {field.kind!r}")

    def _read_editor(self, field: Field):
        editor = self._editors[field.key]
        if field.kind == "bool":
            return editor.isChecked()
        if field.kind == "int":
            return editor.value()
        if field.kind == "str":
            return editor.text().strip()
        if field.kind == "enum":
            return editor.currentText()
        return None

    def _write_editor(self, field: Field, value) -> None:
        editor = self._editors[field.key]
        if field.kind == "bool":
            editor.setChecked(bool(value))
            editor.setText("on" if editor.isChecked() else "off")
        elif field.kind == "int":
            try:
                editor.setValue(int(value or 0))
            except (TypeError, ValueError):
                editor.setValue(0)
        elif field.kind == "str":
            editor.setText(str(value or ""))
        elif field.kind == "enum":
            idx = editor.findText(str(value) if value is not None else "")
            if idx >= 0:
                editor.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Public API used by the Config page

    def reload(self) -> None:
        _schedule(self._reload_async())

    async def _reload_async(self) -> None:
        try:
            import config as cfg
            import meshtasticd_client
            getter = getattr(meshtasticd_client, self._spec.getter)
            data = await getter(cfg.DB_PATH)
        except Exception:
            log.exception("module reload (%s) failed", self._spec.title)
            return
        for field in self._spec.fields:
            value = data.get(field.key, field.default)
            self._write_editor(field, value)

    # ------------------------------------------------------------------
    # Save

    def _on_save(self) -> None:
        params = {f.key: self._read_editor(f) for f in self._spec.fields}
        _schedule(self._save_async(params))

    async def _save_async(self, params: dict) -> None:
        try:
            import meshtasticd_client
            setter = getattr(meshtasticd_client, self._spec.setter)
            await setter(params)
        except Exception:
            log.exception("module save (%s) failed", self._spec.title)
            QMessageBox.warning(self, self._spec.title, "Save failed.")
            return
        # Briefly indicate success on the button label.
        # (Caller can listen on signals if it needs richer feedback.)
        self.setTitle(f"{self._spec.title}  ✓")
        QTimer = _import_qtimer()
        QTimer.singleShot(2000, lambda: self.setTitle(self._spec.title))


def _import_qtimer():
    from PySide6.QtCore import QTimer
    return QTimer
