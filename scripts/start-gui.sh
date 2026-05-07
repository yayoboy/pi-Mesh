#!/bin/bash
# scripts/start-gui.sh — Native Qt GUI launcher (xinit target).
# Used by systemd/pimesh-gui.service. Mutually exclusive with the web kiosk
# (start-kiosk.sh + surf): only one of pimesh-gui.service or kiosk.service
# should be enabled at a time.

set -e

export DISPLAY=:0

# Touchscreen energy saving off so the kiosk display never blanks.
xset -dpms
xset s off
xset s noblank

# Borderless WM (same as the web kiosk).
matchbox-window-manager -use_titlebar no &

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# Pick the venv interpreter if it exists, fall back to system Python with
# system-site-packages support (needed when PySide6 is installed via apt).
if [ -x "$REPO_DIR/venv/bin/python" ]; then
    PY="$REPO_DIR/venv/bin/python"
else
    PY="/usr/bin/python3"
fi

# Optional config (PIMESH_GUI_EMBEDDED_UVICORN, PIMESH_ORIENTATION, ...).
if [ -f "$REPO_DIR/config.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/config.env"
    set +a
fi

exec "$PY" -m gui
