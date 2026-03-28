#!/usr/bin/env python3
"""
Download offline map tiles for Italy (OSM, OpenTopoMap, ESRI satellite).
Stores tiles as static/tiles/{source}/{z}/{x}/{y}.png
Run from the pi-Mesh project root directory.
"""
import math, os, sys, time, urllib.request, urllib.error

LAT_MIN  = 35.5
LAT_MAX  = 47.1
LON_MIN  = 6.6
LON_MAX  = 18.6
ZOOM_MIN = 7
ZOOM_MAX = 12   # zoom 13 doubles tile count; use 12 for initial deployment

SOURCES = {
    "osm": {
        "url":     "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "headers": {"User-Agent": "pi-Mesh/1.0 tile downloader (https://github.com/yayoboy/pi-Mesh)"},
    },
    "topo": {
        "url":     "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        "headers": {"User-Agent": "pi-Mesh/1.0 tile downloader (https://github.com/yayoboy/pi-Mesh)"},
    },
    "satellite": {
        "url":     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "headers": {"User-Agent": "pi-Mesh/1.0"},
    },
}

DELAY = 0.35  # seconds between requests per source


def deg2tile(lat_deg, lon_deg, zoom):
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    x = int((lon_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_range(zoom):
    x_min, y_min = deg2tile(LAT_MAX, LON_MIN, zoom)  # top-left
    x_max, y_max = deg2tile(LAT_MIN, LON_MAX, zoom)  # bottom-right
    # clamp to valid range
    n = 2 ** zoom - 1
    return (max(0, x_min), min(n, x_max),
            max(0, y_min), min(n, y_max))


def download_source(name, cfg):
    url_tpl = cfg["url"]
    headers = cfg["headers"]
    base_dir = os.path.join("static", "tiles", name)

    total = 0
    for z in range(ZOOM_MIN, ZOOM_MAX + 1):
        x_min, x_max, y_min, y_max = tile_range(z)
        total += (x_max - x_min + 1) * (y_max - y_min + 1)

    done = skipped = errors = 0
    start = time.time()

    for z in range(ZOOM_MIN, ZOOM_MAX + 1):
        x_min, x_max, y_min, y_max = tile_range(z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                path = os.path.join(base_dir, str(z), str(x), f"{y}.png")
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    skipped += 1
                    continue

                os.makedirs(os.path.dirname(path), exist_ok=True)
                url = url_tpl.format(z=z, x=x, y=y)
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    done += 1
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        # Write empty placeholder so we skip it next time
                        open(path, "wb").close()
                    else:
                        errors += 1
                    time.sleep(DELAY)
                    continue
                except Exception:
                    errors += 1
                    time.sleep(DELAY)
                    continue

                time.sleep(DELAY)

                completed = done + skipped + errors
                if completed % 100 == 0 or completed == total:
                    elapsed = time.time() - start
                    rate = done / elapsed if elapsed > 0 else 0
                    eta  = (total - completed) / rate if rate > 0 else 0
                    print(
                        f"[{name}] z={z} {completed}/{total} "
                        f"(+{done} dl, ~{skipped} skip, {errors} err) "
                        f"ETA {eta/60:.0f}min",
                        flush=True,
                    )

    print(f"[{name}] DONE — {done} downloaded, {skipped} skipped, {errors} errors", flush=True)


if __name__ == "__main__":
    sources = sys.argv[1:] or list(SOURCES.keys())
    for name in sources:
        if name not in SOURCES:
            print(f"Unknown source: {name}. Valid: {list(SOURCES.keys())}")
            sys.exit(1)
        print(f"\n=== Downloading {name} tiles (zoom {ZOOM_MIN}-{ZOOM_MAX}) ===", flush=True)
        download_source(name, SOURCES[name])
    print("\nAll done.")
