# YAY-107 Nodi Campi Avanzati — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere campi avanzati ai nodi: RSSI, firmware version, role, public key, altitudine — dal pacchetto Meshtastic fino alla UI.

**Architecture:** Migration DB (5 nuove colonne), cattura campi in meshtasticd_client.py (_refresh_node_cache + _on_receive NODEINFO_APP/POSITION_APP), update database.py upsert, display in nodes.html expanded detail.

**Tech Stack:** Python 3.11, FastAPI, aiosqlite, Alpine.js, Meshtastic Python

---

## File Structure

| File | Responsabilità |
|------|---------------|
| `database.py` | Schema migration + upsert con 5 nuove colonne |
| `meshtasticd_client.py` | Cattura rssi/firmware/role/publicKey/altitude da pacchetti |
| `templates/nodes.html` | Display campi avanzati nella card espansa |

---

### Task 1: DB schema migration — aggiungere 5 colonne

**Files:**
- Modify: `database.py`

- [ ] **Step 1: Aggiungere colonne allo schema `_SCHEMA`**

In `database.py`, nella definizione `_SCHEMA`, trovare la tabella nodes e aggiungere le nuove colonne. Trovare:

```python
    hw_model TEXT,
    is_local INTEGER DEFAULT 0,
    raw_json TEXT,
    distance_km REAL
);
```

Sostituire con:

```python
    hw_model TEXT,
    is_local INTEGER DEFAULT 0,
    raw_json TEXT,
    distance_km REAL,
    rssi INTEGER,
    firmware_version TEXT,
    role TEXT,
    public_key TEXT,
    altitude REAL
);
```

- [ ] **Step 2: Aggiungere migration per colonne mancanti in `init()`**

In `database.py`, nella funzione `init()`, dopo il blocco migration `distance_km`, aggiungere:

```python
        # Migrate nodes table: add advanced fields (M5 — YAY-107)
        for col, col_type in [
            ('rssi', 'INTEGER'),
            ('firmware_version', 'TEXT'),
            ('role', 'TEXT'),
            ('public_key', 'TEXT'),
            ('altitude', 'REAL'),
        ]:
            if col not in node_cols:
                logger.info('Migrating nodes table: adding %s column', col)
                await db.execute(f'ALTER TABLE nodes ADD COLUMN {col} {col_type}')
```

Questo va subito dopo:

```python
        if node_cols and 'distance_km' not in node_cols:
            logger.info('Migrating nodes table: adding distance_km column')
            await db.execute('ALTER TABLE nodes ADD COLUMN distance_km REAL')
```

- [ ] **Step 3: Aggiornare `upsert_node()` con le nuove colonne**

Trovare l'intera query in `upsert_node()`:

```python
        await db.execute("""
            INSERT INTO nodes (id, short_name, long_name, latitude, longitude,
                last_heard, snr, battery_level, hop_count, hw_model, is_local, raw_json,
                distance_km)
            VALUES (:id, :short_name, :long_name, :latitude, :longitude,
                :last_heard, :snr, :battery_level, :hop_count, :hw_model, :is_local, :raw_json,
                :distance_km)
            ON CONFLICT(id) DO UPDATE SET
                short_name=excluded.short_name, long_name=excluded.long_name,
                latitude=excluded.latitude, longitude=excluded.longitude,
                last_heard=excluded.last_heard, snr=excluded.snr,
                battery_level=excluded.battery_level, hop_count=excluded.hop_count,
                hw_model=excluded.hw_model, is_local=excluded.is_local,
                raw_json=excluded.raw_json,
                distance_km=excluded.distance_km
        """, node)
```

Sostituire con:

```python
        await db.execute("""
            INSERT INTO nodes (id, short_name, long_name, latitude, longitude,
                last_heard, snr, battery_level, hop_count, hw_model, is_local, raw_json,
                distance_km, rssi, firmware_version, role, public_key, altitude)
            VALUES (:id, :short_name, :long_name, :latitude, :longitude,
                :last_heard, :snr, :battery_level, :hop_count, :hw_model, :is_local, :raw_json,
                :distance_km, :rssi, :firmware_version, :role, :public_key, :altitude)
            ON CONFLICT(id) DO UPDATE SET
                short_name=excluded.short_name, long_name=excluded.long_name,
                latitude=excluded.latitude, longitude=excluded.longitude,
                last_heard=excluded.last_heard, snr=excluded.snr,
                battery_level=excluded.battery_level, hop_count=excluded.hop_count,
                hw_model=excluded.hw_model, is_local=excluded.is_local,
                raw_json=excluded.raw_json,
                distance_km=excluded.distance_km,
                rssi=excluded.rssi,
                firmware_version=excluded.firmware_version,
                role=excluded.role,
                public_key=excluded.public_key,
                altitude=excluded.altitude
        """, node)
```

- [ ] **Step 4: Aggiornare `bulk_upsert_nodes()` con le nuove colonne**

Trovare l'intera query in `bulk_upsert_nodes()`:

```python
            await db.execute(
                '''INSERT INTO nodes
                   (id, short_name, long_name, latitude, longitude,
                    last_heard, snr, battery_level, hop_count, hw_model,
                    is_local, raw_json, distance_km)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     short_name=excluded.short_name,
                     long_name=excluded.long_name,
                     latitude=excluded.latitude,
                     longitude=excluded.longitude,
                     last_heard=excluded.last_heard,
                     snr=excluded.snr,
                     battery_level=excluded.battery_level,
                     hop_count=excluded.hop_count,
                     hw_model=excluded.hw_model,
                     is_local=excluded.is_local,
                     raw_json=excluded.raw_json,
                     distance_km=excluded.distance_km''',
                (
                    node.get('id'), node.get('short_name'), node.get('long_name'),
                    node.get('latitude'), node.get('longitude'),
                    node.get('last_heard'), node.get('snr'),
                    node.get('battery_level'), node.get('hop_count'),
                    node.get('hw_model'), node.get('is_local'),
                    node.get('raw_json'), node.get('distance_km'),
                )
            )
```

Sostituire con:

```python
            await db.execute(
                '''INSERT INTO nodes
                   (id, short_name, long_name, latitude, longitude,
                    last_heard, snr, battery_level, hop_count, hw_model,
                    is_local, raw_json, distance_km,
                    rssi, firmware_version, role, public_key, altitude)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     short_name=excluded.short_name,
                     long_name=excluded.long_name,
                     latitude=excluded.latitude,
                     longitude=excluded.longitude,
                     last_heard=excluded.last_heard,
                     snr=excluded.snr,
                     battery_level=excluded.battery_level,
                     hop_count=excluded.hop_count,
                     hw_model=excluded.hw_model,
                     is_local=excluded.is_local,
                     raw_json=excluded.raw_json,
                     distance_km=excluded.distance_km,
                     rssi=excluded.rssi,
                     firmware_version=excluded.firmware_version,
                     role=excluded.role,
                     public_key=excluded.public_key,
                     altitude=excluded.altitude''',
                (
                    node.get('id'), node.get('short_name'), node.get('long_name'),
                    node.get('latitude'), node.get('longitude'),
                    node.get('last_heard'), node.get('snr'),
                    node.get('battery_level'), node.get('hop_count'),
                    node.get('hw_model'), node.get('is_local'),
                    node.get('raw_json'), node.get('distance_km'),
                    node.get('rssi'), node.get('firmware_version'),
                    node.get('role'), node.get('public_key'),
                    node.get('altitude'),
                )
            )
```

- [ ] **Step 5: Commit**

```bash
git add database.py
git commit -m "feat(db): add rssi, firmware_version, role, public_key, altitude columns to nodes (YAY-107)"
```

---

### Task 2: Cattura campi avanzati in meshtasticd_client.py

**Files:**
- Modify: `meshtasticd_client.py`

- [ ] **Step 1: Aggiornare `_refresh_node_cache()` per catturare i nuovi campi**

In `meshtasticd_client.py`, nella funzione `_refresh_node_cache()`, trovare il blocco che costruisce il dict del nodo:

```python
            _node_cache[node_id] = {
                'id':            user.get('id', node_id),
                'short_name':    user.get('shortName', ''),
                'long_name':     user.get('longName', ''),
                'hw_model':      user.get('hwModel', ''),
                'latitude':      pos.get('latitude'),
                'longitude':     pos.get('longitude'),
                'last_heard':    info.get('lastHeard'),
                'snr':           info.get('snr'),
                'hop_count':     info.get('hopsAway'),
                'battery_level': metrics.get('batteryLevel'),
                'is_local':      node_id == _local_id,
                'raw_json':      str(info),
                'distance_km':   None,
            }
```

Sostituire con:

```python
            _node_cache[node_id] = {
                'id':               user.get('id', node_id),
                'short_name':       user.get('shortName', ''),
                'long_name':        user.get('longName', ''),
                'hw_model':         user.get('hwModel', ''),
                'latitude':         pos.get('latitude'),
                'longitude':        pos.get('longitude'),
                'last_heard':       info.get('lastHeard'),
                'snr':              info.get('snr'),
                'hop_count':        info.get('hopsAway'),
                'battery_level':    metrics.get('batteryLevel'),
                'is_local':         node_id == _local_id,
                'raw_json':         str(info),
                'distance_km':      None,
                'rssi':             info.get('rxRssi'),
                'firmware_version': user.get('firmwareVersion'),
                'role':             user.get('role'),
                'public_key':       user.get('publicKey'),
                'altitude':         pos.get('altitude'),
            }
```

- [ ] **Step 2: Aggiornare evento `NODEINFO_APP` in `_on_receive()` con firmware/role/publicKey**

In `_on_receive()`, trovare il blocco NODEINFO_APP:

```python
    if portnum == 'NODEINFO_APP':
        user = decoded.get('user', {})
        typed_event = {
            'type':          'node',
            'id':            from_id,
            'short_name':    user.get('shortName', ''),
            'long_name':     user.get('longName', ''),
            'hw_model':      user.get('hwModel', ''),
            'last_heard':    int(time.time()),
            'snr':           snr,
            'hop_count':     hop_limit,
            'battery_level': None,
            'latitude':      None,
            'longitude':     None,
            'is_local':      False,
            'distance_km':   None,
        }
```

Sostituire con:

```python
    if portnum == 'NODEINFO_APP':
        user = decoded.get('user', {})
        typed_event = {
            'type':             'node',
            'id':               from_id,
            'short_name':       user.get('shortName', ''),
            'long_name':        user.get('longName', ''),
            'hw_model':         user.get('hwModel', ''),
            'last_heard':       int(time.time()),
            'snr':              snr,
            'hop_count':        hop_limit,
            'battery_level':    None,
            'latitude':         None,
            'longitude':        None,
            'is_local':         False,
            'distance_km':      None,
            'rssi':             packet.get('rxRssi'),
            'firmware_version': user.get('firmwareVersion'),
            'role':             user.get('role'),
            'public_key':       user.get('publicKey'),
            'altitude':         None,
        }
```

- [ ] **Step 3: Aggiornare evento `POSITION_APP` in `_on_receive()` con altitude e rssi**

In `_on_receive()`, trovare il blocco POSITION_APP:

```python
    elif portnum == 'POSITION_APP':
        pos = decoded.get('position', {})
        typed_event = {
            'type':       'position',
            'id':         from_id,
            'latitude':   pos.get('latitude'),
            'longitude':  pos.get('longitude'),
            'last_heard': int(time.time()),
        }
```

Sostituire con:

```python
    elif portnum == 'POSITION_APP':
        pos = decoded.get('position', {})
        typed_event = {
            'type':       'position',
            'id':         from_id,
            'latitude':   pos.get('latitude'),
            'longitude':  pos.get('longitude'),
            'altitude':   pos.get('altitude'),
            'last_heard': int(time.time()),
        }
```

- [ ] **Step 4: Aggiornare `_on_receive()` per salvare rssi nella node_cache su ogni pacchetto**

In `_on_receive()`, subito prima del commento `# Refresh node cache on any packet`, aggiungere la cattura rssi nel nodo cache. Trovare:

```python
    # Refresh node cache on any packet
    if _connected and _interface:
        _refresh_node_cache()
```

Sostituire con:

```python
    # Update rssi in node cache from incoming packet
    rx_rssi = packet.get('rxRssi')
    if rx_rssi is not None and from_id in _node_cache:
        _node_cache[from_id]['rssi'] = rx_rssi
        _dirty_nodes.add(from_id)

    # Refresh node cache on any packet
    if _connected and _interface:
        _refresh_node_cache()
```

- [ ] **Step 5: Commit**

```bash
git add meshtasticd_client.py
git commit -m "feat(client): capture rssi, firmware, role, publicKey, altitude from packets (YAY-107)"
```

---

### Task 3: Display campi avanzati in nodes.html

**Files:**
- Modify: `templates/nodes.html`

- [ ] **Step 1: Aggiungere riga stat RSSI + Altitude nella card espansa portrait**

In `templates/nodes.html`, nella sezione portrait expanded detail, dopo la prima `stat-grid` (quella con Hops/SNR/Batt/Dist), aggiungere una seconda riga. Trovare:

```html
            <div class="mt-2" style="font-size:9px;color:var(--muted);" x-text="node.id"></div>
```

(dentro la sezione `.node-detail`) e sostituire con:

```html
            <div class="stat-grid mt-2">
              <div class="stat-box">
                <div class="stat-val" x-text="node.rssi != null ? node.rssi + ' dBm' : '—'"></div>
                <div class="stat-lbl">RSSI</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" x-text="node.altitude != null ? Math.round(node.altitude) + 'm' : '—'"></div>
                <div class="stat-lbl">Alt</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:10px;" x-text="node.role || '—'"></div>
                <div class="stat-lbl">Ruolo</div>
              </div>
              <div class="stat-box">
                <div class="stat-val" style="font-size:10px;" x-text="node.firmware_version || '—'"></div>
                <div class="stat-lbl">FW</div>
              </div>
            </div>

            <div class="mt-2" style="font-size:9px;color:var(--muted);" x-text="node.id"></div>
```

- [ ] **Step 2: Aggiungere riga stat RSSI + Altitude nella detail panel landscape**

In `templates/nodes.html`, nella sezione landscape detail panel, dopo la `stat-grid mb-3` (quella con Hops/SNR/Batt/Dist), aggiungere. Trovare:

```html
          <!-- Node ID -->
          <div style="font-size:9px;color:var(--muted);margin-bottom:10px;" x-text="selectedNode.id"></div>
```

Sostituire con:

```html
          <!-- Advanced stats -->
          <div class="stat-grid mb-3">
            <div class="stat-box">
              <div class="stat-val" x-text="selectedNode.rssi != null ? selectedNode.rssi + ' dBm' : '—'"></div>
              <div class="stat-lbl">RSSI</div>
            </div>
            <div class="stat-box">
              <div class="stat-val" x-text="selectedNode.altitude != null ? Math.round(selectedNode.altitude) + 'm' : '—'"></div>
              <div class="stat-lbl">Alt</div>
            </div>
            <div class="stat-box">
              <div class="stat-val" style="font-size:10px;" x-text="selectedNode.role || '—'"></div>
              <div class="stat-lbl">Ruolo</div>
            </div>
            <div class="stat-box">
              <div class="stat-val" style="font-size:10px;" x-text="selectedNode.firmware_version || '—'"></div>
              <div class="stat-lbl">FW</div>
            </div>
          </div>

          <!-- Node ID -->
          <div style="font-size:9px;color:var(--muted);margin-bottom:10px;" x-text="selectedNode.id"></div>
```

- [ ] **Step 3: Aggiornare il WS handler `node-update` per merge dei nuovi campi**

Il handler `_nodeUpdateHandler` in `init()` già usa `Object.assign()` che copierà automaticamente i nuovi campi. Nessuna modifica necessaria — verificare solo che il merge funziona.

Il `fetchNodes()` chiama `/api/nodes` che fa `SELECT *` e quindi restituisce automaticamente le nuove colonne. Nessuna modifica necessaria.

- [ ] **Step 4: Aggiornare position-update handler per altitude**

In `nodes.html`, nella funzione `init()`, il nodo viene aggiornato via `node-update` events. Per posizioni, `app.js` dispatcha `position-update`. Verificare che `app.js` propaga il campo `altitude` nell'evento position. Se `app.js` già passa tutti i campi del messaggio WS al `CustomEvent`, altitude arriva automaticamente.

Nessuna modifica necessaria se `app.js` usa spread operator nel dispatch dell'evento position.

- [ ] **Step 5: Commit**

```bash
git add templates/nodes.html
git commit -m "feat(nodes): display RSSI, altitude, role, firmware in expanded card (YAY-107)"
```

---

### Task 4: Deploy e test

**Files:** Nessun file da modificare

- [ ] **Step 1: Deploy sul Pi**

```bash
sshpass -p pimesh rsync -avz --relative \
  database.py meshtasticd_client.py templates/nodes.html \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Attendere avvio servizio e verificare migration DB**

```bash
sleep 20
sshpass -p pimesh ssh pimesh@192.168.1.36 "sqlite3 ~/pi-Mesh/data/mesh.db '.schema nodes'"
```

Verificare che la tabella nodes contiene le colonne: rssi, firmware_version, role, public_key, altitude.

- [ ] **Step 3: Verificare con Playwright**

- Navigare a `http://192.168.1.36:8080/nodes`
- Screenshot a 320x480 (portrait) e 480x320 (landscape)
- Espandere un nodo e verificare che le nuove stat box RSSI/Alt/Ruolo/FW sono visibili
- Verificare che i valori mostrano dati reali o '—' per campi non ancora ricevuti

- [ ] **Step 4: Commit finale se necessario**
