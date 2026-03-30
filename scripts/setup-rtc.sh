#!/usr/bin/env bash
# setup-rtc.sh — configura driver RTC I2C sul Pi 3 A+
# Idempotente: sicuro da rieseguire più volte.
# Uso: sudo bash scripts/setup-rtc.sh <model>
# Modelli: ds3231 (default), ds1307, pcf8523, pcf8563, rv3028, mcp7940x, abx80x

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
skip() { echo -e "${YELLOW}  ~ $* (già fatto)${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; exit 1; }

VALID_MODELS="ds3231 ds1307 pcf8523 pcf8563 rv3028 mcp7940x abx80x"
MODEL="${1:-ds3231}"

echo "========================================"
echo "  pi-Mesh — Setup RTC I2C ($MODEL)"
echo "========================================"
echo ""

# Valida modello
if ! echo "$VALID_MODELS" | grep -qw "$MODEL"; then
  err "Modello non supportato: $MODEL. Validi: $VALID_MODELS"
fi

# Richiede root
if [[ $EUID -ne 0 ]]; then
  err "Esegui come root: sudo bash $0 $MODEL"
fi

CONFIG="/boot/firmware/config.txt"
MODULES="/etc/modules"

echo "▶ [1/4] Abilito I2C..."
if raspi-config nonint get_i2c | grep -q "0"; then
  skip "I2C già abilitato"
else
  raspi-config nonint do_i2c 0
  ok "I2C abilitato"
fi

echo ""
echo "▶ [2/4] Configuro dtoverlay in $CONFIG..."
OVERLAY="dtoverlay=i2c-rtc,$MODEL"
if grep -q "dtoverlay=i2c-rtc" "$CONFIG"; then
  skip "$OVERLAY già presente"
else
  echo "$OVERLAY" >> "$CONFIG"
  ok "Aggiunto: $OVERLAY"
fi

echo ""
echo "▶ [3/4] Rimuovo fake-hwclock (interferisce con RTC reale)..."
if dpkg -l fake-hwclock 2>/dev/null | grep -q "^ii"; then
  apt-get purge -y fake-hwclock 2>/dev/null
  ok "fake-hwclock rimosso"
else
  skip "fake-hwclock non installato"
fi

echo ""
echo "▶ [4/4] Configuro hwclock-set..."
HWCLOCK_SET="/lib/udev/hwclock-set"
if [[ -f "$HWCLOCK_SET" ]]; then
  # Commenta le righe che saltano hwclock su sistemi senza RTC onboard
  if grep -q "^if \[ -e /run/systemd" "$HWCLOCK_SET"; then
    sed -i 's|^if \[ -e /run/systemd|#if [ -e /run/systemd|' "$HWCLOCK_SET"
    sed -i 's|^    exit 0|#    exit 0|' "$HWCLOCK_SET"
    sed -i 's|^fi$|#fi|' "$HWCLOCK_SET"
    ok "hwclock-set configurato"
  else
    skip "hwclock-set già configurato"
  fi
else
  skip "hwclock-set non trovato (OK su sistemi recenti)"
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}Setup completato!${NC}"
echo "  Riavvia il Pi per attivare il driver:"
echo "  sudo reboot"
echo ""
echo "  Dopo il reboot, verifica con:"
echo "  sudo hwclock -r"
echo "========================================"
