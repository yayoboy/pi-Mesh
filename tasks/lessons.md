# Lezioni — pi-Mesh

## Redesign web UI su kiosk WPE/cog (2026-07-05)

- **La SPA di app.js innesta solo il `#content`**: gli `<style>` e i `<link>` nel
  `{% block head %}` delle pagine NON vengono applicati navigando dalla sidebar.
  Gli stili di pagina vanno nel content block; app.js ora inietta anche i
  `<link rel=stylesheet>` del head. Qualsiasi `getElementById(...)` a livello
  di script di pagina è null durante la navigazione SPA → usare delega sul
  document con guardia anti-doppia-registrazione.
- **WPE/cog espone `window.PointerEvent` ma non emette mai pointer events dai
  tocchi** (consegna TouchEvent reali). Librerie che preferiscono i pointer
  (Leaflet 1.9) restano sorde al touch. Firma del caso: `ontouchstart` presente
  + `maxTouchPoints === 0` → shim in base.html che nasconde PointerEvent.
- **Leaflet scrive attributi SVG**: `var(--token)` non si risolve negli
  attributi presentazionali — leggere i colori computati dal root
  (`themeColor()` in map.js) a ogni render.
- **Istanze Jinja2Templates multiple = globals fantasma**: ogni router creava
  la sua istanza e i globals di main.py non arrivavano mai alle pagine
  (`map_local_tiles` sempre vuoto → tile locali mai usate). Ora c'è
  `templating.py` condiviso; i globals dinamici sono callable.
- **Flag persistiti nel DB vanno riconciliati alla connessione**: `is_local`
  restava sulla board precedente per sempre (`set_local_node()` al connect).
- **Diagnosi touch senza dita**: touchscreen virtuale uinput (python3-evdev,
  protocollo MT tipo B clonando i range del pannello) + pagina di test che
  logga gli eventi a un http.server locale. Le pagine diagnostiche sono in
  static/touchtest.html e static/leaflettest.html.
- **Alpine x-show azzera il `display` inline** al rimostrare (`display:''`):
  mai mettere `display:flex` inline su un elemento con x-show — la centratura
  dei modali va in una classe CSS. E il binding `:style` stringa SOSTITUISCE
  lo style statico, non lo fonde.
- **pkill -f si suicida via ssh**: il pattern matcha anche la cmdline della
  propria sessione remota — usare classi carattere (`'http[.]server'`).
- **fbgrab è cieco in modalità KMS**: cattura la console fbdev, non il piano
  DRM di cog — la feature screenshot dell'app va riscritta per KMS.
- **grep -vi "warning" mangia i log dell'app**: il backend logga tutto a
  livello WARNING (`WARNING:meshtasticd_client:...`) — filtrare solo
  `setlocale`/`warning:` di bash, mai la parola intera case-insensitive.
- **EDID di pannelli HDMI economici**: possono dichiarare preferred un modo
  interlacciato inesistente ("out of range") — start-kiosk-hdmi.sh ora forza
  il gemello progressivo via COG_PLATFORM_DRM_VIDEO_MODE (nome modo DRM
  esatto, senza @refresh: cog fa strcmp e crasha in SIGTRAP se non matcha).
- **Undervoltage (0x50005) produce SIGSEGV casuali di cog** sotto carico —
  prima di dare la colpa al software, `vcgencmd get_throttled` e dmesg.
