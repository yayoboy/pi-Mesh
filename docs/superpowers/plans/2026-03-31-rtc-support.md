# RTC I2C Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere supporto moduli RTC I2C: script di setup driver + endpoint status + sezione UI in config.

**Architecture:** Script bash idempotente per configurare il driver kernel; endpoint `GET /api/config/rtc/status` read-only che legge `/boot/firmware/config.txt` e `/dev/rtc0`; sezione "RTC" in config.html con lazy-load come le altre sezioni.

**Tech Stack:** Python 3.11, FastAPI, subprocess, Alpine.js, bash.

---

## File Structure

| File | Azione |
|------|--------|
| `scripts/setup-rtc.sh` | crea |
| `routers/config_router.py` | modifica — aggiungi `GET /api/config/rtc/status` |
| `templates/config.html` | modifica — aggiungi sidebar item RTC + sezione template |
| `tests/test_api.py` | modifica — aggiungi test endpoint RTC status |

---

## Task 1: scripts/setup-rtc.sh

**Files:**
- Create: `scripts/setup-rtc.sh`

- [ ] **Step 1: Crea il file**

```bash
#!/usr/bin/env bash
# setup-rtc.sh — configura driver RTC I2C sul Pi 3 A+
# Idempotente: sicuro da rieseguire più volte.
# Uso: sudo bash scripts/setup-rtc.sh <model>
# Modelli: ds3231 (default), ds1307, pcf8523, pcf8563, rv3028, mcp7940x, abx80x

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
skip() { echo -e "${YELLOW}  ~ $* (già fatto)${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; exit 1; }

VALID_MODELS="ds3231 ds1307 pcf8523 pcf8563 rv3028 mcp7940x abx80x"
MODEL="${1:-ds3231}"

echo "========================================"
echo "  pi-Mesh — Setup RTC I2C ($MODEL)"
echo "========================================"
echo ""

# Valida modello
if ! echo "$VALID_MODELS" | grep -qw "$MODEL"; then
  err "Modello non supportato: $MODEL. Validi: $VALID_MODELS"
fi

# Richiede root
if [[ $EUID -ne 0 ]]; then
  err "Esegui come root: sudo bash $0 $MODEL"
fi

CONFIG="/boot/firmware/config.txt"
MODULES="/etc/modules"

echo "▶ [1/4] Abilito I2C..."
if raspi-config nonint get_i2c | grep -q "0"; then
  skip "I2C già abilitato"
else
  raspi-config nonint do_i2c 0
  ok "I2C abilitato"
fi

echo ""
echo "▶ [2/4] Configuro dtoverlay in $CONFIG..."
OVERLAY="dtoverlay=i2c-rtc,$MODEL"
if grep -q "dtoverlay=i2c-rtc" "$CONFIG"; then
  skip "$OVERLAY già presente"
else
  echo "$OVERLAY" >> "$CONFIG"
  ok "Aggiunto: $OVERLAY"
fi

echo ""
echo "▶ [3/4] Rimuovo fake-hwclock (interferisce con RTC reale)..."
if dpkg -l fake-hwclock 2>/dev/null | grep -q "^ii"; then
  apt-get purge -y fake-hwclock 2>/dev/null
  ok "fake-hwclock rimosso"
else
  skip "fake-hwclock non installato"
fi

echo ""
echo "▶ [4/4] Configuro hwclock-set..."
HWCLOCK_SET="/lib/udev/hwclock-set"
if [[ -f "$HWCLOCK_SET" ]]; then
  # Commenta le righe che saltano hwclock su sistemi senza RTC onboard
  if grep -q "^if \[ -e /run/systemd" "$HWCLOCK_SET"; then
    sed -i 's|^if \[ -e /run/systemd|#if [ -e /run/systemd|' "$HWCLOCK_SET"
    sed -i 's|^    exit 0|#    exit 0|' "$HWCLOCK_SET"
    sed -i 's|^fi$|#fi|' "$HWCLOCK_SET"
    ok "hwclock-set configurato"
  else
    skip "hwclock-set già configurato"
  fi
else
  skip "hwclock-set non trovato (OK su sistemi recenti)"
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}Setup completato!${NC}"
echo "  Riavvia il Pi per attivare il driver:"
echo "  sudo reboot"
echo ""
echo "  Dopo il reboot, verifica con:"
echo "  sudo hwclock -r"
echo "========================================"
```

- [ ] **Step 2: Rendi eseguibile e verifica sintassi**

```bash
chmod +x scripts/setup-rtc.sh
bash -n scripts/setup-rtc.sh
```
Expected: nessun output (nessun errore di sintassi)

- [ ] **Step 3: Commit**

```bash
git add scripts/setup-rtc.sh
git commit -m "feat: add setup-rtc.sh — configure I2C RTC driver (YAY-153)"
```

---

## Task 2: API endpoint GET /api/config/rtc/status

**Files:**
- Modify: `routers/config_router.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Scrivi il test che fallisce**

In `tests/test_api.py`, aggiungi alla fine del file:

```python
@pytest.mark.asyncio
async def test_rtc_status_not_configured(mock_client):
    from main import app
    from unittest.mock import patch, mock_open
    fake_config = "# Raspberry Pi config\ndtparam=audio=on\n"
    with patch('builtins.open', mock_open(read_data=fake_config)), \
         patch('os.path.exists', return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/config/rtc/status')
    assert r.status_code == 200
    data = r.json()
    assert data['configured'] is False
    assert data['model'] is None
    assert data['device'] is None
    assert data['time'] is None


@pytest.mark.asyncio
async def test_rtc_status_configured_no_device(mock_client):
    from main import app
    from unittest.mock import patch, mock_open
    fake_config = "dtparam=audio=on\ndtoverlay=i2c-rtc,ds3231\n"
    with patch('builtins.open', mock_open(read_data=fake_config)), \
         patch('os.path.exists', return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/config/rtc/status')
    assert r.status_code == 200
    data = r.json()
    assert data['configured'] is True
    assert data['model'] == 'ds3231'
    assert data['device'] is None
    assert data['time'] is None


@pytest.mark.asyncio
async def test_rtc_status_configured_with_device(mock_client):
    from main import app
    from unittest.mock import patch, mock_open
    fake_config = "dtoverlay=i2c-rtc,ds3231\n"
    fake_hwclock = type('R', (), {
        'stdout': '2026-03-31 21:00:00.000000+0000',
        'returncode': 0
    })()
    with patch('builtins.open', mock_open(read_data=fake_config)), \
         patch('os.path.exists', return_value=True), \
         patch('subprocess.run', return_value=fake_hwclock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            r = await ac.get('/api/config/rtc/status')
    assert r.status_code == 200
    data = r.json()
    assert data['configured'] is True
    assert data['model'] == 'ds3231'
    assert data['device'] == '/dev/rtc0'
    assert '2026-03-31' in data['time']
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
python3 -m pytest tests/test_api.py::test_rtc_status_not_configured tests/test_api.py::test_rtc_status_configured_no_device tests/test_api.py::test_rtc_status_configured_with_device -v
```
Expected: FAILED (endpoint non esiste ancora)

- [ ] **Step 3: Aggiungi l'endpoint in `routers/config_router.py`**

Aggiungi in fondo al file (prima dell'ultima riga se presente, o dopo `wifi_connect`):

```python
@router.get('/api/config/rtc/status')
async def rtc_status():
    import os
    CONFIG_PATH = '/boot/firmware/config.txt'
    configured = False
    model = None
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith('dtoverlay=i2c-rtc'):
                    configured = True
                    # dtoverlay=i2c-rtc,ds3231
                    parts = line.split(',')
                    if len(parts) >= 2:
                        model = parts[1]
                    break
    except FileNotFoundError:
        pass

    device = '/dev/rtc0' if os.path.exists('/dev/rtc0') else None

    time_str = None
    if device:
        try:
            result = subprocess.run(
                ['hwclock', '-r', '--rtc=/dev/rtc0'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                time_str = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return {
        'configured': configured,
        'model': model,
        'device': device,
        'time': time_str,
    }
```

- [ ] **Step 4: Verifica che i test passino**

```bash
python3 -m pytest tests/test_api.py::test_rtc_status_not_configured tests/test_api.py::test_rtc_status_configured_no_device tests/test_api.py::test_rtc_status_configured_with_device -v
```
Expected: 3 PASSED

- [ ] **Step 5: Verifica che tutti i test passino ancora**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: tutti PASSED

- [ ] **Step 6: Commit**

```bash
git add routers/config_router.py tests/test_api.py
git commit -m "feat: add GET /api/config/rtc/status endpoint (YAY-153)"
```

---

## Task 3: UI — sezione RTC in config.html

**Files:**
- Modify: `templates/config.html`

- [ ] **Step 1: Aggiungi "RTC" alla sidebar sections**

Trova nel `<script>` la riga:
```javascript
      { id: 'wifi',     label: 'WiFi' },
```
Sostituisci con:
```javascript
      { id: 'wifi',     label: 'WiFi' },
      { id: 'rtc',      label: 'RTC' },
```

- [ ] **Step 2: Aggiungi la sezione RTC nel template HTML**

Trova `<!-- WIFI -->` e subito prima di `</div><!-- /CONTENT -->` (che segue la sezione WiFi), aggiungi dopo la chiusura della sezione WiFi (`</template>` di wifi):

```html
    <!-- RTC -->
    <template x-if="section === 'rtc'">
      <div>
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:10px;">RTC I2C</div>

        <!-- Stato -->
        <div style="padding:10px;background:var(--panel);border:1px solid var(--border);border-radius:6px;margin-bottom:12px;">
          <template x-if="rtcStatus === null">
            <span style="font-size:11px;color:var(--muted);">Caricamento...</span>
          </template>
          <template x-if="rtcStatus !== null && rtcStatus.configured">
            <div>
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                <div style="width:8px;height:8px;border-radius:50%;background:#4caf50;flex-shrink:0;"></div>
                <span style="font-size:11px;color:var(--text);font-weight:600;">Attivo</span>
                <span style="font-size:10px;color:var(--muted);" x-text="rtcStatus.model ? '· ' + rtcStatus.model.toUpperCase() : ''"></span>
              </div>
              <div x-show="rtcStatus.device" style="font-size:10px;color:var(--muted);" x-text="rtcStatus.device + (rtcStatus.time ? ' · ' + rtcStatus.time : '')"></div>
              <div x-show="!rtcStatus.device" style="font-size:10px;color:#e5a50a;">Driver configurato — riavvia il Pi per attivare.</div>
            </div>
          </template>
          <template x-if="rtcStatus !== null && !rtcStatus.configured">
            <div style="display:flex;align-items:center;gap:6px;">
              <div style="width:8px;height:8px;border-radius:50%;background:#374151;flex-shrink:0;"></div>
              <span style="font-size:11px;color:var(--muted);">Non configurato</span>
            </div>
          </template>
        </div>

        <!-- Selettore modello + comando setup -->
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">Modello RTC</div>
        <select x-model="rtcModel"
                style="width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;margin-bottom:10px;">
          <option value="ds3231">DS3231 (consigliato)</option>
          <option value="ds1307">DS1307</option>
          <option value="pcf8523">PCF8523</option>
          <option value="pcf8563">PCF8563</option>
          <option value="rv3028">RV3028</option>
          <option value="mcp7940x">MCP7940X</option>
          <option value="abx80x">ABx80x</option>
        </select>

        <div style="font-size:10px;color:var(--muted);margin-bottom:4px;">Comando di setup (copia e incolla nel terminale)</div>
        <div style="display:flex;align-items:center;gap:6px;">
          <code style="flex:1;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:4px;font-size:10px;color:var(--accent);word-break:break-all;"
                x-text="'sudo bash ~/pi-Mesh/scripts/setup-rtc.sh ' + rtcModel"></code>
          <button @click="copyRtcCmd()"
                  style="padding:7px 10px;background:#1a3a5c;color:var(--accent);border:1px solid #2a5a8a;border-radius:4px;font-size:11px;cursor:pointer;white-space:nowrap;"
                  x-text="rtcCopied ? '✓' : 'Copia'"></button>
        </div>
        <p style="font-size:10px;color:var(--muted);margin-top:8px;">Richiede root. Riavvia il Pi dopo l'esecuzione.</p>
      </div>
    </template>
```

- [ ] **Step 3: Aggiungi proprietà e metodi RTC al component Alpine.js**

Nel `<script>`, trova `// WiFi` e prima di esso aggiungi:

```javascript
    // RTC
    rtcStatus: null,
    rtcModel: 'ds3231',
    rtcCopied: false,

    async loadRtc() {
      const r = await fetch('/api/config/rtc/status')
      if (r.ok) this.rtcStatus = await r.json()
    },

    copyRtcCmd() {
      const cmd = 'sudo bash ~/pi-Mesh/scripts/setup-rtc.sh ' + this.rtcModel
      navigator.clipboard.writeText(cmd).then(() => {
        this.rtcCopied = true
        setTimeout(() => { this.rtcCopied = false }, 2000)
      })
    },
```

- [ ] **Step 4: Aggiorna selectSection per caricare RTC**

Trova nel `<script>`:
```javascript
      if (s === 'gpio')                                   await this.loadGpio()
```
Sostituisci con:
```javascript
      if (s === 'gpio')                                   await this.loadGpio()
      if (s === 'rtc')                                    await this.loadRtc()
```

- [ ] **Step 5: Verifica tutti i test**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: tutti PASSED (nessun test HTML da eseguire)

- [ ] **Step 6: Commit**

```bash
git add templates/config.html
git commit -m "feat: config.html RTC section — status + setup command (YAY-153)"
```

---

## Task 4: Deploy e chiudi su Linear

- [ ] **Step 1: Push e deploy sul Pi**

```bash
git push && sshpass -p 'pimesh' ssh pimesh@192.168.1.36 'cd ~/pi-Mesh && git pull && sudo systemctl restart pimesh'
```

- [ ] **Step 2: Verifica che il servizio sia attivo**

```bash
sshpass -p 'pimesh' ssh pimesh@192.168.1.36 'systemctl is-active pimesh.service'
```
Expected: `active`

- [ ] **Step 3: Marca YAY-153 come Done su Linear**
