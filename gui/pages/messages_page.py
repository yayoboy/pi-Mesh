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
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QToolButton,
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
        self._oldest_id: int | None = None  # for "load more" pagination

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

        # Clear-history trash button
        clear = QToolButton(self)
        clear.setText("Del")
        clear.setToolTip("Clear history")
        clear.clicked.connect(self._on_clear)
        head.addWidget(clear)
        layout.addLayout(head)

        self.list = QListWidget(self)
        self.list.setUniformItemSizes(False)
        self.list.setWordWrap(True)
        f = self.list.font()
        f.setFamily("monospace")
        self.list.setFont(f)
        # Top "Load more" item is inserted on demand and removed once consumed.
        self.list.itemActivated.connect(self._maybe_load_more)
        layout.addWidget(self.list, 1)

        comp = QHBoxLayout()
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Type a message…")
        self.input.returnPressed.connect(self._on_send)
        canned = QToolButton(self)
        canned.setText("...")
        canned.setToolTip("Canned messages")
        canned.clicked.connect(self._show_canned_menu)
        send = QPushButton("Send")
        send.clicked.connect(self._on_send)
        comp.addWidget(self.input, 1)
        comp.addWidget(canned)
        comp.addWidget(send)
        layout.addLayout(comp)

        _schedule(self._reload_async())

    def set_initial_focus(self) -> None:
        """Focus the compose input so the QMK keyboard can type immediately.
        Enter sends (already wired via returnPressed)."""
        self.input.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------

    def _reload(self) -> None:
        _schedule(self._reload_async())

    async def _reload_async(self) -> None:
        try:
            import config as cfg
            import database
            msgs = await database.get_messages(cfg.DB_PATH, channel=self.channel.value(), limit=50)
        except Exception:
            log.exception("messages reload failed")
            msgs = []

        self.list.clear()
        self._oldest_id = msgs[0]["id"] if msgs and "id" in msgs[0] else None
        if self._oldest_id:
            self._add_load_more_item()
        for m in msgs:
            self._append(m)
        self.info.setText(f"{len(msgs)} msgs")
        self._scroll_bottom()

    def _add_load_more_item(self) -> None:
        item = QListWidgetItem("↑ Load older messages")
        item.setData(Qt.ItemDataRole.UserRole, "load_more")
        item.setForeground(Qt.GlobalColor.gray)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list.insertItem(0, item)

    def _append(self, msg: dict) -> None:
        item = QListWidgetItem(format_message(msg))
        if msg.get("is_outgoing"):
            f = item.font()
            f.setItalic(True)
            item.setFont(f)
        self.list.addItem(item)

    def _prepend_below_loader(self, msg: dict) -> None:
        item = QListWidgetItem(format_message(msg))
        if msg.get("is_outgoing"):
            f = item.font()
            f.setItalic(True)
            item.setFont(f)
        # Insert just after the loader (index 1) so loader stays at top.
        idx = 1 if self.list.count() and self.list.item(0).data(Qt.ItemDataRole.UserRole) == "load_more" else 0
        self.list.insertItem(idx, item)

    def _scroll_bottom(self) -> None:
        if self.list.count() > 0:
            self.list.scrollToItem(self.list.item(self.list.count() - 1))

    def _maybe_load_more(self, item: QListWidgetItem) -> None:
        if item is None or item.data(Qt.ItemDataRole.UserRole) != "load_more":
            return
        if not self._oldest_id:
            return
        _schedule(self._load_older(self._oldest_id))

    async def _load_older(self, before_id: int) -> None:
        try:
            import config as cfg
            import database
            older = await database.get_messages(
                cfg.DB_PATH, channel=self.channel.value(), limit=50, before_id=before_id,
            )
        except Exception:
            log.exception("load older failed")
            return
        if not older:
            # Nothing more — drop the loader.
            top = self.list.item(0)
            if top and top.data(Qt.ItemDataRole.UserRole) == "load_more":
                self.list.takeItem(0)
            self._oldest_id = None
            return
        # Replace loader with new oldest_id, then prepend in chronological
        # order so the visible row order stays correct.
        top = self.list.item(0)
        if top and top.data(Qt.ItemDataRole.UserRole) == "load_more":
            self.list.takeItem(0)
        for m in reversed(older):
            self._prepend_below_loader(m)
        self._oldest_id = older[0].get("id")
        if self._oldest_id:
            self._add_load_more_item()

    def _on_clear(self) -> None:
        if QMessageBox.question(
            self, "Messages", "Clear all message history (broadcast + DM)?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._clear()

    def _clear(self) -> None:
        try:
            from gui import backend
            backend.clear_messages()
        except Exception:
            log.exception("clear messages failed")
            return
        self.list.clear()
        self.info.setText("cleared")

    def _show_canned_menu(self) -> None:
        self._populate_and_show_canned()

    def _populate_and_show_canned(self) -> None:
        try:
            from gui import backend
            items = backend.get_canned_messages()
        except Exception:
            items = []
        if not items:
            from gui.widgets.toast import show_toast
            show_toast(self, "No canned messages — add some in Config", role="warn")
            return
        menu = QMenu(self)
        for it in items:
            text = it.get("text") or ""
            if not text:
                continue
            short = text if len(text) <= 32 else text[:30] + "…"
            menu.addAction(short, lambda t=text: self._insert_canned(t))
        menu.exec(self.mapToGlobal(self.input.geometry().bottomLeft()))

    def _insert_canned(self, text: str) -> None:
        self.input.setText(text)
        self.input.setFocus()

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
    """Threads list → thread detail as a stacked navigation (no splitter).

    On a 320px screen a horizontal splitter makes both panes too narrow.
    Instead we use a QStackedWidget: page 0 = thread list, page 1 = conversation.
    A "Back" button returns to the thread list.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peer_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        # Page 0: threads list
        threads_page = QWidget()
        tl = QVBoxLayout(threads_page)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)
        tl.addWidget(QLabel("Threads"))
        self.threads = QListWidget(threads_page)
        self.threads.itemClicked.connect(self._on_thread_selected_item)
        tl.addWidget(self.threads, 1)
        self._stack.addWidget(threads_page)

        # Page 1: conversation + composer
        conv_page = QWidget()
        rl = QVBoxLayout(conv_page)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)

        head = QHBoxLayout()
        back_btn = QPushButton("<")
        back_btn.setFixedSize(36, 36)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        head.addWidget(back_btn)
        self.peer_lbl = QLabel("(select a thread)")
        self.peer_lbl.setProperty("role", "muted")
        head.addWidget(self.peer_lbl, 1)
        rl.addLayout(head)

        self.msgs = QListWidget(conv_page)
        self.msgs.setUniformItemSizes(True)
        f = self.msgs.font()
        f.setFamily("monospace")
        self.msgs.setFont(f)
        rl.addWidget(self.msgs, 1)

        comp = QHBoxLayout()
        self.input = QLineEdit(conv_page)
        self.input.setPlaceholderText("Type a DM...")
        self.input.returnPressed.connect(self._on_send)
        send = QPushButton("Send")
        send.clicked.connect(self._on_send)
        comp.addWidget(self.input, 1)
        comp.addWidget(send)
        rl.addLayout(comp)
        self._stack.addWidget(conv_page)

        _schedule(self._reload_threads())

    def set_initial_focus(self) -> None:
        """If we're on the threads list, focus that (so Up/Down/Enter can
        pick a thread without auto-opening the VKB). If a conversation is
        already open, focus the compose input."""
        if self._stack.currentIndex() == 0:
            self.threads.setFocus(Qt.FocusReason.OtherFocusReason)
            if self.threads.count() > 0 and self.threads.currentRow() < 0:
                self.threads.setCurrentRow(0)
        else:
            self.input.setFocus(Qt.FocusReason.OtherFocusReason)

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

    def _on_thread_selected_item(self, item: QListWidgetItem) -> None:
        peer = item.data(Qt.ItemDataRole.UserRole)
        if not peer:
            return
        self._peer_id = peer
        self.peer_lbl.setText(peer or "")
        self._stack.setCurrentIndex(1)
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

        # Mode toggle at the top: Broadcast / DMs — QPushButtons for
        # visual consistency with the rest of the app (QTabBar has its own
        # styling that doesn't match the dark theme).
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.setContentsMargins(4, 2, 4, 2)
        self._btn_broadcast = QPushButton("Broadcast")
        self._btn_dm = QPushButton("DMs")
        for btn in (self._btn_broadcast, self._btn_dm):
            btn.setCheckable(True)
            btn.setMinimumHeight(36)
        self._btn_broadcast.setChecked(True)
        self._btn_broadcast.clicked.connect(lambda: self._on_tab_changed(0))
        self._btn_dm.clicked.connect(lambda: self._on_tab_changed(1))
        tab_row.addWidget(self._btn_broadcast, 1)
        tab_row.addWidget(self._btn_dm, 1)
        layout.addLayout(tab_row)

        self._stack = QStackedWidget(self)
        self._broadcast = _BroadcastView(self._stack)
        self._dm = _DmView(self._stack)
        self._stack.addWidget(self._broadcast)
        self._stack.addWidget(self._dm)
        layout.addWidget(self._stack, 1)

        if eventbus is not None:
            eventbus.message_received.connect(self._on_incoming)
            eventbus.ack_received.connect(self._broadcast.on_ack)

    def set_initial_focus(self) -> None:
        """Delegate to the active sub-view's set_initial_focus()."""
        current = self._stack.currentWidget()
        fn = getattr(current, "set_initial_focus", None)
        if callable(fn):
            fn()

    @Slot(int)
    def _on_tab_changed(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        self._btn_broadcast.setChecked(idx == 0)
        self._btn_dm.setChecked(idx == 1)
        if idx == 1:
            self._dm.reload()

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
