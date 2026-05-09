"""Node detail dialog opened by tapping a row in the Nodes list."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
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
        - Traceroute
        - Send DM (opens prompt → meshtasticd_client.send_text(text, node_id))
    """

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

        # Action buttons
        actions = QHBoxLayout()
        pos_btn = QPushButton("Request position")
        tr_btn = QPushButton("Traceroute")
        dm_btn = QPushButton("Send DM")
        for b in (pos_btn, tr_btn, dm_btn):
            b.setMinimumHeight(28)
            actions.addWidget(b)
        layout.addLayout(actions)

        pos_btn.clicked.connect(self._request_position)
        tr_btn.clicked.connect(self._traceroute)
        dm_btn.clicked.connect(self._send_dm)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------

    def _node_id(self) -> str | None:
        return self._node.get("id")

    def _schedule(self, coro) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(coro)

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
