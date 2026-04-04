# meshtasticd_client.py
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
_event_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
_loop: asyncio.AbstractEventLoop | None = None
_traceroute_cache: dict[str, dict] = {}
_command_queue: asyncio.Queue = asyncio.Queue()

import config as cfg
import database


def _enqueue_event(event: dict) -> None:
    """Thread-safe enqueue to _event_queue, dropping if full."""
    try:
        _event_queue.put_nowait(event)
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


def get_event_queue() -> asyncio.Queue:
    return _event_queue


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
                return {
                    'long_name': _interface.getLongName(),
                    'short_name': _interface.getShortName(),
                    'role': dc.Role.Name(dc.role),
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


def _do_set_node_config(long_name: str, short_name: str, role: str) -> None:
    """Sync helper — runs in command queue thread."""
    _interface.localNode.setOwner(long_name, short_name)
    from meshtastic.protobuf import config_pb2
    role_val = config_pb2.Config.DeviceConfig.Role.Value(role)
    dev_cfg = config_pb2.Config.DeviceConfig(role=role_val)
    _interface.localNode.setConfig(config_pb2.Config(device=dev_cfg))


async def set_node_config(long_name: str, short_name: str, role: str) -> None:
    """Queue node config write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _ln, _sn, _r = long_name, short_name, role
    await _command_queue.put(lambda: _do_set_node_config(_ln, _sn, _r))


def _do_set_lora_config(region: str, preset: str) -> None:
    """Sync helper — runs in command queue thread."""
    from meshtastic.protobuf import config_pb2
    region_val = config_pb2.Config.LoRaConfig.RegionCode.Value(region)
    preset_val = config_pb2.Config.LoRaConfig.ModemPreset.Value(preset)
    lora_cfg = config_pb2.Config.LoRaConfig(region=region_val, modem_preset=preset_val)
    _interface.localNode.setConfig(config_pb2.Config(lora=lora_cfg))


async def set_lora_config(region: str, preset: str) -> None:
    """Queue LoRa config write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _r, _p = region, preset
    await _command_queue.put(lambda: _do_set_lora_config(_r, _p))


def _do_set_mqtt_config(params: dict) -> None:
    """Sync helper — runs in command queue thread."""
    from meshtastic.protobuf import module_config_pb2
    mqtt_cfg = module_config_pb2.ModuleConfig.MQTTConfig(
        enabled=params.get('enabled', False),
        address=params.get('address', ''),
        username=params.get('username', ''),
        password=params.get('password', ''),
        encryption_enabled=params.get('encryption_enabled', False),
        json_enabled=params.get('json_enabled', False),
        tls_enabled=params.get('tls_enabled', False),
        root=params.get('root', ''),
        proxy_to_client_enabled=params.get('proxy_to_client_enabled', False),
        map_reporting_enabled=params.get('map_reporting_enabled', False),
    )
    _interface.localNode.setConfig(
        module_config_pb2.ModuleConfig(mqtt=mqtt_cfg)
    )


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.ExternalNotificationConfig(
        enabled=params.get('enabled', False),
        output_pin=params.get('output_pin', 0),
        active_high=params.get('active_high', False),
        alert_message=params.get('alert_message', False),
        alert_bell=params.get('alert_bell', False),
        use_pwm=params.get('use_pwm', False),
        nag_timeout=params.get('nag_timeout', 0),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(external_notification=cfg))


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.StoreAndForwardConfig(
        enabled=params.get('enabled', False),
        heartbeat=params.get('heartbeat', False),
        history_return_max=params.get('history_return_max', 0),
        history_return_window=params.get('history_return_window', 0),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(store_forward=cfg))


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.TelemetryConfig(
        device_update_interval=params.get('device_update_interval', 0),
        environment_update_interval=params.get('environment_update_interval', 0),
        environment_measurement_enabled=params.get('environment_measurement_enabled', False),
        air_quality_enabled=params.get('air_quality_enabled', False),
        power_measurement_enabled=params.get('power_measurement_enabled', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(telemetry=cfg))


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.CannedMessageConfig(
        rotary1_enabled=params.get('rotary1_enabled', False),
        send_bell=params.get('send_bell', False),
        free_text_sms_enabled=params.get('free_text_sms_enabled', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(canned_message=cfg))


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.RangeTestConfig(
        enabled=params.get('enabled', False),
        sender=params.get('sender', 0),
        save=params.get('save', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(range_test=cfg))


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.DetectionSensorConfig(
        enabled=params.get('enabled', False),
        minimum_broadcast_secs=params.get('minimum_broadcast_secs', 0),
        state_broadcast_secs=params.get('state_broadcast_secs', 0),
        name=params.get('name', ''),
        monitor_pin=params.get('monitor_pin', 0),
        use_pullup=params.get('use_pullup', False),
        detection_triggered_high=params.get('detection_triggered_high', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(detection_sensor=cfg))


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.AmbientLightingConfig(
        led_state=params.get('led_state', False),
        current=params.get('current', 0),
        red=params.get('red', 0),
        green=params.get('green', 0),
        blue=params.get('blue', 0),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(ambient_lighting=cfg))


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
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.NeighborInfoConfig(
        enabled=params.get('enabled', False),
        update_interval=params.get('update_interval', 0),
        transmit_over_lora=params.get('transmit_over_lora', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(neighbor_info=cfg))


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
    cfg = module_config_pb2.ModuleConfig.SerialConfig(
        enabled=params.get('enabled', False),
        echo=params.get('echo', False),
        rxd=params.get('rxd', 0),
        txd=params.get('txd', 0),
        timeout=params.get('timeout', 0),
        mode=mode_val,
        override_console_serial_port=params.get('override_console_serial_port', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(serial=cfg))


async def set_serial_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_serial_module_config(_p))


def _do_set_channel(idx: int, name: str, psk_b64: str) -> None:
    """Sync helper — runs in command queue thread."""
    import base64
    ch = _interface.localNode.channels[idx]
    ch.settings.name = name
    if psk_b64:
        ch.settings.psk = base64.b64decode(psk_b64)
    _interface.localNode.writeChannel(idx)


async def set_channel(idx: int, name: str, psk_b64: str) -> None:
    """Queue channel write. Raises if board not connected."""
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _i, _n, _p = idx, name, psk_b64
    await _command_queue.put(lambda: _do_set_channel(_i, _n, _p))


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
        'node_id':     from_id,
        'channel':     channel,
        'text':        text,
        'ts':          now,
        'is_outgoing': False,
        'rx_snr':      snr,
        'hop_count':   hop_limit,
        'ack':         0,
        'destination': dest,
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
            _interface = meshtastic.serial_interface.SerialInterface(cfg.SERIAL_PATH)
            _connected = True
            backoff = 15
            logger.warning(f'Connected to board at {cfg.SERIAL_PATH}')
            # Wait for myInfo to be populated before reading local ID
            await asyncio.sleep(3)
            _local_id = f'!{_interface.localNode.nodeNum:08x}'
            logger.warning(f'Local node ID: {_local_id}')
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
