#!/usr/bin/env bash
# build-tailwind.sh — rigenera static/tailwind.css (build one-off, da committare).
# Da rilanciare solo quando si aggiungono NUOVE classi Tailwind nei template o
# negli script; il runtime non è necessario sul Pi. Richiede Node (solo in dev).
# Uso: bash scripts/build-tailwind.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/tailwind.config.js" <<EOF
module.exports = {
  content: [
    '$REPO/templates/**/*.html',
    '$REPO/static/*.js',
  ],
}
EOF
printf '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n' > "$TMP/input.css"

cd "$TMP"
npx --yes tailwindcss@3.4 -c tailwind.config.js -i input.css \
    -o "$REPO/static/tailwind.css" --minify

echo "OK: static/tailwind.css rigenerato ($(wc -c < "$REPO/static/tailwind.css") byte)"
