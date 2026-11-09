#!/usr/bin/env python3
"""
FINAL analysis: the seasonal light-pollution pattern from fishing lights
over Hong Kong, and what it means for stargazing.

WHY THE FIRST ATTEMPT WAS WRONG (and how this version fixes it)
  The permitted bright-light fishing polygons overlap COASTAL LAND.  A
  naive mean over the polygon is dominated by the city's own glow on
  those land pixels, which swamps the fishing signal.  So:
    - the analysis runs on WATER pixels only (the AFCD fishing-operation
      grids define HK's waters)
    - the comparison is permitted-water MINUS other-HK-water, which
      cancels the scene-wide seasonal drift (haze, cloud, atmospheric
      scattering) that affects the whole image
    - the open-sea control is used as a third, independent check

THE ESTIMATOR
  Per-cell monthly composites (mean of all nights in that month, all
  years).  A per-cell composite is far more robust than a per-night
  mean: each pixel's seasonal difference is built from dozens of
  observations, and cloud-contaminated nights average out.

THE KEY NUMBERS
  attributable  = D[permitted water] - D[other HK water]
                  D = May-Aug composite MINUS Sep-Apr composite
  Plus a bootstrap 95% CI, a per-year consistency count, a per-polygon
  breakdown, and the BRIGHT-PIXEL enrichment (are the moderately
  brightened pixels concentrated in the fishing areas?).
"""
import csv
import json
import math
import os
import statistics

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin

OUT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(OUT, "raw_seasonal")
CSDI = "/Users/davidhermes/GIS Data/hk-spatial/data"
PERMITTED = f"{CSDI}/mardep_rcd_1730952503222_38811.geojson"
FISHING = f"{CSDI}/afcd_rcd_1697167244880_33192.geojson"

WIDTH, HEIGHT = 1200, 840
BBOX_W, BBOX_S, BBOX_E, BBOX_N = 113.72, 22.15, 114.45, 22.60
MORATORIUM = (5, 6, 7, 8)
OPEN = (1, 2, 3, 4, 9, 10, 11, 12)
MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def log(m):
    print(m, flush=True)


def build_masks():
    import geopandas as gpd
    tr = from_origin(BBOX_W, BBOX_N, (BBOX_E - BBOX_W) / WIDTH,
                     (BBOX_N - BBOX_S) / HEIGHT)
    perm = gpd.read_file(PERMITTED)
    fish = gpd.read_file(FISHING)
    if perm.crs is None:
        perm = perm.set_crs(4326)
    if fish.crs is None:
        fish = fish.set_crs(4326)

    water = np.zeros((HEIGHT, WIDTH), dtype=bool)
    for geom in fish.geometry:
        water |= rasterize([(geom, 1)], out_shape=(HEIGHT, WIDTH),
                           transform=tr, fill=0, dtype="uint8").astype(bool)

    pm_all = np.zeros((HEIGHT, WIDTH), dtype=bool)
    pm_water = np.zeros((HEIGHT, WIDTH), dtype=bool)
    for geom in perm.geometry:
        m = rasterize([(geom, 1)], out_shape=(HEIGHT, WIDTH),
                      transform=tr, fill=0, dtype="uint8").astype(bool)
        pm_all |= m
        pm_water |= (m & water)
    log(f"permitted: {pm_all.sum():,} px total, {pm_water.sum():,} px on water")
    log(f"HK water (AFCD grids): {water.sum():,} px")
    return perm, fish, tr, water, pm_all, pm_water


def monthly_composites(rows):
    """Mean of every night in each month, per cell."""
    by_m = {}
    for r in rows:
        by_m.setdefault(r["month"], []).append(r)
    comp = {}
    for m in range(1, 13):
        sel = by_m.get(m, [])
        if not sel:
            continue
        acc = np.zeros((HEIGHT, WIDTH), dtype=np.float64)
        for r in sel:
            p = os.path.join(RAW, f"SNPP_{r['date']}.tif")
            if not os.path.exists(p):
                continue
            with rasterio.open(p) as ds:
                acc += ds.read(1)
        comp[m] = acc / len(sel)
        log(f"  month {MONTHS[m]}: {len(sel)} nights -> composite")
    return comp


def bootstrap_diff(D, a, b, n=3000, seed=13):
    rng = np.random.default_rng(seed)
    va, vb = D[a], D[b]
    out = []
    for _ in range(n):
        out.append(rng.choice(va, len(va), replace=True).mean()
                   - rng.choice(vb, len(vb), replace=True).mean())
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def main():
    with open(os.path.join(OUT, "seasonal_nights.json")) as f:
        rows = json.load(f)
    log(f"nights: {len(rows)}  ({rows[0]['date']} .. {rows[-1]['date']})")

    perm, fish, tr, water, pm_all, pm_water = build_masks()
    ctrl = np.load(os.path.join(OUT, "control_mask.npy"))
    other_water = water & ~pm_water & ~ctrl

    log("building per-cell monthly composites")
    comp = monthly_composites(rows)
    ma = np.mean([comp[m] for m in MORATORIUM], axis=0)
    sa = np.mean([comp[m] for m in OPEN], axis=0)
    D = ma - sa

    np.save(os.path.join(OUT, "_D_mor_minus_open.npy"), D)
    np.save(os.path.join(OUT, "_ma_composite.npy"), ma)
    np.save(os.path.join(OUT, "_sa_composite.npy"), sa)

    # ---------------- the headline ---------------------------------
    d_per = D[pm_water].mean()
    d_oth = D[other_water].mean()
    d_ctl = D[ctrl].mean()
    attrib = d_per - d_oth
    lo, hi = bootstrap_diff(D, pm_water, other_water)
    lo2, hi2 = bootstrap_diff(D, pm_water, ctrl)

    print("\n" + "=" * 68)
    print("HEADLINE: seasonal change in the permitted fishing areas")
    print("=" * 68)
    print("  May-Aug composite MINUS Sep-Apr composite, per cell")
    print(f"    permitted areas, water pixels : {d_per:+.3f} DN")
    print(f"    other HK water                : {d_oth:+.3f} DN")
    print(f"    open-sea control              : {d_ctl:+.3f} DN")
    print(f"  ATTRIBUTABLE (permitted - other HK water): {attrib:+.3f} DN")
    print(f"    bootstrap 95% CI: [{lo:+.3f}, {hi:+.3f}]")
    print(f"  vs open-sea control: {d_per - d_ctl:+.3f} DN  CI [{lo2:+.3f}, {hi2:+.3f}]")

    # ---------------- per-year consistency -------------------------
    print("\n" + "=" * 68)
    print("PER-YEAR CONSISTENCY (same statistic, one year at a time)")
    print("=" * 68)
    per_year = {}
    for r in rows:
        per_year.setdefault(r["year"], []).append(r)
    consistent = 0
    tested = 0
    for y in sorted(per_year):
        sel = per_year[y]
        mo = [r for r in sel if r["month"] in MORATORIUM]
        op = [r for r in sel if r["month"] in OPEN]
        if len(mo) < 6 or len(op) < 6:
            continue

        def comp_of(rs):
            acc = np.zeros((HEIGHT, WIDTH), dtype=np.float64)
            n = 0
            for r in rs:
                p = os.path.join(RAW, f"SNPP_{r['date']}.tif")
                if os.path.exists(p):
                    with rasterio.open(p) as ds:
                        acc += ds.read(1)
                    n += 1
            return acc / max(n, 1)

        dy = comp_of(mo) - comp_of(op)
        v = dy[pm_water].mean() - dy[other_water].mean()
        tested += 1
        if v > 0:
            consistent += 1
        print(f"  {y}: {v:+.3f} DN   (n_mor={len(mo)}, n_open={len(op)})")
    print(f"  -> {consistent}/{tested} years show a brighter fishing area in May-Aug")

    # ---------------- per-polygon ----------------------------------
    print("\n" + "=" * 68)
    print("PER-AREA (water pixels only)")
    print("=" * 68)
    poly_rows = []
    for i, geom in enumerate(perm.geometry):
        m = rasterize([(geom, 1)], out_shape=(HEIGHT, WIDTH), transform=tr,
                      fill=0, dtype="uint8").astype(bool) & water
        if m.sum() < 50:
            continue
        v = D[m].mean() - D[other_water].mean()
        poly_rows.append({
            "area": perm.OBJNAM.iloc[i],
            "centroid_lon": round(perm.geometry.iloc[i].centroid.x, 4),
            "centroid_lat": round(perm.geometry.iloc[i].centroid.y, 4),
            "water_px": int(m.sum()),
            "may_aug": round(float(ma[m].mean()), 2),
            "sep_apr": round(float(sa[m].mean()), 2),
            "attributable_change": round(float(v), 3),
        })
    poly_rows.sort(key=lambda r: -r["attributable_change"])
    print(f"  {'area':44s} {'MayAug':>7s} {'SepApr':>7s} {'change':>8s}")
    for p in poly_rows:
        print(f"  {p['area'][:44]:44s} {p['may_aug']:7.1f} {p['sep_apr']:7.1f} "
              f"{p['attributable_change']:+8.3f}")

    # ---------------- bright-pixel enrichment ----------------------
    print("\n" + "=" * 68)
    print("BRIGHT-PIXEL ENRICHMENT (are brightened pixels in the fishing areas?)")
    print("=" * 68)
    enrich = []
    for thr in (2, 5, 10, 15, 20):
        r_per = (pm_water & (D >= thr)).sum() / pm_water.sum() * 100
        r_oth = (other_water & (D >= thr)).sum() / other_water.sum() * 100
        enrich.append({"threshold_dn": thr,
                       "permitted_pct": round(float(r_per), 3),
                       "other_water_pct": round(float(r_oth), 3),
                       "enrichment": round(float(r_per / r_oth), 2) if r_oth > 0 else None})
        print(f"  change >= +{thr:2d} DN: permitted {r_per:6.3f}%  "
              f"other water {r_oth:6.3f}%  enrichment {r_per / r_oth:5.2f}x")

    # ---------------- the monthly curve ----------------------------
    print("\n" + "=" * 68)
    print("MONTHLY PATTERN (the recommendation table)")
    print("=" * 68)
    by_m = {}
    for r in rows:
        by_m.setdefault(r["month"], []).append(r)
    monthly = []
    for m in range(1, 13):
        if m not in comp:
            continue
        others = [comp[k] for k in comp if k != m]
        diff = comp[m] - np.mean(others, axis=0)
        v = diff[pm_water].mean() - diff[other_water].mean()
        monthly.append({
            "month": m, "name": MONTHS[m],
            "n_nights": len(by_m.get(m, [])),
            "level_permitted_water": round(float(comp[m][pm_water].mean()), 2),
            "level_other_hk_water": round(float(comp[m][other_water].mean()), 2),
            "attributable_vs_other_months": round(float(v), 3),
            "in_moratorium": m in MORATORIUM,
        })
        print(f"  {MONTHS[m]:4s} n={len(by_m.get(m, [])):3d}  "
              f"level {comp[m][pm_water].mean():7.2f}  "
              f"attributable vs rest of year {v:+7.3f}"
              f"{'   <- moratorium' if m in MORATORIUM else ''}")

    best = min(monthly, key=lambda r: r["attributable_vs_other_months"])
    worst = max(monthly, key=lambda r: r["attributable_vs_other_months"])
    print(f"\n  DARKEST month (fishing-light signal): {best['name']} "
          f"({best['attributable_vs_other_months']:+.3f})")
    print(f"  BRIGHTEST month (fishing-light signal): {worst['name']} "
          f"({worst['attributable_vs_other_months']:+.3f})")

    # ---------------- moon check ------------------------------------
    print("\n" + "=" * 68)
    print("CONFOUNDER CHECK")
    print("=" * 68)
    for lab, lo_m, hi_m in (("moon <40%", 0, 40), ("moon >80%", 80, 101)):
        sel = [r for r in rows if lo_m <= r["moon_pct"] < hi_m]
        ctl = [r["control_mean"] for r in sel]
        print(f"  {lab}: n={len(sel):4d}  control mean {statistics.mean(ctl):6.2f}")

    # ---------------- write ----------------------------------------
    result = {
        "nights": len(rows),
        "period": [rows[0]["date"], rows[-1]["date"]],
        "method": "per-cell monthly composites; permitted WATER pixels minus other HK water",
        "may_aug_minus_sep_apr": {
            "permitted_water": round(float(d_per), 3),
            "other_hk_water": round(float(d_oth), 3),
            "open_sea_control": round(float(d_ctl), 3),
            "attributable": round(float(attrib), 3),
            "ci95_low": round(lo, 3), "ci95_high": round(hi, 3),
            "vs_control": round(float(d_per - d_ctl), 3),
            "vs_control_ci95": [round(lo2, 3), round(hi2, 3)],
        },
        "years_consistent": f"{consistent}/{tested}",
        "per_area": poly_rows,
        "bright_pixel_enrichment": enrich,
        "monthly": monthly,
        "darkest_month": best["name"],
        "brightest_month": worst["name"],
    }
    with open(os.path.join(OUT, "fishing_light_seasonal.json"), "w") as f:
        json.dump(result, f, indent=1)

    with open(os.path.join(OUT, "fishing_light_monthly.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "n_nights", "permitted_water_level_DN",
                    "other_hk_water_level_DN", "attributable_vs_other_months_DN",
                    "in_fishing_moratorium"])
        for m in monthly:
            w.writerow([m["name"], m["n_nights"], m["level_permitted_water"],
                        m["level_other_hk_water"], m["attributable_vs_other_months"],
                        "yes" if m["in_moratorium"] else "no"])

    print("\nwrote fishing_light_seasonal.json, fishing_light_monthly.csv")
    print("OK")


if __name__ == "__main__":
    main()
