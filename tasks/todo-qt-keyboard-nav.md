# pi-Mesh — Navigazione mouse-free da tastiera QMK

## Contesto
Tastiera USB custom con firmware QMK/VIA. Obiettivo: rendere la GUI 100% azionabile senza mouse né touch. Il firmware manderà combinazioni "esotiche" (`Ctrl+Alt+Shift+<lettera>`) per evitare conflitti con OS, Qt nativi e altre app sul Pi. Tutta la logica di mapping resta lato GUI: il firmware è un trasduttore.

## Hardware target
Tastiera ~50 tasti stile **M5Stack CardKB** con firmware QMK custom.
- Layout: QWERTY 4x12 circa, con `Esc`, `Tab`, `Enter`, `Shift`, `Bksp`, `Space`, `Fn`.
- Niente `Ctrl` fisico dedicato.
- Frecce sotto layer Fn (Fn+IJKL o equivalente).
- Userà la stessa tastiera anche per **scrivere messaggi** → digitazione = primaria.

## Schema scorciatoie (contratto firmware ↔ GUI) — FINALE

**Principio**: scorciatoie **sempre con modifier o tasti rari**. Mentre digiti in un campo testo, `q` inserisce `q`, mai un comando. Zero ambiguità.

**Firmware QMK**: layer Fn manda `F13..F24` (tasti standard scancode-wise ma virtualmente inesistenti su tastiere normali → zero collisioni anche se in futuro colleghi una tastiera USB standard).

### Globali (sempre attive, contesto `ApplicationShortcut`)
| QMK manda     | Azione                                  |
|---------------|-----------------------------------------|
| `F13`..`F18`  | Pagine: Nodi / Mappa / Msg / Config / Metriche / Log |
| `F19`         | Telemetria (pagina nascosta)            |
| `F20`         | Screenshot                              |
| `F21`         | Rotation menu                           |
| `F22`         | Reboot (conferma)                       |
| `F23`         | Shutdown (conferma)                     |
| `F24`         | Toggle VKB on/off                       |
| `Esc`         | Chiudi dialog / overlay / blur focus    |
| `F1`          | Cheat-sheet overlay                     |
| `Tab` / `S-Tab` | Focus next/prev (gestito da Qt)       |

### Per-pagina (contesto `WidgetWithChildrenShortcut`, NON sparano se focus è in `QLineEdit`/`QTextEdit`)
- **Nodi**: `↑/↓` selezione lista, `Enter` apri dettaglio, `/` apri filtro.
- **Mappa**: `↑↓←→` pan, `+/-` zoom, `[`/`]` marker prev/next, `Enter` apri marker, `Home` torna su nodo locale.
- **Msg**:
  - Focus su lista canali: `↑/↓` cambia, `Enter` entra.
  - Focus su input: `Enter` invia, `Shift+Enter` newline, `Esc` blur (torna a lista).
  - Globale msg: `Ctrl+N` (= `F19` via Fn? oppure dedicato) nuovo DM. **Da decidere se serve davvero.**
- **Config**: `↑/↓` tra sezioni collassabili, `Space`/`Enter` espandi/collassa, `Tab` campo successivo.
- **Metriche**: `↑/↓` scroll, `1..5` range temporale (singolo digit, valido solo se focus su pagina, non su input).
- **Log**: `↑/↓` scroll, `End` ultima riga, `Home` prima riga.

## Architettura proposta
1. **Modulo centrale** `gui/shortcuts.py` con classe `ShortcutManager`:
   - registra `QShortcut` globali su `MainWindow` (cambio pagina, system actions, F1).
   - espone API `register_page_shortcuts(page_widget, mapping)` per scorciatoie contestuali (vincolate via `Qt.ShortcutContext.WidgetWithChildrenShortcut` così non sporcano altre pagine).
   - segnale `cheatsheet_requested` per F1.
2. **Focus management** — modifiche minimali e mirate:
   - `_TabButton` → `setFocusPolicy(Qt.StrongFocus)` + ordine tab espliciti in `TabBar`.
   - Ogni `Page` espone (opzionalmente) `set_initial_focus()` chiamato da `MainWindow._select_tab` dopo lo switch, così l'utente arriva sulla pagina con focus già piazzato sul widget giusto.
   - `setTabOrder` esplicito dentro ciascuna pagina (sidebar di Config, lista in Nodi, input in Msg).
3. **Focus ring visibile** in `gui/theme/qss.py`:
   - aggiungere regole `*:focus { outline: 2px solid <accent>; outline-offset: 1px; }` con colori dalla palette corrente.
   - testare contrasto sia in tema dark che eventuali altri.
4. **VKB interaction** — la tastiera virtuale ha già `NoFocus` (controllato). Aggiungere:
   - flag `PIMESH_GUI_NO_VKB=1` già esistente per dev; aggiungere shortcut runtime `C-A-S-K` che chiama `vkb_controller.toggle()` per quando si usa tastiera fisica.
5. **Mappa** — punto più tosto:
   - se `map_page.py` usa `QWebEngineView` (Leaflet/MapLibre), serve un JS-bridge: handler `keyPressEvent` su Python che inietta JS (`map.panBy`, `map.zoomIn`, marker focus). Da verificare leggendo `map_page.py`.
   - se è widget custom QPainter: `keyPressEvent` diretto + indice marker corrente.
6. **Cheat-sheet overlay** (F1):
   - widget semi-trasparente full-screen elencando le combo per la pagina corrente + globali. Dismiss con `Esc` o nuovo `F1`.
7. **Accessibilità collaterale** (low cost, alto valore):
   - `setAccessibleName` sui widget chiave (sidebar tab, input messaggio, lista nodi) per screen reader e per debug futuro.

## Piano di implementazione (a step incrementali)
- [ ] **Step 0 — Esplorazione**: leggere `map_page.py`, `messages_page.py`, `nodes_page.py`, `config_page.py` per capire la struttura widget di ciascuna pagina e dove ancorare i focus.
- [x] **Step 1 — Infrastruttura**: `gui/shortcuts.py` (`ShortcutManager`, debounce 500ms), `gui/main_window.py` (metodi pubblici + wire), `gui/widgets/vkb.py` (toggle persistente). Schema F1..F12 + Shift+F12 (F13..F24 droppati: keymap Qt linuxfb non li copre). Drop-in service `keyboard.conf` aggiunge `evdevkeyboard` ai generic plugins. Verifica live su Pi con `scripts/test_fkeys.py` (uinput): tutti i tasti firano una volta, eccetto F5 (lazy-build Config, idempotente).
- [x] **Step 2 — Focus globale**: `StrongFocus` + accessibleName su `_TabButton`. Hook `set_initial_focus()` in `_select_tab`. QSS focus indicators come `border: 1px solid {accent}` (Qt outline inaffidabile su QListView/QToolButton).
- [ ] **Step 3 — Pagina per pagina** (una alla volta, verifica live dopo ognuna):
  - [x] 3a. Nodi: focus su list (non search), setTabOrder esplicito, ring visibile. Note: selection highlight da rifinire (QLabel item widget).
  - [x] 3b. Msg: `_BroadcastView.set_initial_focus()` → input. `_DmView.set_initial_focus()` distingue threads-list vs conversation. `Page` delega allo `_stack.currentWidget()`. Verifica: F4 → focus su input, Enter invia (default), Shift+F12 nasconde VKB.
  - [x] 3c. Config: `CollapsibleSection._toggle` StrongFocus + accessibleName + `header_button()`. `Page.set_initial_focus()` mira al primo header. `eventFilter` su ogni header_button con dedup 100ms intercetta Up/Down e cicla tra sezioni. Space/Enter espande/collassa via QToolButton checkable. Inline-style ridotto a `border: 1px solid transparent` così `:focus` QSS globale può applicare l'accento senza layout shift.
  - [x] 3d. Metriche e Log: `metrics_page.Page.set_initial_focus()` → `self._scroll` (QScrollArea, arrows/PgUp/PgDn nativi). `log_page.Page.set_initial_focus()` → `self._view` (QPlainTextEdit readonly, navigazione cursore nativa).
  - [x] 3e. Mappa: `MapView.setFocusPolicy(StrongFocus)`, `keyPressEvent` con dedup time-only 250ms (cattura duplicates Qt-evdev anche quando arrivano con Qt.Key diversi tipo Equal/Plus per stesso scancode). Arrows pan 40px, `+/=` zoom in, `-/_` zoom out, `Home` → signal `home_requested` → Page `_recenter_local`, `[/]` cycle markers via `_marker_coords` dict popolato in `update_marker`/`clear_markers`. Page `set_initial_focus()` → `_view.setFocus()`. Bonus fix: zoom label da fixed-width 20px (troncava "z=9" a "z=") a min-width 32px e formato consistente `z{N}`.
- [x] **Step 4 — Keymap configurabile da GUI** (richiesta utente 2026-05-12):
  - [x] 4a. `gui/keymap.py` — ACTIONS list (13 azioni), load/save su `~/.config/pimesh/keymap.json` (write atomico via .tmp+rename), fallback ai default su file mancante o malformato.
  - [x] 4b. Refactor `gui/shortcuts.py` — ShortcutManager prende `load_keymap()`, mantiene `action_id → QShortcut` per `setKey()` in vivo, espone `get_binding/set_binding/reset_to_defaults`, singleton module-level `get_instance()`.
  - [x] 4c. `gui/pages/_shortcuts_section.py` — `_BindingButton` con capture-mode (intercetta keyPressEvent, ignora bare-modifier, Esc annulla), `Section` con QFormLayout + Reset, conflict detection + toast.
  - [x] 4d. Aggiungere section "Tasti" come prima sezione (top) della Config page.
  - [x] 4e. Deploy live: smoke test mostra UI corretta con F2/F3/F4 visibili e i restanti 10 binding scrollabili.
- [x] **Step 5 — Cheat-sheet F1**: `gui/widgets/cheatsheet.py::CheatsheetOverlay` parented to MainWindow, full-window semi-trasparente (rgba 8,12,24,235 + border accent). QFormLayout legge `ShortcutManager.get_binding(action_id)` per ogni voce → riflette automaticamente le rimappature. Dismiss su qualsiasi keypress non-modifier o click. ShortcutManager F1 handler instanzia (e dedup tramite `findChild`).
- [ ] **Step 6 — Accessible names** dove non già presenti (parziale: solo tab buttons e CollapsibleSection header).
- [x] **Step 7 — Export keymap QMK**: `docs/qmk-keymap-suggestion.md` con contratto F1..F12, motivazione (evdevkeyboard non copre F13+), layout suggerito 4×12 con `_BASE`+`_PIMESH` layer, snippet `keymap.c`.

## Bonus fix (2026-05-12)
- [x] **Log page details**: `format_log_line()` ignorava `event["summary"]` (pre-built da `meshtasticd_client`) e `event["ts"]`. Risultato: righe TELEMETRY tutte identiche `… · SNR ? · TELEMETRY_APP hops=3` nonostante payload diversi. Fix: usa summary (batt/voltage/temp/humidity/lat-lon/text), prepend `HH:MM:SS`, abbrevia portnum (`TELEMETRY_APP` → `TELEMETRY`). Bonus: word-wrap on per QPlainTextEdit così le righe lunghe non richiedono scroll orizzontale.

## Verifica
Prima di ogni "step complete":
- deploy su Pi (regola memory `feedback_deploy_and_test.md`);
- test manuale con tastiera USB collegata;
- screenshot via `C-A-S-P` se ho già lo step 1, altrimenti via touch;
- check che il touchscreen continui a funzionare in parallelo (non regressione).

## Domande aperte da risolvere prima di codare
- Quanti tasti **fisici** avrai a disposizione? Determina quante combo "first-class" (senza modificatori) possiamo permetterci vs. tutto su `C-A-S-`.
- Il firmware potrà avere **layer multipli** (es. layer Mappa, layer Msg) o sarà un layout flat? Con layer si può rimappare gli stessi 6 tasti per ogni pagina e la GUI riceve sempre lo stesso scancode logico.
- `map_page.py` usa `QWebEngineView` o widget custom? (definisce la complessità Step 3e)
