#!/usr/bin/env bash
# Attiva un Access Point locale "pi-mesh-portal" se nessun Wi-Fi noto è disponibile.
# Prerequisiti: hostapd, dnsmasq installati. Eseguire come servizio o da rc.local.
set -euo pipefail

AP_SSID="pi-mesh-portal"
AP_PASS="meshtastic"
AP_IP="192.168.88.1"
CHECK_TIMEOUT=60  # secondi di attesa prima di attivare l'AP

check_wifi() {
    # Controlla se siamo connessi a una rete Wi-Fi (indirizzo IP assegnato su wlan0)
    ip addr show wlan0 2>/dev/null | grep -q "inet " && return 0 || return 1
}

echo "Attendo connessione Wi-Fi per ${CHECK_TIMEOUT}s..."
for i in $(seq 1 $CHECK_TIMEOUT); do
    if check_wifi; then
        echo "Wi-Fi connesso. AP non necessario."
        exit 0
    fi
    sleep 1
done

echo "Nessun Wi-Fi trovato — attivazione AP '$AP_SSID'..."

# Configura IP statico
ip addr add "${AP_IP}/24" dev wlan0 2>/dev/null || true

# Configura hostapd
cat > /tmp/hostapd_mesh.conf <<EOF
interface=wlan0
ssid=$AP_SSID
hw_mode=g
channel=6
wpa=2
wpa_passphrase=$AP_PASS
wpa_key_mgmt=WPA-PSK
EOF

# Configura dnsmasq (DHCP + DNS)
cat > /tmp/dnsmasq_mesh.conf <<EOF
interface=wlan0
dhcp-range=192.168.88.10,192.168.88.50,12h
address=/#/$AP_IP
EOF

pkill hostapd  2>/dev/null || true
pkill dnsmasq  2>/dev/null || true

hostapd -B /tmp/hostapd_mesh.conf
dnsmasq -C /tmp/dnsmasq_mesh.conf

echo "AP '$AP_SSID' attivo su $AP_IP — accedi a http://$AP_IP:8080"
