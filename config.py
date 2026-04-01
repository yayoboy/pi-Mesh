# config.py
import os

SERIAL_PATH    = os.getenv('SERIAL_PATH', '/dev/ttyACM0')
DB_PATH        = os.getenv('DB_PATH', 'data/mesh.db')
LOG_LEVEL      = os.getenv('LOG_LEVEL', 'WARNING')
NODE_CACHE_TTL = float(os.getenv('NODE_CACHE_TTL', '8.0'))

MAP_LOCAL_TILES = os.getenv('MAP_LOCAL_TILES', '0') == '1'
MAP_REGION      = os.getenv('MAP_REGION', 'italia')

# Alert thresholds
ALERT_NODE_OFFLINE_MIN = int(os.getenv('ALERT_NODE_OFFLINE_MIN', '30'))
ALERT_BATTERY_LOW      = int(os.getenv('ALERT_BATTERY_LOW', '20'))
ALERT_RAM_HIGH         = int(os.getenv('ALERT_RAM_HIGH', '85'))

REGION_BOUNDS: dict[str, dict[str, float]] = {
    'italia':   {'lat_min': 35.0,  'lat_max': 47.5, 'lon_min':   6.5, 'lon_max':  18.5},
    'francia':  {'lat_min': 41.3,  'lat_max': 51.1, 'lon_min':  -5.2, 'lon_max':   9.6},
    'germania': {'lat_min': 47.3,  'lat_max': 55.1, 'lon_min':   5.9, 'lon_max':  15.0},
    'spagna':   {'lat_min': 35.9,  'lat_max': 43.8, 'lon_min':  -9.3, 'lon_max':   4.3},
    'europa':   {'lat_min': 34.0,  'lat_max': 72.0, 'lon_min': -25.0, 'lon_max':  45.0},
    'mondo':    {'lat_min': -85.0, 'lat_max': 85.0, 'lon_min':-180.0, 'lon_max': 180.0},
}
