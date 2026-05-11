"""Visual test for Step 2: verify focus ring shows and Tab cycles widgets.

Run as root on the Pi. Produces 4 screenshots:
    A. After F2 (Nodi page) -> focus should be on page or first child.
    B. After Tab x2 -> focus should have moved.
    C. After Shift+Tab x6 -> focus should reach the tab bar (visible ring on a tab).
    D. After F4 (Msg) -> focus on message input (or page container).

Tail the journal to see shortcut events:
    journalctl -u pimesh-gui -f
"""
from __future__ import annotations

import time
from evdev import UInput, ecodes as e

ALL_KEYS = [
    e.KEY_F2, e.KEY_F3, e.KEY_F4, e.KEY_F9,
    e.KEY_TAB, e.KEY_LEFTSHIFT,
]


def tap(ui, *keys):
    for k in keys:
        ui.write(e.EV_KEY, k, 1)
    ui.syn()
    time.sleep(0.05)
    for k in reversed(keys):
        ui.write(e.EV_KEY, k, 0)
    ui.syn()


def main() -> None:
    caps = {e.EV_KEY: ALL_KEYS}
    with UInput(caps, name="pimesh-focus-test") as ui:
        print("uinput created, settle 2s...")
        time.sleep(2)

        print("A: F2 (Nodi) + F9 screenshot")
        tap(ui, e.KEY_F2)
        time.sleep(1.0)
        tap(ui, e.KEY_F9)
        time.sleep(0.8)

        print("B: Tab x2 + F9 screenshot")
        tap(ui, e.KEY_TAB)
        time.sleep(0.3)
        tap(ui, e.KEY_TAB)
        time.sleep(0.3)
        tap(ui, e.KEY_F9)
        time.sleep(0.8)

        print("C: Shift+Tab x6 (try to reach tab bar) + F9 screenshot")
        for _ in range(6):
            tap(ui, e.KEY_LEFTSHIFT, e.KEY_TAB)
            time.sleep(0.2)
        tap(ui, e.KEY_F9)
        time.sleep(0.8)

        print("D: F4 (Msg) + F9 screenshot")
        tap(ui, e.KEY_F4)
        time.sleep(1.0)
        tap(ui, e.KEY_F9)
        time.sleep(0.8)
        print("done.")


if __name__ == "__main__":
    main()
