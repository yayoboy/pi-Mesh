import asyncio, logging, time

try:
    import smbus2
    _SMBUS_AVAILABLE = True
except ImportError:
    logging.warning("smbus2 non disponibile — sensori I2C disabilitati")
    _SMBUS_AVAILABLE = False

try:
    import busio, board
    _BLINKA_AVAILABLE = True
except ImportError:
    _BLINKA_AVAILABLE = False

_blinka_i2c = None


def _get_blinka_i2c():
    """Return a shared busio.I2C instance, initialising it on first call."""
    global _blinka_i2c
    if _blinka_i2c is None and _BLINKA_AVAILABLE:
        try:
            _blinka_i2c = busio.I2C(board.SCL, board.SDA)
        except Exception as e:
            logging.error(f"Blinka I2C init error: {e}")
    return _blinka_i2c


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


# ── smbus2-based drivers ──────────────────────────────────────────────────────

class BME280Driver(BaseSensor):
    @property
    def name(self): return "bme280"

    def read(self) -> dict | None:
        try:
            import bme280
            calibration_params = bme280.load_calibration_params(self._bus, self.address)
            data = bme280.sample(self._bus, self.address, calibration_params)
            return {
                "temp":     round(data.temperature, 1),
                "humidity": round(data.humidity, 1),
                "pressure": round(data.pressure, 1),
            }
        except Exception as e:
            logging.error(f"BME280 read error: {e}")
            return None


class BME680Driver(BaseSensor):
    @property
    def name(self): return "bme680"

    def __init__(self, address: int):
        super().__init__(address)
        self._sensor = None
        if _SMBUS_AVAILABLE:
            try:
                import bme680
                self._sensor = bme680.BME680(address, i2c_device=self._bus)
                self._sensor.set_humidity_oversample(bme680.OS_2X)
                self._sensor.set_pressure_oversample(bme680.OS_4X)
                self._sensor.set_temperature_oversample(bme680.OS_8X)
                self._sensor.set_filter(bme680.FILTER_SIZE_3)
                self._sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)
                self._sensor.set_gas_heater_temperature(320)
                self._sensor.set_gas_heater_duration(150)
                self._sensor.select_gas_heater_profile(0)
            except Exception as e:
                logging.error(f"BME680 init error: {e}")

    def read(self) -> dict | None:
        if not self._sensor:
            return None
        try:
            if not self._sensor.get_sensor_data():
                return None
            result = {
                "temp":     round(self._sensor.data.temperature, 1),
                "humidity": round(self._sensor.data.humidity, 1),
                "pressure": round(self._sensor.data.pressure, 1),
            }
            if self._sensor.data.heat_stable:
                result["gas_resistance"] = round(self._sensor.data.gas_resistance, 0)
            return result
        except Exception as e:
            logging.error(f"BME680 read error: {e}")
            return None


class INA219Driver(BaseSensor):
    @property
    def name(self): return "ina219"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        if _SMBUS_AVAILABLE:
            try:
                from ina219 import INA219
                self._driver = INA219(0.1, busnum=1, address=self.address)
                self._driver.configure()
            except Exception as e:
                logging.error(f"INA219 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "voltage": round(self._driver.voltage(), 2),
                "current": round(self._driver.current(), 1),
                "power":   round(self._driver.power(), 1),
            }
        except Exception as e:
            logging.error(f"INA219 read error: {e}")
            return None


# ── Adafruit CircuitPython / Blinka drivers ───────────────────────────────────

class BMP280Driver(BaseSensor):
    @property
    def name(self): return "bmp280"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_bmp280
                self._driver = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=self.address)
            except Exception as e:
                logging.error(f"BMP280 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "temp":     round(self._driver.temperature, 1),
                "pressure": round(self._driver.pressure, 1),
            }
        except Exception as e:
            logging.error(f"BMP280 read error: {e}")
            return None


class BMP085Driver(BaseSensor):
    """Covers BMP085 and BMP180 (identical protocol, fixed address 0x77)."""
    @property
    def name(self): return "bmp085"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_bmp085
                self._driver = adafruit_bmp085.Adafruit_BMP085(i2c)
            except Exception as e:
                logging.error(f"BMP085 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "temp":     round(self._driver.temperature, 1),
                "pressure": round(self._driver.pressure / 100.0, 1),
            }
        except Exception as e:
            logging.error(f"BMP085 read error: {e}")
            return None


class SHT31Driver(BaseSensor):
    @property
    def name(self): return "sht31"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_sht31d
                self._driver = adafruit_sht31d.SHT31D(i2c, address=self.address)
            except Exception as e:
                logging.error(f"SHT31 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "temp":     round(self._driver.temperature, 1),
                "humidity": round(self._driver.relative_humidity, 1),
            }
        except Exception as e:
            logging.error(f"SHT31 read error: {e}")
            return None


class SHTC3Driver(BaseSensor):
    @property
    def name(self): return "shtc3"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_shtc3
                self._driver = adafruit_shtc3.SHTC3(i2c)
            except Exception as e:
                logging.error(f"SHTC3 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            temp, humidity = self._driver.measurements
            return {
                "temp":     round(temp, 1),
                "humidity": round(humidity, 1),
            }
        except Exception as e:
            logging.error(f"SHTC3 read error: {e}")
            return None


class MCP9808Driver(BaseSensor):
    @property
    def name(self): return "mcp9808"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_mcp9808
                self._driver = adafruit_mcp9808.MCP9808(i2c, address=self.address)
            except Exception as e:
                logging.error(f"MCP9808 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {"temp": round(self._driver.temperature, 2)}
        except Exception as e:
            logging.error(f"MCP9808 read error: {e}")
            return None


class LPS22HBDriver(BaseSensor):
    @property
    def name(self): return "lps22hb"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_lps2x
                self._driver = adafruit_lps2x.LPS22(i2c, address=self.address)
            except Exception as e:
                logging.error(f"LPS22HB init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "pressure": round(self._driver.pressure, 2),
                "temp":     round(self._driver.temperature, 1),
            }
        except Exception as e:
            logging.error(f"LPS22HB read error: {e}")
            return None


class PMSA003IDriver(BaseSensor):
    @property
    def name(self): return "pmsa003i"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_pm25.i2c as pm25_i2c
                self._driver = pm25_i2c.PM25_I2C(i2c, None, address=self.address)
            except Exception as e:
                logging.error(f"PMSA003I init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            d = self._driver.read()
            return {
                "pm10_std":  d["pm10 standard"],
                "pm25_std":  d["pm25 standard"],
                "pm100_std": d["pm100 standard"],
                "pm10_env":  d["pm10 env"],
                "pm25_env":  d["pm25 env"],
                "pm100_env": d["pm100 env"],
            }
        except Exception as e:
            logging.error(f"PMSA003I read error: {e}")
            return None


class SEN5XDriver(BaseSensor):
    """Sensirion SEN50/SEN54/SEN55 — NOx, VOC, PM, temp, humidity."""
    @property
    def name(self): return "sen5x"

    def __init__(self, address: int):
        super().__init__(address)
        self._device = None
        if _SMBUS_AVAILABLE:
            try:
                from sensirion_i2c_driver import LinuxI2cTransport, I2cConnection
                from sensirion_i2c_sen5x import Sen5xI2cDevice
                transport = LinuxI2cTransport('/dev/i2c-1')
                self._device = Sen5xI2cDevice(I2cConnection(transport))
                self._device.device_reset()
                self._device.start_measurement()
            except Exception as e:
                logging.error(f"SEN5X init error: {e}")

    def read(self) -> dict | None:
        if not self._device:
            return None
        try:
            v = self._device.read_measured_values()
            result = {}
            _maybe = lambda val, key, r=1: result.__setitem__(key, round(val.physical_value, r)) \
                if val.physical_value is not None else None
            _maybe(v.mass_concentration_pm1p0,  "pm1_0")
            _maybe(v.mass_concentration_pm2p5,  "pm2_5")
            _maybe(v.mass_concentration_pm10p0, "pm10")
            _maybe(v.ambient_humidity,           "humidity")
            _maybe(v.ambient_temperature,        "temp")
            _maybe(v.voc_index,                  "voc_index", 0)
            _maybe(v.nox_index,                  "nox_index", 0)
            return result if result else None
        except Exception as e:
            logging.error(f"SEN5X read error: {e}")
            return None


class VEML7700Driver(BaseSensor):
    @property
    def name(self): return "veml7700"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_veml7700
                self._driver = adafruit_veml7700.VEML7700(i2c, address=self.address)
            except Exception as e:
                logging.error(f"VEML7700 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {"lux": round(self._driver.lux, 1)}
        except Exception as e:
            logging.error(f"VEML7700 read error: {e}")
            return None


class TSL2591Driver(BaseSensor):
    @property
    def name(self): return "tsl2591"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_tsl2591
                self._driver = adafruit_tsl2591.TSL2591(i2c)
            except Exception as e:
                logging.error(f"TSL2591 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "lux":      round(self._driver.lux, 1),
                "infrared": self._driver.infrared,
                "visible":  self._driver.visible,
            }
        except Exception as e:
            logging.error(f"TSL2591 read error: {e}")
            return None


class RCWL9620Driver(BaseSensor):
    @property
    def name(self): return "rcwl9620"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_rcwl9620
                self._driver = adafruit_rcwl9620.RCWL9620(i2c, address=self.address)
            except Exception as e:
                logging.error(f"RCWL9620 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {"distance_cm": round(self._driver.distance, 1)}
        except Exception as e:
            logging.error(f"RCWL9620 read error: {e}")
            return None


class INA260Driver(BaseSensor):
    @property
    def name(self): return "ina260"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_ina260
                self._driver = adafruit_ina260.INA260(i2c, address=self.address)
            except Exception as e:
                logging.error(f"INA260 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "voltage": round(self._driver.voltage, 2),
                "current": round(self._driver.current, 1),
                "power":   round(self._driver.power, 1),
            }
        except Exception as e:
            logging.error(f"INA260 read error: {e}")
            return None


class INA3221Driver(BaseSensor):
    @property
    def name(self): return "ina3221"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_ina3221
                self._driver = adafruit_ina3221.INA3221(i2c, address=self.address)
            except Exception as e:
                logging.error(f"INA3221 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            result = {}
            for ch in range(1, 4):
                chan = self._driver[ch]
                result[f"ch{ch}_voltage"] = round(chan.bus_voltage, 2)
                result[f"ch{ch}_current"] = round(chan.current, 1)
            return result
        except Exception as e:
            logging.error(f"INA3221 read error: {e}")
            return None


class MAX17048Driver(BaseSensor):
    @property
    def name(self): return "max17048"

    def __init__(self, address: int):
        super().__init__(address)
        self._driver = None
        i2c = _get_blinka_i2c()
        if i2c is not None:
            try:
                import adafruit_max1704x
                self._driver = adafruit_max1704x.MAX17048(i2c)
            except Exception as e:
                logging.error(f"MAX17048 init error: {e}")

    def read(self) -> dict | None:
        if not self._driver:
            return None
        try:
            return {
                "voltage": round(self._driver.cell_voltage, 2),
                "percent": round(self._driver.cell_percent, 1),
            }
        except Exception as e:
            logging.error(f"MAX17048 read error: {e}")
            return None


# ── Registry ──────────────────────────────────────────────────────────────────

_DRIVER_MAP = {
    "bme280":   BME280Driver,
    "bme680":   BME680Driver,
    "bmp280":   BMP280Driver,
    "bmp085":   BMP085Driver,
    "bmp180":   BMP085Driver,   # BMP180 is hardware-compatible with BMP085
    "sht31":    SHT31Driver,
    "shtc3":    SHTC3Driver,
    "mcp9808":  MCP9808Driver,
    "lps22hb":  LPS22HBDriver,
    "pmsa003i": PMSA003IDriver,
    "sen5x":    SEN5XDriver,
    "veml7700": VEML7700Driver,
    "tsl2591":  TSL2591Driver,
    "rcwl9620": RCWL9620Driver,
    "ina219":   INA219Driver,
    "ina260":   INA260Driver,
    "ina3221":  INA3221Driver,
    "max17048": MAX17048Driver,
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
                data = await asyncio.to_thread(driver.read)
                if data is not None:
                    await database.save_sensor_reading(conn, driver.name, data)
                    await broadcast_fn({"type": "sensor", "data": {"sensor": driver.name, "values": data}})
            except Exception as e:
                logging.error(f"Lettura {driver.name} fallita: {e}")
        await asyncio.sleep(interval)
