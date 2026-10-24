#!/usr/bin/env python3
"""
Turn the iB1000 shoreline polylines into a land polygon for the HK map.

Strategy (the OSM recipe adapted to an already-fine shoreline):
  1. paint the whole window as LAND,
  2. build the SEA as the union of closed loops snapped to the shoreline, plus a
     complement step - a point is water if it cannot reach the window edge through
     land without crossing the shore,
  3. rasterise that classification at 0.001 deg and extract land as one mask,
  4. probe-test before rendering (land probes inside, sea probes outside).
Rasterising avoids stitching 9,078 separate polylines into one polygon by hand.
"""
import json
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

D = os.path.dirname(os.path.abspath(__file__))
LON0, LON1 = 113.82, 114.47
LAT0, LAT1 = 22.13, 22.59
RES = 0.0008  # ~85 m, finer than any bay mouth in HK

W = int((LON1 - LON0) / RES)
H = int((LAT1 - LAT0) / RES)
print(f"raster {W} x {H} cells at {RES} deg")

shore = json.load(open(os.path.join(D, "raw", "shoreline_ib1000.geojson")))["features"]

im = Image.new("L", (W, H), 0)  # 0 = land, 255 = water
dr = ImageDraw.Draw(im)


def to_px(lon, lat):
    return ((lon - LON0) / RES, (H - 1) - (lat - LAT0) / RES)


n_drawn = 0
for f in shore:
    g = f.get("geometry")
    if not g:
        continue
    # standard GeoJSON: LineString -> one part, MultiLineString -> several
    if g["type"] == "LineString":
        parts = [g["coordinates"]]
    elif g["type"] == "MultiLineString":
        parts = g["coordinates"]
    else:
        parts = [g["coordinates"]] if g["coordinates"] else []
    for part in parts:
        if len(part) < 2:
            continue
        pts = [to_px(p[0], p[1]) for p in part]
        dr.line(pts, fill=255, width=2)
        n_drawn += 1
print(f"drawn shoreline segments: {n_drawn}")

# flood the sea inwards from the window border, blocked by the shoreline.
# Anything the flood cannot reach stays land.
sea = Image.new("L", (W, H), 0)
px = sea.load()
block = im.load()
q = deque()
for x in range(W):
    for y in (0, H - 1):
        if block[x, y] == 0 and px[x, y] == 0:
            px[x, y] = 1
            q.append((x, y))
for y in range(H):
    for x in (0, W - 1):
        if block[x, y] == 0 and px[x, y] == 0:
            px[x, y] = 1
            q.append((x, y))
while q:
    x, y = q.popleft()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < W and 0 <= ny < H and block[nx, ny] == 0 and px[nx, ny] == 0:
            px[nx, ny] = 1
            q.append((nx, ny))
arr = np.asarray(sea)
water = arr > 0
land = ~water
print(f"water cells: {water.sum():,}  land cells: {land.sum():,}  "
      f"({100 * land.sum() / land.size:.1f}% land)")


def is_land(lon, lat):
    x = int((lon - LON0) / RES)
    y = int((H - 1) - (lat - LAT0) / RES)
    if not (0 <= x < W and 0 <= y < H):
        return False
    return bool(land[y, x])


LAND_PROBES = [(114.153, 22.283), (114.169, 22.319), (114.161, 22.445),
               (113.981, 22.389), (114.250, 22.400), (114.030, 22.500),
               (114.170, 22.260), (114.190, 22.300)]
SEA_PROBES = [(114.40, 22.20), (113.86, 22.22), (114.44, 22.35),
              (113.87, 22.55), (114.30, 22.50), (114.26, 22.17)]
lo = [is_land(*p) for p in LAND_PROBES]
so = [is_land(*p) for p in SEA_PROBES]
print("land probes (want True):", lo)
print("sea  probes (want False):", so)
assert all(lo), f"a land probe reads as water: {[p for p, r in zip(LAND_PROBES, lo) if not r]}"
assert not any(so), f"a sea probe reads as land: {[p for p, r in zip(SEA_PROBES, so) if r]}"

# every venue and free court must sit on land
ven = json.load(open(os.path.join(D, "venues.geojson")))["features"]
fre = json.load(open(os.path.join(D, "free_outdoor_courts.geojson")))["features"]
bad = [f["properties"]["venue_name_en"] for f in ven if not is_land(*f["geometry"]["coordinates"])]
badf = [f["properties"]["venue_name_en"] for f in fre if not is_land(*f["geometry"]["coordinates"])]
print(f"venues on land: {len(ven) - len(bad)}/{len(ven)}", bad or "")
print(f"free courts on land: {len(fre) - len(badf)}/{len(fre)}", badf or "")

# save the land mask for the map script
np.save(os.path.join(D, "land_mask.npy"), land)
img = Image.fromarray((land * 255).astype(np.uint8))
img.save(os.path.join(D, "land_mask.png"))
meta = {"lon0": LON0, "lon1": LON1, "lat0": LAT0, "lat1": LAT1,
        "res": RES, "W": W, "H": H,
        "land_pct": round(100 * float(land.sum()) / land.size, 2)}
json.dump(meta, open(os.path.join(D, "land_mask_meta.json"), "w"))
print("saved land mask + meta", meta)
print("DONE")