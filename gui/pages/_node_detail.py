"""Node detail dialog opened by tapping a row in the Nodes list."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.pages._node_format import fmt_age, fmt_node

log = logging.getLogger(__name__)


def _format_field(node: dict, key: str) -> str:
    """Render a single detail field as a string."""
    if key == "id":
        return node.get("id") or "—"
    if key == "hw_model":
        return node.get("hw_model") or "—"
    if key == "role":
        return node.get("role") or "—"
    if key == "firmware":
        return node.get("firmware_version") or "—"
    if key == "public_key":
        pk = node.get("public_key") or ""
        return (pk[:24] + "…") if len(pk) > 26 else (pk or "—")
    if key == "lat_lon":
        lat = node.get("latitude")
        lon = node.get("longitude")
        if lat is None or lon is None:
            return "—"
        return f"{lat:.5f}, {lon:.5f}"
    if key == "altitude":
        v = node.get("altitude")
        return f"{v} m" if v is not None else "—"
    if key == "last_seen":
        return fmt_age(node.get("last_heard"))
    return fmt_node(node, key)


class NodeDetailDialog(QDialog):
    """Modal dialog showing node info + action buttons.

    Buttons (require radio connected):
        - Request position
        - Request telemetry (admin)
        - Traceroute
        - Send DM (opens prompt → meshtasticd_client.send_text(text, node_id))
        - Remote reboot (admin) [confirm]
        - Remote factory reset (admin) [type RESET to confirm]
        - Forget node (DELETE /api/nodes/{id}; optional purge of messages)
    """

    forget_requested = Signal(str)  # emitted with node_id when the user forgets

    def __init__(self, node: dict, *, parent=None):
        super().__init__(parent)
        self._node = node
        self.setWindowTitle(node.get("short_name") or node.get("id") or "Node")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title row
        title = QLabel(node.get("long_name") or node.get("short_name") or "Node")
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        title.setWordWrap(True)
        layout.addWidget(title)

        # Form rows
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(2)
        for label, key in (
            ("ID",        "id"),
            ("HW",        "hw_model"),
            ("Role",      "role"),
            ("Firmware",  "firmware"),
            ("Pubkey",    "public_key"),
            ("Position",  "lat_lon"),
            ("Altitude",  "altitude"),
            ("SNR",       "snr"),
            ("Battery",   "batt"),
            ("Hops",      "hops"),
            ("Distance",  "dist"),
            ("Last seen", "last_seen"),
        ):
            value_lbl = QLabel(_format_field(node, key))
            value_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_lbl.setWordWrap(True)
            form.addRow(label, value_lbl)
        layout.addLayout(form)

        # Action buttons — local
        actions = QHBoxLayout()
        pos_btn = QPushButton("Position")
        tr_btn = QPushButton("Traceroute")
        dm_btn = QPushButton("Send DM")
        for b in (pos_btn, tr_btn, dm_btn):
            b.setMinimumHeight(28)
            actions.addWidget(b)
        layout.addLayout(actions)

        pos_btn.clicked.connect(self._request_position)
        tr_btn.clicked.connect(self._traceroute)
        dm_btn.clicked.connect(self._send_dm)

        # Admin actions — POST /api/admin/{node_id}/{op}
        admin = QHBoxLayout()
        tel_btn = QPushButton("Telemetry")
        reboot_btn = QPushButton("Reboot")
        reset_btn = QPushButton("Factory reset")
        forget_btn = QPushButton("Forget")
        for b in (tel_btn, reboot_btn, reset_btn, forget_btn):
            b.setMinimumHeight(26)
            admin.addWidget(b)
        layout.addLayout(admin)

        tel_btn.clicked.connect(self._request_telemetry)
        reboot_btn.clicked.connect(self._remote_reboot)
        reset_btn.clicked.connect(self._remote_factory_reset)
        forget_btn.clicked.connect(self._forget_node)

        # Status banner for action feedback
        self._action_status = QLabel("")
        self._action_status.setProperty("role", "muted")
        self._action_status.setWordWrap(True)
        layout.addWidget(self._action_status)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------

    def _node_id(self) -> str | None:
        return self._node.get("id")

    def _request_position(self) -> None:
        nid = self._node_id()
        if not nid:
            return
        self._schedule(self._do_request_position(nid))

    async def _do_request_position(self, nid: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.request_position(nid)
        except Exception:
            log.exception("request_position failed")
            QMessageBox.warning(self, "Node", "Failed to queue position request.")

    def _traceroute(self) -> None:
        nid = self._node_id()
        if not nid:
            return
        self._schedule(self._do_traceroute(nid))

    async def _do_traceroute(self, nid: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.request_traceroute(nid)
        except Exception:
            log.exception("request_traceroute failed")
            QMessageBox.warning(self, "Node", "Failed to queue traceroute.")

    def _send_dm(self) -> None:
        nid = self._node_id()
        if not nid:
            return
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(self, "Send DM", "Message")
        if not ok or not text.strip():
            return
        self._schedule(self._do_send_dm(nid, text.strip()))

    async def _do_send_dm(self, nid: str, text: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.send_text(text, nid, channel=0)
        except Exception:
            log.exception("send_text DM failed")
            QMessageBox.warning(self, "Node", "Failed to send DM.")

    # -- Admin actions -----------------------------------------------

    def _set_status(self, text: str, *, role: str = "muted") -> None:
        self._action_status.setText(text)
        self._action_status.setProperty("role", role)
        self._action_status.style().unpolish(self._action_status)
        self._action_status.style().polish(self._action_status)

    def _request_telemetry(self) -> None:
        nid = self._node_id()
        if not nid:
            return
        self._schedule(self._post_admin(nid, "request-telemetry", "telemetry requested"))

    def _remote_reboot(self) -> None:
        nid = self._node_id()
        if not nid:
            return
        if QMessageBox.question(
            self, "Remote reboot",
            f"Reboot node {nid}? It will be unreachable for ~30 s.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._schedule(self._post_admin(nid, "reboot", "reboot sent"))

    def _remote_factory_reset(self) -> None:
        nid = self._node_id()
        if not nid:
            return
        # Type 'RESET' to confirm — matches the web UI flow.
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "Factory reset", f"Type RESET to factory-reset {nid}:"
        )
        if not ok or text.strip() != "RESET":
            self._set_status("factory reset cancelled")
            return
        self._schedule(self._post_admin(nid, "factory-reset", "factory reset sent", warn=True))

    async def _post_admin(self, nid: str, operation: str, ok_msg: str, *, warn: bool = False) -> None:
        self._set_status(f"sending {operation}…")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(
                    f"http://127.0.0.1:8080/api/admin/{nid}/{operation}",
                )
            if r.status_code == 200:
                self._set_status(f"✓ {ok_msg}", role="warn" if warn else "ok")
                return
            err = ""
            try:
                err = r.json().get("error") or r.json().get("detail") or ""
            except Exception:
                err = r.text[:160]
            self._set_status(f"✗ {operation} failed: {err}", role="danger")
        except Exception as exc:
            self._set_status(f"✗ {operation} error: {exc}", role="danger")

    # -- Forget ------------------------------------------------------

    def _forget_node(self) -> None:
        nid = self._node_id()
        if not nid:
            return
        # Single dialog with optional purge checkbox.
        dlg = QDialog(self)
        dlg.setWindowTitle("Forget node")
        dlg.setModal(True)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(f"Remove {nid} from the local cache."))
        purge = QCheckBox("Also delete messages and telemetry (purge)")
        v.addWidget(purge)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._schedule(self._do_forget(nid, purge.isChecked()))

    async def _do_forget(self, nid: str, purge: bool) -> None:
        url = f"http://127.0.0.1:8080/api/nodes/{nid}"
        if purge:
            url += "?purge=true"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.delete(url)
            if r.status_code != 200:
                self._set_status(f"✗ forget failed: {r.text[:120]}", role="danger")
                return
        except Exception as exc:
            self._set_status(f"✗ forget error: {exc}", role="danger")
            return
        self._set_status("✓ node removed", role="ok")
        self.forget_requested.emit(nid)
        self.accept()

    # -- helpers -----------------------------------------------------

    @staticmethod
    def _schedule(coro) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(coro)


# Convert internal `self._schedule` references back to the staticmethod call.
# (No-op marker — keeps the surrounding diff minimal.)
