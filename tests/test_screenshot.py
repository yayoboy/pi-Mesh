# tests/test_screenshot.py
"""KMS screenshot: the VC4 detile pass runs on Raspberry only."""
import asyncio

import routers.commands as commands


class _Proc:
    returncode = 0

    async def communicate(self):
        return b'', b''


def _capture(monkeypatch, vc4: bool):
    calls = []

    async def fake_exec(*argv, **kwargs):
        calls.append(argv)
        return _Proc()

    monkeypatch.setattr(commands._asyncio, 'create_subprocess_exec', fake_exec)
    monkeypatch.setattr(commands, '_vc4_loaded', lambda: vc4)
    assert asyncio.run(commands._capture_kms('/out/shot.png')) is None
    return calls


def test_raspberry_detiles(monkeypatch):
    calls = _capture(monkeypatch, vc4=True)
    assert len(calls) == 2
    assert calls[0][-1] == commands._KMS_TILED_TMP
    assert calls[1][1] == commands._DETILER and calls[1][-1] == '/out/shot.png'


def test_other_boards_keep_kmsgrab_output(monkeypatch):
    calls = _capture(monkeypatch, vc4=False)
    assert len(calls) == 1
    assert calls[0][-1] == '/out/shot.png'
