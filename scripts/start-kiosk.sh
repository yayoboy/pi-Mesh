#!/bin/bash
# start-kiosk.sh — Kiosk browser launcher for pi-Mesh
# Used by kiosk.service via xinit
export DISPLAY=:0
xset -dpms
xset s off
xset s noblank

matchbox-window-manager -use_titlebar no &

# Wait for pimesh uvicorn to be ready (max 60s)
echo "Waiting for pimesh..." >&2
for i in $(seq 1 60); do
  if curl -sf http://localhost:8080 > /dev/null 2>&1; then
    echo "pimesh ready after ${i}s" >&2
    break
  fi
  sleep 1
done

exec surf -F http://localhost:8080
