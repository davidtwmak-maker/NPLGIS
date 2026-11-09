#!/usr/bin/env python3
"""
FINAL SUMMARY: the fishing-light signal is EPISODIC, not a smooth curve.

Only a small number of nights per year carry the signal, and on those nights
the excess of transient bright cells is large.  This script:

  1. characterises the individual "active nights" (spatial spread, magnitude);
  2. counts active nights per year and their months - the practical answer
     for stargazing advice;
  3. produces the final table of numbers used in the write-up.
"""
import collections
import json
import math
import os
import statistics
from datetime import datetime

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
THR = 140
MOR = (5, 6, 7, 8)
NEW_MOON = datetime(2000, 1, 6, 18, 14)


def log(m):
    print(m, flush=True)


def moon_pct(ds):
    d = datetime.fromisoformat(ds)
    days = (d - NEW_MOON).total_seconds() / 86400.0
    ph = (days % 29.530588853) / 29.530588853
    return (1 - math.cos(2 * math.pi * ph)) / 2 * 100


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
    for lo, la in ((113.9705, 22.1545), (114.38, 22.56)):
        fixed |= np.hypot((xs - lo) * 111.32 * math.cos(math.radians(22.15)),
                          (ys - la) * 110.574) <= 3.0

    perm = gpd.read_file(f"{CSDI}/mardep_rcd_1730952503222_38811.geojson")
    pm = np.zeros((H, W), dtype=bool)
    for g in perm.geometry:
        pm |= rasterize([(g, 1)], out_shape=(H, W), transform=TR, fill=0,
                        dtype="uint8").astype(bool)
    pm &= sea

    dp = sea & (d2l >= 3.0) & pm & ~fixed
    dc = sea & (d2l >= 3.0) & ~pm & ~fixed

    rows = json.load(open(f"{ROOT}/seasonal_nights.json"))
    nights = [(r["date"], r["year"], r["month"]) for r in rows
              if os.path.exists(f"{RAW}/SNPP/{date}.tif" if False else
                               f"{RAW}/SNPP_{r['date']}.tif")]
    nights.sort()

    lit_p = collections.defaultdict(list)
    lit_c = collections.defaultdict(list)
    per_night = []
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
        bp = dp & (a >= THR)
        bc = dc & (a >= THR)
        for r_, c_ in zip(*np.nonzero(bp)):
            lit_p[(r_, c_)].append(date)
        for r_, c_ in zip(*np.nonzero(bc)):
            lit_c[(r_, c_)].append(date)
        per_night.append({"date": date, "year": year, "month": month,
                          "moon": moon_pct(date), "np": int(bp.sum()),
                          "nc": int(bc.sum()),
                          "npix_p": int(dp.sum()), "npix_c": int(dc.sum())})

    tp = {k: v[0] for k, v in lit_p.items() if len(v) == 1}
    tc = {k: v[0] for k, v in lit_c.items() if len(v) == 1}
    tp_by_night = collections.Counter(tp.values())
    tc_by_night = collections.Counter(tc.values())

    # ---------- 1. the active nights ----------
    log("=" * 84)
    log("1  ACTIVE NIGHTS: transient-cell excess (permitted minus control)")
    log("=" * 84)
    log(f"  {'date':12s} {'mo':>3s} {'moon%':>7s} {'excess':>8s} {'permVessel':>11s} "
        f"{'ctrlVessel':>11s} {'permAllBright':>14s}")
    scored = []
    for r in per_night:
        ex = tp_by_night.get(r["date"], 0) - tc_by_night.get(r["date"], 0)
        scored.append((r["date"], r["month"], r["moon"], ex,
                       tp_by_night.get(r["date"], 0), tc_by_night.get(r["date"], 0),
                       r["np"]))
    scored.sort(key=lambda x: -x[3])
    for s in scored[:12]:
        log(f"  {s[0]:12s} {s[1]:3d} {s[2]:7.1f} {s[3]:8d} {s[4]:11d} {s[5]:11d} {s[6]:14d}")

    active = [s for s in scored if s[3] >= 20]
    log(f"\n  nights with an excess of >=20 transient cells: {len(active)}")
    log(f"    dates: " + ", ".join(f"{s[0]} ({s[1]:02d})" for s in active))
    log(f"    months: {sorted(set(s[1] for s in active))}")
    log(f"    in May-Aug: {sum(1 for s in active if s[1] in MOR)} of {len(active)}")

    # ---------- 2. the biggest night in detail ----------
    if active:
        big = active[0][0]
        log("\n" + "=" * 84)
        log(f"2  THE BIGGEST ACTIVE NIGHT: {big}")
        log("=" * 84)
        a = rasterio.open(f"{RAW}/SNPP_{big}.tif").read(1)
        b = (a >= THR) & dp
        ys2, xs2 = np.nonzero(b)
        lons = TR.c + xs2 * TR.a + TR.a / 2
        lats = TR.f + ys2 * TR.e + TR.e / 2
        log(f"    bright deep permitted cells: {len(ys2)}")
        log(f"    spatial extent: lon {lons.min():.3f}..{lons.max():.3f} "
            f"({(lons.max()-lons.min())*111.32*math.cos(math.radians(22.2)):.1f} km), "
            f"lat {lats.min():.3f}..{lats.max():.3f}")
        log(f"    centroid: {lons.mean():.4f}E, {lats.mean():.4f}N")
        # is it a tight cluster or a spread fleet?
        sd = math.hypot(lons.std() * 111.32 * math.cos(math.radians(22.2)),
                        lats.std() * 110.574)
        log(f"    spread (1 SD): {sd:.2f} km  -> "
            f"{'a tight cluster (a single vessel or structure)' if sd < 2 else 'a spread-out fleet'}")
        c = collections.Counter()
        for lo, la in zip(lons, lats):
            c[(round(lo, 2), round(la, 2))] += 1
        log(f"    distinct 0.01-deg cells: {len(c):,}; top: {c.most_common(5)}")
        from shapely.geometry import Point
        hits = collections.Counter()
        for lo, la in zip(lons, lats):
            pt = Point(lo, la)
            for nm, g in zip(perm.OBJNAM, perm.geometry):
                if g.contains(pt):
                    hits[nm] += 1
        log(f"    by permitted area: {hits.most_common()}")

    # ---------- 3. active nights per year ----------
    log("\n" + "=" * 84)
    log("3  ACTIVE NIGHTS PER YEAR (excess >= 20 transient cells)")
    log("=" * 84)
    per_year = collections.defaultdict(list)
    for s in scored:
        if s[3] >= 20:
            per_year[s[1] and 0 or 0].append(s) if False else None
    by_year = collections.defaultdict(list)
    for s in scored:
        if s[3] >= 20:
            by_year[int(s[0][:4])].append(s)
    log(f"  {'year':6s} {'nActive':>8s} {'months':>22s} {'total excess':>13s}")
    for y in sorted(by_year):
        v = by_year[y]
        log(f"  {y}   {len(v):>6d}   {str([s[1] for s in v]):>22s} {sum(s[3] for s in v):>13d}")
    yrs = sorted(by_year)
    mor_n = sum(1 for y in yrs for s in by_year[y] if s[1] in MOR)
    tot_n = sum(len(by_year[y]) for y in yrs)
    log(f"\n    total active nights: {tot_n} over {len(yrs)} years "
        f"({tot_n/len(yrs):.1f} per year)")
    log(f"    of which in May-Aug: {mor_n} ({100*mor_n/max(tot_n,1):.0f}%)")
    log(f"    months with an active night: {sorted(set(s[1] for y in yrs for s in by_year[y]))}")

    out = {
        "active_nights_threshold_excess": 20,
        "active_nights": [{"date": s[0], "month": s[1], "moon_pct": s[2],
                            "excess": s[3], "perm_vessel": s[4],
                            "ctrl_vessel": s[5], "perm_all_bright": s[6]}
                           for s in active],
        "n_active": len(active),
        "n_active_in_moratorium": sum(1 for s in active if s[1] in MOR),
        "months_with_active_night": sorted(set(s[1] for s in active)),
        "active_per_year": {str(y): len(v) for y, v in sorted(by_year.items())},
        "mean_active_per_year": tot_n / len(yrs) if yrs else None,
    }
    json.dump(out, open(f"{ROOT}/active_nights.json", "w"), indent=2)
    log(f"\n  wrote {ROOT}/active_nights.json")


if __name__ == "__main__":
    main()
