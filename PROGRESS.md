# Meshtastic Pi — Progress

Aggiorna questo file dopo ogni step completato.
Formato: `[x]` completato, `[ ]` da fare, `[~]` in corso

Per riprendere il lavoro: trova il primo `[ ]` e segui il piano in
`docs/plans/2026-03-23-meshtastic-pi-design.md`

---

## M1 — Core Backend
- [x] M1-S0 setup
- [x] M1-S1 `config.py` + `config.env` + `requirements.txt`
- [x] M1-S2 `database.py`
- [x] M1-S3 `meshtastic_client.py`
- [x] M1-S4 `watchdog.py`

## M2 — UI Base
- [x] M2-S1 `main.py` scheletro + WebSocket
- [x] M2-S2 `style.css` + `base.html` dual-orientation
- [x] M2-S3 `app.js` WebSocket client
- [x] M2-S4 `messages.html`
- [x] M2-S5 `nodes.html`
- [x] M2-S6 `map.html` + tile offline

## M3 — UI Estesa
- [x] M3-S1 `gpio_handler.py`
- [x] M3-S2 `sensor_handler.py`
- [x] M3-S3 `telemetry.html`
- [x] M3-S4 `settings.html` base
- [x] M3-S5 temi UI (light/dark/high-contrast)
- [x] M3-S6 config GPIO/I2C da UI

## M4 — Feature Avanzate
- [x] M4-S1 admin nodi remoti
- [x] M4-S2 config nodo avanzata (ruoli + LoRa preset)
- [x] M4-S3 framework bot
- [ ] M4-S4 collaudo completo
