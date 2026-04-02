# Optimize Pi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Creare `scripts/optimize-pi.sh` — script bash idempotente che disabilita servizi inutili e rimuove pacchetti non necessari dal Pi 3 A+.

**Architecture:** Singolo script bash con tre sezioni sequenziali (servizi → pacchetti → pulizia), output colorato, riepilogo spazio liberato prima/dopo.

**Tech Stack:** bash, systemctl, apt-get.

---

## File Structure

| File | Azione |
|------|--------|
| `scripts/optimize-pi.sh` | crea — script di ottimizzazione |

---

## Task 1: Crea scripts/optimize-pi.sh

**Files:**
- Create: `scripts/optimize-pi.sh`

- [ ] **Step 1: Crea il file**

```bash
#!/usr/bin/env bash
# optimize-pi.sh — rimuove pacchetti e servizi inutili dal Pi 3 A+
# Idempotente: sicuro da rieseguire più volte.
# Uso: sudo bash scripts/optimize-pi.sh

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
skip() { echo -e "${YELLOW}  ~ $* (già fatto)${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; }

echo "========================================"
echo "  pi-Mesh — Ottimizzazione Raspberry Pi"
echo "========================================"
echo ""

# Richiede root
if [[ $EUID -ne 0 ]]; then
  err "Esegui come root: sudo bash $0"
  exit 1
fi

# --- SPAZIO INIZIALE ---
DISK_BEFORE=$(df / --output=used | tail -1)

echo "▶ [1/3] Disabilito servizi inutili..."
echo ""

disable_service() {
  local svc="$1"
  if systemctl is-enabled "$svc" &>/dev/null; then
    systemctl disable --now "$svc" 2>/dev/null && ok "Disabilitato: $svc" || err "Errore: $svc"
  else
    skip "$svc"
  fi
}

disable_service bluetooth.service
disable_service ModemManager.service
disable_service triggerhappy.service

echo ""
echo "▶ [2/3] Rimuovo pacchetti non necessari..."
echo ""

PKGS=(
  mkvtoolnix
  gcc-12
  g++-12
  gdb
  linux-headers-6.12.47+rpt-common-rpi
  "linux-headers-6.12.47+rpt-rpi-2712"
  "linux-headers-6.12.47+rpt-rpi-v8"
  modemmanager
  triggerhappy
  bluez
  pi-bluetooth
  bluez-firmware
)

TO_REMOVE=()
for pkg in "${PKGS[@]}"; do
  if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
    TO_REMOVE+=("$pkg")
  else
    skip "$pkg"
  fi
done

if [[ ${#TO_REMOVE[@]} -gt 0 ]]; then
  apt-get purge -y "${TO_REMOVE[@]}" 2>&1 | grep -E "Removing|Purging" | while read -r line; do
    ok "$line"
  done
  apt-get autoremove -y --purge 2>&1 | grep -E "Removing|Purging" | while read -r line; do
    ok "$line"
  done
fi

echo ""
echo "▶ [3/3] Pulizia cache apt..."
echo ""

apt-get clean
ok "Cache apt pulita"

# --- RIEPILOGO ---
DISK_AFTER=$(df / --output=used | tail -1)
FREED=$(( (DISK_BEFORE - DISK_AFTER) / 1024 ))

echo ""
echo "========================================"
echo -e "  ${GREEN}Ottimizzazione completata!${NC}"
printf "  Spazio liberato: ~%d MB\n" "$FREED"
echo "========================================"
```

- [ ] **Step 2: Rendi eseguibile**

```bash
chmod +x scripts/optimize-pi.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/optimize-pi.sh
git commit -m "feat: add optimize-pi.sh — remove unused packages and services (YAY-152)"
```

---

## Task 2: Esegui sul Pi

**SSH:** `pimesh@192.168.1.36` password `pimesh`

- [ ] **Step 1: Push e copia sul Pi**

```bash
git push
sshpass -p 'pimesh' ssh pimesh@192.168.1.36 'cd ~/pi-Mesh && git pull'
```

- [ ] **Step 2: Esegui lo script**

```bash
sshpass -p 'pimesh' ssh pimesh@192.168.1.36 'sudo bash ~/pi-Mesh/scripts/optimize-pi.sh'
```

Output atteso: sezioni 1/3, 2/3, 3/3 con ✓ per ogni azione, riepilogo con MB liberati.

- [ ] **Step 3: Verifica RAM liberata**

```bash
sshpass -p 'pimesh' ssh pimesh@192.168.1.36 'free -m && systemctl is-active bluetooth.service ModemManager.service triggerhappy.service'
```

Output atteso: RAM `used` inferiore a 178MB, i tre servizi in stato `inactive` o `failed`.

- [ ] **Step 4: Verifica che pimesh.service funzioni ancora**

```bash
sshpass -p 'pimesh' ssh pimesh@192.168.1.36 'systemctl is-active pimesh.service'
```

Output atteso: `active`

---

## Task 3: Chiudi su Linear

- [ ] **Step 1: Marca YAY-152 come Done su Linear**
