# QMK keymap suggestion for pi-Mesh

This document describes the **firmware-side contract** for a custom QMK
keyboard (CardKB-like form factor, ~48 keys) that drives the pi-Mesh GUI.
The GUI itself ships defaults that match this layout exactly; the user
can rebind anything from **Config → Tasti** without touching the firmware.

## Contract summary

The GUI listens for these QKeySequence values out of the box:

| pi-Mesh action          | Default key |
|-------------------------|-------------|
| Cheatsheet overlay      | `F1`        |
| Page Nodi               | `F2`        |
| Page Mappa              | `F3`        |
| Page Msg                | `F4`        |
| Page Config             | `F5`        |
| Page Metriche           | `F6`        |
| Page Log                | `F7`        |
| Telemetria (hidden)     | `F8`        |
| Screenshot              | `F9`        |
| Rotation menu           | `F10`       |
| Reboot (confirm)        | `F11`       |
| Shutdown (confirm)      | `F12`       |
| Toggle VKB              | `Shift+F12` |

Per-page extras (handled by widget-level event handlers, **not** keymap
configurable today):

- **Map**: arrows pan, `+`/`-` zoom, `Home` recenter local, `[`/`]` cycle markers.
- **Config**: arrows walk between collapsible section headers, `Space`/`Enter` expand/collapse, `Tab`/`Shift+Tab` step into/out of section bodies.
- **Nodi**: arrows on the list, `Enter` opens node detail.
- **Msg**: `Enter` sends, `Shift+Enter` newline.
- **Log/Metriche**: arrows/PgUp/PgDn scroll natively.

## Why F1..F12 (and not F13..F24)

Qt's `evdevkeyboard` plugin under `linuxfb` ships a built-in keymap
derived from US English and does **not** cover F13..F24 — those scancodes
reach the kernel but Qt drops them before turning them into QKeyEvents.
Sticking to F1..F12 keeps the defaults working with zero custom-keymap
plumbing, while the user can still rebind anything to any QKeySequence
that Qt parses (including `Ctrl+X`, `Alt+M`, etc.) via the UI.

## Suggested QMK layout (CardKB-like, 4×12 ≈ 48 keys)

The idea: stay typeable in **base layer** (so the user can compose
messages naturally on the Msg page), and put all pi-Mesh navigation
behind a single `Fn` modifier so it doesn't collide with text.

### Base layer (`_BASE`)

Plain QWERTY-ish row mapping. `Fn` is a one-shot held modifier (not a
toggle) that activates `_PIMESH`. Caps/Sym/Bksp/Enter behave as on a
CardKB.

```
  Q  W  E  R  T  Y  U  I  O  P  Bksp
  A  S  D  F  G  H  J  K  L  ;  Ent
Sh  Z  X  C  V  B  N  M  ,  .  /
Sym Fn       Space          Sym
```

### Fn layer (`_PIMESH`)

This is the pi-Mesh control layer. Holding `Fn`:

```
  F1  F2  F3  F4  F5  F6  F7  F8  F9 F10 F11
  Hm  ↑   PgU [   ]   …   ?   ?   ?  F12  Esc
←   ↓   →   -   +   ?   ?   ?   ?   ?   ?
?   trans                              Shift+F12
```

Mapping per row (top → bottom):

| Position    | Sends         | What it does in pi-Mesh     |
|-------------|---------------|------------------------------|
| Row 0, k1   | `F1`          | Cheatsheet overlay           |
| Row 0, k2   | `F2`          | Page Nodi                    |
| Row 0, k3   | `F3`          | Page Mappa                   |
| Row 0, k4   | `F4`          | Page Msg                     |
| Row 0, k5   | `F5`          | Page Config                  |
| Row 0, k6   | `F6`          | Page Metriche                |
| Row 0, k7   | `F7`          | Page Log                     |
| Row 0, k8   | `F8`          | Telemetria                   |
| Row 0, k9   | `F9`          | Screenshot                   |
| Row 0, k10  | `F10`         | Rotation                     |
| Row 0, k11  | `F11`         | Reboot                       |
| Row 1, k1   | `KC_HOME`     | Map: recenter local          |
| Row 1, k2   | `KC_UP`       | Map: pan north / Config nav  |
| Row 1, k3   | `KC_PGUP`     | Log/Metriche: scroll up      |
| Row 1, k4   | `KC_LBRC` `[` | Map: cycle marker prev       |
| Row 1, k5   | `KC_RBRC` `]` | Map: cycle marker next       |
| Row 1, k10  | `F12`         | Shutdown                     |
| Row 1, k11  | `KC_ESC`      | Dismiss dialogs/overlays     |
| Row 2, k1   | `KC_LEFT`     | Map: pan west                |
| Row 2, k2   | `KC_DOWN`     | Map: pan south / Config nav  |
| Row 2, k3   | `KC_RIGHT`    | Map: pan east                |
| Row 2, k4   | `KC_MINS` `-` | Map: zoom out                |
| Row 2, k5   | `KC_EQL` `+`  | Map: zoom in (`=`)           |
| Row 3, k12  | `LSFT(F12)`   | Toggle VKB                   |

`?` slots are unused — natural spots for user macros (paste a canned
message, jump to a specific nodes filter, ...). The GUI ignores
anything it doesn't have a binding for, so adding extras costs nothing.

## QMK keymap snippet

Minimal `keymap.c` excerpt (drop into `qmk_firmware/keyboards/<your-board>/keymaps/pimesh/keymap.c`):

```c
enum layers { _BASE, _PIMESH };

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
  [_BASE] = LAYOUT(
    KC_Q, KC_W, KC_E, KC_R, KC_T, KC_Y, KC_U, KC_I, KC_O, KC_P, KC_BSPC,
    KC_A, KC_S, KC_D, KC_F, KC_G, KC_H, KC_J, KC_K, KC_L, KC_SCLN, KC_ENT,
    KC_LSFT, KC_Z, KC_X, KC_C, KC_V, KC_B, KC_N, KC_M, KC_COMM, KC_DOT, KC_SLSH,
    KC_NO, MO(_PIMESH), KC_SPC, KC_NO
  ),
  [_PIMESH] = LAYOUT(
    KC_F1, KC_F2, KC_F3, KC_F4, KC_F5, KC_F6, KC_F7, KC_F8, KC_F9, KC_F10, KC_F11,
    KC_HOME, KC_UP, KC_PGUP, KC_LBRC, KC_RBRC, KC_NO, KC_NO, KC_NO, KC_NO, KC_F12, KC_ESC,
    KC_LEFT, KC_DOWN, KC_RIGHT, KC_MINS, KC_EQL, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO,
    KC_NO, KC_TRNS, KC_NO, S(KC_F12)
  ),
};
```

(Matrix size and exact `LAYOUT(...)` shape must match the physical
PCB — this is the logical mapping, not a drop-in for an arbitrary board.)

## Re-binding via the GUI

Open **Config → Tasti**, click the binding cell of the action you want
to change, then press the new combo. `Esc` cancels capture. Conflicts
(same combo bound to two actions) surface as a toast and the rebind is
rejected. The change is persisted to `~/.config/pimesh/keymap.json`
atomically and the live `QShortcut` updates without a restart.

If the file gets corrupted, the GUI silently falls back to the defaults
above and logs a warning — no risk of losing keyboard control.
