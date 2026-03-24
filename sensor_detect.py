"""
I2C bus scanner — probes all addresses 0x08-0x77 and identifies sensors.

Strategy mirrors Meshtastic firmware's ScanI2C:
  1. Probe each address with read_byte() — ACK means a device is there
  2. Look up the address in the known-sensor table
  3. For ambiguous addresses, read a chip-ID or die-ID register to disambiguate

Usage:
    import sensor_detect
    sensors = sensor_detect.scan()           # → [{"name": "bme280", "address": 118}, ...]
    merged  = sensor_detect.merge(sensors, explicit_list)
"""
import logging

try:
    import smbus2 as _smbus2
    _SMBUS_AVAILABLE = True
except ImportError:
    _SMBUS_AVAILABLE = False


# ── Disambiguation helpers ────────────────────────────────────────────────────

def _read_byte_reg(bus, addr: int, reg: int) -> int | None:
    try:
        return bus.read_i2c_block_data(addr, reg, 1)[0]
    except OSError:
        return None


def _read_word_be(bus, addr: int, reg: int) -> int | None:
    """Read a 16-bit big-endian register (e.g. die-ID)."""
    try:
        d = bus.read_i2c_block_data(addr, reg, 2)
        return (d[0] << 8) | d[1]
    except OSError:
        return None


# Bosch BME/BMP family — register 0xD0 holds a unique chip_id byte
_BOSCH_CHIP_IDS: dict[int, str] = {
    0x60: "bme280",
    0x61: "bme680",
    0x58: "bmp280",
    0x56: "bmp280",   # engineering sample rev A
    0x57: "bmp280",   # engineering sample rev B
    0x55: "bmp085",   # also covers BMP180 (identical protocol)
}

# Texas Instruments INA family — register 0xFF (16-bit BE) holds die_id
_INA_DIE_IDS: dict[int, str] = {
    0x2270: "ina260",
    0x3220: "ina3221",
}


def _identify_bosch(bus, addr: int) -> str:
    chip_id = _read_byte_reg(bus, addr, 0xD0)
    if chip_id is not None:
        name = _BOSCH_CHIP_IDS.get(chip_id)
        if name:
            return name
        logging.warning(f"sensor_detect: chip_id Bosch sconosciuto 0x{chip_id:02X} @ {hex(addr)}")
    return "bme280"   # safest fallback — most common in the family


def _identify_ina(bus, addr: int) -> str:
    die_id = _read_word_be(bus, addr, 0xFF)
    if die_id is not None:
        name = _INA_DIE_IDS.get(die_id)
        if name:
            # INA3221 is only valid at 0x40-0x43
            if name == "ina3221" and addr > 0x43:
                return "ina260"
            return name
    return "ina219"   # no recognised die_id → assume INA219


def _identify_ina_or_sht31(bus, addr: int) -> str:
    """
    0x44 / 0x45 are shared by SHT31 and INA219 / INA260.
    Read the INA die-ID register; if it matches INA260 use that,
    otherwise assume SHT31 (the more common choice at those addresses
    for environment-sensing applications).
    """
    die_id = _read_word_be(bus, addr, 0xFF)
    if die_id == 0x2270:
        return "ina260"
    return "sht31"


# ── Address table ─────────────────────────────────────────────────────────────
# Values starting with "_" are sentinel strings that trigger a disambiguation
# function call; all other values are direct sensor names.

_ADDR_TABLE: dict[int, str] = {
    0x10: "veml7700",
    0x12: "pmsa003i",
    0x13: "rcwl9620",
    # MCP9808 configurable via A2-A0 pins → addresses 0x18-0x1F
    **{a: "mcp9808" for a in range(0x18, 0x20)},
    0x29: "tsl2591",
    0x36: "max17048",
    # INA family 0x40-0x4F; SHT31 also lives at 0x44/0x45
    **{a: ("_ina_or_sht31" if a in (0x44, 0x45) else "_ina") for a in range(0x40, 0x50)},
    0x5C: "lps22hb",
    0x5D: "lps22hb",
    0x69: "sen5x",
    0x70: "shtc3",
    # Bosch BME/BMP at 0x76/0x77 → read chip_id register to identify
    0x76: "_bosch",
    0x77: "_bosch",
}

_DISAMBIGUATORS = {
    "_bosch":        _identify_bosch,
    "_ina":          _identify_ina,
    "_ina_or_sht31": _identify_ina_or_sht31,
}


# ── Public API ────────────────────────────────────────────────────────────────

def scan(bus=None) -> list[dict]:
    """
    Scan I2C bus 1 and return identified sensors.

    Returns:
        List of ``{"name": str, "address": int}`` dicts, sorted by address,
        suitable for passing directly to ``sensor_handler.init()``.
    """
    if not _SMBUS_AVAILABLE:
        logging.warning("sensor_detect: smbus2 non disponibile, scan impossibile")
        return []

    _own_bus = bus is None
    if _own_bus:
        try:
            bus = _smbus2.SMBus(1)
        except Exception as e:
            logging.error(f"sensor_detect: apertura I2C bus 1 fallita: {e}")
            return []

    found: list[dict] = []
    try:
        for addr in range(0x08, 0x78):
            try:
                bus.read_byte(addr)
            except OSError:
                continue   # no device at this address

            handler = _ADDR_TABLE.get(addr)
            if handler is None:
                logging.debug(f"sensor_detect: dispositivo sconosciuto @ {hex(addr)}")
                continue

            disambiguate = _DISAMBIGUATORS.get(handler)
            name = disambiguate(bus, addr) if disambiguate else handler

            found.append({"name": name, "address": addr})
            logging.info(f"sensor_detect: trovato {name} @ {hex(addr)}")
    finally:
        if _own_bus:
            bus.close()

    return found


def merge(scanned: list[dict], explicit: list[dict]) -> list[dict]:
    """
    Merge auto-scan results with an explicit sensor list from config.

    Explicit entries always win when two entries share the same address,
    allowing the user to override a misdetected sensor without disabling
    the scan for everything else.

    Args:
        scanned:  output of ``scan()``
        explicit: parsed ``I2C_SENSORS`` from ``config.py``

    Returns:
        Combined list, sorted by address.
    """
    by_addr: dict[int, dict] = {s["address"]: s for s in scanned}
    for entry in explicit:
        by_addr[entry["address"]] = entry   # explicit wins
    return sorted(by_addr.values(), key=lambda s: s["address"])
