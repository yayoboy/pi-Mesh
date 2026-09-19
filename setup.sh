#!/usr/bin/env bash
# setup.sh — One-command pi-Mesh setup on Raspberry Pi OS, Debian or Ubuntu
# (Raspberry Pi, Orange Pi 4 Pro, any Linux SBC with a USB radio)
#
# Usage: sudo bash setup.sh [headless|kiosk-spi|kiosk-hdmi|desktop] [--with-meshtasticd]
#
# The profile decides what gets installed beyond the backend. Omit it and the
# machine is probed: SPI framebuffer → kiosk-spi, graphical target → desktop,
# connected DRM output → kiosk-hdmi, otherwise headless (Pi Zero, servers).
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="${SUDO_USER:-pimesh}"
HOME_DIR="/home/$USER"

detect_profile() {
    if [ -e /sys/class/graphics/fb1 ]; then
        echo kiosk-spi
    elif systemctl get-default 2>/dev/null | grep -q graphical; then
        echo desktop
    elif grep -qx connected /sys/class/drm/*/status 2>/dev/null; then
        echo kiosk-hdmi
    else
        echo headless
    fi
}

PROFILE=""
WITH_MESHTASTICD=0
for arg in "$@"; do
    case "$arg" in
        headless|kiosk-spi|kiosk-hdmi|desktop) PROFILE="$arg" ;;
        --with-meshtasticd) WITH_MESHTASTICD=1 ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done
[ -n "$PROFILE" ] || { PROFILE="$(detect_profile)"; echo "==> Profile auto-detected: $PROFILE"; }

# MemTotal in kB. zram earns its keep under ~2 GB; above that it is noise.
RAM_KB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"

echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends python3-venv python3-pip git

if [ "$RAM_KB" -lt 2097152 ]; then
    echo "==> Configuring zram swap (lz4, 50% RAM)..."
    apt-get install -y --no-install-recommends zram-tools
    cat > /etc/default/zramswap <<'EOF'
ALGO=lz4
PERCENT=50
EOF
    systemctl restart zramswap
    echo "    zram swap active: $(zramctl)"
else
    echo "==> Skipping zram ($((RAM_KB / 1024)) MB RAM — not needed)"
fi

create_venv() {
    local extra_flags="$1"
    sudo -u "$USER" rm -rf "$REPO_DIR/venv"
    # shellcheck disable=SC2086
    sudo -u "$USER" python3 -m venv $extra_flags "$REPO_DIR/venv"
    sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q --upgrade pip
}

install_core() {
    echo "==> Installing core Python deps..."
    sudo -u "$USER" "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
}

echo "==> Setting up Python venv..."
create_venv ""
install_core

echo "==> Group membership (gpio, dialout)..."
# Raspberry Pi OS ships a gpio group and a udev rule that hands /dev/gpiochip*
# to it. Debian and Ubuntu (Orange Pi images included) ship neither, so the
# GPIO would only work as root there: create both.
if ! getent group gpio >/dev/null; then
    groupadd gpio
    echo 'SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"' \
        > /etc/udev/rules.d/60-pimesh-gpio.rules
    udevadm control --reload-rules && udevadm trigger --subsystem-match=gpio
    echo "    gpio group created, /dev/gpiochip* handed to it"
fi
# /dev/gpiochip* for the buzzer and LEDs, /dev/tty* for the radio: both
# without root. dialout does not exist on every distribution.
for grp in gpio dialout; do
    if getent group "$grp" >/dev/null; then
        usermod -aG "$grp" "$USER"
        echo "    $USER added to $grp"
    fi
done

echo "==> Stable serial alias for the radio..."
# config.env points SERIAL_PATH at /dev/ttyMESHTASTIC. Without this rule that
# path never appears, and the client retries against it forever: the radio is
# plugged in and the UI still shows no board.
if [ ! -f /etc/udev/rules.d/99-meshtastic-serial.rules ]; then
    install -m 644 "$REPO_DIR/scripts/99-meshtastic-serial.rules" /etc/udev/rules.d/
    udevadm control --reload-rules && udevadm trigger --subsystem-match=tty
    echo "    /dev/ttyMESHTASTIC alias installed"
else
    echo "    already installed"
fi

echo "==> Creating data directory..."
sudo -u "$USER" mkdir -p "$REPO_DIR/data"

# The unit loads config.env as an EnvironmentFile and systemd refuses to start
# a service whose EnvironmentFile is missing. A fresh clone only ships the
# example, so seed it here; an existing config is never overwritten.
[ -f "$REPO_DIR/config.env" ] || \
    sudo -u "$USER" cp "$REPO_DIR/config.env.example" "$REPO_DIR/config.env"

echo "==> Installing systemd services..."
# The unit is written for user pimesh with the repo in /home/pimesh/pi-Mesh;
# rewrite it for whoever runs this script and wherever the repo actually is.
sed -e "s|/home/pimesh/pi-Mesh|$REPO_DIR|g" -e "s|^User=pimesh|User=$USER|" \
    "$REPO_DIR/systemd/pimesh.service" > /etc/systemd/system/pimesh.service
systemctl daemon-reload
systemctl enable pimesh

# meshtasticd only serves native LoRa HATs; an ESP32 board over USB is driven
# directly by meshtastic.SerialInterface and the daemon just holds the port.
if [ "$WITH_MESHTASTICD" = 1 ]; then
    cp "$REPO_DIR/systemd/meshtasticd.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable meshtasticd
    systemctl start  meshtasticd
    sleep 3
fi
systemctl start  pimesh

if [ "$PROFILE" = desktop ]; then
    echo "==> Installing desktop launcher..."
    # Raspberry Pi OS Desktop ships Chromium, so the launcher finds a browser.
    # The Orange Pi image ships a full XFCE session and no browser at all, and
    # there the launcher would open nothing. Install one only when missing.
    if ! command -v chromium-browser >/dev/null && ! command -v chromium >/dev/null; then
        echo "    No browser installed: adding chromium..."
        apt-get install -y --no-install-recommends chromium
    fi
    # Exec deve nominare un eseguibile, non una riga di shell: si scrive qui
    # quello che la macchina ha, ora che sappiamo che c'è.
    BROWSER="$(command -v chromium-browser || command -v chromium || command -v xdg-open)"
    case "$BROWSER" in
        */xdg-open) EXEC="$BROWSER http://localhost:8080" ;;
        *)          EXEC="$BROWSER --app=http://localhost:8080 --window-size=1024,600" ;;
    esac
    LAUNCHER="$(mktemp)"
    sed "s|^Exec=.*|Exec=$EXEC|" "$REPO_DIR/pimesh.desktop" > "$LAUNCHER"
    install -m 644 "$LAUNCHER" /usr/share/applications/pimesh.desktop
    if [ -d "$HOME_DIR/Desktop" ]; then
        install -m 755 -o "$USER" -g "$USER" "$LAUNCHER" "$HOME_DIR/Desktop/pimesh.desktop"
        # XFCE non avvia un .desktop che sta sulla scrivania finché non è
        # "marcato sicuro": un doppio click apre soltanto un avviso, e
        # l'applicazione non parte. Lo marchiamo qui, che è esattamente ciò che
        # fa il pulsante "Mark As Secure And Launch" di quell'avviso. Il
        # checksum va scritto come metadato GIO, e per farlo serve il bus di
        # sessione dell'utente: se non ha ancora fatto login non c'è, e in quel
        # caso l'avviso comparirà una volta sola.
        if sudo -u "$USER" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u "$USER")/bus" \
             gio set -t string "$HOME_DIR/Desktop/pimesh.desktop" metadata::xfce-exe-checksum \
             "$(sha256sum "$HOME_DIR/Desktop/pimesh.desktop" | cut -d' ' -f1)" 2>/dev/null; then
            echo "    icona marcata come sicura per XFCE"
        else
            echo "    icona non marcata: al primo click XFCE chiederà conferma una volta"
        fi
    fi
    # Su un terminale la finestra deve esserci già all'accensione: lo stesso
    # file in ~/.config/autostart la apre a ogni login, senza toccare niente.
    # È lo standard XDG, quindi vale per XFCE, LXDE, GNOME e compagnia.
    install -d -m 755 -o "$USER" -g "$USER" "$HOME_DIR/.config/autostart"
    install -m 644 -o "$USER" -g "$USER" "$LAUNCHER" "$HOME_DIR/.config/autostart/pimesh.desktop"
    rm -f "$LAUNCHER"
    echo "    launcher: $EXEC"
    echo "    autostart: si apre da sola al login"
fi

echo
echo "==> Done. Profile: $PROFILE"
echo
echo "    Web UI: http://localhost:8080  (also reachable on the LAN)"
echo
case "$PROFILE" in
    headless)
        echo "    Headless: open the UI from another device on the network."
        ;;
    kiosk-spi)
        echo "    Next step — SPI 3.5\" kiosk: sudo bash scripts/setup-display.sh"
        ;;
    kiosk-hdmi)
        echo "    Next step — HDMI GPU kiosk: sudo bash scripts/setup-display-hdmi.sh"
        ;;
    desktop)
        echo "    Launcher installed: look for \"pi-Mesh\" in the menu or on the desktop."
        ;;
esac
echo
