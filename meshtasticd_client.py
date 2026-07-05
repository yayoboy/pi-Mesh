"""meshtasticd_client.py — Unico punto di contatto con la radio Meshtastic.

Incapsula la libreria ``meshtastic`` (SerialInterface o TCPInterface, vedi
``connect()``) e la espone al resto dell'app in forma async-friendly:

  Letture     — cache nodi in memoria (refresh ogni 30s, flush su SQLite),
                get_*_config() leggono live dalla board e cadono sulla
                cache DB quando la board è offline.
  Scritture   — mai dirette: ogni comando passa da ``_command_queue`` ed è
                eseguito in serie da ``_command_worker`` in un executor,
                perché la libreria meshtastic è sincrona e non thread-safe.
  Eventi      — i callback pubsub della libreria (thread separato) vengono
                riportati sull'event loop con ``call_soon_threadsafe`` e
                fanno fan-out sulle code registrate con subscribe_events()
                (WebSocket, bot, bridge MQTT). Tipi evento: message, node,
                position, telemetry, log, traceroute_result, ack, waypoint,
                neighbor_info, sensor, paxcounter.

Le scritture config usano ``_write_local_config`` (mutazione in-place +
``writeConfig``): è l'API reale di meshtastic 2.x e preserva i campi non
toccati. L'admin remoto passa da ``getNode()`` così ``ensureSessionKey``
gestisce il PKC richiesto dal firmware 2.5+.
"""
import asyncio
import logging
import math
import time
from collections import deque

logger = logging.getLogger(__name__)

# --- State ---
_interface      = None
_connected      = False
_is_connecting  = False
_local_id: str  = ''
_node_cache: dict[str, dict] = {}
_dirty_nodes: set[str] = set()
_last_node_fetch: float = 0.0
_log_queue: deque = deque(maxlen=500)
_subscribers: list = []
_event_queues: list[asyncio.Queue] = []
_loop: asyncio.AbstractEventLoop | None = None
_traceroute_cache: dict[str, dict] = {}
_command_queue: asyncio.Queue = asyncio.Queue()

import config as cfg
import database


def _enqueue_event(event: dict) -> None:
    """Fan-out: thread-safe enqueue to every subscribed queue, dropping per-queue if full."""
    for q in _event_queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

NODE_CACHE_TTL = cfg.NODE_CACHE_TTL


# --- Public API ---

def is_connected() -> bool:
    return _connected


def get_nodes() -> list[dict]:
    """Return cached node list. Cache is refreshed by background connect loop every 30s."""
    return list(_node_cache.values())


def get_local_id() -> str:
    """Return the local node ID, or empty string if not yet known."""
    return _local_id


def get_local_node() -> dict | None:
    for node in _node_cache.values():
        if node.get('is_local'):
            return node
    return None


def get_log_queue() -> deque:
    return _log_queue


def subscribe_log(callback) -> None:
    _subscribers.append(callback)


def unsubscribe_log(callback) -> None:
    if callback in _subscribers:
        _subscribers.remove(callback)


def subscribe_events(maxsize: int = 500) -> asyncio.Queue:
    """Register a new subscriber queue. Every future event will be fanned out to it.

    Each subscriber owns its queue; backpressure on one subscriber does not affect
    the others (events are dropped per-queue when full, never globally).
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    _event_queues.append(q)
    return q


def unsubscribe_events(q: asyncio.Queue) -> None:
    """Remove a previously subscribed queue. Safe to call with an unknown queue."""
    if q in _event_queues:
        _event_queues.remove(q)


def get_event_queue() -> asyncio.Queue:
    """Backward-compat: returns the first subscribed queue, creating one if needed.

    New code should use subscribe_events() / unsubscribe_events() instead.
    """
    if not _event_queues:
        _event_queues.append(asyncio.Queue(maxsize=500))
    return _event_queues[0]


async def request_traceroute(node_id: str) -> None:
    """Queue a traceroute request to the given node."""
    await _command_queue.put(lambda: _interface.sendTraceRoute(dest=node_id, hopLimit=3))


async def request_position(node_id: str) -> None:
    """Queue a position request to the given node."""
    await _command_queue.put(lambda: _interface.requestPosition(node_id))


async def send_text(text: str, destination_id: str, channel: int = 0) -> None:
    """Queue a text message to the given destination."""
    await _command_queue.put(
        lambda: _interface.sendText(text, destinationId=destination_id, channelIndex=channel)
    )
    # Il log pacchetti nasce da _on_receive (solo RX): senza questo, i
    # messaggi trasmessi non comparirebbero mai nella pagina Log.
    dest = 'broadcast' if destination_id == '^all' else destination_id
    log_event = {
        'type':    'log',
        'ts':      int(time.time()),
        'from':    'tu',
        'portnum': 'TEXT_MESSAGE_APP',
        'snr':     None,
        'hop_limit': None,
        'summary': f'→ {dest} (ch {channel}): {text[:60]}',
    }
    _log_queue.append(log_event)
    if _loop is not None:
        _loop.call_soon_threadsafe(_enqueue_event, log_event)


def get_traceroute_result(node_id: str) -> dict | None:
    """Return cached traceroute result for a node, or None if not available."""
    return _traceroute_cache.get(node_id)


async def get_node_config(db_path: str) -> dict:
    """Read node config live from board, cache result. Returns cache if offline."""
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                dc = _interface.localNode.localConfig.device
                user = _interface.getMyUser() or {}
                return {
                    'long_name': _interface.getLongName(),
                    'short_name': _interface.getShortName(),
                    'role': dc.Role.Name(dc.role),
                    'is_licensed': bool(user.get('isLicensed', False)),
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'node', data)
            return data
        except Exception as e:
            logger.error('get_node_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'node')
    if cached:
        cached['cached'] = True
        return cached
    return {'cached': True}


async def get_lora_config(db_path: str) -> dict:
    """Read LoRa config live from board, cache result. Returns cache if offline."""
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                lc = _interface.localNode.localConfig.lora
                return {
                    'region': lc.RegionCode.Name(lc.region),
                    'modem_preset': lc.ModemPreset.Name(lc.modem_preset),
                    'hop_limit': lc.hop_limit,
                    'tx_enabled': lc.tx_enabled,
                    'tx_power': lc.tx_power,
                    'channel_num': lc.channel_num,
                    'override_duty_cycle': lc.override_duty_cycle,
                    'sx126x_rx_boosted_gain': lc.sx126x_rx_boosted_gain,
                    'ignore_mqtt': lc.ignore_mqtt,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'lora', data)
            return data
        except Exception as e:
            logger.error('get_lora_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'lora')
    if cached:
        cached['cached'] = True
        return cached
    return {'cached': True}


async def get_channels(db_path: str) -> list[dict]:
    """Read channels from board, cache result. Returns cache if offline."""
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                import base64
                result = []
                for ch in _interface.localNode.channels:
                    psk_b64 = base64.b64encode(ch.settings.psk).decode() if ch.settings.psk else ''
                    result.append({
                        'index': ch.index,
                        'name': ch.settings.name,
                        'psk_b64': psk_b64,
                        'role': ch.Role.Name(ch.role),
                        'uplink_enabled': ch.settings.uplink_enabled,
                        'downlink_enabled': ch.settings.downlink_enabled,
                        # 0 = precisione piena; 1-32 = bit di precisione della
                        # posizione condivisa su questo canale
                        'position_precision': ch.settings.module_settings.position_precision,
                    })
                return result
            data = await loop.run_in_executor(None, _read)
            await database.set_config_cache(db_path, 'channels', {'channels': data})
            return data
        except Exception as e:
            logger.error('get_channels failed: %s', e)
    cached = await database.get_config_cache(db_path, 'channels')
    if cached:
        return cached.get('channels', [])
    return []


async def get_mqtt_config(db_path: str) -> dict:
    """Read MQTT module config from board, cache result."""
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.mqtt
                return {
                    'enabled': mc.enabled,
                    'address': mc.address or 'mqtt.meshtastic.org',
                    'username': mc.username or 'meshdev',
                    'password': mc.password or 'large4cats',
                    'encryption_enabled': mc.encryption_enabled,
                    'json_enabled': mc.json_enabled,
                    'tls_enabled': mc.tls_enabled,
                    'root': mc.root or 'msh',
                    'proxy_to_client_enabled': mc.proxy_to_client_enabled,
                    'map_reporting_enabled': mc.map_reporting_enabled,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'mqtt', data)
            return data
        except Exception as e:
            logger.error('get_mqtt_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'mqtt')
    if cached:
        cached['cached'] = True
        return cached
    return {
        'enabled': False, 'address': 'mqtt.meshtastic.org', 'username': 'meshdev',
        'password': 'large4cats', 'encryption_enabled': False, 'json_enabled': False,
        'tls_enabled': False, 'root': 'msh', 'proxy_to_client_enabled': False,
        'map_reporting_enabled': False, 'cached': True,
    }


_LOCAL_CONFIG_SECTIONS = frozenset(
    {'device', 'position', 'power', 'network', 'display', 'lora', 'bluetooth', 'security'})


def _write_local_config(section: str, updates: dict) -> None:
    """Apply updates in place to localConfig/moduleConfig.<section>, then
    persist with writeConfig().

    In-place mutation preserves every field we are not changing (a freshly
    built protobuf would silently zero them), and writeConfig() is the write
    API that actually exists in meshtastic 2.x — Node.setConfig does not.
    """
    node = _interface.localNode
    root = node.localConfig if section in _LOCAL_CONFIG_SECTIONS else node.moduleConfig
    target = getattr(root, section)
    for key, value in updates.items():
        setattr(target, key, value)
    node.writeConfig(section)


def _do_set_node_config(long_name: str, short_name: str, role: str,
                        is_licensed: bool = False) -> None:
    """Sync helper — runs in command queue thread."""
    _interface.localNode.setOwner(long_name, short_name, is_licensed=is_licensed)
    from meshtastic.protobuf import config_pb2
    role_val = config_pb2.Config.DeviceConfig.Role.Value(role)
    _write_local_config('device', {'role': role_val})


async def set_node_config(long_name: str, short_name: str, role: str,
                          is_licensed: bool = False) -> None:
    """Queue node config write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _ln, _sn, _r, _lic = long_name, short_name, role, is_licensed
    await _command_queue.put(lambda: _do_set_node_config(_ln, _sn, _r, _lic))


def _do_set_lora_config(params: dict) -> None:
    """Sync helper — runs in command queue thread."""
    from meshtastic.protobuf import config_pb2
    _write_local_config('lora', {
        'region': config_pb2.Config.LoRaConfig.RegionCode.Value(
            params.get('region', 'UNSET')),
        'modem_preset': config_pb2.Config.LoRaConfig.ModemPreset.Value(
            params.get('modem_preset', 'LONG_FAST')),
        'hop_limit': params.get('hop_limit', 3),
        'tx_enabled': params.get('tx_enabled', True),
        'tx_power': params.get('tx_power', 0),        # 0 = massimo consentito
        'channel_num': params.get('channel_num', 0),  # 0 = slot dal nome canale
        'override_duty_cycle': params.get('override_duty_cycle', False),
        'sx126x_rx_boosted_gain': params.get('sx126x_rx_boosted_gain', False),
        'ignore_mqtt': params.get('ignore_mqtt', False),
    })


async def set_lora_config(params: dict) -> None:
    """Queue LoRa config write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_lora_config(_p))


async def send_waypoint(name: str, lat: float, lon: float,
                        icon: str, description: str, expire: int) -> None:
    """Send a waypoint via serial interface."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    import random
    wp_id = random.randint(1, 0x7FFFFFFF)
    _n, _la, _lo, _ic, _de, _ex, _id = name, lat, lon, icon, description, expire, wp_id

    def _do():
        from meshtastic.protobuf import mesh_pb2
        wp = mesh_pb2.Waypoint(
            id=_id,
            name=_n,
            description=_de,
            expire=_ex,
            latitude_i=int(_la * 1e7),
            longitude_i=int(_lo * 1e7),
        )
        _interface.sendWaypoint(wp)

    await _command_queue.put(_do)


async def send_admin(dest_node_id: str, operation: str, payload: dict | None = None) -> None:
    """Send an admin command to a remote node via mesh.

    Supported operations:
      'request_position'  — ask node to send its GPS position
      'request_telemetry' — ask node to send device telemetry
      'reboot'            — reboot the remote node
      'factory_reset'     — factory reset the remote node (DESTRUCTIVE)
    """
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _dest = dest_node_id
    _op = operation

    def _do():
        try:
            int(_dest.lstrip('!'), 16)
        except ValueError:
            raise RuntimeError(f'Invalid node id: {_dest}')

        if _op == 'request_position':
            _interface.sendPosition(destinationId=_dest, wantResponse=True)
        elif _op == 'request_telemetry':
            _interface.sendTelemetry(destinationId=_dest, wantResponse=True)
        elif _op in ('reboot', 'factory_reset'):
            # getNode() gives a Node whose admin sends go through
            # ensureSessionKey(): required by firmware 2.5+ (PKC/session
            # passkey) — raw AdminMessages on ADMIN_APP get rejected there.
            # Channels are not needed for these operations, skip the
            # (slow) remote channel fetch.
            node = _interface.getNode(_dest, requestChannels=False)
            if _op == 'reboot':
                node.reboot(secs=2)
            else:
                node.factoryReset()
        else:
            raise RuntimeError(f'Unknown admin operation: {_op}')

    await _command_queue.put(_do)


def _do_set_mqtt_config(params: dict) -> None:
    """Sync helper — runs in command queue thread."""
    _write_local_config('mqtt', {
        'enabled': params.get('enabled', False),
        'address': params.get('address', ''),
        'username': params.get('username', ''),
        'password': params.get('password', ''),
        'encryption_enabled': params.get('encryption_enabled', False),
        'json_enabled': params.get('json_enabled', False),
        'tls_enabled': params.get('tls_enabled', False),
        'root': params.get('root', ''),
        'proxy_to_client_enabled': params.get('proxy_to_client_enabled', False),
        'map_reporting_enabled': params.get('map_reporting_enabled', False),
    })


async def set_mqtt_config(params: dict) -> None:
    """Queue MQTT config write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    p = dict(params)
    await _command_queue.put(lambda: _do_set_mqtt_config(p))


async def get_external_notification_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.external_notification
                return {
                    'enabled': mc.enabled,
                    'output_pin': mc.output_pin,
                    'active_high': mc.active_high,
                    'alert_message': mc.alert_message,
                    'alert_bell': mc.alert_bell,
                    'use_pwm': mc.use_pwm,
                    'nag_timeout': mc.nag_timeout,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'external_notification', data)
            return data
        except Exception as e:
            logger.error('get_external_notification_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'external_notification')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'output_pin': 0, 'active_high': False,
            'alert_message': False, 'alert_bell': False, 'use_pwm': False,
            'nag_timeout': 0, 'cached': True}


def _do_set_external_notification_config(params: dict) -> None:
    _write_local_config('external_notification', {
        'enabled': params.get('enabled', False),
        'output_pin': params.get('output_pin', 0),
        'active_high': params.get('active_high', False),
        'alert_message': params.get('alert_message', False),
        'alert_bell': params.get('alert_bell', False),
        'use_pwm': params.get('use_pwm', False),
        'nag_timeout': params.get('nag_timeout', 0),
    })


async def set_external_notification_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_external_notification_config(_p))


async def get_store_forward_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.store_forward
                return {
                    'enabled': mc.enabled,
                    'heartbeat': mc.heartbeat,
                    'history_return_max': mc.history_return_max,
                    'history_return_window': mc.history_return_window,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'store_forward', data)
            return data
        except Exception as e:
            logger.error('get_store_forward_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'store_forward')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'heartbeat': False,
            'history_return_max': 0, 'history_return_window': 0, 'cached': True}


def _do_set_store_forward_config(params: dict) -> None:
    _write_local_config('store_forward', {
        'enabled': params.get('enabled', False),
        'heartbeat': params.get('heartbeat', False),
        'history_return_max': params.get('history_return_max', 0),
        'history_return_window': params.get('history_return_window', 0),
    })


async def set_store_forward_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_store_forward_config(_p))


async def get_telemetry_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.telemetry
                return {
                    'device_update_interval': mc.device_update_interval,
                    'environment_update_interval': mc.environment_update_interval,
                    'environment_measurement_enabled': mc.environment_measurement_enabled,
                    'air_quality_enabled': mc.air_quality_enabled,
                    'power_measurement_enabled': mc.power_measurement_enabled,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'telemetry_module', data)
            return data
        except Exception as e:
            logger.error('get_telemetry_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'telemetry_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'device_update_interval': 0, 'environment_update_interval': 0,
            'environment_measurement_enabled': False, 'air_quality_enabled': False,
            'power_measurement_enabled': False, 'cached': True}


def _do_set_telemetry_module_config(params: dict) -> None:
    _write_local_config('telemetry', {
        'device_update_interval': params.get('device_update_interval', 0),
        'environment_update_interval': params.get('environment_update_interval', 0),
        'environment_measurement_enabled': params.get('environment_measurement_enabled', False),
        'air_quality_enabled': params.get('air_quality_enabled', False),
        'power_measurement_enabled': params.get('power_measurement_enabled', False),
    })


async def set_telemetry_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_telemetry_module_config(_p))


async def get_canned_message_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.canned_message
                return {
                    'rotary1_enabled': mc.rotary1_enabled,
                    'send_bell': mc.send_bell,
                    'free_text_sms_enabled': mc.free_text_sms_enabled,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'canned_message_module', data)
            return data
        except Exception as e:
            logger.error('get_canned_message_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'canned_message_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'rotary1_enabled': False, 'send_bell': False,
            'free_text_sms_enabled': False, 'cached': True}


def _do_set_canned_message_module_config(params: dict) -> None:
    _write_local_config('canned_message', {
        'rotary1_enabled': params.get('rotary1_enabled', False),
        'send_bell': params.get('send_bell', False),
        'free_text_sms_enabled': params.get('free_text_sms_enabled', False),
    })


async def set_canned_message_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_canned_message_module_config(_p))


async def get_range_test_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.range_test
                return {
                    'enabled': mc.enabled,
                    'sender': mc.sender,
                    'save': mc.save,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'range_test', data)
            return data
        except Exception as e:
            logger.error('get_range_test_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'range_test')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'sender': 0, 'save': False, 'cached': True}


def _do_set_range_test_config(params: dict) -> None:
    _write_local_config('range_test', {
        'enabled': params.get('enabled', False),
        'sender': params.get('sender', 0),
        'save': params.get('save', False),
    })


async def set_range_test_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_range_test_config(_p))


async def get_detection_sensor_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.detection_sensor
                return {
                    'enabled': mc.enabled,
                    'minimum_broadcast_secs': mc.minimum_broadcast_secs,
                    'state_broadcast_secs': mc.state_broadcast_secs,
                    'name': mc.name,
                    'monitor_pin': mc.monitor_pin,
                    'use_pullup': mc.use_pullup,
                    'detection_triggered_high': mc.detection_triggered_high,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'detection_sensor', data)
            return data
        except Exception as e:
            logger.error('get_detection_sensor_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'detection_sensor')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'minimum_broadcast_secs': 0, 'state_broadcast_secs': 0,
            'name': '', 'monitor_pin': 0, 'use_pullup': False,
            'detection_triggered_high': False, 'cached': True}


def _do_set_detection_sensor_config(params: dict) -> None:
    _write_local_config('detection_sensor', {
        'enabled': params.get('enabled', False),
        'minimum_broadcast_secs': params.get('minimum_broadcast_secs', 0),
        'state_broadcast_secs': params.get('state_broadcast_secs', 0),
        'name': params.get('name', ''),
        'monitor_pin': params.get('monitor_pin', 0),
        'use_pullup': params.get('use_pullup', False),
        'detection_triggered_high': params.get('detection_triggered_high', False),
    })


async def set_detection_sensor_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_detection_sensor_config(_p))


async def get_ambient_lighting_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.ambient_lighting
                return {
                    'led_state': mc.led_state,
                    'current': mc.current,
                    'red': mc.red,
                    'green': mc.green,
                    'blue': mc.blue,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'ambient_lighting', data)
            return data
        except Exception as e:
            logger.error('get_ambient_lighting_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'ambient_lighting')
    if cached:
        cached['cached'] = True
        return cached
    return {'led_state': False, 'current': 0, 'red': 0,
            'green': 0, 'blue': 0, 'cached': True}


def _do_set_ambient_lighting_config(params: dict) -> None:
    _write_local_config('ambient_lighting', {
        'led_state': params.get('led_state', False),
        'current': params.get('current', 0),
        'red': params.get('red', 0),
        'green': params.get('green', 0),
        'blue': params.get('blue', 0),
    })


async def set_ambient_lighting_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_ambient_lighting_config(_p))


async def get_neighbor_info_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.neighbor_info
                return {
                    'enabled': mc.enabled,
                    'update_interval': mc.update_interval,
                    'transmit_over_lora': mc.transmit_over_lora,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'neighbor_info_module', data)
            return data
        except Exception as e:
            logger.error('get_neighbor_info_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'neighbor_info_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'update_interval': 0,
            'transmit_over_lora': False, 'cached': True}


def _do_set_neighbor_info_module_config(params: dict) -> None:
    _write_local_config('neighbor_info', {
        'enabled': params.get('enabled', False),
        'update_interval': params.get('update_interval', 0),
        'transmit_over_lora': params.get('transmit_over_lora', False),
    })


async def set_neighbor_info_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_neighbor_info_module_config(_p))


async def get_serial_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.serial
                return {
                    'enabled': mc.enabled,
                    'echo': mc.echo,
                    'rxd': mc.rxd,
                    'txd': mc.txd,
                    'timeout': mc.timeout,
                    'mode': mc.Mode.Name(mc.mode),
                    'override_console_serial_port': mc.override_console_serial_port,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'serial_module', data)
            return data
        except Exception as e:
            logger.error('get_serial_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'serial_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'echo': False, 'rxd': 0, 'txd': 0,
            'timeout': 0, 'mode': 'DEFAULT', 'override_console_serial_port': False,
            'cached': True}


def _do_set_serial_module_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    mode_val = 0  # DEFAULT enum value
    try:
        mode_val = module_config_pb2.ModuleConfig.SerialConfig.Mode.Value(params.get('mode', 'DEFAULT'))
    except ValueError:
        pass
    _write_local_config('serial', {
        'enabled': params.get('enabled', False),
        'echo': params.get('echo', False),
        'rxd': params.get('rxd', 0),
        'txd': params.get('txd', 0),
        'timeout': params.get('timeout', 0),
        'mode': mode_val,
        'override_console_serial_port': params.get('override_console_serial_port', False),
    })


async def set_serial_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_serial_module_config(_p))


def _do_set_channel(idx: int, params: dict) -> None:
    """Sync helper — runs in command queue thread."""
    import base64
    from meshtastic.protobuf import channel_pb2
    ch = _interface.localNode.channels[idx]
    ch.settings.name = params.get('name', '')
    if params.get('psk_b64'):
        ch.settings.psk = base64.b64decode(params['psk_b64'])
    if params.get('role') is not None:
        ch.role = channel_pb2.Channel.Role.Value(params['role'])
    ch.settings.uplink_enabled = params.get('uplink_enabled', False)
    ch.settings.downlink_enabled = params.get('downlink_enabled', False)
    ch.settings.module_settings.position_precision = params.get('position_precision', 0)
    _interface.localNode.writeChannel(idx)


async def set_channel(idx: int, params: dict) -> None:
    """Queue channel write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _i, _p = idx, dict(params)
    await _command_queue.put(lambda: _do_set_channel(_i, _p))


async def get_channel_url() -> str:
    """URL condivisibile (https://meshtastic.org/e/#...) di canali+LoRa."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _interface.localNode.getURL())


async def set_channel_url(url: str, add_only: bool = False) -> None:
    """Importa canali (e config LoRa) da un URL meshtastic.org/e/#.

    Con add_only=True i canali dell'URL vengono aggiunti a quelli esistenti
    invece di sostituirli.
    """
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _u, _a = url, add_only
    await _command_queue.put(lambda: _interface.localNode.setURL(_u, addOnly=_a))


# --- Device-level config sections (position, power, display, network, bluetooth, security) ---

async def _get_cached_section(db_path: str, cache_key: str, reader, defaults: dict) -> dict:
    """Shared read pattern: live read + cache when connected, cache fallback,
    defaults as last resort. `reader` is a sync callable run in the executor."""
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, reader)
            data['cached'] = False
            await database.set_config_cache(db_path, cache_key, data)
            return data
        except Exception as e:
            logger.error('get %s config failed: %s', cache_key, e)
    cached = await database.get_config_cache(db_path, cache_key)
    if cached:
        cached['cached'] = True
        return cached
    return {**defaults, 'cached': True}


POSITION_DEFAULTS = {
    'position_broadcast_secs': 0, 'position_broadcast_smart_enabled': False,
    'fixed_position': False, 'gps_mode': 'DISABLED', 'gps_update_interval': 0,
    'fixed_lat': None, 'fixed_lon': None, 'fixed_alt': 0,
}


async def get_position_config(db_path: str) -> dict:
    def _read():
        pc = _interface.localNode.localConfig.position
        return {
            'position_broadcast_secs': pc.position_broadcast_secs,
            'position_broadcast_smart_enabled': pc.position_broadcast_smart_enabled,
            'fixed_position': pc.fixed_position,
            'gps_mode': pc.GpsMode.Name(pc.gps_mode),
            'gps_update_interval': pc.gps_update_interval,
        }
    return await _get_cached_section(db_path, 'position', _read, POSITION_DEFAULTS)


def _do_set_position_config(params: dict) -> None:
    from meshtastic.protobuf import config_pb2
    fixed = bool(params.get('fixed_position', False))
    lat, lon = params.get('fixed_lat'), params.get('fixed_lon')
    if fixed and lat is not None and lon is not None:
        # setFixedPosition sends the admin message that stores the position
        # AND raises the fixed_position flag on the node.
        _interface.localNode.setFixedPosition(
            float(lat), float(lon), int(params.get('fixed_alt') or 0))
    elif not fixed and _interface.localNode.localConfig.position.fixed_position:
        _interface.localNode.removeFixedPosition()
    _write_local_config('position', {
        'position_broadcast_secs': params.get('position_broadcast_secs', 0),
        'position_broadcast_smart_enabled': params.get('position_broadcast_smart_enabled', False),
        'fixed_position': fixed,
        'gps_mode': config_pb2.Config.PositionConfig.GpsMode.Value(
            params.get('gps_mode', 'DISABLED')),
        'gps_update_interval': params.get('gps_update_interval', 0),
    })


async def set_position_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_position_config(_p))


POWER_DEFAULTS = {
    'is_power_saving': False, 'on_battery_shutdown_after_secs': 0,
    'wait_bluetooth_secs': 0, 'sds_secs': 0, 'ls_secs': 0, 'min_wake_secs': 0,
}


async def get_power_config(db_path: str) -> dict:
    def _read():
        pc = _interface.localNode.localConfig.power
        return {
            'is_power_saving': pc.is_power_saving,
            'on_battery_shutdown_after_secs': pc.on_battery_shutdown_after_secs,
            'wait_bluetooth_secs': pc.wait_bluetooth_secs,
            'sds_secs': pc.sds_secs,
            'ls_secs': pc.ls_secs,
            'min_wake_secs': pc.min_wake_secs,
        }
    return await _get_cached_section(db_path, 'power', _read, POWER_DEFAULTS)


def _do_set_power_config(params: dict) -> None:
    _write_local_config('power', {
        'is_power_saving': params.get('is_power_saving', False),
        'on_battery_shutdown_after_secs': params.get('on_battery_shutdown_after_secs', 0),
        'wait_bluetooth_secs': params.get('wait_bluetooth_secs', 0),
        'sds_secs': params.get('sds_secs', 0),
        'ls_secs': params.get('ls_secs', 0),
        'min_wake_secs': params.get('min_wake_secs', 0),
    })


async def set_power_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_power_config(_p))


DISPLAY_DEVICE_DEFAULTS = {
    'screen_on_secs': 0, 'auto_screen_carousel_secs': 0, 'compass_north_top': False,
    'flip_screen': False, 'units': 'METRIC', 'displaymode': 'DEFAULT',
    'heading_bold': False, 'wake_on_tap_or_motion': False, 'use_12h_clock': False,
}


async def get_display_device_config(db_path: str) -> dict:
    """Display config of the Meshtastic board (OLED), not the Pi display."""
    def _read():
        dc = _interface.localNode.localConfig.display
        return {
            'screen_on_secs': dc.screen_on_secs,
            'auto_screen_carousel_secs': dc.auto_screen_carousel_secs,
            'compass_north_top': dc.compass_north_top,
            'flip_screen': dc.flip_screen,
            'units': dc.DisplayUnits.Name(dc.units),
            'displaymode': dc.DisplayMode.Name(dc.displaymode),
            'heading_bold': dc.heading_bold,
            'wake_on_tap_or_motion': dc.wake_on_tap_or_motion,
            'use_12h_clock': dc.use_12h_clock,
        }
    return await _get_cached_section(db_path, 'display_device', _read, DISPLAY_DEVICE_DEFAULTS)


def _do_set_display_device_config(params: dict) -> None:
    from meshtastic.protobuf import config_pb2
    _write_local_config('display', {
        'screen_on_secs': params.get('screen_on_secs', 0),
        'auto_screen_carousel_secs': params.get('auto_screen_carousel_secs', 0),
        'compass_north_top': params.get('compass_north_top', False),
        'flip_screen': params.get('flip_screen', False),
        'units': config_pb2.Config.DisplayConfig.DisplayUnits.Value(
            params.get('units', 'METRIC')),
        'displaymode': config_pb2.Config.DisplayConfig.DisplayMode.Value(
            params.get('displaymode', 'DEFAULT')),
        'heading_bold': params.get('heading_bold', False),
        'wake_on_tap_or_motion': params.get('wake_on_tap_or_motion', False),
        'use_12h_clock': params.get('use_12h_clock', False),
    })


async def set_display_device_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_display_device_config(_p))


NETWORK_DEFAULTS = {
    'wifi_enabled': False, 'wifi_ssid': '', 'wifi_psk': '',
    'eth_enabled': False, 'ntp_server': '', 'address_mode': 'DHCP',
}


async def get_network_config(db_path: str) -> dict:
    def _read():
        nc = _interface.localNode.localConfig.network
        return {
            'wifi_enabled': nc.wifi_enabled,
            'wifi_ssid': nc.wifi_ssid,
            'wifi_psk': nc.wifi_psk,
            'eth_enabled': nc.eth_enabled,
            'ntp_server': nc.ntp_server,
            'address_mode': nc.AddressMode.Name(nc.address_mode),
        }
    return await _get_cached_section(db_path, 'network', _read, NETWORK_DEFAULTS)


def _do_set_network_config(params: dict) -> None:
    from meshtastic.protobuf import config_pb2
    _write_local_config('network', {
        'wifi_enabled': params.get('wifi_enabled', False),
        'wifi_ssid': params.get('wifi_ssid', ''),
        'wifi_psk': params.get('wifi_psk', ''),
        'eth_enabled': params.get('eth_enabled', False),
        'ntp_server': params.get('ntp_server', ''),
        'address_mode': config_pb2.Config.NetworkConfig.AddressMode.Value(
            params.get('address_mode', 'DHCP')),
    })


async def set_network_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_network_config(_p))


BLUETOOTH_DEFAULTS = {'enabled': False, 'mode': 'RANDOM_PIN', 'fixed_pin': 123456}


async def get_bluetooth_config(db_path: str) -> dict:
    def _read():
        bc = _interface.localNode.localConfig.bluetooth
        return {
            'enabled': bc.enabled,
            'mode': bc.PairingMode.Name(bc.mode),
            'fixed_pin': bc.fixed_pin,
        }
    return await _get_cached_section(db_path, 'bluetooth', _read, BLUETOOTH_DEFAULTS)


def _do_set_bluetooth_config(params: dict) -> None:
    from meshtastic.protobuf import config_pb2
    _write_local_config('bluetooth', {
        'enabled': params.get('enabled', False),
        'mode': config_pb2.Config.BluetoothConfig.PairingMode.Value(
            params.get('mode', 'RANDOM_PIN')),
        'fixed_pin': params.get('fixed_pin', 123456),
    })


async def set_bluetooth_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_bluetooth_config(_p))


SECURITY_DEFAULTS = {
    'is_managed': False, 'serial_enabled': True,
    'debug_log_api_enabled': False, 'admin_channel_enabled': False,
    'public_key_b64': '',
}


async def get_security_config(db_path: str) -> dict:
    def _read():
        import base64
        sc = _interface.localNode.localConfig.security
        return {
            'is_managed': sc.is_managed,
            'serial_enabled': sc.serial_enabled,
            'debug_log_api_enabled': sc.debug_log_api_enabled,
            'admin_channel_enabled': sc.admin_channel_enabled,
            # Read-only: the key pair is never writable from the UI.
            'public_key_b64': base64.b64encode(sc.public_key).decode() if sc.public_key else '',
        }
    return await _get_cached_section(db_path, 'security', _read, SECURITY_DEFAULTS)


def _do_set_security_config(params: dict) -> None:
    _write_local_config('security', {
        'is_managed': params.get('is_managed', False),
        'serial_enabled': params.get('serial_enabled', True),
        'debug_log_api_enabled': params.get('debug_log_api_enabled', False),
        'admin_channel_enabled': params.get('admin_channel_enabled', False),
    })


async def set_security_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_security_config(_p))


# --- Moduli restanti: audio, paxcounter, remote hardware ---

AUDIO_DEFAULTS = {'codec2_enabled': False, 'ptt_pin': 0, 'bitrate': 'CODEC2_DEFAULT',
                  'i2s_ws': 0, 'i2s_sd': 0, 'i2s_din': 0, 'i2s_sck': 0}


async def get_audio_config(db_path: str) -> dict:
    def _read():
        mc = _interface.localNode.moduleConfig.audio
        return {
            'codec2_enabled': mc.codec2_enabled,
            'ptt_pin': mc.ptt_pin,
            'bitrate': mc.Audio_Baud.Name(mc.bitrate),
            'i2s_ws': mc.i2s_ws, 'i2s_sd': mc.i2s_sd,
            'i2s_din': mc.i2s_din, 'i2s_sck': mc.i2s_sck,
        }
    return await _get_cached_section(db_path, 'audio', _read, AUDIO_DEFAULTS)


def _do_set_audio_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    _write_local_config('audio', {
        'codec2_enabled': params.get('codec2_enabled', False),
        'ptt_pin': params.get('ptt_pin', 0),
        'bitrate': module_config_pb2.ModuleConfig.AudioConfig.Audio_Baud.Value(
            params.get('bitrate', 'CODEC2_DEFAULT')),
        'i2s_ws': params.get('i2s_ws', 0), 'i2s_sd': params.get('i2s_sd', 0),
        'i2s_din': params.get('i2s_din', 0), 'i2s_sck': params.get('i2s_sck', 0),
    })


async def set_audio_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_audio_config(_p))


PAXCOUNTER_DEFAULTS = {'enabled': False, 'paxcounter_update_interval': 0,
                       'wifi_threshold': 0, 'ble_threshold': 0}


async def get_paxcounter_config(db_path: str) -> dict:
    def _read():
        mc = _interface.localNode.moduleConfig.paxcounter
        return {
            'enabled': mc.enabled,
            'paxcounter_update_interval': mc.paxcounter_update_interval,
            'wifi_threshold': mc.wifi_threshold,
            'ble_threshold': mc.ble_threshold,
        }
    return await _get_cached_section(db_path, 'paxcounter', _read, PAXCOUNTER_DEFAULTS)


def _do_set_paxcounter_config(params: dict) -> None:
    _write_local_config('paxcounter', {
        'enabled': params.get('enabled', False),
        'paxcounter_update_interval': params.get('paxcounter_update_interval', 0),
        'wifi_threshold': params.get('wifi_threshold', 0),
        'ble_threshold': params.get('ble_threshold', 0),
    })


async def set_paxcounter_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_paxcounter_config(_p))


REMOTE_HARDWARE_DEFAULTS = {'enabled': False, 'allow_undefined_pin_access': False}


async def get_remote_hardware_config(db_path: str) -> dict:
    def _read():
        mc = _interface.localNode.moduleConfig.remote_hardware
        return {
            'enabled': mc.enabled,
            'allow_undefined_pin_access': mc.allow_undefined_pin_access,
        }
    return await _get_cached_section(db_path, 'remote_hardware', _read,
                                     REMOTE_HARDWARE_DEFAULTS)


def _do_set_remote_hardware_config(params: dict) -> None:
    _write_local_config('remote_hardware', {
        'enabled': params.get('enabled', False),
        'allow_undefined_pin_access': params.get('allow_undefined_pin_access', False),
    })


async def set_remote_hardware_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_remote_hardware_config(_p))


# --- Utilità nodo: preferiti/ignorati, orario, reset NodeDB ---

async def set_node_favorite(node_id: str, favorite: bool) -> None:
    """Marca/smarca un nodo come preferito sulla board locale."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _id, _fav = node_id, favorite

    def _do():
        if _fav:
            _interface.localNode.setFavorite(_id)
        else:
            _interface.localNode.removeFavorite(_id)
    await _command_queue.put(_do)


async def set_node_ignored(node_id: str, ignored: bool) -> None:
    """Ignora/de-ignora un nodo sulla board locale."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _id, _ign = node_id, ignored

    def _do():
        if _ign:
            _interface.localNode.setIgnored(_id)
        else:
            _interface.localNode.removeIgnored(_id)
    await _command_queue.put(_do)


async def sync_time() -> None:
    """Imposta l'orologio della board dall'orario del Pi (RTC/NTP)."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    await _command_queue.put(lambda: _interface.localNode.setTime(int(time.time())))


async def reset_nodedb() -> None:
    """Svuota il NodeDB della board (l'anagrafica nodi ricomincia da zero)."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    await _command_queue.put(lambda: _interface.localNode.resetNodeDb())


# --- Config remota: leggi/scrivi le sezioni di un nodo via mesh ---

def _apply_updates(msg, updates: dict) -> None:
    """Applica un dict a un messaggio protobuf, convertendo i nomi enum.

    Ignora le chiavi sconosciute e i campi non scalari (bytes/sub-messaggi):
    la UI remota lavora sugli stessi nomi campo dei form locali.
    """
    from google.protobuf.descriptor import FieldDescriptor
    fields = {f.name: f for f in msg.DESCRIPTOR.fields}
    for key, value in updates.items():
        f = fields.get(key)
        if f is None or f.type == FieldDescriptor.TYPE_BYTES \
                or f.type == FieldDescriptor.TYPE_MESSAGE:
            continue
        if f.type == FieldDescriptor.TYPE_ENUM and isinstance(value, str):
            value = f.enum_type.values_by_name[value].number
        setattr(msg, key, value)


REMOTE_CONFIG_TIMEOUT = 120  # s: un roundtrip admin sulla mesh può essere lento


async def get_remote_config(node_id: str, section: str) -> dict:
    """Legge una sezione config da un nodo remoto via admin mesh (lento)."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')

    def _read():
        from google.protobuf.json_format import MessageToDict
        node = _interface.getNode(node_id, requestChannels=False)
        root = node.localConfig if section in _LOCAL_CONFIG_SECTIONS else node.moduleConfig
        node.requestConfig(root.DESCRIPTOR.fields_by_name[section])
        return MessageToDict(getattr(root, section), preserving_proto_field_name=True,
                             always_print_fields_with_no_presence=True)

    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(loop.run_in_executor(None, _read),
                                  timeout=REMOTE_CONFIG_TIMEOUT)


async def set_remote_config(node_id: str, section: str, updates: dict) -> None:
    """Scrive una sezione config su un nodo remoto via admin mesh.

    Prima rilegge la sezione dal nodo per non azzerare i campi non toccati,
    poi applica gli update e la riscrive con writeConfig (session key PKC
    gestita da getNode/_sendAdmin).
    """
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _id, _sec, _upd = node_id, section, dict(updates)

    def _do():
        node = _interface.getNode(_id, requestChannels=False)
        root = node.localConfig if _sec in _LOCAL_CONFIG_SECTIONS else node.moduleConfig
        node.requestConfig(root.DESCRIPTOR.fields_by_name[_sec])
        _apply_updates(getattr(root, _sec), _upd)
        node.writeConfig(_sec)

    await _command_queue.put(_do)


# --- Internal ---

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _add_distances() -> None:
    local_lat = local_lon = None
    for node in _node_cache.values():
        if node.get('is_local') and node.get('latitude') is not None and node.get('longitude') is not None:
            local_lat = node['latitude']
            local_lon = node['longitude']
            break
    for node in _node_cache.values():
        if node.get('is_local'):
            node['distance_km'] = 0.0
        elif local_lat is not None and node.get('latitude') is not None and node.get('longitude') is not None:
            node['distance_km'] = round(_haversine(local_lat, local_lon, node['latitude'], node['longitude']), 2)
        else:
            node['distance_km'] = None


def _refresh_node_cache() -> None:
    global _node_cache, _last_node_fetch
    try:
        raw = _interface.nodes or {}
        new_cache = {}
        for node_id, info in raw.items():
            user = info.get('user', {})
            pos  = info.get('position', {})
            metrics = info.get('deviceMetrics', {})
            new_cache[node_id] = {
                'id':            user.get('id', node_id),
                'short_name':    user.get('shortName', ''),
                'long_name':     user.get('longName', ''),
                'hw_model':      user.get('hwModel', ''),
                'latitude':      pos.get('latitude'),
                'longitude':     pos.get('longitude'),
                'last_heard':    info.get('lastHeard'),
                'snr':           info.get('snr'),
                'hop_count':     info.get('hopsAway'),
                'battery_level': metrics.get('batteryLevel'),
                'is_local':      node_id == _local_id,
                'raw_json':      str(info),
                'distance_km':   None,
                'rssi':             info.get('rxRssi'),
                'firmware_version': user.get('firmwareVersion'),
                'role':             user.get('role'),
                'public_key':       user.get('publicKey'),
                'altitude':         pos.get('altitude'),
            }
        _dirty_nodes.update(new_cache.keys())
        _node_cache = new_cache  # atomic swap
        _add_distances()
        _last_node_fetch = time.time()
    except Exception as e:
        logger.warning(f'Node cache refresh failed: {e}')


async def _save_incoming_message(
    from_id: str, channel: int, text: str, snr, hop_limit, dest: str
) -> None:
    now = int(time.time())
    msg_id = await database.save_message(
        cfg.DB_PATH, from_id, channel, text,
        now, False, snr, hop_limit, dest
    )
    typed_event = {
        'type':        'message',
        'id':          msg_id,
        'from':        from_id,        # alias used by EventBus / bots layer
        'node_id':     from_id,
        'channel':     channel,
        'text':        text,
        'ts':          now,
        'is_outgoing': False,
        'rx_snr':      snr,
        'hop_count':   hop_limit,
        'ack':         0,
        'destination': dest,
        'is_dm':       bool(dest != '^all' and _local_id and dest == _local_id),
    }
    if _loop is not None:
        _loop.call_soon_threadsafe(_enqueue_event,typed_event)


def _build_log_summary(portnum: str, decoded: dict) -> str:
    """Build a short human-readable summary from a decoded packet."""
    try:
        if portnum == 'TELEMETRY_APP':
            t = decoded.get('telemetry', {})
            dm = t.get('deviceMetrics', {})
            em = t.get('environmentMetrics', {})
            parts = []
            if dm.get('batteryLevel') is not None:
                parts.append(f"batt {dm['batteryLevel']}%")
            if dm.get('voltage') is not None:
                parts.append(f"{dm['voltage']:.1f}V")
            if dm.get('channelUtilization') is not None:
                parts.append(f"ch {dm['channelUtilization']:.1f}%")
            if em.get('temperature') is not None:
                parts.append(f"{em['temperature']:.1f}°C")
            if em.get('relativeHumidity') is not None:
                parts.append(f"{em['relativeHumidity']:.0f}%RH")
            return ' · '.join(parts) if parts else ''
        elif portnum == 'POSITION_APP':
            pos = decoded.get('position', {})
            lat, lon = pos.get('latitude'), pos.get('longitude')
            alt = pos.get('altitude')
            if lat is not None and lon is not None:
                s = f"{lat:.4f}, {lon:.4f}"
                if alt is not None:
                    s += f" · {alt}m"
                return s
        elif portnum == 'NODEINFO_APP':
            user = decoded.get('user', {})
            name = user.get('longName') or user.get('shortName') or ''
            hw = user.get('hwModel', '')
            return f"{name} ({hw})" if hw else name
        elif portnum == 'TEXT_MESSAGE_APP':
            text = decoded.get('text', '')
            return text[:80] if text else ''
        elif portnum == 'ROUTING_APP':
            err = decoded.get('routing', {}).get('errorReason', 'NONE')
            return err if err != 'NONE' else 'ACK'
        elif portnum == 'TRACEROUTE_APP':
            hops = decoded.get('routeDiscovery', {}).get('route', [])
            return f"{len(hops)} hops" if hops else 'direct'
        elif portnum == 'WAYPOINT_APP':
            wp = decoded.get('waypoint', {})
            name = wp.get('name', '')
            return f"Waypoint: {name}" if name else 'Waypoint'
        elif portnum == 'NEIGHBORINFO_APP':
            neighbors = decoded.get('neighborinfo', {}).get('neighbors', [])
            return f"{len(neighbors)} neighbor(s)"
        elif portnum == 'DETECTION_SENSOR_APP':
            ds = decoded.get('detectionSensor', {})
            triggered = ds.get('triggered', False)
            name = ds.get('name', 'sensor')
            return f"{name}: triggered" if triggered else f"{name}: cleared"
        elif portnum == 'PAXCOUNTER_APP':
            px = decoded.get('paxcounter', {})
            return f"BLE: {px.get('ble', 0)} WiFi: {px.get('wifi', 0)}"
    except Exception:
        pass
    return ''


def _on_receive(packet, interface) -> None:
    from_id   = packet.get('fromId') or '?'
    portnum   = packet.get('decoded', {}).get('portnum', 'UNKNOWN')
    snr       = packet.get('rxSnr')
    hop_limit = packet.get('hopLimit')

    # Emit typed event based on portnum
    decoded = packet.get('decoded', {})

    # Build a human-readable summary for the log
    summary = _build_log_summary(portnum, decoded)

    # Always emit a log event
    log_event = {
        'type':      'log',
        'ts':        int(time.time()),
        'from':      from_id,
        'portnum':   portnum,
        'snr':       snr,
        'hop_limit': hop_limit,
        'summary':   summary,
    }
    _log_queue.append(log_event)
    if _loop is not None:
        _loop.call_soon_threadsafe(_enqueue_event,log_event)

    if portnum == 'NODEINFO_APP':
        user = decoded.get('user', {})
        typed_event = {
            'type':          'node',
            'id':            from_id,
            'short_name':    user.get('shortName', ''),
            'long_name':     user.get('longName', ''),
            'hw_model':      user.get('hwModel', ''),
            'last_heard':    int(time.time()),
            'snr':           snr,
            'hop_count':     hop_limit,
            'rssi':             packet.get('rxRssi'),
            'firmware_version': user.get('firmwareVersion'),
            'role':             user.get('role'),
            'public_key':       user.get('publicKey'),
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_enqueue_event,typed_event)

    elif portnum == 'POSITION_APP':
        pos = decoded.get('position', {})
        typed_event = {
            'type':       'position',
            'id':         from_id,
            'latitude':   pos.get('latitude'),
            'longitude':  pos.get('longitude'),
            'last_heard': int(time.time()),
            'altitude':   pos.get('altitude'),
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_enqueue_event,typed_event)

    elif portnum == 'TELEMETRY_APP' and from_id != '?':
        telemetry = decoded.get('telemetry', {})

        # Device metrics
        device_metrics = telemetry.get('deviceMetrics', {})
        if device_metrics:
            tdata = {
                'battery_level': device_metrics.get('batteryLevel'),
                'voltage': device_metrics.get('voltage'),
                'channel_utilization': device_metrics.get('channelUtilization'),
                'air_util_tx': device_metrics.get('airUtilTx'),
                'uptime_seconds': device_metrics.get('uptimeSeconds'),
            }
            typed_event = {
                'type': 'telemetry',
                'ttype': 'device',
                'id': from_id,
                'data': tdata,
            }
            if _loop is not None:
                _loop.call_soon_threadsafe(_enqueue_event,typed_event)
                fut = asyncio.run_coroutine_threadsafe(
                    database.save_telemetry(cfg.DB_PATH, from_id, 'device', tdata), _loop
                )
                fut.add_done_callback(
                    lambda f: logger.error('save_telemetry failed: %s', f.exception())
                    if f.exception() else None
                )

        # Environment metrics
        env_metrics = telemetry.get('environmentMetrics', {})
        if env_metrics:
            tdata = {
                'temperature': env_metrics.get('temperature'),
                'relative_humidity': env_metrics.get('relativeHumidity'),
                'barometric_pressure': env_metrics.get('barometricPressure'),
                'gas_resistance': env_metrics.get('gasResistance'),
                'iaq': env_metrics.get('iaq'),
            }
            typed_event = {
                'type': 'telemetry',
                'ttype': 'environment',
                'id': from_id,
                'data': tdata,
            }
            if _loop is not None:
                _loop.call_soon_threadsafe(_enqueue_event,typed_event)
                fut = asyncio.run_coroutine_threadsafe(
                    database.save_telemetry(cfg.DB_PATH, from_id, 'environment', tdata), _loop
                )
                fut.add_done_callback(
                    lambda f: logger.error('save_telemetry failed: %s', f.exception())
                    if f.exception() else None
                )

        # Power metrics
        power_metrics = telemetry.get('powerMetrics', {})
        if power_metrics:
            tdata = dict(power_metrics)
            typed_event = {
                'type': 'telemetry',
                'ttype': 'power',
                'id': from_id,
                'data': tdata,
            }
            if _loop is not None:
                _loop.call_soon_threadsafe(_enqueue_event,typed_event)
                fut = asyncio.run_coroutine_threadsafe(
                    database.save_telemetry(cfg.DB_PATH, from_id, 'power', tdata), _loop
                )
                fut.add_done_callback(
                    lambda f: logger.error('save_telemetry failed: %s', f.exception())
                    if f.exception() else None
                )

        # Air quality metrics
        air_quality = telemetry.get('airQualityMetrics', {})
        if air_quality:
            tdata = dict(air_quality)
            typed_event = {
                'type': 'telemetry',
                'ttype': 'air_quality',
                'id': from_id,
                'data': tdata,
            }
            if _loop is not None:
                _loop.call_soon_threadsafe(_enqueue_event,typed_event)
                fut = asyncio.run_coroutine_threadsafe(
                    database.save_telemetry(cfg.DB_PATH, from_id, 'air_quality', tdata), _loop
                )
                fut.add_done_callback(
                    lambda f: logger.error('save_telemetry failed: %s', f.exception())
                    if f.exception() else None
                )

    elif portnum == 'TRACEROUTE_APP':
        route_discovery = decoded.get('routeDiscovery', {})
        hops = route_discovery.get('route', [])
        _traceroute_cache[from_id] = {
            'node_id': from_id,
            'hops':    hops,
            'ts':      int(time.time()),
        }
        typed_event = {
            'type':    'traceroute_result',
            'node_id': from_id,
            'hops':    hops,
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_enqueue_event,typed_event)

    elif portnum == 'TEXT_MESSAGE_APP':
        text    = decoded.get('text', '')
        channel = int(packet.get('channel', 0))
        try:
            to_num = int(packet.get('to', 0xFFFFFFFF))
        except (TypeError, ValueError):
            to_num = 0xFFFFFFFF
        dest = '^all' if to_num == 0xFFFFFFFF else f'!{to_num:08x}'
        if _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                _save_incoming_message(from_id, channel, text, snr, hop_limit, dest),
                _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_incoming_message failed: %s', f.exception())
                if f.exception() else None
            )

    elif portnum == 'ROUTING_APP':
        error_reason = decoded.get('routing', {}).get('errorReason', 'NONE')
        if error_reason == 'NONE' and _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                database.update_message_ack(cfg.DB_PATH, from_id), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('update_message_ack failed: %s', f.exception())
                if f.exception() else None
            )
            ack_event = {'type': 'ack', 'node_id': from_id}
            _loop.call_soon_threadsafe(_enqueue_event,ack_event)

    elif portnum == 'WAYPOINT_APP':
        wp_raw = decoded.get('waypoint', {})
        lat = wp_raw.get('latitudeI', 0) / 1e7 if wp_raw.get('latitudeI') else None
        lon = wp_raw.get('longitudeI', 0) / 1e7 if wp_raw.get('longitudeI') else None
        wp = {
            'id':          wp_raw.get('id', int(time.time())),
            'name':        wp_raw.get('name', ''),
            'lat':         lat,
            'lon':         lon,
            'icon':        wp_raw.get('icon', 'default'),
            'description': wp_raw.get('description', ''),
            'expire':      wp_raw.get('expire', 0),
            'from_id':     from_id,
            'ts':          int(time.time()),
        }
        if lat is not None and lon is not None and _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                database.upsert_waypoint(wp), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('upsert_waypoint failed: %s', f.exception())
                if f.exception() else None
            )
            _loop.call_soon_threadsafe(_enqueue_event, {'type': 'waypoint', **wp})

    elif portnum == 'NEIGHBORINFO_APP':
        ni = decoded.get('neighborinfo', {})
        neighbors = ni.get('neighbors', [])
        for nb in neighbors:
            neighbor_id = f"!{nb.get('nodeId', 0):08x}"
            snr = float(nb.get('snr', 0.0))
            if _loop is not None:
                fut = asyncio.run_coroutine_threadsafe(
                    database.upsert_neighbor_info(from_id, neighbor_id, snr), _loop
                )
                fut.add_done_callback(
                    lambda f: logger.error('upsert_neighbor_info failed: %s', f.exception())
                    if f.exception() else None
                )
        typed_event = {
            'type':      'neighbor_info',
            'from_id':   from_id,
            'neighbors': [{'node_id': f"!{nb.get('nodeId',0):08x}", 'snr': float(nb.get('snr', 0.0))}
                          for nb in neighbors],
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_enqueue_event, typed_event)

    elif portnum == 'DETECTION_SENSOR_APP':
        ds = decoded.get('detectionSensor', {})
        data = {'triggered': ds.get('triggered', False), 'name': ds.get('name', '')}
        if _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                database.save_sensor_event(from_id, 'detection', data), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_sensor_event failed: %s', f.exception())
                if f.exception() else None
            )
            _loop.call_soon_threadsafe(_enqueue_event, {'type': 'sensor', 'from_id': from_id, 'data': data})

    elif portnum == 'PAXCOUNTER_APP':
        px = decoded.get('paxcounter', {})
        data = {'ble': px.get('ble', 0), 'wifi': px.get('wifi', 0)}
        if _loop is not None:
            fut = asyncio.run_coroutine_threadsafe(
                database.save_sensor_event(from_id, 'paxcounter', data), _loop
            )
            fut.add_done_callback(
                lambda f: logger.error('save_sensor_event failed: %s', f.exception())
                if f.exception() else None
            )
            _loop.call_soon_threadsafe(_enqueue_event, {'type': 'paxcounter', 'from_id': from_id, 'data': data})

    # Notify log subscribers
    failed = []
    for cb in list(_subscribers):
        try:
            cb(log_event)
        except Exception:
            failed.append(cb)
    for cb in failed:
        unsubscribe_log(cb)

    # Update rssi in node cache from incoming packet
    rx_rssi = packet.get('rxRssi')
    if rx_rssi is not None and from_id in _node_cache:
        _node_cache[from_id]['rssi'] = rx_rssi
        _dirty_nodes.add(from_id)

    # Node cache is refreshed via TTL in get_nodes() and every 30s in connect()


async def _flush_dirty(db_path: str) -> None:
    """Write all dirty nodes to SQLite and clear the dirty set."""
    if not _dirty_nodes:
        return
    nodes_to_flush = [_node_cache[nid] for nid in list(_dirty_nodes) if nid in _node_cache]
    await database.bulk_upsert_nodes(db_path, nodes_to_flush)
    _dirty_nodes.clear()
    logger.debug(f'Flushed {len(nodes_to_flush)} dirty nodes to DB')


async def _flush_task() -> None:
    """Background task: persist dirty nodes to SQLite every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        try:
            await _flush_dirty(cfg.DB_PATH)
        except Exception as e:
            logger.warning(f'Flush task error: {e}')


async def load_nodes_from_db(db_path: str | None = None) -> None:
    """Populate _node_cache from SQLite at startup before board connects."""
    path = db_path or cfg.DB_PATH
    rows = await database.get_all_nodes(path)
    for row in rows:
        _node_cache[row['id']] = row
    logger.info(f'Loaded {len(rows)} nodes from DB into cache')


def _do_factory_reset() -> None:
    """Sync helper — factory reset the node."""
    if _interface:
        _interface.localNode.setOwner('')  # reset owner
        _interface.localNode.beginSettingsTransaction()
        _interface.localNode.commitSettingsTransaction()
        logger.warning('Factory reset executed')


async def factory_reset() -> None:
    """Queue factory reset command."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    await _command_queue.put(_do_factory_reset)


async def _command_worker() -> None:
    """Consume commands from _command_queue and execute them serially via executor."""
    loop = asyncio.get_running_loop()
    while True:
        cmd_fn = await _command_queue.get()
        try:
            await loop.run_in_executor(None, cmd_fn)
        except Exception as e:
            logger.warning(f'Command execution failed: {e}')
        finally:
            _command_queue.task_done()


async def connect() -> None:
    global _interface, _connected, _is_connecting, _local_id, _loop
    if _is_connecting:
        return
    _is_connecting = True
    import meshtastic.serial_interface
    from pubsub import pub
    _loop = asyncio.get_event_loop()    # capture event loop for threadsafe callbacks
    asyncio.create_task(_command_worker())
    asyncio.create_task(_flush_task())
    backoff = 15
    pub.subscribe(_on_receive, 'meshtastic.receive')
    while True:
        try:
            logger.warning(f'Connecting to board at {cfg.SERIAL_PATH}')
            if cfg.SERIAL_PATH.startswith('tcp://'):
                # meshtasticd (LoRa HAT nativo sul Pi) o board remota:
                # SERIAL_PATH=tcp://host[:porta], default porta 4403.
                import meshtastic.tcp_interface
                host, _, port = cfg.SERIAL_PATH[6:].partition(':')
                _interface = meshtastic.tcp_interface.TCPInterface(
                    host, portNumber=int(port or 4403))
            else:
                _interface = meshtastic.serial_interface.SerialInterface(cfg.SERIAL_PATH)
            _connected = True
            backoff = 15
            logger.warning(f'Connected to board at {cfg.SERIAL_PATH}')
            # Wait for myInfo to be populated before reading local ID
            await asyncio.sleep(3)
            _local_id = f'!{_interface.localNode.nodeNum:08x}'
            logger.warning(f'Local node ID: {_local_id}')
            # La board collegata detta il nodo locale: azzera il flag
            # is_local persistito da eventuali board precedenti, altrimenti
            # la UI continuerebbe a mostrare come locale il nodo vecchio.
            await database.set_local_node(cfg.DB_PATH, _local_id)
            # Keep alive — poll every 30s
            while _connected:
                _refresh_node_cache()
                await asyncio.sleep(30)
        except Exception as e:
            _connected = False
            logger.warning(f'Board connection failed: {e}. Retry in {backoff}s')
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


async def disconnect() -> None:
    global _connected, _interface
    await _flush_dirty(cfg.DB_PATH)   # flush pending nodes before shutdown
    _connected = False
    if _interface:
        try:
            _interface.close()
        except Exception:
            pass
        _interface = None
