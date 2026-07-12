# rpi_telemetry.py
"""Raspberry Pi system telemetry collection."""
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

_last: dict = {}
_power_events: int = 0
_power_last_event_ts: int | None = None
_power_prev_active: bool = False


def collect() -> dict:
    """Collect current RPi system metrics. Returns dict with all fields."""
    global _last
    data = {
        'ts': int(time.time()),
        'cpu_temp': _cpu_temp(),
        'cpu_percent': _cpu_percent(),
        'ram_total_mb': 0,
        'ram_used_mb': 0,
        'ram_percent': 0.0,
        'disk_total_mb': 0,
        'disk_used_mb': 0,
        'disk_percent': 0.0,
        'uptime_seconds': _uptime(),
    }
    # RAM from /proc/meminfo
    try:
        with open('/proc/meminfo') as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(':')] = int(parts[1])
            total = meminfo.get('MemTotal', 0) // 1024
            available = meminfo.get('MemAvailable', 0) // 1024
            data['ram_total_mb'] = total
            data['ram_used_mb'] = total - available
            data['ram_percent'] = round((total - available) / total * 100, 1) if total else 0
    except (OSError, ValueError, ZeroDivisionError):
        pass

    # Disk usage
    try:
        import shutil
        usage = shutil.disk_usage('/')
        data['disk_total_mb'] = round(usage.total / (1024 * 1024))
        data['disk_used_mb'] = round(usage.used / (1024 * 1024))
        data['disk_percent'] = round(usage.used / usage.total * 100, 1)
    except OSError:
        pass

    # Power supply status (undervoltage/throttling)
    global _power_events, _power_last_event_ts, _power_prev_active
    power = _parse_throttled(_read_throttled())
    data.update(power)
    active = bool(power['undervolt_now'] or power['throttle_now'])
    if active and not _power_prev_active:
        _power_events += 1
        _power_last_event_ts = data['ts']
    _power_prev_active = active
    data['power_events'] = _power_events
    data['power_last_event_ts'] = _power_last_event_ts

    _last = data
    return data


def get_last() -> dict:
    """Return last collected metrics without re-collecting."""
    return _last


def _cpu_temp() -> float | None:
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def _cpu_percent() -> float | None:
    try:
        with open('/proc/stat') as f:
            line = f.readline()
        vals = [int(x) for x in line.split()[1:]]
        idle = vals[3]
        total = sum(vals)
        if hasattr(_cpu_percent, '_prev'):
            d_idle = idle - _cpu_percent._prev[0]
            d_total = total - _cpu_percent._prev[1]
            pct = round((1 - d_idle / d_total) * 100, 1) if d_total else 0
        else:
            pct = 0.0
        _cpu_percent._prev = (idle, total)
        return pct
    except (OSError, ValueError, ZeroDivisionError):
        return None


def _uptime() -> int:
    try:
        with open('/proc/uptime') as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError):
        return 0


def _read_throttled() -> int | None:
    """Read raw get_throttled bitmask via vcgencmd. None if unavailable."""
    try:
        out = subprocess.run(['vcgencmd', 'get_throttled'],
                             capture_output=True, text=True, timeout=2)
        # output: "throttled=0x50000"
        return int(out.stdout.strip().split('=')[1], 16)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _parse_throttled(raw: int | None) -> dict:
    """Derive power flags from the get_throttled bitmask (pure function)."""
    if raw is None:
        return {'throttled': None, 'undervolt_now': None, 'throttle_now': None,
                'undervolt_boot': None, 'throttle_boot': None}
    return {
        'throttled': raw,
        'undervolt_now': bool(raw & 0x1),
        'throttle_now': bool(raw & 0x4),
        'undervolt_boot': bool(raw & 0x10000),
        'throttle_boot': bool(raw & 0x40000),
    }
