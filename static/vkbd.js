// vkbd.js — Virtual keyboard for pi-Mesh touchscreen kiosk
;(function() {
  var _target = null
  var _kbd = null
  var _preview = null
  var _keysContainer = null
  var _shift = false
  var _page = 0

  var ROWS_ALPHA = [
    ['q','w','e','r','t','y','u','i','o','p'],
    ['a','s','d','f','g','h','j','k','l'],
    ['z','x','c','v','b','n','m']
  ]
  var ROWS_SYM = [
    ['1','2','3','4','5','6','7','8','9','0'],
    ['@','#','$','%','&','*','-','+','='],
    ['!','"','\'','(',')','/',':',';']
  ]
  var ROWS_SYM2 = [
    ['_','~','<','>','{','}','[',']'],
    ['^','|','\\','`','?','€'],
  ]

  function build() {
    _kbd = document.createElement('div')
    _kbd.id = 'vkbd'
    _kbd.style.cssText = 'display:none;position:fixed;bottom:32px;left:0;right:0;z-index:9999;' +
      'background:#1a1a2e;border-top:1px solid #333;padding:0 2px 4px;touch-action:manipulation;'

    // Preview bar showing current input value
    _preview = document.createElement('div')
    _preview.id = 'vkbd-preview'
    _preview.style.cssText = 'padding:4px 8px;font-size:12px;color:#4a9eff;background:#0d1017;' +
      'border-bottom:1px solid #333;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;' +
      'direction:rtl;text-align:left;min-height:22px;'
    _kbd.appendChild(_preview)

    _keysContainer = document.createElement('div')
    _keysContainer.style.cssText = 'padding-top:4px;'
    _kbd.appendChild(_keysContainer)

    render()
    document.body.appendChild(_kbd)
  }

  function render() {
    var rows = _page === 1 ? ROWS_SYM : _page === 2 ? ROWS_SYM2 : ROWS_ALPHA
    // Build keyboard using DOM methods (no innerHTML with user data)
    var frag = document.createDocumentFragment()

    // Add style element
    var style = document.createElement('style')
    style.textContent = '.vk{min-width:26px;height:32px;border:none;border-radius:4px;' +
      'background:#2d2d44;color:#c9d1e0;font-size:13px;font-family:system-ui;cursor:pointer;' +
      'touch-action:manipulation;padding:0 4px;-webkit-tap-highlight-color:transparent;}' +
      '.vk:active{background:#4a9eff;color:#fff;}'
    frag.appendChild(style)

    for (var r = 0; r < rows.length; r++) {
      var row = document.createElement('div')
      row.style.cssText = 'display:flex;justify-content:center;gap:2px;margin-bottom:2px;'

      // Shift key on last alpha row
      if (r === 2 && _page === 0) {
        var shiftBtn = document.createElement('button')
        shiftBtn.className = 'vk'
        shiftBtn.dataset.action = 'shift'
        shiftBtn.style.minWidth = '32px'
        if (_shift) { shiftBtn.style.background = '#4a9eff'; shiftBtn.style.color = '#fff' }
        shiftBtn.textContent = '\u21E7'
        row.appendChild(shiftBtn)
      }

      for (var c = 0; c < rows[r].length; c++) {
        var ch = rows[r][c]
        var display = _shift && _page === 0 ? ch.toUpperCase() : ch
        var btn = document.createElement('button')
        btn.className = 'vk'
        btn.dataset.char = display
        btn.textContent = display
        row.appendChild(btn)
      }

      // Backspace on last row
      if (r === rows.length - 1) {
        var bsBtn = document.createElement('button')
        bsBtn.className = 'vk'
        bsBtn.dataset.action = 'backspace'
        bsBtn.style.minWidth = '32px'
        bsBtn.textContent = '\u232B'
        row.appendChild(bsBtn)
      }

      frag.appendChild(row)
    }

    // Bottom row: sym toggle, comma, space, period, done
    var bottom = document.createElement('div')
    bottom.style.cssText = 'display:flex;justify-content:center;gap:2px;'

    var symBtn = document.createElement('button')
    symBtn.className = 'vk'
    symBtn.dataset.action = 'sym'
    symBtn.style.cssText = 'min-width:40px;font-size:10px;'
    if (_page !== 0) { symBtn.style.background = '#4a9eff'; symBtn.style.color = '#fff' }
    symBtn.textContent = _page === 0 ? '123' : _page === 1 ? '#+=': 'ABC'
    bottom.appendChild(symBtn)

    var commaBtn = document.createElement('button')
    commaBtn.className = 'vk'
    commaBtn.dataset.char = ','
    commaBtn.style.minWidth = '24px'
    commaBtn.textContent = ','
    bottom.appendChild(commaBtn)

    var spaceBtn = document.createElement('button')
    spaceBtn.className = 'vk'
    spaceBtn.dataset.char = ' '
    spaceBtn.style.flex = '1'
    spaceBtn.textContent = '\u2423'
    bottom.appendChild(spaceBtn)

    var dotBtn = document.createElement('button')
    dotBtn.className = 'vk'
    dotBtn.dataset.char = '.'
    dotBtn.style.minWidth = '24px'
    dotBtn.textContent = '.'
    bottom.appendChild(dotBtn)

    var doneBtn = document.createElement('button')
    doneBtn.className = 'vk'
    doneBtn.dataset.action = 'done'
    doneBtn.style.cssText = 'min-width:48px;background:#4a9eff;color:#fff;font-size:10px;'
    doneBtn.textContent = 'OK'
    bottom.appendChild(doneBtn)

    frag.appendChild(bottom)

    _keysContainer.textContent = ''
    _keysContainer.appendChild(frag)
    updatePreview()
  }

  function onKey(e) {
    var btn = e.target.closest('.vk')
    if (!btn || !_target) return
    e.preventDefault()
    e.stopPropagation()

    var action = btn.dataset.action
    var ch = btn.dataset.char

    if (action === 'shift') {
      _shift = !_shift
      render()
      return
    }
    if (action === 'sym') {
      _page = (_page + 1) % 3
      _shift = false
      render()
      return
    }
    if (action === 'backspace') {
      var start = _target.selectionStart
      var end = _target.selectionEnd
      if (start !== end) {
        _target.value = _target.value.slice(0, start) + _target.value.slice(end)
        _target.selectionStart = _target.selectionEnd = start
      } else if (start > 0) {
        _target.value = _target.value.slice(0, start - 1) + _target.value.slice(start)
        _target.selectionStart = _target.selectionEnd = start - 1
      }
      fireInput()
      return
    }
    if (action === 'done') {
      hide()
      _target.blur()
      return
    }
    if (ch != null) {
      var start = _target.selectionStart
      var end = _target.selectionEnd
      _target.value = _target.value.slice(0, start) + ch + _target.value.slice(end)
      _target.selectionStart = _target.selectionEnd = start + ch.length
      if (_shift && _page === 0) {
        _shift = false
        render()
      }
      fireInput()
    }
  }

  function fireInput() {
    _target.dispatchEvent(new Event('input', { bubbles: true }))
    updatePreview()
  }

  function updatePreview() {
    if (!_preview || !_target) return
    var val = _target.value
    var placeholder = _target.placeholder || ''
    if (val) {
      // Use LTR override inside RTL container so cursor stays at the right (latest chars visible)
      _preview.textContent = val
    } else {
      _preview.textContent = placeholder
      _preview.style.opacity = '0.5'
      return
    }
    _preview.style.opacity = '1'
  }

  function show(el) {
    if (!_kbd) build()
    _target = el
    _shift = false
    _page = 0
    render()
    _kbd.style.display = 'block'
    // Shrink content area to avoid keyboard overlap
    var content = document.getElementById('content')
    if (content) content.style.height = 'calc(100vh - 24px - 48px - ' + _kbd.offsetHeight + 'px)'
    // Scroll input into visible area above keyboard
    setTimeout(function() {
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 50)
  }

  function hide() {
    if (!_kbd) return
    _kbd.style.display = 'none'
    _target = null
    var content = document.getElementById('content')
    if (content) content.style.height = ''
  }

  // Listen for focus on inputs/textareas
  document.addEventListener('focusin', function(e) {
    var tag = e.target.tagName
    var type = (e.target.type || '').toLowerCase()
    if ((tag === 'INPUT' && type !== 'checkbox' && type !== 'radio' && type !== 'range' && type !== 'hidden') ||
         tag === 'TEXTAREA') {
      show(e.target)
    }
  })

  // Hide on focusout only if new focus is not another input
  document.addEventListener('focusout', function() {
    setTimeout(function() {
      var active = document.activeElement
      if (!active || (active.tagName !== 'INPUT' && active.tagName !== 'TEXTAREA')) {
        if (_kbd && _kbd.contains(active)) return
        hide()
      }
    }, 100)
  })

  // Handle keyboard clicks via delegation
  document.addEventListener('pointerdown', function(e) {
    if (_kbd && _kbd.contains(e.target)) {
      e.preventDefault() // Prevent blur on input
      onKey(e)
    }
  })
})()
