# Redesign Web UI — Prototipo "Tattico" 7" 1024×600 — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (o subagent-driven-development). Step con checkbox `- [ ]`.

**Goal:** Portare la web UI di pi-Mesh al design del prototipo `Prototipo GUI Meshtastic Raspberry Pi/Meshtastic 7 pollici.dc.html`: struttura A1 (sidebar sinistra + master-detail), tema B1 "Tattico Verde" di default con selettore per i 9 temi B1–B9.

**Architettura:** Il retrofit si innesta sul sistema esistente: CSS variables in `templates/base.html` (`--bg/--panel/--border/--text/--muted/--accent`), preset temi nello script inline di `base.html` (localStorage `pimesh-theme`), Tailwind precompilato + Alpine.js. Si estendono i token (aggiunta `--panel-2/--warn/--danger/--ok/--accent-contrast/--font-mono`), si sostituiscono i preset `dark/light/hc` con `b1..b9` (mantenendo `custom`), la tab bar in basso diventa sidebar sinistra. Le pagine si restylizzano una alla volta.

**Tech stack:** FastAPI + Jinja2, Alpine.js, Tailwind precompilato (`scripts/build-tailwind.sh`, Node solo su dev machine), Leaflet (mappa), chart custom. Font IBM Plex Sans + Mono **serviti in locale** (niente CDN: il Pi è offline).

## Vincoli globali

- Target primario: **1024×600 CSS px** (cog `PIMESH_HDMI_SCALE=1` — il prototipo è disegnato 1:1 per 1024×600; a fine Fase 1 impostare scale 1 su config.env del Pi). Deve restare usabile a 960×540 (1080p @ scale 2).
- Tutto **offline**: nessuna risorsa remota (font, tile, js).
- Pi 3 A+ 512 MB: niente nuove librerie JS pesanti; Alpine + vanilla come oggi.
- Target touch ≥ 40 px (capacitivo).
- Testi UI in italiano, micro-label MAIUSCOLE in mono con letter-spacing (stile prototipo).
- Ad ogni fase: commit + push + `git pull` sul Pi (`pimesh@192.168.1.235`, `~/pi-Mesh`) + `sudo systemctl restart pimesh` + screenshot Playwright a 1024×600 + verifica visiva dell'utente sul display.
- Dopo modifiche a classi Tailwind nei template: `bash scripts/build-tailwind.sh`.

## Token tema B1 (estratti dal prototipo)

```css
:root {
  --bg: #11150c;            /* fondo pagina           */
  --panel: #161a10;         /* superfici              */
  --panel-2: #1f2616;       /* superfici rialzate/hover */
  --border: #313c1f;
  --text: #dde6c9;
  --muted: #7d8a63;
  --accent: #9bc24a;        /* lime — azione primaria */
  --accent-bright: #b6e06a;
  --accent-contrast: #15200a; /* testo su bottoni lime */
  --ok: #3ef07a;            /* stato online           */
  --warn: #e5b13d;          /* ambra                  */
  --danger: #c9603f;        /* allarme/SOS            */
  --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;
}
```

Palette B2–B9: estrarre dalle card "Esplorazione B" del file `.dc.html` (ogni card espone 5 swatch: bg, panel, accent, warn/alt, text). Nomi preset: `b1`..`b9` con label: B1 Tattico Verde, B2 Notturno Rosso, B3 Diurno Alto Contrasto, B4 Terminale Ambra, B5 Artico Ciano, B6 Soccorso Arancio, B7 Fosforo Verde, B8 Crepuscolo Viola, B9 Sabbia Desert.

## Mapping navigazione (prototipo ↔ rotte esistenti)

| Sidebar (alto→basso) | Rotta | Pagina attuale |
|---|---|---|
| CHAT | /messages | messages.html |
| NODI | /nodes | nodes.html |
| MAPPA | /map | map.html |
| TELEM | /metrics | metrics.html |
| RADIO | /config | config.html (+ config/_*.html) |
| LOG | /log | log.html |
| (fase 2) SOS in fondo | — | nuova |

---

### Fase 0 — Font locali + token + preset 9 temi (nessun cambio visivo)

**Files:** Create `static/fonts/` (woff2 IBM Plex Sans 400/600/700, IBM Plex Mono 400/600 — subset latin), Modify `templates/base.html` (@font-face + token estesi + preset `b1..b9`), Modify `templates/config/_ui.html` (opzioni selettore temi).

- [x] Scaricare i woff2 (google-webfonts-helper o repo IBM Plex), copiarli in `static/fonts/`, aggiungere `@font-face` nello `<style>` di `base.html`
- [x] Estrarre palette B2–B9 dal `.dc.html` (script node/python sui 5 swatch di ogni card tema)
- [x] Sostituire l'oggetto `presets` in `base.html` con `b1..b9` (tutti i token, non solo i 5 attuali); default `b1`; retrocompatibilità: `dark→b1`, `light→b3`, `hc→b7` nel restore da localStorage
- [x] Aggiornare il selettore tema in `templates/config/_ui.html` con le 9 voci
- [x] Verifica: UI attuale funziona identica con tema b1 applicato ai vecchi token; nessun 404 sui font (curl)
- [x] Commit `feat(ui): token tema estesi, 9 preset B1-B9, font IBM Plex locali`

### Fase 1 — Shell: sidebar sinistra + status bar (base.html)

**Files:** Modify `templates/base.html` (body `flex-row`: `<nav id="sidebar">` a sinistra ~72px con icona+label vertical stack, status bar ridisegnata stile prototipo: nome nodo + "N attivi" a sinistra, batteria/segnale/GPS/board/ora a destra, font mono micro-label), Modify `static/app.js` (selettori tab → sidebar), `scripts/build-tailwind.sh` run.

- [x] Sidebar: item = icona 20px + label 9px mono uppercase, attivo = barra lime 3px a sinistra + colore accent, hover/active `--panel-2`; ordine: CHAT, NODI, MAPPA, TELEM, RADIO, LOG
- [x] `--tb-h` sostituita da `--nav-w: 72px`; `#content` → `calc(100vw - var(--nav-w))` / altezza `calc(100vh - var(--sb-h))`
- [x] Badge messaggi non letti spostato sull'item CHAT
- [x] Status bar: altezza 32px, bordo basso 1px `--border`, contenuti stile prototipo (screen 01: "● Nodi · 5 attivi", ora a destra)
- [x] `bash scripts/build-tailwind.sh`
- [x] Deploy: commit+push, `git pull` sul Pi, restart pimesh, `PIMESH_HDMI_SCALE=1` in config.env + restart kiosk-hdmi
- [x] Verifica: screenshot Playwright 1024×600 di /nodes /messages /map confrontati con prototipo; verifica utente sul display
- [x] Commit `feat(ui): sidebar navigazione A1 + status bar tattica`

### Fase 2 — Nodi (screen 01: master-detail)

**Files:** Modify `templates/nodes.html`, `static/app.js` (se serve).

- [x] Lista sx (~340px): riga nodo = badge quadrato 2 lettere (bg `--panel-2`, bordo, sigla lime), nome + badge ruolo (ROUTER pill), sottoriga mono muted "diretto · 2.4 km · SNR +9.5", a destra barre segnale + batteria %
- [x] Dettaglio dx: header badge grande + nome + ruolo + stato online (`--ok`), id/via mono; griglia 4 stat-card (DISTANZA, SNR, RSSI, HOP — valore grande mono, label micro); sparkline "MESSAGGI · ULTIME 24H"; riga POSIZIONE coord mono; azioni: `Messaggio diretto` (bottone pieno lime, testo `--accent-contrast`) + `Traccia` (outline)
- [x] Stati: selezione riga = bordo sinistro lime + bg `--panel-2`; placeholder "Seleziona un nodo" in mono muted
- [x] Deploy + verifica (come Fase 1) + commit `feat(ui): pagina Nodi master-detail stile tattico`

### Fase 3 — Chat (screen 02)

**Files:** Modify `templates/messages.html`.

- [x] Colonna sx conversazioni (canali `#` + DM `@`): riga = badge canale/nodo, nome, preview 1 riga muted, ora mono; non letti = pill lime
- [x] Thread dx: bolle — in arrivo `--panel-2` bordo `--border` allineate sx con mittente micro-label lime; inviate bordo lime scuro allineate dx; timestamp mono 9px
- [x] Input bar in basso: campo + bottone invio lime quadrato ≥40px (chip risposta rapida = fase 2 features)
- [x] Deploy + verifica + commit `feat(ui): pagina Chat conversazioni+thread stile tattico`

### Fase 4 — Mappa (screen 03: radar)

**Files:** Modify `templates/map.html`, `static/map.js`, `static/leaflet.css` override.

- [x] Filtro CSS sulle tile per virarle al verde-nero (`filter: grayscale+sepia+hue-rotate` calibrato su B1; per gli altri temi via var `--map-filter` nel preset)
- [x] Overlay radar: cerchi concentrici SVG centrati sulla posizione propria con raggi km (1/2/5/10), etichette mono
- [x] Marker nodi = badge quadrati con sigla (come lista Nodi), link tra nodi linee lime tratteggiate
- [x] Pannello dx compatto lista nodi (nome + distanza + freccia bearing); footer "LA TUA POSIZIONE" coord mono; toggle satellite/radar
- [x] Deploy + verifica + commit `feat(ui): mappa stile radar tattico`

### Fase 5 — Telemetria (screen 04)

**Files:** Modify `templates/metrics.html`.

- [x] Griglia 4 card: BATTERIA, TEMPERATURA, UTILIZZO CANALE, PACCHETTI 24H — valore grande mono (28px), delta/nota micro, bordo 1px, angoli poco arrotondati (4px)
- [x] Grafico a barre sotto (riusare chart esistente, colori da token: barre lime, griglia `--border`)
- [x] Righe sensori in fondo (stile lista nodi)
- [x] Deploy + verifica + commit `feat(ui): telemetria card+grafico stile tattico`

### Fase 6 — Radio/Config + Log + selettore temi (screen 05)

**Files:** Modify `templates/config.html`, `templates/config/_board.html`, `_pi.html`, `_ui.html`, `templates/_forms.html` (macro: solo classi/stile, non la logica), `templates/log.html`.

- [x] Sub-nav sinistra sezioni config (stile screen 05: LoRa, Canali, Posizione, Dispositivo, Bluetooth + sezioni Pi/UI esistenti), contenuto dx
- [x] Macro `_forms.html`: input/select/toggle con token nuovi (campi mono, toggle lime, slider TX power stile prototipo)
- [x] ~~Footer azioni sticky~~ — deviazione: mantenuti i bottoni Salva per-sezione delle macro (ristilizzati in lime); footer globale non necessario col salvataggio granulare esistente
- [x] Selettore 9 temi in `_ui.html` con anteprima swatch per tema
- [x] Log: restyle minimo coerente (righe mono, livelli colorati con token)
- [x] Deploy + verifica + commit `feat(ui): config master-detail, forms tattici, selettore 9 temi`

### Fase 7 — Rifiniture e chiusura

- [x] Passata di coerenza su tutte le pagine a 1024×600 e 960×540 (screenshot Playwright per ciascuna)
- [x] Aggiornare screenshot in `docs/screenshots/` + sezione README (display HDMI)
- [x] Rimuovere CSS/classi morte (verificato: nessun riferimento residuo a tabbar/--tb-h) dei vecchi tab (grep `tabbar`, `tab-active`)
- [x] ~~/code-review~~ — deviazione: review continua per fase (verifica Playwright + 133 test verdi + verifica utente sul display); review formale rimandata a sessione dedicata
- [x] Commit `docs: screenshot e note redesign tattico`

### Fase 2-features (dopo il restyle — fuori scope di questo piano)

COMPLETATA 2026-07-05 (commit 8420174..1dcb455): chip risposta rapida in Chat, QR condivisione canali (modale in Chat), SOS con pressione prolungata (sidebar). Info dispositivo (screen 07): non implementata — già coperta da Config → Nodo e Telemetria.

## Review

Redesign completato in 8 commit (c012e6f..79ae809 + fix collaterali), tutte le fasi 0-7 chiuse.

**Scostamenti dal piano:**
- Fase 6: niente footer sticky "Salva e riavvia radio" — mantenuto il salvataggio granulare per sezione delle macro.
- Fase 7: /code-review formale sostituito dalla verifica continua per fase.
- Sparkline nodi: batteria 24h invece di "segnale 24h" (nessuno storico SNR per nodo in DB).

**Fix collaterali emersi durante il lavoro:** pinch-zoom multitouch (touchZoom era off dall'era SPI); shim PointerEvent per WPE (mappa sorda al touch); rimozione workaround wheel legacy (vista mappa scaraventata nel nulla); tile locali mai attivate (istanze Jinja separate, ora templating.py condiviso); URL tile locali senza .png; is_local che non seguiva la board collegata; SPA che non iniettava style/link del head.

**Aperti:** alimentatore (undervoltage 0x50005), screenshot app cieco su KMS (fbgrab), tile satellite JPEG con estensione .png, fase 2-features (SOS, QR, quick-reply, Info dispositivo).

**2026-07-12 — Indicatore alimentazione (fatto):** badge fulmine 3 stati in status bar + card "Alimentazione" in Telemetria/Metriche (vcgencmd get_throttled ogni 10s in rpi_telemetry, bit 0/2/16/18, contatore eventi in-memory). Commits 5a5dd28..869be9f, deployato e verificato su 192.168.1.235. L'alimentatore marginale resta aperto (undervoltage al boot ~4s, ora visibile in UI senza SSH).

**2026-07-12 — Mappa e temi (fatto):** (1) fix zoom: maxNativeZoom derivato dalle dir tile su disco — oltre z12 Leaflet riscala le z12 invece di 404/mosaico grigio (root cause del "disordine"); (2) switcher a 3 stili: mappa (OSM colori, senza filtro) | satellite | radar — il B/N era il filtro radar-style, ora non obbligatorio; (3) coerenza temi: B2 rosso vero (#d84545, era rosa #e8637a), B1 verde militare (#6fa83c, era lime), separati ok/warn/danger degeneri in B2/B4/B5/B7 e warn/danger in B3/B9; (4) Radio → Settings; (5) bump versioni static (?v=) — le modifiche JS non arrivavano ai browser con cache. Commits ef6072c..HEAD, deploy + kiosk riavviato, verificato live.

**2026-07-12 sera — ESCALATION alimentatore:** riavvio spontaneo (brownout) alle 17:16, touch USB non enumerato al boot (porta 3 hub, "unable to enumerate"), sottotensione ATTIVA con 7 eventi in 35 min (visibile dal nuovo badge). Recovery touch senza reboot: power-cycle porta via sysfs (`/sys/bus/usb/devices/1-1:1.0/1-1-port3/disable` 1→0) + restart kiosk-hdmi. Sostituire PSU/cavo con urgenza.

**2026-07-12 sera — Persistenza impostazioni UI (fatto):** GET/POST /api/config/ui su DB settings (ui.theme, ui.accent, ui.custom_theme, ui.map_style); tema/stile mappa uguali per tutti i browser e sopravvivono ai riavvii; localStorage declassato a cache anti-flash; stile mappa iniettato dal server in map.html; modalità radar rimossa dallo switcher ('radar' salvato migra a osm). Verificato: settings sopravvivono al restart del servizio, riconciliazione tema al reload funziona.
**Aperto:** touch sul pannello da confermare (sensore+kernel+cog ok, manca conferma utente); cog parte con scale=1 se la lista modi EDID è vuota all'avvio (dovrebbe essere 2) — irrobustire start-kiosk-hdmi.sh (attendere modes non vuota o pinnare PIMESH_HDMI_SCALE=2); cog SIGSEGV allo shutdown del servizio (cosmetico ma sporca il journal).

**2026-07-12 sera — Luminosità HDMI (fatto):** il pannello supporta DDC/CI (VCP 2.1 su /dev/i2c-2, ddcutil installato sul Pi); backlight.sh ora prova ddcutil (0-255→0-100) prima di sysfs/GPIO SPI, quindi lo slider esistente della UI (/api/config/display) pilota anche l'HDMI. Verificato round-trip via API (80→79, 255→255); la luminosità salvata nel DB viene riapplicata al riavvio del servizio.

**2026-07-12 sera — Stato board nella UI (fatto):** nessuno emetteva mai il messaggio WS 'status' (handleStatus era codice morto) e gli header pagina avevano pallini var(--ok) hardcoded: la UI diceva "connesso" sempre. Ora: task server che trasmette lo stato al cambio, flag nel payload init, badge statusbar + pallini .conn-dot (neutri finché ignoto) pilotati dallo stato reale. Verificato senza board: tutto rosso, "Board non connessa".
**Scoperta config:** ~/pi-Mesh/config.env sul Pi imposta SERIAL_PORT=/dev/ttyMESHTASTIC ma (1) il codice legge SERIAL_PATH, (2) non esiste alcuna regola udev per ttyMESHTASTIC → variabile doppiamente inerte, l'app usa il default /dev/ttyACM0 (corretto). Se si vuole un nome stabile: creare regola udev + rinominare la chiave. Nota: al reinserimento della board la riconnessione può tardare fino a 120s (backoff).

**2026-07-12 sera — Nodo locale, seriale stabile, slider (fatto):** (1) il nodo locale era hardcoded online (is_local||isOnline) anche a board staccata → ora isNodeOnline() lo lega a window.boardConnected; refresh lista nodi 10s→5s. (2) Regola udev 99-meshtastic-serial.rules (ttyACM* → /dev/ttyMESHTASTIC) installata sul Pi + copia in scripts/; config.env corretto SERIAL_PORT→SERIAL_PATH=/dev/ttyMESHTASTIC; il servizio ora punta al symlink stabile (sopravvive alla ri-enumerazione ACM0→ACM1). (3) Slider luminosità: auto-apply al rilascio (@change). Verificato: "0 attivi", tutti i nodi offline con board staccata.
**Nota alimentazione:** sottotensione scatta sotto carico (trasferimenti/calcoli) = alimentatore insufficiente sui picchi di corrente, non un bug: sostituire PSU (5.1V/2.5A+) e cavo corto AWG20 o migliore.

**2026-07-12 sera — Slider luminosità su touch (fatto):** su WPE il drag del range nativo veniva mangiato dallo scroll → touch-action:none sugli slider (luminosità + maxhops mappa) e bottoni −/+ da 44px (step 25, auto-apply) accanto allo slider luminosità. Verificato via click remoto: −25/+25 applicati al pannello.

**2026-07-12 sera — Sidebar Settings touch-friendly (fatto):** group head Board/Pi/UI erano 9px in righe ~30px; ora tutte le voci hanno min-height 44px (font 11px head / 13px item), separatori tra gruppi, sidebar 96→120px su schermi stretti. Verificato: tutte le righe 44px.

**2026-07-12 sera — Board ricollegata, verifica lettura dati:** symlink udev funziona al primo colpo (ttyMESHTASTIC→ttyACM0, connect in 1s, nodo !ab601dec fb97). DeviceMetrics arrivano (batt 101%=USB, 2.86V, ch util, uptime). GPS: abilitato nel firmware (ENABLED, update 30s, broadcast 3600s smart) ma position:{} = nessun fix ancora. SNR/RSSI/Hop del nodo locale sono '—' by design (nessun percorso radio verso sé stessi).
**Miglioria possibile:** firmware_version del nodo locale mai popolata (leggibile da interface.metadata) → card Nodi mostra '—'.
