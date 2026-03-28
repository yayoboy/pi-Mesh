# YAY-106 — DM Thread View: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distinguere messaggi DM da broadcast con sidebar thread, menu contestuale nodi con info e azioni, badge unread in real-time.

**Architecture:** Aggiunta colonne `destination` e `read_at` in `messages`; 3 nuovi endpoint REST; pagina messaggi ristrutturata in sidebar conversazioni + thread; menu `···` nei nodi che espone info nodo e azioni incluso "Invia DM".

**Tech Stack:** Python 3.11, aiosqlite, FastAPI, Jinja2, vanilla JS, SVG Heroicons inline.

---

## File Map

| File | Operazione | Responsabilità |
|------|-----------|----------------|
| `database.py` | Modifica | Migrazione + `save_message` + 3 nuove funzioni |
| `meshtastic_client.py` | Modifica | `_parse_message` aggiunge `destination` |
| `main.py` | Modifica | Fix `/send` + 3 nuovi endpoint `/api/dm/*` |
| `templates/messages.html` | Riscrittura | Layout sidebar conversazioni |
| `static/app.js` | Modifica | Handler DM + `loadDmThread` + `loadDmThreads` |
| `templates/nodes.html` | Modifica | Menu `···` con info nodo + azioni |
| `tests/test_database.py` | Modifica | Test per nuove funzioni DM |

---

## Task 1: DB — migrazione e nuove funzioni

**Files:**
- Modify: `database.py`
- Modify: `tests/test_database.py`

- [ ] **Step 1.1: Scrivi i test che devono fallire**

Aggiungi in fondo a `tests/test_database.py`:

```python
@pytest.mark.asyncio
async def test_save_message_stores_destination(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    ts = int(time.time())
    await database.save_message(conn, "node1", 0, "ciao", ts, 0, None, None, destination="!abc123")
    msgs = await database.get_messages(conn, 0, limit=10)
    assert msgs[0]["destination"] == "!abc123"
    await conn.close()

@pytest.mark.asyncio
async def test_get_dm_threads_returns_threads_with_unread(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    ts = int(time.time())
    await database.save_message(conn, "!node1", 0, "ciao", ts,   0, None, None, destination="!local")
    await database.save_message(conn, "!node1", 0, "ok?",  ts+1, 0, None, None, destination="!local")
    await database.save_message(conn, "local",  0, "si!",  ts+2, 1, None, None, destination="!node1")
    threads = await database.get_dm_threads(conn)
    assert len(threads) == 1
    assert threads[0]["peer"] == "!node1"
    assert threads[0]["unread_count"] == 2
    await conn.close()

@pytest.mark.asyncio
async def test_get_dm_messages_returns_thread(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    ts = int(time.time())
    await database.save_message(conn, "!peer1", 0, "dm in",  ts,   0, None, None, destination="!local")
    await database.save_message(conn, "local",  0, "dm out", ts+1, 1, None, None, destination="!peer1")
    await database.save_message(conn, "!other", 0, "other",  ts+2, 0, None, None, destination="!local")
    msgs = await database.get_dm_messages(conn, "!peer1")
    assert len(msgs) == 2
    assert all(m["text"] in ("dm in", "dm out") for m in msgs)

@pytest.mark.asyncio
async def test_mark_dm_read_clears_unread(tmp_db):
    import database
    conn = await database.init_db(runtime_path=tmp_db)
    ts = int(time.time())
    await database.save_message(conn, "!peer1", 0, "msg1", ts,   0, None, None, destination="!local")
    await database.save_message(conn, "!peer1", 0, "msg2", ts+1, 0, None, None, destination="!local")
    threads_before = await database.get_dm_threads(conn)
    assert threads_before[0]["unread_count"] == 2
    await database.mark_dm_read(conn, "!peer1")
    threads_after = await database.get_dm_threads(conn)
    assert threads_after[0]["unread_count"] == 0
    await conn.close()
```

- [ ] **Step 1.2: Verifica che i test falliscano**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh
python -m pytest tests/test_database.py::test_save_message_stores_destination \
  tests/test_database.py::test_get_dm_threads_returns_threads_with_unread \
  tests/test_database.py::test_get_dm_messages_returns_thread \
  tests/test_database.py::test_mark_dm_read_clears_unread -v
```

Atteso: FAIL.

- [ ] **Step 1.3: Aggiungi migrazione in `_create_tables` (database.py, dopo il try per hop_count ~riga 73)**

```python
    for col_def in ["destination TEXT DEFAULT '^all'", "read_at INTEGER DEFAULT NULL"]:
        try:
            await conn.execute(f"ALTER TABLE messages ADD COLUMN {col_def}")
        except Exception:
            pass
    await conn.commit()
```

- [ ] **Step 1.4: Sostituisci `save_message` (database.py riga 78)**

```python
async def save_message(conn, node_id, channel, text, timestamp, is_outgoing, snr, rssi, destination='^all', hop_count=None):
    await conn.execute(
        "INSERT INTO messages (node_id,channel,text,timestamp,is_outgoing,rx_snr,rx_rssi,destination,hop_count) VALUES (?,?,?,?,?,?,?,?,?)",
        (node_id, channel, text, timestamp, is_outgoing, snr, rssi, destination, hop_count)
    )
    await conn.commit()
```

- [ ] **Step 1.5: Aggiungi 3 funzioni dopo `get_message_count` (database.py riga ~110)**

```python
async def get_dm_threads(conn) -> list:
    cur = await conn.execute(
        "SELECT CASE WHEN is_outgoing=1 THEN destination ELSE node_id END AS peer,"
        " text, timestamp, is_outgoing, read_at, id"
        " FROM messages WHERE destination != '^all' AND destination IS NOT NULL ORDER BY id DESC"
    )
    rows = [dict(r) for r in await cur.fetchall()]
    seen, unread = {}, {}
    for r in rows:
        peer = r["peer"]
        if peer not in seen:
            seen[peer] = r
        if not r["is_outgoing"] and r["read_at"] is None:
            unread[peer] = unread.get(peer, 0) + 1
    result = []
    for peer, msg in seen.items():
        msg["unread_count"] = unread.get(peer, 0)
        result.append(msg)
    return sorted(result, key=lambda x: x["timestamp"], reverse=True)

async def get_dm_messages(conn, peer_id: str, limit: int = 50, before_id: int = None) -> list:
    base = ("SELECT * FROM messages WHERE"
            " ((node_id = ? AND is_outgoing = 0 AND destination != '^all')"
            "  OR (destination = ? AND is_outgoing = 1))")
    if before_id:
        cur = await conn.execute(base + " AND id < ? ORDER BY id DESC LIMIT ?",
                                 (peer_id, peer_id, before_id, limit))
    else:
        cur = await conn.execute(base + " ORDER BY id DESC LIMIT ?", (peer_id, peer_id, limit))
    return [dict(r) for r in await cur.fetchall()]

async def mark_dm_read(conn, peer_id: str):
    await conn.execute(
        "UPDATE messages SET read_at = ? WHERE node_id = ? AND is_outgoing = 0"
        " AND read_at IS NULL AND destination != '^all'",
        (int(time.time()), peer_id)
    )
    await conn.commit()
```

- [ ] **Step 1.6: Esegui tutti i test database**

```bash
python -m pytest tests/test_database.py -v
```

Atteso: tutti PASS.

- [ ] **Step 1.7: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "feat: YAY-106 DB migration destination/read_at + get_dm_threads/messages/mark_read"
```

---

## Task 2: Backend — meshtastic_client + main.py

**Files:**
- Modify: `meshtastic_client.py`
- Modify: `main.py`

- [ ] **Step 2.1: Aggiungi `destination` nel dict di `_parse_message` (meshtastic_client.py riga ~302)**

Aggiungi questa riga nel dict restituito da `_parse_message`, dopo `"rssi"`:

```python
            "destination": packet.get("toId", "^all"),
```

- [ ] **Step 2.2: Fix `/send` — salva `destination` nel DB (main.py riga ~162)**

```python
# Sostituisci:
await database.save_message(_conn, "local", channel, text, int(time.time()), 1, None, None)
# Con:
await database.save_message(_conn, "local", channel, text, int(time.time()), 1, None, None, destination=destination)
```

- [ ] **Step 2.3: Aggiungi 3 endpoint DM in main.py dopo la route `GET /api/messages` (riga ~186)**

```python
@app.get("/api/dm/threads")
async def api_dm_threads():
    return await database.get_dm_threads(_conn)

@app.get("/api/dm/messages")
async def api_dm_messages(peer: str, limit: int = 50, before_id: int = None):
    if not peer:
        return JSONResponse({"error": "peer required"}, status_code=400)
    return await database.get_dm_messages(_conn, peer, limit, before_id)

@app.post("/api/dm/read")
async def api_dm_read(peer: str):
    if not peer:
        return JSONResponse({"error": "peer required"}, status_code=400)
    await database.mark_dm_read(_conn, peer)
    return {"ok": True}
```

- [ ] **Step 2.4: Verifica import**

```bash
python -c "import main; print('import OK')"
```

- [ ] **Step 2.5: Commit**

```bash
git add meshtastic_client.py main.py
git commit -m "feat: YAY-106 parse destination, fix /send DB save, add /api/dm/* endpoints"
```

---

## Task 3: messages.html — sidebar layout

**Files:**
- Rewrite: `templates/messages.html`

- [ ] **Step 3.1: Riscrivi il file con layout sidebar**

Il file deve estendere `base.html` e contenere nel `{% block content %}` un div flex con:

**Sidebar sinistra (width:130px, border-right, flex-column):**
- Header label "Conversazioni" (font-size:10px, color:var(--accent))
- Voce "Broadcast" con id `conv-broadcast`, icona megaphone SVG Heroicons, onclick `selectConv('broadcast', null)`
- Separatore + label "Diretti" (font-size:9px, color:var(--muted))
- `div#dm-thread-list` (flex:1, overflow-y:auto) — popolato da JS

**Area thread destra (flex:1, flex-column):**
- `div#thread-header` (padding:6px 10px, border-bottom): icona + `span#thread-title` + `span#thread-sub` + `select#ch-select` (display:none in DM)
- `div#msg-list` (flex:1, overflow-y:auto): messaggi server-rendered iniziali con Jinja `{% for m in messages|reverse %}`
- Form invio: `input#msg-input` + button submit con icona paper-plane SVG

**Stato e funzioni JS nel `<script>` del template:**

```javascript
let currentConv = 'broadcast'
let currentChannel = 0
let loadingMore = false

function selectConv(type, peerId) {
  currentConv = (type === 'broadcast') ? 'broadcast' : peerId
  // highlight sidebar: rimuovi stile attivo da tutte le voci, applica a quella cliccata
  document.querySelectorAll('.conv-item').forEach(el => { el.style.borderLeft = '2px solid transparent'; el.style.background = '' })
  const active = (type === 'broadcast')
    ? document.getElementById('conv-broadcast')
    : document.querySelector('[data-peer="' + CSS.escape(peerId) + '"]')
  if (active) { active.style.borderLeft = '2px solid var(--accent)'; active.style.background = 'var(--panel)' }

  if (type === 'broadcast') {
    document.getElementById('ch-select').style.display = ''
    document.getElementById('thread-title').textContent = 'Broadcast'
    document.getElementById('thread-sub').textContent = 'Canale ' + currentChannel + ' - tutti i nodi'
    reloadBroadcast()
  } else {
    document.getElementById('ch-select').style.display = 'none'
    const name = nodeCache.get(peerId)?.short_name || peerId
    document.getElementById('thread-title').textContent = name
    document.getElementById('thread-sub').textContent = 'Messaggio diretto'
    loadDmThread(peerId)
    fetch('/api/dm/read?peer=' + encodeURIComponent(peerId), { method: 'POST' })
    const badge = document.querySelector('[data-peer="' + CSS.escape(peerId) + '"] .unread-badge')
    if (badge) badge.remove()
  }
}

async function reloadBroadcast() {
  currentChannel = parseInt(document.getElementById('ch-select').value)
  document.getElementById('thread-sub').textContent = 'Canale ' + currentChannel + ' - tutti i nodi'
  const r = await fetch('/api/messages?channel=' + currentChannel + '&limit=50')
  if (r.ok) renderMessages([...(await r.json())].reverse(), false)
}

async function loadDmThread(peerId) {
  const r = await fetch('/api/dm/messages?peer=' + encodeURIComponent(peerId) + '&limit=50')
  if (r.ok) renderMessages([...(await r.json())].reverse(), true)
}

async function loadDmThreads() {
  const r = await fetch('/api/dm/threads')
  if (!r.ok) return
  const threads = await r.json()
  const list = document.getElementById('dm-thread-list')
  list.textContent = ''
  threads.forEach(t => {
    const item = document.createElement('div')
    item.className = 'conv-item'
    item.dataset.peer = t.peer
    item.style.cssText = 'padding:5px 8px; display:flex; align-items:center; gap:5px; cursor:pointer; font-size:11px; border-left:2px solid transparent;'
    item.onclick = () => selectConv('dm', t.peer)
    const nameEl = document.createElement('span')
    nameEl.style.cssText = 'flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'
    nameEl.textContent = nodeCache.get(t.peer)?.short_name || t.peer
    item.appendChild(nameEl)
    if (t.unread_count > 0) {
      const badge = document.createElement('span')
      badge.className = 'unread-badge'
      badge.style.cssText = 'background:var(--danger,#c62828); color:#fff; border-radius:8px; padding:0 5px; font-size:9px; flex-shrink:0;'
      badge.textContent = t.unread_count
      item.appendChild(badge)
    }
    list.appendChild(item)
  })
}

function renderMessages(msgs, isDm) {
  const list = document.getElementById('msg-list')
  list.textContent = ''
  msgs.forEach(m => list.appendChild(makeRow(m)))
  const sentinel = document.createElement('div')
  sentinel.id = 'load-more'
  list.appendChild(sentinel)
  list.scrollTop = list.scrollHeight
  observeSentinel()
}

function makeRow(m) {
  const row = document.createElement('div')
  row.className = 'msg-row' + (m.is_outgoing ? ' outgoing' : '')
  row.dataset.msgId = m.id
  const bubble = document.createElement('div')
  bubble.className = 'msg-bubble'
  bubble.textContent = m.text
  const meta = document.createElement('div')
  meta.className = 'msg-meta'
  const name = nodeCache.get(m.node_id)?.short_name || m.node_id
  const ts = new Date(m.timestamp * 1000).toLocaleTimeString('it', { hour:'2-digit', minute:'2-digit' })
  meta.textContent = (m.is_outgoing ? '' : name + ' \u00b7 ') + ts +
    (m.rx_snr != null ? ' \u00b7 ' + m.rx_snr + 'dB' : '') +
    (m.hop_count != null && m.hop_count > 0 ? ' \u00b7 ' + m.hop_count + 'hop' : '')
  if (m.is_outgoing) {
    const ackEl = document.createElement('span')
    ackEl.className = 'msg-ack' + (m.ack ? ' delivered' : '')
    ackEl.textContent = m.ack ? ' \u2713\u2713' : ' \u2713'
    ackEl.title = m.ack ? 'Consegnato' : 'Inviato'
    meta.appendChild(ackEl)
  }
  row.append(bubble, meta)
  return row
}

async function sendMsg(e) {
  e.preventDefault()
  const text  = document.getElementById('msg-input').value.trim()
  const input = document.getElementById('msg-input')
  if (!text) return
  const destination = (currentConv === 'broadcast') ? '^all' : currentConv
  const channel     = (currentConv === 'broadcast') ? currentChannel : 0
  const r = await fetch('/send', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ text, channel, destination })
  })
  if (r.ok) { input.value = '' }
  else { input.style.borderColor = 'var(--danger)'; setTimeout(() => { input.style.borderColor = '' }, 1500) }
}

function observeSentinel() {
  const sentinel = document.getElementById('load-more')
  if (!sentinel) return
  new IntersectionObserver(async ([entry]) => {
    if (!entry.isIntersecting || loadingMore) return
    const items = document.querySelectorAll('.msg-row')
    if (!items.length) return
    loadingMore = true
    const firstId = items[0].dataset.msgId
    if (!firstId) { loadingMore = false; return }
    const url = (currentConv === 'broadcast')
      ? '/api/messages?channel=' + currentChannel + '&limit=50&before_id=' + firstId
      : '/api/dm/messages?peer=' + encodeURIComponent(currentConv) + '&limit=50&before_id=' + firstId
    const resp = await fetch(url)
    const msgs = await resp.json()
    const list = document.getElementById('msg-list')
    const prevH = list.scrollHeight
    ;[...msgs].reverse().forEach(m => list.insertBefore(makeRow(m), list.firstChild))
    list.scrollTop = list.scrollHeight - prevH
    loadingMore = false
  }).observe(sentinel)
}

window.addEventListener('message-new', e => {
  const m = e.detail
  const isDm = m.destination && m.destination !== '^all'
  if (isDm) {
    loadDmThreads()
    if (currentConv === m.node_id || currentConv === m.destination) {
      const list = document.getElementById('msg-list')
      list.insertBefore(makeRow(m), document.getElementById('load-more'))
      list.scrollTop = list.scrollHeight
    }
  } else if (currentConv === 'broadcast' && m.channel === currentChannel) {
    const list = document.getElementById('msg-list')
    list.insertBefore(makeRow(m), document.getElementById('load-more'))
    list.scrollTop = list.scrollHeight
  }
})

window.addEventListener('msg-ack', () => {
  document.querySelectorAll('.msg-row.outgoing .msg-ack:not(.delivered)').forEach(el => {
    el.classList.add('delivered'); el.textContent = ' \u2713\u2713'; el.title = 'Consegnato'
  })
})

// Timestamp server-rendered
document.querySelectorAll('[data-ts]').forEach(el => {
  const ts = parseInt(el.dataset.ts)
  if (ts) el.textContent = new Date(ts * 1000).toLocaleTimeString('it', { hour:'2-digit', minute:'2-digit' })
})

// Init
const _openDm = new URLSearchParams(window.location.search).get('open_dm')
observeSentinel()
document.getElementById('msg-list').scrollTop = document.getElementById('msg-list').scrollHeight
loadDmThreads().then(() => { if (_openDm) selectConv('dm', _openDm) })
```

- [ ] **Step 3.2: Commit**

```bash
git add templates/messages.html
git commit -m "feat: YAY-106 messages sidebar layout con thread DM e broadcast"
```

---

## Task 4: app.js — dispatch eventi WebSocket

**Files:**
- Modify: `static/app.js`

- [ ] **Step 4.1: Verifica handler attuali**

```bash
grep -n "handleMessage\|handleAck\|dispatchEvent\|message-new\|msg-ack" static/app.js | head -20
```

- [ ] **Step 4.2: Aggiorna `handleMessage` per dispatchare `message-new`**

Trova `handleMessage` in `app.js`. Deve dispatchare `message-new` con `detail: data`:

```javascript
function handleMessage(data) {
  messageCache.unshift(data)
  if (messageCache.length > 200) messageCache.pop()
  window.dispatchEvent(new CustomEvent('message-new', { detail: data }))
  const prefix = (data.destination && data.destination !== '^all') ? 'DM ' : 'MSG '
  showToast(prefix + (data.node_id || '') + ': ' + (data.text || '').slice(0, 30))
}
```

- [ ] **Step 4.3: Aggiorna `handleAck` per dispatchare `msg-ack`**

```javascript
function handleAck(data) {
  window.dispatchEvent(new CustomEvent('msg-ack', { detail: data }))
}
```

- [ ] **Step 4.4: Commit**

```bash
git add static/app.js
git commit -m "feat: YAY-106 app.js dispatch message-new e msg-ack"
```

---

## Task 5: nodes.html — menu ··· con info nodo

**Files:**
- Modify: `templates/nodes.html`

Il menu `···` (bottone con `data-menu-btn`) sostituisce il click-sull'intera-riga come trigger per aprire il pannello dettaglio. Il pannello ora mostra info nodo in griglia + 3 azioni.

- [ ] **Step 5.1: Aggiungi helper `makeSvgIcon` nel blocco script**

Aggiungi all'inizio del `<script>` in `nodes.html`:

```javascript
function makeSvgIcon(type) {
  const ns = 'http://www.w3.org/2000/svg'
  const svg = document.createElementNS(ns, 'svg')
  svg.setAttribute('width', '13'); svg.setAttribute('height', '13')
  svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor')
  svg.setAttribute('stroke-width', '2'); svg.setAttribute('viewBox', '0 0 24 24')
  const defs = {
    menu:  [['circle','5','12','2'], ['circle','12','12','2'], ['circle','19','12','2']],
    chat:  null,
    pin:   null,
    trash: null,
  }
  if (type === 'menu') {
    defs.menu.forEach(([tag, cx, cy, r]) => {
      const el = document.createElementNS(ns, 'circle')
      el.setAttribute('cx', cx); el.setAttribute('cy', cy); el.setAttribute('r', r)
      svg.appendChild(el)
    })
  } else {
    const paths = {
      chat:  'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z',
      pin:   'M17.657 16.657L13.414 20.9a2 2 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z',
      trash: 'M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16',
    }
    const p = document.createElementNS(ns, 'path')
    p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round')
    p.setAttribute('d', paths[type])
    svg.appendChild(p)
  }
  return svg
}
```

- [ ] **Step 5.2: Aggiorna `renderNodeRow` — header con bottone `···`**

Nel header della riga (dopo `stats`), sostituisci il `div stats` con:
1. `span#dm-badge-{id}` (display:none, bg rosso) per unread DM
2. `button` con `data-menu-btn=n.id`, `makeSvgIcon('menu')` come contenuto, stile `background:none; border:none; padding:4px; cursor:pointer; color:var(--muted)`

Rimuovi il div `stats` che mostrava batteria/SNR (queste info appaiono nel pannello dettaglio).

- [ ] **Step 5.3: Aggiorna `renderNodeRow` — pannello dettaglio**

Sostituisci il contenuto del `detail` div con:

1. **Griglia info** (display:grid, grid-template-columns: auto 1fr, gap: 2px 10px, font-size:11px):
   Campi: ID, Nome, HW, Firmware, Batteria (se disponibile), SNR (se disponibile), RSSI (se disponibile), Ultimo visto (formattato con toLocaleTimeString), Posizione lat/lon (se disponibile).
   
   Costruzione con createElement: per ogni campo `[label, value]`, crea due `span` — label con `color:var(--muted)`, value con il testo.

2. **Sezione azioni** (border-top, padding-top, flex-column, gap:4px):
   - Bottone "Invia DM": `makeSvgIcon('chat')` + testo, onclick `window.location.href = '/messages?open_dm=' + encodeURIComponent(n.id)`
   - Bottone posizione: `makeSvgIcon('pin')` + testo "Richiedi posizione", `dataset.reqPos = n.id`
   - Bottone elimina: `makeSvgIcon('trash')` + testo "Elimina nodo", `dataset.forgetNode = n.id`, colore `var(--danger)`
   - Label checkbox cascade: come attuale ma con testo "anche messaggi e telemetria"

- [ ] **Step 5.4: Aggiorna template Jinja server-rendered**

Aggiorna il blocco `{% for n in nodes %}` per corrispondere alla struttura JS:
- Header: badge + info (nome/long_name) + span#dm-badge + button data-menu-btn con SVG tre cerchi
- Pannello detail: griglia info + azioni (link `/messages?open_dm=`, button req-pos, button forget-node + checkbox cascade)

SVG nei template Jinja (inserisci inline, non inline JS):
```html
<!-- Icona menu tre cerchi -->
<svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
  <circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>
</svg>
<!-- Icona chat -->
<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
</svg>
<!-- Icona pin -->
<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a2 2 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z"/>
</svg>
<!-- Icona trash -->
<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
  <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
</svg>
```

- [ ] **Step 5.5: Aggiorna click handler `node-list`**

Sostituisci il handler esistente:

```javascript
document.getElementById('node-list').addEventListener('click', e => {
  const reqBtn = e.target.closest('[data-req-pos]')
  if (reqBtn) {
    e.stopPropagation()
    fetch('/send', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ text: '', destination: reqBtn.dataset.reqPos, type: 'position_request' })
    })
    return
  }
  const forgetBtn = e.target.closest('[data-forget-node]')
  if (forgetBtn) {
    e.stopPropagation()
    const nodeId = forgetBtn.dataset.forgetNode
    if (!confirm('Eliminare il nodo ' + nodeId + '?')) return
    const cascadeCheck = document.querySelector('[data-forget-cascade="' + nodeId + '"]')
    fetch('/api/nodes/' + encodeURIComponent(nodeId) + (cascadeCheck?.checked ? '?cascade=true' : ''), { method: 'DELETE' })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          document.querySelector('[data-node-id="' + nodeId + '"]')?.remove()
          if (!document.querySelector('[data-node-id]')) {
            const msg = document.createElement('div')
            msg.id = 'no-nodes'
            msg.style.cssText = 'padding:24px; text-align:center; color:var(--muted); font-size:13px;'
            msg.textContent = 'Nessun nodo rilevato'
            document.getElementById('node-list').appendChild(msg)
          }
        }
      })
    return
  }
  const menuBtn = e.target.closest('[data-menu-btn]')
  if (menuBtn) {
    e.stopPropagation()
    const nodeId = menuBtn.dataset.menuBtn
    const el = document.getElementById('detail-' + nodeId)
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none'
    return
  }
})
```

- [ ] **Step 5.6: Commit**

```bash
git add templates/nodes.html
git commit -m "feat: YAY-106 nodes menu contestuale con info nodo e azioni DM/posizione/elimina"
```

---

## Task 6: Deploy e verifica

- [ ] **Step 6.1: Esegui tutti i test**

```bash
cd /Users/yayoboy/Desktop/GitHub/pi-Mesh
python -m pytest tests/test_database.py tests/test_main.py -v
```

Atteso: tutti PASS.

- [ ] **Step 6.2: Deploy su Raspberry Pi**

```bash
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.superpowers' \
  /Users/yayoboy/Desktop/GitHub/pi-Mesh/ pi@192.168.1.36:/home/pi/pi-Mesh/
ssh pi@192.168.1.36 "sudo systemctl restart meshtastic-pi@pimesh"
```

- [ ] **Step 6.3: Verifica endpoint**

```bash
curl http://192.168.1.36/api/dm/threads
```

Atteso: `[]` o lista thread JSON.

- [ ] **Step 6.4: Verifica UI messaggi (http://192.168.1.36/messages)**

- Sidebar sinistra con "Broadcast" e sezione "Diretti"
- Select canale visibile solo in Broadcast
- Thread DM si apre cliccando nodo con `?open_dm`

- [ ] **Step 6.5: Verifica menu nodi (http://192.168.1.36/nodes)**

- Icona `···` visibile su ogni riga
- Click apre pannello con info griglia + azioni
- "Invia DM" naviga a messages con thread pre-selezionato

- [ ] **Step 6.6: Push + chiudi issue**

```bash
git push origin master
```

Marca YAY-106 come Done in Linear.
