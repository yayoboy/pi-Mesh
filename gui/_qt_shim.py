"""PySide6 → PyQt6 compatibility shim.

Import this module *before* any ``from PySide6 …`` statement.  It patches
``sys.modules`` so that ``PySide6.*`` names resolve transparently to their
``PyQt6`` counterparts, adding the few alias differences (Signal/Slot/Property).

If PySide6 is genuinely installed the shim is a no-op.
"""

from __future__ import annotations

import importlib
import sys
import types


def _apply_shim() -> None:
    try:
        import PySide6  # noqa: F401 — already available, nothing to do
        return
    except ImportError:
        pass

    try:
        import PyQt6  # noqa: F401
    except ImportError:
        raise ImportError("Neither PySide6 nor PyQt6 is installed")

    _ALIASES = {
        "Signal": "pyqtSignal",
        "Slot": "pyqtSlot",
        "Property": "pyqtProperty",
    }

    _SUBMODULES = ("QtCore", "QtGui", "QtWidgets", "QtSvg", "QtSvgWidgets",
                   "QtOpenGL", "QtOpenGLWidgets", "QtNetwork", "QtSql", "QtTest")

    fake_top = types.ModuleType("PySide6")
    fake_top.__path__ = []
    fake_top.__package__ = "PySide6"
    sys.modules["PySide6"] = fake_top

    for sub in _SUBMODULES:
        pyqt_name = f"PyQt6.{sub}"
        pyside_name = f"PySide6.{sub}"
        try:
            real = importlib.import_module(pyqt_name)
        except ImportError:
            continue

        wrapper = types.ModuleType(pyside_name)
        wrapper.__dict__.update(real.__dict__)
        for alias, original in _ALIASES.items():
            if hasattr(real, original):
                wrapper.__dict__[alias] = getattr(real, original)

        sys.modules[pyside_name] = wrapper
        setattr(fake_top, sub, wrapper)


_apply_shim()
