#!/usr/bin/env bash
# backlight.sh — Control MPI3501 display backlight (GPIO 18, ILI9486/tft35a)
#
# Usage:
#   backlight.sh <0-255>     Set brightness (0=off, 255=full)
#   backlight.sh on          Full brightness
#   backlight.sh off         Turn off backlight
#   backlight.sh get         Read current brightness
#
# Requires: dtoverlay=gpio-backlight,gpiopin=18 in /boot/firmware/config.txt
# Falls back to direct raspi-gpio toggle if sysfs node not present.

set -euo pipefail

SYSFS_PATH="/sys/class/backlight/soc:backlight"
GPIO_PIN=18
MAX_BRIGHTNESS=255

usage() {
  echo "Usage: $0 <0-255 | on | off | get>"
  exit 1
}

[[ $# -eq 1 ]] || usage

ARG="$1"

# Normalise on/off to numeric
case "$ARG" in
  on)  VALUE=$MAX_BRIGHTNESS ;;
  off) VALUE=0 ;;
  get)
    if [[ -f "$SYSFS_PATH/brightness" ]]; then
      cat "$SYSFS_PATH/brightness"
    else
      raspi-gpio get "$GPIO_PIN" | grep -oP 'level=\K[0-9]+' || echo "unknown"
    fi
    exit 0
    ;;
  ''|*[!0-9]*)
    echo "Error: argument must be 0-255, on, or off" >&2
    usage
    ;;
  *) VALUE="$ARG" ;;
esac

# Clamp to 0-255
if (( VALUE < 0 || VALUE > 255 )); then
  echo "Error: brightness must be 0-255" >&2
  exit 1
fi

# --- Sysfs path (available after reboot with gpio-backlight overlay) ---
if [[ -f "$SYSFS_PATH/brightness" ]]; then
  echo "$VALUE" > "$SYSFS_PATH/brightness"
  exit 0
fi

# --- Fallback: direct GPIO toggle via raspi-gpio (on/off only, no PWM) ---
# This works without the overlay but provides only binary control.
if command -v raspi-gpio &>/dev/null; then
  if (( VALUE > 0 )); then
    raspi-gpio set "$GPIO_PIN" op dh
  else
    raspi-gpio set "$GPIO_PIN" op dl
  fi
  exit 0
fi

echo "Error: neither $SYSFS_PATH nor raspi-gpio available." >&2
echo "Add 'dtoverlay=gpio-backlight,gpiopin=18' to /boot/firmware/config.txt and reboot." >&2
exit 1
