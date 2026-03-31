#!/usr/bin/env bash
# manage-tiles.sh — Select region, download tiles if needed, rsync to Pi
# Usage: bash scripts/manage-tiles.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TILES_DIR="$PROJECT_DIR/static/tiles"
CONFIG_ENV="$PROJECT_DIR/config.env"

# ─── Region definitions ─────────────────────────────────────────────────────
declare -A REGION_NAMES=(
  [italia]="🇮🇹  Italia"
  [francia]="🇫🇷  Francia"
  [germania]="🇩🇪  Germania"
  [spagna]="🇪🇸  Spagna"
  [europa]="🌍  Europa"
  [mondo]="🌐  Mondo (z1-z8)"
)
declare -A REGION_LAT_MIN=([italia]=35.0 [francia]=41.3 [germania]=47.3 [spagna]=35.9 [europa]=34.0 [mondo]=-85.0)
declare -A REGION_LAT_MAX=([italia]=47.5 [francia]=51.1 [germania]=55.1 [spagna]=43.8 [europa]=72.0 [mondo]=85.0)
declare -A REGION_LON_MIN=([italia]=6.5  [francia]=-5.2 [germania]=5.9  [spagna]=-9.3 [europa]=-25.0 [mondo]=-180.0)
declare -A REGION_LON_MAX=([italia]=18.5 [francia]=9.6  [germania]=15.0 [spagna]=4.3  [europa]=45.0  [mondo]=180.0)
declare -A REGION_ZOOM=([italia]="7 8 9 10 11 12" [francia]="7 8 9 10 11 12" [germania]="7 8 9 10 11 12" [spagna]="7 8 9 10 11 12" [europa]="7 8 9 10 11" [mondo]="1 2 3 4 5 6 7 8")
REGION_KEYS=(italia francia germania spagna europa mondo)

# ─── Read Pi SSH settings ────────────────────────────────────────────────────
PI_HOST=$(grep '^SSH_HOST=' "$CONFIG_ENV" 2>/dev/null | cut -d= -f2 || true)
PI_USER=$(grep '^SSH_USER=' "$CONFIG_ENV" 2>/dev/null | cut -d= -f2 || echo "pimesh")
PI_PATH="/home/${PI_USER}/pi-Mesh/static/tiles"

if [[ -z "$PI_HOST" ]]; then
  read -r -p "Pi IP address [192.168.1.36]: " PI_HOST
  PI_HOST="${PI_HOST:-192.168.1.36}"
fi

# ─── Menu ────────────────────────────────────────────────────────────────────
echo ""
echo "  🗺  pi-Mesh Tile Manager"
echo "  Pi: ${PI_USER}@${PI_HOST}"
echo ""
echo "  Seleziona regione:"
echo ""
i=1
for key in "${REGION_KEYS[@]}"; do
  local_status=""
  if [[ -d "$TILES_DIR/osm/$(echo "${REGION_ZOOM[$key]}" | awk '{print $1}')" ]]; then
    size=$(du -sh "$TILES_DIR" 2>/dev/null | cut -f1 || echo "?")
    local_status=" \033[32m✓ tile presenti ($size)\033[0m"
  else
    local_status=" \033[90m— non scaricate\033[0m"
  fi
  printf "  %d) %s%b\n" "$i" "${REGION_NAMES[$key]}" "$local_status"
  ((i++))
done
echo ""
read -r -p "  > " choice
echo ""

# Validate input
if ! [[ "$choice" =~ ^[1-6]$ ]]; then
  echo "Scelta non valida." && exit 1
fi
REGION="${REGION_KEYS[$((choice-1))]}"
echo "  Regione selezionata: ${REGION_NAMES[$REGION]}"
echo ""

# ─── Download tiles if missing ───────────────────────────────────────────────
LAYERS=(osm topo satellite)
LAYER_URLS=(
  "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
  "https://tile.opentopomap.org/{z}/{x}/{y}.png"
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

_lon2x() { echo "scale=0; (($1 + 180) / 360 * 2^$2) / 1" | bc; }
_lat2y() {
  python3 -c "
import math, sys
lat,z = float('$1'), int('$2')
lat_r = math.radians(lat)
n = 2**z
y = int((1 - math.log(math.tan(lat_r) + 1/math.cos(lat_r))/math.pi) / 2 * n)
print(y)
"
}

for idx in 0 1 2; do
  LAYER="${LAYERS[$idx]}"
  URL_TMPL="${LAYER_URLS[$idx]}"
  LAYER_DIR="$TILES_DIR/$LAYER"

  missing=false
  for z in ${REGION_ZOOM[$REGION]}; do
    [[ ! -d "$LAYER_DIR/$z" ]] && missing=true && break
  done

  if $missing; then
    echo "  📥 Download layer: $LAYER"
    for z in ${REGION_ZOOM[$REGION]}; do
      x_min=$(_lon2x "${REGION_LON_MIN[$REGION]}" "$z")
      x_max=$(_lon2x "${REGION_LON_MAX[$REGION]}" "$z")
      y_min=$(_lat2y "${REGION_LAT_MAX[$REGION]}" "$z")
      y_max=$(_lat2y "${REGION_LAT_MIN[$REGION]}" "$z")
      echo "    z=$z: x=$x_min-$x_max y=$y_min-$y_max"
      for ((x=x_min; x<=x_max; x++)); do
        mkdir -p "$LAYER_DIR/$z/$x"
        for ((y=y_min; y<=y_max; y++)); do
          dest="$LAYER_DIR/$z/$x/$y.png"
          [[ -f "$dest" ]] && continue
          url="${URL_TMPL//\{z\}/$z}"
          url="${url//\{x\}/$x}"
          url="${url//\{y\}/$y}"
          curl -sf -A "pi-Mesh/1.0 tile-download" -o "$dest" "$url" || true
          sleep 0.15  # respect rate limits
        done
      done
    done
    echo "  ✓ Layer $LAYER scaricato"
    echo ""
  else
    echo "  ✓ Layer $LAYER già presente"
  fi
done

# ─── rsync to Pi ────────────────────────────────────────────────────────────
echo "  📡 Trasferisco tile al Pi..."
rsync -av --progress "$TILES_DIR/" "${PI_USER}@${PI_HOST}:${PI_PATH}/" || {
  echo "  ❌ Rsync fallito. Verifica connessione SSH e permessi."
  exit 1
}
echo "  ✓ Tile copiate"
echo ""

# ─── Update Pi config ────────────────────────────────────────────────────────
echo "  ⚙️  Aggiorno configurazione Pi..."
ssh "${PI_USER}@${PI_HOST}" "
  cd ~/pi-Mesh
  grep -q '^MAP_LOCAL_TILES=' config.env && sed -i 's/^MAP_LOCAL_TILES=.*/MAP_LOCAL_TILES=1/' config.env || echo 'MAP_LOCAL_TILES=1' >> config.env
  grep -q '^MAP_REGION=' config.env && sed -i 's/^MAP_REGION=.*/MAP_REGION=${REGION}/' config.env || echo 'MAP_REGION=${REGION}' >> config.env
  grep -q '^SSH_HOST=' config.env || echo 'SSH_HOST=${PI_HOST}' >> config.env
  sudo systemctl restart pimesh
  echo '✓ Config aggiornata e pimesh riavviato'
"
echo ""
echo "  ✅ Done! pi-Mesh ora usa tile locali per: ${REGION_NAMES[$REGION]}"
