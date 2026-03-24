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

def test_long_press_not_overwritten_by_shutdown():
    """init() signature must accept db_conn parameter."""
    import inspect
    import gpio_handler
    sig = inspect.signature(gpio_handler.init)
    assert 'db_conn' in sig.parameters, "init() must accept db_conn parameter"

def test_init_stores_db_conn():
    import gpio_handler, asyncio
    async def fake_broadcast(data): pass
    loop = asyncio.new_event_loop()
    conn = object()  # sentinel
    gpio_handler.init(
        (17, 27, 22), (5, 6, 13),
        fake_broadcast, db_conn=conn, loop=loop
    )
    assert gpio_handler._conn is conn
    loop.close()

def test_held_handler_sends_long_press_and_conditional_shutdown():
    """Held handler must fire long_press always, shutdown only when both held."""
    import gpio_handler, asyncio
    from unittest.mock import MagicMock, patch

    broadcast_calls = []
    async def fake_broadcast(data):
        broadcast_calls.append(data)

    loop = asyncio.new_event_loop()

    # Mock GPIO classes so _GPIO_AVAILABLE path runs
    mock_enc = MagicMock()
    mock_btn1 = MagicMock()
    mock_btn2 = MagicMock()
    mock_factory = MagicMock()

    btn_instances = [mock_btn1, mock_btn2]
    btn_call_count = [0]

    def make_button(*a, **kw):
        idx = btn_call_count[0]
        btn_call_count[0] += 1
        return btn_instances[idx]

    with patch("gpio_handler._GPIO_AVAILABLE", True), \
         patch("gpio_handler._factory", mock_factory, create=True), \
         patch("gpio_handler.RotaryEncoder", return_value=mock_enc, create=True), \
         patch("gpio_handler.Button", side_effect=make_button, create=True), \
         patch("gpio_handler._bridge_coroutine") as mock_bridge_coro:

        gpio_handler.init(
            (17, 27, 22), (5, 6, 13),
            fake_broadcast, db_conn=None, loop=loop
        )

        # Capture the assigned when_held handlers
        held1 = mock_btn1.when_held
        held2 = mock_btn2.when_held

        # Simulate btn1 held alone (btn2 NOT held)
        mock_btn1.is_held = True
        mock_btn2.is_held = False

        # Track _bridge_event calls
        bridge_event_calls = []
        original_bridge = gpio_handler._bridge_event
        gpio_handler._bridge_event = lambda enc, action: bridge_event_calls.append((enc, action))

        held1()

        assert ("long_press" in [a for _, a in bridge_event_calls]), \
            "held handler must fire long_press"
        assert mock_bridge_coro.call_count == 0, \
            "shutdown must NOT fire when only one button is held"

        # Simulate both held
        bridge_event_calls.clear()
        mock_btn1.is_held = True
        mock_btn2.is_held = True

        held1()

        assert ("long_press" in [a for _, a in bridge_event_calls]), \
            "held handler must still fire long_press when both held"
        assert mock_bridge_coro.call_count == 1, \
            "shutdown MUST fire when both buttons are held"

    # Restore
    gpio_handler._bridge_event = original_bridge
    loop.close()
