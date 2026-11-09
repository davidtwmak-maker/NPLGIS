#!/usr/bin/env python3
"""
Why do bright deep-water pixels inside the permitted areas appear only from
2023 onwards?

Candidate explanations:
  (a) a change in the GIBS product's rendering / scaling / sensor
      processing;
  (b) the threshold of 140 DN is only crossed once the overall scene got
      brighter, so the signal existed all along below threshold;
  (c) fishing activity genuinely changed.

Test for (a): a stable, unsaturated artificial light source must not change
value across the 2022/2023 boundary if the product is consistent.  A saturated
one (the urban core, pinned at 255) cannot reveal a scale change, so use
moderate sources.

Test for (b): compare the MAXIMUM and P99.9 of the permitted deep water, not
a threshold count, year by year.
"""
import json
import math
import os
import statistics

import numpy as np
import rasterio
import geopandas as gpd
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
ROOT = os.environ.get("GIS_DATA_DIR", f"{GIS_DATA}") + "/HK Night Lights"
RAW = f"{ROOT}/raw_seasonal"
CSDI = f"{GIS_DATA}/hk-spatial/data"
COAST = "/tmp/_coast_ways_full.json"

W, H = 1200, 840
TR = from_origin(113.72, 22.60, (114.45 - 113.72) / W, (22.60 - 22.15) / H)
XRES = abs(TR.a) * 111.32 * math.cos(math.radians(22.375))
YRES = abs(TR.e) * 110.574


def log(m):
    print(m, flush=True)


def box(a, lon0, lat0, lon1, lat1):
    r0 = int((22.60 - lat1) / (-TR.e)); r1 = int((22.60 - lat0) / (-TR.e))
    c0 = int((lon0 - 113.72) / TR.a); c1 = int((lon1 - 113.72) / TR.a)
    return a[r0:r1, c0:c1]


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
    deep_p, deep_o = deep & pm, deep & ~pm

    rows = json.load(open(f"{ROOT}/seasonal_nights.json"))
    nights = [(r["date"], r["year"], r["month"]) for r in rows
              if os.path.exists(f"{RAW}/SNPP_{r['date']}.tif")]
    nights.sort()

    # moderate, unsaturated, stable artificial sources (coastal towns)
    SOURCES = {
        "Lantau (Mui Wo)": (113.985, 22.262, 113.997, 22.272),
        "Sai Kung town": (114.268, 22.376, 114.278, 22.386),
        "Yuen Long town": (114.028, 22.444, 114.040, 22.452),
        "Sheung Shui": (114.125, 22.492, 114.135, 22.500),
        "Tuen Mun": (113.975, 22.388, 113.988, 22.398),
    }
    by_year = {}
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1).astype(np.float32)
        rec = by_year.setdefault(year, [])
        rec.append({
            "dp_max": float(a[deep_p].max()),
            "dp_p999": float(np.percentile(a[deep_p], 99.9)),
            "dp_mean": float(a[deep_p].mean()),
            "do_max": float(a[deep_o].max()),
            "do_p999": float(np.percentile(a[deep_o], 99.9)),
            "do_mean": float(a[deep_o].mean()),
            "srcs": {k: float(box(a, *v).max()) for k, v in SOURCES.items()},
        })

    log("=" * 94)
    log("A  MODERATE, UNSATURATED ARTIFICIAL LIGHT SOURCES - max DN per year")
    log("   (if the product changed in 2023, these jump)")
    log("=" * 94)
    hdr = "  year " + "".join(f"{k[:13]:>15s}" for k in SOURCES)
    log(hdr)
    for y in sorted(by_year):
        v = by_year[y]
        log(f"  {y} " + "".join(f"{statistics.median(r['srcs'][k] for r in v):15.1f}"
                               for k in SOURCES))

    log("\n" + "=" * 94)
    log("B  DEEP WATER inside vs outside the permitted areas - max and P99.9 per year")
    log("   (tests explanation (b): the signal existed below threshold all along)")
    log("=" * 94)
    log("  year   dpMax  dpP999  dpMean |  doMax  doP999  doMean")
    for y in sorted(by_year):
        v = by_year[y]
        log(f"  {y} {statistics.median(r['dp_max'] for r in v):7.0f} "
            f"{statistics.median(r['dp_p999'] for r in v):7.0f} "
            f"{statistics.median(r['dp_mean'] for r in v):7.2f} | "
            f"{statistics.median(r['do_max'] for r in v):6.0f} "
            f"{statistics.median(r['do_p999'] for r in v):6.0f} "
            f"{statistics.median(r['do_mean'] for r in v):6.2f}")

    log("\n" + "=" * 94)
    log("C  THE BRIGHT CLUSTER: Soko Islands / West Lamma channel (113.95-114.05, 22.14-22.17)")
    log("=" * 94)
    for (date, year, month) in nights:
        if year not in (2015, 2018, 2020, 2022, 2023, 2024, 2026):
            continue
        a = rasterio.open(f"{RAW}/SNPP/{date}.tif" if False else
                          f"{RAW}/SNPP_{date}.tif").read(1).astype(np.float32)
        b = box(a, 113.95, 22.14, 114.05, 22.17)
        log(f"    {date}  cluster max {b.max():5.0f}  P99 {np.percentile(b,99):5.0f}  "
            f"n>=140 {int((b>=140).sum()):4d}  n>=100 {int((b>=100).sum()):4d}")


if __name__ == "__main__":
    main()
