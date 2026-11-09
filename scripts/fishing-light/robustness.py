#!/usr/bin/env python3
"""
ROBUSTNESS: does the seasonal effect survive removing the single biggest
year, and removing the single biggest night?

2018 contributes +2.08 percentage points against a typical +0.2 to +0.6.
If the effect is carried by one night, it is not a seasonal signal - it is
an episodic event.  This script reports the estimate with various exclusions,
plus a leave-one-year-out table.
"""
import collections
import json
import math
import os
import random
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
THR = 140
MOR = (5, 6, 7, 8)


def log(m):
    print(m, flush=True)


def boot(py, n=4000, seed=20261109):
    years = sorted(py)
    rng = random.Random(seed)
    v = sorted(statistics.mean(py[rng.choice(years)] for _ in years) for _ in range(n))
    lo, hi = v[int(0.025 * n)], v[int(0.975 * n)]
    p = 2 * min(sum(1 for x in v if x <= 0), sum(1 for x in v if x >= 0)) / n
    return lo, hi, p


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
              if os.path.exists(f"{RAW}/SNPP_{r['date']}.tif")]
    nights.sort()

    per_night = []
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
        bp = dp & (a >= THR)
        bc = dc & (a >= THR)
        per_night.append({"date": date, "year": year, "month": month,
                          "rp": float(bp.sum()) / int(dp.sum()) * 100,
                          "ro": float(bc.sum()) / int(dc.sum()) * 100})

    def effect(subset):
        py = collections.defaultdict(lambda: {"mor": [], "oth": []})
        for r in subset:
            py[r["year"]]["mor" if r["month"] in MOR else "oth"].append(r["rp"] - r["ro"])
        out = {y: statistics.mean(d["mor"]) - statistics.mean(d["oth"])
               for y, d in py.items() if d["mor"] and d["oth"]}
        return out

    full = effect(per_night)
    log("=" * 80)
    log("1  LEAVE-ONE-YEAR-OUT")
    log("=" * 80)
    log(f"  {'excluded':10s} {'estimate':>10s} {'95% CI':>22s} {'p':>8s} {'years+':>7s}")
    m, lo, hi, p = statistics.mean(full.values()), *boot(full)
    log(f"  {'(none)':10s} {m:+10.4f} [{lo:+9.4f},{hi:+9.4f}] {p:8.4f} "
        f"{sum(1 for v in full.values() if v>0):>4d}/{len(full)}")
    for y in sorted(full):
        sub = {k: v for k, v in full.items() if k != y}
        m2 = statistics.mean(sub.values())
        l2, h2, p2 = boot(sub)
        log(f"  {y:<10d} {m2:+10.4f} [{l2:+9.4f},{h2:+9.4f}] {p2:8.4f} "
            f"{sum(1 for v in sub.values() if v>0):>4d}/{len(sub)}")

    log("\n" + "=" * 80)
    log("2  LEAVE-ONE-NIGHT-OUT: the effect with the biggest nights removed")
    log("=" * 80)
    contrib = []
    for y, d in collections.defaultdict(
            lambda: {"mor": [], "oth": []},
            {y: {"mor": [r["rp"] - r["ro"] for r in per_night
                         if r["year"] == y and r["month"] in MOR],
                 "oth": [r["rp"] - r["ro"] for r in per_night
                         if r["year"] == y and r["month"] not in MOR]}
             for y in set(r["year"] for r in per_night)}).items():
        contrib.append((max(d["mor"], default=0) - max(d["oth"], default=0), y))
    contrib.sort(reverse=True)
    log(f"  biggest single-night swing by year: {[(y, round(c,2)) for c, y in contrib[:5]]}")

    # remove the single most extreme night overall
    allv = []
    for r in per_night:
        allv.append((r["rp"] - r["ro"], r["date"]))
    allv.sort(reverse=True)
    for k in (1, 3, 5, 10):
        drop = {d for _, d in allv[:k]}
        sub = [r for r in per_night if r["date"] not in drop]
        eff = effect(sub)
        m3, l3, h3, p3 = statistics.mean(eff.values()), *boot(eff)
        log(f"  dropping the {k:2d} most extreme night(s): "
            f"{m3:+.4f} pp  CI[{l3:+.4f},{h3:+.4f}]  p={p3:.4f}  "
            f"{sum(1 for v in eff.values() if v>0)}/{len(eff)} years")

    log("\n" + "=" * 80)
    log("3  SENSITIVITY TO THE BRIGHTNESS THRESHOLD")
    log("=" * 80)
    log(f"  {'thr':>5s} {'estimate pp':>13s} {'95% CI':>24s} {'p':>8s} {'years+':>8s}")
    thr_rows = []
    for thr in (80, 100, 120, 140, 160, 180):
        pn = []
        for (date, year, month) in nights:
            a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
            bp = dp & (a >= thr)
            bc = dc & (a >= thr)
            pn.append({"date": date, "year": year, "month": month,
                       "rp": float(bp.sum()) / int(dp.sum()) * 100,
                       "ro": float(bc.sum()) / int(dc.sum()) * 100})
        eff = effect(pn)
        m4, l4, h4, p4 = statistics.mean(eff.values()), *boot(eff)
        thr_rows.append({"threshold": thr, "estimate_pp": m4,
                         "ci_pp": [l4, h4], "p": p4,
                         "years_positive": sum(1 for v in eff.values() if v > 0),
                         "n_years": len(eff)})
        log(f"  {thr:>5d} {m4:>13.4f} [{l4:+11.4f},{h4:+11.4f}] {p4:8.4f} "
            f"{sum(1 for v in eff.values() if v>0):>4d}/{len(eff)}")

    # ---------- persist the robustness numbers ----------
    loo = {}
    for y in sorted(full):
        sub = {k: v for k, v in full.items() if k != y}
        m2 = statistics.mean(sub.values())
        l2, h2, p2 = boot(sub)
        loo[str(y)] = {"estimate_pp": m2, "ci_pp": [l2, h2], "p": p2}

    drop_rows = []
    allv = sorted(((r["rp"] - r["ro"], r["date"]) for r in per_night), reverse=True)
    for k in (1, 3, 5, 10):
        drop = {d for _, d in allv[:k]}
        sub = [r for r in per_night if r["date"] not in drop]
        eff = effect(sub)
        m3, l3, h3, p3 = statistics.mean(eff.values()), *boot(eff)
        drop_rows.append({"n_dropped": k, "estimate_pp": m3, "ci_pp": [l3, h3],
                          "p": p3, "years_positive": sum(1 for v in eff.values() if v > 0),
                          "n_years": len(eff)})

    json.dump({"full": {"estimate_pp": statistics.mean(full.values()),
                        "ci_pp": [boot(full)[0], boot(full)[1]],
                        "p": boot(full)[2],
                        "years_positive": sum(1 for v in full.values() if v > 0),
                        "n_years": len(full),
                        "per_year": {str(k): v for k, v in full.items()}},
               "leave_one_year_out": loo,
               "leave_one_night_out": drop_rows,
               "threshold_sensitivity": thr_rows},
              open(f"{ROOT}/robustness.json", "w"), indent=2)
    log(f"\n  wrote {ROOT}/robustness.json")


if __name__ == "__main__":
    main()
