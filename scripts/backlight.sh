#!/usr/bin/env bash
# backlight.sh — Display brightness, auto-detecting the display type:
#   1. HDMI panel with DDC/CI (ddcutil, VCP 0x10, scale 0-100)
#   2. SPI display backlight via sysfs (gpio-backlight overlay, GPIO 18)
#   3. Fallback: raspi-gpio on/off toggle (no PWM)
#
# Usage:
#   backlight.sh <0-255>     Set brightness (0=off, 255=full)
#   backlight.sh on          Full brightness
#   backlight.sh off         Turn off backlight
#   backlight.sh get         Read current brightness
#
# SPI path requires: dtoverlay=gpio-backlight,gpiopin=18 in /boot/firmware/config.txt

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
    if command -v ddcutil &>/dev/null; then
      PCT=$(ddcutil --brief getvcp 10 2>/dev/null | awk '{print $4}')
      if [[ "$PCT" =~ ^[0-9]+$ ]]; then
        echo $(( PCT * MAX_BRIGHTNESS / 100 ))
        exit 0
      fi
    fi
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

# --- HDMI panel via DDC/CI (VCP 0x10 wants 0-100) ---
if command -v ddcutil &>/dev/null; then
  PCT=$(( VALUE * 100 / MAX_BRIGHTNESS ))
  if ddcutil --brief setvcp 10 "$PCT" 2>/dev/null; then
    exit 0
  fi
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
