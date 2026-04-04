import asyncio
import pytest
import database


@pytest.fixture
def tmp_db(tmp_path):
    path = str(tmp_path / 'test.db')
    asyncio.run(database.init(path))
    yield path
    asyncio.run(database.close())


def test_canned_messages_empty_on_init(tmp_db):
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs == []


def test_canned_messages_add_and_get(tmp_db):
    msg_id = asyncio.run(database.add_canned_message('CQ CQ'))
    assert isinstance(msg_id, int)
    msgs = asyncio.run(database.get_canned_messages())
    assert len(msgs) == 1
    assert msgs[0]['text'] == 'CQ CQ'
    assert msgs[0]['sort_order'] == 0


def test_canned_messages_update(tmp_db):
    msg_id = asyncio.run(database.add_canned_message('CQ CQ'))
    asyncio.run(database.update_canned_message(msg_id, 'CQ DX', 5))
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs[0]['text'] == 'CQ DX'
    assert msgs[0]['sort_order'] == 5


def test_canned_messages_delete(tmp_db):
    msg_id = asyncio.run(database.add_canned_message('CQ CQ'))
    asyncio.run(database.delete_canned_message(msg_id))
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs == []


def test_canned_messages_order_by_sort_order(tmp_db):
    asyncio.run(database.add_canned_message('B', sort_order=10))
    asyncio.run(database.add_canned_message('A', sort_order=1))
    msgs = asyncio.run(database.get_canned_messages())
    assert msgs[0]['text'] == 'A'
    assert msgs[1]['text'] == 'B'
