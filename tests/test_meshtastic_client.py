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

# Bug 1: concurrent connect() calls must not stack — SerialInterface called only once
@pytest.mark.asyncio
async def test_connect_not_reentrant():
    import meshtastic_client as mc
    mc._loop = asyncio.get_event_loop()
    mc._broadcast = AsyncMock()
    si_call_count = 0

    class SlowSI:
        def __init__(self, *a, **kw):
            nonlocal si_call_count
            si_call_count += 1

    with patch("meshtastic.serial_interface.SerialInterface", SlowSI):
        # Fire two concurrent connect() tasks
        t1 = asyncio.create_task(mc.connect())
        t2 = asyncio.create_task(mc.connect())
        await asyncio.gather(t1, t2, return_exceptions=True)

    # _is_connecting guard must ensure SerialInterface is only created once
    assert si_call_count == 1, f"Expected 1 SerialInterface init, got {si_call_count}"

# Bug 2: send_message must use asyncio.to_thread
@pytest.mark.asyncio
async def test_send_message_uses_to_thread():
    import meshtastic_client as mc
    mock_iface = MagicMock()
    mc._interface = mock_iface
    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        await mc.send_message("ciao", 0, "^all")
        mock_thread.assert_called_once()

# Bug 7: _bridge logs errors from failed coroutines
def test_bridge_adds_done_callback():
    import meshtastic_client as mc
    loop = asyncio.new_event_loop()
    mc._loop = loop
    async def failing():
        raise ValueError("test error")
    future = MagicMock()
    future.cancelled.return_value = False
    future.result.side_effect = ValueError("test error")
    with patch("asyncio.run_coroutine_threadsafe", return_value=future) as mock_rcts:
        mc._bridge(failing())
        mock_rcts.assert_called_once()
        future.add_done_callback.assert_called_once()
    loop.close()
