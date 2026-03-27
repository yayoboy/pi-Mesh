import asyncio, logging, time
import config as cfg

_loop      = None
_broadcast = None
_conn      = None
_buzzer    = None

try:
    from gpiozero import RotaryEncoder, Button
    # Prefer lgpio (available on Raspberry Pi OS Bookworm/Trixie via python3-lgpio).
    # Fall back to pigpio for older distros where pigpiod is still present.
    try:
        from gpiozero.pins.lgpio import LGPIOFactory
        _factory = LGPIOFactory()
        logging.info("GPIO: usando LGPIOFactory (lgpio)")
    except Exception:
        from gpiozero.pins.pigpio import PiGPIOFactory
        _factory = PiGPIOFactory()
        logging.info("GPIO: usando PiGPIOFactory (pigpio)")
    _GPIO_AVAILABLE = True
except Exception:
    logging.warning("gpiozero non disponibile — GPIO disabilitato")
    _GPIO_AVAILABLE = False

def init(enc1_pins: tuple, enc2_pins: tuple, broadcast_fn, db_conn=None, loop=None):
    global _loop, _broadcast, _conn, _buzzer
    _broadcast = broadcast_fn
    _conn = db_conn
    _loop = loop or asyncio.get_event_loop()

    if not _GPIO_AVAILABLE:
        return

    enc1 = RotaryEncoder(enc1_pins[0], enc1_pins[1], pin_factory=_factory, wrap=False, max_steps=0)
    btn1 = Button(enc1_pins[2], pin_factory=_factory, hold_time=1.0)
    enc2 = RotaryEncoder(enc2_pins[0], enc2_pins[1], pin_factory=_factory, wrap=False, max_steps=0)
    btn2 = Button(enc2_pins[2], pin_factory=_factory, hold_time=1.0)

    def make_handler(encoder_num, action):
        def handler():
            _bridge_event(encoder_num, action)
        return handler

    enc1.when_rotated_clockwise          = make_handler(1, "cw")
    enc1.when_rotated_counter_clockwise  = make_handler(1, "ccw")
    btn1.when_pressed                    = make_handler(1, "press")
    enc2.when_rotated_clockwise          = make_handler(2, "cw")
    enc2.when_rotated_counter_clockwise  = make_handler(2, "ccw")
    btn2.when_pressed                    = make_handler(2, "press")

    def make_held_handler(encoder_num):
        def handler():
            # Always send long_press for UI navigation
            _bridge_event(encoder_num, "long_press")
            # Shutdown only when BOTH buttons are held simultaneously
            if btn1.is_held and btn2.is_held:
                logging.info("Gesture shutdown rilevata")
                _bridge_coroutine(_graceful_shutdown())
        return handler

    btn1.when_held = make_held_handler(1)
    btn2.when_held = make_held_handler(2)

    if cfg.BUZZER_PIN:
        try:
            from gpiozero import TonalBuzzer
            _buzzer = TonalBuzzer(cfg.BUZZER_PIN, pin_factory=_factory)
        except Exception as e:
            logging.warning(f"Buzzer non disponibile: {e}")

def _bridge_event(encoder_num: int, action: str):
    if _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(
            _broadcast({"type": "encoder", "data": {
                "encoder": encoder_num,
                "action":  action,
                "ts":      int(time.time())
            }}),
            _loop
        )

def _bridge_coroutine(coro):
    if _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(coro, _loop)

def beep(pattern: str = "single"):
    """Emit a beep on the optional piezo buzzer.
    pattern: 'single' (1 short beep), 'double' (2 short beeps)
    No-op if no buzzer is configured.
    """
    if not _buzzer:
        return
    import threading, time

    def _play():
        try:
            if pattern == "single":
                _buzzer.play(440)
                time.sleep(0.1)
                _buzzer.stop()
            elif pattern == "double":
                for _ in range(2):
                    _buzzer.play(440)
                    time.sleep(0.08)
                    _buzzer.stop()
                    time.sleep(0.08)
        except Exception as e:
            logging.debug(f"beep error: {e}")

    threading.Thread(target=_play, daemon=True).start()

async def _graceful_shutdown():
    import database, os
    if _conn:
        await database.sync_to_sd(_conn)
    os.system("sudo shutdown -h now")
