"""Inject synthetic F-key presses via /dev/uinput to verify ShortcutManager.

Run on the Pi to verify that the Qt app receives keyboard events and
ShortcutManager dispatches to the right slots. Tail the journal in another
shell:

    journalctl -u pimesh-gui -f

Sequence (skips F10/F11/F12 which trigger rotation/reboot/shutdown dialogs):

    F2..F7    -> pages Nodi/Mappa/Msg/Config/Metriche/Log
    F8        -> telemetry page
    F9        -> screenshot
    F1        -> cheat-sheet placeholder log
    Shift+F12 -> toggle VKB

Each shortcut writes a WARNING line to the journal of pimesh-gui.service so
they show up under the default systemd-journal verbosity.

Requires python3-evdev. Must be run as root (uinput access).
"""
from __future__ import annotations

import time
from evdev import UInput, ecodes as e

# (description, [keys-pressed-together])
SEQUENCE = [
    ("F2 -> page Nodi",       [e.KEY_F2]),
    ("F3 -> page Mappa",      [e.KEY_F3]),
    ("F4 -> page Msg",        [e.KEY_F4]),
    ("F5 -> page Config",     [e.KEY_F5]),
    ("F6 -> page Metriche",   [e.KEY_F6]),
    ("F7 -> page Log",        [e.KEY_F7]),
    ("F8 -> telemetry",       [e.KEY_F8]),
    ("F9 -> screenshot",      [e.KEY_F9]),
    ("F1 -> cheatsheet log",  [e.KEY_F1]),
    ("Shift+F12 -> toggle VKB", [e.KEY_LEFTSHIFT, e.KEY_F12]),
]


def main() -> None:
    all_keys = {e.KEY_F1, e.KEY_F2, e.KEY_F3, e.KEY_F4, e.KEY_F5, e.KEY_F6,
                e.KEY_F7, e.KEY_F8, e.KEY_F9, e.KEY_F10, e.KEY_F11, e.KEY_F12,
                e.KEY_LEFTSHIFT}
    caps = {e.EV_KEY: list(all_keys)}
    with UInput(caps, name="pimesh-test-kbd") as ui:
        print("uinput device created, waiting 2s for Qt to discover it...")
        time.sleep(2)
        for label, keys in SEQUENCE:
            print(f"-> {label}")
            # Press in order, release in reverse (modifiers held during target).
            for k in keys:
                ui.write(e.EV_KEY, k, 1)
            ui.syn()
            time.sleep(0.05)
            for k in reversed(keys):
                ui.write(e.EV_KEY, k, 0)
            ui.syn()
            time.sleep(1.2)
        print("done.")


if __name__ == "__main__":
    main()
