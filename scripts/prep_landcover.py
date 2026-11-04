#!/usr/bin/env python3
"""ESA WorldCover 2021 land cover for Hong Kong -> 200 m class fractions.

Tiles: N21E111 and N21E114 (3x3 degree COGs, EPSG:4326, 10 m).
Method: build a 0/1 mask for each of the 11 WorldCover classes over the HK
window, then warp each mask to the 200 m HK1980 (EPSG:2326) analysis grid with
average resampling -> the output is the true areal fraction of that class in
each 200 m cell (not a point sample).

Output: work/landcover_200m.npz
"""
import os
import numpy as np
import rasterio
import rasterio.warp
from rasterio.windows import Window
from rasterio.enums import Resampling
from rasterio.transform import from_origin

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
WORK = os.path.join(BASE, "work")
TILES = ["N21E111", "N21E114"]
URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
       "ESA_WorldCover_10m_2021_v200_{t}_Map.tif")

GRID = 200.0
BBOX = (113.70, 21.95, 114.55, 22.60)   # W, S, E, N in WGS84
CLASSES = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]


def main():
    os.makedirs(RAW, exist_ok=True)
    paths = []
    for t in TILES:
        p = os.path.join(RAW, f"worldcover_{t}.tif")
        if not os.path.exists(p):
            os.system(f"curl -sL -o '{p}' '{URL.format(t=t)}'")
        paths.append(p)
        print("tile", t, os.path.getsize(p), flush=True)

    tz = np.load(os.path.join(WORK, "terrain_200m.npz"))
    X0, Y0, CELL = float(tz["x0"]), float(tz["y0"]), float(tz["cell"])
    NY, NX = tz["slope"].shape

    # 200 m output grid in HK1980
    x_min = X0 - CELL / 2
    x_max = X0 + (NX - 1) * CELL + CELL / 2
    y_min = Y0 - (NY - 1) * CELL - CELL / 2
    y_max = Y0 + CELL / 2
    dst_transform = from_origin(x_min, y_max, CELL, CELL)
    dst_crs = "EPSG:2326"
    print(f"target {NY}x{NX} @ {CELL} m, HK1980 X[{x_min:.0f},{x_max:.0f}] Y[{y_min:.0f},{y_max:.0f}]", flush=True)

    # --- read the HK window from both tiles into one 4326 raster at ~10 m ---
    w, s, e, n = BBOX
    dx = 10.0 / (111320 * np.cos(np.radians(22.3)))
    dy = 10.0 / 110540
    nw = int(np.ceil((e - w) / dx))
    nh = int(np.ceil((n - s) / dy))
    src_transform = from_origin(w, n, dx, dy)
    print(f"4326 window {nw}x{nh} @ ~10 m", flush=True)

    lc = np.zeros((nh, nw), dtype=np.uint8)
    for p in paths:
        with rasterio.open(p) as src:
            left = (w - src.transform.c) / src.transform.a
            top = (n - src.transform.f) / src.transform.e
            width = (e - w) / src.transform.a
            height = (s - n) / src.transform.e
            win = Window(left, top, width, height).round_offsets().round_lengths()
            data = src.read(1, window=win, resampling=Resampling.nearest)
            src_win_transform = src.window_transform(win)
            rasterio.warp.reproject(
                source=data, destination=lc,
                src_transform=src_win_transform, src_crs="EPSG:4326",
                dst_transform=src_transform, dst_crs="EPSG:4326",
                resampling=Resampling.nearest, init_dest_nodata=False)
            print("  merged", os.path.basename(p), data.shape, flush=True)

    # --- per-class area fraction on the 200 m HK1980 grid ---
    fr = {}
    for c in CLASSES:
        mask = (lc == c).astype(np.float32)
        out = np.zeros((NY, NX), dtype=np.float32)
        rasterio.warp.reproject(
            source=mask, destination=out,
            src_transform=src_transform, src_crs="EPSG:4326",
            dst_transform=dst_transform, dst_crs=dst_crs,
            resampling=Resampling.average, init_dest_nodata=False)
        fr[c] = out
        print(f"  class {c}: mean frac {out.mean():.4f}, cells>0.1: {int((out > 0.1).sum())}", flush=True)

    tree = fr[10]; shrub = fr[20]; grass = fr[30]; bare = fr[60]
    built = fr[50]; water = fr[80]
    veg = np.clip(tree + shrub + grass, 0, 1)
    np.savez_compressed(
        os.path.join(WORK, "landcover_200m.npz"),
        tree=tree, shrub=shrub, grass=grass, bare=bare, built=built,
        water=water, veg=veg,
        **{f"cls_{c}": fr[c] for c in CLASSES},
        x0=np.float64(X0), y0=np.float64(Y0), cell=np.float64(GRID))
    print("wrote work/landcover_200m.npz", flush=True)


if __name__ == "__main__":
    main()
