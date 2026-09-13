"""GPIO locale: buzzer e LED sugli eventi della mesh, più le primitive
che la pagina Settings usa per il pulsante "test".

Qui si parla al GPIO con **lgpio**, non con RPi.GPIO: quest'ultima parla
solo ai chip Broadcom, quindi non funziona sul Pi 5 (dove il chip è
diverso) né su una scheda che Raspberry non è — Orange Pi, Allwinner,
Rockchip. lgpio lavora sul gpiochip del kernel, che c'è su qualunque
Linux, e ha wheel precompilate per armv7l e aarch64.

Il numero di pin è il numero di LINEA del gpiochip, che su Raspberry
coincide col numero BCM stampato sull'header. Se il tuo header sta su un
altro chip (il Pi 5 con certi kernel, o un SoC con più banchi come
l'Allwinner, dove i pin si chiamano PB0/PH8), cambia ``GPIO_CHIP`` in
config.env: ``gpiodetect`` elenca i chip disponibili e ``gpioinfo`` le
loro linee.

Le azioni di encoder e pulsante che la pagina Settings offre (scorri
pagine, invia posizione, allarme) restano NON implementate: sono
ingressi, e dovrebbero pilotare la UI dal server via WebSocket.
"""
import asyncio
import logging
import time

import config as cfg
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


def pulse(pin: int, times: int = 2, on_s: float = 0.08, off_s: float = 0.08) -> None:
    """Impulsi brevi su un pin di uscita. Bloccante: chiamare in un thread."""
    import lgpio
    handle = lgpio.gpiochip_open(cfg.GPIO_CHIP)
    try:
        lgpio.gpio_claim_output(handle, pin, 0)
        for _ in range(times):
            lgpio.gpio_write(handle, pin, 1)
            time.sleep(on_s)
            lgpio.gpio_write(handle, pin, 0)
            time.sleep(off_s)
        lgpio.gpio_free(handle, pin)
    finally:
        lgpio.gpiochip_close(handle)


def read(pin: int, pull_up: bool = True) -> int:
    """Livello di un pin di ingresso (1/0). Bloccante: chiamare in un thread."""
    import lgpio
    handle = lgpio.gpiochip_open(cfg.GPIO_CHIP)
    try:
        lgpio.gpio_claim_input(handle, pin, lgpio.SET_BIAS_PULL_UP if pull_up else 0)
        value = lgpio.gpio_read(handle, pin)
        lgpio.gpio_free(handle, pin)
        return value
    finally:
        lgpio.gpiochip_close(handle)


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
            await asyncio.to_thread(pulse, dev['pin_a'])
    except Exception as e:
        # ImportError dove lgpio non è installato, o pin già occupato: mai
        # far cadere il task che inoltra gli eventi alla UI.
        logger.warning(f'GPIO output error: {e}')


def notify_soon(db_path: str, event_type: str) -> None:
    """Versione fire-and-forget: il beep non deve ritardare il broadcast WS."""
    task = asyncio.create_task(notify(db_path, event_type))
    _running.add(task)
    task.add_done_callback(_running.discard)
