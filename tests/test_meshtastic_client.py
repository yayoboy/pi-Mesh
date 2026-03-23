# tests/test_meshtastic_client.py
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

@pytest.fixture(autouse=True)
def reset_module():
    # Reset state tra i test
    import sys
    # Rimuovi il modulo dalla cache per resettare le variabili module-level
    if 'meshtastic_client' in sys.modules:
        del sys.modules['meshtastic_client']
    yield
    if 'meshtastic_client' in sys.modules:
        del sys.modules['meshtastic_client']

def test_is_connected_false_initially():
    import meshtastic_client as mc
    assert mc.is_connected() is False

def test_init_sets_loop_and_broadcast():
    import meshtastic_client as mc
    loop = asyncio.new_event_loop()
    broadcast = AsyncMock()
    mc.init(loop, broadcast)
    assert mc._loop is loop
    assert mc._broadcast is broadcast
    loop.close()

def test_parse_message_valid():
    import meshtastic_client as mc
    packet = {
        "fromId": "!abc123",
        "channel": 1,
        "decoded": {"text": "ciao"},
        "rxTime": 1700000000,
        "rxSnr": 7.5,
        "rxRssi": -90,
    }
    result = mc._parse_message(packet)
    assert result["node_id"] == "!abc123"
    assert result["text"] == "ciao"
    assert result["rx_snr"] == 7.5

def test_parse_message_malformed_returns_none():
    import meshtastic_client as mc
    result = mc._parse_message(None)
    assert result is None

@pytest.mark.asyncio
async def test_connect_sets_connected_on_success():
    import meshtastic_client as mc
    with patch("meshtastic.serial_interface.SerialInterface") as mock_si:
        mock_si.return_value = MagicMock()
        mc._loop = asyncio.get_event_loop()
        mc._broadcast = AsyncMock()
        await mc.connect()
        assert mc.is_connected() is True
