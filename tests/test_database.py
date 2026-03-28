# tests/test_database.py
import asyncio, os, pytest, time

@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test.db"), str(tmp_path / "persistent.db")

@pytest.mark.asyncio
async def test_init_creates_tables(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in await cur.fetchall()}
    assert {"messages", "nodes", "telemetry", "sensor_readings"} <= tables
    await conn.close()

@pytest.mark.asyncio
async def test_save_and_get_message(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    ts = int(time.time())
    await database.save_message(conn, "node1", 0, "hello", ts, 0, 1.5, -90)
    msgs = await database.get_messages(conn, 0, limit=10)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "hello"
    await conn.close()

@pytest.mark.asyncio
async def test_save_and_get_node(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    await database.save_node(conn, {
        "id": "abc123", "long_name": "Test Node", "short_name": "TST",
        "hw_model": "HELTEC_V3", "battery_level": 80, "voltage": 3.8,
        "snr": 5.0, "last_heard": int(time.time()),
        "latitude": 41.9, "longitude": 12.5, "altitude": 50, "is_local": 1,
        "rssi": None, "firmware_version": None, "role": None
    })
    nodes = await database.get_nodes(conn)
    assert len(nodes) == 1
    assert nodes[0]["id"] == "abc123"
    await conn.close()

@pytest.mark.asyncio
async def test_sync_to_sd(tmp_db, tmp_path):
    import database
    runtime, _ = tmp_db
    persistent = str(tmp_path / "sync_persistent.db")
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    await database.sync_to_sd(conn, runtime_path=runtime, persistent_path=persistent)
    assert os.path.exists(persistent)
    await conn.close()

@pytest.mark.asyncio
async def test_get_messages_pagination(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    for i in range(10):
        await database.save_message(conn, "n1", 0, f"msg{i}", i+1, 0, None, None)
    page1 = await database.get_messages(conn, 0, limit=5)
    assert len(page1) == 5
    oldest_id = page1[-1]["id"]
    page2 = await database.get_messages(conn, 0, limit=5, before_id=oldest_id)
    assert len(page2) == 5
    await conn.close()

@pytest.mark.asyncio
async def test_prune_sensor_readings():
    import database
    conn = await database.init_db(runtime_path=":memory:", persistent_path="/nonexistent")
    # Insert 20 readings
    for i in range(20):
        await database.save_sensor_reading(conn, "bme280", {"temp": i})
    # Prune keeping only last 5
    await database.prune_sensor_readings(conn, max_rows=5)
    rows = await database.get_sensor_readings(conn, "bme280", limit=100)
    assert len(rows) == 5
    await conn.close()

@pytest.mark.asyncio
async def test_save_message_stores_destination(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    ts = int(time.time())
    await database.save_message(conn, "node1", 0, "ciao", ts, 0, None, None, destination="!abc123")
    msgs = await database.get_messages(conn, 0, limit=10)
    assert msgs[0]["destination"] == "!abc123"
    await conn.close()

@pytest.mark.asyncio
async def test_get_dm_threads_returns_threads_with_unread(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    ts = int(time.time())
    await database.save_message(conn, "!node1", 0, "ciao", ts,   0, None, None, destination="!local")
    await database.save_message(conn, "!node1", 0, "ok?",  ts+1, 0, None, None, destination="!local")
    await database.save_message(conn, "local",  0, "si!",  ts+2, 1, None, None, destination="!node1")
    threads = await database.get_dm_threads(conn)
    assert len(threads) == 1
    assert threads[0]["peer"] == "!node1"
    assert threads[0]["unread_count"] == 2
    await conn.close()

@pytest.mark.asyncio
async def test_get_dm_messages_returns_thread(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    ts = int(time.time())
    await database.save_message(conn, "!peer1", 0, "dm in",  ts,   0, None, None, destination="!local")
    await database.save_message(conn, "local",  0, "dm out", ts+1, 1, None, None, destination="!peer1")
    await database.save_message(conn, "!other", 0, "other",  ts+2, 0, None, None, destination="!local")
    msgs = await database.get_dm_messages(conn, "!peer1")
    assert len(msgs) == 2
    assert all(m["text"] in ("dm in", "dm out") for m in msgs)
    await conn.close()

@pytest.mark.asyncio
async def test_mark_dm_read_clears_unread(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    ts = int(time.time())
    await database.save_message(conn, "!peer1", 0, "msg1", ts,   0, None, None, destination="!local")
    await database.save_message(conn, "!peer1", 0, "msg2", ts+1, 0, None, None, destination="!local")
    threads_before = await database.get_dm_threads(conn)
    assert threads_before[0]["unread_count"] == 2
    await database.mark_dm_read(conn, "!peer1")
    threads_after = await database.get_dm_threads(conn)
    assert threads_after[0]["unread_count"] == 0
    await conn.close()

@pytest.mark.asyncio
async def test_save_and_get_marker(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    marker_id = await database.save_marker(conn, "Test", "poi", 45.0, 9.0)
    markers = await database.get_markers(conn)
    assert len(markers) == 1
    assert markers[0]["label"] == "Test"
    assert markers[0]["id"] == marker_id
    await conn.close()

@pytest.mark.asyncio
async def test_delete_marker(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    mid = await database.save_marker(conn, "Del", "poi", 45.0, 9.0)
    await database.delete_marker(conn, mid)
    markers = await database.get_markers(conn)
    assert len(markers) == 0
    await conn.close()

@pytest.mark.asyncio
async def test_save_and_get_traceroute(tmp_db):
    import database
    runtime, persistent = tmp_db
    conn = await database.init_db(runtime_path=runtime, persistent_path=persistent)
    hops = ["!local", "!a1b2c3d4", "!dest0001"]
    tid = await database.save_traceroute(conn, "!dest0001", hops)
    results = await database.get_traceroutes(conn, "!dest0001")
    assert len(results) == 1
    assert results[0]["hops"] == hops
    assert results[0]["id"] == tid
    await conn.close()
