# YAY-145 Pannello Messaggi Bugfix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fixare due bug nel pannello messaggi: informazioni nodo mancanti nei messaggi e scroll infinito rotto.

**Architecture:** Fix in-place su messages.html (Alpine.js reactive node lookup), app.js (toast con nome nodo), e IntersectionObserver (debounce + guard).

**Tech Stack:** Alpine.js, JavaScript, CSS

---

## File Structure

| File | Responsabilità |
|------|---------------|
| `templates/messages.html` | Fix node info display + infinite scroll |
| `static/app.js` | Fix toast notification con nome nodo |

---

### Task 1: Fix informazioni nodo nei messaggi

**Files:**
- Modify: `templates/messages.html`
- Modify: `static/app.js`

**Bug:** Il nome del nodo nei messaggi usa `window.nodeCache?.get(msg.node_id)?.short_name` che viene valutato una sola volta da Alpine.js. Se il nodeCache non è ancora popolato al momento del render, mostra il raw node_id e non si aggiorna mai.

- [ ] **Step 1: Aggiungere metodo helper per risolvere nome nodo in messages.html**

Nel blocco Alpine.js `messagesPage()`, dopo il getter `convTitle`, aggiungere un metodo:

```javascript
    nodeName(nodeId) {
      return window.nodeCache?.get(nodeId)?.short_name || nodeId
    },
```

- [ ] **Step 2: Usare il metodo nel template messaggi**

In messages.html, trovare la riga con il display del nome nodo (circa riga 70):

```html
<span x-text="(window.nodeCache?.get(msg.node_id)?.short_name || msg.node_id) + ' \xb7 '"></span>
```

Sostituire con:

```html
<span x-text="nodeName(msg.node_id) + ' \xb7 '"></span>
```

Questo non risolve la reattività di per sé (Alpine non re-renderizza su window.nodeCache changes), ma centralizza il lookup. Per la vera reattività, aggiungere un listener che forza il re-render quando arrivano nuovi nodi.

- [ ] **Step 3: Aggiungere ws-init listener per aggiornare messaggi con nomi nodo**

Nell'`init()` di messagesPage, dopo i listener `message-new` e `msg-ack`, aggiungere:

```javascript
      this._onNodeUpdate = () => {
        // Force Alpine to re-evaluate node names by triggering a shallow copy
        this.messages = [...this.messages]
      }
      window.addEventListener('ws-init', this._onNodeUpdate)
```

E nel `destroy()`, aggiungere:

```javascript
      window.removeEventListener('ws-init', this._onNodeUpdate)
```

Nota: usiamo `ws-init` (che arriva dopo il caricamento dei nodi dal DB) piuttosto che `node-update` (troppo frequente). Così al primo connect WS, i nomi si aggiornano.

- [ ] **Step 4: Fix toast notifica con nome nodo in app.js**

In `static/app.js`, nella funzione `handleMessage(msg)` (circa riga 137-138), trovare:

```javascript
  const prefix = (msg.destination && msg.destination !== '^all') ? 'DM ' : 'MSG '
  if (typeof showToast === 'function') showToast(prefix + (msg.node_id || '') + ': ' + (msg.text || '').slice(0, 30))
```

Sostituire con:

```javascript
  const prefix = (msg.destination && msg.destination !== '^all') ? 'DM ' : ''
  const sender = nodeCache.get(msg.node_id)?.short_name || msg.node_id
  if (typeof showToast === 'function') showToast(prefix + sender + ': ' + (msg.text || '').slice(0, 30))
```

- [ ] **Step 5: Commit**

```bash
git add templates/messages.html static/app.js
git commit -m "fix(messages): show node name instead of raw ID in messages and toasts (YAY-145)"
```

---

### Task 2: Fix infinite scroll

**Files:**
- Modify: `templates/messages.html`

**Bug:** Il sentinel IntersectionObserver al top della lista può triggerare ripetutamente:
1. Al primo caricamento, se i messaggi non riempiono il container, il sentinel è visibile → loadMore() parte subito → loop
2. Dopo Alpine re-render dell'array `messages`, il sentinel può diventare momentaneamente visibile → trigger spurio

- [ ] **Step 1: Aggiungere debounce e guard al loadMore**

In messages.html, modificare la funzione `loadMore()`. Trovare:

```javascript
    async loadMore() {
      if (this.loading || !this.hasMore || !this.messages.length) return
      const beforeId = this.messages[0].id
      this.loading = true
```

Sostituire con:

```javascript
    async loadMore() {
      if (this.loading || !this.hasMore || !this.messages.length) return
      if (this._loadMoreCooldown) return
      this._loadMoreCooldown = true
      setTimeout(() => { this._loadMoreCooldown = false }, 500)
      const beforeId = this.messages[0].id
      this.loading = true
```

- [ ] **Step 2: Disconnettere observer quando hasMore è false**

Alla fine di `loadMore()`, dopo `this.hasMore = data.length === 50`, aggiungere:

```javascript
        if (!this.hasMore && this._observer) {
          this._observer.disconnect()
        }
```

- [ ] **Step 3: Ritardare l'attivazione dell'observer dopo il primo caricamento**

Nell'`init()`, modificare il setup dell'IntersectionObserver. Trovare:

```javascript
      this._observer = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) this.loadMore()
      })
      this.$nextTick(() => {
        if (this.$refs.sentinel) this._observer.observe(this.$refs.sentinel)
      })
```

Sostituire con:

```javascript
      this._observer = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) this.loadMore()
      })
      // Delay observer activation to avoid triggering before initial messages render
      setTimeout(() => {
        if (this.$refs.sentinel) this._observer.observe(this.$refs.sentinel)
      }, 500)
```

- [ ] **Step 4: Commit**

```bash
git add templates/messages.html
git commit -m "fix(messages): prevent infinite scroll loop with debounce and delayed observer (YAY-145)"
```

---

### Task 3: Deploy e test

**Files:** Nessun file da modificare

- [ ] **Step 1: Deploy sul Pi**

```bash
sshpass -p pimesh rsync -avz --relative \
  templates/messages.html static/app.js \
  pimesh@192.168.1.36:~/pi-Mesh/

sshpass -p pimesh ssh pimesh@192.168.1.36 "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Verificare con Playwright**

- Navigare a `http://192.168.1.36:8080/messages`
- Verificare che la pagina carica senza loop (no console spam di fetch)
- Verificare layout portrait (320x480) e landscape (480x320)
- Se ci sono messaggi, verificare che il nome nodo appare correttamente

- [ ] **Step 3: Commit finale se necessario**
