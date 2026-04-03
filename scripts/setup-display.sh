#!/usr/bin/env bash
# setup-display.sh — Setup display and kiosk mode for pi-Mesh
# Installs X11, window manager, browser, and configures autostart
# Usage: sudo bash scripts/setup-display.sh [--uninstall]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
skip() { echo -e "${YELLOW}  ~ $* (già fatto)${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; }

PIMESH_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIMESH_USER="${PIMESH_USER:-pimesh}"
KIOSK_SERVICE="kiosk"

if [[ $EUID -ne 0 ]]; then
  err "Esegui come root: sudo bash $0"
  exit 1
fi

# --- UNINSTALL ---
if [[ "${1:-}" == "--uninstall" ]]; then
  echo "▶ Rimozione kiosk mode..."
  systemctl disable --now "$KIOSK_SERVICE" 2>/dev/null && ok "Servizio kiosk disabilitato" || skip "Servizio non attivo"
  rm -f "/etc/systemd/system/${KIOSK_SERVICE}.service"
  systemctl daemon-reload
  ok "Kiosk mode rimosso"
  exit 0
fi

echo "========================================"
echo "  pi-Mesh — Setup Display & Kiosk"
echo "========================================"
echo ""

# --- STEP 1: Install packages ---
echo "▶ [1/5] Installazione pacchetti X11 e browser..."
PKGS=(xserver-xorg xinit matchbox-window-manager surf x11-xserver-utils)
TO_INSTALL=()
for pkg in "${PKGS[@]}"; do
  if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
    skip "$pkg"
  else
    TO_INSTALL+=("$pkg")
  fi
done

if [[ ${#TO_INSTALL[@]} -gt 0 ]]; then
  apt-get update -qq
  apt-get install -y "${TO_INSTALL[@]}" >/dev/null 2>&1 && ok "Installati: ${TO_INSTALL[*]}" || { err "Installazione fallita"; exit 1; }
fi

# --- STEP 2: Create pimesh user if needed ---
echo ""
echo "▶ [2/5] Verifica utente $PIMESH_USER..."
if id "$PIMESH_USER" &>/dev/null; then
  skip "Utente $PIMESH_USER esiste"
else
  useradd -m -s /bin/bash "$PIMESH_USER"
  ok "Utente $PIMESH_USER creato"
fi

# Add to video, input, tty groups for display/touch access
for grp in video input tty; do
  if groups "$PIMESH_USER" | grep -qw "$grp"; then
    skip "$PIMESH_USER in gruppo $grp"
  else
    usermod -aG "$grp" "$PIMESH_USER"
    ok "$PIMESH_USER aggiunto a $grp"
  fi
done

# --- STEP 3: Install kiosk scripts ---
echo ""
echo "▶ [3/5] Installazione script kiosk..."

# Copy start-kiosk.sh to user home
cp "$PIMESH_DIR/scripts/start-kiosk.sh" "/home/$PIMESH_USER/start-kiosk.sh"
chmod +x "/home/$PIMESH_USER/start-kiosk.sh"
chown "$PIMESH_USER:$PIMESH_USER" "/home/$PIMESH_USER/start-kiosk.sh"
ok "start-kiosk.sh installato in /home/$PIMESH_USER/"

# --- STEP 4: Install systemd service ---
echo ""
echo "▶ [4/5] Configurazione servizio systemd..."

cp "$PIMESH_DIR/scripts/kiosk.service" "/etc/systemd/system/${KIOSK_SERVICE}.service"
systemctl daemon-reload
systemctl enable "$KIOSK_SERVICE"
ok "Servizio $KIOSK_SERVICE abilitato"

# --- STEP 5: Display configuration ---
echo ""
echo "▶ [5/5] Configurazione display..."

# Console blanking off (keep display always on)
CMDLINE="/boot/firmware/cmdline.txt"
if [[ -f "$CMDLINE" ]]; then
  if grep -q "consoleblank=0" "$CMDLINE"; then
    skip "Console blanking già disabilitato"
  else
    sed -i 's/$/ consoleblank=0/' "$CMDLINE"
    ok "Console blanking disabilitato in cmdline.txt"
  fi
fi

# Ensure fbdev permissions
if [[ -e /dev/fb0 ]]; then
  chmod 666 /dev/fb0 2>/dev/null
  ok "Permessi /dev/fb0 impostati"
else
  skip "/dev/fb0 non presente (verrà creato al boot con display collegato)"
fi

# X11 wrapper permissions for non-root xinit
XWRAPPER="/etc/X11/Xwrapper.config"
if [[ -f "$XWRAPPER" ]]; then
  if grep -q "allowed_users=anybody" "$XWRAPPER"; then
    skip "Xwrapper già configurato"
  else
    echo "allowed_users=anybody" > "$XWRAPPER"
    ok "Xwrapper configurato per utente non-root"
  fi
else
  mkdir -p "$(dirname "$XWRAPPER")"
  echo "allowed_users=anybody" > "$XWRAPPER"
  ok "Xwrapper creato e configurato"
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}Setup display completato!${NC}"
echo ""
echo "  Per avviare il kiosk:"
echo "    sudo systemctl start $KIOSK_SERVICE"
echo ""
echo "  Per calibrare il touch:"
echo "    sudo bash scripts/calibrate-touch.sh"
echo ""
echo "  Per rimuovere il kiosk:"
echo "    sudo bash scripts/setup-display.sh --uninstall"
echo "========================================"
