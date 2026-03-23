# tests/test_watchdog.py
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

@pytest.mark.asyncio
async def test_db_sync_task_calls_sync(monkeypatch):
    import watchdog, database
    sync_called = []
    async def fake_sync(conn, **kw):
        sync_called.append(1)
    monkeypatch.setattr(database, "sync_to_sd", fake_sync)
    conn = MagicMock()
    task = asyncio.create_task(watchdog.db_sync_task(conn, interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(sync_called) >= 1

@pytest.mark.asyncio
async def test_memory_watchdog_collects_gc(monkeypatch):
    import watchdog, gc
    gc_collected = []
    monkeypatch.setattr(gc, "collect", lambda: gc_collected.append(1))
    broadcast = AsyncMock()
    fake_usage = MagicMock()
    fake_usage.ru_maxrss = 130 * 1024  # 130MB in KB
    with patch("resource.getrusage", return_value=fake_usage):
        task = asyncio.create_task(watchdog.memory_watchdog_task(broadcast, interval=0.01))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    assert len(gc_collected) >= 1
