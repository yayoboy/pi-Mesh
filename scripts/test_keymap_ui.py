"""Smoke test for Config > Tasti section.

Sequence:
  1. Shift+F12 (VKB off so it doesn't cover the form)
  2. F5 (Config)  — first section "Tasti" is expanded by default
  3. F9 screenshot
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
    caps = {e.EV_KEY: [e.KEY_F5, e.KEY_F9, e.KEY_F12, e.KEY_LEFTSHIFT]}
    with UInput(caps, name="pimesh-keymap-ui") as ui:
        time.sleep(2)
        tap(ui, e.KEY_LEFTSHIFT, e.KEY_F12)
        time.sleep(0.6)
        tap(ui, e.KEY_F5)
        time.sleep(2.5)
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("done.")


if __name__ == "__main__":
    main()
