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

import config as cfg

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


async def connect() -> None:
    global _interface, _connected, _local_id, _loop
    import meshtastic.serial_interface
    from pubsub import pub
    _loop = asyncio.get_event_loop()    # capture event loop for threadsafe callbacks
    backoff = 15
    while True:
        try:
            logger.warning(f'Connecting to board at {cfg.SERIAL_PATH}')
            _interface = meshtastic.serial_interface.SerialInterface(cfg.SERIAL_PATH)
            pub.subscribe(_on_receive, 'meshtastic.receive')
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
    _connected = False
    if _interface:
        try:
            _interface.close()
        except Exception:
            pass
        _interface = None
