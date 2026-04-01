# routers/config_router.py
import os
import subprocess
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config as cfg
import database
import meshtasticd_client
import usb_storage

router = APIRouter()
templates = Jinja2Templates(directory='templates')

# Module-level constant for config file path
CONFIG_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.env')

# I2C address lookup table
_I2C_KNOWN = {
    '0x76': 'BME280', '0x77': 'BMP280/BME280',
    '0x68': 'DS3231', '0x6f': 'DS1307',
    '0x3c': 'SSD1306', '0x3d': 'SSD1306',
    '0x44': 'SHT31', '0x45': 'SHT31',
    '0x38': 'AHT20', '0x40': 'HTU21D',
}


def _write_env(key: str, value: str) -> None:
    """Write or update a KEY=value line in config.env."""
    path = CONFIG_ENV_PATH
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f'{key}=') or line.startswith(f'{key} ='):
            new_lines.append(f'{key}={value}\n')
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f'{key}={value}\n')
    with open(path, 'w') as f:
        f.writelines(new_lines)


@router.get('/config', response_class=HTMLResponse)
async def config_page(request: Request):
    gpio = await database.get_gpio_devices(cfg.DB_PATH)
    return templates.TemplateResponse(request, 'config.html', {
        'active_tab': 'config',
        'gpio_devices': gpio,
    })


@router.get('/api/config/node')
async def get_node_config():
    return await meshtasticd_client.get_node_config(cfg.DB_PATH)


class NodeConfigRequest(BaseModel):
    long_name: str
    short_name: str
    role: str


@router.post('/api/config/node')
async def post_node_config(body: NodeConfigRequest):
    try:
        await meshtasticd_client.set_node_config(body.long_name, body.short_name, body.role)
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


@router.get('/api/config/lora')
async def get_lora_config():
    return await meshtasticd_client.get_lora_config(cfg.DB_PATH)


class LoraConfigRequest(BaseModel):
    region: str
    modem_preset: str


@router.post('/api/config/lora')
async def post_lora_config(body: LoraConfigRequest):
    try:
        await meshtasticd_client.set_lora_config(body.region, body.modem_preset)
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


@router.get('/api/config/channels')
async def get_channels():
    return await meshtasticd_client.get_channels(cfg.DB_PATH)


class ChannelRequest(BaseModel):
    name: str
    psk_b64: str = ''


@router.post('/api/config/channels/{idx}')
async def post_channel(idx: int, body: ChannelRequest):
    try:
        await meshtasticd_client.set_channel(idx, body.name, body.psk_b64)
        return {'ok': True}
    except RuntimeError as e:
        return JSONResponse({'error': str(e)}, status_code=503)


@router.get('/api/config/gpio')
async def get_gpio():
    return await database.get_gpio_devices(cfg.DB_PATH)


class GpioDeviceRequest(BaseModel):
    type: str
    name: str
    enabled: int = 1
    pin_a: int | None = None
    pin_b: int | None = None
    pin_sw: int | None = None
    i2c_bus: int = 1
    i2c_address: str | None = None
    sensor_type: str | None = None
    action: str | None = None
    config_json: str = '{}'


@router.post('/api/config/gpio')
async def add_gpio(body: GpioDeviceRequest):
    dev_id = await database.add_gpio_device(cfg.DB_PATH, body.model_dump())
    return {'id': dev_id}


@router.put('/api/config/gpio/{dev_id}')
async def update_gpio(dev_id: int, body: GpioDeviceRequest):
    await database.update_gpio_device(cfg.DB_PATH, dev_id, body.model_dump())
    return {'ok': True}


@router.delete('/api/config/gpio/{dev_id}')
async def delete_gpio(dev_id: int):
    await database.delete_gpio_device(cfg.DB_PATH, dev_id)
    return {'ok': True}


@router.post('/api/config/gpio/{dev_id}/test')
async def test_gpio(dev_id: int):
    devices = await database.get_gpio_devices(cfg.DB_PATH)
    dev = next((d for d in devices if d['id'] == dev_id), None)
    if dev is None:
        return JSONResponse({'error': 'Device not found'}, status_code=404)
    try:
        result = _test_device(dev)
        return {'ok': True, 'result': result}
    except Exception as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)


def _test_device(dev: dict) -> str:
    dtype = dev['type']
    if dtype in ('i2c_sensor', 'rtc'):
        import smbus2
        bus = smbus2.SMBus(dev['i2c_bus'])
        addr = int(dev['i2c_address'], 16)
        val = bus.read_byte(addr)
        bus.close()
        return f'read byte: 0x{val:02x}'
    elif dtype == 'buzzer':
        import RPi.GPIO as GPIO
        pin = dev['pin_a']
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)
        import time
        time.sleep(0.2)
        GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup(pin)
        return 'buzz OK'
    elif dtype == 'led':
        import RPi.GPIO as GPIO
        pin = dev['pin_a']
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        for _ in range(3):
            GPIO.output(pin, GPIO.HIGH)
            import time; time.sleep(0.1)
            GPIO.output(pin, GPIO.LOW)
            time.sleep(0.1)
        GPIO.cleanup(pin)
        return 'blink OK'
    elif dtype == 'encoder':
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(dev['pin_a'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(dev['pin_b'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        a = GPIO.input(dev['pin_a'])
        b = GPIO.input(dev['pin_b'])
        GPIO.cleanup([dev['pin_a'], dev['pin_b']])
        return f'pin_a={a} pin_b={b}'
    elif dtype == 'button':
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(dev['pin_a'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        val = GPIO.input(dev['pin_a'])
        GPIO.cleanup(dev['pin_a'])
        return f'state={val}'
    return 'unknown type'


def _parse_i2cdetect(output: str) -> list[dict]:
    """Parse i2cdetect -y N output into list of {address, known_device}."""
    found = []
    for line in output.splitlines():
        parts = line.split()
        if not parts or not parts[0].endswith(':'):
            continue
        row_base = int(parts[0].rstrip(':'), 16)
        for col, cell in enumerate(parts[1:]):
            if cell not in ('--', 'UU') and len(cell) == 2:
                try:
                    addr_int = row_base + col
                    addr_str = f'0x{addr_int:02x}'
                    known = _I2C_KNOWN.get(addr_str, '')
                    found.append({'address': addr_str, 'known_device': known})
                except ValueError:
                    pass
    return found


@router.get('/api/config/i2c-scan')
async def i2c_scan(bus: int = 1):
    try:
        result = subprocess.run(
            ['i2cdetect', '-y', str(bus)],
            capture_output=True, text=True, timeout=5
        )
        return _parse_i2cdetect(result.stdout)
    except FileNotFoundError:
        return JSONResponse({'error': 'i2cdetect not found — install i2c-tools'}, status_code=500)
    except subprocess.TimeoutExpired:
        return JSONResponse({'error': 'i2cdetect timeout'}, status_code=500)


@router.get('/api/config/wifi/scan')
async def wifi_scan():
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
            capture_output=True, text=True, timeout=10
        )
        networks = []
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 3 and parts[0]:
                networks.append({
                    'ssid': parts[0],
                    'signal': int(parts[1]) if parts[1].isdigit() else 0,
                    'security': parts[2],
                })
        return networks
    except FileNotFoundError:
        return JSONResponse({'error': 'nmcli not found'}, status_code=500)


class WifiConnectRequest(BaseModel):
    ssid: str
    password: str


@router.post('/api/config/wifi/connect')
async def wifi_connect(body: WifiConnectRequest):
    try:
        result = subprocess.run(
            ['nmcli', 'dev', 'wifi', 'connect', body.ssid, 'password', body.password],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return {'ok': True}
        return JSONResponse({'error': result.stderr.strip()}, status_code=500)
    except FileNotFoundError:
        return JSONResponse({'error': 'nmcli not found'}, status_code=500)


@router.get('/api/config/wifi/status')
async def wifi_status():
    """Return current WiFi connection status: SSID, IP, signal, method."""
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,DEVICE,TYPE', 'con', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )
        active_ssid = ''
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 3 and parts[2] == '802-11-wireless':
                active_ssid = parts[0]
                break

        ip_addr = ''
        method = 'auto'
        if active_ssid:
            r2 = subprocess.run(
                ['nmcli', '-t', '-f', 'IP4.ADDRESS,ipv4.method', 'con', 'show', active_ssid],
                capture_output=True, text=True, timeout=10
            )
            for line in r2.stdout.splitlines():
                if line.startswith('IP4.ADDRESS'):
                    ip_addr = line.split(':', 1)[1].strip()
                elif line.startswith('ipv4.method'):
                    method = line.split(':', 1)[1].strip()

        return {
            'connected': bool(active_ssid),
            'ssid': active_ssid,
            'ip': ip_addr,
            'method': method,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {'connected': False, 'ssid': '', 'ip': '', 'method': 'auto'}


@router.get('/api/config/wifi/saved')
async def wifi_saved():
    """Return list of saved WiFi connection profiles."""
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'],
            capture_output=True, text=True, timeout=10
        )
        saved = []
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and parts[1] == '802-11-wireless':
                saved.append(parts[0])
        return saved
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


@router.delete('/api/config/wifi/saved/{name}')
async def wifi_delete_saved(name: str):
    """Delete a saved WiFi connection profile."""
    try:
        result = subprocess.run(
            ['nmcli', 'con', 'delete', name],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return {'ok': True}
        return JSONResponse({'error': result.stderr.strip()}, status_code=500)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return JSONResponse({'error': str(e)}, status_code=500)


class WifiIpRequest(BaseModel):
    method: str  # 'auto' or 'manual'
    address: str = ''
    gateway: str = ''
    dns: str = ''


@router.post('/api/config/wifi/ip')
async def wifi_set_ip(body: WifiIpRequest):
    """Set IP configuration (DHCP or static) on active WiFi connection."""
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )
        con_name = ''
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and parts[1] == '802-11-wireless':
                con_name = parts[0]
                break
        if not con_name:
            return JSONResponse({'error': 'No active WiFi connection'}, status_code=400)

        if body.method == 'auto':
            subprocess.run(
                ['nmcli', 'con', 'mod', con_name, 'ipv4.method', 'auto',
                 'ipv4.addresses', '', 'ipv4.gateway', '', 'ipv4.dns', ''],
                capture_output=True, text=True, timeout=10
            )
        else:
            if not body.address or not body.gateway:
                return JSONResponse({'error': 'Address and gateway required for static IP'}, status_code=400)
            cmd = ['nmcli', 'con', 'mod', con_name,
                   'ipv4.method', 'manual',
                   'ipv4.addresses', body.address,
                   'ipv4.gateway', body.gateway]
            if body.dns:
                cmd += ['ipv4.dns', body.dns]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        subprocess.run(
            ['nmcli', 'con', 'up', con_name],
            capture_output=True, text=True, timeout=15
        )
        return {'ok': True}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get('/api/config/rtc/status')
async def rtc_status():
    config_paths = ['/boot/firmware/config.txt', '/boot/config.txt']
    configured = False
    model = None
    for path in config_paths:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('dtoverlay=i2c-rtc'):
                        configured = True
                        parts = line.split(',')
                        if len(parts) >= 2 and parts[1].strip():
                            model = parts[1].strip()
                        break
            break
        except (FileNotFoundError, PermissionError, OSError):
            continue

    device = '/dev/rtc0' if os.path.exists('/dev/rtc0') else None

    time_str = None
    if device:
        try:
            result = subprocess.run(
                ['hwclock', '-r', '--rtc=/dev/rtc0'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                time_str = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return {
        'configured': configured,
        'model': model,
        'device': device,
        'time': time_str,
    }


@router.post('/api/system/reboot')
async def system_reboot():
    subprocess.Popen(['sudo', 'reboot'])
    return {'ok': True, 'action': 'reboot'}


@router.post('/api/system/shutdown')
async def system_shutdown():
    subprocess.Popen(['sudo', 'shutdown', '-h', 'now'])
    return {'ok': True, 'action': 'shutdown'}


class MapConfigRequest(BaseModel):
    local_tiles: bool


@router.get('/api/config/map')
async def get_map_config():
    tiles_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'tiles', 'osm')
    tiles_present = os.path.isdir(tiles_dir) and bool(os.listdir(tiles_dir))
    return {
        'local_tiles': cfg.MAP_LOCAL_TILES,
        'region': cfg.MAP_REGION,
        'tiles_present': tiles_present,
    }


@router.post('/api/config/map')
async def post_map_config(body: MapConfigRequest):
    _write_env('MAP_LOCAL_TILES', '1' if body.local_tiles else '0')
    cfg.MAP_LOCAL_TILES = body.local_tiles
    return {'local_tiles': cfg.MAP_LOCAL_TILES, 'region': cfg.MAP_REGION}


class AlertConfigRequest(BaseModel):
    node_offline_min: int
    battery_low: int
    ram_high: int


@router.get('/api/config/alerts')
async def get_alert_config():
    return {
        'node_offline_min': cfg.ALERT_NODE_OFFLINE_MIN,
        'battery_low': cfg.ALERT_BATTERY_LOW,
        'ram_high': cfg.ALERT_RAM_HIGH,
    }


@router.post('/api/config/alerts')
async def post_alert_config(body: AlertConfigRequest):
    _write_env('ALERT_NODE_OFFLINE_MIN', str(body.node_offline_min))
    _write_env('ALERT_BATTERY_LOW', str(body.battery_low))
    _write_env('ALERT_RAM_HIGH', str(body.ram_high))
    cfg.ALERT_NODE_OFFLINE_MIN = body.node_offline_min
    cfg.ALERT_BATTERY_LOW = body.battery_low
    cfg.ALERT_RAM_HIGH = body.ram_high
    return {'ok': True}


# --- USB Storage ---

_TILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'tiles')


@router.get('/api/config/usb/status')
async def usb_status():
    status = usb_storage.get_usb_status()
    status['tiles_location'] = usb_storage.get_tiles_location(_TILES_DIR)
    return status


@router.post('/api/config/usb/move-tiles')
async def usb_move_tiles():
    result = usb_storage.move_tiles_to_usb(_TILES_DIR)
    if not result['ok']:
        return JSONResponse(result, status_code=400)
    return result


@router.post('/api/config/usb/restore-tiles')
async def usb_restore_tiles():
    result = usb_storage.restore_tiles_to_sd(_TILES_DIR)
    if not result['ok']:
        return JSONResponse(result, status_code=400)
    return result
