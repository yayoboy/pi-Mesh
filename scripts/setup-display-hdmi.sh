#!/usr/bin/env bash
# setup-display-hdmi.sh — Setup display HDMI + kiosk GPU per pi-Mesh
# Installa cog (browser WPE WebKit), abilita il driver KMS vc4 con CMA
# ridotto (adatto ai 512 MB del Pi 3 A+), disattiva il display SPI tft35a
# e configura il servizio kiosk-hdmi.
#
# Uso: sudo bash scripts/setup-display-hdmi.sh [--uninstall]
# Variabili: PIMESH_USER (default pimesh), PIMESH_CMA (default 96 [MB])
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
skip() { echo -e "${YELLOW}  ~ $* (già fatto)${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; }

PIMESH_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIMESH_USER="${PIMESH_USER:-pimesh}"
PIMESH_CMA="${PIMESH_CMA:-96}"
KIOSK_SERVICE="kiosk-hdmi"
CONFIG_TXT="/boot/firmware/config.txt"
[[ -f "$CONFIG_TXT" ]] || CONFIG_TXT="/boot/config.txt"

if [[ $EUID -ne 0 ]]; then
  err "Esegui come root: sudo bash $0"
  exit 1
fi

# --- UNINSTALL ---
if [[ "${1:-}" == "--uninstall" ]]; then
  echo "▶ Rimozione kiosk HDMI..."
  systemctl disable --now "$KIOSK_SERVICE" 2>/dev/null && ok "Servizio $KIOSK_SERVICE disabilitato" || skip "Servizio non attivo"
  rm -f "/etc/systemd/system/${KIOSK_SERVICE}.service"
  systemctl daemon-reload
  ok "Kiosk HDMI rimosso"
  echo ""
  echo "  Le modifiche a $CONFIG_TXT NON sono state toccate."
  BACKUP=$(ls -t "${CONFIG_TXT}".pimesh-bak.* 2>/dev/null | head -1 || true)
  [[ -n "$BACKUP" ]] && echo "  Per ripristinare il display SPI: sudo cp $BACKUP $CONFIG_TXT && sudo reboot"
  exit 0
fi

echo "========================================"
echo "  pi-Mesh — Setup Display HDMI (GPU)"
echo "========================================"
echo ""

# --- STEP 1: Install packages ---
echo "▶ [1/6] Installazione browser WPE (cog)..."
if dpkg -l cog 2>/dev/null | grep -q "^ii"; then
  skip "cog"
else
  apt-get update -qq
  apt-get install -y cog >/dev/null 2>&1 && ok "Installato: cog" || {
    err "Installazione cog fallita — verifica che il pacchetto esista nella tua release"
    exit 1
  }
fi

# --- STEP 2: Utente e gruppi ---
echo ""
echo "▶ [2/6] Verifica utente $PIMESH_USER..."
if id "$PIMESH_USER" &>/dev/null; then
  skip "Utente $PIMESH_USER esiste"
else
  useradd -m -s /bin/bash "$PIMESH_USER"
  ok "Utente $PIMESH_USER creato"
fi

# video/render per DRM+GPU, input per touchscreen/tastiera via libinput
for grp in video render input tty; do
  if groups "$PIMESH_USER" | grep -qw "$grp"; then
    skip "$PIMESH_USER in gruppo $grp"
  else
    usermod -aG "$grp" "$PIMESH_USER"
    ok "$PIMESH_USER aggiunto a $grp"
  fi
done

# --- STEP 3: Script kiosk ---
echo ""
echo "▶ [3/6] Installazione script kiosk..."
cp "$PIMESH_DIR/scripts/start-kiosk-hdmi.sh" "/home/$PIMESH_USER/start-kiosk-hdmi.sh"
chmod +x "/home/$PIMESH_USER/start-kiosk-hdmi.sh"
chown "$PIMESH_USER:$PIMESH_USER" "/home/$PIMESH_USER/start-kiosk-hdmi.sh"
ok "start-kiosk-hdmi.sh installato in /home/$PIMESH_USER/"

# --- STEP 4: Servizio systemd ---
echo ""
echo "▶ [4/6] Configurazione servizio systemd..."
cp "$PIMESH_DIR/scripts/kiosk-hdmi.service" "/etc/systemd/system/${KIOSK_SERVICE}.service"
systemctl daemon-reload
systemctl enable "$KIOSK_SERVICE"
ok "Servizio $KIOSK_SERVICE abilitato"

# --- STEP 5: config.txt — KMS on, SPI off ---
echo ""
echo "▶ [5/6] Configurazione $CONFIG_TXT..."

BACKUP="${CONFIG_TXT}.pimesh-bak.$(date +%Y%m%d%H%M%S)"
cp "$CONFIG_TXT" "$BACKUP"
ok "Backup: $BACKUP"

# Disattiva il display SPI (tft35a): con l'HDMI attivo terrebbe occupati
# GPIO e un framebuffer inutile.
if grep -qE '^\s*dtoverlay=tft35a' "$CONFIG_TXT"; then
  sed -i -E 's/^\s*(dtoverlay=tft35a.*)/#\1  # disattivato da setup-display-hdmi/' "$CONFIG_TXT"
  ok "Overlay tft35a (display SPI) disattivato"
else
  skip "Overlay tft35a non presente"
fi

# Abilita KMS con CMA ridotto: il default (256-512 MB) è insostenibile su
# un Pi da 512 MB; ${PIMESH_CMA} MB bastano per 800×480/1024×600 double
# buffered + compositing WebKit.
if grep -qE "^\s*dtoverlay=vc4-kms-v3d,cma-${PIMESH_CMA}\b" "$CONFIG_TXT"; then
  skip "vc4-kms-v3d,cma-${PIMESH_CMA} già configurato"
elif grep -qE '^\s*dtoverlay=vc4-kms-v3d' "$CONFIG_TXT"; then
  sed -i -E "s/^\s*dtoverlay=vc4-kms-v3d.*/dtoverlay=vc4-kms-v3d,cma-${PIMESH_CMA}/" "$CONFIG_TXT"
  ok "vc4-kms-v3d aggiornato con cma-${PIMESH_CMA}"
else
  printf '\n# pi-Mesh HDMI: GPU via KMS, CMA ridotto per 512MB RAM\ndtoverlay=vc4-kms-v3d,cma-%s\n' "$PIMESH_CMA" >> "$CONFIG_TXT"
  ok "vc4-kms-v3d,cma-${PIMESH_CMA} aggiunto"
fi

# Con KMS il firmware non usa più gpu_mem: un valore alto spreca solo RAM.
if grep -qE '^\s*gpu_mem=' "$CONFIG_TXT"; then
  sed -i -E 's/^\s*(gpu_mem=.*)/#\1  # ignorato con KMS/' "$CONFIG_TXT"
  ok "gpu_mem commentato (ignorato con KMS)"
else
  skip "gpu_mem non presente"
fi

# --- STEP 6: cmdline.txt — niente blanking console ---
echo ""
echo "▶ [6/6] Configurazione cmdline..."
CMDLINE="/boot/firmware/cmdline.txt"
[[ -f "$CMDLINE" ]] || CMDLINE="/boot/cmdline.txt"
if [[ -f "$CMDLINE" ]]; then
  if grep -q "consoleblank=0" "$CMDLINE"; then
    skip "Console blanking già disabilitato"
  else
    sed -i 's/$/ consoleblank=0/' "$CMDLINE"
    ok "Console blanking disabilitato in cmdline.txt"
  fi
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}Setup display HDMI completato!${NC}"
echo ""
echo "  Riavvia per attivare il driver KMS:"
echo "    sudo reboot"
echo ""
echo "  Il kiosk parte da solo al boot. Avvio manuale:"
echo "    sudo systemctl start $KIOSK_SERVICE"
echo ""
echo "  Scala UI manuale (opzionale, in config.env):"
echo "    PIMESH_HDMI_SCALE=2"
echo ""
echo "  Per rimuovere:"
echo "    sudo bash scripts/setup-display-hdmi.sh --uninstall"
echo "========================================"
