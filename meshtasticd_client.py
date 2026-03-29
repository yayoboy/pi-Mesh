# meshtasticd_client.py
import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

# --- State ---
_interface      = None
_connected      = False
_local_id: str  = ''
_node_cache: dict[str, dict] = {}
_last_node_fetch: float = 0.0
_log_queue: deque = deque(maxlen=500)
_subscribers: list = []

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


# --- Internal ---

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
            }
        _last_node_fetch = time.time()
    except Exception as e:
        logger.warning(f'Node cache refresh failed: {e}')


def _on_receive(packet, interface) -> None:
    entry = {
        'ts':          int(time.time()),
        'from':        packet.get('fromId', '?'),
        'type':        packet.get('decoded', {}).get('portnum', 'UNKNOWN'),
        'snr':         packet.get('rxSnr'),
        'hop_limit':   packet.get('hopLimit'),
    }
    _log_queue.append(entry)
    failed = []
    for cb in list(_subscribers):
        try:
            cb(entry)
        except Exception:
            failed.append(cb)
    for cb in failed:
        unsubscribe_log(cb)
    # Refresh node cache on any packet
    if _connected and _interface:
        _refresh_node_cache()


async def connect() -> None:
    global _interface, _connected, _local_id
    import meshtastic.serial_interface
    from pubsub import pub
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
