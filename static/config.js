// static/config.js — logica Alpine della pagina Config (templates/config.html).
//
// Espone window.configPage(): stato + metodi per le 28 sezioni della sidebar
// (gruppi Board / Pi / UI, definiti in `groups`). Pattern per sezione:
//   selectSection(id)  → lazy-load della sezione al primo click
//   loadX()            → GET dell'endpoint corrispondente
//   saveX()/saveModule(endpoint, oggetto) → POST + esito in `moduleStatus`
// I form delle sezioni module/device sono generati dalle macro Jinja in
// templates/_forms.html; i nomi dei campi combaciano coi modelli Pydantic
// dei router (module_config_router, device_config_router).
//
function configPage() {
  return {
    section: 'node',
    openGroup: 'board',
    groups: [
      { id: 'board', label: 'Board', sections: [
        { id: 'node', label: 'Nodo' }, { id: 'lora', label: 'LoRa' }, { id: 'channels', label: 'Canali' },
        { id: 'position', label: 'Posizione' }, { id: 'power', label: 'Power' },
        { id: 'devdisplay', label: 'Schermo' }, { id: 'network', label: 'Rete' },
        { id: 'bluetooth', label: 'Bluetooth' }, { id: 'security', label: 'Sicurezza' },
        { id: 'mqtt', label: 'MQTT' }, { id: 'alert', label: 'Alert' },
        { id: 'extnotif', label: 'ExtNotif' }, { id: 'sf', label: 'S&F' }, { id: 'telmod', label: 'Telemetry' },
        { id: 'cannedmod', label: 'CannedMod' }, { id: 'rangetest', label: 'RangeTest' },
        { id: 'detsensor', label: 'DetSensor' }, { id: 'ambilight', label: 'AmbLight' },
        { id: 'neighinfo', label: 'Neighbor' }, { id: 'serial', label: 'Serial' },
        { id: 'audio', label: 'Audio' }, { id: 'paxcounter', label: 'Paxcounter' },
        { id: 'remotehw', label: 'RemoteHW' },
      ]},
      { id: 'pi', label: 'Pi', sections: [
        { id: 'gpio', label: 'GPIO' }, { id: 'rtc', label: 'RTC' }, { id: 'usb', label: 'USB' },
        { id: 'wifi', label: 'WiFi' }, { id: 'display', label: 'Display' },
      ]},
      { id: 'ui', label: 'UI', sections: [
        { id: 'theme', label: 'Tema' }, { id: 'mappa', label: 'Mappa' }, { id: 'canned', label: 'Canned' },
      ]},
    ],

    node: { long_name: '', short_name: '', role: 'CLIENT', cached: true },
    serialPort: '',
    serialPorts: [],
    factoryModal: false,
    lora: { region: 'EU_868', modem_preset: 'LONG_FAST', cached: true },
    channels: [],
    channelsCached: true,
    mappa: { local_tiles: false, region: 'italia', tiles_present: false, cached: false, saving: false },
    usb: { connected: false, devices: [], tiles_location: 'sd', loading: false, moving: false },
    display: { brightness: 255, rotation: 0, saving: false, savingRotation: false, status: '', rotationStatus: '' },
    alert: { node_offline_min: 30, battery_low: 20, ram_high: 85, saving: false },
    mqtt: { enabled: false, address: 'mqtt.meshtastic.org', username: 'meshdev', password: 'large4cats',
            encryption_enabled: false, json_enabled: false, tls_enabled: false, root: 'msh',
            proxy_to_client_enabled: false, map_reporting_enabled: false, cached: true },
    mqttStatus: { available: false, connected: false, broker: '', enabled: false },
    mqttSaving: false,
    cannedMessages: [],
    cannedNew: '',
    cannedStatus: '',
    extNotif: {}, storeForward: {}, telMod: {}, cannedMod: {},
    rangeTest: {}, detSensor: {}, ambLight: {}, neighInfo: {}, serialMod: {},
    devPosition: {}, devPower: {}, devDisplay: {}, devNetwork: {},
    devBluetooth: {}, devSecurity: {},
    audioMod: {}, paxMod: {}, remoteHw: {},
    moduleStatus: '',
    // Condivisione canali (URL/QR meshtastic.org/e/#)
    chUrl: '', chImportUrl: '', chAddOnly: false, chQrVisible: false,
    // Config remota: 'local' oppure id nodo (!aabbccdd). Le sezioni board
    // remote-capable vengono lette/scritte via /api/admin/{id}/config/{sez}.
    target: 'local', targetNodes: [],

    loaded: { node: false, lora: false, channels: false },
    saving: { node: false, lora: false, channels: false },
    status: { node: '', lora: '', channels: '', gpio: '', wifi: '', mqtt: '', serial: '' },

    async init() {
      await this.loadNode()
      await this.scanSerialPorts()
      await this.loadTargets()
    },

    async selectSection(s, groupId) {
      this.section = s
      if (groupId) this.openGroup = groupId
      if (s === 'node'     && !this.loaded.node)     await this.loadNode()
      if (s === 'lora'     && !this.loaded.lora)     await this.loadLora()
      if (s === 'channels' && !this.loaded.channels) await this.loadChannels()
      if (s === 'gpio')                                   await this.loadGpio()
      if (s === 'rtc')                                    await this.loadRtc()
      if (s === 'mappa')                                  await this.loadMappa()
      if (s === 'usb')                                    await this.loadUsb()
      if (s === 'display')                                await this.loadDisplay()
      if (s === 'alert') await this.loadAlert()
      if (s === 'mqtt') { await this.loadMqtt(); await this.loadMqttStatus() }
      if (s === 'canned') await this.loadCanned()
      if (s === 'extnotif')  await this.loadExtNotif()
      if (s === 'sf')        await this.loadStoreForward()
      if (s === 'telmod')    await this.loadTelMod()
      if (s === 'cannedmod') await this.loadCannedMod()
      if (s === 'rangetest') await this.loadRangeTest()
      if (s === 'detsensor') await this.loadDetSensor()
      if (s === 'ambilight') await this.loadAmbLight()
      if (s === 'neighinfo') await this.loadNeighInfo()
      if (s === 'serial')    await this.loadSerialMod()
      if (s === 'position')  await this.loadDevSection('position', 'devPosition')
      if (s === 'power')     await this.loadDevSection('power', 'devPower')
      if (s === 'devdisplay') await this.loadDevSection('display', 'devDisplay')
      if (s === 'network')   await this.loadDevSection('network', 'devNetwork')
      if (s === 'bluetooth') await this.loadDevSection('bluetooth', 'devBluetooth')
      if (s === 'security')  await this.loadDevSection('security', 'devSecurity')
      if (s === 'audio')     await this.loadModSection('/api/config/module/audio', 'audioMod')
      if (s === 'paxcounter') await this.loadModSection('/api/config/module/paxcounter', 'paxMod')
      if (s === 'remotehw')  await this.loadModSection('/api/config/module/remote-hardware', 'remoteHw')
      if (s === 'channels' && !this.channelsCached) await this.loadChannelUrl()
    },

    async loadModSection(endpoint, prop) {
      if (this.target !== 'local') this.moduleStatus = '⏳ lettura dal nodo remoto…'
      const r = await fetch(this.cfgEndpoint(endpoint))
      if (r.ok) this[prop] = await r.json()
      if (this.target !== 'local') this.moduleStatus = r.ok ? '' : '✗ nodo non raggiungibile'
    },

    // endpoint locale → nome sezione protobuf per la config remota
    _remoteSections: {
      '/api/config/lora': 'lora',
      '/api/config/mqtt': 'mqtt',
      '/api/config/device/position': 'position',
      '/api/config/device/power': 'power',
      '/api/config/device/display': 'display',
      '/api/config/device/network': 'network',
      '/api/config/device/bluetooth': 'bluetooth',
      '/api/config/device/security': 'security',
      '/api/config/module/external-notification': 'external_notification',
      '/api/config/module/store-forward': 'store_forward',
      '/api/config/module/telemetry': 'telemetry',
      '/api/config/module/canned-message': 'canned_message',
      '/api/config/module/range-test': 'range_test',
      '/api/config/module/detection-sensor': 'detection_sensor',
      '/api/config/module/ambient-lighting': 'ambient_lighting',
      '/api/config/module/neighbor-info': 'neighbor_info',
      '/api/config/module/serial': 'serial',
      '/api/config/module/audio': 'audio',
      '/api/config/module/paxcounter': 'paxcounter',
      '/api/config/module/remote-hardware': 'remote_hardware',
    },

    // Se il target è un nodo remoto, ridirige l'endpoint sull'API admin.
    cfgEndpoint(url) {
      if (this.target === 'local') return url
      const sec = this._remoteSections[url]
      return sec ? `/api/admin/${this.target}/config/${sec}` : url
    },

    remoteCapable() {
      // sezioni con almeno un endpoint remotizzabile (tutte le board tranne
      // node/canali, che restano locali)
      return ['lora','mqtt','position','power','devdisplay','network','bluetooth',
              'security','extnotif','sf','telmod','cannedmod','rangetest',
              'detsensor','ambilight','neighinfo','serial','audio','paxcounter',
              'remotehw'].includes(this.section)
    },

    async loadTargets() {
      const r = await fetch('/api/nodes')
      if (r.ok) {
        const nodes = await r.json()
        this.targetNodes = nodes.filter(n => !n.is_local)
      }
    },

    async setTarget(t) {
      this.target = t
      // ricarica la sezione corrente dal nuovo target
      await this.selectSection(this.section)
    },

    async loadDevSection(endpoint, prop) {
      if (this.target !== 'local') this.moduleStatus = '⏳ lettura dal nodo remoto…'
      const r = await fetch(this.cfgEndpoint(`/api/config/device/${endpoint}`))
      if (r.ok) this[prop] = await r.json()
      else this[prop] = {}
      if (this.target !== 'local') this.moduleStatus = r.ok ? '' : '✗ nodo non raggiungibile'
    },

    // --- Condivisione canali (URL / QR) ---
    async loadChannelUrl() {
      const r = await fetch('/api/config/channels/url')
      this.chUrl = r.ok ? (await r.json()).url : ''
    },

    async copyChannelUrl() {
      try {
        await navigator.clipboard.writeText(this.chUrl)
        this.status.channels = '✓ URL copiato'
      } catch (e) {
        this.status.channels = '✗ Copia non disponibile'
      }
    },

    async importChannelUrl() {
      if (!this.chImportUrl.includes('#')) {
        this.status.channels = '✗ URL non valido'
        return
      }
      const r = await fetch('/api/config/channels/url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: this.chImportUrl, add_only: this.chAddOnly })
      })
      const data = await r.json()
      this.status.channels = r.ok ? '✓ Canali importati — riavvio consigliato' : '✗ ' + (data.error || 'Errore')
      if (r.ok) { this.chImportUrl = ''; await this.loadChannels(); await this.loadChannelUrl() }
    },

    // --- Utilità board (sezione Nodo) ---
    async syncTime() {
      const r = await fetch('/api/system/sync-time', { method: 'POST' })
      this.status.node = r.ok ? '✓ Orario sincronizzato' : '✗ Board non connessa'
    },

    async resetNodeDb() {
      if (!confirm("Svuotare l'anagrafica nodi della board? I nodi verranno riscoperti dalla mesh.")) return
      const r = await fetch('/api/system/reset-nodedb', { method: 'POST' })
      this.status.node = r.ok ? '✓ NodeDB azzerato' : '✗ Board non connessa'
    },

    async loadNode() {
      const r = await fetch('/api/config/node')
      if (r.ok) this.node = await r.json()
      this.loaded.node = true
    },

    async loadLora() {
      const r = await fetch(this.cfgEndpoint('/api/config/lora'))
      if (r.ok) this.lora = await r.json()
      this.loaded.lora = true
    },

    async loadChannels() {
      const r = await fetch('/api/config/channels')
      if (r.ok) {
        const data = await r.json()
        this.channels = data.channels ?? data
        this.channelsCached = data.cached ?? false
      }
      this.loaded.channels = true
    },

    async saveNode() {
      if (!this.node.long_name.trim()) {
        this.status.node = '✗ Long name obbligatorio'
        return
      }
      if (this.node.long_name.trim().length > 36) {
        this.status.node = '✗ Long name max 36 caratteri'
        return
      }
      if (!this.node.short_name.trim()) {
        this.status.node = '✗ Short name obbligatorio'
        return
      }
      if (this.node.short_name.trim().length > 4) {
        this.status.node = '✗ Short name max 4 caratteri'
        return
      }
      this.saving.node = true
      this.status.node = ''
      try {
        const r = await fetch('/api/config/node', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ long_name: this.node.long_name, short_name: this.node.short_name, role: this.node.role, is_licensed: !!this.node.is_licensed })
        })
        const data = await r.json()
        this.status.node = r.ok ? '✓ Salvato' : '✗ ' + (data.error || 'Errore')
      } finally {
        this.saving.node = false
      }
    },

    async scanSerialPorts() {
      try {
        const r = await fetch('/api/config/serial/ports')
        const d = await r.json()
        this.serialPorts = d.ports
        this.serialPort = d.current
      } catch(e) { this.status.serial = '✗ scan fallito' }
    },

    async saveSerialPort() {
      try {
        const r = await fetch('/api/config/serial/port', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({port: this.serialPort})
        })
        const d = await r.json()
        if (d.ok) {
          this.status.serial = '✓ Porta cambiata — riavvio necessario'
        } else {
          this.status.serial = '✗ ' + (d.error || 'errore')
        }
      } catch(e) { this.status.serial = '✗ errore' }
    },

    async doFactoryReset() {
      this.factoryModal = false
      try {
        const r = await fetch('/api/system/factory-reset', {method:'POST'})
        const d = await r.json()
        if (d.ok) {
          this.status.node = '✓ Factory reset completato'
        } else {
          this.status.node = '✗ ' + (d.error || 'errore')
        }
      } catch(e) { this.status.node = '✗ reset fallito' }
    },

    async saveLora() {
      const validRegions = ['UNSET','US','EU_433','EU_868','CN','JP','ANZ','KR','TW','RU',
                            'IN','NZ_865','TH','LORA_24','UA_433','UA_868','MY_433','MY_919','SG_923']
      const validPresets = ['LONG_FAST','LONG_SLOW','VERY_LONG_SLOW','MEDIUM_SLOW',
                            'MEDIUM_FAST','SHORT_SLOW','SHORT_FAST','SHORT_TURBO']
      if (!validRegions.includes(this.lora.region)) {
        this.status.lora = '✗ Regione non valida'
        return
      }
      if (!validPresets.includes(this.lora.modem_preset)) {
        this.status.lora = '✗ Preset non valido'
        return
      }
      this.saving.lora = true
      this.status.lora = ''
      try {
        const r = await fetch(this.cfgEndpoint('/api/config/lora'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            region: this.lora.region, modem_preset: this.lora.modem_preset,
            hop_limit: this.lora.hop_limit ?? 3, tx_enabled: this.lora.tx_enabled ?? true,
            tx_power: this.lora.tx_power ?? 0, channel_num: this.lora.channel_num ?? 0,
            override_duty_cycle: !!this.lora.override_duty_cycle,
            sx126x_rx_boosted_gain: !!this.lora.sx126x_rx_boosted_gain,
            ignore_mqtt: !!this.lora.ignore_mqtt,
          })
        })
        const data = await r.json()
        this.status.lora = r.ok ? '✓ Salvato' : '✗ ' + (data.error || 'Errore')
      } finally {
        this.saving.lora = false
      }
    },

    async saveChannel(idx) {
      const ch = this.channels.find(c => c.index === idx)
      if (!ch) return
      if (ch.psk_b64 && ch.psk_b64.length > 0) {
        try {
          atob(ch.psk_b64)
        } catch(e) {
          this.status.channels = '✗ PSK non è Base64 valido'
          return
        }
      }
      const r = await fetch(`/api/config/channels/${idx}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: ch.name, psk_b64: ch.psk_b64 || '', role: ch.role || 'SECONDARY',
          uplink_enabled: !!ch.uplink_enabled, downlink_enabled: !!ch.downlink_enabled,
          position_precision: ch.position_precision ?? 0,
        })
      })
      const data = await r.json()
      this.status.channels = r.ok ? `✓ CH${idx} salvato` : '✗ ' + (data.error || 'Errore')
    },

    // GPIO
    gpio: [],
    showAddGpio: false,
    gpioStep: 'type',
    gpioForm: {},
    i2cScanResults: [],
    i2cScanning: false,
    pinDropdownOpen: false,
    pinDropdownOpenB: false,
    allPins: [4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27],
    reservedPins: { 2:'I2C SDA', 3:'I2C SCL', 14:'UART TX', 15:'UART RX', 9:'SPI MISO', 10:'SPI MOSI', 11:'SPI CLK' },
    gpioTypes: [
      { id:'i2c_sensor', icon:'🌡', label:'I2C Sensore', sub:'BME280, SHT31…' },
      { id:'rtc',        icon:'🕐', label:'RTC I2C',     sub:'DS3231, DS1307' },
      { id:'buzzer',     icon:'🔊', label:'Buzzer',      sub:'GPIO output' },
      { id:'encoder',    icon:'🔄', label:'Encoder',     sub:'Rotativo A/B' },
      { id:'led',        icon:'💡', label:'LED',         sub:'GPIO output' },
      { id:'button',     icon:'🔘', label:'Pulsante',    sub:'GPIO input' },
    ],

    get usedPins() {
      const used = {}
      for (const d of this.gpio) {
        if (d.pin_a) used[d.pin_a] = d.name
        if (d.pin_b) used[d.pin_b] = d.name
        if (d.pin_sw) used[d.pin_sw] = d.name
      }
      return used
    },

    getPinStyle(pin, selected) {
      if (pin === selected) return 'background:#1a3a5c;color:var(--accent);'
      if (this.usedPins[pin]) return 'background:#1a0a0a;color:#ef4444;'
      if (this.reservedPins[pin]) return 'background:#1a1500;color:#e5a50a;'
      return 'color:var(--text);'
    },

    async loadGpio() {
      const r = await fetch('/api/config/gpio')
      if (r.ok) this.gpio = await r.json()
    },

    async scanI2C(bus) {
      this.i2cScanning = true
      this.i2cScanResults = []
      try {
        const r = await fetch(`/api/config/i2c-scan?bus=${bus}`)
        if (r.ok) this.i2cScanResults = await r.json()
      } finally {
        this.i2cScanning = false
      }
    },

    async saveGpioDevice() {
      const r = await fetch('/api/config/gpio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.gpioForm)
      })
      if (r.ok) {
        await this.loadGpio()
        this.showAddGpio = false
        this.status.gpio = '✓ Periferica aggiunta'
      } else {
        this.status.gpio = '✗ Errore salvataggio'
      }
    },

    async testGpioDevice(id) {
      this.status.gpio = 'Test in corso...'
      const r = await fetch(`/api/config/gpio/${id}/test`, { method: 'POST' })
      const data = await r.json()
      this.status.gpio = r.ok ? '✓ ' + data.result : '✗ ' + (data.error || 'Errore')
    },

    async deleteGpioDevice(id) {
      const r = await fetch(`/api/config/gpio/${id}`, { method: 'DELETE' })
      if (r.ok) {
        await this.loadGpio()
        this.status.gpio = '✓ Rimosso'
      }
    },

    // Tema — preset b1..b9 definiti in base.html (window.PIMESH_THEMES).
    currentTheme: (function(t) { var l = { dark:'b1', light:'b3', hc:'b7' }; return l[t] || t })(localStorage.getItem('pimesh-theme') || 'b1'),
    currentAccent: localStorage.getItem('pimesh-accent') || '#9bc24a',
    themePresets: window.PIMESH_THEMES || {},
    accentSwatches: ['#9bc24a','#3ef07a','#f2c14e','#ff7a1a','#e8637a','#4fc3e8','#a78bfa'],
    // Color picker state
    cpOpen: false, cpKey: '', cpLabel: '', cpValue: '',
    cpPalette: [
      '#f44336','#e91e63','#9c27b0','#673ab7','#3f51b5','#2196f3','#03a9f4','#00bcd4','#009688','#4caf50',
      '#ef5350','#ec407a','#ab47bc','#7e57c2','#5c6bc0','#42a5f5','#29b6f6','#26c6da','#26a69a','#66bb6a',
      '#e57373','#f06292','#ba68c8','#9575cd','#7986cb','#64b5f6','#4fc3f7','#4dd0e1','#4db6ac','#81c784',
      '#ff5722','#ff9800','#ffc107','#ffeb3b','#cddc39','#8bc34a','#c6ff00','#ffea00','#ffd600','#ff6d00',
      '#ff8a65','#ffb74d','#ffd54f','#fff176','#dce775','#aed581','#e6ee9c','#fff59d','#ffe082','#ffab91',
      '#795548','#8d6e63','#a1887f','#bcaaa4','#607d8b','#78909c','#90a4ae','#b0bec5','#546e7a','#455a64',
    ],
    cpGrays: ['#000000','#111111','#222222','#333333','#444444','#666666','#888888','#aaaaaa','#cccccc','#ffffff'],
    themeVars: [
      { key: '--bg',      label: 'Sfondo',      value: getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#11150c' },
      { key: '--panel',   label: 'Pannello',    value: getComputedStyle(document.documentElement).getPropertyValue('--panel').trim() || '#161a10' },
      { key: '--panel-2', label: 'Pannello 2',  value: getComputedStyle(document.documentElement).getPropertyValue('--panel-2').trim() || '#1f2616' },
      { key: '--border',  label: 'Bordo',       value: getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#313c1f' },
      { key: '--text',    label: 'Testo',       value: getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#dde6c9' },
      { key: '--muted',   label: 'Secondario',  value: getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#7d8a63' },
      { key: '--accent',  label: 'Accento',     value: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#9bc24a' },
      { key: '--ok',      label: 'OK',          value: getComputedStyle(document.documentElement).getPropertyValue('--ok').trim() || '#3ef07a' },
      { key: '--warn',    label: 'Avviso',      value: getComputedStyle(document.documentElement).getPropertyValue('--warn').trim() || '#e5b13d' },
      { key: '--danger',  label: 'Allarme',     value: getComputedStyle(document.documentElement).getPropertyValue('--danger').trim() || '#c9603f' },
    ],

    applyTheme(theme) {
      this.currentTheme = theme
      localStorage.setItem('pimesh-theme', theme)
      const root = document.documentElement
      if (theme === 'custom') {
        try {
          var saved = JSON.parse(localStorage.getItem('pimesh-custom-theme') || '{}')
          Object.keys(saved).forEach(function(k) { root.style.setProperty(k, saved[k]) })
        } catch(e) {}
      } else {
        var preset = this.themePresets[theme]
        if (preset) Object.keys(preset).forEach(function(k) { if (k.indexOf('--') === 0) root.style.setProperty(k, preset[k]) })
        // L'accento del preset sostituisce l'override manuale salvato.
        if (preset && preset['--accent']) {
          this.currentAccent = preset['--accent']
          localStorage.removeItem('pimesh-accent')
        }
      }
      // Sync themeVars with current computed values
      var cs = getComputedStyle(root)
      if (this.themeVars) this.themeVars.forEach(function(v) { v.value = cs.getPropertyValue(v.key).trim() })
    },

    applyAccent(color) {
      this.currentAccent = color
      localStorage.setItem('pimesh-accent', color)
      document.documentElement.style.setProperty('--accent', color)
      var v = this.themeVars.find(v => v.key === '--accent')
      if (v) v.value = color
    },

    openColorPicker(key, label, value) {
      this.cpKey = key; this.cpLabel = label; this.cpValue = value; this.cpOpen = true
    },
    cpSelect(color) {
      this.cpValue = color
      this.setThemeVar(this.cpKey, color)
      if (this.cpKey === '--accent') this.applyAccent(color)
    },
    cpSetHex(val) {
      if (/^#[0-9a-fA-F]{6}$/.test(val)) { this.cpSelect(val) }
    },

    setThemeVar(key, value) {
      document.documentElement.style.setProperty(key, value)
      var v = this.themeVars.find(v => v.key === key)
      if (v) v.value = value
      if (key === '--accent') { this.currentAccent = value; localStorage.setItem('pimesh-accent', value) }
    },

    resetThemeVars() {
      this.applyTheme(this.currentTheme)
      var cs = getComputedStyle(document.documentElement)
      this.themeVars.forEach(function(v) {
        v.value = cs.getPropertyValue(v.key).trim()
      })
    },

    saveCustomTheme() {
      var custom = {}
      this.themeVars.forEach(function(v) { custom[v.key] = v.value })
      localStorage.setItem('pimesh-custom-theme', JSON.stringify(custom))
      this.currentTheme = 'custom'
      localStorage.setItem('pimesh-theme', 'custom')
    },

    // RTC
    rtcStatus: null,
    rtcModel: 'ds3231',
    rtcCopied: false,

    async loadRtc() {
      const r = await fetch('/api/config/rtc/status')
      if (r.ok) this.rtcStatus = await r.json()
    },

    copyRtcCmd() {
      const cmd = 'sudo bash ~/pi-Mesh/scripts/setup-rtc.sh ' + this.rtcModel
      navigator.clipboard.writeText(cmd).then(() => {
        this.rtcCopied = true
        setTimeout(() => { this.rtcCopied = false }, 2000)
      })
    },

    async loadMappa() {
      if (this.mappa.cached) return
      const r = await fetch('/api/config/map')
      const d = await r.json()
      this.mappa.local_tiles  = d.local_tiles
      this.mappa.region       = d.region
      this.mappa.tiles_present = d.tiles_present
      this.mappa.cached = true
    },

    async saveMappa() {
      this.mappa.saving = true
      try {
        const r = await fetch('/api/config/map', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ local_tiles: this.mappa.local_tiles })
        })
        if (!r.ok) {
          console.error('Failed to save mappa config:', r.status)
          this.mappa.local_tiles = !this.mappa.local_tiles
        }
      } catch (err) {
        console.error('Error saving mappa config:', err)
        this.mappa.local_tiles = !this.mappa.local_tiles
      } finally {
        this.mappa.saving = false
      }
    },

    async loadUsb() {
      this.usb.loading = true
      try {
        const r = await fetch('/api/config/usb/status')
        if (r.ok) {
          const d = await r.json()
          this.usb.connected = d.connected
          this.usb.devices = d.devices || []
          this.usb.tiles_location = d.tiles_location || 'sd'
        }
      } catch(e) { console.error('USB status error:', e) }
      this.usb.loading = false
    },

    async moveTilesToUsb() {
      this.usb.moving = true
      try {
        const r = await fetch('/api/config/usb/move-tiles', { method: 'POST' })
        const d = await r.json()
        if (d.ok) {
          this.usb.tiles_location = 'usb'
          if (typeof showToast === 'function') showToast('Tile spostate su USB')
        } else {
          if (typeof showToast === 'function') showToast(d.error || 'Errore', 'warn')
        }
      } catch(e) { if (typeof showToast === 'function') showToast('Errore spostamento', 'warn') }
      this.usb.moving = false
    },

    async restoreTilesToSd() {
      this.usb.moving = true
      try {
        const r = await fetch('/api/config/usb/restore-tiles', { method: 'POST' })
        const d = await r.json()
        if (d.ok) {
          this.usb.tiles_location = 'sd'
          if (typeof showToast === 'function') showToast('Tile ripristinate su SD')
        } else {
          if (typeof showToast === 'function') showToast(d.error || 'Errore', 'warn')
        }
      } catch(e) { if (typeof showToast === 'function') showToast('Errore ripristino', 'warn') }
      this.usb.moving = false
    },

    async loadDisplay() {
      try {
        const r = await fetch('/api/config/display')
        if (r.ok) {
          const d = await r.json()
          this.display.brightness = d.brightness
          this.display.rotation = d.rotation ?? 0
        }
      } catch(e) {}
    },

    async saveRotation() {
      this.display.savingRotation = true
      this.display.rotationStatus = ''
      try {
        const r = await fetch('/api/config/display', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ brightness: this.display.brightness, rotation: this.display.rotation })
        })
        const d = await r.json()
        if (r.ok) {
          this.display.rotationStatus = 'Il Pi si riavvierà per applicare la rotazione'
          await fetch('/api/system/reboot', { method: 'POST' })
        } else {
          this.display.rotationStatus = '✗ ' + (d.error || 'Errore')
        }
      } catch(e) {
        this.display.rotationStatus = '✗ Errore di rete'
      } finally {
        this.display.savingRotation = false
      }
    },

    async saveDisplay() {
      this.display.saving = true
      this.display.status = ''
      try {
        const r = await fetch('/api/config/display', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ brightness: this.display.brightness })
        })
        const d = await r.json()
        this.display.status = r.ok ? '✓ Salvato' : '✗ ' + (d.error || 'Errore')
      } catch(e) {
        this.display.status = '✗ Errore di rete'
      } finally {
        this.display.saving = false
      }
    },

    async loadAlert() {
      try {
        const r = await fetch('/api/config/alerts')
        if (r.ok) {
          const d = await r.json()
          this.alert.node_offline_min = d.node_offline_min
          this.alert.battery_low = d.battery_low
          this.alert.ram_high = d.ram_high
        }
      } catch(e) {}
    },

    async saveAlert() {
      this.alert.saving = true
      try {
        await fetch('/api/config/alerts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            node_offline_min: this.alert.node_offline_min,
            battery_low: this.alert.battery_low,
            ram_high: this.alert.ram_high,
          })
        })
      } catch(e) {}
      this.alert.saving = false
    },

    // WiFi
    wifiNetworks: [],
    wifiScanning: false,
    wifiConnecting: false,
    wifi: { ssid: '', password: '' },
    wifiStatus: { connected: false, ssid: '', ip: '', method: 'auto' },
    wifiSaved: [],
    wifiIp: { method: 'auto', address: '', gateway: '', dns: '' },
    wifiIpSaving: false,
    apActive: false,
    apIp: '',
    apToggling: false,

    async loadApStatus() {
      try {
        const r = await fetch('/api/config/ap/status')
        if (r.ok) {
          const d = await r.json()
          this.apActive = d.active
        }
      } catch(e) {}
    },

    async toggleAP() {
      this.apToggling = true
      try {
        const r = await fetch('/api/config/ap/toggle', { method: 'POST' })
        if (r.ok) {
          const d = await r.json()
          this.apActive = d.active
          this.apIp = d.ip || ''
          if (typeof showToast === 'function') showToast(d.message || (d.active ? 'AP attivato' : 'AP disattivato'))
        }
      } catch(e) {
        if (typeof showToast === 'function') showToast('Errore AP', 'warn')
      } finally {
        this.apToggling = false
      }
    },

    async scanWifi() {
      this.wifiScanning = true
      this.wifiNetworks = []
      try {
        const r = await fetch('/api/config/wifi/scan')
        if (r.ok) this.wifiNetworks = await r.json()
      } finally {
        this.wifiScanning = false
      }
    },

    async connectWifi() {
      this.wifiConnecting = true
      this.status.wifi = ''
      try {
        const r = await fetch('/api/config/wifi/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.wifi)
        })
        const data = await r.json()
        this.status.wifi = r.ok ? '✓ Connesso a ' + this.wifi.ssid : '✗ ' + (data.error || 'Errore')
        if (r.ok) {
          await this.loadWifiStatus()
          await this.loadWifiSaved()
        }
      } finally {
        this.wifiConnecting = false
      }
    },

    async loadWifiStatus() {
      try {
        const r = await fetch('/api/config/wifi/status')
        if (r.ok) {
          this.wifiStatus = await r.json()
          this.wifiIp.method = this.wifiStatus.method === 'manual' ? 'manual' : 'auto'
        }
      } catch(e) {}
    },

    async loadWifiSaved() {
      try {
        const r = await fetch('/api/config/wifi/saved')
        if (r.ok) this.wifiSaved = await r.json()
      } catch(e) {}
    },

    async deleteWifiSaved(name) {
      try {
        const r = await fetch('/api/config/wifi/saved/' + encodeURIComponent(name), { method: 'DELETE' })
        if (r.ok) {
          this.wifiSaved = this.wifiSaved.filter(n => n.name !== name)
          this.status.wifi = '✓ Rete rimossa'
        }
      } catch(e) {}
    },

    async saveWifiIp() {
      this.wifiIpSaving = true
      try {
        const r = await fetch('/api/config/wifi/ip', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.wifiIp)
        })
        const data = await r.json()
        this.status.wifi = r.ok ? '✓ IP aggiornato' : '✗ ' + (data.error || 'Errore')
        if (r.ok) await this.loadWifiStatus()
      } finally {
        this.wifiIpSaving = false
      }
    },

    async loadMqtt() {
      const r = await fetch(this.cfgEndpoint('/api/config/mqtt'))
      if (r.ok) this.mqtt = await r.json()
    },

    async loadMqttStatus() {
      const r = await fetch('/api/config/mqtt/status')
      if (r.ok) this.mqttStatus = await r.json()
    },

    async saveMqtt() {
      this.mqttSaving = true
      this.status.mqtt = ''
      try {
        const r = await fetch(this.cfgEndpoint('/api/config/mqtt'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            enabled: this.mqtt.enabled,
            address: this.mqtt.address,
            username: this.mqtt.username,
            password: this.mqtt.password,
            encryption_enabled: this.mqtt.encryption_enabled,
            json_enabled: this.mqtt.json_enabled,
            tls_enabled: this.mqtt.tls_enabled,
            root: this.mqtt.root,
            proxy_to_client_enabled: this.mqtt.proxy_to_client_enabled,
            map_reporting_enabled: this.mqtt.map_reporting_enabled,
          })
        })
        const data = await r.json()
        this.status.mqtt = r.ok ? '✓ Salvato — bridge riavviato' : '✗ ' + (data.error || 'Errore')
        if (r.ok) await this.loadMqttStatus()
      } finally {
        this.mqttSaving = false
      }
    },

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

    async saveModule(endpoint, data) {
      if (this.target !== 'local') this.moduleStatus = '⏳ scrittura sul nodo remoto…'
      const r = await fetch(this.cfgEndpoint(endpoint), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
      })
      this.moduleStatus = r.ok ? '✓ Salvato' : '✗ Errore'
      setTimeout(() => { this.moduleStatus = '' }, 2000)
    },

    async loadExtNotif() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/external-notification'))
      if (r.ok) this.extNotif = await r.json()
    },
    async loadStoreForward() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/store-forward'))
      if (r.ok) this.storeForward = await r.json()
    },
    async loadTelMod() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/telemetry'))
      if (r.ok) this.telMod = await r.json()
    },
    async loadCannedMod() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/canned-message'))
      if (r.ok) this.cannedMod = await r.json()
    },
    async loadRangeTest() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/range-test'))
      if (r.ok) this.rangeTest = await r.json()
    },
    async loadDetSensor() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/detection-sensor'))
      if (r.ok) this.detSensor = await r.json()
    },
    async loadAmbLight() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/ambient-lighting'))
      if (r.ok) this.ambLight = await r.json()
    },
    async loadNeighInfo() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/neighbor-info'))
      if (r.ok) this.neighInfo = await r.json()
    },
    async loadSerialMod() {
      const r = await fetch(this.cfgEndpoint('/api/config/module/serial'))
      if (r.ok) this.serialMod = await r.json()
    },
  }
}
