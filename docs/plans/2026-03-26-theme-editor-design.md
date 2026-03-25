# Theme Editor — Design Document
**Data:** 2026-03-26
**Milestone:** M4 — Theme Editor
**Approccio:** A — editor inline in Settings con preview live

---

## Obiettivo

Permettere all'utente di creare e modificare temi UI personalizzati direttamente dall'interfaccia web, con anteprima in tempo reale, font picker (sistema + cartella `static/fonts/`) e color picker per tutte e 10 le variabili CSS. I temi custom si aggiungono ai tre built-in (dark/light/hc) e persistono dopo il riavvio.

---

## 1. Architettura dati

I temi custom sono salvati in `static/themes.json`:

```json
[
  {
    "id": "my-theme",
    "name": "My Theme",
    "font": "system-ui",
    "vars": {
      "--bg":      "#1a1a2e",
      "--bg2":     "#16213e",
      "--bg3":     "#0f3460",
      "--border":  "#533483",
      "--text":    "#e0e0e0",
      "--text2":   "#aaaaaa",
      "--accent":  "#e94560",
      "--ok":      "#4caf50",
      "--warn":    "#ffc107",
      "--danger":  "#f44336"
    }
  }
]
```

I temi built-in (dark/light/hc) rimangono definiti in `style.css` — non vengono toccati.

Il file `static/themes.json` viene creato al primo salvataggio se non esiste.

---

## 2. UI in Settings

Nuova sezione **"Temi custom"** aggiunta in fondo a **Settings → Display**.

### Lista temi custom
- Una riga per ogni tema: pallino colore accent + nome + pulsanti **Attiva** / **Modifica** / **Elimina**
- Pulsante **+ Nuovo tema** in fondo alla lista

### Form editor (inline, si apre sotto la lista)
- Campo **Nome tema** (testo libero, max 40 char)
- **Font picker** — `<select>` con:
  - Font di sistema: `system-ui`, `monospace`, `Georgia`, `"Courier New"`
  - Font trovati in `static/fonts/` (`.ttf` / `.woff2`), caricati via `@font-face` dinamico
- **10 color picker** — `<input type="color">` con etichetta descrittiva:

| Variabile | Etichetta |
|-----------|-----------|
| `--bg` | Sfondo principale |
| `--bg2` | Sfondo card / barre |
| `--bg3` | Sfondo input / celle |
| `--border` | Bordi |
| `--text` | Testo primario |
| `--text2` | Testo secondario |
| `--accent` | Accent / bottoni |
| `--ok` | OK / nodo online |
| `--warn` | Avviso |
| `--danger` | Errore / disconnesso |

- Pulsanti **Salva** e **Annulla**

### Preview live
Ogni modifica al color picker o al font picker aggiorna immediatamente le CSS vars sulla pagina via `document.documentElement.style.setProperty`. L'intera pagina Settings (header, card, bottoni, tab bar) funge da anteprima live. Al click su "Annulla" le variabili vengono ripristinate.

---

## 3. Backend — nuovi endpoint

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/api/themes` | Lista tutti i temi: built-in (dark/light/hc) + custom da `themes.json` |
| `POST` | `/api/themes` | Crea o aggiorna un tema custom → scrive `static/themes.json` |
| `DELETE` | `/api/themes/{id}` | Rimuove un tema custom da `static/themes.json` |
| `GET` | `/api/themes/fonts` | Lista font disponibili in `static/fonts/` |

Il `POST /api/set-theme` esistente continua a funzionare invariato — accetta qualsiasi `id` inclusi quelli custom.

---

## 4. Iniezione CSS in base.html

Quando il tema attivo è custom, il server inietta un blocco `<style>` in `base.html`:

```html
{% if custom_theme %}
<style id="custom-theme-style">
body.theme-{{ theme }} {
  font-family: {{ custom_theme.font | e }};
  {% for var, val in custom_theme.vars.items() %}
  {{ var }}: {{ val | e }};
  {% endfor %}
}
</style>
{% if custom_fonts %}
<style>
{% for font_name, font_path in custom_fonts.items() %}
@font-face { font-family: {{ font_name | e }}; src: url('/static/fonts/{{ font_path | e }}'); }
{% endfor %}
</style>
{% endif %}
{% endif %}
```

I `@font-face` per i font in `static/fonts/` vengono iniettati su tutte le pagine (non solo quando il tema custom è attivo), così sono disponibili nel picker anche quando si edita un nuovo tema.

---

## 5. Sicurezza

- **Colori** — validati server-side con regex `^#[0-9a-fA-F]{6}$` prima di scrivere nel JSON e iniettare nel template
- **Font name** — whitelist: font di sistema predefiniti + nomi derivati dai filename in `static/fonts/` (solo `[A-Za-z0-9 _-]`)
- **Theme id** — sanitizzato a `[a-z0-9-]`, max 32 caratteri; usato come classe CSS → no path traversal
- **Nome tema** — escape Jinja2 autoescape; non usato come id/classe
- **Built-in protection** — `DELETE /api/themes/{id}` rifiuta `dark`, `light`, `hc`

---

## 6. Modifiche ai file esistenti

| File | Modifica |
|------|----------|
| `main.py` | Aggiunge `GET/POST /api/themes`, `DELETE /api/themes/{id}`, `GET /api/themes/fonts`; modifica helper per caricare `themes.json`; inietta `custom_theme` nel context di tutti i template |
| `templates/base.html` | Aggiunge iniezione `<style>` per tema custom e `@font-face` |
| `templates/settings.html` | Aggiunge sezione "Temi custom" con lista + form editor + JS color picker |
| `static/themes.json` | Creato al primo salvataggio (non in git, aggiunto a `.gitignore`) |
| `static/fonts/` | Directory già in `static/`; aggiunta a `.gitignore` per i font dell'utente |

---

## 7. Struttura directory finale

```
pi-Mesh/
├── static/
│   ├── style.css                  ← invariato
│   ├── themes.json                ← nuovo (creato al runtime, in .gitignore)
│   └── fonts/                     ← nuova dir (font utente, in .gitignore)
├── templates/
│   ├── base.html                  ← modifica: iniezione <style> custom
│   └── settings.html              ← modifica: sezione temi custom
└── docs/plans/
    └── 2026-03-26-theme-editor-design.md
```
