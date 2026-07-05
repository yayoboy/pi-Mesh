"""Istanza Jinja2 condivisa da main e da tutti i router.

Prima ogni router creava la propria Jinja2Templates: i globals impostati
in main.py (es. map_local_tiles) non esistevano nelle istanze dei router
e nelle pagine rendevano stringa vuota — le tile locali non venivano mai
attivate. I globals dinamici sono callable così riflettono i cambi di
configurazione a runtime (toggle in Config) al render successivo.
"""
from fastapi.templating import Jinja2Templates

import config as cfg

templates = Jinja2Templates(directory='templates')
templates.env.globals['map_local_tiles_fn'] = lambda: '1' if cfg.MAP_LOCAL_TILES else '0'
