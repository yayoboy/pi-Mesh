import pytest

from gui.core.event_dispatcher import (
    EVENT_TYPE_TO_SIGNAL,
    dispatch_event,
    known_event_types,
)


class FakeSignal:
    def __init__(self):
        self.emissions: list[tuple] = []

    def emit(self, *args):
        self.emissions.append(args)


class FakeSinks:
    """Lightweight stand-in for the Qt EventBus, exposing the same attributes."""

    def __init__(self):
        for name in EVENT_TYPE_TO_SIGNAL.values():
            setattr(self, name, FakeSignal())
        self.mqtt_event = FakeSignal()


# --- happy paths ------------------------------------------------------------

@pytest.mark.parametrize("etype,signal_name", list(EVENT_TYPE_TO_SIGNAL.items()))
def test_known_event_emits_corresponding_signal(etype, signal_name):
    sinks = FakeSinks()
    event = {"type": etype, "payload": "x"}

    emitted = dispatch_event(event, sinks)

    assert emitted == signal_name
    sig: FakeSignal = getattr(sinks, signal_name)
    assert sig.emissions == [(event,)]


def test_position_event_carries_full_dict():
    sinks = FakeSinks()
    event = {"type": "position", "id": "!aabb", "latitude": 41.9, "longitude": 12.5}

    name = dispatch_event(event, sinks)

    assert name == "position_updated"
    assert sinks.position_updated.emissions == [(event,)]


def test_known_event_types_matches_mapping():
    assert set(known_event_types()) == set(EVENT_TYPE_TO_SIGNAL.keys())


# --- MQTT forwarded events --------------------------------------------------

def test_mqtt_event_routes_to_mqtt_signal_with_type_and_payload():
    sinks = FakeSinks()
    event = {"type": "mqtt_message", "from": "!a", "payload": "hi"}

    name = dispatch_event(event, sinks)

    assert name == "mqtt_event"
    assert sinks.mqtt_event.emissions == [("mqtt_message", event)]


def test_mqtt_position_event_also_routes_to_mqtt():
    sinks = FakeSinks()
    event = {"type": "mqtt_position", "id": "!b", "latitude": 0.0, "longitude": 0.0}

    name = dispatch_event(event, sinks)

    assert name == "mqtt_event"
    assert sinks.mqtt_event.emissions[0] == ("mqtt_position", event)


# --- robustness -------------------------------------------------------------

def test_unknown_event_type_returns_none_and_emits_nothing():
    sinks = FakeSinks()

    name = dispatch_event({"type": "totally_unknown"}, sinks)

    assert name is None
    for signal_name in EVENT_TYPE_TO_SIGNAL.values():
        assert getattr(sinks, signal_name).emissions == []
    assert sinks.mqtt_event.emissions == []


def test_missing_type_returns_none():
    sinks = FakeSinks()
    name = dispatch_event({"no_type": "here"}, sinks)
    assert name is None


def test_non_string_type_returns_none():
    sinks = FakeSinks()
    name = dispatch_event({"type": 42}, sinks)
    assert name is None


def test_sink_missing_signal_returns_none_no_raise():
    """If the sinks object is incomplete, dispatch shouldn't crash."""

    class HalfSinks:
        # Intentionally missing every signal.
        pass

    sinks = HalfSinks()
    # Known type, but the corresponding attribute does not exist.
    name = dispatch_event({"type": "node"}, sinks)
    assert name is None


def test_mqtt_with_no_mqtt_signal_returns_none():
    class NoMqtt:
        pass

    sinks = NoMqtt()
    name = dispatch_event({"type": "mqtt_message"}, sinks)
    assert name is None


def test_dispatch_does_not_mutate_event():
    sinks = FakeSinks()
    event = {"type": "node", "id": "!a"}
    snapshot = dict(event)

    dispatch_event(event, sinks)

    assert event == snapshot
