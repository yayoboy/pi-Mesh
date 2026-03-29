# config.py
import os

SERIAL_PATH    = os.getenv('SERIAL_PATH', '/dev/ttyACM0')
DB_PATH        = os.getenv('DB_PATH', 'data/mesh.db')
LOG_LEVEL      = os.getenv('LOG_LEVEL', 'WARNING')
NODE_CACHE_TTL = float(os.getenv('NODE_CACHE_TTL', '8.0'))
