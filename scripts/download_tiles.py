#!/usr/bin/env python3
"""
Download offline map tiles for Italy (OSM, OpenTopoMap, ESRI satellite).
Stores tiles as static/tiles/{source}/{z}/{x}/{y}.png

Parallel version: uses ThreadPoolExecutor per source.
  - OSM / Topo  : max 2 workers (OSM usage policy)
  - Satellite   : max 8 workers (ESRI, less restrictive)

Run from the pi-Mesh project root directory.
"""
import math, os, ssl, sys, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# macOS Python from python.org lacks system CA certs; use certifi if available
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

LAT_MIN  = 35.5
LAT_MAX  = 47.1
LON_MIN  = 6.6
LON_MAX  = 18.6
ZOOM_MIN = 7
ZOOM_MAX = 12

SOURCES = {
    "osm": {
        "url":     "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "headers": {"User-Agent": "pi-Mesh/1.0 tile downloader (https://github.com/yayoboy/pi-Mesh)"},
        "workers": 2,
        "delay":   0.2,
    },
    "topo": {
        "url":     "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        "headers": {"User-Agent": "pi-Mesh/1.0 tile downloader (https://github.com/yayoboy/pi-Mesh)"},
        "workers": 2,
        "delay":   0.2,
    },
    "satellite": {
        "url":     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "headers": {"User-Agent": "pi-Mesh/1.0"},
        "workers": 8,
        "delay":   0.05,
    },
}


def deg2tile(lat_deg, lon_deg, zoom):
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    x = int((lon_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_range(zoom):
    x_min, y_min = deg2tile(LAT_MAX, LON_MIN, zoom)
    x_max, y_max = deg2tile(LAT_MIN, LON_MAX, zoom)
    n = 2 ** zoom - 1
    return (max(0, x_min), min(n, x_max),
            max(0, y_min), min(n, y_max))


def _build_tile_list(name):
    base_dir = os.path.join("static", "tiles", name)
    tiles = []
    for z in range(ZOOM_MIN, ZOOM_MAX + 1):
        x_min, x_max, y_min, y_max = tile_range(z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                path = os.path.join(base_dir, str(z), str(x), f"{y}.png")
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    continue  # already downloaded
                tiles.append((z, x, y, path))
    return tiles


def _fetch_tile(url_tpl, headers, delay, z, x, y, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = url_tpl.format(z=z, x=x, y=y)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
        time.sleep(delay)
        return "ok"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            open(path, "wb").close()  # empty placeholder
            return "404"
        time.sleep(delay)
        return f"err:{e.code}"
    except Exception as e:
        time.sleep(delay)
        return f"err:{e}"


def download_source(name, cfg):
    url_tpl  = cfg["url"]
    headers  = cfg["headers"]
    workers  = cfg["workers"]
    delay    = cfg["delay"]

    tiles = _build_tile_list(name)
    total_existing = sum(
        1 for z in range(ZOOM_MIN, ZOOM_MAX + 1)
        for x_min, x_max, y_min, y_max in [tile_range(z)]
        for x in range(x_min, x_max + 1)
        for y in range(y_min, y_max + 1)
    )
    skipped = total_existing - len(tiles)
    total   = total_existing

    if not tiles:
        print(f"[{name}] Tutto già scaricato ({skipped} tile). Nulla da fare.")
        return

    print(f"[{name}] {len(tiles)} tile da scaricare ({skipped} già presenti) — {workers} worker paralleli")

    lock    = threading.Lock()
    done    = 0
    errors  = 0
    start   = time.time()

    def _job(args):
        return _fetch_tile(url_tpl, headers, delay, *args)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_job, t): t for t in tiles}
        for fut in as_completed(futures):
            result = fut.result()
            with lock:
                if result == "ok" or result == "404":
                    done += 1
                else:
                    errors += 1
                completed = done + skipped + errors
                if completed % 200 == 0 or completed == total:
                    elapsed = time.time() - start
                    rate    = done / elapsed if elapsed > 0 else 0
                    eta     = (len(tiles) - done - errors) / rate if rate > 0 else 0
                    print(
                        f"[{name}] {completed}/{total} "
                        f"(+{done} dl, {skipped} skip, {errors} err) "
                        f"{rate:.1f} tile/s  ETA {eta/60:.0f}min",
                        flush=True,
                    )

    elapsed = time.time() - start
    rate    = done / elapsed if elapsed > 0 else 0
    print(f"[{name}] DONE — {done} scaricate, {skipped} già presenti, {errors} errori — {rate:.1f} tile/s", flush=True)


if __name__ == "__main__":
    sources = sys.argv[1:] or list(SOURCES.keys())
    for name in sources:
        if name not in SOURCES:
            print(f"Sorgente sconosciuta: {name}. Valide: {list(SOURCES.keys())}")
            sys.exit(1)
        print(f"\n=== Scaricando {name} (zoom {ZOOM_MIN}-{ZOOM_MAX}) ===", flush=True)
        download_source(name, SOURCES[name])
    print("\nFatto.")
