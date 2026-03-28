# YAY-106 — DM Thread View: Design Spec

**Data:** 2026-03-28
**Issue:** [YAY-106](https://linear.app/yayoboy/issue/YAY-106/messaggi-view-messaggi-diretti-dm)
**Stato:** Approvato — pronto per implementazione

---

## Problema

I messaggi diretti (DM) e broadcast sono mescolati nella stessa lista senza distinzione visiva. Non esiste un thread conversazione per nodo. Non è possibile inviare un DM direttamente dalla lista nodi.

---

## Decisioni di Design

| Domanda | Scelta |
|---------|--------|
| Layout navigazione messaggi | Sidebar conversazioni (stile chat) |
| Avviare DM dalla lista nodi | Menu contestuale `···` su ogni riga nodo |
| Menu contestuale | Mostra info nodo + azioni (DM, posizione, elimina) |
| Icone | SVG Heroicons — nessuna emoji |

---

## 1. Database

### Migrazione

Aggiungere colonna `destination` alla tabella `messages`:

```sql
ALTER TABLE messages ADD COLUMN destination TEXT DEFAULT '^all';
ALTER TABLE messages ADD COLUMN read_at INTEGER DEFAULT NULL;
```

- `destination = '^all'` → messaggio broadcast
- `destination = '!a3f21b04'` → DM verso nodo con quell'ID
- `read_at` → timestamp Unix quando il thread è stato aperto (NULL = non letto)

La migrazione viene applicata all'avvio tramite `database.py` con controllo `PRAGMA table_info`.

### Nuove query

**`get_dm_threads(conn)`**
Restituisce lista thread DM con ultimo messaggio e conteggio unread:
```sql
SELECT
  CASE WHEN is_outgoing=1 THEN destination ELSE node_id END AS peer,
  text, timestamp, is_outgoing,
  SUM(CASE WHEN read_at IS NULL AND is_outgoing=0 THEN 1 ELSE 0 END) AS unread_count
FROM messages
WHERE destination != '^all'
GROUP BY peer
ORDER BY timestamp DESC
```

**`get_dm_messages(conn, peer_id, limit, before_id)`**
Messaggi del thread con un nodo specifico:
```sql
SELECT * FROM messages
WHERE (node_id = ? AND is_outgoing = 0) OR (destination = ? AND is_outgoing = 1)
ORDER BY timestamp DESC LIMIT ?
```

**`mark_dm_read(conn, peer_id)`**
Marca tutti i messaggi non letti del thread come letti:
```sql
UPDATE messages SET read_at = ?
WHERE node_id = ? AND is_outgoing = 0 AND read_at IS NULL
```

---

## 2. Backend

### meshtastic_client.py

`_parse_message()` — aggiungere estrazione `destination`:
```python
"destination": packet.get("toId", "^all"),
```

`save_message()` — aggiungere parametro `destination` (default `'^all'`).

### database.py

Aggiungere: `get_dm_threads()`, `get_dm_messages()`, `mark_dm_read()`.
Modificare: `save_message()` per includere `destination`.
Aggiungere migrazione automatica per `destination` e `read_at`.

### main.py

Nuovi endpoint REST:

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET` | `/api/dm/threads` | Lista thread DM con unread count |
| `GET` | `/api/dm/messages` | Messaggi di un thread (`?peer=!abc123`) |
| `POST` | `/api/dm/read` | Marca thread letto (`?peer=!abc123`) |

Modifiche esistenti:
- `POST /send` — il campo `destination` già presente; aggiungere salvataggio nel DB con il valore corretto.

### WebSocket

Nuovo evento broadcast inviato ai client quando arriva un DM:
```json
{ "type": "dm_thread_update", "data": { "peer": "!a3f21b04", "unread_count": 3 } }
```

Evento inviato da `_handle_message()` quando `destination != '^all'`.

---

## 3. Frontend

### messages.html — Ristrutturazione layout

Layout a due colonne:

```
┌──────────────┬──────────────────────────────────┐
│ Conversazioni│ Thread attivo                    │
│              │                                  │
│ > Broadcast  │ [Header: nome + info]            │
│ ─────────    │                                  │
│ Diretti      │ [Messaggi scrollabili]           │
│  Node-Beta 3 │                                  │
│  Node-Alpha  │ [Input invio]                    │
│  Node-Gamma  │                                  │
└──────────────┴──────────────────────────────────┘
```

- Sidebar: larghezza fissa ~130px, scroll se molti nodi
- Thread: flex-grow, scroll verticale messaggi
- Broadcast in cima alla sidebar, sezione "Diretti" sotto separatore
- Badge unread rosso su ogni voce DM con messaggi non letti
- Click voce sidebar → carica thread, chiama `POST /api/dm/read`

### app.js — Modifiche

**Nuovo handler WebSocket:**
```javascript
dm_thread_update: handleDmThreadUpdate
```
Aggiorna badge unread nella sidebar senza ricaricare la pagina.

**`loadDmThread(peerId)`** — carica messaggi via `GET /api/dm/messages?peer=peerId`, renderizza nel pannello destro, imposta destinatario nel form invio.

**`loadDmThreads()`** — popola sidebar con lista da `GET /api/dm/threads`.

**`sendMsg()`** — già legge `destination` dal `dest-select`; assicurarsi che sia valorizzato con `peerId` quando si è in un thread DM.

### nodes.html — Menu contestuale

Aggiungere icona `···` (tre cerchi SVG Heroicons) su ogni riga nodo.

Click apre pannello inline sotto la riga con:

**Sezione info nodo** (grid 2 colonne):
- ID, nome lungo, hardware, firmware
- Batteria, SNR, RSSI, hop count, ultimo visto, lat/lon (se disponibili)

**Sezione azioni:**
- "Invia DM" (con badge unread se presenti) → naviga a `/messages` con `?open_dm=!nodeId`
- "Richiedi posizione"
- "Elimina nodo" (rosso, con conferma)

La pagina messaggi legge il parametro `open_dm` all'avvio e pre-seleziona il thread corretto.

---

## 4. Flusso Completo

### Ricezione DM
1. Nodo remoto invia pacchetto con `toId = '!localId'`
2. `_parse_message()` estrae `destination = '!localId'`
3. `save_message()` salva con `destination` valorizzato
4. Backend broadcast `dm_thread_update` via WebSocket
5. Frontend aggiorna badge nella sidebar in real-time

### Invio DM
1. Utente clicca `···` su nodo → "Invia DM" → naviga a messaggi con `?open_dm=!nodeId`
2. Sidebar pre-seleziona thread DM del nodo
3. Input invio ha destinatario impostato a `!nodeId`
4. Invio → `POST /send` con `destination: '!nodeId'`
5. Backend salva e invia sulla rete Meshtastic

### Lettura DM
1. Utente clicca thread in sidebar
2. Frontend chiama `POST /api/dm/read?peer=!nodeId`
3. Badge scompare; `read_at` aggiornato nel DB

---

## 5. Fuori Scope

- Notifiche push / suoni per nuovi DM
- Cifratura end-to-end a livello applicativo (gestita da Meshtastic)
- Supporto multi-canale per DM (Meshtastic usa canale 0 per DM)
- Ricerca messaggi nel thread
