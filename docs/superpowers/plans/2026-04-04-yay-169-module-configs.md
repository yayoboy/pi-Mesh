# Module Configs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere configurazione completa di 9 moduli Meshtastic mancanti nella pagina /config.

**Architecture:** Nuovo router `module_config_router.py` con GET/SET per ogni modulo via meshtastic-python. Pattern identico al MQTT config già esistente: `_interface.localNode.moduleConfig.xxx` per lettura, `setConfig(ModuleConfig(xxx=cfg))` per scrittura. Nove nuove sezioni nella sidebar di config.html.

**Tech Stack:** FastAPI, meshtastic-python, protobuf (module_config_pb2), Alpine.js, Jinja2

---

### Task 1: Funzioni get/set in meshtasticd_client.py

**Files:**
- Modify: `meshtasticd_client.py`

Aggiungi queste funzioni dopo `set_mqtt_config`. Il pattern è identico per ogni modulo: lettura live con fallback cache, scrittura via `_command_queue`.

- [ ] **Step 1: Aggiungi get/set External Notifications**

```python
async def get_external_notification_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.external_notification
                return {
                    'enabled': mc.enabled,
                    'output_pin': mc.output_pin,
                    'active_high': mc.active_high,
                    'alert_message': mc.alert_message,
                    'alert_bell': mc.alert_bell,
                    'use_pwm': mc.use_pwm,
                    'nag_timeout': mc.nag_timeout,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'external_notification', data)
            return data
        except Exception as e:
            logger.error('get_external_notification_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'external_notification')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'output_pin': 0, 'active_high': False,
            'alert_message': False, 'alert_bell': False, 'use_pwm': False,
            'nag_timeout': 0, 'cached': True}


def _do_set_external_notification_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.ExternalNotificationConfig(
        enabled=params.get('enabled', False),
        output_pin=params.get('output_pin', 0),
        active_high=params.get('active_high', False),
        alert_message=params.get('alert_message', False),
        alert_bell=params.get('alert_bell', False),
        use_pwm=params.get('use_pwm', False),
        nag_timeout=params.get('nag_timeout', 0),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(external_notification=cfg))


async def set_external_notification_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_external_notification_config(_p))
```

- [ ] **Step 2: Aggiungi get/set Store & Forward**

```python
async def get_store_forward_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.store_forward
                return {
                    'enabled': mc.enabled,
                    'heartbeat': mc.heartbeat,
                    'history_return_max': mc.history_return_max,
                    'history_return_window': mc.history_return_window,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'store_forward', data)
            return data
        except Exception as e:
            logger.error('get_store_forward_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'store_forward')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'heartbeat': False,
            'history_return_max': 0, 'history_return_window': 0, 'cached': True}


def _do_set_store_forward_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.StoreAndForwardConfig(
        enabled=params.get('enabled', False),
        heartbeat=params.get('heartbeat', False),
        history_return_max=params.get('history_return_max', 0),
        history_return_window=params.get('history_return_window', 0),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(store_forward=cfg))


async def set_store_forward_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_store_forward_config(_p))
```

- [ ] **Step 3: Aggiungi get/set Telemetry**

```python
async def get_telemetry_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.telemetry
                return {
                    'device_update_interval': mc.device_update_interval,
                    'environment_update_interval': mc.environment_update_interval,
                    'environment_measurement_enabled': mc.environment_measurement_enabled,
                    'air_quality_enabled': mc.air_quality_enabled,
                    'power_measurement_enabled': mc.power_measurement_enabled,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'telemetry_module', data)
            return data
        except Exception as e:
            logger.error('get_telemetry_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'telemetry_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'device_update_interval': 0, 'environment_update_interval': 0,
            'environment_measurement_enabled': False, 'air_quality_enabled': False,
            'power_measurement_enabled': False, 'cached': True}


def _do_set_telemetry_module_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.TelemetryConfig(
        device_update_interval=params.get('device_update_interval', 0),
        environment_update_interval=params.get('environment_update_interval', 0),
        environment_measurement_enabled=params.get('environment_measurement_enabled', False),
        air_quality_enabled=params.get('air_quality_enabled', False),
        power_measurement_enabled=params.get('power_measurement_enabled', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(telemetry=cfg))


async def set_telemetry_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_telemetry_module_config(_p))
```

- [ ] **Step 4: Aggiungi get/set Canned Message (board-side)**

```python
async def get_canned_message_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.canned_message
                return {
                    'rotary1_enabled': mc.rotary1_enabled,
                    'send_bell': mc.send_bell,
                    'free_text_sms_enabled': mc.free_text_sms_enabled,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'canned_message_module', data)
            return data
        except Exception as e:
            logger.error('get_canned_message_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'canned_message_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'rotary1_enabled': False, 'send_bell': False,
            'free_text_sms_enabled': False, 'cached': True}


def _do_set_canned_message_module_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.CannedMessageConfig(
        rotary1_enabled=params.get('rotary1_enabled', False),
        send_bell=params.get('send_bell', False),
        free_text_sms_enabled=params.get('free_text_sms_enabled', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(canned_message=cfg))


async def set_canned_message_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_canned_message_module_config(_p))
```

- [ ] **Step 5: Aggiungi get/set Range Test**

```python
async def get_range_test_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.range_test
                return {
                    'enabled': mc.enabled,
                    'sender': mc.sender,
                    'save': mc.save,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'range_test', data)
            return data
        except Exception as e:
            logger.error('get_range_test_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'range_test')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'sender': 0, 'save': False, 'cached': True}


def _do_set_range_test_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.RangeTestConfig(
        enabled=params.get('enabled', False),
        sender=params.get('sender', 0),
        save=params.get('save', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(range_test=cfg))


async def set_range_test_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_range_test_config(_p))
```

- [ ] **Step 6: Aggiungi get/set Detection Sensor**

```python
async def get_detection_sensor_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.detection_sensor
                return {
                    'enabled': mc.enabled,
                    'minimum_broadcast_secs': mc.minimum_broadcast_secs,
                    'state_broadcast_secs': mc.state_broadcast_secs,
                    'name': mc.name,
                    'monitor_pin': mc.monitor_pin,
                    'use_pullup': mc.use_pullup,
                    'detection_triggered_high': mc.detection_triggered_high,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'detection_sensor', data)
            return data
        except Exception as e:
            logger.error('get_detection_sensor_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'detection_sensor')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'minimum_broadcast_secs': 0, 'state_broadcast_secs': 0,
            'name': '', 'monitor_pin': 0, 'use_pullup': False,
            'detection_triggered_high': False, 'cached': True}


def _do_set_detection_sensor_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.DetectionSensorConfig(
        enabled=params.get('enabled', False),
        minimum_broadcast_secs=params.get('minimum_broadcast_secs', 0),
        state_broadcast_secs=params.get('state_broadcast_secs', 0),
        name=params.get('name', ''),
        monitor_pin=params.get('monitor_pin', 0),
        use_pullup=params.get('use_pullup', False),
        detection_triggered_high=params.get('detection_triggered_high', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(detection_sensor=cfg))


async def set_detection_sensor_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_detection_sensor_config(_p))
```

- [ ] **Step 7: Aggiungi get/set Ambient Lighting**

```python
async def get_ambient_lighting_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.ambient_lighting
                return {
                    'led_state': mc.led_state,
                    'current': mc.current,
                    'red': mc.red,
                    'green': mc.green,
                    'blue': mc.blue,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'ambient_lighting', data)
            return data
        except Exception as e:
            logger.error('get_ambient_lighting_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'ambient_lighting')
    if cached:
        cached['cached'] = True
        return cached
    return {'led_state': False, 'current': 0, 'red': 0,
            'green': 0, 'blue': 0, 'cached': True}


def _do_set_ambient_lighting_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.AmbientLightingConfig(
        led_state=params.get('led_state', False),
        current=params.get('current', 0),
        red=params.get('red', 0),
        green=params.get('green', 0),
        blue=params.get('blue', 0),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(ambient_lighting=cfg))


async def set_ambient_lighting_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_ambient_lighting_config(_p))
```

- [ ] **Step 8: Aggiungi get/set Neighbor Info**

```python
async def get_neighbor_info_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.neighbor_info
                return {
                    'enabled': mc.enabled,
                    'update_interval': mc.update_interval,
                    'transmit_over_lora': mc.transmit_over_lora,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'neighbor_info_module', data)
            return data
        except Exception as e:
            logger.error('get_neighbor_info_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'neighbor_info_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'update_interval': 0,
            'transmit_over_lora': False, 'cached': True}


def _do_set_neighbor_info_module_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    cfg = module_config_pb2.ModuleConfig.NeighborInfoConfig(
        enabled=params.get('enabled', False),
        update_interval=params.get('update_interval', 0),
        transmit_over_lora=params.get('transmit_over_lora', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(neighbor_info=cfg))


async def set_neighbor_info_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_neighbor_info_module_config(_p))
```

- [ ] **Step 9: Aggiungi get/set Serial**

```python
async def get_serial_module_config(db_path: str) -> dict:
    if _connected and _interface:
        try:
            loop = asyncio.get_event_loop()
            def _read():
                mc = _interface.localNode.moduleConfig.serial
                return {
                    'enabled': mc.enabled,
                    'echo': mc.echo,
                    'rxd': mc.rxd,
                    'txd': mc.txd,
                    'timeout': mc.timeout,
                    'mode': mc.Mode.Name(mc.mode),
                    'override_console_serial_port': mc.override_console_serial_port,
                }
            data = await loop.run_in_executor(None, _read)
            data['cached'] = False
            await database.set_config_cache(db_path, 'serial_module', data)
            return data
        except Exception as e:
            logger.error('get_serial_module_config failed: %s', e)
    cached = await database.get_config_cache(db_path, 'serial_module')
    if cached:
        cached['cached'] = True
        return cached
    return {'enabled': False, 'echo': False, 'rxd': 0, 'txd': 0,
            'timeout': 0, 'mode': 'DEFAULT', 'override_console_serial_port': False,
            'cached': True}


def _do_set_serial_module_config(params: dict) -> None:
    from meshtastic.protobuf import module_config_pb2
    mode_val = module_config_pb2.ModuleConfig.SerialConfig.Serial_Baud.Value('DEFAULT')
    try:
        mode_val = module_config_pb2.ModuleConfig.SerialConfig.Mode.Value(params.get('mode', 'DEFAULT'))
    except ValueError:
        pass
    cfg = module_config_pb2.ModuleConfig.SerialConfig(
        enabled=params.get('enabled', False),
        echo=params.get('echo', False),
        rxd=params.get('rxd', 0),
        txd=params.get('txd', 0),
        timeout=params.get('timeout', 0),
        mode=mode_val,
        override_console_serial_port=params.get('override_console_serial_port', False),
    )
    _interface.localNode.setConfig(module_config_pb2.ModuleConfig(serial=cfg))


async def set_serial_module_config(params: dict) -> None:
    if not _connected or not _interface:
        raise RuntimeError('Board not connected')
    _p = dict(params)
    await _command_queue.put(lambda: _do_set_serial_module_config(_p))
```

- [ ] **Step 10: Commit**

```bash
git add meshtasticd_client.py
git commit -m "feat(modules): add get/set functions for 9 module configs"
```

---

### Task 2: Router module_config_router.py

**Files:**
- Create: `routers/module_config_router.py`
- Modify: `main.py`

- [ ] **Step 1: Crea `routers/module_config_router.py`**

```python
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
```

- [ ] **Step 2: Registra in `main.py`**

Trova:
```python
from routers import nodes, map_router, log_router, commands, ws_router, messages_router, config_router, metrics_router, canned_router
```

Aggiungi `module_config_router` alla fine dell'import:
```python
from routers import nodes, map_router, log_router, commands, ws_router, messages_router, config_router, metrics_router, canned_router, module_config_router
```

Aggiungi dopo `app.include_router(canned_router.router)`:
```python
app.include_router(module_config_router.router)
```

- [ ] **Step 3: Commit**

```bash
git add routers/module_config_router.py main.py
git commit -m "feat(modules): add module_config_router with 18 API endpoints"
```

---

### Task 3: config.html — 9 nuove sezioni

**Files:**
- Modify: `templates/config.html`

- [ ] **Step 1: Aggiungi 9 voci alla sidebar `sections`**

Trova:
```javascript
{ id: 'canned',   label: 'Canned' },
```

Aggiungi dopo:
```javascript
{ id: 'extnotif', label: 'ExtNotif' },
{ id: 'sf',       label: 'S&F' },
{ id: 'telmod',   label: 'Telemetry' },
{ id: 'cannedmod',label: 'CannedMod' },
{ id: 'rangetest',label: 'RangeTest' },
{ id: 'detsensor',label: 'DetSensor' },
{ id: 'ambilight',label: 'AmbLight' },
{ id: 'neighinfo', label: 'Neighbor' },
{ id: 'serial',   label: 'Serial' },
```

- [ ] **Step 2: Aggiungi dati Alpine per tutti i moduli in `configPage()`**

Nel blocco `data`:
```javascript
extNotif: {}, storeForward: {}, telMod: {}, cannedMod: {},
rangeTest: {}, detSensor: {}, ambLight: {}, neighInfo: {}, serialMod: {},
moduleStatus: '',
```

Aggiungi metodo helper e loader per ogni modulo:
```javascript
async saveModule(endpoint, data) {
  const r = await fetch(endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  })
  this.moduleStatus = r.ok ? '✓ Salvato' : '✗ Errore'
  setTimeout(() => { this.moduleStatus = '' }, 2000)
},

async loadExtNotif() {
  const r = await fetch('/api/config/module/external-notification')
  if (r.ok) this.extNotif = await r.json()
},
async loadStoreForward() {
  const r = await fetch('/api/config/module/store-forward')
  if (r.ok) this.storeForward = await r.json()
},
async loadTelMod() {
  const r = await fetch('/api/config/module/telemetry')
  if (r.ok) this.telMod = await r.json()
},
async loadCannedMod() {
  const r = await fetch('/api/config/module/canned-message')
  if (r.ok) this.cannedMod = await r.json()
},
async loadRangeTest() {
  const r = await fetch('/api/config/module/range-test')
  if (r.ok) this.rangeTest = await r.json()
},
async loadDetSensor() {
  const r = await fetch('/api/config/module/detection-sensor')
  if (r.ok) this.detSensor = await r.json()
},
async loadAmbLight() {
  const r = await fetch('/api/config/module/ambient-lighting')
  if (r.ok) this.ambLight = await r.json()
},
async loadNeighInfo() {
  const r = await fetch('/api/config/module/neighbor-info')
  if (r.ok) this.neighInfo = await r.json()
},
async loadSerialMod() {
  const r = await fetch('/api/config/module/serial')
  if (r.ok) this.serialMod = await r.json()
},
```

Nella funzione `selectSection(id)`, aggiungi i lazy-load:
```javascript
if (id === 'extnotif')  await this.loadExtNotif()
if (id === 'sf')        await this.loadStoreForward()
if (id === 'telmod')    await this.loadTelMod()
if (id === 'cannedmod') await this.loadCannedMod()
if (id === 'rangetest') await this.loadRangeTest()
if (id === 'detsensor') await this.loadDetSensor()
if (id === 'ambilight') await this.loadAmbLight()
if (id === 'neighinfo') await this.loadNeighInfo()
if (id === 'serial')    await this.loadSerialMod()
```

- [ ] **Step 3: Aggiungi blocchi HTML per ogni sezione**

Aggiungi prima dell'ultimo `</div>` che chiude il `<!-- CONTENT AREA -->`:

**External Notifications:**
```html
<template x-if="section === 'extnotif'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">External Notifications</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;">
        <input type="checkbox" x-model="extNotif.enabled"> Abilitato
      </label>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Output Pin GPIO</label>
        <input type="number" x-model.number="extNotif.output_pin" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:80px;">
      </div>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;">
        <input type="checkbox" x-model="extNotif.active_high"> Active High
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;">
        <input type="checkbox" x-model="extNotif.alert_message"> Alert su messaggio
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;">
        <input type="checkbox" x-model="extNotif.alert_bell"> Alert su bell
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;">
        <input type="checkbox" x-model="extNotif.use_pwm"> Usa PWM
      </label>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Nag timeout (ms)</label>
        <input type="number" x-model.number="extNotif.nag_timeout" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:100px;">
      </div>
      <button @click="saveModule('/api/config/module/external-notification', extNotif)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">
        Salva
      </button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Store & Forward:**
```html
<template x-if="section === 'sf'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Store &amp; Forward</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="storeForward.enabled"> Abilitato</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="storeForward.heartbeat"> Heartbeat</label>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">History return max</label>
        <input type="number" x-model.number="storeForward.history_return_max" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:80px;">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">History return window (s)</label>
        <input type="number" x-model.number="storeForward.history_return_window" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:100px;">
      </div>
      <button @click="saveModule('/api/config/module/store-forward', storeForward)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Telemetry:**
```html
<template x-if="section === 'telmod'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Telemetry Module</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Device update interval (s, 0=default)</label>
        <input type="number" x-model.number="telMod.device_update_interval" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:100px;">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Environment update interval (s, 0=default)</label>
        <input type="number" x-model.number="telMod.environment_update_interval" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:100px;">
      </div>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="telMod.environment_measurement_enabled"> Environment sensors</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="telMod.air_quality_enabled"> Air quality</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="telMod.power_measurement_enabled"> Power measurement</label>
      <button @click="saveModule('/api/config/module/telemetry', telMod)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Canned Message Module (board-side):**
```html
<template x-if="section === 'cannedmod'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Canned Message Module</div>
    <div style="font-size:10px;color:var(--muted);margin-bottom:8px;">Configurazione lato board (encoder rotativo, bell). Per gestire i testi vedi Config → Canned.</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="cannedMod.rotary1_enabled"> Rotary encoder</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="cannedMod.send_bell"> Invia bell</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="cannedMod.free_text_sms_enabled"> Free text SMS</label>
      <button @click="saveModule('/api/config/module/canned-message', cannedMod)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Range Test:**
```html
<template x-if="section === 'rangetest'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Range Test</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="rangeTest.enabled"> Abilitato</label>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Sender interval (s, 0=off)</label>
        <input type="number" x-model.number="rangeTest.sender" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:80px;">
      </div>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="rangeTest.save"> Salva risultati su flash</label>
      <button @click="saveModule('/api/config/module/range-test', rangeTest)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Detection Sensor:**
```html
<template x-if="section === 'detsensor'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Detection Sensor</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="detSensor.enabled"> Abilitato</label>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Nome sensore</label>
        <input x-model="detSensor.name" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Monitor pin GPIO</label>
        <input type="number" x-model.number="detSensor.monitor_pin" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:80px;">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Min broadcast (s)</label>
        <input type="number" x-model.number="detSensor.minimum_broadcast_secs" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:80px;">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">State broadcast (s)</label>
        <input type="number" x-model.number="detSensor.state_broadcast_secs" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:80px;">
      </div>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="detSensor.use_pullup"> Pull-up interno</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="detSensor.detection_triggered_high"> Triggered HIGH</label>
      <button @click="saveModule('/api/config/module/detection-sensor', detSensor)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Ambient Lighting:**
```html
<template x-if="section === 'ambilight'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Ambient Lighting (NeoPixel)</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="ambLight.led_state"> LED acceso</label>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Corrente (0-31)</label>
        <input type="number" min="0" max="31" x-model.number="ambLight.current" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:70px;">
      </div>
      <div style="display:flex;gap:8px;">
        <div style="display:flex;flex-direction:column;gap:3px;">
          <label style="font-size:10px;color:var(--muted);">R</label>
          <input type="number" min="0" max="255" x-model.number="ambLight.red" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:65px;">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px;">
          <label style="font-size:10px;color:var(--muted);">G</label>
          <input type="number" min="0" max="255" x-model.number="ambLight.green" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:65px;">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px;">
          <label style="font-size:10px;color:var(--muted);">B</label>
          <input type="number" min="0" max="255" x-model.number="ambLight.blue" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:65px;">
        </div>
      </div>
      <button @click="saveModule('/api/config/module/ambient-lighting', ambLight)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Neighbor Info:**
```html
<template x-if="section === 'neighinfo'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Neighbor Info</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="neighInfo.enabled"> Abilitato</label>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Update interval (s, 0=default)</label>
        <input type="number" x-model.number="neighInfo.update_interval" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:100px;">
      </div>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="neighInfo.transmit_over_lora"> Trasmetti su LoRa</label>
      <button @click="saveModule('/api/config/module/neighbor-info', neighInfo)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

**Serial:**
```html
<template x-if="section === 'serial'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">Serial Module</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="serialMod.enabled"> Abilitato</label>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="serialMod.echo"> Echo</label>
      <div style="display:flex;gap:8px;">
        <div style="display:flex;flex-direction:column;gap:3px;">
          <label style="font-size:10px;color:var(--muted);">RXD pin</label>
          <input type="number" x-model.number="serialMod.rxd" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:70px;">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px;">
          <label style="font-size:10px;color:var(--muted);">TXD pin</label>
          <input type="number" x-model.number="serialMod.txd" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:70px;">
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Timeout (ms)</label>
        <input type="number" x-model.number="serialMod.timeout" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;width:100px;">
      </div>
      <div style="display:flex;flex-direction:column;gap:3px;">
        <label style="font-size:10px;color:var(--muted);">Mode</label>
        <select x-model="serialMod.mode" style="background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
          <option>DEFAULT</option><option>SIMPLE</option><option>PROTO</option>
          <option>TEXTMSG</option><option>NMEA</option><option>CALTOPO</option>
        </select>
      </div>
      <label style="display:flex;align-items:center;gap:8px;font-size:12px;"><input type="checkbox" x-model="serialMod.override_console_serial_port"> Override console serial</label>
      <button @click="saveModule('/api/config/module/serial', serialMod)"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 14px;font-size:12px;cursor:pointer;align-self:flex-start;">Salva</button>
      <div x-show="moduleStatus" x-text="moduleStatus" style="font-size:10px;color:#4caf50;"></div>
    </div>
  </div>
</template>
```

- [ ] **Step 4: Commit**

```bash
git add templates/config.html
git commit -m "feat(modules): add 9 module config sections to config page"
```

---

### Task 4: Deploy e verifica su Pi

- [ ] **Step 1: Deploy**

```bash
sshpass -p pimesh rsync -avz --relative \
  meshtasticd_client.py routers/module_config_router.py \
  main.py templates/config.html \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Verifica API**

```bash
curl http://192.168.1.36:8080/api/config/module/store-forward
# Expected: {"enabled":false/true,"heartbeat":...,"cached":false/true}

curl http://192.168.1.36:8080/api/config/module/telemetry
# Expected: {"device_update_interval":N,...}
```

- [ ] **Step 3: Verifica UI**

Apri `http://192.168.1.36:8080/config` → verifica che le 9 nuove voci appaiano nella sidebar → clicca ognuna → verifica che i campi si carichino (o mostrino default se board offline).

- [ ] **Step 4: Commit finale**

```bash
git add -A
git commit -m "feat: M8 complete — module configs (YAY-169)"
```
