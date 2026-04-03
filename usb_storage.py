# usb_storage.py
"""USB storage detection, auto-mount, and tile management."""
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

USB_MOUNT_BASE = '/media'
TILES_SUBDIR = 'pi-mesh/tiles'


def _find_usb_block_devices() -> list[dict]:
    """Find USB block devices via lsblk."""
    try:
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,SIZE,MOUNTPOINT,FSTYPE,TRAN,LABEL'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        import json
        data = json.loads(result.stdout)
        devices = []
        for dev in data.get('blockdevices', []):
            if dev.get('tran') != 'usb':
                continue
            for child in dev.get('children', []):
                if child.get('fstype'):
                    devices.append({
                        'name': child['name'],
                        'size': child.get('size', ''),
                        'mountpoint': child.get('mountpoint'),
                        'fstype': child.get('fstype', ''),
                        'label': child.get('label') or child['name'],
                    })
            # Device without partitions (e.g. /dev/sda with fs directly)
            if not dev.get('children') and dev.get('fstype'):
                devices.append({
                    'name': dev['name'],
                    'size': dev.get('size', ''),
                    'mountpoint': dev.get('mountpoint'),
                    'fstype': dev.get('fstype', ''),
                    'label': dev.get('label') or dev['name'],
                })
        return devices
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.warning('lsblk failed: %s', e)
        return []


def _auto_mount(device: dict) -> str | None:
    """Auto-mount a USB device, return mount point or None."""
    dev_path = f"/dev/{device['name']}"
    mount_dir = os.path.join(USB_MOUNT_BASE, device['label'])
    try:
        os.makedirs(mount_dir, exist_ok=True)
        result = subprocess.run(
            ['sudo', 'mount', '-o', 'rw,noexec,nodev,nosuid', dev_path, mount_dir],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info('Mounted %s at %s', dev_path, mount_dir)
            return mount_dir
        # Already mounted somewhere?
        if 'already mounted' in result.stderr.lower():
            return device.get('mountpoint')
        logger.warning('Mount failed: %s', result.stderr.strip())
    except Exception as e:
        logger.warning('Mount error: %s', e)
    return None


def get_usb_status() -> dict:
    """Return USB storage status: connected, mount point, space info."""
    devices = _find_usb_block_devices()
    if not devices:
        return {'connected': False, 'devices': []}

    result_devices = []
    for dev in devices:
        mount = dev['mountpoint']
        # Auto-mount if not already mounted
        if not mount:
            mount = _auto_mount(dev)

        info = {
            'name': dev['label'],
            'dev': dev['name'],
            'size': dev['size'],
            'fstype': dev['fstype'],
            'mountpoint': mount,
            'total_mb': 0,
            'used_mb': 0,
            'free_mb': 0,
        }
        if mount:
            try:
                stat = shutil.disk_usage(mount)
                info['total_mb'] = round(stat.total / (1024 * 1024))
                info['used_mb'] = round(stat.used / (1024 * 1024))
                info['free_mb'] = round(stat.free / (1024 * 1024))
            except OSError:
                pass
        result_devices.append(info)

    return {
        'connected': True,
        'devices': result_devices,
    }


def _get_primary_mount() -> str | None:
    """Get mount point of first connected USB device."""
    status = get_usb_status()
    if not status['connected']:
        return None
    for dev in status['devices']:
        if dev['mountpoint']:
            return dev['mountpoint']
    return None


def move_tiles_to_usb(tiles_src: str) -> dict:
    """Move tiles directory from SD to USB. Creates symlink back."""
    mount = _get_primary_mount()
    if not mount:
        return {'ok': False, 'error': 'Nessuna USB collegata'}

    usb_tiles = os.path.join(mount, TILES_SUBDIR)

    # Already on USB?
    if os.path.islink(tiles_src) and os.readlink(tiles_src).startswith(mount):
        return {'ok': True, 'message': 'Tile già su USB', 'path': usb_tiles}

    if not os.path.isdir(tiles_src):
        return {'ok': False, 'error': 'Directory tile non trovata'}

    try:
        # Copy tiles to USB
        os.makedirs(os.path.dirname(usb_tiles), exist_ok=True)
        if os.path.exists(usb_tiles):
            shutil.rmtree(usb_tiles)
        shutil.copytree(tiles_src, usb_tiles)

        # Replace original with symlink
        shutil.rmtree(tiles_src)
        os.symlink(usb_tiles, tiles_src)

        logger.info('Tiles moved to USB: %s -> %s', tiles_src, usb_tiles)
        return {'ok': True, 'message': 'Tile spostate su USB', 'path': usb_tiles}
    except Exception as e:
        logger.error('Failed to move tiles: %s', e)
        return {'ok': False, 'error': str(e)}


def restore_tiles_to_sd(tiles_src: str) -> dict:
    """Restore tiles from USB back to SD."""
    if not os.path.islink(tiles_src):
        return {'ok': True, 'message': 'Tile già su SD'}

    usb_path = os.readlink(tiles_src)
    if not os.path.isdir(usb_path):
        return {'ok': False, 'error': 'Tile su USB non trovate'}

    try:
        # Remove symlink
        os.unlink(tiles_src)
        # Copy back from USB
        shutil.copytree(usb_path, tiles_src)

        logger.info('Tiles restored to SD: %s', tiles_src)
        return {'ok': True, 'message': 'Tile ripristinate su SD'}
    except Exception as e:
        logger.error('Failed to restore tiles: %s', e)
        return {'ok': False, 'error': str(e)}


def get_tiles_location(tiles_src: str) -> str:
    """Return 'usb' if tiles are symlinked to USB, otherwise 'sd'."""
    if os.path.islink(tiles_src):
        return 'usb'
    return 'sd'
