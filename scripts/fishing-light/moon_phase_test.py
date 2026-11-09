#!/usr/bin/env python3
"""
Are the transient ("lit on exactly one night") bright deep-water pixels
FISHING VESSELS or CLOUDS REFLECTING MOONLIGHT?

A vessel is lit regardless of the moon phase.  A moonlit cloud top is only
bright when the moon is up, so the population of transient bright pixels
should track moon illumination.

This is the decisive discriminator between the two explanations, and it needs
no assumption about the fishing season.

Method: for each transient bright cell inside the permitted deep water
(lit on exactly one night, above the threshold), record the moon illumination
of that night.  Compare the distribution with the control water's transient
cells, and with the moon illumination of ALL nights (which is the null: if
the transient cells were spread evenly across all nights, the distribution
would match the all-nights distribution).
"""
import collections
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

ROOT = "/Users/davidhermes/GIS Data/HK Night Lights"
RAW = f"{ROOT}/raw_seasonal"
CSDI = "/Users/davidhermes/GIS Data/hk-spatial/data"
COAST = "/tmp/_coast_ways_full.json"

W, H = 1200, 840
TR = from_origin(113.72, 22.60, (114.45 - 113.72) / W, (22.60 - 22.15) / H)
XRES = abs(TR.a) * 111.32 * math.cos(math.radians(22.375))
YRES = abs(TR.e) * 110.574
THR = 100
LNG_LON, LNG_LAT = 113.9705, 22.1545
CABLE_LON, CABLE_LAT = 114.38, 22.56


def log(m):
    print(m, flush=True)


def moon_pct(date_str):
    """Illuminated fraction of the moon, from a known new moon epoch."""
    from datetime import datetime
    NEW_MOON = datetime(2000, 1, 6, 18, 14)
    d = datetime.fromisoformat(date_str)
    days = (d - NEW_MOON).total_seconds() / 86400.0
    phase = (days % 29.530588853) / 29.530588853
    return (1 - math.cos(2 * math.pi * phase)) / 2 * 100


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

    ri, ci = np.indices((H, W))
    xs = TR.c + ci * TR.a + TR.a / 2
    ys = TR.f + ri * TR.e + TR.e / 2
    fixed = np.zeros((H, W), dtype=bool)
    for (lo, la, r) in ((LNG_LON, LNG_LAT, 3.0), (CABLE_LON, CABLE_LAT, 3.0)):
        fixed |= np.hypot((xs - lo) * 111.32 * math.cos(math.radians(22.15)),
                          (ys - la) * 110.574) <= r

    perm = gpd.read_file(f"{CSDI}/mardep_rcd_1730952503222_38811.geojson")
    pm = np.zeros((H, W), dtype=bool)
    for g in perm.geometry:
        pm |= rasterize([(g, 1)], out_shape=(H, W), transform=TR, fill=0,
                        dtype="uint8").astype(bool)
    pm &= sea

    deep_p = sea & (d2l >= 3.0) & pm & ~fixed
    deep_c = sea & (d2l >= 3.0) & ~pm & ~fixed

    rows = json.load(open(f"{ROOT}/seasonal_nights.json"))
    nights = [(r["date"], r["year"], r["month"]) for r in rows
              if os.path.exists(f"{RAW}/SNPP_{r['date']}.tif")]
    nights.sort()

    counts_p = collections.Counter()
    counts_c = collections.Counter()
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
        ys2, xs2 = np.nonzero(deep_p & (a >= THR))
        for r_, c_ in zip(ys2, xs2):
            counts_p[(r_, c_)] += 1
        ys2, xs2 = np.nonzero(deep_c & (a >= THR))
        for r_, c_ in zip(ys2, xs2):
            counts_c[(r_, c_)] += 1

    # which night was each transient cell lit on?
    firstnight = {}
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
        ys2, xs2 = np.nonzero(deep_p & (a >= THR))
        for r_, c_ in zip(ys2, xs2):
            counts_p[(r_, c_)] = counts_p[(r_, c_)]  # no-op, keep structure clear
    # recompute properly: for each cell, the set of nights
    lit_p = collections.defaultdict(list)
    lit_c = collections.defaultdict(list)
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
        for r_, c_ in zip(*np.nonzero(deep_p & (a >= THR))):
            lit_p[(r_, c_)].append(date)
        for r_, c_ in zip(*np.nonzero(deep_c & (a >= THR))):
            lit_c[(r_, c_)].append(date)

    trans_p = [v[0] for v in lit_p.values() if len(v) == 1]
    trans_c = [v[0] for v in lit_c.values() if len(v) == 1]
    all_nights = [d for (d, y, m) in nights]

    log("=" * 78)
    log(f"MOON-PHASE TEST on transient bright cells (>={THR} DN, deep water)")
    log("=" * 78)
    log(f"  transient cells inside permitted areas: {len(trans_p):,}")
    log(f"  transient cells in control water     : {len(trans_c):,}")
    log(f"  nights analysed                       : {len(all_nights)}")

    def mstats(dates):
        if not dates:
            return None
        v = [moon_pct(d) for d in dates]
        return {"mean": statistics.mean(v), "median": statistics.median(v),
                "n": len(v),
                "frac_above_50": sum(1 for x in v if x > 50) / len(v),
                "frac_above_75": sum(1 for x in v if x > 75) / len(v)}

    allm = mstats(all_nights)
    pm_ = mstats(trans_p)
    cm_ = mstats(trans_c)
    log("")
    log(f"  {'population':38s} {'n':>8s} {'mean moon%':>11s} {'median':>8s} {'>50%':>7s} {'>75%':>7s}")
    log(f"  {'ALL nights (null distribution)':38s} {allm['n']:>8,} {allm['mean']:>11.1f} "
        f"{allm['median']:>8.1f} {allm['frac_above_50']:>7.2f} {allm['frac_above_75']:>7.2f}")
    log(f"  {'transient cells, PERMITTED areas':38s} {pm_['n']:>8,} {pm_['mean']:>11.1f} "
        f"{pm_['median']:>8.1f} {pm_['frac_above_50']:>7.2f} {pm_['frac_above_75']:>7.2f}")
    log(f"  {'transient cells, CONTROL water':38s} {cm_['n']:>8,} {cm_['mean']:>11.1f} "
        f"{cm_['median']:>8.1f} {cm_['frac_above_50']:>7.2f} {cm_['frac_above_75']:>7.2f}")

    # seasonal pattern of the transient population
    log("\n  transient cells inside permitted areas by month:")
    mon = collections.Counter()
    for d in trans_p:
        mon[int(d[5:7])] += 1
    monc = collections.Counter()
    for d in trans_c:
        monc[int(d[5:7])] += 1
    log("    month: " + "  ".join(f"{m:02d}:{mon.get(m,0):,}" for m in range(1, 13)))
    log("    control: " + "  ".join(f"{m:02d}:{monc.get(m,0):,}" for m in range(1, 13)))

    json.dump({
        "threshold": THR,
        "all_nights_moon": allm,
        "permitted_transient_moon": pm_,
        "control_transient_moon": cm_,
        "permitted_transient_by_month": {str(k): v for k, v in sorted(mon.items())},
        "control_transient_by_month": {str(k): v for k, v in sorted(monc.items())},
    }, open(f"{ROOT}/moon_phase_test.json", "w"), indent=2)
    log(f"\n  wrote {ROOT}/moon_phase_test.json")


if __name__ == "__main__":
    main()
