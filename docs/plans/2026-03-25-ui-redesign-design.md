# UI Redesign — Design Document
**Data:** 2026-03-25
**Approccio:** Refactor completo (Approccio A)
**Display target:** 320×480 portrait (default), 480×320 landscape (selezionabile)
**Stack:** Flask + Jinja2 + vanilla JS + CSS custom properties + WebSocket
**Principi CSS:** tiny-css (zero framework, system-ui, logical properties), MDI SVG sprite inline

---

## 1. Chrome & Layout

### Struttura verticale portrait
```
STATUS BAR   20 / 24 / 32px  (density: compact / icons / full)
CONTENT      412 / 408 / 400px
TAB BAR      48px
```

### Struttura landscape (480×320)
```
STATUS BAR   20 / 24 / 32px
CONTENT      252 / 248 / 240px
TAB BAR      48px
```

### Orientamento
- Default: portrait
- Selezionabile in Settings → `screen_orientation`: `portrait` | `landscape`
- JS applica classe `.orient-landscape` su `<body>` al cambio + salva in config
- CSS `@media (orientation: landscape)` + override `.orient-landscape` per forzare da settings

---

## 2. Status Bar

### Density mode (`status_bar_density`)

| Valore | Altezza | Contenuto |
|--------|---------|-----------|
| `compact` | 20px | 5 dot colorati (●) senza icona |
| `icons` | 24px | 5 icone MDI colorate, no testo |
| `full` | 32px | 5 icone MDI + valore testuale |

### 5 Indicatori

| # | Indicatore | Icona MDI | Verde | Giallo | Rosso |
|---|------------|-----------|-------|--------|-------|
| 1 | Meshtastic | `router` | connesso | connecting | disconnesso |
| 2 | USB Serial | `usb` | porta aperta | — | errore/assente |
| 3 | GPS | `gps_fixed` | fix 3D | fix 2D | no fix |
| 4 | Batteria | `battery_5_bar` + `bolt` se carica | >50% | 20–50% | <20% |
| 5 | TX/RX | `sync_alt` | idle | TX attivo | RX attivo |

In `full`: batteria mostra `87%`, GPS mostra `8sat`, Meshtastic mostra `3nodi`.

### CSS variables colori stato
```css
--ok:     #4caf50   /* verde */
--warn:   #ff9800   /* giallo */
--danger: #f44336   /* rosso */
--muted:  #888      /* grigio idle */
```

---

## 3. Tab Bar

6 tab fisse, 53px larghezza ciascuna (320px / 6). Icona MDI 20px + label 10px.

| Tab | Icona MDI | Label | Route |
|-----|-----------|-------|-------|
| Home | `home` | Home | `/` |
| Canali | `forum` | Chat | `/channels` |
| Mappa | `map` | Mappa | `/map` |
| Hardware | `memory` | HW | `/hardware` |
| Impostazioni | `settings` | Set | `/settings` |
| Remote | `cloud_sync` | RMT | `/remote` |

Tab attiva: `color: var(--accent)`. Inattiva: `color: var(--muted)`.
Navigazione SPA invariata: fetch + innerHTML swap + `reexecScripts`.

### Encoder 1 (navigazione tab)
- CW → tab successiva
- CCW → tab precedente
- Long press → Home

---

## 4. Tab Home

Card verticali full-width, scroll verticale, padding 12px.

### Card Nodo Locale
- Nome nodo, ID hex, canale attivo
- SNR, RSSI, hop count, battery %
- Icone: `router`, `battery_5_bar`, `hub`
- Colori: battery <20% → `--danger`, <50% → `--warn`

### Card Raspberry Pi
- CPU%, RAM usata/totale, temperatura, uptime, spazio disco
- Icone: `memory`, `thermostat`, `schedule`, `storage`
- Soglie colore: CPU >80% → `--warn`, Temp >70°C → `--danger`
- Aggiornato via WebSocket handler `status`

### Mini Lista Nodi Recenti
- Ultimi 4 nodi con dot stato colorato, nome, SNR, tempo fa
- Verde = online (<15min), giallo = recente (15min–2h), grigio = offline

---

## 5. Tab Canali

### Layout selezionabile (`channel_layout`)

**`list`** (default): lista canali/conversazioni → tap → chat in-place con back (←)
**`tabs`**: due pill-tab interne `Canali | Privati` → chat sotto
**`unified`**: lista unica con badge 📢/👤 per distinguere tipo

### Vista Lista
```
[Tutti i canali]
  📢 CH 0 · LongFast   3●
  📢 CH 1 · Private    1●
[Conversazioni]
  👤 NodoA      12:34  2↩
  👤 NodoB      ieri
```

### Vista Chat (in-place)
- Header: `←` back + nome canale/nodo + badge nodi attivi
- Bubble chat: outgoing destra (accent), incoming sinistra (bg2)
- Meta sotto bubble: SNR, timestamp
- `↩` = ACK ricevuto, `▶` = in attesa ACK
- Form invio: select canale + input testo + button invio
- Scroll infinito verso il passato (già implementato)
- Back via tap `←` o encoder 2 long_press

---

## 6. Tab Mappa

Leaflet full-screen nel content area. Overlay compatti sovrapposti.

### Layer switcher (overlay top-right)
3 pulsanti pill: `OSM` | `SAT` | `TOPO`
Tutti serviti da **tile cache locale** (pre-scaricata via Settings).
Tile provider: OSM, ESRI World Imagery, OpenTopoMap.

### Marker nodi
| Colore | Stato |
|--------|-------|
| Verde `--ok` | Online (<15min) |
| Giallo `--warn` | Recente (15min–2h) |
| Grigio `--muted` | Offline (>2h) |
| Cerchio pieno | Nodo locale (GPS) |

Tap marker → popup: nome, SNR, battery, ultima posizione, pulsante "Traceroute".

### Traceroute
- Linea tratteggiata `--accent` tra hop del percorso
- Attivato da popup marker → mostra path completo

### Overlay bottom
- `[↺ centra]` → centra su posizione locale
- `[≡ nodi]` → drawer laterale lista nodi + distanze

### Encoder 2
- CW → zoom in, CCW → zoom out (invariato)

### Tile Cache (gestita da Settings)
- Download area corrente a zoom 8–16
- Progress bar durante download
- Mostra dimensione cache, pulsante elimina

---

## 7. Tab Hardware

3 sezioni scrollabili verticalmente.

### GPIO Grid
- Celle 28×28px, font 9px, numero pin BCM
- Colori: `--muted`=non configurato, `--ok`=HIGH, `var(--border)`=LOW, `--accent`=PWM, `--danger`=errore
- Tap pin → mini popup: funzione, valore, direzione IN/OUT

### Sensori I2C
- Lista: indirizzo hex + tipo + ultimi valori
- Colori stato: ok → `--ok`, timeout/errore → `--danger`
- `[↺]` re-scan bus I2C

### Encoder
- Posizione corrente encoder 1 e 2
- Pulsanti test CW/CCW per verifica fisica

---

## 8. Tab Settings

Sezioni con label uppercase 11px `--muted`, righe 44px touch target, scroll verticale.

### Sezioni e parametri

**DISPLAY**
- `theme`: Dark / Light / HC
- `screen_orientation`: Portrait / Landscape
- `status_bar_density`: Compatta / Icone / Completa

**INTERFACCIA**
- `channel_layout`: Lista / Tab / Unificata
- `lingua`: IT / EN

**CONNESSIONE**
- `usb_port`: select porta `/dev/tty*`
- `baud_rate`: 115200 / 9600 / ...
- Button: Test connessione

**MESHTASTIC**
- Nome nodo, canale 0 preset, regione RF (EU_868, ecc.)

**MAPPA**
- Info dimensione cache tile
- Button: Scarica area corrente
- Button: Elimina cache

**SISTEMA**
- Versione + Button aggiorna
- Button: Riavvia servizio

---

## 9. Tab Remote

### Vista selezione nodo
Lista nodi raggiungibili con stato, SNR, hop count.
Tap → vista dettaglio nodo (in-place, back con `←`).

### Vista dettaglio nodo

**STATO**: SNR, battery, hop, GPS, ultimo contatto

**COMANDI RAPIDI**
- `[Reboot]` `[Mute]` `[Ping]`
- Confirm dialog prima di azioni destructive

**CONFIGURAZIONE**
- Nome nodo, canale, TX power, GPS on/off
- `[Applica modifiche]` → invia via Meshtastic admin channel (cifrato)
- Confirm dialog obbligatorio prima dell'invio

**TELEMETRIA REMOTA**
- Temperatura, uptime (request-on-demand, no polling)
- `[Richiedi aggiornamento]`

### Vincoli
- Nodi offline → comandi disabilitati (`opacity: 0.5`, `cursor: not-allowed`)
- Tutti i comandi via admin channel Meshtastic

---

## 10. CSS Architecture (tiny-css principles)

```css
/* Base minimale */
:root {
  color-scheme: light dark;
  font-family: system-ui;
  accent-color: var(--accent);
}

/* Nessun reset aggressivo — browser defaults OK */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* SVG eredita colore testo */
:where(svg) { fill: currentColor; }

/* Responsive embeds */
:where(img, svg, video, iframe) { max-inline-size: 100%; block-size: auto; }

/* Cursore interattivo */
:where(button, select, label) { cursor: pointer; }

/* High contrast mode */
@media (forced-colors: active) {
  :where(button) { border: 1px solid; }
}
```

MDI: SVG sprite inline in `base.html` — offline-safe, nessun CDN.
Grid: 4px base unit per tutti i spacing.
Logical properties per padding/margin dove applicabile.

---

## 11. Impostazioni — Persistenza

Tutte le preferenze UI salvate nel config del backend (già presente).
Al caricamento pagina: init via WebSocket `handleInit` → applica tema, density, orientamento.
JS legge `data-*` attributes su `<body>` per applicare le classi corrette.

```html
<body class="theme-dark" data-density="icons" data-orientation="portrait" data-channel-layout="list">
```

---

## 12. Encoder 2 — Mapping per tab

| Tab | CW | CCW | Press | Long Press |
|-----|----|-----|-------|------------|
| Home | scroll giù | scroll su | — | — |
| Chat (lista) | naviga giù | naviga su | apri chat | — |
| Chat (chat) | scroll giù | scroll su | — | back |
| Mappa | zoom in | zoom out | — | — |
| Hardware | scroll giù | scroll su | — | — |
| Settings | scroll giù | scroll su | — | — |
| Remote (lista) | naviga giù | naviga su | apri nodo | — |
| Remote (nodo) | scroll giù | scroll su | — | back |
