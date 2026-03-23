# sensor_handler.py — stub (implementato in M3-S2)
import asyncio

def init(sensors_config: list) -> list:
    """Inizializza driver sensori I2C. Ritorna lista driver."""
    return []

async def start_polling(drivers: list, conn, broadcast_fn):
    """Polling asincrono sensori. No-op se nessun driver."""
    while True:
        await asyncio.sleep(60)

async def get_latest(sensor_name: str) -> dict:
    return {}
