# routers/module_config_router.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import meshtasticd_client
import config as cfg

router = APIRouter()


# ─── External Notifications ────────────────────────────────────────────
@router.get('/api/config/module/external-notification')
async def get_ext_notif():
    return await meshtasticd_client.get_external_notification_config(cfg.DB_PATH)


class ExtNotifConfig(BaseModel):
    enabled: bool = False
    output_pin: int = 0
    active_high: bool = False
    alert_message: bool = False
    alert_bell: bool = False
    use_pwm: bool = False
    nag_timeout: int = 0


@router.post('/api/config/module/external-notification')
async def set_ext_notif(body: ExtNotifConfig):
    try:
        await meshtasticd_client.set_external_notification_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Store & Forward ───────────────────────────────────────────────────
@router.get('/api/config/module/store-forward')
async def get_store_forward():
    return await meshtasticd_client.get_store_forward_config(cfg.DB_PATH)


class StoreForwardConfig(BaseModel):
    enabled: bool = False
    heartbeat: bool = False
    history_return_max: int = 0
    history_return_window: int = 0


@router.post('/api/config/module/store-forward')
async def set_store_forward(body: StoreForwardConfig):
    try:
        await meshtasticd_client.set_store_forward_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Telemetry ─────────────────────────────────────────────────────────
@router.get('/api/config/module/telemetry')
async def get_telemetry_module():
    return await meshtasticd_client.get_telemetry_module_config(cfg.DB_PATH)


class TelemetryModuleConfig(BaseModel):
    device_update_interval: int = 0
    environment_update_interval: int = 0
    environment_measurement_enabled: bool = False
    air_quality_enabled: bool = False
    power_measurement_enabled: bool = False


@router.post('/api/config/module/telemetry')
async def set_telemetry_module(body: TelemetryModuleConfig):
    try:
        await meshtasticd_client.set_telemetry_module_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Canned Message (board-side) ───────────────────────────────────────
@router.get('/api/config/module/canned-message')
async def get_canned_message_module():
    return await meshtasticd_client.get_canned_message_module_config(cfg.DB_PATH)


class CannedMessageModuleConfig(BaseModel):
    rotary1_enabled: bool = False
    send_bell: bool = False
    free_text_sms_enabled: bool = False


@router.post('/api/config/module/canned-message')
async def set_canned_message_module(body: CannedMessageModuleConfig):
    try:
        await meshtasticd_client.set_canned_message_module_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Range Test ────────────────────────────────────────────────────────
@router.get('/api/config/module/range-test')
async def get_range_test():
    return await meshtasticd_client.get_range_test_config(cfg.DB_PATH)


class RangeTestConfig(BaseModel):
    enabled: bool = False
    sender: int = 0
    save: bool = False


@router.post('/api/config/module/range-test')
async def set_range_test(body: RangeTestConfig):
    try:
        await meshtasticd_client.set_range_test_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Detection Sensor ──────────────────────────────────────────────────
@router.get('/api/config/module/detection-sensor')
async def get_detection_sensor():
    return await meshtasticd_client.get_detection_sensor_config(cfg.DB_PATH)


class DetectionSensorConfig(BaseModel):
    enabled: bool = False
    minimum_broadcast_secs: int = 0
    state_broadcast_secs: int = 0
    name: str = ''
    monitor_pin: int = 0
    use_pullup: bool = False
    detection_triggered_high: bool = False


@router.post('/api/config/module/detection-sensor')
async def set_detection_sensor(body: DetectionSensorConfig):
    try:
        await meshtasticd_client.set_detection_sensor_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Ambient Lighting ──────────────────────────────────────────────────
@router.get('/api/config/module/ambient-lighting')
async def get_ambient_lighting():
    return await meshtasticd_client.get_ambient_lighting_config(cfg.DB_PATH)


class AmbientLightingConfig(BaseModel):
    led_state: bool = False
    current: int = 0
    red: int = 0
    green: int = 0
    blue: int = 0


@router.post('/api/config/module/ambient-lighting')
async def set_ambient_lighting(body: AmbientLightingConfig):
    try:
        await meshtasticd_client.set_ambient_lighting_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Neighbor Info ─────────────────────────────────────────────────────
@router.get('/api/config/module/neighbor-info')
async def get_neighbor_info_module():
    return await meshtasticd_client.get_neighbor_info_module_config(cfg.DB_PATH)


class NeighborInfoModuleConfig(BaseModel):
    enabled: bool = False
    update_interval: int = 0
    transmit_over_lora: bool = False


@router.post('/api/config/module/neighbor-info')
async def set_neighbor_info_module(body: NeighborInfoModuleConfig):
    try:
        await meshtasticd_client.set_neighbor_info_module_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


# ─── Serial ────────────────────────────────────────────────────────────
@router.get('/api/config/module/serial')
async def get_serial_module():
    return await meshtasticd_client.get_serial_module_config(cfg.DB_PATH)


class SerialModuleConfig(BaseModel):
    enabled: bool = False
    echo: bool = False
    rxd: int = 0
    txd: int = 0
    timeout: int = 0
    mode: str = 'DEFAULT'
    override_console_serial_port: bool = False


@router.post('/api/config/module/serial')
async def set_serial_module(body: SerialModuleConfig):
    try:
        await meshtasticd_client.set_serial_module_config(body.model_dump())
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)
