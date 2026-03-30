# Design: RTC I2C Support (YAY-153)

**Goal:** Supporto moduli RTC I2C sul Pi 3 A+: script di setup del driver + stato RTC nell'app web.

---

## Componenti

### 1. Script `scripts/setup-rtc.sh`

Script bash eseguito una volta come root per configurare il driver RTC.

**Parametro:** modello RTC (default: `ds3231`)

**Modelli supportati:** `ds3231`, `ds1307`, `pcf8523`, `pcf8563`, `rv3028`, `mcp7940x`, `abx80x`

**Azioni (idempotenti):**
1. Valida il modello passato come argomento
2. Abilita I2C via `raspi-config nonint do_i2c 0` (skip se già abilitato)
3. Aggiunge `dtoverlay=i2c-rtc,<model>` a `/boot/firmware/config.txt` (skip se già presente)
4. Rimuove `fake-hwclock` se installato (`apt-get purge -y fake-hwclock`)
5. Aggiunge `rtc-ds1307` (o il modulo corretto) a `/etc/modules` (skip se già presente)
6. Configura `/lib/udev/hwclock-set` per non saltare hwclock su sistemi senza RTC onboard
7. Output colorato (ok/skip/err), riepilogo finale con istruzione di reboot

**Uso:**
```bash
sudo bash scripts/setup-rtc.sh ds3231
sudo bash scripts/setup-rtc.sh ds1307
```

**Dopo il reboot**, Linux esegue automaticamente `hwclock -s` (RTC → sistema) prima di NTP.

---

### 2. API endpoint `GET /api/config/rtc/status`

Legge lo stato del driver RTC senza modificare nulla.

**Response:**
```json
{
  "configured": true,
  "model": "ds3231",
  "device": "/dev/rtc0",
  "time": "2026-03-30T21:00:00"
}
```
oppure:
```json
{
  "configured": false,
  "model": null,
  "device": null,
  "time": null
}
```

**Logica:**
- `configured`: cerca `dtoverlay=i2c-rtc` in `/boot/firmware/config.txt`
- `model`: estrae il modello dalla riga dtoverlay
- `device`: controlla se `/dev/rtc0` esiste
- `time`: se `/dev/rtc0` esiste, legge l'ora con `hwclock -r --rtc=/dev/rtc0`

---

### 3. UI — nuova sezione "RTC" in `templates/config.html`

**Sidebar:** aggiunge `{ id: 'rtc', label: 'RTC' }` alle sections.

**Contenuto sezione:**

- **Stato:** badge verde "Attivo · DS3231 · /dev/rtc0 · 2026-03-30 21:00" oppure badge grigio "Non configurato"
- **Dropdown modello:** selezione tra i modelli supportati
- **Comando setup:** box di testo read-only con il comando da copiare:
  ```
  sudo bash ~/pi-Mesh/scripts/setup-rtc.sh ds3231
  ```
- **Nota:** "Richiede reboot per attivare il driver."
- La sezione si aggiorna ogni volta che viene selezionata (lazy load come le altre).

---

## File modificati

| File | Azione |
|------|--------|
| `scripts/setup-rtc.sh` | crea |
| `routers/config_router.py` | modifica — aggiungi `GET /api/config/rtc/status` |
| `templates/config.html` | modifica — aggiungi sezione RTC + sidebar item |
| `tests/test_api.py` | modifica — aggiungi test endpoint RTC status |

---

## Vincoli

- L'app **non esegue** lo script automaticamente (niente subprocess con sudo dall'app web)
- Lo script è l'unico punto di modifica del sistema
- L'endpoint è read-only (solo status)
- Il tipo "rtc" in GPIO config rimane invariato (registra la periferica, non configura il driver)
