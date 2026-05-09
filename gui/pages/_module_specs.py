"""Specs for the Meshtastic module configs that follow a uniform shape.

Each spec is a tuple ``(title, getter, setter, fields)`` where ``fields`` is
a list of ``(key, kind, label, default[, extra])``:

- kind ``'bool'``: rendered as a checkable QPushButton.
- kind ``'int'``:  QSpinBox; extra is an optional (min, max) tuple.
- kind ``'str'``:  QLineEdit.
- kind ``'enum'``: QComboBox; extra is the list of enum string values.

The :class:`gui.pages._module_section.ModuleSection` widget reads this and
renders the form, so adding a new module is a one-line spec change.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class Field(NamedTuple):
    key: str
    kind: str  # 'bool' | 'int' | 'str' | 'enum'
    label: str
    default: Any = None
    extra: Any = None


class ModuleSpec(NamedTuple):
    title: str
    getter: str
    setter: str
    fields: list[Field]


SPEC_TELEMETRY = ModuleSpec(
    title="Telemetry module",
    getter="get_telemetry_module_config",
    setter="set_telemetry_module_config",
    fields=[
        Field("device_update_interval",          "int",  "Device update (s)",      0,    (0, 86400)),
        Field("environment_update_interval",     "int",  "Env update (s)",         0,    (0, 86400)),
        Field("environment_measurement_enabled", "bool", "Env enabled",            False),
        Field("air_quality_enabled",             "bool", "Air quality",            False),
        Field("power_measurement_enabled",       "bool", "Power",                  False),
    ],
)

SPEC_CANNED = ModuleSpec(
    title="Canned messages",
    getter="get_canned_message_module_config",
    setter="set_canned_message_module_config",
    fields=[
        Field("send_bell",            "bool", "Send bell",     False),
        Field("free_text_sms_enabled","bool", "Free text SMS", False),
    ],
)

SPEC_RANGE_TEST = ModuleSpec(
    title="Range test",
    getter="get_range_test_config",
    setter="set_range_test_config",
    fields=[
        Field("enabled", "bool", "Enabled", False),
        Field("sender",  "int",  "Sender period (s)", 0, (0, 86400)),
        Field("save",    "bool", "Save samples", False),
    ],
)

SPEC_NEIGHBOR_INFO = ModuleSpec(
    title="Neighbor info",
    getter="get_neighbor_info_module_config",
    setter="set_neighbor_info_module_config",
    fields=[
        Field("enabled",            "bool", "Enabled", False),
        Field("update_interval",    "int",  "Update (s)", 0, (0, 86400)),
        Field("transmit_over_lora", "bool", "Transmit over LoRa", False),
    ],
)

SPEC_STORE_FORWARD = ModuleSpec(
    title="Store and forward",
    getter="get_store_forward_config",
    setter="set_store_forward_config",
    fields=[
        Field("enabled",   "bool", "Enabled",  False),
        Field("heartbeat", "bool", "Heartbeat", False),
    ],
)

SPEC_EXTERNAL_NOTIFICATION = ModuleSpec(
    title="External notification",
    getter="get_external_notification_config",
    setter="set_external_notification_config",
    fields=[
        Field("enabled",      "bool", "Enabled",       False),
        Field("output_pin",   "int",  "Output pin",    0, (0, 64)),
        Field("active_high",  "bool", "Active high",   False),
        Field("alert_message","bool", "Alert on msg",  False),
        Field("alert_bell",   "bool", "Alert on bell", False),
        Field("use_pwm",      "bool", "Use PWM",       False),
        Field("nag_timeout",  "int",  "Nag timeout (s)", 0, (0, 600)),
    ],
)

SPEC_AMBIENT_LIGHTING = ModuleSpec(
    title="Ambient lighting",
    getter="get_ambient_lighting_config",
    setter="set_ambient_lighting_config",
    fields=[
        Field("led_state", "bool", "LED on",  False),
        Field("current",   "int",  "Current", 0, (0, 255)),
        Field("red",       "int",  "Red",     0, (0, 255)),
        Field("green",     "int",  "Green",   0, (0, 255)),
        Field("blue",      "int",  "Blue",    0, (0, 255)),
    ],
)

SPEC_DETECTION_SENSOR = ModuleSpec(
    title="Detection sensor",
    getter="get_detection_sensor_config",
    setter="set_detection_sensor_config",
    fields=[
        Field("enabled",                  "bool", "Enabled", False),
        Field("name",                     "str",  "Name", ""),
        Field("monitor_pin",              "int",  "Pin",  0, (0, 64)),
        Field("minimum_broadcast_secs",   "int",  "Min broadcast (s)", 0, (0, 86400)),
        Field("state_broadcast_secs",     "int",  "State broadcast (s)", 0, (0, 86400)),
        Field("use_pullup",               "bool", "Pull-up", False),
        Field("detection_triggered_high", "bool", "Trigger high", False),
    ],
)

SPEC_SERIAL = ModuleSpec(
    title="Serial module",
    getter="get_serial_module_config",
    setter="set_serial_module_config",
    fields=[
        Field("enabled", "bool", "Enabled", False),
        Field("echo",    "bool", "Echo",    False),
        Field("rxd",     "int",  "RXD pin", 0, (0, 64)),
        Field("txd",     "int",  "TXD pin", 0, (0, 64)),
        Field("timeout", "int",  "Timeout (s)", 0, (0, 86400)),
        Field("mode",    "enum", "Mode", "DEFAULT",
              ["DEFAULT", "SIMPLE", "PROTO", "TEXTMSG", "NMEA", "CALTOPO", "WS85"]),
        Field("override_console_serial_port", "bool", "Override console port", False),
    ],
)


ALL_MODULE_SPECS: list[ModuleSpec] = [
    SPEC_TELEMETRY,
    SPEC_CANNED,
    SPEC_RANGE_TEST,
    SPEC_NEIGHBOR_INFO,
    SPEC_STORE_FORWARD,
    SPEC_EXTERNAL_NOTIFICATION,
    SPEC_AMBIENT_LIGHTING,
    SPEC_DETECTION_SENSOR,
    SPEC_SERIAL,
]
