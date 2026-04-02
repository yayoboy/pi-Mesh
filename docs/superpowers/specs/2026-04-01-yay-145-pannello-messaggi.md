# YAY-145 — Pannello Messaggi

## Overview

Due bug indipendenti nel pannello messaggi:
1. Info nodo mancanti nei messaggi ricevuti
2. Lista messaggi scorre infinitamente al caricamento

## Bug 1 — Info nodo mancanti

### Problema

`get_messages` e `get_dm_messages` non fanno JOIN con la tabella `nodes`, quindi `short_name` e `distance_km` non sono disponibili nel payload. Il template usa `window.nodeCache` che non è popolato sulla pagina messaggi (è inizializzato solo in `map.html`).

### Fix

**`database.py`** — `get_messages` e `get_dm_messages`:
- Aggiungere LEFT JOIN con `nodes` su `node_id`
- Restituire `short_name` e `distance_km` per ogni messaggio

**`templates/messages.html`**:
- Sostituire `window.nodeCache?.get(msg.node_id)?.short_name || msg.node_id` con `msg.short_name || msg.node_id`
- Meta line per messaggi ricevuti: `short_name · HH:MM · SNR dB · Nhop · X.Xkm`
- Ogni campo appare solo se non null

## Bug 2 — Scroll infinito

### Problema

`IntersectionObserver` osserva il sentinel (primo elemento della lista) immediatamente dopo `init()`. Prima che `loadMessages()` faccia scroll in fondo, il sentinel è visibile → `loadMore()` scatta in loop.

### Fix

**`templates/messages.html`**:
- Rimuovere sentinel element `<div x-ref="sentinel">` e l'`IntersectionObserver`
- Aggiungere listener `scroll` sul `$refs.msgList`:
  ```js
  this._onScroll = () => {
    if (this.$refs.msgList.scrollTop < 80) this.loadMore()
  }
  this.$refs.msgList.addEventListener('scroll', this._onScroll)
  ```
- Rimuovere listener in `destroy()`

## Files to Modify

- `database.py` — `get_messages`, `get_dm_messages`: aggiungere LEFT JOIN nodes
- `templates/messages.html` — fix template node info + fix scroll listener
- `tests/test_api.py` — aggiungere test per short_name nella risposta messaggi
