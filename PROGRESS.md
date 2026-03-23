# Meshtastic Pi — Progress

Aggiorna questo file dopo ogni step completato.
Formato: `[x]` completato, `[ ]` da fare, `[~]` in corso

Per riprendere il lavoro: trova il primo `[ ]` e segui il piano in
`docs/plans/2026-03-23-meshtastic-pi-design.md`

---

## M1 — Core Backend
- [x] M1-S0 setup
- [x] M1-S1 `config.py` + `config.env` + `requirements.txt`
- [ ] M1-S2 `database.py`
- [ ] M1-S3 `meshtastic_client.py`
- [ ] M1-S4 `watchdog.py`

## M2 — UI Base
- [ ] M2-S1 `main.py` scheletro + WebSocket
- [ ] M2-S2 `style.css` + `base.html` dual-orientation
- [ ] M2-S3 `app.js` WebSocket client
- [ ] M2-S4 `messages.html`
- [ ] M2-S5 `nodes.html`
- [ ] M2-S6 `map.html` + tile offline

## M3 — UI Estesa
- [ ] M3-S1 `gpio_handler.py`
- [ ] M3-S2 `sensor_handler.py`
- [ ] M3-S3 `telemetry.html`
- [ ] M3-S4 `settings.html` base
- [ ] M3-S5 temi UI (light/dark/high-contrast)
- [ ] M3-S6 config GPIO/I2C da UI

## M4 — Feature Avanzate
- [ ] M4-S1 admin nodi remoti
- [ ] M4-S2 config nodo avanzata (ruoli + LoRa preset)
- [ ] M4-S3 framework bot
- [ ] M4-S4 collaudo completo
