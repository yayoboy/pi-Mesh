"""Service layer: replaces httpx calls to localhost:8080 with direct backend calls.

All public functions are synchronous. Async database/client functions are
bridged via _run_async(), which submits work to a dedicated thread that owns
its own event loop so it never conflicts with the qasync loop running in the
Qt main thread.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import subprocess
import threading
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Async bridge
# ---------------------------------------------------------------------------

# A dedicated background thread with its own event loop handles all async
# calls.  This avoids the "cannot run nested event loop" problem that would
# occur if we tried to use run_until_complete() on the already-running qasync
# loop.

_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_lock = threading.Lock()


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop
    with _bg_lock:
        if _bg_loop is None or not _bg_loop.is_running():
            loop = asyncio.new_event_loop()
            t = threading.Thread(target=loop.run_forever, daemon=True,
                                 name="backend-async")
            t.start()
            _bg_loop = loop
        return _bg_loop


def _run_async(coro) -> Any:
    """Submit an async coroutine to the background loop and wait for result."""
    loop = _get_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=15)


# ---------------------------------------------------------------------------
# Lazy imports (modules live in the pi-Mesh root, not the gui/ package)
# ---------------------------------------------------------------------------

def _import_database():
    import database  # noqa: PLC0415
    return database


def _import_meshtasticd_client():
    import meshtasticd_client  # noqa: PLC0415
    return meshtasticd_client


def _import_cfg():
    import config as cfg  # noqa: PLC0415
    return cfg


def _import_bots_runner():
    from bots import runner  # noqa: PLC0415
    return runner


def _import_usb_storage():
    import usb_storage  # noqa: PLC0415
    return usb_storage


def _import_mqtt_bridge():
    import mqtt_bridge  # noqa: PLC0415
    return mqtt_bridge


# ---------------------------------------------------------------------------
# Config.env writer (mirrors config_router._write_env)
# ---------------------------------------------------------------------------

_CONFIG_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'config.env'
)


def _write_env(key: str, value: str) -> None:
    path = _CONFIG_ENV_PATH
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


# ---------------------------------------------------------------------------
# Database wrappers
# ---------------------------------------------------------------------------

def get_setting(key: str, default=None):
    try:
        return _run_async(_import_database().get_setting(key, default))
    except Exception as e:
        log.warning("get_setting(%r) failed: %s", key, e)
        return default


def set_setting(key: str, value: str) -> None:
    try:
        _run_async(_import_database().set_setting(key, value))
    except Exception as e:
        log.warning("set_setting(%r) failed: %s", key, e)


def get_waypoints(active_only: bool = True) -> list:
    try:
        return _run_async(_import_database().get_waypoints(active_only)) or []
    except Exception as e:
        log.warning("get_waypoints() failed: %s", e)
        return []


def upsert_waypoint(wp: dict) -> None:
    try:
        _run_async(_import_database().upsert_waypoint(wp))
    except Exception as e:
        log.warning("upsert_waypoint() failed: %s", e)


def delete_waypoint(wp_id: int) -> None:
    try:
        _run_async(_import_database().delete_waypoint(wp_id))
    except Exception as e:
        log.warning("delete_waypoint(%r) failed: %s", wp_id, e)


def get_markers() -> list:
    try:
        cfg = _import_cfg()
        return _run_async(_import_database().get_markers(cfg.DB_PATH)) or []
    except Exception as e:
        log.warning("get_markers() failed: %s", e)
        return []


def create_marker(label: str, icon_type: str, lat: float, lon: float,
                  notes: str = "") -> dict | None:
    try:
        cfg = _import_cfg()
        return _run_async(
            _import_database().create_marker(cfg.DB_PATH, label, icon_type, lat, lon, notes)
        )
    except Exception as e:
        log.warning("create_marker() failed: %s", e)
        return None


def delete_marker(marker_id: int) -> bool:
    try:
        cfg = _import_cfg()
        return _run_async(_import_database().delete_marker(cfg.DB_PATH, marker_id))
    except Exception as e:
        log.warning("delete_marker(%r) failed: %s", marker_id, e)
        return False


def get_neighbor_info() -> list:
    try:
        return _run_async(_import_database().get_neighbor_info()) or []
    except Exception as e:
        log.warning("get_neighbor_info() failed: %s", e)
        return []


def get_canned_messages() -> list:
    try:
        return _run_async(_import_database().get_canned_messages()) or []
    except Exception as e:
        log.warning("get_canned_messages() failed: %s", e)
        return []


def add_canned_message(text: str, sort_order: int = 0) -> int | None:
    try:
        return _run_async(_import_database().add_canned_message(text, sort_order))
    except Exception as e:
        log.warning("add_canned_message() failed: %s", e)
        return None


def update_canned_message(msg_id: int, text: str, sort_order: int) -> None:
    try:
        _run_async(_import_database().update_canned_message(msg_id, text, sort_order))
    except Exception as e:
        log.warning("update_canned_message(%r) failed: %s", msg_id, e)


def delete_canned_message(msg_id: int) -> None:
    try:
        _run_async(_import_database().delete_canned_message(msg_id))
    except Exception as e:
        log.warning("delete_canned_message(%r) failed: %s", msg_id, e)


def get_telemetry(node_id=None, ttype=None, limit: int = 100) -> list:
    try:
        cfg = _import_cfg()
        return _run_async(
            _import_database().get_telemetry(cfg.DB_PATH, node_id, ttype, limit)
        ) or []
    except Exception as e:
        log.warning("get_telemetry() failed: %s", e)
        return []


def export_telemetry(fmt: str, limit: int = 1000) -> str | bytes | None:
    """Return telemetry as CSV or JSON string."""
    try:
        rows = get_telemetry(limit=limit)
        if fmt == 'json':
            import json
            return json.dumps(rows, indent=2)
        # csv
        import csv
        import io
        if not rows:
            return ''
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()
    except Exception as e:
        log.warning("export_telemetry() failed: %s", e)
        return None


def get_gpio_devices() -> list:
    try:
        cfg = _import_cfg()
        return _run_async(_import_database().get_gpio_devices(cfg.DB_PATH)) or []
    except Exception as e:
        log.warning("get_gpio_devices() failed: %s", e)
        return []


def add_gpio_device(device: dict) -> int | None:
    try:
        cfg = _import_cfg()
        return _run_async(_import_database().add_gpio_device(cfg.DB_PATH, device))
    except Exception as e:
        log.warning("add_gpio_device() failed: %s", e)
        return None


def update_gpio_device(dev_id: int, device: dict) -> None:
    try:
        cfg = _import_cfg()
        _run_async(_import_database().update_gpio_device(cfg.DB_PATH, dev_id, device))
    except Exception as e:
        log.warning("update_gpio_device(%r) failed: %s", dev_id, e)


def delete_gpio_device(dev_id: int) -> None:
    try:
        cfg = _import_cfg()
        _run_async(_import_database().delete_gpio_device(cfg.DB_PATH, dev_id))
    except Exception as e:
        log.warning("delete_gpio_device(%r) failed: %s", dev_id, e)


def test_gpio(dev_id: int) -> dict:
    """Test a GPIO device (buzzer beep, LED blink, sensor read, etc.)."""
    try:
        devices = get_gpio_devices()
        dev = next((d for d in devices if d.get("id") == dev_id), None)
        if dev is None:
            return {"ok": False, "error": "Device not found"}
        dtype = dev.get("type", "")
        if dtype in ("i2c_sensor", "rtc"):
            import smbus2
            bus = smbus2.SMBus(dev["i2c_bus"])
            addr = int(dev["i2c_address"], 16)
            val = bus.read_byte(addr)
            bus.close()
            return {"ok": True, "result": f"read byte: 0x{val:02x}"}
        elif dtype == "buzzer":
            import RPi.GPIO as GPIO
            import time
            pin = dev["pin_a"]
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
            time.sleep(0.2)
            GPIO.output(pin, GPIO.LOW)
            GPIO.cleanup(pin)
            return {"ok": True, "result": "buzz OK"}
        elif dtype == "led":
            import RPi.GPIO as GPIO
            import time
            pin = dev["pin_a"]
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            for _ in range(3):
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(0.1)
                GPIO.output(pin, GPIO.LOW)
                time.sleep(0.1)
            GPIO.cleanup(pin)
            return {"ok": True, "result": "blink OK"}
        elif dtype == "encoder":
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(dev["pin_a"], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(dev["pin_b"], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            a = GPIO.input(dev["pin_a"])
            b = GPIO.input(dev["pin_b"])
            GPIO.cleanup([dev["pin_a"], dev["pin_b"]])
            return {"ok": True, "result": f"pin_a={a} pin_b={b}"}
        elif dtype == "button":
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(dev["pin_a"], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            val = GPIO.input(dev["pin_a"])
            GPIO.cleanup(dev["pin_a"])
            return {"ok": True, "result": f"state={val}"}
        return {"ok": False, "error": "unknown type"}
    except Exception as e:
        log.warning("test_gpio(%r) failed: %s", dev_id, e)
        return {"ok": False, "error": str(e)}


def get_messages(limit: int = 100) -> list:
    try:
        cfg = _import_cfg()
        return _run_async(_import_database().get_messages(cfg.DB_PATH, limit=limit)) or []
    except Exception as e:
        log.warning("get_messages() failed: %s", e)
        return []


def clear_messages() -> None:
    try:
        cfg = _import_cfg()
        _run_async(_import_database().clear_messages(cfg.DB_PATH))
    except Exception as e:
        log.warning("clear_messages() failed: %s", e)


def get_total_unread() -> int:
    try:
        client = _import_meshtasticd_client()
        local_id = client.get_local_id()
        cfg = _import_cfg()
        return _run_async(_import_database().get_total_unread(cfg.DB_PATH, local_id)) or 0
    except Exception as e:
        log.warning("get_total_unread() failed: %s", e)
        return 0


def delete_node(node_id: str) -> None:
    try:
        cfg = _import_cfg()
        _run_async(_import_database().delete_node(cfg.DB_PATH, node_id))
    except Exception as e:
        log.warning("delete_node(%r) failed: %s", node_id, e)


# ---------------------------------------------------------------------------
# WiFi (subprocess via nmcli)
# ---------------------------------------------------------------------------

def wifi_scan() -> list:
    try:
        result = subprocess.run(
            ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi',
             'list', '--rescan', 'yes'],
            capture_output=True, text=True, timeout=15
        )
        best: dict[str, dict] = {}
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 3 and parts[0] and parts[0] != '--':
                ssid = parts[0]
                try:
                    signal = int(parts[1])
                except ValueError:
                    signal = 0
                if ssid not in best or signal > best[ssid]['signal']:
                    best[ssid] = {'ssid': ssid, 'signal': signal, 'security': parts[2]}
        return sorted(best.values(), key=lambda n: n['signal'], reverse=True)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("wifi_scan() failed: %s", e)
        return []


def wifi_status() -> dict:
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE,STATE,DEVICE', 'con', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 3 and parts[1] == '802-11-wireless':
                con_name = parts[0]
                # Get IP details
                detail = subprocess.run(
                    ['nmcli', '-t', '-f', 'IP4.ADDRESS,IP4.GATEWAY,GENERAL.DEVICE',
                     'con', 'show', con_name],
                    capture_output=True, text=True, timeout=5
                )
                ip = ''
                gateway = ''
                device = ''
                for dline in detail.stdout.splitlines():
                    if dline.startswith('IP4.ADDRESS'):
                        ip = dline.split(':', 1)[1]
                    elif dline.startswith('IP4.GATEWAY'):
                        gateway = dline.split(':', 1)[1]
                    elif dline.startswith('GENERAL.DEVICE'):
                        device = dline.split(':', 1)[1]
                return {
                    'connected': True,
                    'ssid': con_name,
                    'ip': ip,
                    'gateway': gateway,
                    'device': device,
                }
        return {'connected': False}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("wifi_status() failed: %s", e)
        return {'connected': False}


def wifi_connect(ssid: str, password: str) -> dict:
    try:
        result = subprocess.run(
            ['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return {'ok': True}
        return {'ok': False, 'error': result.stderr.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("wifi_connect() failed: %s", e)
        return {'ok': False, 'error': str(e)}


def wifi_saved() -> list:
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'],
            capture_output=True, text=True, timeout=10
        )
        names = []
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and parts[1] == '802-11-wireless':
                names.append(parts[0])
        saved = []
        for name in names:
            detail = subprocess.run(
                ['sudo', 'nmcli', '-s', '-t', '-f',
                 '802-11-wireless.ssid,802-11-wireless-security.psk',
                 'con', 'show', name],
                capture_output=True, text=True, timeout=5
            )
            ssid = name
            psk = ''
            for dline in detail.stdout.splitlines():
                if dline.startswith('802-11-wireless.ssid:'):
                    ssid = dline.split(':', 1)[1]
                elif dline.startswith('802-11-wireless-security.psk:'):
                    psk = dline.split(':', 1)[1]
            saved.append({'name': name, 'ssid': ssid, 'psk': psk})
        return saved
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("wifi_saved() failed: %s", e)
        return []


def wifi_delete_saved(name: str) -> dict:
    try:
        result = subprocess.run(
            ['nmcli', 'con', 'delete', name],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return {'ok': True}
        return {'ok': False, 'error': result.stderr.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("wifi_delete_saved(%r) failed: %s", name, e)
        return {'ok': False, 'error': str(e)}


def wifi_set_ip(mode: str, address: str | None = None, gateway: str | None = None,
                dns: str | None = None) -> dict:
    """Set static or DHCP IP on the active WiFi connection."""
    try:
        # Find active WiFi connection name
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )
        con_name = None
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and parts[1] == '802-11-wireless':
                con_name = parts[0]
                break
        if not con_name:
            return {'ok': False, 'error': 'No active WiFi connection'}

        if mode == 'dhcp':
            subprocess.run(
                ['nmcli', 'con', 'mod', con_name, 'ipv4.method', 'auto',
                 'ipv4.addresses', '', 'ipv4.gateway', '', 'ipv4.dns', ''],
                capture_output=True, text=True, timeout=10
            )
        else:
            if not address:
                return {'ok': False, 'error': 'address required for static mode'}
            args = ['nmcli', 'con', 'mod', con_name,
                    'ipv4.method', 'manual',
                    'ipv4.addresses', address]
            if gateway:
                args += ['ipv4.gateway', gateway]
            if dns:
                args += ['ipv4.dns', dns]
            subprocess.run(args, capture_output=True, text=True, timeout=10)

        subprocess.run(
            ['nmcli', 'con', 'up', con_name],
            capture_output=True, text=True, timeout=15
        )
        return {'ok': True}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("wifi_set_ip() failed: %s", e)
        return {'ok': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

_BACKLIGHT_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'scripts', 'backlight.sh'
)

_ROTATION_CALIBRATION = {
    0:   ('227 3936 268 3880', 0),
    90:  ('3936 227 268 3880', 1),
    180: ('3936 227 3880 268', 0),
    270: ('227 3936 3880 268', 1),
}

_CALIBRATION_CONF_TEMPLATE = '''\
Section "InputClass"
    Identifier "calibration"
    MatchProduct "ADS7846 Touchscreen"
    Option "Calibration" "{cal}"
    Option "SwapAxes" "{swap}"
EndSection
'''


def _apply_rotation_to_files(rotation: int) -> None:
    cal, swap = _ROTATION_CALIBRATION[rotation]
    subprocess.run(
        ['sudo', 'sed', '-i',
         f's/dtoverlay=tft35a:rotate=[0-9]*/dtoverlay=tft35a:rotate={rotation}/',
         '/boot/firmware/config.txt'],
        capture_output=True, text=True, timeout=10
    )
    if rotation in (0, 180):
        res = '320 480'
    else:
        res = '480 320'
    subprocess.run(
        ['sudo', 'sed', '-i',
         f's/hdmi_cvt [0-9]* [0-9]*/hdmi_cvt {res}/',
         '/boot/firmware/config.txt'],
        capture_output=True, text=True, timeout=10
    )
    conf_content = _CALIBRATION_CONF_TEMPLATE.format(cal=cal, swap=swap)
    subprocess.run(
        ['sudo', 'tee', '/etc/X11/xorg.conf.d/99-calibration.conf'],
        input=conf_content, capture_output=True, text=True, timeout=5
    )


def get_display_config() -> dict:
    brightness = get_setting('display.brightness', '255')
    rotation = get_setting('display.rotation', '0')
    return {'brightness': int(brightness), 'rotation': int(rotation)}


def set_display_config(brightness: int | None = None,
                       rotation: int | None = None) -> dict:
    result: dict = {'ok': True}
    if brightness is not None:
        brightness = max(0, min(255, brightness))
        set_setting('display.brightness', str(brightness))
        try:
            subprocess.run(
                ['bash', _BACKLIGHT_SCRIPT, str(brightness)],
                capture_output=True, text=True, timeout=5
            )
        except Exception:
            pass
        result['brightness'] = brightness
    if rotation is not None:
        if rotation not in (0, 90, 180, 270):
            return {'ok': False, 'error': 'rotation must be 0, 90, 180 or 270'}
        set_setting('display.rotation', str(rotation))
        try:
            _apply_rotation_to_files(rotation)
        except Exception:
            pass
        result['rotation'] = rotation
        result['reboot_required'] = True
    return result


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

def system_reboot() -> dict:
    subprocess.Popen(['sudo', 'reboot'])
    return {'ok': True, 'action': 'reboot'}


def factory_reset() -> dict:
    try:
        client = _import_meshtasticd_client()
        if not client.is_connected():
            return {'ok': False, 'error': 'Board not connected'}
        _run_async(client.factory_reset())
        return {'ok': True}
    except Exception as e:
        log.warning("factory_reset() failed: %s", e)
        return {'ok': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Access Point
# ---------------------------------------------------------------------------

def ap_status() -> dict:
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'con', 'show', '--active'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and 'wifi-p2p' in parts[1]:
                return {'active': True, 'name': parts[0]}
        hostapd = subprocess.run(
            ['systemctl', 'is-active', 'hostapd'],
            capture_output=True, text=True, timeout=5
        )
        if hostapd.stdout.strip() == 'active':
            return {'active': True, 'name': 'hostapd'}
        return {'active': False}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {'active': False}


def ap_toggle() -> dict:
    """Toggle AP mode using hostapd systemctl or nmcli hotspot."""
    try:
        hostapd = subprocess.run(
            ['systemctl', 'is-active', 'hostapd'],
            capture_output=True, text=True, timeout=5
        )
        if hostapd.stdout.strip() == 'active':
            subprocess.run(
                ['sudo', 'systemctl', 'stop', 'hostapd'],
                capture_output=True, text=True, timeout=10
            )
            return {'ok': True, 'active': False}
        else:
            subprocess.run(
                ['sudo', 'systemctl', 'start', 'hostapd'],
                capture_output=True, text=True, timeout=10
            )
            return {'ok': True, 'active': True}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("ap_toggle() failed: %s", e)
        return {'ok': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Hardware: I2C, RTC, Serial, USB
# ---------------------------------------------------------------------------

_I2C_KNOWN = {
    '0x76': 'BME280', '0x77': 'BMP280/BME280',
    '0x68': 'DS3231', '0x6f': 'DS1307',
    '0x3c': 'SSD1306', '0x3d': 'SSD1306',
    '0x44': 'SHT31', '0x45': 'SHT31',
    '0x38': 'AHT20', '0x40': 'HTU21D',
}


def _parse_i2cdetect(output: str) -> list[dict]:
    found = []
    for line in output.splitlines():
        parts = line.split()
        if not parts or not parts[0].endswith(':'):
            continue
        row_base = int(parts[0].rstrip(':'), 16)
        for col, cell in enumerate(parts[1:]):
            if cell not in ('--', 'UU', ''):
                try:
                    addr_int = row_base + col
                    addr_str = f'0x{addr_int:02x}'
                    known = _I2C_KNOWN.get(addr_str, '')
                    found.append({'address': addr_str, 'known_device': known})
                except ValueError:
                    pass
    return found


def i2c_scan(bus: int = 1) -> list:
    try:
        result = subprocess.run(
            ['i2cdetect', '-y', str(bus)],
            capture_output=True, text=True, timeout=10
        )
        return _parse_i2cdetect(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("i2c_scan() failed: %s", e)
        return []


def rtc_status() -> dict:
    try:
        # Check for known RTC modules
        rtc_result = subprocess.run(
            ['i2cdetect', '-y', '1'],
            capture_output=True, text=True, timeout=10
        )
        devices = _parse_i2cdetect(rtc_result.stdout)
        rtc_device = next(
            (d for d in devices if d['known_device'] in ('DS3231', 'DS1307')),
            None
        )
        configured = rtc_device is not None

        hw_time = ''
        try:
            hwclock = subprocess.run(
                ['sudo', 'hwclock', '-r'],
                capture_output=True, text=True, timeout=5
            )
            hw_time = hwclock.stdout.strip()
        except Exception:
            pass

        return {
            'configured': configured,
            'model': rtc_device['known_device'] if rtc_device else None,
            'device': rtc_device['address'] if rtc_device else None,
            'time': hw_time or None,
        }
    except Exception as e:
        log.warning("rtc_status() failed: %s", e)
        return {'configured': False, 'model': None, 'device': None, 'time': None}


def list_serial_ports() -> dict:
    cfg = _import_cfg()
    patterns = ['/dev/ttyACM*', '/dev/ttyUSB*', '/dev/ttyAMA*']
    ports: list[str] = []
    for pat in patterns:
        ports.extend(glob.glob(pat))
    ports.sort()
    return {'ports': ports, 'current': cfg.SERIAL_PATH}


def set_serial_port(port: str) -> dict:
    if not os.path.exists(port):
        return {'ok': False, 'error': f'Port {port} not found'}
    cfg = _import_cfg()
    _write_env('SERIAL_PATH', port)
    cfg.SERIAL_PATH = port
    return {'ok': True, 'port': port, 'restart_required': True}


def usb_status() -> dict:
    try:
        usb_storage = _import_usb_storage()
        _TILES_DIR = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'static', 'tiles'
        )
        status = usb_storage.get_usb_status()
        status['tiles_location'] = usb_storage.get_tiles_location(_TILES_DIR)
        return status
    except Exception as e:
        log.warning("usb_status() failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Alerts & Map config
# ---------------------------------------------------------------------------

def get_alert_config() -> dict:
    cfg = _import_cfg()
    return {
        'node_offline_min': cfg.ALERT_NODE_OFFLINE_MIN,
        'battery_low': cfg.ALERT_BATTERY_LOW,
        'ram_high': cfg.ALERT_RAM_HIGH,
    }


def set_alert_config(config: dict) -> dict:
    cfg = _import_cfg()
    if 'node_offline_min' in config:
        _write_env('ALERT_NODE_OFFLINE_MIN', str(config['node_offline_min']))
        cfg.ALERT_NODE_OFFLINE_MIN = config['node_offline_min']
    if 'battery_low' in config:
        _write_env('ALERT_BATTERY_LOW', str(config['battery_low']))
        cfg.ALERT_BATTERY_LOW = config['battery_low']
    if 'ram_high' in config:
        _write_env('ALERT_RAM_HIGH', str(config['ram_high']))
        cfg.ALERT_RAM_HIGH = config['ram_high']
    return {'ok': True}


def get_map_config() -> dict:
    cfg = _import_cfg()
    tiles_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'static', 'tiles', 'osm'
    )
    tiles_present = os.path.isdir(tiles_dir) and bool(os.listdir(tiles_dir))
    return {
        'local_tiles': cfg.MAP_LOCAL_TILES,
        'region': cfg.MAP_REGION,
        'tiles_present': tiles_present,
    }


def set_map_config(config: dict) -> dict:
    cfg = _import_cfg()
    if 'local_tiles' in config:
        _write_env('MAP_LOCAL_TILES', '1' if config['local_tiles'] else '0')
        cfg.MAP_LOCAL_TILES = bool(config['local_tiles'])
    if 'region' in config:
        _write_env('MAP_REGION', config['region'])
        cfg.MAP_REGION = config['region']
    return {'local_tiles': cfg.MAP_LOCAL_TILES, 'region': cfg.MAP_REGION}


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------

def get_mqtt_status() -> dict:
    try:
        return _import_mqtt_bridge().get_status()
    except Exception as e:
        log.warning("get_mqtt_status() failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------

def get_bots() -> dict:
    try:
        return _import_bots_runner().get_state_snapshot()
    except Exception as e:
        log.warning("get_bots() failed: %s", e)
        return {'bots': []}


def toggle_bot(name: str, enabled: bool) -> dict:
    try:
        runner = _import_bots_runner()
        state = runner.get_state_snapshot()
        if not any(b['name'] == name for b in state.get('bots', [])):
            return {'ok': False, 'error': f'unknown bot: {name}'}
        cfg_obj = runner._state.config
        if cfg_obj is None:
            return {'ok': False, 'error': 'bots runner not started'}
        _run_async(cfg_obj.set_enabled(name, enabled))
        _run_async(runner.reload_config())
        return {'ok': True, 'name': name, 'enabled': enabled}
    except Exception as e:
        log.warning("toggle_bot(%r) failed: %s", name, e)
        return {'ok': False, 'error': str(e)}


def set_bot_prefix(prefix: str) -> dict:
    try:
        prefix = (prefix or '').strip()
        if not prefix:
            return {'ok': False, 'error': 'prefix cannot be empty'}
        runner = _import_bots_runner()
        cfg_obj = runner._state.config
        if cfg_obj is None:
            return {'ok': False, 'error': 'bots runner not started'}
        _run_async(cfg_obj.set_prefix(prefix))
        _run_async(runner.reload_config())
        return {'ok': True, 'prefix': prefix}
    except Exception as e:
        log.warning("set_bot_prefix() failed: %s", e)
        return {'ok': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Admin — remote node operations
# ---------------------------------------------------------------------------

def admin_action(node_id: str, operation: str,
                 params: dict | None = None) -> dict:
    """Send an admin operation to a remote node.

    operation: 'request_position' | 'request_telemetry' | 'reboot' | 'factory_reset'
    """
    try:
        client = _import_meshtasticd_client()
        if not client.is_connected():
            return {'ok': False, 'error': 'board not connected'}
        _run_async(client.send_admin(node_id, operation, params))
        return {'ok': True}
    except RuntimeError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        log.warning("admin_action(%r, %r) failed: %s", node_id, operation, e)
        return {'ok': False, 'error': str(e)}


def forget_node(node_id: str) -> dict:
    """Remove a node from the in-memory cache and the database."""
    try:
        client = _import_meshtasticd_client()
        # Remove from in-memory cache (best-effort — internal dict)
        if hasattr(client, '_node_cache'):
            client._node_cache.pop(node_id, None)
        delete_node(node_id)
        return {'ok': True}
    except Exception as e:
        log.warning("forget_node(%r) failed: %s", node_id, e)
        return {'ok': False, 'error': str(e)}
