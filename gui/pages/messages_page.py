"""Messages page: broadcast channel chat (single tab in this first cut).

DM threads and per-channel switching come in a follow-up commit; this page
covers the most common case (the primary broadcast channel) so the user can
read incoming and send outgoing messages from the kiosk.
"""

from __future__ import annotations

import asyncio
import logging
import time

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.pages._message_format import format_message

log = logging.getLogger(__name__)


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header: channel selector
        head = QHBoxLayout()
        head.addWidget(QLabel("Channel"))
        self._channel = QSpinBox(self)
        self._channel.setRange(0, 7)
        self._channel.valueChanged.connect(lambda _v: self._reload())
        head.addWidget(self._channel)
        head.addStretch(1)
        self._info = QLabel("")
        self._info.setProperty("role", "muted")
        head.addWidget(self._info)
        layout.addLayout(head)

        # Message list
        self._list = QListWidget(self)
        self._list.setUniformItemSizes(True)
        f = self._list.font()
        f.setFamily("monospace")
        self._list.setFont(f)
        layout.addWidget(self._list, 1)

        # Composer
        comp = QHBoxLayout()
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Type a message…")
        self._input.returnPressed.connect(self._on_send)
        send = QPushButton("Send")
        send.clicked.connect(self._on_send)
        comp.addWidget(self._input, 1)
        comp.addWidget(send)
        layout.addLayout(comp)

        # Initial fill (deferred to event loop so __init__ doesn't await).
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._reload_async())

        if eventbus is not None:
            eventbus.message_received.connect(self._on_incoming)
            eventbus.ack_received.connect(self._on_ack)

    # ------------------------------------------------------------------

    def _reload(self) -> None:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._reload_async())

    async def _reload_async(self) -> None:
        try:
            import config as cfg
            import database
            msgs = await database.get_messages(cfg.DB_PATH, channel=self._channel.value(), limit=200)
        except Exception:
            log.exception("messages reload failed")
            msgs = []

        self._list.clear()
        for m in msgs:
            self._append(m)
        self._info.setText(f"{len(msgs)} messages")
        self._scroll_to_bottom()

    def _append(self, msg: dict) -> None:
        item = QListWidgetItem(format_message(msg))
        if msg.get("is_outgoing"):
            f = item.font()
            f.setItalic(True)
            item.setFont(f)
        self._list.addItem(item)

    def _scroll_to_bottom(self) -> None:
        if self._list.count() > 0:
            self._list.scrollToItem(self._list.item(self._list.count() - 1))

    # Slots --------------------------------------------------------------

    @Slot(dict)
    def _on_incoming(self, event: dict) -> None:
        if event.get("channel", 0) != self._channel.value():
            return
        msg = {
            "ts": event.get("ts") or int(time.time()),
            "node_id": event.get("from") or event.get("id"),
            "text": event.get("text") or "",
            "is_outgoing": False,
            "ack": 0,
        }
        self._append(msg)
        self._scroll_to_bottom()

    @Slot(dict)
    def _on_ack(self, event: dict) -> None:
        # Find the most recent outgoing item without ack and mark it.
        for i in range(self._list.count() - 1, -1, -1):
            item = self._list.item(i)
            if "me:" in item.text() and "✓" not in item.text():
                item.setText(item.text() + " ✓")
                break

    @Slot()
    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            loop.create_task(self._send_async(text))

    async def _send_async(self, text: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.send_text(text, "^all", channel=self._channel.value())
        except Exception:
            log.exception("send_text failed")
            return

        msg = {
            "ts": int(time.time()),
            "node_id": "me",
            "text": text,
            "is_outgoing": True,
            "ack": 0,
        }
        self._append(msg)
        self._scroll_to_bottom()
