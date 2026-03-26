# Theme Editor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Aggiungere un editor temi UI in Settings che permette di creare/modificare temi custom con color picker per tutte e 10 le CSS vars, font picker (sistema + `static/fonts/`), preview live, persistenza in `static/themes.json`.

**Architecture:** I temi custom sono salvati in `static/themes.json` (array JSON). `main.py` espone 4 nuovi endpoint REST. `base.html` inietta un `<style>` con le CSS vars del tema attivo se custom. L'editor in `settings.html` aggiorna le CSS vars live via `document.documentElement.style.setProperty` e salva tramite `POST /api/themes`.

**Tech Stack:** FastAPI, Jinja2, `<input type="color">` nativo browser, `static/themes.json`, `static/fonts/`

**Design doc:** `docs/plans/2026-03-26-theme-editor-design.md`

---

### Task 1: backend — helpers `_load_themes` / `_save_themes` + endpoint `GET /api/themes`

**Files:**
- Modify: `main.py`
- Test: `tests/test_theme_api.py`

**Step 1: scrivi il test fallente**

```python
# tests/test_theme_api.py
import json, pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


@pytest.fixture
def mock_hw():
    mock_conn = MagicMock()
    mock_conn.execute  = AsyncMock()
    mock_conn.commit   = AsyncMock()
    mock_conn.close    = AsyncMock()
    with patch("database.init_db",            new_callable=AsyncMock, return_value=mock_conn), \
         patch("database.get_nodes",           new_callable=AsyncMock, return_value=[]),       \
         patch("database.get_messages",        new_callable=AsyncMock, return_value=[]),       \
         patch("meshtastic_client.init"),                                                       \
         patch("meshtastic_client.connect",    new_callable=AsyncMock),                        \
         patch("meshtastic_client.disconnect", new_callable=AsyncMock),                        \
         patch("meshtastic_client.is_connected",  return_value=False),                         \
         patch("meshtastic_client.get_local_node", return_value=None),                         \
         patch("sensor_handler.init",          return_value=[]),                               \
         patch("sensor_handler.start_polling", new_callable=AsyncMock),                        \
         patch("gpio_handler.init"),                                                            \
         patch("watchdog.start_all"):
        yield mock_conn


def _get_app():
    import sys
    if "main" in sys.modules:
        del sys.modules["main"]
    import config
    config.SETUP_DONE = True
    from main import app
    return app


@pytest.mark.asyncio
async def test_get_themes_includes_builtins(mock_hw):
    from httpx import AsyncClient, ASGITransport
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/themes")
    assert resp.status_code == 200
    data = resp.json()
    ids = [t["id"] for t in data["themes"]]
    assert "dark" in ids
    assert "light" in ids
    assert "hc" in ids


@pytest.mark.asyncio
async def test_get_themes_includes_custom(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    themes_file.write_text(json.dumps([{
        "id": "my-theme", "name": "My Theme", "font": "system-ui",
        "vars": {"--bg": "#111111", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }]))
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/themes")
    data = resp.json()
    ids = [t["id"] for t in data["themes"]]
    assert "my-theme" in ids
```

**Step 2: verifica fallimento**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py -v 2>&1 | tail -10
```
Expected: ImportError o 404 — endpoint non esiste.

**Step 3: implementa in `main.py`**

Aggiungi dopo `import re` (in cima al file, con gli altri import):
```python
import json as _json
```

Aggiungi dopo la riga `_PORT_RE = ...` (vicino agli altri helper constants):
```python
THEMES_PATH = "static/themes.json"

_BUILTIN_THEMES = [
    {"id": "dark",  "name": "Scuro",          "builtin": True},
    {"id": "light", "name": "Chiaro",          "builtin": True},
    {"id": "hc",    "name": "Alto contrasto",  "builtin": True},
]

_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_ID_RE    = re.compile(r'^[a-z0-9-]{1,32}$')
_SYSTEM_FONTS = ["system-ui", "monospace", "Georgia", '"Courier New"']


def _load_themes() -> list:
    try:
        with open(THEMES_PATH) as f:
            return _json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.error(f"_load_themes: {e}")
        return []


def _save_themes(themes: list) -> None:
    import os
    os.makedirs(os.path.dirname(THEMES_PATH) or ".", exist_ok=True)
    with open(THEMES_PATH, "w") as f:
        _json.dump(themes, f, indent=2)
```

Aggiungi l'endpoint dopo `POST /api/setup/reset`:
```python
@app.get("/api/themes")
async def list_themes():
    custom = _load_themes()
    return {"themes": _BUILTIN_THEMES + [dict(t, builtin=False) for t in custom]}
```

**Step 4: verifica test**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py::test_get_themes_includes_builtins tests/test_theme_api.py::test_get_themes_includes_custom -v
```
Expected: 2 passed.

**Step 5: suite completa**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/ -q 2>&1 | tail -5
```

**Step 6: commit**

```bash
git add main.py tests/test_theme_api.py && git commit -m "feat: add _load_themes/_save_themes helpers and GET /api/themes endpoint"
```

---

### Task 2: backend — `POST /api/themes`, `DELETE /api/themes/{id}`, `GET /api/themes/fonts`

**Files:**
- Modify: `main.py`
- Test: `tests/test_theme_api.py`

**Step 1: aggiungi test**

Aggiungi in fondo a `tests/test_theme_api.py`:

```python
@pytest.mark.asyncio
async def test_post_theme_creates_entry(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    app = _get_app()
    payload = {
        "id": "my-theme", "name": "My Theme", "font": "system-ui",
        "vars": {"--bg": "#111111", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/themes", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    saved = _json.loads(themes_file.read_text())
    assert saved[0]["id"] == "my-theme"


@pytest.mark.asyncio
async def test_post_theme_rejects_invalid_color(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    app = _get_app()
    payload = {
        "id": "bad", "name": "Bad", "font": "system-ui",
        "vars": {"--bg": "red", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/themes", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_theme(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    themes_file.write_text(_json.dumps([{
        "id": "to-delete", "name": "Del", "font": "system-ui",
        "vars": {"--bg": "#111111", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }]))
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/themes/to-delete")
    assert resp.status_code == 200
    saved = _json.loads(themes_file.read_text())
    assert len(saved) == 0


@pytest.mark.asyncio
async def test_delete_builtin_rejected(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    monkeypatch.setattr("main.THEMES_PATH", str(tmp_path / "themes.json"))
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/themes/dark")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_fonts_returns_list(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "MyFont.ttf").write_bytes(b"")
    (fonts_dir / "Other.woff2").write_bytes(b"")
    monkeypatch.setattr("main.FONTS_PATH", str(fonts_dir))
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/themes/fonts")
    assert resp.status_code == 200
    data = resp.json()
    assert "system_fonts" in data
    assert "custom_fonts" in data
    names = [f["name"] for f in data["custom_fonts"]]
    assert "MyFont" in names
```

**Step 2: verifica fallimento**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py -v 2>&1 | tail -15
```
Expected: i 5 nuovi test falliscono.

**Step 3: implementa in `main.py`**

Aggiungi dopo `THEMES_PATH = "static/themes.json"`:
```python
FONTS_PATH = "static/fonts"
```

Aggiungi i 3 nuovi endpoint dopo `GET /api/themes`:

```python
_REQUIRED_VARS = {"--bg","--bg2","--bg3","--border","--text","--text2",
                  "--accent","--ok","--warn","--danger"}

@app.post("/api/themes")
async def save_theme(payload: dict):
    theme_id = str(payload.get("id", "")).strip().lower()
    if not _ID_RE.match(theme_id):
        return JSONResponse({"ok": False, "error": "id non valido"}, status_code=400)
    if theme_id in ("dark", "light", "hc"):
        return JSONResponse({"ok": False, "error": "id riservato"}, status_code=400)
    name = str(payload.get("name", theme_id))[:40]
    font = str(payload.get("font", "system-ui"))
    # validate font: system list or alphanumeric + space/dash/underscore
    allowed_fonts = set(_SYSTEM_FONTS)
    import os, glob as _glob2
    for p in _glob2.glob(f"{FONTS_PATH}/*.ttf") + _glob2.glob(f"{FONTS_PATH}/*.woff2"):
        allowed_fonts.add(os.path.splitext(os.path.basename(p))[0])
    if font not in allowed_fonts:
        return JSONResponse({"ok": False, "error": "font non valido"}, status_code=400)
    vars_raw = payload.get("vars", {})
    if not isinstance(vars_raw, dict) or not _REQUIRED_VARS.issubset(vars_raw.keys()):
        return JSONResponse({"ok": False, "error": "vars incompleto"}, status_code=400)
    for k, v in vars_raw.items():
        if k not in _REQUIRED_VARS:
            return JSONResponse({"ok": False, "error": f"variabile sconosciuta: {k}"}, status_code=400)
        if not _COLOR_RE.match(str(v)):
            return JSONResponse({"ok": False, "error": f"colore non valido: {k}={v}"}, status_code=400)
    themes = [t for t in _load_themes() if t["id"] != theme_id]
    themes.append({"id": theme_id, "name": name, "font": font, "vars": vars_raw})
    _save_themes(themes)
    return {"ok": True}


@app.delete("/api/themes/{theme_id}")
async def delete_theme(theme_id: str):
    if theme_id in ("dark", "light", "hc"):
        return JSONResponse({"ok": False, "error": "tema built-in non eliminabile"}, status_code=400)
    themes = [t for t in _load_themes() if t["id"] != theme_id]
    _save_themes(themes)
    return {"ok": True}


@app.get("/api/themes/fonts")
async def list_fonts():
    import os, glob as _glob2
    custom = []
    for p in sorted(_glob2.glob(f"{FONTS_PATH}/*.ttf") + _glob2.glob(f"{FONTS_PATH}/*.woff2")):
        name = os.path.splitext(os.path.basename(p))[0]
        ext  = os.path.splitext(p)[1].lstrip(".")
        custom.append({"name": name, "file": os.path.basename(p), "format": ext})
    return {
        "system_fonts": _SYSTEM_FONTS,
        "custom_fonts": custom,
    }
```

**Step 4: verifica test**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py -v 2>&1 | tail -15
```
Expected: 7 passed.

**Step 5: suite completa**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/ -q 2>&1 | tail -5
```

**Step 6: commit**

```bash
git add main.py tests/test_theme_api.py && git commit -m "feat: POST /api/themes, DELETE /api/themes/{id}, GET /api/themes/fonts"
```

---

### Task 3: backend — iniezione tema custom in `base.html` + context nei template

**Files:**
- Modify: `main.py`
- Modify: `templates/base.html`
- Test: `tests/test_theme_api.py`

**Step 1: aggiungi test**

Aggiungi in fondo a `tests/test_theme_api.py`:

```python
@pytest.mark.asyncio
async def test_base_html_injects_custom_theme_style(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    themes_file.write_text(_json.dumps([{
        "id": "my-theme", "name": "My Theme", "font": "system-ui",
        "vars": {"--bg": "#aabbcc", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }]))
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    import config
    config.UI_THEME = "my-theme"
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/home")
    assert resp.status_code == 200
    assert b"#aabbcc" in resp.content
    config.UI_THEME = "dark"  # reset
```

**Step 2: verifica fallimento**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py::test_base_html_injects_custom_theme_style -v 2>&1 | tail -10
```

**Step 3: aggiungi helper `_get_custom_theme` in `main.py`**

Aggiungi dopo `_save_themes`:
```python
def _get_custom_theme(theme_id: str) -> dict | None:
    """Restituisce il dict del tema custom se esiste, None se built-in o non trovato."""
    if theme_id in ("dark", "light", "hc"):
        return None
    for t in _load_themes():
        if t["id"] == theme_id:
            return t
    return None
```

**Step 4: aggiungi `custom_theme` e `custom_fonts` al context di tutti i template**

In `main.py`, ogni `TemplateResponse` deve ricevere `custom_theme` e `custom_fonts`. Crea un helper che costruisce il context comune:

```python
def _base_ctx(extra: dict = None) -> dict:
    """Context condiviso da tutti i template (tema, font custom)."""
    ct = _get_custom_theme(cfg.UI_THEME)
    # font custom per @font-face in base.html
    import os, glob as _glob2
    cf = {}
    for p in sorted(_glob2.glob(f"{FONTS_PATH}/*.ttf") + _glob2.glob(f"{FONTS_PATH}/*.woff2")):
        name = os.path.splitext(os.path.basename(p))[0]
        cf[name] = os.path.basename(p)
    ctx = {
        "theme":        cfg.UI_THEME,
        "density":      cfg.UI_STATUS_DENSITY,
        "orientation":  cfg.UI_ORIENTATION,
        "channel_layout": cfg.UI_CHANNEL_LAYOUT,
        "custom_theme": ct,
        "custom_fonts": cf,
    }
    if extra:
        ctx.update(extra)
    return ctx
```

Poi aggiorna le route esistenti per usarlo. Per esempio la route `/home`:
```python
# prima:
return templates.TemplateResponse(request, "home.html", {
    "nodes": nodes, "node": node_info,
    "theme": cfg.UI_THEME, "density": cfg.UI_STATUS_DENSITY,
    "orientation": cfg.UI_ORIENTATION, "channel_layout": cfg.UI_CHANNEL_LAYOUT,
    "active": "home", "now": int(time.time()),
})
# dopo:
return templates.TemplateResponse(request, "home.html",
    _base_ctx({"nodes": nodes, "node": node_info, "active": "home", "now": int(time.time())}))
```

Applica lo stesso refactor a tutte le route pagina: `/home`, `/channels`, `/map`, `/hardware`, `/settings`, `/remote`, `/setup`.

**Step 5: modifica `templates/base.html`**

Aggiungi subito dopo `<link rel="stylesheet" href="/static/style.css">`:

```html
{% if custom_fonts %}
<style>
{% for font_name, font_file in custom_fonts.items() %}
@font-face { font-family: {{ font_name | e }}; src: url('/static/fonts/{{ font_file | e }}'); }
{% endfor %}
</style>
{% endif %}
{% if custom_theme %}
<style id="custom-theme-style">
body.theme-{{ theme | e }} {
  font-family: {{ custom_theme.font | e }};
{% for var, val in custom_theme.vars.items() %}
  {{ var | e }}: {{ val | e }};
{% endfor %}
}
</style>
{% endif %}
```

**Step 6: verifica test**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py -v 2>&1 | tail -12
```
Expected: 8 passed.

**Step 7: suite completa**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/ -q 2>&1 | tail -5
```

**Step 8: commit**

```bash
git add main.py templates/base.html && git commit -m "feat: inject custom theme CSS vars in base.html; add _base_ctx helper"
```

---

### Task 4: `/api/set-theme` — accetta temi custom

**Files:**
- Modify: `main.py`
- Test: `tests/test_theme_api.py`

**Step 1: aggiungi test**

```python
@pytest.mark.asyncio
async def test_set_theme_accepts_custom(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    themes_file = tmp_path / "themes.json"
    themes_file.write_text(_json.dumps([{
        "id": "my-theme", "name": "My", "font": "system-ui",
        "vars": {"--bg": "#111111", "--bg2": "#222222", "--bg3": "#333333",
                 "--border": "#444444", "--text": "#ffffff", "--text2": "#aaaaaa",
                 "--accent": "#ff0000", "--ok": "#00ff00", "--warn": "#ffff00",
                 "--danger": "#ff0000"}
    }]))
    monkeypatch.setattr("main.THEMES_PATH", str(themes_file))
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/set-theme", json={"theme": "my-theme"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_set_theme_rejects_unknown(mock_hw, tmp_path, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    monkeypatch.setattr("main.THEMES_PATH", str(tmp_path / "themes.json"))
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/set-theme", json={"theme": "nonexistent"})
    assert resp.status_code == 400
```

**Step 2: verifica fallimento**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py::test_set_theme_accepts_custom tests/test_theme_api.py::test_set_theme_rejects_unknown -v 2>&1 | tail -10
```

**Step 3: modifica `POST /api/set-theme` in `main.py`**

```python
# prima:
if theme not in ("dark", "light", "hc"):
    return JSONResponse({"ok": False}, status_code=400)

# dopo:
_valid_ids = {"dark", "light", "hc"} | {t["id"] for t in _load_themes()}
if theme not in _valid_ids:
    return JSONResponse({"ok": False, "error": "tema non trovato"}, status_code=400)
```

**Step 4: verifica test**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/test_theme_api.py -v 2>&1 | tail -15
```
Expected: 10 passed.

**Step 5: suite completa**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/ -q 2>&1 | tail -5
```

**Step 6: commit**

```bash
git add main.py tests/test_theme_api.py && git commit -m "feat: /api/set-theme accepts custom theme ids"
```

---

### Task 5: `settings.html` — sezione Temi custom con editor e preview live

**Files:**
- Modify: `templates/settings.html`

Nota: questa task non ha test automatici (è UI pura). La verifica è manuale.

**Step 1: aggiungi la sezione in `settings.html`**

Trova la fine della sezione `Display` (dopo il `</div>` che chiude il blocco con `section-header Display`) e aggiungi prima della sezione `Interfaccia`:

```html
<div class="section-header">Temi custom</div>
<div id="custom-themes-list" style="padding:4px 0"></div>
<div style="padding:8px">
  <button class="btn btn-secondary" style="width:100%;font-size:12px" onclick="openThemeEditor(null)">+ Nuovo tema</button>
</div>

<div id="theme-editor" style="display:none;border-top:1px solid var(--border)">
  <div style="padding:12px;display:flex;flex-direction:column;gap:10px">

    <div class="setting-row">
      <span class="setting-label">Nome</span>
      <input type="text" id="te-name" maxlength="40" placeholder="Es. Foresta">
    </div>

    <div class="setting-row">
      <span class="setting-label">Font</span>
      <select id="te-font"></select>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <label style="font-size:11px;color:var(--text2)">Sfondo principale
        <input type="color" id="te--bg" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Sfondo card
        <input type="color" id="te--bg2" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Sfondo input
        <input type="color" id="te--bg3" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Bordi
        <input type="color" id="te--border" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Testo primario
        <input type="color" id="te--text" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Testo secondario
        <input type="color" id="te--text2" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Accent / bottoni
        <input type="color" id="te--accent" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">OK / online
        <input type="color" id="te--ok" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Avviso
        <input type="color" id="te--warn" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
      <label style="font-size:11px;color:var(--text2)">Errore
        <input type="color" id="te--danger" style="width:100%;height:28px;padding:2px;border:1px solid var(--border);border-radius:4px;background:none;cursor:pointer">
      </label>
    </div>

    <div style="display:flex;gap:8px">
      <button class="btn btn-primary"   style="flex:1;font-size:12px" onclick="saveTheme()">Salva</button>
      <button class="btn btn-secondary" style="flex:1;font-size:12px" onclick="cancelTheme()">Annulla</button>
    </div>
    <div id="te-status" style="font-size:11px;color:var(--text2)"></div>
  </div>
</div>
```

**Step 2: aggiungi il blocco JS in fondo a `settings.html`, prima di `</body>`**

```html
<script>
// ---- Theme editor ----
const TE_VARS = ['--bg','--bg2','--bg3','--border','--text','--text2','--accent','--ok','--warn','--danger']
let _teEditId  = null   // null = nuovo tema
let _teOrigVars = {}    // vars prima dell'edit, per ripristino su Annulla

function _slugify(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,32) || 'tema'
}

function _getCSSVar(v) {
  return getComputedStyle(document.documentElement).getPropertyValue(v).trim()
}

function _applyPreview(vars, font) {
  const root = document.documentElement
  for (const [k,v] of Object.entries(vars)) root.style.setProperty(k, v)
  if (font) root.style.setProperty('font-family', font)
}

function _resetPreview() {
  const root = document.documentElement
  for (const v of TE_VARS) root.style.removeProperty(v)
  root.style.removeProperty('font-family')
}

function openThemeEditor(theme) {
  _teEditId = theme ? theme.id : null
  // Capture current vars for cancel
  _teOrigVars = {}
  for (const v of TE_VARS) _teOrigVars[v] = _getCSSVar(v) || '#000000'

  document.getElementById('te-name').value = theme ? theme.name : ''
  // Populate font select
  fetch('/api/themes/fonts').then(r=>r.json()).then(data => {
    const sel = document.getElementById('te-font')
    sel.textContent = ''
    const allFonts = [...data.system_fonts, ...data.custom_fonts.map(f=>f.name)]
    allFonts.forEach(f => {
      const opt = document.createElement('option')
      opt.value = f
      opt.textContent = f
      if (theme && theme.font === f) opt.selected = true
      sel.appendChild(opt)
    })
    if (!theme) sel.value = 'system-ui'
  })
  // Set color pickers
  const vars = theme ? theme.vars : _teOrigVars
  for (const v of TE_VARS) {
    const el = document.getElementById('te' + v)
    if (el) el.value = vars[v] || '#000000'
  }
  // Live preview on input
  for (const v of TE_VARS) {
    const el = document.getElementById('te' + v)
    if (el) el.oninput = () => {
      document.documentElement.style.setProperty(v, el.value)
    }
  }
  document.getElementById('te-font').onchange = e => {
    document.documentElement.style.setProperty('font-family', e.target.value)
  }
  document.getElementById('theme-editor').style.display = 'block'
  document.getElementById('theme-editor').scrollIntoView({behavior:'smooth'})
}

function cancelTheme() {
  _resetPreview()
  document.getElementById('theme-editor').style.display = 'none'
}

function saveTheme() {
  const name = document.getElementById('te-name').value.trim()
  if (!name) { document.getElementById('te-status').textContent = 'Inserisci un nome'; return }
  const id   = _teEditId || _slugify(name)
  const font = document.getElementById('te-font').value
  const vars = {}
  for (const v of TE_VARS) vars[v] = document.getElementById('te' + v).value
  const btn = document.querySelector('#theme-editor .btn-primary')
  btn.disabled = true
  document.getElementById('te-status').textContent = 'Salvataggio…'
  fetch('/api/themes', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({id, name, font, vars})
  })
  .then(r=>r.json())
  .then(data => {
    btn.disabled = false
    if (data.ok) {
      document.getElementById('te-status').textContent = '✓ Salvato'
      document.getElementById('theme-editor').style.display = 'none'
      loadCustomThemes()
    } else {
      document.getElementById('te-status').textContent = 'Errore: ' + (data.error||'sconosciuto')
    }
  })
}

function loadCustomThemes() {
  fetch('/api/themes').then(r=>r.json()).then(data => {
    const list = document.getElementById('custom-themes-list')
    list.textContent = ''
    const custom = data.themes.filter(t => !t.builtin)
    if (custom.length === 0) {
      const p = document.createElement('p')
      p.style.cssText = 'font-size:12px;color:var(--text2);padding:8px'
      p.textContent = 'Nessun tema personalizzato.'
      list.appendChild(p)
      return
    }
    custom.forEach(t => {
      const row = document.createElement('div')
      row.className = 'setting-row'
      const label = document.createElement('span')
      label.textContent = t.name
      label.style.fontSize = '13px'
      const actions = document.createElement('div')
      actions.style.cssText = 'display:flex;gap:4px'

      const btnActivate = document.createElement('button')
      btnActivate.className = 'btn btn-secondary'
      btnActivate.style.fontSize = '11px'
      btnActivate.textContent = 'Attiva'
      btnActivate.onclick = () => {
        fetch('/api/set-theme', {method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({theme:t.id})})
          .then(r=>r.json()).then(d=>{ if(d.ok) location.reload() })
      }

      const btnEdit = document.createElement('button')
      btnEdit.className = 'btn btn-secondary'
      btnEdit.style.fontSize = '11px'
      btnEdit.textContent = 'Modifica'
      btnEdit.onclick = () => openThemeEditor(t)

      const btnDel = document.createElement('button')
      btnDel.className = 'btn btn-danger'
      btnDel.style.fontSize = '11px'
      btnDel.textContent = 'Elimina'
      btnDel.onclick = () => {
        if (!confirm('Eliminare il tema "' + t.name + '"?')) return
        fetch('/api/themes/' + encodeURIComponent(t.id), {method:'DELETE'})
          .then(r=>r.json()).then(() => loadCustomThemes())
      }

      actions.appendChild(btnActivate)
      actions.appendChild(btnEdit)
      actions.appendChild(btnDel)
      row.appendChild(label)
      row.appendChild(actions)
      list.appendChild(row)
    })
  })
}

loadCustomThemes()
</script>
```

**Step 3: verifica manuale**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && SETUP_DONE=1 python -m uvicorn main:app --port 8080 2>&1 &
```
Apri `http://localhost:8080/settings`.
- Verifica che la sezione "Temi custom" sia presente
- Crea un tema, cambia colori → la pagina deve cambiare colore in tempo reale
- Salva → il tema appare nella lista
- Attiva → la pagina si ricarica con il nuovo tema

```bash
kill %1
```

**Step 4: suite completa**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/ -q 2>&1 | tail -5
```

**Step 5: commit**

```bash
git add templates/settings.html && git commit -m "feat: theme editor UI in Settings — color pickers, font picker, live preview"
```

---

### Task 6: `.gitignore` + `static/fonts/` directory + push

**Files:**
- Modify: `.gitignore`
- Create: `static/fonts/.gitkeep`

**Step 1: aggiorna `.gitignore`**

Controlla se esiste `.gitignore`:
```bash
cat /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign/.gitignore
```

Aggiungi queste righe se non presenti:
```
static/themes.json
static/fonts/*.ttf
static/fonts/*.woff2
static/fonts/*.woff
static/fonts/*.otf
```

**Step 2: crea la directory fonts**

```bash
mkdir -p /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign/static/fonts
touch /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign/static/fonts/.gitkeep
```

**Step 3: suite completa**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && python -m pytest tests/ -q 2>&1 | tail -5
```

**Step 4: commit e push**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh/.worktrees/ui-redesign && \
git add .gitignore static/fonts/.gitkeep && \
git commit -m "chore: add static/fonts/ dir and gitignore custom theme files" && \
git push origin feature/ui-redesign
```
