"""``python -m gui`` entry point. Delegates to :mod:`gui.app`."""

from gui.app import main


if __name__ == "__main__":
    raise SystemExit(main())
