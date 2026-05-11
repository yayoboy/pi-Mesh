"""Smoke test for the remaining Step 3 pages + cheatsheet overlay.

Sequence:
  1. Shift+F12 (disable VKB)
  2. F6 (Metriche), F9 screenshot
  3. F7 (Log), F9 screenshot
  4. F1 (cheatsheet), F9 screenshot
  5. Esc (dismiss), F9 screenshot
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
        e.KEY_F1, e.KEY_F6, e.KEY_F7, e.KEY_F9, e.KEY_F12,
        e.KEY_LEFTSHIFT, e.KEY_ESC,
    ]}
    with UInput(caps, name="pimesh-misc-test") as ui:
        time.sleep(2)
        tap(ui, e.KEY_LEFTSHIFT, e.KEY_F12); time.sleep(0.5)
        print("F6 Metriche")
        tap(ui, e.KEY_F6); time.sleep(1.5)
        tap(ui, e.KEY_F9); time.sleep(1.0)
        print("F7 Log")
        tap(ui, e.KEY_F7); time.sleep(1.5)
        tap(ui, e.KEY_F9); time.sleep(1.0)
        print("F1 Cheatsheet")
        tap(ui, e.KEY_F1); time.sleep(1.0)
        tap(ui, e.KEY_F9); time.sleep(1.0)
        print("Esc (dismiss)")
        tap(ui, e.KEY_ESC); time.sleep(0.5)
        tap(ui, e.KEY_F9); time.sleep(1.0)
        print("done.")


if __name__ == "__main__":
    main()
