# tests/test_gpio_handler.py
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio, pytest

def test_init_calls_gpiozero_with_correct_pins():
    mock_enc = MagicMock()
    mock_btn = MagicMock()
    broadcast = AsyncMock()
    loop = asyncio.new_event_loop()
    import gpio_handler
    with patch.object(gpio_handler, '_GPIO_AVAILABLE', True), \
         patch('gpio_handler.RotaryEncoder', mock_enc, create=True), \
         patch('gpio_handler.Button', mock_btn, create=True), \
         patch('gpio_handler._factory', MagicMock(), create=True):
        gpio_handler.init((17, 27, 22), (5, 6, 13), broadcast, loop=loop)
        assert mock_enc.call_count == 2
        assert mock_btn.call_count == 2
    loop.close()

def test_bridge_event_sends_to_loop():
    loop = asyncio.new_event_loop()
    broadcast = AsyncMock()
    import gpio_handler
    gpio_handler._loop = loop
    gpio_handler._broadcast = broadcast
    # non crashare
    gpio_handler._bridge_event(1, 'cw')
    loop.close()
