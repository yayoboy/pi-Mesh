# Design: scripts/optimize-pi.sh (YAY-152)

**Goal:** Script bash eseguito una volta sul Pi per liberare RAM (disabilitando servizi inutili) e disco (rimuovendo pacchetti non necessari).

---

## Deliverable

Un singolo file `scripts/optimize-pi.sh` eseguibile via SSH o direttamente sul Pi.

---

## Pacchetti da rimuovere

| Pacchetto | Motivo |
|-----------|--------|
| `mkvtoolnix` | Tool video editing (~25MB installato) |
| `gcc-12` `g++-12` `gdb` | Compilatori C/C++, non servono in produzione |
| `linux-headers-6.12.47+rpt-common-rpi` | Header kernel vecchio (abbiamo 6.12.75) |
| `linux-headers-6.12.47+rpt-rpi-2712` | idem |
| `linux-headers-6.12.47+rpt-rpi-v8` | idem |
| `modemmanager` | Gestione modem 3G/4G, non presente |
| `triggerhappy` | Daemon eventi tastiera hardware, inutile headless |
| `bluez` `pi-bluetooth` `bluez-firmware` | Bluetooth — non usato (Heltec via USB seriale) |

Seguiti da `apt-get autoremove -y` e `apt-get clean` per liberare dipendenze orfane e cache.

---

## Servizi da disabilitare

| Servizio | Motivo |
|----------|--------|
| `bluetooth.service` | Bluetooth non usato |
| `ModemManager.service` | Modem 3G/4G non presente |
| `triggerhappy.service` | Tastiera hardware, inutile headless |

Comando: `systemctl disable --now <service>` (idempotente — non fallisce se già disabilitato).

---

## Struttura script

```
scripts/optimize-pi.sh
├── Banner iniziale (versione, data)
├── Check: deve girare come root
├── Sezione 1: Disabilita servizi
├── Sezione 2: Rimuovi pacchetti (purge + autoremove)
├── Sezione 3: Pulizia cache apt
└── Riepilogo finale: spazio liberato prima/dopo
```

**Output:** colorato (verde OK, giallo SKIP se già rimosso, rosso ERROR).

**Idempotenza:** sicuro da rieseguire — `apt purge` e `systemctl disable` non falliscono se già applicati.

---

## Non toccare

- `avahi-daemon` — mDNS, potrebbe servire per `pimesh.local`
- `NetworkManager`, `wpa_supplicant` — gestione WiFi necessaria
- `wireless-regdb` — regolamentazione wireless necessaria
- `firmware-brcm80211` — firmware WiFi onboard Pi 3
