import asyncio

import pytest

from gui.core.settings import Settings


# --- pure cache logic --------------------------------------------------------

def test_get_returns_default_when_key_missing():
    async def saver(k, v):  # not called
        pytest.fail("saver should not be called")

    s = Settings(saver=saver)
    assert s.get("missing") is None
    assert s.get("missing", "fallback") == "fallback"


@pytest.mark.asyncio
async def test_load_populates_cache():
    async def saver(k, v):
        pytest.fail("saver should not be called")

    async def loader(keys):
        return {"display.theme": "dark", "display.brightness": "200"}

    s = Settings(saver=saver, loop=asyncio.get_running_loop())
    await s.load(loader, ["display.theme", "display.brightness"])

    assert s.get("display.theme") == "dark"
    assert s.get("display.brightness") == "200"


@pytest.mark.asyncio
async def test_set_updates_cache_immediately():
    saved: list[tuple[str, str]] = []

    async def saver(k, v):
        saved.append((k, v))

    s = Settings(saver=saver, loop=asyncio.get_running_loop())
    s.set("foo", "bar")

    # Cache is updated synchronously, before the saver task runs
    assert s.get("foo") == "bar"

    await s.flush()
    assert saved == [("foo", "bar")]


@pytest.mark.asyncio
async def test_set_schedules_async_write_on_running_loop():
    write_event = asyncio.Event()
    saved: list[tuple[str, str]] = []

    async def saver(k, v):
        saved.append((k, v))
        write_event.set()

    s = Settings(saver=saver, loop=asyncio.get_running_loop())
    s.set("display.theme", "light")

    await asyncio.wait_for(write_event.wait(), timeout=1.0)
    assert saved == [("display.theme", "light")]


@pytest.mark.asyncio
async def test_set_without_loop_warns_and_drops_write(caplog):
    saved: list[tuple[str, str]] = []

    async def saver(k, v):
        saved.append((k, v))

    s = Settings(saver=saver, loop=None)
    # Force the discovery of the running loop to fail by using a fake helper.
    # We patch the static method on the instance.
    s._running_loop = staticmethod(lambda: None)  # type: ignore[method-assign]

    with caplog.at_level("WARNING"):
        s.set("foo", "bar")

    assert s.get("foo") == "bar"  # cache still updated
    assert saved == []  # nothing persisted
    assert any("no loop available" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_set_swallows_saver_exceptions(caplog):
    async def saver(k, v):
        raise RuntimeError("DB unavailable")

    s = Settings(saver=saver, loop=asyncio.get_running_loop())

    with caplog.at_level("WARNING"):
        s.set("foo", "bar")
        await s.flush()

    assert s.get("foo") == "bar"
    assert any("DB unavailable" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_multiple_writes_resolve_in_flush():
    saved: list[tuple[str, str]] = []

    async def saver(k, v):
        await asyncio.sleep(0)  # yield to loop
        saved.append((k, v))

    s = Settings(saver=saver, loop=asyncio.get_running_loop())
    for i in range(5):
        s.set(f"key{i}", str(i))

    await s.flush()
    assert sorted(saved) == [(f"key{i}", str(i)) for i in range(5)]


@pytest.mark.asyncio
async def test_get_settings_singleton_raises_when_not_initialised():
    import gui.core.settings as mod

    # Reset the module-level singleton in case other tests left one behind.
    mod._singleton = None
    from gui.core.settings import get_settings

    with pytest.raises(RuntimeError, match="not initialised"):
        get_settings()


@pytest.mark.asyncio
async def test_init_from_database_round_trip(tmp_path):
    import database

    db = tmp_path / "test_settings.db"
    await database.init(str(db))
    await database.set_setting("display.theme", "hc")

    from gui.core.settings import init_from_database, get_settings

    s = await init_from_database(str(db))
    assert s is get_settings()
    assert s.get("display.theme") == "hc"
    assert s.get("display.brightness") is None  # not set in DB

    s.set("display.theme", "light")
    await s.flush()

    # Verify persisted
    val = await database.get_setting("display.theme")
    assert val == "light"

    await database.close()
