"""Pure-Python event → signal dispatcher.

The Qt-side ``EventBus`` (see ``eventbus.py``) holds the actual ``Signal``
declarations; this module owns the **mapping** from raw event dicts (the same
shape that ``meshtasticd_client._enqueue_event`` produces and that
``mqtt_bridge`` forwards) to the right signal name. Keeping the mapping here
makes it unit-testable without importing Qt, and means the only thing a Qt
slot consumer needs to do is connect to the named signal.
"""

from __future__ import annotations

from typing import Any, Protocol


class _SignalLike(Protocol):
    def emit(self, *args: Any) -> None: ...


class _SignalSink(Protocol):
    """Anything that exposes the EventBus signals as attributes."""

    node_updated: _SignalLike
    position_updated: _SignalLike
    message_received: _SignalLike
    log_line: _SignalLike
    telemetry: _SignalLike
    traceroute_result: _SignalLike
    ack_received: _SignalLike
    waypoint: _SignalLike
    neighbor_info: _SignalLike
    sensor: _SignalLike
    paxcounter: _SignalLike
    rpi_telemetry: _SignalLike
    mqtt_event: _SignalLike


# Map raw event ``type`` field → ``EventBus`` signal attribute name.
# Keep keys in sync with meshtasticd_client._enqueue_event() and
# rpi_telemetry feed in main.py:_rpi_telemetry_task.
EVENT_TYPE_TO_SIGNAL: dict[str, str] = {
    "node":              "node_updated",
    "position":          "position_updated",
    "message":           "message_received",
    "log":               "log_line",
    "telemetry":         "telemetry",
    "traceroute_result": "traceroute_result",
    "ack":               "ack_received",
    "waypoint":          "waypoint",
    "neighbor_info":     "neighbor_info",
    "sensor":            "sensor",
    "paxcounter":        "paxcounter",
    "rpi_telemetry":     "rpi_telemetry",
}


# MQTT-forwarded events arrive with type strings like ``mqtt_position``,
# ``mqtt_message`` (whatever ``mqtt_bridge`` chooses). They all funnel into a
# single signal carrying (type, payload).
MQTT_EVENT_PREFIX = "mqtt_"


def dispatch_event(event: dict, sinks: _SignalSink) -> str | None:
    """Emit the signal on ``sinks`` matching ``event['type']``.

    Returns the name of the emitted signal, or ``None`` if no signal was
    emitted (unknown / missing type, or sink lacks the attribute).

    Never raises on unknown types: this is a pub/sub fan-out, garbage events
    must not crash the GUI.
    """
    etype = event.get("type")
    if not isinstance(etype, str):
        return None

    signal_name = EVENT_TYPE_TO_SIGNAL.get(etype)
    if signal_name is not None:
        signal = getattr(sinks, signal_name, None)
        if signal is None:
            return None
        signal.emit(event)
        return signal_name

    # MQTT bridge forwards under ``mqtt_*`` types; collapse them into one
    # signal that carries (event_type, full_payload).
    if etype.startswith(MQTT_EVENT_PREFIX):
        signal = getattr(sinks, "mqtt_event", None)
        if signal is None:
            return None
        signal.emit(etype, event)
        return "mqtt_event"

    return None


def known_event_types() -> tuple[str, ...]:
    """Useful for tests and debugging."""
    return tuple(EVENT_TYPE_TO_SIGNAL.keys())
