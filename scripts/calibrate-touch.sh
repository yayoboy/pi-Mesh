#!/usr/bin/env bash
# calibrate-touch.sh — Calibrate resistive touchscreen for pi-Mesh kiosk
# Usage: sudo bash scripts/calibrate-touch.sh [--reset]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
skip() { echo -e "${YELLOW}  ~ $*${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; }

CALIB_CONF="/etc/X11/xorg.conf.d/99-calibration.conf"

if [[ $EUID -ne 0 ]]; then
  err "Esegui come root: sudo bash $0"
  exit 1
fi

# Reset mode
if [[ "${1:-}" == "--reset" ]]; then
  if [[ -f "$CALIB_CONF" ]]; then
    rm -f "$CALIB_CONF"
    ok "Calibrazione rimossa: $CALIB_CONF"
    echo "  Riavvia il kiosk per applicare: sudo systemctl restart kiosk"
  else
    skip "Nessuna calibrazione trovata"
  fi
  exit 0
fi

echo "========================================"
echo "  pi-Mesh — Calibrazione Touch"
echo "========================================"
echo ""

# Install xinput-calibrator if needed
if ! command -v xinput_calibrator &>/dev/null; then
  echo "▶ Installo xinput-calibrator..."
  apt-get install -y xinput-calibrator >/dev/null 2>&1 && ok "xinput-calibrator installato" || { err "Installazione fallita"; exit 1; }
else
  skip "xinput-calibrator già installato"
fi

# Check X11 is running
if ! xdpyinfo -display :0 &>/dev/null; then
  err "X11 non attivo su :0"
  echo "  Avvia il kiosk prima: sudo systemctl start kiosk"
  exit 1
fi

export DISPLAY=:0

# Detect touch device
echo ""
echo "▶ Dispositivi touch rilevati:"
xinput list --name-only 2>/dev/null | grep -i -E "touch|ads|resistive|ft5" || {
  echo "  (nessun dispositivo touch trovato — procedo comunque)"
}

echo ""
echo "▶ Avvio calibrazione..."
echo "  Tocca i 4 punti sullo schermo quando richiesto."
echo ""

# Run calibrator and capture output
mkdir -p "$(dirname "$CALIB_CONF")"
CALIB_OUTPUT="$(DISPLAY=:0 xinput_calibrator --output-type xorg.conf.d 2>&1)" || {
  err "Calibrazione annullata o fallita"
  exit 1
}

# Extract the Section block and save
echo "$CALIB_OUTPUT" | sed -n '/Section/,/EndSection/p' > "$CALIB_CONF"

if [[ -s "$CALIB_CONF" ]]; then
  ok "Calibrazione salvata: $CALIB_CONF"
  echo ""
  cat "$CALIB_CONF"
  echo ""
  echo "  Riavvia il kiosk per applicare: sudo systemctl restart kiosk"
else
  err "Nessun dato di calibrazione generato"
  rm -f "$CALIB_CONF"
  exit 1
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}Calibrazione completata!${NC}"
echo "========================================"
