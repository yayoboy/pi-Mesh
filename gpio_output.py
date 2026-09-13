"""Buzzer e LED locali azionati dagli eventi della mesh.

La sezione GPIO di Settings salva buzzer e LED in ``gpio_devices``, ma
finora nessuno li pilotava: l'unico codice che toccava i pin era il
pulsante "test" di quella stessa pagina. Qui i dispositivi abilitati
suonano o lampeggiano quando arriva un messaggio dalla mesh — su un
terminale in tasca è l'unica cosa che avvisa senza guardare lo schermo.

Le azioni di encoder e pulsante che la stessa pagina offre (scorri
pagine, invia posizione, allarme) restano NON implementate: sono
ingressi, e dovrebbero pilotare la UI dal server via WebSocket.

Su una macchina senza RPi.GPIO — un PC, o il Pi 5, dove quella libreria
non funziona — ogni chiamata qui è un no-op silenzioso.
"""
import asyncio
import logging
import time

import database

logger = logging.getLogger(__name__)

# Un beep ogni tot secondi al massimo: in una mesh trafficata il buzzer
# suonerebbe di continuo e il terminale diventerebbe inusabile.
COOLDOWN_S = 3.0

_last_fired = 0.0
_running: set[asyncio.Task] = set()   # evita che i task fire-and-forget spariscano


def devices_for(event_type: str, devices: list[dict]) -> list[dict]:
    """Dispositivi di uscita da azionare per questo evento.

    Separata dall'I/O perché è l'unica parte con logica: il resto è
    scrittura di pin, che senza hardware non si può provare.
    """
    if event_type != 'message':
        return []
    out = []
    for dev in devices:
        if not dev.get('enabled'):
            continue
        if dev['type'] == 'buzzer':
            out.append(dev)
        elif dev['type'] == 'led' and dev.get('action') == 'new_message':
            out.append(dev)
    return out


def _pulse(dev: dict, times: int = 2, on_s: float = 0.08, off_s: float = 0.08) -> None:
    """Due impulsi brevi sul pin. Bloccante: chiamare in un thread."""
    import RPi.GPIO as GPIO
    pin = dev['pin_a']
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT)
    try:
        for _ in range(times):
            GPIO.output(pin, GPIO.HIGH)
            time.sleep(on_s)
            GPIO.output(pin, GPIO.LOW)
            time.sleep(off_s)
    finally:
        GPIO.cleanup(pin)


async def notify(db_path: str, event_type: str) -> None:
    """Aziona i dispositivi configurati per l'evento. Non solleva mai."""
    global _last_fired
    now = time.monotonic()
    if now - _last_fired < COOLDOWN_S:
        return
    try:
        devices = devices_for(event_type, await database.get_gpio_devices(db_path))
        if not devices:
            return
        _last_fired = now
        for dev in devices:
            await asyncio.to_thread(_pulse, dev)
    except Exception as e:
        # ImportError su macchine senza RPi.GPIO, o pin occupato: mai
        # far cadere il task che inoltra gli eventi alla UI.
        logger.warning(f'GPIO output error: {e}')


def notify_soon(db_path: str, event_type: str) -> None:
    """Versione fire-and-forget: il beep non deve ritardare il broadcast WS."""
    task = asyncio.create_task(notify(db_path, event_type))
    _running.add(task)
    task.add_done_callback(_running.discard)
