# Installer & CI/CD — Design Document
**Data:** 2026-03-25
**Milestone:** M3 — Installer & CI/CD
**Approccio:** C — install.sh + first-boot wizard + GitHub Actions image

---

## Obiettivo

Rendere l'installazione di pi-Mesh il più semplice possibile partendo da Raspberry Pi OS standard, mantenendo al contempo la possibilità di configurare tutto via file per utenti tecnici. Produrre automaticamente un'immagine SD pronta all'uso ad ogni release stabile.

---

## 1. `install.sh`

### Invocazione

```bash
curl -fsSL https://raw.githubusercontent.com/yayoboy/pi-Mesh/master/install.sh | bash
```

Oppure, già sul Pi:

```bash
bash install.sh
```

### Comportamento

1. **Verifica OS** — abort se non è Raspberry Pi OS / Debian ARM
2. **Dipendenze di sistema** — `apt-get install -y git python3-venv python3-pip pigpiod avahi-daemon` (skip se già installati)
3. **Clone / aggiornamento repo** — clona in `/home/pi/pi-mesh`; se già presente esegue `git pull`
4. **Venv + pip** — `python3 -m venv venv && venv/bin/pip install -r requirements.txt`
5. **config.env** — copia `config.env` in `/boot/firmware/config.env` solo se non esiste già
6. **Servizio systemd** — copia `meshtastic-pi.service`, `systemctl daemon-reload && enable --now`
7. **pigpiod** — `systemctl enable --now pigpiod`
8. **ZRAM** — esegue `scripts/setup_zram.sh` automaticamente
9. **auto-AP** — chiede interattivamente (`--non-interactive` salta la domanda, default: no)
10. **Output finale** — `✓ pi-Mesh pronto → http://pi-mesh.local:8080`

### Flag

| Flag | Comportamento |
|------|---------------|
| `--non-interactive` | Nessuna domanda, usa tutti i default |
| `--update` | Salta installazione dipendenze, fa solo git pull + restart |
| `--no-zram` | Salta setup_zram.sh |
| `--with-ap` | Abilita auto_ap.sh senza chiedere |

### Idempotenza

Rieseguire lo script non rompe nulla: ogni passo controlla lo stato attuale prima di agire.

---

## 2. First-boot wizard

### Rilevamento primo avvio

`config.env` non contiene `SETUP_DONE=1`. In questo stato, `main.py` reindirizza ogni richiesta a `/setup` (tranne `/api/*` e `/ws`).

### Route e template

| Path | Descrizione |
|------|-------------|
| `GET /setup` | Pagina wizard (template `setup.html`) |
| `POST /api/setup/serial-ports` | Restituisce lista `/dev/tty*` disponibili |
| `POST /api/setup/connect` | Prova connessione alla porta selezionata, legge node info |
| `POST /api/setup/save` | Scrive le impostazioni in `config.env`, imposta `SETUP_DONE=1`, riavvia il servizio |

### Step 1 — Radio

- Lista automatica delle porte seriali disponibili (`/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/ttyMESHTASTIC`)
- Select con la porta; pulsante **Connetti** che chiama `POST /api/setup/connect`
- Se la connessione riesce → avanza a Step 2 con node info pre-compilata

### Step 2 — Area mappa

- Mini mappa Leaflet (tile online solo durante il setup via CDN)
- L'utente trascina un rettangolo sull'area geografica di interesse
- Oppure inserisce manualmente le coordinate
- Default: Italia centrale (`41–43°N, 11.5–14.5°E`)
- Salva: `MAP_LAT_MIN/MAX`, `MAP_LON_MIN/MAX`

### Step 3 — Nodo

- Campi **Nome lungo** e **Nome breve** pre-compilati dalla radio (se connessa in Step 1)
- Modificabili; opzionali se la radio ha già i valori
- Se la connessione fallisce: campi vuoti, editabili a mano
- Salva: `NODE_LONG_NAME`, `NODE_SHORT_NAME`

### Completamento

- `POST /api/setup/save` scrive tutte le chiavi in `config.env`
- Scrive `SETUP_DONE=1` in `config.env`
- Riavvia il servizio (`systemctl restart meshtastic-pi`)
- Redirect a `/home`

### Re-esecuzione post-setup

Accessibile da **Settings → Sistema → Riesegui wizard** — rimuove `SETUP_DONE=1` e reindirizza a `/setup`.

---

## 3. GitHub Actions — build immagine

### Trigger

```yaml
on:
  push:
    tags:
      - 'v*.*.*'
```

### Pipeline

**Job 1: `build-image`** (runner: `ubuntu-latest`)

```
1. checkout@v4
2. Download Raspberry Pi OS Lite (arm64) + verifica SHA256
3. Installa QEMU user-static + binfmt_misc
4. Espandi immagine (+2GB liberi per installazione)
5. Monta immagine + chroot con systemd-nspawn
6. All'interno del chroot:
   a. apt update + install git curl python3-venv pigpiod avahi-daemon
   b. Clona repo al tag corrente
   c. Esegue install.sh --non-interactive --no-zram
   d. setup_zram.sh (dentro l'immagine)
   e. Abilita SSH con password "meshtastic" (da cambiare al primo login)
   f. Configura avahi-daemon → pi-mesh.local
   g. NON imposta SETUP_DONE=1 → wizard attivo al primo boot
7. Umonta immagine
8. Esegue pishrink.sh (riduce partizione root al minimo)
9. Comprime con xz -9 → pi-mesh-v1.2.0.img.xz
10. Genera sha256sum.txt
```

**Job 2: `create-release`** (dipende da `build-image`)

```
- Crea GitHub Release con il tag
- Allega pi-mesh-vX.Y.Z.img.xz e sha256sum.txt
- Genera release notes automatiche da git log
```

### Dimensione attesa output

| File | Dimensione |
|------|-----------|
| `.img` non compresso | ~3 GB |
| `.img.xz` compresso | ~750 MB |

### Tempi stimati CI

| Fase | Durata |
|------|--------|
| Download base image | ~3 min |
| Install in chroot | ~10 min |
| Shrink + compress | ~5 min |
| Upload release | ~2 min |
| **Totale** | **~20 min** |

---

## 4. Modifiche ai file esistenti

| File | Modifica |
|------|---------|
| `main.py` | Aggiunge redirect a `/setup` se `SETUP_DONE` assente; nuove route `/setup`, `/api/setup/*` |
| `config.py` | Aggiunge `SETUP_DONE = os.getenv("SETUP_DONE", "0")` |
| `templates/setup.html` | Nuovo template wizard 3-step |
| `install.sh` | Nuovo file nella root del progetto |
| `.github/workflows/build-image.yml` | Nuovo file workflow CI |
| `scripts/build-image.sh` | Script helper richiamato dalla CI |
| `README.md` | Aggiunge sezione "Download immagine pronta" con link alla release |

---

## 5. Struttura directory finale

```
pi-Mesh/
├── install.sh                          ← nuovo
├── .github/
│   └── workflows/
│       └── build-image.yml             ← nuovo
├── scripts/
│   ├── setup_zram.sh
│   ├── auto_ap.sh
│   └── build-image.sh                  ← nuovo (helper CI)
├── templates/
│   └── setup.html                      ← nuovo
└── docs/plans/
    └── 2026-03-25-installer-design.md  ← questo file
```

---

## 6. Considerazioni di sicurezza

- L'immagine pre-built ha SSH abilitato con password `meshtastic` — documentato prominentemente nel README e nella release notes
- Il wizard è esposto senza autenticazione solo se `SETUP_DONE=0`; una volta completato non è più accessibile senza autenticazione esplicita
- `install.sh` via `curl | bash` è comodo ma richiede fiducia nel server; documentare alternativa `wget + verifica + bash`
