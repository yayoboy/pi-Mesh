"""Visual test for Map keyboard navigation (Step 3e).

Sequence:
  1. Shift+F12 (VKB off)
  2. F3 (Mappa) -> focus on MapView, expect initial render at zoom 7 over Lazio
  3. F9 screenshot
  4. Right x5 (pan east)
  5. F9 screenshot
  6. Plus x2 (zoom in)
  7. F9 screenshot
  8. Home (recenter on local node)
  9. F9 screenshot
"""
from __future__ import annotations

import time
from evdev import UInput, ecodes as e


def tap(ui, *keys):
    for k in keys:
        ui.write(e.EV_KEY, k, 1)
    ui.syn()
    time.sleep(0.05)
    for k in reversed(keys):
        ui.write(e.EV_KEY, k, 0)
    ui.syn()


def main() -> None:
    caps = {e.EV_KEY: [
        e.KEY_F3, e.KEY_F9, e.KEY_F12, e.KEY_LEFTSHIFT,
        e.KEY_RIGHT, e.KEY_HOME, e.KEY_KPPLUS, e.KEY_EQUAL,
    ]}
    with UInput(caps, name="pimesh-map-test") as ui:
        time.sleep(2)
        print("1. Shift+F12 (VKB off)")
        tap(ui, e.KEY_LEFTSHIFT, e.KEY_F12)
        time.sleep(0.5)
        print("2. F3 (Mappa)")
        tap(ui, e.KEY_F3)
        time.sleep(1.5)
        print("3. F9 screenshot (initial)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("4. Right x5 (pan east)")
        for _ in range(5):
            tap(ui, e.KEY_RIGHT)
            time.sleep(0.3)
        print("5. F9 screenshot (panned)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        # Plus on US keyboards is Shift+Equal; KEY_EQUAL gives '=' which Qt
        # also accepts as Qt.Key.Key_Equal. Tap twice to zoom in.
        print("6. Equal x2 (zoom in)")
        for _ in range(2):
            tap(ui, e.KEY_EQUAL)
            time.sleep(0.4)
        print("7. F9 screenshot (zoomed in)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("8. Home (recenter)")
        tap(ui, e.KEY_HOME)
        time.sleep(0.8)
        print("9. F9 screenshot (recentered)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("done.")


if __name__ == "__main__":
    main()
