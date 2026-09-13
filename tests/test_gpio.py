"""Selezione dei dispositivi di uscita e cooldown del buzzer.

L'I/O sui pin non è provabile senza hardware (lgpio ha wheel solo per
Linux); quello che si può rompere in silenzio è la scelta di *quali*
dispositivi azionare e il freno che evita un beep per ogni pacchetto.
"""
import pytest

import gpio

BUZZER     = {'type': 'buzzer', 'enabled': 1, 'pin_a': 18, 'action': None}
BUZZER_OFF = {'type': 'buzzer', 'enabled': 0, 'pin_a': 19, 'action': None}
LED_MSG    = {'type': 'led',    'enabled': 1, 'pin_a': 23, 'action': 'new_message'}
LED_GPS    = {'type': 'led',    'enabled': 1, 'pin_a': 24, 'action': 'gps_fix'}


def test_message_fires_buzzers_and_new_message_leds():
    got = gpio.devices_for('message', [BUZZER, LED_MSG, LED_GPS, BUZZER_OFF])
    assert got == [BUZZER, LED_MSG]


def test_other_events_fire_nothing():
    assert gpio.devices_for('position', [BUZZER, LED_MSG]) == []


@pytest.mark.asyncio
async def test_cooldown_swallows_the_second_message(monkeypatch):
    fired = []

    async def fake_devices(db_path):
        return [BUZZER]

    monkeypatch.setattr(gpio.database, 'get_gpio_devices', fake_devices)
    monkeypatch.setattr(gpio, 'pulse', lambda pin: fired.append(pin))
    gpio._last_fired = 0.0

    await gpio.notify('unused.db', 'message')
    await gpio.notify('unused.db', 'message')

    assert fired == [18]


@pytest.mark.asyncio
async def test_notify_survives_missing_lgpio(monkeypatch):
    async def fake_devices(db_path):
        return [BUZZER]

    def boom(pin):
        raise ImportError('No module named lgpio')

    monkeypatch.setattr(gpio.database, 'get_gpio_devices', fake_devices)
    monkeypatch.setattr(gpio, 'pulse', boom)
    gpio._last_fired = 0.0

    await gpio.notify('unused.db', 'message')   # non deve sollevare
