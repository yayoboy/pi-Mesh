"""config.py — Configurazione globale letta dalle variabili d'ambiente.

I valori arrivano da config.env / config.env.local (caricati da systemd
con EnvironmentFile o da uvicorn con --env-file); qui ci sono solo i
default. SERIAL_PATH accetta un device seriale (/dev/tty...) oppure
``tcp://host[:porta]`` per meshtasticd o una board remota.
"""
import os
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from shutil import which

SERIAL_PATH    = os.getenv('SERIAL_PATH', '/dev/ttyACM0')
DB_PATH        = os.getenv('DB_PATH', 'data/mesh.db')
LOG_LEVEL      = os.getenv('LOG_LEVEL', 'WARNING')
NODE_CACHE_TTL = float(os.getenv('NODE_CACHE_TTL', '8.0'))

# gpiochip su cui sta l'header: 0 su Raspberry fino al Pi 4 (dove il numero
# di linea coincide col BCM). Il Pi 5 e i SoC con più banchi (Allwinner,
# Rockchip) possono usarne un altro: `gpiodetect` li elenca.
GPIO_CHIP = int(os.getenv('GPIO_CHIP', '0'))

MAP_LOCAL_TILES = os.getenv('MAP_LOCAL_TILES', '0') == '1'
MAP_REGION      = os.getenv('MAP_REGION', 'italia')

# Alert thresholds
ALERT_NODE_OFFLINE_MIN = int(os.getenv('ALERT_NODE_OFFLINE_MIN', '30'))
ALERT_BATTERY_LOW      = int(os.getenv('ALERT_BATTERY_LOW', '20'))
ALERT_RAM_HIGH         = int(os.getenv('ALERT_RAM_HIGH', '85'))

# MQTT bridge
MQTT_ENABLED = os.getenv('MQTT_ENABLED', '0') == '1'

@lru_cache(maxsize=1)
def capabilities() -> dict[str, bool]:
    """Hardware davvero presente su questa macchina.

    Le sezioni di Settings che pilotano hardware assente vengono nascoste
    (window.PIMESH_CAPS in base.html, filtro in static/config.js): la stessa
    build gira su Pi con display SPI, Pi con HDMI, Pi Zero headless o un PC
    Linux con la sola radio USB, mostrando solo ciò che quella macchina ha.
    """
    # ponytail: rilevato una volta per processo — riavvia il servizio se
    # aggiungi hardware a caldo (pannello DDC/CI, chiavetta USB, HAT RTC).
    return {
        'vcgencmd':    bool(which('vcgencmd')),                                   # metriche Pi + undervoltage
        'backlight':   bool(which('ddcutil')) or Path('/sys/class/backlight').exists(),
        # "pilotabile", non "esiste": su una scheda non-Raspberry il gpiochip
        # c'è comunque, ma senza lgpio ogni comando fallirebbe al click.
        'gpio':        Path(f'/dev/gpiochip{GPIO_CHIP}').exists() and find_spec('lgpio') is not None,
        'i2c':         any(Path('/dev').glob('i2c-*')),                           # sensori, RTC
        'wifi':        bool(which('nmcli')),                                      # rete Pi + access point
        'usb_storage': bool(which('lsblk')),                                      # tile su chiavetta
        'spi_display': Path('/sys/class/graphics/fb1').exists(),                  # rotazione tft35a
    }


REGION_BOUNDS: dict[str, dict[str, float]] = {
    'italia':   {'lat_min': 35.0,  'lat_max': 47.5, 'lon_min':   6.5, 'lon_max':  18.5},
    'francia':  {'lat_min': 41.3,  'lat_max': 51.1, 'lon_min':  -5.2, 'lon_max':   9.6},
    'germania': {'lat_min': 47.3,  'lat_max': 55.1, 'lon_min':   5.9, 'lon_max':  15.0},
    'spagna':   {'lat_min': 35.9,  'lat_max': 43.8, 'lon_min':  -9.3, 'lon_max':   4.3},
    'europa':   {'lat_min': 34.0,  'lat_max': 72.0, 'lon_min': -25.0, 'lon_max':  45.0},
    'mondo':    {'lat_min': -85.0, 'lat_max': 85.0, 'lon_min':-180.0, 'lon_max': 180.0},
}
