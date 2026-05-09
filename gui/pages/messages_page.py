"""Messages page: broadcast channel + DM threads.

Top-level QTabBar splits the two flows:
- Broadcast: channel selector (0-7) + chronological message list + composer.
- DMs: list of threads (left) + selected thread + composer (right).
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
    QSplitter,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from gui.pages._message_format import format_message

log = logging.getLogger(__name__)


def _schedule(coro) -> None:
    loop = asyncio.get_event_loop_policy().get_event_loop()
    if loop.is_running():
        loop.create_task(coro)


class _BroadcastView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        head = QHBoxLayout()
        head.addWidget(QLabel("Channel"))
        self.channel = QSpinBox(self)
        self.channel.setRange(0, 7)
        self.channel.valueChanged.connect(lambda _v: self._reload())
        head.addWidget(self.channel)
        head.addStretch(1)
        self.info = QLabel("")
        self.info.setProperty("role", "muted")
        head.addWidget(self.info)
        layout.addLayout(head)

        self.list = QListWidget(self)
        self.list.setUniformItemSizes(True)
        f = self.list.font()
        f.setFamily("monospace")
        self.list.setFont(f)
        layout.addWidget(self.list, 1)

        comp = QHBoxLayout()
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Type a message…")
        self.input.returnPressed.connect(self._on_send)
        send = QPushButton("Send")
        send.clicked.connect(self._on_send)
        comp.addWidget(self.input, 1)
        comp.addWidget(send)
        layout.addLayout(comp)

        _schedule(self._reload_async())

    # ------------------------------------------------------------------

    def _reload(self) -> None:
        _schedule(self._reload_async())

    async def _reload_async(self) -> None:
        try:
            import config as cfg
            import database
            msgs = await database.get_messages(cfg.DB_PATH, channel=self.channel.value(), limit=200)
        except Exception:
            log.exception("messages reload failed")
            msgs = []

        self.list.clear()
        for m in msgs:
            self._append(m)
        self.info.setText(f"{len(msgs)} msgs")
        self._scroll_bottom()

    def _append(self, msg: dict) -> None:
        item = QListWidgetItem(format_message(msg))
        if msg.get("is_outgoing"):
            f = item.font()
            f.setItalic(True)
            item.setFont(f)
        self.list.addItem(item)

    def _scroll_bottom(self) -> None:
        if self.list.count() > 0:
            self.list.scrollToItem(self.list.item(self.list.count() - 1))

    # Slots --------------------------------------------------------------

    @Slot(dict)
    def on_incoming(self, event: dict) -> None:
        if event.get("channel", 0) != self.channel.value():
            return
        msg = {
            "ts": event.get("ts") or int(time.time()),
            "node_id": event.get("from") or event.get("id"),
            "text": event.get("text") or "",
            "is_outgoing": False,
            "ack": 0,
        }
        self._append(msg)
        self._scroll_bottom()

    @Slot(dict)
    def on_ack(self, event: dict) -> None:
        for i in range(self.list.count() - 1, -1, -1):
            item = self.list.item(i)
            if "me:" in item.text() and "✓" not in item.text():
                item.setText(item.text() + " ✓")
                break

    @Slot()
    def _on_send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        _schedule(self._send_async(text))

    async def _send_async(self, text: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.send_text(text, "^all", channel=self.channel.value())
        except Exception:
            log.exception("send_text failed")
            return
        self._append({"ts": int(time.time()), "node_id": "me", "text": text, "is_outgoing": True})
        self._scroll_bottom()


class _DmView(QWidget):
    """Threads list + thread messages + composer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peer_id: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        split = QSplitter(Qt.Orientation.Horizontal, self)
        layout.addWidget(split, 1)

        # Left: threads list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(2)
        ll.addWidget(QLabel("Threads"))
        self.threads = QListWidget(left)
        self.threads.itemSelectionChanged.connect(self._on_thread_selected)
        ll.addWidget(self.threads, 1)
        split.addWidget(left)

        # Right: thread + composer
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)
        self.peer_lbl = QLabel("(select a thread)")
        self.peer_lbl.setProperty("role", "muted")
        rl.addWidget(self.peer_lbl)
        self.msgs = QListWidget(right)
        self.msgs.setUniformItemSizes(True)
        f = self.msgs.font()
        f.setFamily("monospace")
        self.msgs.setFont(f)
        rl.addWidget(self.msgs, 1)

        comp = QHBoxLayout()
        self.input = QLineEdit(right)
        self.input.setPlaceholderText("Type a DM…")
        self.input.returnPressed.connect(self._on_send)
        send = QPushButton("Send")
        send.clicked.connect(self._on_send)
        comp.addWidget(self.input, 1)
        comp.addWidget(send)
        rl.addLayout(comp)
        split.addWidget(right)
        # 1/3 threads, 2/3 messages on a 480 px screen.
        split.setSizes([160, 320])

        _schedule(self._reload_threads())

    # ------------------------------------------------------------------

    def reload(self) -> None:
        _schedule(self._reload_threads())

    async def _reload_threads(self) -> None:
        try:
            import config as cfg
            import database
            import meshtasticd_client
            local_id = meshtasticd_client.get_local_id()
            threads = await database.get_dm_threads(cfg.DB_PATH, local_id)
        except Exception:
            log.exception("dm threads reload failed")
            threads = []

        self.threads.clear()
        for t in threads:
            label = t.get("short_name") or t.get("peer_id") or "?"
            unread = t.get("unread") or 0
            text = f"{label}  ({unread} new)" if unread else label
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t.get("peer_id"))
            if unread:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.threads.addItem(item)

    @Slot()
    def _on_thread_selected(self) -> None:
        items = self.threads.selectedItems()
        if not items:
            return
        peer = items[0].data(Qt.ItemDataRole.UserRole)
        self._peer_id = peer
        self.peer_lbl.setText(peer or "")
        _schedule(self._load_messages(peer))

    async def _load_messages(self, peer: str) -> None:
        try:
            import config as cfg
            import database
            import meshtasticd_client
            local_id = meshtasticd_client.get_local_id()
            msgs = await database.get_dm_messages(cfg.DB_PATH, peer, local_id, limit=100)
            await database.mark_dm_read(cfg.DB_PATH, peer)
        except Exception:
            log.exception("dm load failed")
            msgs = []
        self.msgs.clear()
        for m in msgs:
            item = QListWidgetItem(format_message(m))
            if m.get("is_outgoing"):
                f = item.font()
                f.setItalic(True)
                item.setFont(f)
            self.msgs.addItem(item)
        if self.msgs.count() > 0:
            self.msgs.scrollToItem(self.msgs.item(self.msgs.count() - 1))

    @Slot()
    def _on_send(self) -> None:
        if not self._peer_id:
            return
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        _schedule(self._send_async(self._peer_id, text))

    async def _send_async(self, peer: str, text: str) -> None:
        try:
            import meshtasticd_client
            await meshtasticd_client.send_text(text, peer, channel=0)
        except Exception:
            log.exception("send DM failed")
            return
        msg = {"ts": int(time.time()), "node_id": "me", "text": text, "is_outgoing": True}
        item = QListWidgetItem(format_message(msg))
        f = item.font()
        f.setItalic(True)
        item.setFont(f)
        self.msgs.addItem(item)
        self.msgs.scrollToItem(self.msgs.item(self.msgs.count() - 1))


class Page(QWidget):
    def __init__(self, eventbus, settings):
        super().__init__()
        self._eventbus = eventbus
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Mode tabs at the top: Broadcast / DMs.
        self._tabs = QTabBar(self)
        self._tabs.addTab("Broadcast")
        self._tabs.addTab("DMs")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

        self._stack = QStackedWidget(self)
        self._broadcast = _BroadcastView(self._stack)
        self._dm = _DmView(self._stack)
        self._stack.addWidget(self._broadcast)
        self._stack.addWidget(self._dm)
        layout.addWidget(self._stack, 1)

        if eventbus is not None:
            eventbus.message_received.connect(self._on_incoming)
            eventbus.ack_received.connect(self._broadcast.on_ack)

    @Slot(int)
    def _on_tab_changed(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        if idx == 1:
            self._dm.reload()  # refresh threads each time DM tab is opened

    @Slot(dict)
    def _on_incoming(self, event: dict) -> None:
        # Broadcast vs DM dispatch.
        dest = event.get("destination") or "^all"
        if dest == "^all":
            self._broadcast.on_incoming(event)
        else:
            # Refresh thread list (unread count changes); the user may also
            # be viewing the DM tab for this peer.
            self._dm.reload()
