#!/usr/bin/env python3
"""iB20000 (1:20,000 photo map, LandsD) tile fetcher — keyless Esri tile cache.

Source: https://services2.map.gov.hk/xyz/ib20000/tile/{z}/{row}/{col}   (PNG, 256px)
Grid  : HK1980 / EPSG:2326, origin (-4786700, 8353100), standard XYZ LODs (level 0-21;
        the GeoInfo Map viewer caps at z17 — use <=17 for guaranteed coverage).
Terms : HKSAR Gov works, non-commercial use with attribution (www.map.gov.hk).

Usage:
  python3 ib20000.py --bbox 114.12,22.26,114.19,22.32 --z 16 --out site.png
  python3 ib20000.py --bbox 830000,812000,840000,820000 --hk80 --z 15 --out site2.png
  python3 ib20000.py --prefetch 14          # whole-HK mosaic -> ib20000_territory_z14.png
"""
import argparse, io, json, math, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "tiles_ib20000")
URL = "https://services2.map.gov.hk/xyz/ib20000/tile/{z}/{row}/{col}"
ORIGIN = (-4786700.0, 8353100.0)
TILE = 256
MAX_Z = 17
UA = "HermesAgent-DavidGeography/1.0 (non-commercial teaching basemap cache)"
L0 = 156543.03392800014


def res(z):
    return L0 / (2 ** z)


def to_hk80(lon, lat):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", "EPSG:2326", always_xy=True).transform(lon, lat)


def tile_range(z, x_min, y_min, x_max, y_max):
    r = res(z)
    s = TILE * r
    c0 = int(math.floor((x_min - ORIGIN[0]) / s))
    c1 = int(math.floor((x_max - ORIGIN[0]) / s))
    r0 = int(math.floor((ORIGIN[1] - y_max) / s))
    r1 = int(math.floor((ORIGIN[1] - y_min) / s))
    return c0, r0, c1, r1


def fetch_tile(z, row, col, tries=3):
    path = os.path.join(CACHE, f"z{z}", str(row), f"{col}.png")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    url = URL.format(z=z, row=row, col=col)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if data[:4] != b"\x89PNG":
                raise RuntimeError(f"not PNG from {url}: {data[:40]!r}")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            time.sleep(0.12)
            return path
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                return f"ERROR:{e}"
            time.sleep(1.0 * (i + 1))


def render(z, x_min, y_min, x_max, y_max, out_path):
    from PIL import Image
    c0, r0, c1, r1 = tile_range(z, x_min, y_min, x_max, y_max)
    ncols, nrows = c1 - c0 + 1, r1 - r0 + 1
    if ncols * nrows > 20000:
        raise SystemExit(f"refusing: {ncols}x{nrows} tiles at z{z}")
    canvas = Image.new("RGB", (ncols * TILE, nrows * TILE), (255, 255, 255))
    errs = 0
    for row in range(r0, r1 + 1):
        for col in range(c0, c1 + 1):
            p = fetch_tile(z, row, col)
            if p is None or (isinstance(p, str) and p.startswith("ERROR")):
                errs += 1
                print(f"  miss z{z}/{row}/{col}: {p}", flush=True)
                continue
            canvas.paste(Image.open(p).convert("RGB"), ((col - c0) * TILE, (row - r0) * TILE))
    # crop to exact bbox (WGS84-converted bbox already in HK80 metres)
    left = int(round((x_min - ORIGIN[0]) / (res(z)) - c0 * TILE))
    top = int(round((ORIGIN[1] - y_max) / res(z) - r0 * TILE))
    right = int(round((x_max - ORIGIN[0]) / (res(z)) - c0 * TILE))
    bottom = int(round((ORIGIN[1] - y_min) / res(z) - r0 * TILE))
    canvas = canvas.crop((max(0, left), max(0, top), min(canvas.width, right), min(canvas.height, bottom)))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    canvas.save(out_path)
    print(f"saved {out_path} ({canvas.width}x{canvas.height}, z{z}, {ncols}x{nrows} tiles, {errs} misses)")
    return errs


def service_extent():
    req = urllib.request.Request("https://services2.map.gov.hk/xyz/ib20000?f=json",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        meta = json.loads(resp.read())
    e = meta["fullExtent"]
    return e["xmin"], e["ymin"], e["xmax"], e["ymax"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", help="w,s,e,n (WGS84 lon/lat by default)")
    ap.add_argument("--hk80", action="store_true", help="bbox is HK1980 metres")
    ap.add_argument("--z", type=int, default=16)
    ap.add_argument("--out")
    ap.add_argument("--prefetch", type=int, metavar="Z", help="whole-territory mosaic at zoom Z")
    a = ap.parse_args()

    if a.prefetch is not None:
        z = a.prefetch
        if z > MAX_Z:
            raise SystemExit(f"prefetch capped at z{MAX_Z}")
        ext = service_extent()
        out = os.path.join(ROOT, f"ib20000_territory_z{z}.png")
        errs = render(z, *ext, out)
        sys.exit(1 if errs else 0)

    if not a.bbox or not a.out:
        raise SystemExit("need --bbox + --out (or --prefetch)")
    w, s, e, n = (float(v) for v in a.bbox.split(","))
    if not a.hk80:
        w, s = to_hk80(w, s)
        e, n = to_hk80(e, n)
    if a.z > MAX_Z:
        raise SystemExit(f"z>{MAX_Z} not guaranteed by the service (viewer caps at 17)")
    errs = render(a.z, w, s, e, n, a.out)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
