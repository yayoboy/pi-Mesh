# Canned Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere messaggi rapidi predefiniti inviabili con un tap dalla pagina messaggi, con lista configurabile in /config.

**Architecture:** Nuovo router `canned_router.py` con CRUD su tabella `canned_messages`. Pulsante ⚡ in `messages.html` apre modal Alpine.js. Sezione "Canned" in `config.html` gestisce la lista. Pattern identico ai router esistenti.

**Tech Stack:** FastAPI, aiosqlite, Alpine.js, Jinja2

---

### Task 1: DB schema e funzioni CRUD

**Files:**
- Modify: `database.py`
- Create: `tests/test_canned_db.py`

- [ ] **Step 1: Aggiungi tabella `canned_messages` a `_SCHEMA`**

In `database.py`, trova la riga:
```
CREATE INDEX IF NOT EXISTS idx_telemetry_node_ts ON telemetry(node_id, ts DESC);
```
Aggiungi **prima** della tripla-virgoletta `"""` che chiude `_SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS canned_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0
);
```

- [ ] **Step 2: Aggiungi funzioni CRUD in `database.py`** (dopo `cleanup_telemetry`):

```python
async def get_canned_messages() -> list:
    async with _get_db() as db:
        cur = await db.execute(
            'SELECT id, text, sort_order FROM canned_messages ORDER BY sort_order, id'
        )
        rows = await cur.fetchall()
        return [{'id': r[0], 'text': r[1], 'sort_order': r[2]} for r in rows]


async def add_canned_message(text: str, sort_order: int = 0) -> int:
    async with _get_db() as db:
        cur = await db.execute(
            'INSERT INTO canned_messages (text, sort_order) VALUES (?, ?)',
            (text, sort_order)
        )
        await db.commit()
        return cur.lastrowid


async def update_canned_message(msg_id: int, text: str, sort_order: int) -> None:
    async with _get_db() as db:
        await db.execute(
            'UPDATE canned_messages SET text=?, sort_order=? WHERE id=?',
            (text, sort_order, msg_id)
        )
        await db.commit()


async def delete_canned_message(msg_id: int) -> None:
    async with _get_db() as db:
        await db.execute('DELETE FROM canned_messages WHERE id=?', (msg_id,))
        await db.commit()
```

- [ ] **Step 3: Crea `tests/test_canned_db.py`**

```python
import asyncio
import pytest
import database


@pytest.fixture
def tmp_db(tmp_path):
    path = str(tmp_path / 'test.db')
    asyncio.run(database.init(path))
    yield path
    asyncio.run(database.close())


def test_canned_messages_empty_on_init(tmp_db):
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs == []


def test_canned_messages_add_and_get(tmp_db):
    msg_id = asyncio.run(database.add_canned_message('CQ CQ'))
    assert isinstance(msg_id, int)
    msgs = asyncio.run(database.get_canned_messages())
    assert len(msgs) == 1
    assert msgs[0]['text'] == 'CQ CQ'
    assert msgs[0]['sort_order'] == 0


def test_canned_messages_update(tmp_db):
    msg_id = asyncio.run(database.add_canned_message('CQ CQ'))
    asyncio.run(database.update_canned_message(msg_id, 'CQ DX', 5))
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs[0]['text'] == 'CQ DX'
    assert msgs[0]['sort_order'] == 5


def test_canned_messages_delete(tmp_db):
    msg_id = asyncio.run(database.add_canned_message('CQ CQ'))
    asyncio.run(database.delete_canned_message(msg_id))
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs == []


def test_canned_messages_order_by_sort_order(tmp_db):
    asyncio.run(database.add_canned_message('B', sort_order=10))
    asyncio.run(database.add_canned_message('A', sort_order=1))
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs[0]['text'] == 'A'
    assert msgs[1]['text'] == 'B'
```

- [ ] **Step 4: Esegui i test**

```bash
cd ~/Desktop/GitHub/pi-Mesh && python -m pytest tests/test_canned_db.py -v
```

Expected output:
```
tests/test_canned_db.py::test_canned_messages_empty_on_init PASSED
tests/test_canned_db.py::test_canned_messages_add_and_get PASSED
tests/test_canned_db.py::test_canned_messages_update PASSED
tests/test_canned_db.py::test_canned_messages_delete PASSED
tests/test_canned_db.py::test_canned_messages_order_by_sort_order PASSED
```

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_canned_db.py
git commit -m "feat(canned): add canned_messages table and CRUD functions"
```

---

### Task 2: Router API

**Files:**
- Create: `routers/canned_router.py`
- Modify: `main.py`

- [ ] **Step 1: Crea `routers/canned_router.py`**

```python
# routers/canned_router.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import database

router = APIRouter()


class CannedMessageCreate(BaseModel):
    text: str
    sort_order: int = 0


class CannedMessageUpdate(BaseModel):
    text: str
    sort_order: int = 0


@router.get('/api/canned-messages')
async def get_canned_messages():
    return await database.get_canned_messages()


@router.post('/api/canned-messages', status_code=201)
async def add_canned_message(body: CannedMessageCreate):
    if not body.text.strip():
        raise HTTPException(400, detail='text cannot be empty')
    msg_id = await database.add_canned_message(body.text.strip(), body.sort_order)
    return {'id': msg_id, 'text': body.text.strip(), 'sort_order': body.sort_order}


@router.put('/api/canned-messages/{msg_id}')
async def update_canned_message(msg_id: int, body: CannedMessageUpdate):
    if not body.text.strip():
        raise HTTPException(400, detail='text cannot be empty')
    await database.update_canned_message(msg_id, body.text.strip(), body.sort_order)
    return {'ok': True}


@router.delete('/api/canned-messages/{msg_id}')
async def delete_canned_message(msg_id: int):
    await database.delete_canned_message(msg_id)
    return {'ok': True}
```

- [ ] **Step 2: Registra il router in `main.py`**

Trova:
```python
from routers import nodes, map_router, log_router, commands, ws_router, messages_router, config_router, metrics_router
```

Sostituisci con:
```python
from routers import nodes, map_router, log_router, commands, ws_router, messages_router, config_router, metrics_router, canned_router
```

Trova:
```python
app.include_router(ws_router.router)
```

Aggiungi dopo:
```python
app.include_router(canned_router.router)
```

- [ ] **Step 3: Commit**

```bash
git add routers/canned_router.py main.py
git commit -m "feat(canned): add CRUD API endpoints for canned messages"
```

---

### Task 3: UI messaggi — pulsante ⚡ e modal

**Files:**
- Modify: `templates/messages.html`

- [ ] **Step 1: Aggiungi proprietà Alpine al componente messaggi**

Nel componente `x-data` principale di `messages.html`, nel blocco `data` (accanto alle altre proprietà come `messages`, `conv`, ecc.), aggiungi:

```javascript
cannedOpen: false,
cannedMessages: [],
```

Aggiungi questi metodi nel blocco `methods` (accanto a `send()`, `loadMessages()`, ecc.):

```javascript
async loadCanned() {
  const r = await fetch('/api/canned-messages')
  if (r.ok) this.cannedMessages = await r.json()
},

async sendCanned(text) {
  this.$refs.input.value = text
  this.cannedOpen = false
  await this.send()
},
```

Nel metodo `init()` esistente, aggiungi alla fine:
```javascript
await this.loadCanned()
```

- [ ] **Step 2: Aggiungi pulsante ⚡ nella barra di invio**

Trova (riga ~91):
```html
<form @submit.prevent="send()" style="display:flex;gap:4px;">
  <input x-ref="input" type="text" placeholder="Messaggio..." autocomplete="off"
```

Sostituisci con:
```html
<form @submit.prevent="send()" style="display:flex;gap:4px;">
  <button type="button" @click="cannedOpen=true"
          style="width:32px;min-height:32px;padding:0;background:none;border:1px solid var(--border);border-radius:4px;color:var(--muted);cursor:pointer;font-size:14px;flex-shrink:0;"
          title="Messaggi predefiniti">⚡</button>
  <input x-ref="input" type="text" placeholder="Messaggio..." autocomplete="off"
```

- [ ] **Step 3: Aggiungi modal canned messages**

Prima del tag `</div>` finale che chiude il blocco `x-data` principale, aggiungi:

```html
<!-- CANNED MESSAGES MODAL -->
<div x-show="cannedOpen" @click.self="cannedOpen=false"
     style="position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;display:flex;align-items:flex-end;justify-content:center;">
  <div style="background:var(--bg);border-radius:10px 10px 0 0;width:100%;max-width:480px;max-height:60vh;overflow-y:auto;padding:12px;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <span style="font-size:12px;font-weight:700;color:var(--accent);">⚡ Messaggi rapidi</span>
      <button @click="cannedOpen=false"
              style="background:none;border:none;color:var(--muted);font-size:16px;cursor:pointer;line-height:1;">✕</button>
    </div>
    <template x-if="cannedMessages.length === 0">
      <div style="color:var(--muted);font-size:11px;text-align:center;padding:16px 0;">
        Nessun messaggio predefinito. Aggiungili in Config → Canned.
      </div>
    </template>
    <template x-for="m in cannedMessages" :key="m.id">
      <div @click="sendCanned(m.text)"
           style="padding:10px 12px;border:1px solid var(--border);border-radius:6px;margin-bottom:6px;cursor:pointer;font-size:12px;color:var(--text);"
           x-text="m.text">
      </div>
    </template>
  </div>
</div>
```

- [ ] **Step 4: Commit**

```bash
git add templates/messages.html
git commit -m "feat(canned): add quick-message button and modal to messages page"
```

---

### Task 4: UI config — sezione Canned Messages

**Files:**
- Modify: `templates/config.html`

- [ ] **Step 1: Aggiungi voce "Canned" nella sidebar sections**

Trova:
```javascript
{ id: 'mqtt',     label: 'MQTT' },
```

Aggiungi dopo:
```javascript
{ id: 'canned',   label: 'Canned' },
```

- [ ] **Step 2: Aggiungi proprietà Alpine in `configPage()`**

Nella funzione `configPage()`, nel blocco `data` (con le altre proprietà come `node`, `lora`, ecc.), aggiungi:

```javascript
cannedMessages: [],
cannedNew: '',
cannedStatus: '',
```

Nel `return` dello stesso oggetto, aggiungi questi metodi:

```javascript
async loadCanned() {
  const r = await fetch('/api/canned-messages')
  if (r.ok) this.cannedMessages = await r.json()
},

async addCanned() {
  const text = this.cannedNew.trim()
  if (!text) return
  const r = await fetch('/api/canned-messages', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ text, sort_order: this.cannedMessages.length })
  })
  if (r.ok) {
    this.cannedNew = ''
    await this.loadCanned()
    this.cannedStatus = '✓ Aggiunto'
    setTimeout(() => { this.cannedStatus = '' }, 2000)
  }
},

async deleteCanned(id) {
  await fetch(`/api/canned-messages/${id}`, { method: 'DELETE' })
  await this.loadCanned()
},
```

Nella funzione `selectSection(id)` (o nell'`init()` di `configPage()`), aggiungi il caricamento quando si apre la sezione. Trova il pattern `if (this.section === 'xxx') await this.loadXxx()` e aggiungi:

```javascript
if (id === 'canned') await this.loadCanned()
```

- [ ] **Step 3: Aggiungi blocco HTML sezione Canned**

Prima dell'ultimo `</div>` che chiude il `<!-- CONTENT AREA -->`, aggiungi:

```html
<!-- CANNED MESSAGES -->
<template x-if="section === 'canned'">
  <div>
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--accent);margin-bottom:8px;">
      Messaggi rapidi
    </div>
    <div style="display:flex;gap:6px;margin-bottom:10px;">
      <input x-model="cannedNew" placeholder="Testo messaggio..."
             @keydown.enter.prevent="addCanned()"
             style="flex:1;background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:7px 8px;font-size:12px;">
      <button @click="addCanned()"
              style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:7px 12px;font-size:12px;cursor:pointer;">
        + Aggiungi
      </button>
    </div>
    <div x-show="cannedStatus" x-text="cannedStatus"
         style="font-size:10px;color:#4caf50;margin-bottom:8px;"></div>
    <template x-if="cannedMessages.length === 0">
      <div style="color:var(--muted);font-size:11px;">Nessun messaggio predefinito.</div>
    </template>
    <template x-for="m in cannedMessages" :key="m.id">
      <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid var(--border);border-radius:6px;margin-bottom:6px;">
        <span x-text="m.text" style="flex:1;font-size:12px;color:var(--text);"></span>
        <button @click="deleteCanned(m.id)"
                style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px;line-height:1;">✕</button>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 4: Commit**

```bash
git add templates/config.html
git commit -m "feat(canned): add Canned Messages section to config page"
```

---

### Task 5: Deploy e verifica su Pi

- [ ] **Step 1: Deploy**

```bash
sshpass -p pimesh rsync -avz --relative \
  database.py routers/canned_router.py main.py \
  templates/messages.html templates/config.html \
  tests/test_canned_db.py \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Verifica /config**

Apri `http://192.168.1.36:8080/config` → sidebar → "Canned" → aggiungi "CQ CQ de IU4" → verifica appare in lista.

- [ ] **Step 3: Verifica /messages**

Apri `http://192.168.1.36:8080/messages` → bottone ⚡ → modal appare con il messaggio → tap → messaggio inviato nel canale corrente → modal chiuso.

- [ ] **Step 4: Commit finale**

```bash
git add -A
git commit -m "feat: M7 complete — canned messages (YAY-168)"
```
