#!/usr/bin/env bash
# Configura ZRAM swap compresso in RAM (equivale a ~700-800MB effettivi su Pi 3 A+)
# Eseguire una volta all'installazione. Richiede privilegi root.
set -euo pipefail

ZRAM_SIZE="256M"  # Compressa diventa ~512MB di swap effettivo

if ! command -v zramctl &>/dev/null; then
    echo "Installazione zram-tools..."
    apt-get install -y zram-tools
fi

# Carica modulo zram
modprobe zram

ZRAM_DEV=$(zramctl --find --size "$ZRAM_SIZE" --algorithm lz4)
mkswap "$ZRAM_DEV"
swapon --priority 100 "$ZRAM_DEV"

echo "ZRAM attivato: $ZRAM_DEV ($ZRAM_SIZE compressa)"

# Rendi persistente al riavvio via systemd
UNIT="/etc/systemd/system/zram-swap.service"
cat > "$UNIT" <<EOF
[Unit]
Description=ZRAM Swap
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c "modprobe zram && DEV=\$(zramctl --find --size $ZRAM_SIZE --algorithm lz4) && mkswap \$DEV && swapon --priority 100 \$DEV"
ExecStop=/bin/bash -c "swapoff \$(zramctl | awk 'NR>1{print \$1}')"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now zram-swap.service
echo "Servizio zram-swap.service attivato"
