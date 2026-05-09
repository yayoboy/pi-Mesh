"""GUI application bootstrap.

Glue between Qt (`QApplication` + `qasync`), the FastAPI/uvicorn stack used
by the web UI, the meshtasticd client and the rest of the backend. Owns the
async lifecycle: setup → run until window closed → teardown.

Entry point: ``python -m gui`` calls :func:`main`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

log = logging.getLogger("gui.app")


def _setup_logging() -> None:
    import config as cfg

    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _build_qapplication():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("pi-Mesh")
    app.setOrganizationName("pi-Mesh")
    app.setStyle("Fusion")
    return app


def apply_theme(app, palette_name: str = "dark", custom: dict | None = None) -> None:
    """Apply a palette to the running ``QApplication``.

    Sets both QSS (controls all custom styling) and QPalette (so native
    widgets that ignore stylesheets — file dialogs, message boxes — still
    pick up the colors).
    """
    from PySide6.QtGui import QColor, QPalette

    from gui.theme.palettes import PALETTES, get_palette
    from gui.theme.qss import build_qss

    if palette_name not in PALETTES and palette_name != "custom":
        palette_name = "dark"
    palette = get_palette(palette_name, custom=custom)
    app.setStyleSheet(build_qss(palette))

    qp = app.palette()
    qp.setColor(QPalette.ColorRole.Window,          QColor(palette["bg"]))
    qp.setColor(QPalette.ColorRole.WindowText,      QColor(palette["text"]))
    qp.setColor(QPalette.ColorRole.Base,            QColor(palette["panel"]))
    qp.setColor(QPalette.ColorRole.AlternateBase,   QColor(palette["bg"]))
    qp.setColor(QPalette.ColorRole.ToolTipBase,     QColor(palette["panel"]))
    qp.setColor(QPalette.ColorRole.ToolTipText,     QColor(palette["text"]))
    qp.setColor(QPalette.ColorRole.Text,            QColor(palette["text"]))
    qp.setColor(QPalette.ColorRole.Button,          QColor(palette["panel"]))
    qp.setColor(QPalette.ColorRole.ButtonText,      QColor(palette["text"]))
    qp.setColor(QPalette.ColorRole.Highlight,       QColor(palette["accent"]))
    qp.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    qp.setColor(QPalette.ColorRole.Link,            QColor(palette["accent"]))
    app.setPalette(qp)


async def _async_main(app, window, *, embed_uvicorn: bool) -> None:
    """Backend setup → run until window closes → teardown.

    Mirrors ``main.py:lifespan`` but lives inside the qasync-driven loop
    so the GUI and uvicorn share one thread.
    """
    import config as cfg
    import database
    import meshtasticd_client

    from gui.core.eventbus import EventBus
    from gui.core.settings import init_from_database

    await database.init(cfg.DB_PATH)
    await database.cleanup_old_messages(cfg.DB_PATH, days=30)

    settings = await init_from_database(cfg.DB_PATH)

    apply_theme(app, settings.get("display.theme", "dark") or "dark")

    # Hot-reload: when display.theme changes (from the Config page or via
    # /api/config/display_theme), re-apply the palette without restarting.
    settings.subscribe("display.theme", lambda v: apply_theme(app, (v or "dark")))
    settings.subscribe("pimesh-accent", lambda _v: apply_theme(app, settings.get("display.theme", "dark") or "dark"))

    await meshtasticd_client.load_nodes_from_db()

    bus = EventBus()
    window.attach(bus, settings)

    from bots import runner as bots_runner
    await bots_runner.start(cfg.DB_PATH)

    background = [
        asyncio.create_task(meshtasticd_client.connect()),
        bus.start(),
    ]

    server = None
    if embed_uvicorn:
        import uvicorn
        from main import app as fastapi_app

        host = os.environ.get("PIMESH_GUI_HOST", "0.0.0.0")
        port = int(os.environ.get("PIMESH_GUI_PORT", "8080"))
        cfg_uv = uvicorn.Config(fastapi_app, host=host, port=port, log_level="warning", loop="asyncio")
        server = uvicorn.Server(cfg_uv)
        background.append(asyncio.create_task(server.serve()))
        log.info("Embedded uvicorn listening on http://%s:%d", host, port)

    window.show()

    quit_future: asyncio.Future = asyncio.Future()
    app.aboutToQuit.connect(lambda: (not quit_future.done()) and quit_future.set_result(None))

    try:
        await quit_future
    finally:
        log.info("shutting down")
        if server is not None:
            server.should_exit = True
        for t in background:
            t.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        try:
            await bots_runner.stop()
        except Exception:
            log.exception("bots runner stop failed")
        try:
            await meshtasticd_client.disconnect()
        except Exception:
            log.exception("disconnect failed")
        await database.close()


def main() -> int:
    _setup_logging()

    import qasync

    app = _build_qapplication()
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    from gui.main_window import MainWindow

    window = MainWindow()

    embed_uvicorn = os.environ.get("PIMESH_GUI_EMBEDDED_UVICORN", "0") != "0"

    with loop:
        try:
            loop.run_until_complete(_async_main(app, window, embed_uvicorn=embed_uvicorn))
        except KeyboardInterrupt:
            log.info("interrupted")

    return 0
