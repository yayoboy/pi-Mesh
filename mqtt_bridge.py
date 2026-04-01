"""MQTT Bridge — connects to MQTT broker and bridges messages to/from WebSocket."""
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# paho-mqtt is optional — bridge is disabled if not installed
try:
    import paho.mqtt.client as paho_mqtt
    HAS_PAHO = True
except ImportError:
    HAS_PAHO = False
    logger.info('paho-mqtt not installed — MQTT bridge disabled')

_client: 'paho_mqtt.Client | None' = None
_loop: asyncio.AbstractEventLoop | None = None
_connected = False
_config: dict = {}

# Callback for dispatching MQTT events to WebSocket
_ws_dispatch = None


def set_ws_dispatch(fn):
    """Set the function used to dispatch events to WebSocket clients.
    Expected signature: fn(event_type: str, data: dict)"""
    global _ws_dispatch
    _ws_dispatch = fn


def _on_connect(client, userdata, flags, rc):
    global _connected
    if rc == 0:
        _connected = True
        logger.info('MQTT connected to %s', _config.get('address', '?'))
        # Subscribe to JSON topics
        root = _config.get('root', 'msh')
        topic = f"{root}/+/2/json/#"
        client.subscribe(topic)
        logger.info('MQTT subscribed to %s', topic)
        if _ws_dispatch and _loop:
            _loop.call_soon_threadsafe(
                _loop.create_task,
                _dispatch('mqtt-status', {'connected': True, 'broker': _config.get('address', '')})
            )
    else:
        _connected = False
        logger.error('MQTT connect failed rc=%d', rc)


def _on_disconnect(client, userdata, rc):
    global _connected
    _connected = False
    logger.warning('MQTT disconnected rc=%d', rc)
    if _ws_dispatch and _loop:
        _loop.call_soon_threadsafe(
            _loop.create_task,
            _dispatch('mqtt-status', {'connected': False, 'broker': _config.get('address', '')})
        )


def _on_message(client, userdata, msg):
    """Handle incoming MQTT message — parse JSON and dispatch to WS."""
    try:
        payload = json.loads(msg.payload.decode('utf-8', errors='replace'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    event_data = {
        'topic': msg.topic,
        'payload': payload,
        'type': payload.get('type', 'unknown'),
    }
    if _ws_dispatch and _loop:
        _loop.call_soon_threadsafe(
            _loop.create_task,
            _dispatch('mqtt-message', event_data)
        )


async def _dispatch(event_type: str, data: dict):
    """Async wrapper for WS dispatch."""
    if _ws_dispatch:
        try:
            await _ws_dispatch(event_type, data)
        except Exception as e:
            logger.error('MQTT dispatch error: %s', e)


async def start(config: dict):
    """Start MQTT bridge with given config. Non-blocking."""
    global _client, _loop, _config
    if not HAS_PAHO:
        logger.warning('Cannot start MQTT bridge: paho-mqtt not installed')
        return
    if not config.get('enabled'):
        logger.info('MQTT bridge disabled in config')
        return
    _config = config
    _loop = asyncio.get_event_loop()

    address = config.get('address', 'mqtt.meshtastic.org')
    username = config.get('username', 'meshdev')
    password = config.get('password', 'large4cats')
    tls = config.get('tls_enabled', False)
    port = 8883 if tls else 1883

    _client = paho_mqtt.Client(client_id='pimesh-bridge', protocol=paho_mqtt.MQTTv311)
    _client.on_connect = _on_connect
    _client.on_disconnect = _on_disconnect
    _client.on_message = _on_message

    if username:
        _client.username_pw_set(username, password)
    if tls:
        _client.tls_set()

    try:
        _client.connect_async(address, port, keepalive=60)
        _client.loop_start()
        logger.info('MQTT bridge starting → %s:%d', address, port)
    except Exception as e:
        logger.error('MQTT bridge start failed: %s', e)


async def stop():
    """Stop MQTT bridge gracefully."""
    global _client, _connected
    if _client:
        _client.loop_stop()
        _client.disconnect()
        _client = None
        _connected = False
        logger.info('MQTT bridge stopped')


async def restart(config: dict):
    """Restart bridge with new config."""
    await stop()
    await start(config)


def publish(topic: str, payload: str | dict) -> bool:
    """Publish a message to MQTT broker. Returns True on success."""
    if not _client or not _connected:
        return False
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    result = _client.publish(topic, payload, qos=0)
    return result.rc == 0


def publish_downlink(text: str, from_id: int, to_id: int | None = None, channel: int = 0) -> bool:
    """Send a text message to the mesh via MQTT downlink.
    Requires json_enabled on the device and downlink_enabled on the channel."""
    if not _client or not _connected:
        return False
    root = _config.get('root', 'msh')
    from_hex = f'!{from_id:08x}'
    topic = f"{root}/2/json/mqtt/{from_hex}"
    msg = {'from': from_id, 'type': 'sendtext', 'payload': text}
    if to_id:
        msg['to'] = to_id
    if channel:
        msg['channel'] = channel
    return publish(topic, msg)


def is_connected() -> bool:
    return _connected


def get_status() -> dict:
    return {
        'available': HAS_PAHO,
        'connected': _connected,
        'broker': _config.get('address', '') if _config else '',
        'enabled': _config.get('enabled', False) if _config else False,
    }
