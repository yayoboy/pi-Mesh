# tests/test_messages.py
import pytest
import time
import tempfile
import os
import database


@pytest.fixture
async def db(tmp_path):
    path = str(tmp_path / 'test.db')
    await database.init(path)
    return path


@pytest.mark.asyncio
async def test_save_and_get_broadcast_messages(db):
    await database.save_message(db, '!aaa', 0, 'hello', 1000, False, -8.0, 1, '^all')
    await database.save_message(db, '!bbb', 0, 'world', 1001, False, -5.0, 0, '^all')
    await database.save_message(db, '!ccc', 1, 'ch1',   1002, False, None, None, '^all')
    msgs = await database.get_messages(db, channel=0)
    assert len(msgs) == 2
    assert msgs[0]['text'] == 'hello'
    assert msgs[1]['text'] == 'world'
    assert msgs[0]['node_id'] == '!aaa'
    assert msgs[0]['rx_snr'] == -8.0
    assert msgs[0]['destination'] == '^all'


@pytest.mark.asyncio
async def test_get_messages_pagination(db):
    for i in range(60):
        await database.save_message(db, '!n', 0, f'msg{i}', 1000 + i, False, None, None, '^all')
    page1 = await database.get_messages(db, channel=0, limit=50)
    assert len(page1) == 50
    assert page1[-1]['text'] == 'msg59'
    oldest_id = page1[0]['id']
    page2 = await database.get_messages(db, channel=0, limit=50, before_id=oldest_id)
    assert len(page2) == 10
    assert page2[-1]['text'] == 'msg9'


@pytest.mark.asyncio
async def test_update_message_ack(db):
    await database.save_message(db, '!local', 0, 'hi', 2000, True, None, None, '!peer')
    await database.update_message_ack(db, '!peer')
    import aiosqlite
    async with aiosqlite.connect(db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute('SELECT ack FROM messages WHERE is_outgoing=1 AND destination=?', ('!peer',))
        row = await cur.fetchone()
    assert row['ack'] == 1


@pytest.mark.asyncio
async def test_clear_messages(db):
    await database.save_message(db, '!a', 0, 'x', 1000, False, None, None, '^all')
    await database.clear_messages(db)
    msgs = await database.get_messages(db, channel=0)
    assert msgs == []


@pytest.mark.asyncio
async def test_cleanup_old_messages(db):
    now = int(time.time())
    await database.save_message(db, '!a', 0, 'old', now - 31 * 86400, False, None, None, '^all')
    await database.save_message(db, '!b', 0, 'new', now - 1 * 86400, False, None, None, '^all')
    await database.cleanup_old_messages(db, days=30)
    msgs = await database.get_messages(db, channel=0)
    assert len(msgs) == 1
    assert msgs[0]['text'] == 'new'


@pytest.mark.asyncio
async def test_save_dm_and_get_threads(db):
    # DM from !peer to us (local = !local)
    await database.save_message(db, '!peer', 0, 'Sei lì?', 1000, False, -5.0, 1, '!local')
    await database.save_message(db, '!peer', 0, 'Ciao!',   1001, False, -6.0, 1, '!local')
    # Our reply to !peer
    await database.save_message(db, '!local', 0, 'Sì!', 1002, True, None, None, '!peer')
    threads = await database.get_dm_threads(db, '!local')
    assert len(threads) == 1
    t = threads[0]
    assert t['peer_id'] == '!peer'
    assert t['last_text'] == 'Sì!'
    assert t['last_ts'] == 1002
    assert t['unread'] == 2   # 2 incoming not yet read


@pytest.mark.asyncio
async def test_mark_dm_read(db):
    await database.save_message(db, '!peer', 0, 'msg1', 1000, False, None, None, '!local')
    await database.save_message(db, '!peer', 0, 'msg2', 1001, False, None, None, '!local')
    threads_before = await database.get_dm_threads(db, '!local')
    assert threads_before[0]['unread'] == 2

    await database.mark_dm_read(db, '!peer')
    threads_after = await database.get_dm_threads(db, '!local')
    assert threads_after[0]['unread'] == 0
