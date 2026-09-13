"""capabilities() deve girare ovunque, non solo sul Pi.

Su una macchina di sviluppo (nessun vcgencmd, nessun /dev/i2c-*) il
risultato è tutto False: è il caso che rende la stessa build eseguibile
fuori dal Raspberry, quindi è quello che va verificato.
"""
import config

EXPECTED = {'vcgencmd', 'backlight', 'gpio', 'i2c', 'wifi', 'usb_storage', 'spi_display'}


def test_capabilities_returns_all_keys_as_bool():
    caps = config.capabilities()
    assert set(caps) == EXPECTED
    assert all(isinstance(v, bool) for v in caps.values())


def test_capabilities_is_cached():
    # Stesso dict: il rilevamento non rifà which()/glob a ogni render.
    assert config.capabilities() is config.capabilities()
