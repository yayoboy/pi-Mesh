"""Visual test for Config page keyboard navigation (Step 3c).

Sequence (VKB pre-disabled so it doesn't interfere):
  1. Shift+F12 (disable VKB)
  2. F5 (Config) -> focus first header (Device)
  3. F9 screenshot
  4. Down x3 -> focus 4th header (MQTT)
  5. F9 screenshot
  6. Space -> expand the focused section
  7. F9 screenshot
  8. Up x10 -> back near top
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
        e.KEY_F5, e.KEY_F9, e.KEY_F12, e.KEY_LEFTSHIFT,
        e.KEY_UP, e.KEY_DOWN, e.KEY_SPACE,
    ]}
    with UInput(caps, name="pimesh-config-test") as ui:
        time.sleep(2)
        print("1. Shift+F12 (disable VKB)")
        tap(ui, e.KEY_LEFTSHIFT, e.KEY_F12)
        time.sleep(0.6)
        print("2. F5 (Config)")
        tap(ui, e.KEY_F5)
        time.sleep(2.0)  # lazy build of Config
        print("3. F9 screenshot (initial focus on Device)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("4. Down x3")
        for _ in range(3):
            tap(ui, e.KEY_DOWN)
            time.sleep(0.3)
        print("5. F9 screenshot (focus on MQTT)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("6. Space (expand MQTT)")
        tap(ui, e.KEY_SPACE)
        time.sleep(0.6)
        print("7. F9 screenshot (MQTT expanded)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("8. Up x10 (back to first)")
        for _ in range(10):
            tap(ui, e.KEY_UP)
            time.sleep(0.2)
        print("9. F9 screenshot (back at Device)")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("done.")


if __name__ == "__main__":
    main()
