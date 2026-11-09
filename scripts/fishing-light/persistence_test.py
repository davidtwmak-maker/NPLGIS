#!/usr/bin/env python3
"""
PERSISTENCE TEST: fixed structure or moving boat?

For every distinct 0.01-degree cell that ever exceeds 140 DN in water more
than 3 km from land, count how many of the 693 nights it is lit on.

  fixed structure (pier, terminal, cable, platform)  -> lit on MANY nights
  fishing vessel                                     -> lit on ONE night

This is the cleanest discriminator, because it needs no assumption about
the fishing season.
"""
import collections
import json
import math
import os

import numpy as np
import rasterio
import geopandas as gpd
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

ROOT = "/Users/davidhermes/GIS Data/HK Night Lights"
RAW = f"{ROOT}/raw_seasonal"
CSDI = "/Users/davidhermes/GIS Data/hk-spatial/data"
COAST = "/tmp/_coast_ways_full.json"

W, H = 1200, 840
TR = from_origin(113.72, 22.60, (114.45 - 113.72) / W, (22.60 - 22.15) / H)
XRES = abs(TR.a) * 111.32 * math.cos(math.radians(22.375))
YRES = abs(TR.e) * 110.574
BRIGHT = 140

FIXED = [
    ("HK Offshore LNG terminal (Shek Kwu Chau)", 113.9705, 22.1545, 3.0),
    ("Ma Liu Shui - Tung Ping Chau cable", 114.38, 22.56, 3.0),
]


def log(m):
    print(m, flush=True)


def main():
    ways = json.load(open(COAST))
    lines = [{"type": "LineString", "coordinates": [(p["lon"], p["lat"]) for p in w]}
             for w in ways]
    coast = rasterize(lines, out_shape=(H, W), transform=TR, fill=0,
                      dtype="uint8", all_touched=True).astype(bool)
    coast = ndimage.binary_dilation(coast, np.ones((7, 7)))
    lab, _ = ndimage.label(~coast)
    sea = (lab == lab[(H - 25, W - 25)])
    d2l = ndimage.distance_transform_edt(sea, sampling=(YRES, XRES))
    deep = sea & (d2l >= 3.0)

    perm = gpd.read_file(f"{CSDI}/mardep_rcd_1730952503222_38811.geojson")
    pm = np.zeros((H, W), dtype=bool)
    for g in perm.geometry:
        pm |= rasterize([(g, 1)], out_shape=(H, W), transform=TR, fill=0,
                        dtype="uint8").astype(bool)
    pm &= sea

    rows = json.load(open(f"{ROOT}/seasonal_nights.json"))
    nights = [(r["date"], r["year"], r["month"]) for r in rows
              if os.path.exists(f"{RAW}/SNPP_{r['date']}.tif")]
    nights.sort()

    nights_per_cell = collections.Counter()
    in_permitted = collections.Counter()
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
        b = (a >= BRIGHT) & deep
        ys, xs = np.nonzero(b)
        for r_, c_ in zip(ys, xs):
            lon = TR.c + c_ * TR.a + TR.a / 2
            lat = TR.f + r_ * TR.e + TR.e / 2
            key = (round(lon, 2), round(lat, 2))
            nights_per_cell[key] += 1
            if pm[r_, c_]:
                in_permitted[key] += 1

    vals = sorted(nights_per_cell.values(), reverse=True)
    pv = sorted(in_permitted.values(), reverse=True)
    log("=" * 76)
    log(f"PERSISTENCE of bright deep-water cells (>= {BRIGHT} DN, >=3 km from land)")
    log(f"  nights analysed: {len(nights)}")
    log("=" * 76)
    log(f"  ALL deep water: {len(vals)} distinct cells ever lit")
    log(f"    lit on max {vals[0]:,} nights, median {vals[len(vals)//2]:,}, min {vals[-1]}")
    log(f"    lit on >=20 nights: {sum(1 for v in vals if v>=20)}")
    log(f"    lit on >=5 nights : {sum(1 for v in vals if v>=5)}")
    log(f"    lit on exactly 1  : {sum(1 for v in vals if v==1)}")
    log(f"  INSIDE PERMITTED areas: {len(pv)} distinct cells ever lit")
    log(f"    lit on max {pv[0]:,} nights, median {pv[len(pv)//2]:,}, min {pv[-1]}")
    log(f"    lit on >=20 nights: {sum(1 for v in pv if v>=20)}")
    log(f"    lit on >=5 nights : {sum(1 for v in pv if v>=5)}")
    log(f"    lit on exactly 1  : {sum(1 for v in pv if v==1)}")
    log(f"    => {100*sum(1 for v in pv if v>=5)/max(len(pv),1):.0f}% of cells are lit on 5+ nights "
        f"=> fixed sources, not boats")

    log("\n  top 10 cells in the permitted deep water:")
    for (lon, lat), n in sorted(in_permitted.items(), key=lambda x: -x[1])[:10]:
        near = min(((math.hypot((lon - L) * 111.32 * math.cos(math.radians(22.15)),
                                (lat - B) * 110.574), name)
                    for name, L, B, _r in FIXED), default=(9999, "-"))
        log(f"    ({lon:8.2f},{lat:7.2f})  {n:4d} nights   {near[0]:5.1f} km from {near[1]}")

    json.dump({
        "n_nights": len(nights),
        "all_deep_cells": len(vals),
        "all_deep_max_nights": vals[0],
        "all_deep_ge20": sum(1 for v in vals if v >= 20),
        "permitted_cells": len(pv),
        "permitted_max_nights": pv[0],
        "permitted_ge5": sum(1 for v in pv if v >= 5),
        "permitted_eq1": sum(1 for v in pv if v == 1),
        "permitted_ge5_pct": 100 * sum(1 for v in pv if v >= 5) / max(len(pv), 1),
        "top_permitted": [{"lon": k[0], "lat": k[1], "nights": v}
                          for k, v in sorted(in_permitted.items(), key=lambda x: -x[1])[:20]],
    }, open(f"{ROOT}/persistence.json", "w"), indent=2)
    log(f"\n  wrote {ROOT}/persistence.json")


if __name__ == "__main__":
    main()
