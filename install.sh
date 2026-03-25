#!/usr/bin/env bash
# install.sh — pi-Mesh one-liner installer
# Usage: bash install.sh [--non-interactive] [--update] [--no-zram] [--with-ap]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}  ${NC} $*"; }
ok()    { echo -e "${GREEN}ok${NC} $*"; }
warn()  { echo -e "${YELLOW}!! ${NC} $*"; }
die()   { echo -e "${RED}ERR${NC} $*" >&2; exit 1; }

NON_INTERACTIVE=0; UPDATE_ONLY=0; NO_ZRAM=0; WITH_AP=0
for arg in "$@"; do
  case $arg in
    --non-interactive) NON_INTERACTIVE=1 ;;
    --update)          UPDATE_ONLY=1 ;;
    --no-zram)         NO_ZRAM=1 ;;
    --with-ap)         WITH_AP=1 ;;
  esac
done

INSTALL_DIR="${INSTALL_DIR:-/home/pi/pi-mesh}"
REPO_URL="https://github.com/yayoboy/pi-Mesh.git"
BRANCH="${BRANCH:-master}"
CONFIG_BOOT="/boot/firmware/config.env"

info "Verifica sistema..."
[[ -f /etc/os-release ]] || die "Sistema non supportato"
source /etc/os-release
[[ "$ID" == "raspbian" || "$ID" == "debian" ]] || warn "Sistema non Raspberry Pi OS"
[[ $(uname -m) == arm* || $(uname -m) == aarch64 ]] || warn "Architettura non ARM"

if [[ $UPDATE_ONLY -eq 0 ]]; then
  info "Installazione dipendenze di sistema..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq git python3-venv python3-pip pigpiod avahi-daemon
  ok "Dipendenze di sistema installate"
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "Aggiornamento repo..."
  git -C "$INSTALL_DIR" fetch origin
  git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
  info "Clone repo in $INSTALL_DIR..."
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
ok "Repo aggiornato"

if [[ $UPDATE_ONLY -eq 0 ]]; then
  info "Installazione dipendenze Python..."
  python3 -m venv "$INSTALL_DIR/venv"
  "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
  "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
  ok "Dipendenze Python installate"
fi

if [[ ! -f "$CONFIG_BOOT" ]]; then
  info "Copia config.env in $CONFIG_BOOT..."
  sudo cp "$INSTALL_DIR/config.env" "$CONFIG_BOOT"
  ok "config.env copiato"
else
  ok "config.env gia' presente ($CONFIG_BOOT) — non sovrascritto"
fi

info "Installazione servizio systemd..."
sudo cp "$INSTALL_DIR/meshtastic-pi.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable meshtastic-pi
ok "Servizio installato"

info "Abilitazione pigpiod..."
sudo systemctl enable --now pigpiod
ok "pigpiod attivo"

if [[ $UPDATE_ONLY -eq 0 ]]; then
  info "Abilitazione avahi-daemon (pi-mesh.local)..."
  sudo systemctl enable --now avahi-daemon
  ok "mDNS attivo"
fi

if [[ $NO_ZRAM -eq 0 && $UPDATE_ONLY -eq 0 ]]; then
  info "Configurazione ZRAM..."
  sudo bash "$INSTALL_DIR/scripts/setup_zram.sh"
  ok "ZRAM configurato"
fi

if [[ $WITH_AP -eq 1 ]]; then
  info "Configurazione hotspot fallback..."
  sudo bash "$INSTALL_DIR/scripts/auto_ap.sh"
  ok "Hotspot configurato"
elif [[ $NON_INTERACTIVE -eq 0 ]]; then
  read -r -p "Abilitare hotspot fallback 'pi-mesh-portal' se Wi-Fi non disponibile? [y/N] " yn
  if [[ "${yn,,}" == "y" ]]; then
    sudo bash "$INSTALL_DIR/scripts/auto_ap.sh"
    ok "Hotspot configurato"
  fi
fi

info "Avvio servizio pi-Mesh..."
sudo systemctl restart meshtastic-pi
ok "Servizio avviato"

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  pi-Mesh installato con successo!${NC}"
echo -e "${GREEN}  -> http://pi-mesh.local:8080${NC}"
echo -e "${GREEN}==========================================${NC}"
