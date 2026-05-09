"""``python -m gui`` entry point. Delegates to :mod:`gui.app`."""

import gui._qt_shim  # noqa: F401 — PySide6↔PyQt6 compat, must be first

from gui.app import main


if __name__ == "__main__":
    raise SystemExit(main())
