"""Config device-level della board Meshtastic — /api/config/device/<sezione>.

Sezioni: position (GPS, posizione fissa), power, display (l'OLED della
board, non il display del Pi), network (WiFi/Eth della board), bluetooth,
security (chiave pubblica in sola lettura). Stesso pattern di
module_config_router: GET live-o-cache, POST validato → coda comandi,
503 a board offline.
"""
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import meshtasticd_client
import config as cfg

router = APIRouter()


# ─── Position ──────────────────────────────────────────────────────────
@router.get('/api/config/device/position')
async def get_position():
    return await meshtasticd_client.get_position_config(cfg.DB_PATH)


class PositionConfig(BaseModel):
    position_broadcast_secs: int = 0
    position_broadcast_smart_enabled: bool = False
    fixed_position: bool = False
    gps_mode: str = 'DISABLED'
    gps_update_interval: int = 0
    fixed_lat: Optional[float] = None
    fixed_lon: Optional[float] = None
    fixed_alt: int = 0


@router.post('/api/config/device/position')
async def set_position(body: PositionConfig):
    if body.gps_mode not in ('DISABLED', 'ENABLED', 'NOT_PRESENT'):
        return JSONResponse({'error': 'gps_mode non valido'}, status_code=400)
    try:
        await meshtasticd_client.set_position_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Power ─────────────────────────────────────────────────────────────
@router.get('/api/config/device/power')
async def get_power():
    return await meshtasticd_client.get_power_config(cfg.DB_PATH)


class PowerConfig(BaseModel):
    is_power_saving: bool = False
    on_battery_shutdown_after_secs: int = 0
    wait_bluetooth_secs: int = 0
    sds_secs: int = 0
    ls_secs: int = 0
    min_wake_secs: int = 0


@router.post('/api/config/device/power')
async def set_power(body: PowerConfig):
    try:
        await meshtasticd_client.set_power_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Display (OLED della board, non il display del Pi) ────────────────
@router.get('/api/config/device/display')
async def get_display_device():
    return await meshtasticd_client.get_display_device_config(cfg.DB_PATH)


class DisplayDeviceConfig(BaseModel):
    screen_on_secs: int = 0
    auto_screen_carousel_secs: int = 0
    compass_north_top: bool = False
    flip_screen: bool = False
    units: str = 'METRIC'
    displaymode: str = 'DEFAULT'
    heading_bold: bool = False
    wake_on_tap_or_motion: bool = False
    use_12h_clock: bool = False


@router.post('/api/config/device/display')
async def set_display_device(body: DisplayDeviceConfig):
    if body.units not in ('METRIC', 'IMPERIAL'):
        return JSONResponse({'error': 'units non valido'}, status_code=400)
    if body.displaymode not in ('DEFAULT', 'TWOCOLOR', 'INVERTED', 'COLOR'):
        return JSONResponse({'error': 'displaymode non valido'}, status_code=400)
    try:
        await meshtasticd_client.set_display_device_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Network (WiFi/Ethernet della board) ───────────────────────────────
@router.get('/api/config/device/network')
async def get_network():
    return await meshtasticd_client.get_network_config(cfg.DB_PATH)


class NetworkConfig(BaseModel):
    wifi_enabled: bool = False
    wifi_ssid: str = ''
    wifi_psk: str = ''
    eth_enabled: bool = False
    ntp_server: str = ''
    address_mode: str = 'DHCP'


@router.post('/api/config/device/network')
async def set_network(body: NetworkConfig):
    if body.address_mode not in ('DHCP', 'STATIC'):
        return JSONResponse({'error': 'address_mode non valido'}, status_code=400)
    try:
        await meshtasticd_client.set_network_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Bluetooth ─────────────────────────────────────────────────────────
@router.get('/api/config/device/bluetooth')
async def get_bluetooth():
    return await meshtasticd_client.get_bluetooth_config(cfg.DB_PATH)


class BluetoothConfig(BaseModel):
    enabled: bool = False
    mode: str = 'RANDOM_PIN'
    fixed_pin: int = 123456


@router.post('/api/config/device/bluetooth')
async def set_bluetooth(body: BluetoothConfig):
    if body.mode not in ('RANDOM_PIN', 'FIXED_PIN', 'NO_PIN'):
        return JSONResponse({'error': 'mode non valido'}, status_code=400)
    if not (100000 <= body.fixed_pin <= 999999):
        return JSONResponse({'error': 'fixed_pin deve essere di 6 cifre'}, status_code=400)
    try:
        await meshtasticd_client.set_bluetooth_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Security ──────────────────────────────────────────────────────────
@router.get('/api/config/device/security')
async def get_security():
    return await meshtasticd_client.get_security_config(cfg.DB_PATH)


class SecurityConfig(BaseModel):
    is_managed: bool = False
    serial_enabled: bool = True
    debug_log_api_enabled: bool = False
    admin_channel_enabled: bool = False


@router.post('/api/config/device/security')
async def set_security(body: SecurityConfig):
    try:
        await meshtasticd_client.set_security_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)
