import asyncio, gc, logging, os, signal
import database, meshtastic_client
import config as cfg

async def db_sync_task(conn, interval: int = None):
    interval = interval or cfg.DB_SYNC_INTERVAL
    while True:
        await asyncio.sleep(interval)
        await database.sync_to_sd(conn)
        logging.debug("DB sincronizzato su SD")

async def connection_watchdog_task(broadcast_fn, interval: int = 30):
    while True:
        await asyncio.sleep(interval)
        if not meshtastic_client.is_connected():
            logging.warning("Connessione persa, tentativo reconnect...")
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
            gc.collect()
        if rss_mb > 150:
            logging.error(f"RAM critica: {rss_mb:.1f}MB — riavvio")
            await broadcast_fn({"type": "status", "data": {"warning": "riavvio per memoria"}})
            await asyncio.sleep(2)
            os.kill(os.getpid(), signal.SIGTERM)

async def meshtastic_telemetry_poll_task(conn, broadcast_fn, interval: int = 60):
    """Legge deviceMetrics dal nodo locale e telemetria Pi ogni `interval` secondi."""
    import time, database
    while True:
        await asyncio.sleep(interval)
        # --- Board Meshtastic ---
        try:
            iface = meshtastic_client._interface
            if iface and meshtastic_client.is_connected():
                # Usa l'ID reale del nodo locale
                local_id = None
                try:
                    my_info  = iface.getMyNodeInfo()
                    local_id = my_info.get("user", {}).get("id")
                except Exception:
                    pass
                if local_id:
                    nodes = iface.nodes or {}
                    local = nodes.get(local_id) or next((v for v in nodes.values() if v.get("user", {}).get("id") == local_id), None)
                    if local:
                        met = local.get("deviceMetrics", {})
                        if met:
                            await database.save_telemetry(conn, local_id, "deviceMetrics", dict(met))
                            await broadcast_fn({"type": "telemetry", "data": {
                                "node_id": local_id, "type": "deviceMetrics", "values": dict(met)
                            }})
        except Exception as e:
            logging.debug(f"meshtastic_poll: {e}")

        # --- Sistema Raspberry Pi ---
        try:
            import resource, time as _time
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            pi_met = {"ram_mb": round(rss_mb, 1)}
            # Temperatura CPU
            temp_path = "/sys/class/thermal/thermal_zone0/temp"
            if os.path.exists(temp_path):
                with open(temp_path) as f:
                    pi_met["cpu_temp_c"] = round(int(f.read().strip()) / 1000, 1)
            # Spazio disco
            st = os.statvfs(".")
            pi_met["disk_free_mb"]  = round(st.f_bavail * st.f_frsize / 1024 / 1024, 1)
            pi_met["disk_total_mb"] = round(st.f_blocks * st.f_frsize / 1024 / 1024, 1)
            await database.save_telemetry(conn, "pi", "systemMetrics", pi_met)
            await broadcast_fn({"type": "telemetry", "data": {
                "node_id": "pi", "type": "systemMetrics", "values": pi_met
            }})
        except Exception as e:
            logging.debug(f"pi_telemetry: {e}")


async def db_maintenance_task(conn, interval: int = 3600):
    while True:
        await asyncio.sleep(interval)
        await database.prune_telemetry(conn)
        await database.prune_sensor_readings(conn)
        await conn.execute("PRAGMA incremental_vacuum")
        await conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        logging.debug("Manutenzione DB completata")

def start_all(conn, broadcast_fn):
    loop = asyncio.get_event_loop()
    loop.create_task(db_sync_task(conn))
    loop.create_task(connection_watchdog_task(broadcast_fn))
    loop.create_task(memory_watchdog_task(broadcast_fn))
    loop.create_task(db_maintenance_task(conn))
    loop.create_task(meshtastic_telemetry_poll_task(conn, broadcast_fn))
