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

echo "==> Installing Qt GUI runtime libraries..."
# Required by PySide6 at import time. Already present on Pi OS desktop, but
# installing them explicitly so the headless 'lite' image works too.
apt-get install -y --no-install-recommends \
    libegl1 libxcb-cursor0 libxkbcommon0 libfontconfig1 \
    || echo "    (some Qt runtime libs missing — GUI may fail to start)"

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

install_gui_deps() {
    # Strategy: try pip first; on ARM where no compatible wheel exists, fall
    # back to apt-installed python3-pyside6.* and rebuild the venv with
    # --system-site-packages so it can see them.
    echo "==> Installing GUI deps (PySide6) via pip..."
    if sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements-gui.txt"; then
        if sudo -u "$USER" "$REPO_DIR/venv/bin/python" -c \
            "import PySide6.QtCore" 2>/dev/null; then
            echo "    PySide6 from pip OK."
            return 0
        fi
        echo "    pip install reported success but import failed; trying apt fallback..."
    else
        echo "    pip install failed (likely no compatible wheel for this arch); trying apt fallback..."
    fi

    echo "==> Installing PySide6 from apt..."
    apt-get install -y --no-install-recommends \
        python3-pyside6.qtcore python3-pyside6.qtgui \
        python3-pyside6.qtwidgets python3-pyside6.qtsvg

    echo "==> Recreating venv with --system-site-packages..."
    create_venv "--system-site-packages"
    install_core

    if ! sudo -u "$USER" "$REPO_DIR/venv/bin/python" -c \
        "import PySide6.QtCore, qasync" 2>/dev/null; then
        echo "    !! PySide6 still not importable after apt fallback."
        echo "       The web UI will continue to work; the native Qt GUI will not."
        return 1
    fi
    echo "    PySide6 from apt + qasync from pip OK."
}

echo "==> Setting up Python venv..."
create_venv ""
install_core
install_gui_deps || true

echo "==> Creating data directory..."
sudo -u "$USER" mkdir -p "$REPO_DIR/data"

echo "==> Installing systemd services..."
cp "$REPO_DIR/systemd/meshtasticd.service" /etc/systemd/system/
cp "$REPO_DIR/systemd/pimesh.service"      /etc/systemd/system/
cp "$REPO_DIR/systemd/pimesh-gui.service"  /etc/systemd/system/
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
echo "    Native Qt kiosk (optional, replaces the surf-based kiosk):"
echo "      sudo systemctl disable --now kiosk.service     # if currently enabled"
echo "      sudo systemctl enable  --now pimesh-gui.service"
echo
