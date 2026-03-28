# UX Fixes Design — pi-Mesh Dashboard

> **Date:** 2026-03-28
> **Status:** Approved
> **Display constraint:** All UI elements must be proportional to 320x480 portrait and 480x320 landscape. Touch targets minimum 44px. This applies project-wide.

---

## 1. Log Toolbar

**Problem:** Buttons occupy entire 320px screen, nothing else visible.

**Solution:** Two-row compact toolbar:
- **Row 1:** Board/Pi tab switcher, full-width, toggle style
- **Row 2:** Search input (flex-grow) + filter buttons (icon-only) + action buttons (icon-only)

All buttons icon-only with tooltips. Tabs use compact toggle style (not full-size buttons). Total toolbar height ~70px max, leaving room for log content.

---

## 2. Telemetry Charts

**Problem:** Three separate charts waste vertical space and split related metrics.

**Solution:** Two charts, conditionally rendered:
- **Chart 1 (always visible):** Combined Board + Pi metrics — RAM, Battery, Temperature, Channel Utilization, AirTx time, Disk usage. Dual Y-axis (% left, voltage/temp right). Colored lines with metric badge legend on top.
- **Chart 2 (conditional):** I2C sensor data — appears only when I2C sensors are detected. Multi-series with auto-assigned colors per sensor metric.

Chart heights proportional to available viewport. Single chart takes full space; two charts split ~60/40.

---

## 3. Map Visibility & Persistence

**Problem:** Map container not visible (height 0 or CSS issue). Position resets every time tab is opened.

**Solution:**
- **Fix container:** Ensure `#map-container` has explicit height filling available viewport (calc 100vh minus status bar, toolbar, tabbar).
- **Persist view state:** Save `{lat, lng, zoom}` to `localStorage` on map move/zoom. Restore on tab reopen instead of recalculating from bounds.
- **Center-on-board button:** Icon-only button in the legend bar. Centers map on board's GPS position. Manual pan/zoom after centering is preserved until next explicit center action.
- **No auto-reset:** `initMapIfNeeded()` only creates the map once. Subsequent tab switches reuse existing instance. `invalidateSize()` on tab show to fix rendering.

---

## 4. Config Serial Port

**Problem:** Empty text field, no indication of detected port.

**Solution:** Dropdown select with:
- Auto-detected ports from system scan (`/dev/ttyACM*`, `/dev/ttyUSB*`) as options
- Each option shows device path
- Last option: "Personalizza..." — selecting it reveals a text input for manual entry
- Current active port highlighted/selected
- API endpoint `GET /api/serial-ports` returns list of detected ports

---

## 5. Theme & Accent Persistence

**Problem:** Accent color resets on browser refresh. No way to customize individual UI element colors.

**Solution:**
- **Preset themes:** Dark, Light, High Contrast (existing) + Custom
- **Custom theme:** Exposes CSS custom properties as color pickers:
  - `--accent` (primary accent)
  - `--bg` (background)
  - `--surface` (card/panel background)
  - `--text` (primary text)
  - `--muted` (secondary text)
  - `--border` (borders/dividers)
  - `--success`, `--warning`, `--danger` (status colors)
- **Persistence:** Dual-layer:
  - `localStorage` for instant apply on page load (before server render)
  - Server sync via `POST /api/set-theme` for cross-browser consistency
  - On load: apply localStorage theme immediately, then hydrate from server response if different
- **UI flow:** Selecting a preset loads its colors. Selecting "Custom" enables individual color pickers. Changes apply live as preview, saved on confirm.

---

## Global Constraint: Display Proportionality

All UI elements across the entire project must respect:
- **Portrait:** 320x480 primary layout
- **Landscape:** 480x320 rotated layout
- **Touch targets:** Minimum 44x44px
- **Font sizes:** Minimum 12px for body, 10px for labels
- **Spacing:** Use relative units (%, vh, vw) or clamp() where appropriate
- **No horizontal overflow:** All layouts must fit without horizontal scrolling
