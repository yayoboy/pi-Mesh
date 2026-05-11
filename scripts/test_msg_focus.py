"""Verify Msg page sets focus on input WITHOUT the VKB obscuring it.

Sequence:
    1. Shift+F12 (disable VKB)
    2. F4 (go to Msg) -> should focus input
    3. F9 screenshot
    4. F3 (go to Mappa, just to clean state)
    5. F9 screenshot
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
    caps = {e.EV_KEY: [e.KEY_F3, e.KEY_F4, e.KEY_F9, e.KEY_F12, e.KEY_LEFTSHIFT]}
    with UInput(caps, name="pimesh-msg-test") as ui:
        time.sleep(2)
        print("1. Shift+F12 (disable VKB)")
        tap(ui, e.KEY_LEFTSHIFT, e.KEY_F12)
        time.sleep(0.8)
        print("2. F4 (Msg)")
        tap(ui, e.KEY_F4)
        time.sleep(1.2)
        print("3. F9 screenshot")
        tap(ui, e.KEY_F9)
        time.sleep(1.0)
        print("done.")


if __name__ == "__main__":
    main()
