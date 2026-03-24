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
