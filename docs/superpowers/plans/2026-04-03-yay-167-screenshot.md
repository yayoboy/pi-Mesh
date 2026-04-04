# YAY-167 Screenshot Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a framebuffer screenshot button to the status bar that saves PNG images to USB (priority) or SD card boot partition.

**Architecture:** New `POST /api/screenshot` endpoint in `routers/commands.py` uses `fbgrab` to capture `/dev/fb0`. Frontend adds a camera icon to the status bar in `base.html` with flash animation and toast feedback. Storage logic reuses existing `usb_storage.get_usb_status()`.

**Tech Stack:** Python (FastAPI), `fbgrab` CLI tool, `usb_storage.py` module, vanilla JS

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `routers/commands.py` | Modify | Add `POST /api/screenshot` endpoint |
| `templates/base.html` | Modify | Add camera icon to status bar (line ~81, before reboot button) |
| `static/app.js` | Modify | Add `takeScreenshot()` function |

---

### Task 1: Backend — Screenshot Endpoint

**Files:**
- Modify: `routers/commands.py`
- Read: `usb_storage.py` (for `get_usb_status()` API)

- [ ] **Step 1: Add imports at top of `routers/commands.py`**

Add after the existing imports:

```python
import os
import re
import subprocess
import usb_storage
```

Note: `time` is already imported in this file.

- [ ] **Step 2: Add the screenshot endpoint**

Add at the end of `routers/commands.py`:

```python
SCREENSHOT_SUBDIR = 'pi-mesh/screenshots'
SCREENSHOT_SD_DIR = '/boot/firmware/screenshots'


@router.post('/api/screenshot')
async def take_screenshot():
    # Determine destination directory
    usb = usb_storage.get_usb_status()
    if usb['connected']:
        mount = None
        for dev in usb['devices']:
            if dev['mountpoint']:
                mount = dev['mountpoint']
                break
        if mount:
            dest_dir = os.path.join(mount, SCREENSHOT_SUBDIR)
            location = 'usb'
        else:
            dest_dir = SCREENSHOT_SD_DIR
            location = 'sd'
    else:
        dest_dir = SCREENSHOT_SD_DIR
        location = 'sd'

    os.makedirs(dest_dir, exist_ok=True)

    # Find next incremental number
    existing = []
    for f in os.listdir(dest_dir):
        m = re.match(r'screenshot_(\d+)\.png$', f)
        if m:
            existing.append(int(m.group(1)))
    next_num = max(existing) + 1 if existing else 1
    filename = f'screenshot_{next_num:03d}.png'
    filepath = os.path.join(dest_dir, filename)

    # Capture framebuffer
    try:
        result = subprocess.run(
            ['sudo', 'fbgrab', filepath],
            capture_output=True, text=True, timeout=10
        )
    except FileNotFoundError:
        return {'ok': False, 'error': 'fbgrab non installato (sudo apt install fbgrab)'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': 'fbgrab timeout'}

    if result.returncode != 0:
        return {'ok': False, 'error': result.stderr.strip() or 'cattura fallita'}

    return {'ok': True, 'path': filename, 'location': location}
```

- [ ] **Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('routers/commands.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add routers/commands.py
git commit -m "feat: add POST /api/screenshot endpoint for framebuffer capture"
```

---

### Task 2: Frontend — Camera Icon in Status Bar

**Files:**
- Modify: `templates/base.html:81` (before the Reboot button)

- [ ] **Step 1: Add camera icon to status bar**

In `templates/base.html`, find the `<!-- Reboot -->` comment (line ~81) and insert this **before** it:

```html
      <!-- Screenshot -->
      <button id="screenshot-btn" onclick="takeScreenshot()" title="Screenshot" style="background:none;border:none;color:var(--muted);cursor:pointer;padding:0;line-height:0;min-height:0;width:auto;">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
          <circle cx="12" cy="13" r="4"/>
        </svg>
      </button>
```

- [ ] **Step 2: Commit**

```bash
git add templates/base.html
git commit -m "feat: add camera icon to status bar for screenshot"
```

---

### Task 3: Frontend — takeScreenshot() Function

**Files:**
- Modify: `static/app.js` (add after the `showToast` function, around line 60)

- [ ] **Step 1: Add takeScreenshot function**

Add after the `showToast` function block in `static/app.js`:

```javascript
// ===== SCREENSHOT =====
function takeScreenshot() {
  const btn = document.getElementById('screenshot-btn')
  fetch('/api/screenshot', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        // Flash effect on icon
        if (btn) {
          btn.style.color = '#ffffff'
          setTimeout(() => { btn.style.color = '' }, 200)
        }
        const loc = data.location === 'usb' ? 'USB' : 'SD'
        showToast(data.path + ' (' + loc + ')', 'success')
      } else {
        showToast('Errore: ' + data.error, 'error')
      }
    })
    .catch(() => {
      showToast('Errore screenshot', 'error')
    })
}
```

- [ ] **Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat: add takeScreenshot() with flash animation and toast"
```

---

### Task 4: Integration Test on Device

- [ ] **Step 1: Deploy to Pi**

```bash
scp routers/commands.py pi@pimesh.local:~/pi-Mesh/routers/
scp templates/base.html pi@pimesh.local:~/pi-Mesh/templates/
scp static/app.js pi@pimesh.local:~/pi-Mesh/static/
ssh pi@pimesh.local "sudo systemctl restart pimesh"
```

- [ ] **Step 2: Install fbgrab on Pi (if not already installed)**

```bash
ssh pi@pimesh.local "sudo apt install -y fbgrab"
```

- [ ] **Step 3: Test screenshot via API**

```bash
ssh pi@pimesh.local "curl -X POST http://localhost:8000/api/screenshot"
```

Expected: `{"ok":true,"path":"screenshot_001.png","location":"sd"}`

- [ ] **Step 4: Verify file exists**

```bash
ssh pi@pimesh.local "ls -la /boot/firmware/screenshots/"
```

Expected: `screenshot_001.png` present

- [ ] **Step 5: Test from UI**

Open pi-Mesh on the device display. Tap the camera icon in the status bar. Verify:
- Icon flashes white briefly
- Toast shows "screenshot_002.png (SD)"

- [ ] **Step 6: Test with USB (if available)**

Insert a USB drive, take another screenshot. Verify it saves to `<usb>/pi-mesh/screenshots/` instead of SD.

- [ ] **Step 7: Final commit with any fixes**

```bash
git add -A
git commit -m "feat(YAY-167): screenshot feature — framebuffer capture with USB/SD storage"
```
