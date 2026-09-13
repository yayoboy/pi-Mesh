#!/usr/bin/env bash
# setup.sh — One-command pi-Mesh setup on Raspberry Pi OS Bookworm
#
# Usage: sudo bash setup.sh [headless|kiosk-spi|kiosk-hdmi|desktop] [--with-meshtasticd]
#
# The profile decides what gets installed beyond the backend. Omit it and the
# machine is probed: SPI framebuffer → kiosk-spi, graphical target → desktop,
# connected DRM output → kiosk-hdmi, otherwise headless (Pi Zero, servers).
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="${SUDO_USER:-pimesh}"
HOME_DIR="/home/$USER"

detect_profile() {
    if [ -e /sys/class/graphics/fb1 ]; then
        echo kiosk-spi
    elif systemctl get-default 2>/dev/null | grep -q graphical; then
        echo desktop
    elif grep -qx connected /sys/class/drm/*/status 2>/dev/null; then
        echo kiosk-hdmi
    else
        echo headless
    fi
}

PROFILE=""
WITH_MESHTASTICD=0
for arg in "$@"; do
    case "$arg" in
        headless|kiosk-spi|kiosk-hdmi|desktop) PROFILE="$arg" ;;
        --with-meshtasticd) WITH_MESHTASTICD=1 ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done
[ -n "$PROFILE" ] || { PROFILE="$(detect_profile)"; echo "==> Profile auto-detected: $PROFILE"; }

# MemTotal in kB. zram earns its keep under ~2 GB; above that it is noise.
RAM_KB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"

echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends python3-venv python3-pip git

if [ "$RAM_KB" -lt 2097152 ]; then
    echo "==> Configuring zram swap (lz4, 50% RAM)..."
    apt-get install -y --no-install-recommends zram-tools
    cat > /etc/default/zramswap <<'EOF'
ALGO=lz4
PERCENT=50
EOF
    systemctl restart zramswap
    echo "    zram swap active: $(zramctl)"
else
    echo "==> Skipping zram ($((RAM_KB / 1024)) MB RAM — not needed)"
fi

create_venv() {
    local extra_flags="$1"
    sudo -u "$USER" rm -rf "$REPO_DIR/venv"
    # shellcheck disable=SC2086
    sudo -u "$USER" python3 -m venv $extra_flags "$REPO_DIR/venv"
    sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q --upgrade pip
}

install_core() {
    echo "==> Installing core Python deps..."
    sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
}

echo "==> Setting up Python venv..."
create_venv ""
install_core

echo "==> Creating data directory..."
sudo -u "$USER" mkdir -p "$REPO_DIR/data"

echo "==> Installing systemd services..."
cp "$REPO_DIR/systemd/pimesh.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable pimesh

# meshtasticd only serves native LoRa HATs; an ESP32 board over USB is driven
# directly by meshtastic.SerialInterface and the daemon just holds the port.
if [ "$WITH_MESHTASTICD" = 1 ]; then
    cp "$REPO_DIR/systemd/meshtasticd.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable meshtasticd
    systemctl start  meshtasticd
    sleep 3
fi
systemctl start  pimesh

if [ "$PROFILE" = desktop ]; then
    echo "==> Installing desktop launcher..."
    install -m 644 "$REPO_DIR/pimesh.desktop" /usr/share/applications/pimesh.desktop
    if [ -d "$HOME_DIR/Desktop" ]; then
        install -m 755 -o "$USER" -g "$USER" "$REPO_DIR/pimesh.desktop" "$HOME_DIR/Desktop/pimesh.desktop"
    fi
fi

echo
echo "==> Done. Profile: $PROFILE"
echo
echo "    Web UI: http://localhost:8080  (also reachable on the LAN)"
echo
case "$PROFILE" in
    headless)
        echo "    Headless: open the UI from another device on the network."
        ;;
    kiosk-spi)
        echo "    Next step — SPI 3.5\" kiosk: sudo bash scripts/setup-display.sh"
        ;;
    kiosk-hdmi)
        echo "    Next step — HDMI GPU kiosk: sudo bash scripts/setup-display-hdmi.sh"
        ;;
    desktop)
        echo "    Launcher installed: look for \"pi-Mesh\" in the menu or on the desktop."
        ;;
esac
echo
