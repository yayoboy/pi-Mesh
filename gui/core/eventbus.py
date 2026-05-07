"""Qt-side ``EventBus``: ``QObject`` with a ``Signal`` per event type.

Imports ``PySide6`` lazily so the rest of ``gui.core`` (in particular
``settings`` and ``event_dispatcher``) can be unit-tested without Qt.

The ``run`` coroutine is the long-lived consumer: it subscribes to
``meshtasticd_client``'s fan-out queue and re-emits every event as a Qt
signal. Started by ``MainWindow.__init__`` (Task 1.5).
"""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QObject, Signal

from gui.core.event_dispatcher import dispatch_event

log = logging.getLogger(__name__)


class EventBus(QObject):
    # All signals carry the raw event dict; consumers know how to read it.
    node_updated      = Signal(dict)
    position_updated  = Signal(dict)
    message_received  = Signal(dict)
    log_line          = Signal(dict)
    telemetry         = Signal(dict)
    traceroute_result = Signal(dict)
    ack_received      = Signal(dict)
    waypoint          = Signal(dict)
    neighbor_info     = Signal(dict)
    sensor            = Signal(dict)
    paxcounter        = Signal(dict)
    rpi_telemetry     = Signal(dict)
    # MQTT bridge forwarded events: (event_type, payload).
    mqtt_event        = Signal(str, dict)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None

    async def run(self) -> None:
        """Consume the meshtasticd_client fan-out queue forever.

        Cancellation-safe: unsubscribes on shutdown.
        """
        import meshtasticd_client

        self._queue = meshtasticd_client.subscribe_events()
        try:
            while True:
                event = await self._queue.get()
                try:
                    dispatch_event(event, self)
                except Exception:
                    log.exception("EventBus dispatch error for event=%r", event)
        finally:
            meshtasticd_client.unsubscribe_events(self._queue)
            self._queue = None

    def start(self) -> asyncio.Task:
        """Schedule ``run`` on the current loop and remember the task."""
        if self._task is not None and not self._task.done():
            return self._task
        self._task = asyncio.get_running_loop().create_task(self.run())
        return self._task

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
