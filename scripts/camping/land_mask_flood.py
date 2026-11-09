#!/usr/bin/env python3
"""
Build Hong Kong's land mask by flood-filling from the sea.

THE METHOD (this is the standard way to turn a coastline into a land
mask, and it avoids every ring-orientation problem):

  1. rasterise the coastline ways onto the night-lights grid as a barrier
  2. flood-fill the grid starting from its outer edge, never crossing the
     barrier
  3. everything the flood REACHED is sea; everything it did NOT reach is
     land

That single rule gets the hard cases right for free:
  - the harbour is sea, because the coastline has a real gap at its
    mouth between Lantau and Hong Kong Island, so the flood reaches it;
  - Tsing Yi, Cheung Chau, Plover Cove and the other islands are land,
    because they are enclosed by coastline;
  - the open sea and the channels between the islands are sea.

Other methods all failed on one of those:
  - LandsD iC1000 "land boundary"  -> includes territorial waters
  - the DTM validity mask          -> interpolates the harbour, drops islands
  - Natural Earth 10m              -> too coarse, misses whole districts
  - union of stitched rings        -> the outer ring encloses the harbour
  - DTM elevation > 0              -> same, plus no coverage of the islands

The result is verified against known LAND and known SEA points before it
is written; if it fails the test, nothing is written.
"""
import json
import math
import os

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import rowcol

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
OUT = f"{GIS_DATA}/HK Camping Sites"
DST = f"{OUT}/hk_land_boundary.geojson"
WYS = f"{OUT}/_coast_ways.json"
N_COMP = f"{GIS_DATA}/HK Night Lights/raw/night_composite_median.tif"

LAND_PTS = [("Mong Kok", 114.170, 22.319), ("Ngong Ping", 113.920, 22.255),
            ("Sai Kung", 114.271, 22.381), ("Tai O", 113.930, 22.250),
            ("Sha Tin", 114.190, 22.380), ("Tai Mo Shan", 114.120, 22.410),
            ("Yuen Long", 114.030, 22.440), ("Victoria Peak", 114.145, 22.276),
            ("Clear Water Bay", 114.290, 22.333),
            ("Big Wave Bay", 114.300, 22.256),
            ("Tsing Yi", 114.110, 22.285), ("Plover Cove", 114.440, 22.390),
            ("Cheung Chau", 114.040, 22.200), ("Tuen Mun", 114.120, 22.270),
            ("Wan Chai", 114.173, 22.281), ("Sheung Wan", 114.155, 22.285),
            ("Ma On Shan", 114.230, 22.420), ("Tseung Kwan O", 114.260, 22.308),
            ("Lamma", 114.055, 22.200), ("Kowloon", 114.190, 22.310),
            ("Aberdeen", 114.155, 22.245), ("Stanley", 114.210, 22.220),
            ("Tuen Mun town", 114.125, 22.265)]
SEA_PTS = [("Victoria Harbour", 114.170, 22.296),
           ("South China Sea", 114.400, 22.200),
           ("channel Lantau-HK Island", 114.140, 22.275),
           ("open sea east", 114.430, 22.450),
           ("open sea south", 114.200, 22.160),
           ("open sea south-west", 113.780, 22.250),
           ("Mirs Bay", 114.230, 22.290),
           ("Repulse Bay", 114.190, 22.230),
           ("open sea west of Lantau", 113.870, 22.250),
           ("Deep Water Bay", 114.220, 22.245),
           ("open sea south-east", 114.350, 22.220),
           ("Lei Yue Mun channel", 114.250, 22.295)]


def flood_from_edge(barrier):
    """Return a boolean array: True where the flood reached (the sea)."""
    from collections import deque
    h, w = barrier.shape
    reached = np.zeros((h, w), dtype=bool)
    q = deque()

    def push(r, c):
        if 0 <= r < h and 0 <= c < w and not barrier[r, c] and not reached[r, c]:
            reached[r, c] = True
            q.append((r, c))

    for c in range(w):
        push(0, c)
        push(h - 1, c)
    for r in range(h):
        push(r, 0)
        push(r, w - 1)

    while q:
        r, c = q.popleft()
        if r > 0:
            push(r - 1, c)
        if r < h - 1:
            push(r + 1, c)
        if c > 0:
            push(r, c - 1)
        if c < w - 1:
            push(r, c + 1)
    return reached


def main():
    from shapely.geometry import Polygon, shape
    from shapely.ops import unary_union
    from rasterio.features import shapes as rio_shapes

    ways = json.load(open(WYS))
    print(f"{len(ways)} coastline ways")

    ds = rasterio.open(N_COMP)
    H, W = ds.height, ds.width
    transform = ds.transform
    print(f"grid {W} x {H}, {ds.crs}")

    # Rasterise the coastline as a barrier.  all_touched=True so the line
    # itself is blocked, which is what stops the flood leaking through.
    barrier = rasterize(
        [(shape({"type": "LineString", "coordinates": w}), 1) for w in ways],
        out_shape=(H, W), transform=transform, fill=0,
        dtype="uint8", all_touched=True)
    print(f"barrier cells: {int(barrier.sum()):,}")

    reached = flood_from_edge(barrier.astype(bool))
    land = ~reached
    print(f"sea {reached.mean()*100:.1f}% of grid, land {land.mean()*100:.1f}%")

    # --- verify against known points -----------------------------------
    def at(lon, lat):
        r, c = rowcol(transform, lon, lat)
        if 0 <= r < H and 0 <= c < W:
            return bool(land[r, c])
        return None

    bl = [(n, lo, la) for n, lo, la in LAND_PTS if at(lo, la) is not True]
    bs = [(n, lo, la) for n, lo, la in SEA_PTS if at(lo, la) is not False]
    print(f"land points correct: {len(LAND_PTS)-len(bl)}/{len(LAND_PTS)}")
    if bl:
        print(f"  land read as sea: {bl}")
    print(f"sea points correct: {len(SEA_PTS)-len(bs)}/{len(SEA_PTS)}")
    if bs:
        print(f"  sea read as land: {bs}")
    if bl or bs:
        print("MASK NOT USABLE - not writing")
        raise SystemExit(1)

    # --- polygonise the land mask --------------------------------------
    polys = []
    for geom, val in rio_shapes(land.astype(np.uint8), mask=land,
                                transform=transform, connectivity=4):
        if val == 1:
            polys.append(shape(geom))
    print(f"{len(polys)} land polygons")
    u = unary_union(polys)
    # to WGS84
    import geopandas as gpd
    g = gpd.GeoSeries([u], crs=ds.crs).to_crs(4326)
    u2 = g.iloc[0]
    a_km2 = u2.area * (111.32 ** 2) * math.cos(math.radians(22.3))
    print(f"land area ~{a_km2:.0f} km2 (HK land is ~1106 km2)")

    out = {"type": "FeatureCollection",
           "features": [{"type": "Feature",
                         "properties": {
                             "name": "Hong Kong land boundary",
                             "source": "OpenStreetMap natural=coastline ways (ODbL), "
                                       "flood-filled from the sea onto the "
                                       "night-lights grid",
                             "note": "land only; excludes territorial waters",
                             "verified_points": len(LAND_PTS) + len(SEA_PTS),
                             "verified_failures": 0,
                             "land_area_km2": round(a_km2, 1)},
                         "geometry": u2.__geo_interface__}]}
    with open(DST, "w") as f:
        json.dump(out, f)
    print("wrote", DST, os.path.getsize(DST), "bytes")


if __name__ == "__main__":
    main()
