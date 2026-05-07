import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch


@pytest.fixture(autouse=True)
async def _reset_database_singleton():
    """Reset the module-level ``database._db`` connection between tests.

    Without this each test inherits the previous test's connection (and its
    ``_db_path``), so tests that use a fresh ``tmp_path`` DB end up reading or
    writing to a stale file — surfaces as ``sqlite3.OperationalError: no such
    table`` and unread-count drift in test_database / test_messages.

    The fixture must be async so we can ``await database.close()`` cleanly;
    pytest-asyncio (asyncio_mode = auto) auto-applies it to sync tests too.
    """
    yield
    import database

    if database._db is not None:
        try:
            await database.close()
        except Exception:
            database._db = None
    database._db_path = None


@pytest.fixture
def mock_client():
    """Mock meshtasticd_client module for tests that don't need real board."""
    with patch('meshtasticd_client.get_nodes') as mock_nodes, \
         patch('meshtasticd_client.is_connected') as mock_conn:
        mock_conn.return_value = True
        mock_nodes.return_value = [
            {
                'id': '!aabbccdd',
                'short_name': 'TEST',
                'long_name': 'Test Node',
                'latitude': 41.9,
                'longitude': 12.5,
                'last_heard': 1700000000,
                'snr': 8.0,
                'battery_level': 85,
                'hop_count': 0,
                'hw_model': 'HELTEC_V3',
                'is_local': True,
            }
        ]
        yield {'nodes': mock_nodes, 'connected': mock_conn}


@pytest.fixture
async def client(mock_client):
    """Async HTTP client for testing FastAPI app."""
    from main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
    ) as ac:
        yield ac
