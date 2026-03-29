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
_local_id: str  = ''
_node_cache: dict[str, dict] = {}
_dirty_nodes: set[str] = set()
_last_node_fetch: float = 0.0
_log_queue: deque = deque(maxlen=500)
_subscribers: list = []
_event_queue: asyncio.Queue = asyncio.Queue()
_loop: asyncio.AbstractEventLoop | None = None
_traceroute_cache: dict[str, dict] = {}
_command_queue: asyncio.Queue = asyncio.Queue()

import config as cfg
import database

NODE_CACHE_TTL = cfg.NODE_CACHE_TTL


# --- Public API ---

def is_connected() -> bool:
    return _connected


def get_nodes() -> list[dict]:
    """Return cached node list. Refreshes from interface if TTL expired."""
    global _node_cache, _last_node_fetch
    if _connected and _interface and (time.time() - _last_node_fetch) > NODE_CACHE_TTL:
        _refresh_node_cache()
    return list(_node_cache.values())


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
                lc = _interface.localNode.localConfig.device
                return {
                    'long_name': lc.long_name,
                    'short_name': lc.short_name,
                    'role': lc.Role.Name(lc.role),
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
        _node_cache = {}
        for node_id, info in raw.items():
            user = info.get('user', {})
            pos  = info.get('position', {})
            metrics = info.get('deviceMetrics', {})
            _node_cache[node_id] = {
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
            }
        _dirty_nodes.update(_node_cache.keys())
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
        _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)


def _on_receive(packet, interface) -> None:
    from_id   = packet.get('fromId', '?')
    portnum   = packet.get('decoded', {}).get('portnum', 'UNKNOWN')
    snr       = packet.get('rxSnr')
    hop_limit = packet.get('hopLimit')

    # Always emit a log event
    log_event = {
        'type':      'log',
        'ts':        int(time.time()),
        'from':      from_id,
        'portnum':   portnum,
        'snr':       snr,
        'hop_limit': hop_limit,
    }
    _log_queue.append(log_event)
    if _loop is not None:
        _loop.call_soon_threadsafe(_event_queue.put_nowait, log_event)

    # Emit typed event based on portnum
    decoded = packet.get('decoded', {})

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
            'battery_level': None,
            'latitude':      None,
            'longitude':     None,
            'is_local':      False,
            'distance_km':   None,
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)

    elif portnum == 'POSITION_APP':
        pos = decoded.get('position', {})
        typed_event = {
            'type':       'position',
            'id':         from_id,
            'latitude':   pos.get('latitude'),
            'longitude':  pos.get('longitude'),
            'last_heard': int(time.time()),
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)

    elif portnum == 'TELEMETRY_APP':
        telemetry = decoded.get('telemetry', {})
        device_metrics = telemetry.get('deviceMetrics', {})
        typed_event = {
            'type':          'telemetry',
            'id':            from_id,
            'battery_level': device_metrics.get('batteryLevel'),
            'snr':           snr,
        }
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)

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
            _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)

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
            _loop.call_soon_threadsafe(_event_queue.put_nowait, ack_event)

    # Notify log subscribers
    failed = []
    for cb in list(_subscribers):
        try:
            cb(log_event)
        except Exception:
            failed.append(cb)
    for cb in failed:
        unsubscribe_log(cb)

    # Refresh node cache on any packet
    if _connected and _interface:
        _refresh_node_cache()


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
    global _interface, _connected, _local_id, _loop
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
