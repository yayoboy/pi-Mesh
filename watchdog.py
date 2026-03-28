import asyncio, gc, logging, os, signal, time
from collections import deque
import database, meshtastic_client
import config as cfg

_pi_log: deque = deque(maxlen=300)
_broadcast_fn = None

def _pi_log_event(level: str, msg: str):
    entry = {"ts": int(time.time()), "level": level, "msg": msg}
    _pi_log.append(entry)
    if _broadcast_fn:
        asyncio.get_event_loop().call_soon_threadsafe(
            lambda e=entry: asyncio.ensure_future(
                _broadcast_fn({"type": "log", "data": {**e, "source": "pi"}})
            )
        )

def get_pi_log() -> list:
    return list(_pi_log)

async def db_sync_task(conn, interval: int = None):
    interval = interval or cfg.DB_SYNC_INTERVAL
    while True:
        await asyncio.sleep(interval)
        await database.sync_to_sd(conn)
        _pi_log_event("info", "DB sincronizzato su SD")
        logging.debug("DB sincronizzato su SD")

async def connection_watchdog_task(broadcast_fn, interval: int = 30):
    while True:
        await asyncio.sleep(interval)
        if not meshtastic_client.is_connected():
            logging.warning("Connessione persa, tentativo reconnect...")
            _pi_log_event("warn", "Connessione Meshtastic persa — tentativo reconnect")
            await meshtastic_client.connect()
            await broadcast_fn({"type": "status", "data": {
                "connected": meshtastic_client.is_connected()
            }})

async def memory_watchdog_task(broadcast_fn, interval: int = 60):
    import resource
    while True:
        await asyncio.sleep(interval)
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = rss_kb / 1024
        if rss_mb > 120:
            logging.warning(f"RAM alta: {rss_mb:.1f}MB")
            _pi_log_event("warn", f"RAM alta: {rss_mb:.1f}MB — GC eseguito")
            gc.collect()
        if rss_mb > 150:
            logging.error(f"RAM critica: {rss_mb:.1f}MB — riavvio")
            _pi_log_event("error", f"RAM critica: {rss_mb:.1f}MB — riavvio in corso")
            await broadcast_fn({"type": "status", "data": {"warning": "riavvio per memoria"}})
            await asyncio.sleep(2)
            os.kill(os.getpid(), signal.SIGTERM)

async def pi_telemetry_task(conn, broadcast_fn, broadcast_interval: int = 10, db_interval: int = 60):
    """Campiona metriche Pi ogni broadcast_interval secondi; salva su DB ogni db_interval secondi."""
    import resource
    _db_counter = 0
    first_run = True
    while True:
        if not first_run:
            await asyncio.sleep(broadcast_interval)
        first_run = False
        try:
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            pi_met = {"ram_mb": round(rss_mb, 1)}

            def _read_disk_temp():
                result = {}
                temp_path = "/sys/class/thermal/thermal_zone0/temp"
                if os.path.exists(temp_path):
                    with open(temp_path) as f:
                        result["cpu_temp_c"] = round(int(f.read().strip()) / 1000, 1)
                st = os.statvfs(".")
                result["disk_free_mb"]  = round(st.f_bavail * st.f_frsize / 1024 / 1024, 1)
                result["disk_total_mb"] = round(st.f_blocks * st.f_frsize / 1024 / 1024, 1)
                return result

            pi_met.update(await asyncio.to_thread(_read_disk_temp))
            await broadcast_fn({"type": "telemetry", "data": {
                "node_id": "pi", "type": "systemMetrics", "values": pi_met
            }})
            _db_counter += broadcast_interval
            if _db_counter >= db_interval:
                await database.save_telemetry(conn, "pi", "systemMetrics", pi_met)
                _db_counter = 0
        except Exception as e:
            logging.debug(f"pi_telemetry: {e}")


async def board_telemetry_task(conn, broadcast_fn, interval: int = 30):
    """Legge deviceMetrics dal nodo Meshtastic locale ogni interval secondi."""
    import database
    _last_met = None
    first_run = True
    while True:
        if not first_run:
            await asyncio.sleep(interval)
        first_run = False
        try:
            iface = meshtastic_client._interface
            if not (iface and meshtastic_client.is_connected()):
                continue
            local_id = None
            try:
                info = await asyncio.to_thread(iface.getMyNodeInfo)
                local_id = info.get("user", {}).get("id")
            except Exception:
                pass
            if not local_id:
                continue
            nodes = dict(iface.nodes or {})
            local = nodes.get(local_id) or next(
                (v for v in nodes.values() if v.get("user", {}).get("id") == local_id), None)
            if not local:
                continue
            met = local.get("deviceMetrics", {})
            if not met:
                continue
            met_snapshot = dict(met)
            await broadcast_fn({"type": "telemetry", "data": {
                "node_id": local_id, "type": "deviceMetrics", "values": met_snapshot
            }})
            if met_snapshot != _last_met:
                await database.save_telemetry(conn, local_id, "deviceMetrics", met_snapshot)
                _last_met = met_snapshot
        except Exception as e:
            logging.debug(f"board_telemetry: {e}")


async def db_maintenance_task(conn, interval: int = 3600):
    while True:
        await asyncio.sleep(interval)
        await database.prune_telemetry(conn)
        await database.prune_sensor_readings(conn)
        await conn.execute("PRAGMA incremental_vacuum")
        await conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        logging.debug("Manutenzione DB completata")

def start_all(conn, broadcast_fn):
    global _broadcast_fn
    _broadcast_fn = broadcast_fn
    _pi_log_event("info", "Sistema avviato")
    loop = asyncio.get_event_loop()
    loop.create_task(db_sync_task(conn))
    loop.create_task(connection_watchdog_task(broadcast_fn))
    loop.create_task(memory_watchdog_task(broadcast_fn))
    loop.create_task(db_maintenance_task(conn))
    loop.create_task(pi_telemetry_task(conn, broadcast_fn))
    loop.create_task(board_telemetry_task(conn, broadcast_fn))
