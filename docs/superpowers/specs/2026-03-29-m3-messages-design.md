# M3 — Messages: Design Spec

**Issue:** YAY-148
**Branch:** rework/v2-rewrite
**Date:** 2026-03-29
**Status:** Approved

---

## Obiettivo

Pagina messaggi completa con broadcast multi-canale, DM thread per nodo, ACK ✓/✓✓, cronologia persistente con auto-cleanup 30 giorni. DM inviabili da qualsiasi pagina con nodi (mappa, lista nodi) via `nodeActions.sendDM()` già implementato in M2.

---

## Approccio

Riscrittura pulita in stile v2 — Alpine.js, typed WS events, coerente con architettura M1/M2. Nessun port dal worktree YAY-106.

---

## Layout

Sidebar fissa 130px (sinistra) + area thread (destra). Funziona su entrambi gli orientamenti senza media query. Basato sul layout esistente di `messages.html`, riscritto con Alpine.js.

```
┌─────────────────────────────────────────────────┐
│ statusbar                                       │
├──────────────┬──────────────────────────────────┤
│ CONV         │ Broadcast · CH 0     [#0 ▾] [🗑] │
│ ──────────── │ ─────────────────────────────────│
│ 📢 Broadcast │ NODE1  Ciao da NODE1             │
│ ──────────── │        5m fa · -8dB              │
│ DM           │                                  │
│  NODE1  [2]  │              Ok ricevuto  ✓✓    │
│  NODE2       │                                  │
│  NODE3       │ NODE2  Qualcuno in zona?          │
│              │        12m fa                    │
│              │ ─────────────────────────────────│
│              │ [input.....................] [➤]  │
├──────────────┴──────────────────────────────────┤
│ tabbar                                          │
└─────────────────────────────────────────────────┘
```

---

## Database Schema

### Tabella `messages` (aggiornamento)

```sql
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT NOT NULL,        -- mittente (!abc123)
    channel     INTEGER DEFAULT 0,
    text        TEXT NOT NULL,
    ts          INTEGER NOT NULL,     -- unix timestamp
    is_outgoing INTEGER DEFAULT 0,   -- 1 = inviato da noi
    rx_snr      REAL,
    hop_count   INTEGER,
    ack         INTEGER DEFAULT 0,   -- 0 = inviato, 1 = ACK ricevuto
    destination TEXT DEFAULT '^all'  -- '^all' broadcast, '!nodeid' DM
);
```

### Tabella `dm_reads` (nuova)

```sql
CREATE TABLE IF NOT EXISTS dm_reads (
    peer_id      TEXT PRIMARY KEY,
    last_read_ts INTEGER NOT NULL   -- ts ultimo messaggio visto dall'utente
);
```

Unread count per thread = `COUNT(*)` messaggi con `destination = local_id OR node_id = peer` con `ts > last_read_ts` e `is_outgoing = 0`.

### Funzioni database

```python
async def save_message(db_path, node_id, channel, text, ts, is_outgoing, rx_snr, hop_count, destination) -> int
async def get_messages(db_path, channel, limit=50, before_id=None) -> list[dict]
async def get_dm_threads(db_path, local_id) -> list[dict]       # [{peer_id, last_text, last_ts, unread}]
async def get_dm_messages(db_path, peer_id, local_id, limit=50, before_id=None) -> list[dict]
async def mark_dm_read(db_path, peer_id) -> None                # upsert dm_reads
async def update_message_ack(db_path, node_id) -> None          # ack=1 su msg outgoing più recente verso node_id
async def clear_messages(db_path) -> None                       # DELETE FROM messages; DELETE FROM dm_reads
async def cleanup_old_messages(db_path, days=30) -> None        # DELETE WHERE ts < now - days*86400
```

---

## Backend — `meshtasticd_client.py`

Aggiunta in `_on_receive()` dopo `TRACEROUTE_APP`:

```python
elif portnum == 'TEXT_MESSAGE_APP':
    text    = decoded.get('text', '')
    to_num  = packet.get('to', 0xFFFFFFFF)
    dest    = '^all' if to_num == 0xFFFFFFFF else f'!{to_num:08x}'
    msg_id  = await database.save_message(
        cfg.DB_PATH, from_id, decoded.get('channel', 0),
        text, int(time.time()), False,
        snr, hop_limit, dest
    )
    typed_event = {
        'type':        'message',
        'id':          msg_id,
        'node_id':     from_id,
        'channel':     decoded.get('channel', 0),
        'text':        text,
        'ts':          int(time.time()),
        'is_outgoing': False,
        'rx_snr':      snr,
        'hop_count':   hop_limit,
        'ack':         0,
        'destination': dest,
    }
    if _loop is not None:
        _loop.call_soon_threadsafe(_event_queue.put_nowait, typed_event)

elif portnum == 'ROUTING_APP':
    # ACK packet — aggiorna messaggio outgoing più recente verso from_id
    error_reason = decoded.get('routing', {}).get('errorReason', 'NONE')
    if error_reason == 'NONE':
        asyncio.run_coroutine_threadsafe(
            database.update_message_ack(cfg.DB_PATH, from_id), _loop
        )
        ack_event = {'type': 'ack', 'node_id': from_id}
        if _loop is not None:
            _loop.call_soon_threadsafe(_event_queue.put_nowait, ack_event)
```

Nota: `save_message` è `async` ma `_on_receive` è sync (thread meshtastic). Usare `asyncio.run_coroutine_threadsafe(..., _loop)` per il salvataggio DB, come per l'ACK.

---

## Backend — `routers/messages_router.py` (nuovo)

```python
GET  /messages                    → TemplateResponse('messages.html', {nodes_data, messages})
GET  /api/messages                → lista broadcast (params: channel, limit, before_id)
GET  /api/dm/threads              → lista thread DM con unread count
GET  /api/dm/messages             → messaggi DM (params: peer, limit, before_id)
POST /api/dm/read                 → {"peer_id": "!abc"} → mark_dm_read
DELETE /api/messages              → clear_messages() + risposta {"ok": true}
```

`POST /api/messages/send` rimane in `routers/commands.py` (page-agnostic, già funzionante).

`local_id` negli endpoint DM viene letto da `meshtasticd_client._local_id` (già esposto come variabile modulo, pattern identico a `_connected`).

### Risposta `GET /api/messages`

```json
[
  {
    "id": 42,
    "node_id": "!a1b2c3d4",
    "channel": 0,
    "text": "Ciao da NODE1",
    "ts": 1711700000,
    "is_outgoing": false,
    "rx_snr": -8.0,
    "hop_count": 2,
    "ack": 0,
    "destination": "^all"
  }
]
```

### Risposta `GET /api/dm/threads`

```json
[
  {
    "peer_id": "!a1b2c3d4",
    "short_name": "NODE1",
    "last_text": "Sei lì?",
    "last_ts": 1711700000,
    "unread": 2
  }
]
```

---

## Backend — `main.py`

```python
from routers import messages_router
app.include_router(messages_router.router)
```

Nel lifespan, dopo `database.init()`:
```python
await database.cleanup_old_messages(cfg.DB_PATH, days=30)
```

---

## Backend — `routers/placeholders.py`

Rimuovere la route `/messages` (ora gestita da `messages_router`).

---

## Frontend — `static/app.js`

Aggiungere handler per evento `ack` nel dispatcher WS:

```javascript
ack: (msg) => {
    window.dispatchEvent(new CustomEvent('msg-ack', { detail: msg }))
},
```

`handleMessage()` già presente e funzionante — emette `message-new`.

---

## Frontend — `templates/messages.html`

### Alpine.js component `messagesPage()`

```javascript
{
  conv: 'broadcast',        // 'broadcast' | '!nodeid'
  channel: 0,
  messages: [],
  dmThreads: [],
  hasMore: false,
  loading: false,
  selectedPeer: null,

  get convTitle() { ... },  // 'Broadcast' | short_name del peer

  async init() {
    await this.loadDmThreads()
    await this.loadMessages()
    window.addEventListener('message-new', (e) => this.onNewMessage(e.detail))
    window.addEventListener('msg-ack', (e) => this.onAck(e.detail))
  },

  async selectConv(type, peerId) { ... },
  async loadMessages(prepend=false) { ... },  // broadcast o DM in base a this.conv
  async loadMore() { ... },                    // before_id = this.messages[0].id
  async loadDmThreads() { ... },
  async send() { ... },                        // nodeActions.sendDM o POST broadcast
  onNewMessage(msg) { ... },                   // aggiunge se conv corrente
  onAck(msg) { ... },                          // aggiorna ✓✓ sul messaggio
  clearHistory() { ... },                      // DELETE /api/messages
}
```

### ACK display (CSS + x-text)

```
is_outgoing=0 → nessuna spunta (messaggio ricevuto)
is_outgoing=1, ack=0 → ✓ (colore muted)
is_outgoing=1, ack=1 → ✓✓ (colore accent)
```

Implementato con SVG Heroicons inline o caratteri Unicode nei metadata della bolla.

### Icone (SVG Heroicons, no testo)

| Azione | Icona |
|--------|-------|
| Pulisci cronologia | `trash` |
| Selettore canale | `hashtag` + numero |
| Invio messaggio | `paper-airplane` (già presente) |
| Unread badge | punto colorato `#4a9eff` |

### Sidebar DM — unread badge

Punto colorato `#4a9eff` a destra del nome nodo se unread > 0. Nessun contatore numerico.

### Scroll infinito

IntersectionObserver su sentinel `#load-more` in cima alla lista. Quando visibile → `loadMore()` → `GET /api/messages?before_id=<oldest_id>`.

---

## Testing — `tests/test_messages.py`

```python
test_save_and_get_broadcast_messages()    # salva 3 msg CH0, verifica ordinamento e campi
test_get_messages_pagination()            # 60 msg, before_id restituisce batch corretto
test_save_dm_and_get_threads()            # DM tra 2 nodi, verifica threads con unread count
test_mark_dm_read()                       # apri thread → unread torna 0
test_update_message_ack()                 # msg outgoing → update_ack → ack=1
test_clear_messages()                     # popola → clear → tabella vuota
test_cleanup_old_messages()               # msg vecchi e recenti → solo >30gg rimossi
```

`tests/test_api.py` — aggiunta:
```python
test_get_messages_endpoint()              # GET /api/messages → 200 + lista
test_get_dm_threads_endpoint()            # GET /api/dm/threads → 200
test_mark_dm_read_endpoint()              # POST /api/dm/read → 200
test_clear_messages_endpoint()            # DELETE /api/messages → 200
```

---

## File modificati / creati

| File | Tipo | Note |
|------|------|------|
| `database.py` | modifica | + tabella `messages` aggiornata, `dm_reads`, 8 funzioni async |
| `meshtasticd_client.py` | modifica | + TEXT_MESSAGE_APP handler, + ROUTING_APP ACK handler |
| `routers/messages_router.py` | nuovo | GET /messages, GET/DELETE /api/messages, DM endpoints |
| `routers/placeholders.py` | modifica | rimuovi route `/messages` |
| `main.py` | modifica | include messages_router, cleanup al boot |
| `static/app.js` | modifica | + handler `ack` nel dispatcher WS |
| `templates/messages.html` | riscrittura | Alpine.js messagesPage(), icone SVG, ACK display |
| `tests/test_messages.py` | nuovo | 7 test DB + logica |
| `tests/test_api.py` | modifica | + 4 test endpoint messaggi |

---

## Decisioni chiave

- `save_message` e `update_message_ack` chiamati da thread meshtastic via `asyncio.run_coroutine_threadsafe` — coerente con pattern `_loop` già usato per l'event queue
- `dm_reads` table separata — non aggiunge colonne a `messages`, più semplice da aggiornare atomicamente
- Unread badge = punto colorato (no contatore) — leggibile su 320px senza affollare la sidebar
- `clear_messages` svuota anche `dm_reads` — stato coerente
- Auto-cleanup 30gg al boot — nessun cron, nessuna complessità aggiuntiva
- `POST /api/messages/send` rimane in `commands.py` — page-agnostic, già usato da mappa e nodi
