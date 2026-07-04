#!/usr/bin/env bash
# setup.sh — One-command pi-Mesh setup on Raspberry Pi OS Bookworm
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="${SUDO_USER:-pimesh}"
HOME_DIR="/home/$USER"

echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3-venv python3-pip git \
    zram-tools

echo "==> Configuring zram swap (lz4, 50% RAM)..."
cat > /etc/default/zramswap <<'EOF'
ALGO=lz4
PERCENT=50
EOF
systemctl restart zramswap
echo "    zram swap active: $(zramctl)"

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
cp "$REPO_DIR/systemd/meshtasticd.service" /etc/systemd/system/
cp "$REPO_DIR/systemd/pimesh.service"      /etc/systemd/system/
systemctl daemon-reload
systemctl enable meshtasticd pimesh
systemctl start  meshtasticd
sleep 3
systemctl start  pimesh

echo
echo "==> Done."
echo
echo "    Web UI: http://localhost:8080  (also reachable on the LAN)"
echo
echo "    Kiosk su display (opzionale):"
echo "      SPI  3.5\": sudo bash scripts/setup-display.sh"
echo "      HDMI (GPU): sudo bash scripts/setup-display-hdmi.sh"
echo
