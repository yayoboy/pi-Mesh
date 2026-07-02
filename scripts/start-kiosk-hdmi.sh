#!/bin/bash
# start-kiosk-hdmi.sh — Kiosk browser launcher per display HDMI (cog/WPE su DRM).
# Usato da kiosk-hdmi.service. Nessun X server: cog disegna direttamente su
# KMS/DRM con compositing accelerato dalla GPU (vc4).
#
# Scala automaticamente la UI in base alla risoluzione del display: la UI è
# disegnata per ~512 CSS px di larghezza in landscape, quindi su un 1024×600
# usa scale 2, su un 800×480 scale 1.5, ecc. Override manuale con
# PIMESH_HDMI_SCALE in config.env.

set -e

# Config opzionale (PIMESH_HDMI_SCALE, PIMESH_URL, ...)
if [ -f /home/pimesh/pi-Mesh/config.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /home/pimesh/pi-Mesh/config.env
  set +a
fi

URL="${PIMESH_URL:-http://localhost:8080}"
DESIGN_W=512   # larghezza CSS di riferimento della UI (landscape)

# Attendi che uvicorn sia pronto (max 60s)
echo "Waiting for pimesh..." >&2
for i in $(seq 1 60); do
  if curl -sf "$URL" > /dev/null 2>&1; then
    echo "pimesh ready after ${i}s" >&2
    break
  fi
  sleep 1
done

# Scala: da PIMESH_HDMI_SCALE, oppure calcolata dal modo preferito del
# connettore HDMI (prima riga di /sys/class/drm/card*-HDMI-A-*/modes),
# arrotondata al quarto e limitata a [1, 2]. Il tetto a 2 fa sì che sopra
# i 1024 px il viewport CSS superi i 640 px e la UI passi ai layout
# multi-colonna invece di ingrandire all'infinito.
SCALE="${PIMESH_HDMI_SCALE:-}"
if [ -z "$SCALE" ]; then
  MODE=$(cat /sys/class/drm/card*-HDMI-A-*/modes 2>/dev/null | head -1)
  WIDTH="${MODE%%x*}"
  if [ -n "$WIDTH" ] && [ "$WIDTH" -gt 0 ] 2>/dev/null; then
    SCALE=$(awk -v w="$WIDTH" -v d="$DESIGN_W" 'BEGIN {
      s = int(w / d * 4 + 0.5) / 4
      if (s < 1) s = 1
      if (s > 2) s = 2
      print s
    }')
  else
    SCALE=1
  fi
fi
echo "HDMI mode: ${MODE:-unknown}, scale: $SCALE" >&2

# --scale è supportato dal platform drm di cog; se la versione installata
# non lo prevede, riparti senza (meglio una UI piccola che nessuna UI).
if cog --help 2>&1 | grep -q -- '--scale'; then
  exec cog -P drm --scale="$SCALE" "$URL"
else
  echo "cog senza supporto --scale, avvio a scala 1" >&2
  exec cog -P drm "$URL"
fi
