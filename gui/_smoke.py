"""Fase 0 / Task 0.2 — Smoke test: QApplication + qasync + uvicorn nello stesso loop.

Scopo: validare che PySide6, qasync e uvicorn coesistano nello stesso event loop
asyncio prima di iniziare il porting vero e proprio.

Esecuzione:
    python -m gui._smoke

La finestra resta aperta 5 s, intanto un endpoint HTTP risponde su :8081/ping
e un task asyncio logga "tick" ogni secondo. Esce con codice 0 se tutto fila.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gui.smoke")


def _build_fastapi() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    return app


async def _ticker(stop: asyncio.Event) -> None:
    n = 0
    while not stop.is_set():
        n += 1
        log.info("tick %d", n)
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            continue


async def _shutdown_after(seconds: float, stop: asyncio.Event, qapp) -> None:
    await asyncio.sleep(seconds)
    log.info("smoke window timeout reached, quitting")
    stop.set()
    qapp.quit()


def main() -> int:
    from PySide6.QtWidgets import QApplication, QLabel
    from PySide6.QtCore import Qt
    import qasync
    import uvicorn

    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    label = QLabel("Hello pi-Mesh\n(smoke test, 5s)")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setMinimumSize(320, 120)
    label.show()

    stop = asyncio.Event()
    server_config = uvicorn.Config(
        _build_fastapi(),
        host="127.0.0.1",
        port=8081,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(server_config)

    with loop:
        loop.create_task(_ticker(stop))
        loop.create_task(server.serve())
        loop.create_task(_shutdown_after(5.0, stop, app))
        loop.run_forever()

    log.info("smoke test finished cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
