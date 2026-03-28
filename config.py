# config.py
import os

MESHTASTICD_HOST = os.getenv('MESHTASTICD_HOST', 'localhost')
MESHTASTICD_PORT = int(os.getenv('MESHTASTICD_PORT', '4403'))
DB_PATH          = os.getenv('DB_PATH', 'data/mesh.db')
LOG_LEVEL        = os.getenv('LOG_LEVEL', 'WARNING')
NODE_CACHE_TTL   = float(os.getenv('NODE_CACHE_TTL', '8.0'))
