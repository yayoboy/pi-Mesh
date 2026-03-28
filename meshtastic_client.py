import asyncio, glob, logging, os, time
from collections import deque

try:
    from pubsub import pub
    import meshtastic.serial_interface
    _MESHTASTIC_AVAILABLE = True
except ImportError:
    logging.warning("meshtastic non disponibile — client disabilitato")
    _MESHTASTIC_AVAILABLE = False
    class _PubStub:
        AUTO_TOPIC = None
        def subscribe(self, *a, **kw): pass
        def unsubscribe(self, *a, **kw): pass
    pub = _PubStub()

import config as cfg

_interface     = None
_loop          = None
_broadcast     = None
_connected     = False
_is_connecting = False
_conn_getter   = None
_shutdown      = False

# Ring buffer eventi board per tab Log
_board_log: deque = deque(maxlen=300)

def _log_event(level: str, msg: str):
    _board_log.append({"ts": int(time.time()), "level": level, "msg": msg})

def get_board_log() -> list:
    return list(_board_log)

def _find_serial_port() -> str:
    """Auto-rileva porta seriale Meshtastic. Prova porta configurata, poi scansiona ttyACM*/ttyUSB*."""
    if cfg.SERIAL_PORT and os.path.exists(cfg.SERIAL_PORT):
        return cfg.SERIAL_PORT
    candidates = sorted(glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*'))
    if candidates:
        logging.info(f"Auto-rilevato porta seriale: {candidates[0]} (disponibili: {candidates})")
        _log_event("info", f"Auto-rilevato porta: {candidates[0]}")
        return candidates[0]
    logging.warning(f"Nessuna porta seriale trovata, uso configurazione: {cfg.SERIAL_PORT}")
    return cfg.SERIAL_PORT

def init(loop, broadcast_fn, conn_getter=None):
    global _loop, _broadcast, _conn_getter
    _loop        = loop
    _broadcast   = broadcast_fn
    _conn_getter = conn_getter
    if not _MESHTASTIC_AVAILABLE:
        return
    pub.subscribe(_on_receive_text,      "meshtastic.receive.text")
    pub.subscribe(_on_receive_telemetry, "meshtastic.receive.telemetry")
    pub.subscribe(_on_receive_position,  "meshtastic.receive.position")
    pub.subscribe(_on_receive_user,      "meshtastic.receive.user")
    pub.subscribe(_on_connected,         "meshtastic.connection.established")
    pub.subscribe(_on_lost,              "meshtastic.connection.lost")

def _bridge(coro):
    if _loop and not _loop.is_closed():
        fut = asyncio.run_coroutine_threadsafe(coro, _loop)
        def _bridge_cb(f):
            if not f.cancelled():
                exc = f.exception()
                if exc:
                    logging.error("_bridge error", exc_info=exc)
        fut.add_done_callback(_bridge_cb)

async def connect():
    global _interface, _connected, _is_connecting
    if _is_connecting or _connected:
        return
    if not _MESHTASTIC_AVAILABLE:
        logging.warning("meshtastic non disponibile, connect() no-op")
        return
    _is_connecting = True
    try:
        while not _shutdown:
            port = _find_serial_port()
            try:
                _log_event("info", f"Tentativo connessione su {port}...")
                _interface = meshtastic.serial_interface.SerialInterface(port)
                _connected = True
                _log_event("info", f"Connesso a {port}")
                logging.info(f"Connesso a {port}")
                return
            except Exception as e:
                _connected = False
                _log_event("warn", f"Connessione fallita ({e}), riprovo in 10s...")
                logging.warning(f"Connessione fallita ({e}), riprovo in 10s...")
                await asyncio.sleep(10)
    finally:
        _is_connecting = False

async def disconnect():
    global _interface, _connected, _shutdown
    _shutdown = True
    if _interface:
        try:
            _interface.close()
        except Exception:
            pass
        _interface = None
    _connected = False
    _log_event("info", "Disconnesso dal dispositivo")

def is_connected() -> bool:
    return _connected

def get_local_node():
    iface = _interface
    if not iface:
        return None
    try:
        info = iface.getMyNodeInfo()
        return {
            "id":         info.get("user", {}).get("id"),
            "long_name":  info.get("user", {}).get("longName"),
            "short_name": info.get("user", {}).get("shortName"),
            "hw_model":   info.get("user", {}).get("hwModel"),
        }
    except Exception:
        return None

async def send_message(text: str, channel: int = 0, destination: str = "^all"):
    iface = _interface
    if not iface:
        raise RuntimeError("Non connesso")
    await asyncio.to_thread(iface.sendText, text, channelIndex=channel, destinationId=destination)

async def set_config(config_dict: dict):
    iface = _interface
    if not iface:
        raise RuntimeError("Non connesso")
    node = await asyncio.to_thread(iface.getNode, '^local')
    for section, values in config_dict.items():
        cfg_section = getattr(node.localConfig, section, None)
        if cfg_section is None:
            cfg_section = getattr(node.moduleConfig, section, None)
        if cfg_section:
            for k, v in values.items():
                setattr(cfg_section, k, v)
            await asyncio.to_thread(node.writeConfig, section)

async def request_position(node_id: str):
    iface = _interface
    if iface:
        await asyncio.to_thread(iface.sendPosition, destinationId=node_id)

# --- Callback pubsub (thread separati) ---

def _on_connected(interface, topic=None):
    global _connected
    _connected = True
    _log_event("info", "Connessione Meshtastic stabilita")
    _bridge(_sync_nodes(interface))

async def _sync_nodes(interface):
    import database
    await _broadcast({"type": "status", "data": {"connected": True}})
    try:
        # Determina l'ID del nodo locale in modo affidabile
        local_id = None
        try:
            my_info = interface.getMyNodeInfo()
            local_id = my_info.get("user", {}).get("id")
        except Exception:
            pass

        nodes_dict = interface.nodes or {}
        for node_id, info in nodes_dict.items():
            user = info.get("user", {})
            pos  = info.get("position", {})
            met  = info.get("deviceMetrics", {})
            nid  = user.get("id") or (info.get("num") and f"!{info['num']:08x}") or node_id
            node = {
                "id":            nid,
                "long_name":     user.get("longName", ""),
                "short_name":    user.get("shortName", ""),
                "hw_model":      user.get("hwModel", ""),
                "battery_level": met.get("batteryLevel"),
                "voltage":       met.get("voltage"),
                "snr":           info.get("snr"),
                "last_heard":    info.get("lastHeard", int(time.time())),
                "latitude":      pos.get("latitudeI", 0) / 1e7 if pos.get("latitudeI") else None,
                "longitude":     pos.get("longitudeI", 0) / 1e7 if pos.get("longitudeI") else None,
                "altitude":      pos.get("altitude"),
                "is_local":      1 if local_id and nid == local_id else 0,
            }
            conn = _conn_getter() if _conn_getter else None
            if conn:
                await database.save_node(conn, node)
            await _broadcast({"type": "node", "data": node})
    except Exception as e:
        logging.error(f"_sync_nodes fallito: {e}")

def _on_lost(interface, topic=None):
    global _connected
    _connected = False
    _log_event("warn", "Connessione Meshtastic persa")
    _bridge(_broadcast({"type": "status", "data": {"connected": False}}))

def _on_receive_text(packet, interface):
    _bridge(_handle_message(packet))

async def _handle_message(packet):
    import database
    data = _parse_message(packet)
    if data and _conn_getter:
        await database.save_message(_conn_getter(), **data)
    if data:
        _log_event("info", f"Messaggio da {data['node_id']}: {data['text'][:60]}")
        await _broadcast({"type": "message", "data": data})
        try:
            import gpio_handler
            gpio_handler.beep("single")
        except Exception:
            pass

def _on_receive_user(packet, interface):
    _bridge(_handle_user(packet))

async def _handle_user(packet):
    import database
    try:
        user = packet.get("decoded", {}).get("user", {})
        node = {
            "id":            packet.get("fromId", "unknown"),
            "long_name":     user.get("longName", ""),
            "short_name":    user.get("shortName", ""),
            "hw_model":      user.get("hwModel", ""),
            "battery_level": None,
            "voltage":       None,
            "snr":           packet.get("rxSnr"),
            "last_heard":    packet.get("rxTime", int(time.time())),
            "latitude":      None,
            "longitude":     None,
            "altitude":      None,
            "is_local":      0,
        }
        if _conn_getter:
            await database.save_node(_conn_getter(), node)
        await _broadcast({"type": "node", "data": node})
        try:
            import gpio_handler
            gpio_handler.beep("double")
        except Exception:
            pass
    except Exception as e:
        logging.error(f"Parsing user fallito: {e}")

def _on_receive_position(packet, interface):
    _bridge(_handle_position(packet))

async def _handle_position(packet):
    try:
        pos = packet.get("decoded", {}).get("position", {})
        data = {
            "node_id":   packet.get("fromId", "unknown"),
            "latitude":  pos.get("latitudeI", 0) / 1e7 if pos.get("latitudeI") else None,
            "longitude": pos.get("longitudeI", 0) / 1e7 if pos.get("longitudeI") else None,
            "altitude":  pos.get("altitude"),
        }
        await _broadcast({"type": "position", "data": data})
    except Exception as e:
        logging.error(f"Parsing position fallito: {e}")

def _on_receive_telemetry(packet, interface):
    _bridge(_handle_telemetry(packet))

async def _handle_telemetry(packet):
    import database
    try:
        telem   = packet.get("decoded", {}).get("telemetry", {})
        node_id = packet.get("fromId", "unknown")
        for type_ in ("deviceMetrics", "environmentMetrics", "powerMetrics"):
            values = telem.get(type_)
            if values and _conn_getter:
                await database.save_telemetry(_conn_getter(), node_id, type_, dict(values))
                await _broadcast({"type": "telemetry", "data": {
                    "node_id": node_id, "type": type_, "values": dict(values)
                }})
    except Exception as e:
        logging.error(f"Parsing telemetry fallito: {e}")

def _parse_message(packet) -> dict | None:
    try:
        decoded = packet.get("decoded", {})
        return {
            "node_id":     packet.get("fromId", "unknown"),
            "channel":     packet.get("channel", 0),
            "text":        decoded.get("text", ""),
            "timestamp":   packet.get("rxTime", int(time.time())),
            "is_outgoing": 0,
            "snr":         packet.get("rxSnr"),
            "rssi":        packet.get("rxRssi"),
        }
    except Exception as e:
        logging.error(f"Parsing messaggio fallito: {e}")
        return None
