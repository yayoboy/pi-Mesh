import os

def parse_sensor_config(s: str) -> list:
    result = []
    if not s.strip():
        return result
    for entry in s.split(","):
        entry = entry.strip()
        try:
            name, addr_str = entry.split(":")
            result.append({"name": name.strip(), "address": int(addr_str.strip(), 16)})
        except (ValueError, TypeError):
            pass
    return result

# Percorsi
SERIAL_PORT      = os.getenv("SERIAL_PORT", "/dev/ttyMESHTASTIC")
DB_PERSISTENT    = os.getenv("DB_PERSISTENT", "/home/pi/meshtastic-pi/data/mesh.db")
DB_RUNTIME       = "/tmp/mesh_runtime.db"
DB_SYNC_INTERVAL = int(os.getenv("DB_SYNC_INTERVAL", "300"))

# GPIO encoder
ENC1_A  = int(os.getenv("ENC1_A", "17"))
ENC1_B  = int(os.getenv("ENC1_B", "27"))
ENC1_SW = int(os.getenv("ENC1_SW", "22"))
ENC2_A  = int(os.getenv("ENC2_A", "5"))
ENC2_B  = int(os.getenv("ENC2_B", "6"))
ENC2_SW = int(os.getenv("ENC2_SW", "13"))
BUZZER_PIN = int(os.getenv("BUZZER_PIN", "0"))  # 0 = disabled

# Sensori I2C
I2C_SENSORS   = parse_sensor_config(os.getenv("I2C_SENSORS", ""))
# I2C_AUTOSCAN=1 → scansiona il bus all'avvio; I2C_SENSORS sovrascrive i risultati per indirizzo
I2C_AUTOSCAN  = os.getenv("I2C_AUTOSCAN", "1") not in ("0", "false", "no")

# Mappa
MAP_BOUNDS = {
    "lat_min": float(os.getenv("MAP_LAT_MIN", "41.0")),
    "lat_max": float(os.getenv("MAP_LAT_MAX", "43.0")),
    "lon_min": float(os.getenv("MAP_LON_MIN", "11.5")),
    "lon_max": float(os.getenv("MAP_LON_MAX", "14.5")),
}
MAP_ZOOM_MIN = int(os.getenv("MAP_ZOOM_MIN", "8"))
MAP_ZOOM_MAX = int(os.getenv("MAP_ZOOM_MAX", "12"))

# Display
DISPLAY_ROTATION = int(os.getenv("DISPLAY_ROTATION", "0"))

# UI
UI_THEME = os.getenv("UI_THEME", "dark")
UI_STATUS_DENSITY    = os.getenv("UI_STATUS_DENSITY", "icons")   # compact | icons | full
UI_CHANNEL_LAYOUT    = os.getenv("UI_CHANNEL_LAYOUT", "list")    # list | tabs | unified
UI_ORIENTATION       = os.getenv("UI_ORIENTATION", "portrait")   # portrait | landscape

# Limiti memoria
MAX_MESSAGES_PER_CHANNEL = 200
MAX_NODES_IN_MEMORY      = 100
