import asyncio, logging, time

try:
    import smbus2
    _SMBUS_AVAILABLE = True
except ImportError:
    logging.warning("smbus2 non disponibile — sensori I2C disabilitati")
    _SMBUS_AVAILABLE = False


class BaseSensor:
    def __init__(self, address: int):
        self.address = address
        self._bus = smbus2.SMBus(1) if _SMBUS_AVAILABLE else None

    def read(self) -> dict | None:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError

    def available(self) -> bool:
        if not _SMBUS_AVAILABLE:
            return False
        try:
            self._bus.read_byte(self.address)
            return True
        except OSError:
            return False


class BME280Driver(BaseSensor):
    @property
    def name(self): return "bme280"

    def read(self) -> dict | None:
        try:
            import bme280
            calibration_params = bme280.load_calibration_params(self._bus, self.address)
            data = bme280.sample(self._bus, self.address, calibration_params)
            return {"temp": round(data.temperature, 1), "humidity": round(data.humidity, 1), "pressure": round(data.pressure, 1)}
        except Exception as e:
            logging.error(f"BME280 read error: {e}")
            return None


class INA219Driver(BaseSensor):
    @property
    def name(self): return "ina219"

    def read(self) -> dict | None:
        try:
            from ina219 import INA219
            ina = INA219(0.1, busnum=1, address=self.address)
            ina.configure()
            return {"voltage": round(ina.voltage(), 2), "current": round(ina.current(), 1), "power": round(ina.power(), 1)}
        except Exception as e:
            logging.error(f"INA219 read error: {e}")
            return None


_DRIVER_MAP = {
    "bme280": BME280Driver,
    "ina219": INA219Driver,
}

def _make_driver(name: str, address: int) -> BaseSensor | None:
    cls = _DRIVER_MAP.get(name)
    if cls:
        return cls(address)
    logging.warning(f"Driver sconosciuto: {name}")
    return None

def init(sensor_config_list: list) -> list:
    drivers = []
    for cfg in sensor_config_list:
        driver = _make_driver(cfg["name"], cfg["address"])
        if driver and driver.available():
            drivers.append(driver)
            logging.info(f"Sensore {cfg['name']} @ {hex(cfg['address'])} ok")
        else:
            logging.warning(f"Sensore {cfg['name']} @ {hex(cfg['address'])} non trovato")
    return drivers

async def start_polling(drivers: list, conn, broadcast_fn, interval: int = 30):
    import database
    while True:
        for driver in drivers:
            try:
                data = driver.read()
                if data is not None:
                    await database.save_sensor_reading(conn, driver.name, data)
                    await broadcast_fn({"type": "sensor", "data": {"sensor": driver.name, "values": data}})
            except Exception as e:
                logging.error(f"Lettura {driver.name} fallita: {e}")
        await asyncio.sleep(interval)
