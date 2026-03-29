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
echo "zram swap active: $(zramctl)"

echo "==> Setting up Python venv..."
sudo -u "$USER" python3 -m venv "$REPO_DIR/venv"
sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

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

echo "==> Done. App available at http://localhost:8080"
