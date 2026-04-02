# rpi_telemetry.py
"""Raspberry Pi system telemetry collection."""
import logging
import os
import time

logger = logging.getLogger(__name__)

_last: dict = {}


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
