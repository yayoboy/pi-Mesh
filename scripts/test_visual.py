"""Inject F-key + F9 (screenshot) per page, so each GUI state lands as a
PNG under data/screenshots/. Used to visually verify Step 1 end-to-end.

Sequence: F3, F9, F4, F9, F5, F9, F6, F9, F7, F9, F2, F9
=> 6 PNGs, one per page (Mappa, Msg, Config, Metriche, Log, Nodi).

Run as root on the Pi. Requires python3-evdev.
"""
from __future__ import annotations

import time
from evdev import UInput, ecodes as e

PAGES = [
    ("Mappa",    e.KEY_F3),
    ("Msg",      e.KEY_F4),
    ("Config",   e.KEY_F5),
    ("Metriche", e.KEY_F6),
    ("Log",      e.KEY_F7),
    ("Nodi",     e.KEY_F2),
]


def tap(ui, key):
    ui.write(e.EV_KEY, key, 1)
    ui.syn()
    time.sleep(0.05)
    ui.write(e.EV_KEY, key, 0)
    ui.syn()


def main() -> None:
    caps = {e.EV_KEY: [k for _, k in PAGES] + [e.KEY_F9]}
    with UInput(caps, name="pimesh-visual-test") as ui:
        print("uinput device created, waiting 2s for Qt to discover it...")
        time.sleep(2)
        for name, key in PAGES:
            print(f"-> page {name} (F{key - e.KEY_F1 + 1})")
            tap(ui, key)
            time.sleep(1.5)  # let page render
            print(f"   screenshot")
            tap(ui, e.KEY_F9)
            time.sleep(0.8)
        print("done.")


if __name__ == "__main__":
    main()
