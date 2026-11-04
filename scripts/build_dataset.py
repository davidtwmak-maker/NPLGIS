#!/usr/bin/env python3
"""Assemble the landslide susceptibility training set.

Labels   : CSDI Location of Landslide Incidents (positive) + ENTLI 1924-2022
           historical landslide crowns (positive) vs sampled pseudo-absent cells.
Predictors: terrain from work/terrain_200m.npz
           + antecedent rainfall from CSDI GEO Raingauge Data (2005-2026)
           + geology class from CSDI Geological Map 1:100,000

Writes work/train_table.csv and work/grid_cells.csv
"""
import os, csv, json, datetime, math
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
WORK = os.path.join(BASE, "work")

# ---------------------------------------------------------------- terrain grid
tz = np.load(os.path.join(WORK, "terrain_200m.npz"))
CELL = float(tz["cell"]); X0 = float(tz["x0"]); Y0 = float(tz["y0"])
slope, relief, curv, rough = tz["slope"], tz["relief"], tz["curv"], tz["rough"]
slope_max, slope_p90 = tz["slope_max"], tz["slope_p90"]
twi, spi, elev, valid = tz["twi"], tz["spi"], tz["elev"], tz["valid"]
NY, NX = slope.shape
print(f"terrain grid {NY}x{NX} @ {CELL} m, valid {valid.sum()}", flush=True)

# land cover fractions (ESA WorldCover 2021)
lcz = np.load(os.path.join(WORK, "landcover_200m.npz"))
LC_TREE, LC_SHRUB, LC_GRASS = lcz["tree"], lcz["shrub"], lcz["grass"]
LC_BARE, LC_BUILT, LC_VEG = lcz["bare"], lcz["built"], lcz["veg"]
print(f"land cover loaded (tree mean {LC_TREE.mean():.3f})", flush=True)


def cell_of(e, n):
    """HK1980 easting/northing -> (row, col) in the 200 m grid.

    The grid cell (row, col) has its CENTRE at easting = X0 + col*CELL and
    northing = Y0 - row*CELL, so the containing cell is found by rounding to
    the NEAREST centre, not by truncating toward the origin. Truncation puts
    every record whose offset exceeds half a cell into the neighbouring cell.
    """
    c = int((e - X0) / CELL + 0.5)
    r = int((Y0 - n) / CELL + 0.5)
    if 0 <= r < NY and 0 <= c < NX:
        return int(r), int(c)
    return None


def sample(arr, e, n):
    rc = cell_of(e, n)
    if rc is None:
        return np.nan
    r, c = rc
    v = arr[r, c]
    return np.nan if (v is None or (isinstance(v, float) and math.isnan(v))) else v


# ---------------------------------------------------------------- rainfall
# GEO Raingauge Data: daily rainfall per gauge. Build a station table and a
# per-day lookup of rainfall extremes, then attach to each landslide by the
# nearest gauges (IDW) and by the antecedent 3-day / 30-day totals.
print("loading rainfall ...", flush=True)
rain = {}
gauge_xy = {}
with open(os.path.join(RAW, "raingauge.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        g = r["Raingauge_No"]
        try:
            val = float(r["Rainfall"])
        except (TypeError, ValueError):
            continue
        d = r["Date_"]
        rain.setdefault(g, {})[d] = val
        try:
            gauge_xy[g] = (float(r["Easting"]), float(r["Northing"]), r["Location"])
        except (TypeError, ValueError):
            pass
print(f"  gauges={len(rain)} days/gauges={sum(len(v) for v in rain.values())}", flush=True)

# Daily basin-wide statistics (any HK gauge) for rainfall-event context
by_day = {}
for g, dd in rain.items():
    for d, v in dd.items():
        by_day.setdefault(d, []).append(v)


def epoch_to_date(ms):
    try:
        v = float(ms)
    except (TypeError, ValueError):
        return None
    if v > 1e11:
        return datetime.datetime.utcfromtimestamp(v / 1000).date()
    if v > 1e9:
        return datetime.datetime.utcfromtimestamp(v).date()
    return None


def ymd(s):
    for fmt in ("%Y%m%d", "%d/%m/%Y", "%Y-%m-%d", "%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


# Precompute per-day max rain across HK (a proxy for territory-wide rainstorm
# intensity) and the per-station series sorted by date for antecedent windows.
day_max = {d: max(v) for d, v in by_day.items()}
day_mean = {d: sum(v) / len(v) for d, v in by_day.items()}
days_sorted = sorted(day_max)
day_index = {d: i for i, d in enumerate(days_sorted)}


def antecedent(station_rain, target, window):
    """Max and sum rainfall over the `window` days before target for a station."""
    if target is None:
        return np.nan, np.nan
    ser = station_rain
    keys = sorted(k for k in ser if k < target)
    if not keys:
        return np.nan, np.nan
    window_keys = keys[-window:]
    vals = [ser[k] for k in window_keys]
    return max(vals), sum(vals)


# ---------------------------------------------------------------- positives
def load_positives():
    pos = []
    # 1. modern incidents (with dates)
    with open(os.path.join(RAW, "incidents.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                e, n = float(r["EASTING"]), float(r["NORTHING"])
            except (TypeError, ValueError):
                continue
            d = epoch_to_date(r.get("FAILDATE", ""))
            if d is None:
                d = ymd(r.get("FAILDATE", "") or "")
            pos.append(dict(src="incident", e=e, n=n, date=d,
                            feat=r.get("FEATTYPE", ""), scale=r.get("SCALE", ""),
                            incid=r.get("INCID", "")))
    n_inc = len(pos)
    # 2. ENTLI historical crowns (1924-2022)
    with open(os.path.join(RAW, "entli_crown.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                e, n = float(r["EASTING"]), float(r["NORTHING"])
            except (TypeError, ValueError):
                continue
            d = ymd(r.get("YEAR_1", "") or "")
            if d is None:
                continue
            pos.append(dict(src="entli", e=e, n=n, date=d,
                            feat="Natural Hillside", scale=r.get("M_WIDTH", ""),
                            incid=r.get("ENTLI_NO", "")))
    print(f"positives: incidents={n_inc} entli={len(pos)-n_inc} total={len(pos)}", flush=True)
    return pos


# ---------------------------------------------------------------- geology lookup
print("loading geology ...", flush=True)
# The weathering factor is derived from lithology by prep_geology.py (see that
# file for the full justification of why weathering is not directly mapped).
gz = np.load(os.path.join(WORK, "geology_200m.npz"))
WX = gz["wx"]                       # dominant weathering class per 200 m cell
WX_FRAC = gz["wx_frac"]             # areal fraction per class (4, NY, NX)
WX_FELSIC = WX_FRAC[3]              # deeply weathered felsic (granite family)
WX_VOLC = WX_FRAC[2]                # weathered volcanic / tuffaceous
WX_MID = WX_FRAC[1]                 # moderate (clastic, metamorphic)
WX_RES = WX_FRAC[0]                 # resistant / reclamation
WX_CLASS = WX                       # 0..3 integer class
print(f"  weathering classes mapped: valid cells "
      f"{int(np.isfinite(WX_FELSIC).sum())}", flush=True)


def build_features(points, label, rng, with_date=True):
    rows = []
    for p in points:
        e, n = p["e"], p["n"]
        s = sample(slope, e, n)
        if s is None or math.isnan(s):
            continue
        if not valid[cell_of(e, n)]:
            continue
        r, c = cell_of(e, n)
        rec = dict(
            label=label, src=p["src"], incid=p.get("incid", ""),
            easting=e, northing=n,
            slope=s,
            slope_max=sample(slope_max, e, n),
            slope_p90=sample(slope_p90, e, n),
            relief=sample(relief, e, n),
            curv=sample(curv, e, n),
            rough=sample(rough, e, n),
            twi=sample(twi, e, n),
            spi=sample(spi, e, n),
            elev=sample(elev, e, n),
            lc_tree=float(LC_TREE[r, c]),
            lc_shrub=float(LC_SHRUB[r, c]),
            lc_grass=float(LC_GRASS[r, c]),
            lc_bare=float(LC_BARE[r, c]),
            lc_built=float(LC_BUILT[r, c]),
            lc_veg=float(LC_VEG[r, c]),
            wx_felsic=float(WX_FELSIC[r, c]),
            wx_volc=float(WX_VOLC[r, c]),
            wx_mid=float(WX_MID[r, c]),
            wx_res=float(WX_RES[r, c]),
            wx_class=int(WX_CLASS[r, c]),
        )
        # rainfall: nearest-gauge search over station coordinates
        d = p.get("date")
        if d and gauge_xy:
            # find 3 nearest gauges
            cand = sorted(gauge_xy.items(), key=lambda kv: (kv[1][0] - e) ** 2 + (kv[1][1] - n) ** 2)[:3]
            wts, r3max, r3sum, r30max, r30sum = [], [], [], [], []
            for k, (ge, gn, _loc) in cand:
                ser = rain.get(k, {})
                m3, s3 = antecedent(ser, d.isoformat().replace("-", ""), 3)
                m30, s30 = antecedent(ser, d.isoformat().replace("-", ""), 30)
                dist = math.hypot(ge - e, gn - n)
                w = 1.0 / (dist + 1.0)
                wts.append(w)
                r3max.append(m3); r3sum.append(s3); r30max.append(m30); r30sum.append(s30)
            wts = np.array(wts, dtype=float); wts = wts / wts.sum()
            def wavg(arr):
                arr = np.array(arr, dtype=float)
                m = np.isfinite(arr)
                if not m.any():
                    return np.nan
                ww = wts[m]
                return float(np.sum(ww * arr[m]) / ww.sum())
            rec["rain3_max"] = wavg(r3max)
            rec["rain3_sum"] = wavg(r3sum)
            rec["rain30_max"] = wavg(r30max)
            rec["rain30_sum"] = wavg(r30sum)
            dstr = d.isoformat().replace("-", "")
            rec["hk_day_max"] = day_max.get(dstr, np.nan)
            rec["hk_day_mean"] = day_mean.get(dstr, np.nan)
        rows.append(rec)
    return rows


def main():
    pos = load_positives()
    # de-duplicate positives landing in the same 200 m cell (keep first)
    seen = set()
    uniq = []
    for p in pos:
        rc = cell_of(p["e"], p["n"])
        if rc is None:
            continue
        key = (rc, p["src"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    print(f"unique positive cells: {len(uniq)}", flush=True)

    rows = build_features(uniq, 1, None)
    print(f"positive rows with predictors: {len(rows)}", flush=True)

    # ---- pseudo-absent: sample land cells with no landslide record ----
    # DATE MATCHING: each negative is assigned the date of a randomly chosen
    # positive. Two reasons:
    #   1. Rainfall on the failure date is a real trigger signal; if negatives
    #      are drawn on random (mostly dry) days, the model separates the
    #      classes by "was it raining" instead of learning susceptibility.
    #   2. Positives before 2005 have no matching gauge record, so their
    #      rainfall is NaN while every negative has a value -- the MISSINGNESS
    #      itself becomes the label (XGBoost splits on NaN natively).
    # Matching the date distribution removes both artefacts.
    rng = np.random.default_rng(42)
    pos_cells = {cell_of(p["e"], p["n"]) for p in uniq}
    dated = [p for p in uniq if p.get("date") is not None]
    print(f"positives with a usable date: {len(dated)}", flush=True)
    neg_rows = []
    target_neg = len(rows)
    tries = 0
    while len(neg_rows) < target_neg and tries < target_neg * 400:
        tries += 1
        r = int(rng.integers(0, NY)); c = int(rng.integers(0, NX))
        if not valid[r, c]:
            continue
        if (r, c) in pos_cells:
            continue
        e = X0 + c * CELL
        n = Y0 - r * CELL
        d = dated[int(rng.integers(0, len(dated)))]["date"] if dated else None
        rec = dict(label=0, src="pseudo", incid="", easting=e, northing=n,
                   slope=slope[r, c], slope_max=slope_max[r, c],
                   slope_p90=slope_p90[r, c],
                   relief=relief[r, c], curv=curv[r, c],
                   rough=rough[r, c], twi=twi[r, c], spi=spi[r, c], elev=elev[r, c],
                   lc_tree=float(LC_TREE[r, c]), lc_shrub=float(LC_SHRUB[r, c]),
                   lc_grass=float(LC_GRASS[r, c]), lc_bare=float(LC_BARE[r, c]),
                   lc_built=float(LC_BUILT[r, c]), lc_veg=float(LC_VEG[r, c]),
                   wx_felsic=float(WX_FELSIC[r, c]), wx_volc=float(WX_VOLC[r, c]),
                   wx_mid=float(WX_MID[r, c]), wx_res=float(WX_RES[r, c]),
                   wx_class=int(WX_CLASS[r, c]))
        # same rainfall extraction as positives (nearest 3 gauges, IDW)
        cand = sorted(gauge_xy.items(), key=lambda kv: (kv[1][0] - e) ** 2 + (kv[1][1] - n) ** 2)[:3]
        wts, r3max, r3sum, r30max, r30sum = [], [], [], [], []
        for k, (ge, gn, _loc) in cand:
            ser = rain.get(k, {})
            m3, s3 = antecedent(ser, d.isoformat().replace("-", ""), 3)
            m30, s30 = antecedent(ser, d.isoformat().replace("-", ""), 30)
            dist = math.hypot(ge - e, gn - n)
            wts.append(1.0 / (dist + 1.0))
            r3max.append(m3); r3sum.append(s3); r30max.append(m30); r30sum.append(s30)
        wts = np.array(wts, dtype=float); wts = wts / wts.sum()
        def wavg(arr):
            arr = np.array(arr, dtype=float)
            m = np.isfinite(arr)
            if not m.any():
                return np.nan
            ww = wts[m]
            return float(np.sum(ww * arr[m]) / ww.sum())
        rec["rain3_max"] = wavg(r3max)
        rec["rain3_sum"] = wavg(r3sum)
        rec["rain30_max"] = wavg(r30max)
        rec["rain30_sum"] = wavg(r30sum)
        dstr = d.isoformat().replace("-", "")
        rec["hk_day_max"] = day_max.get(dstr, np.nan)
        rec["hk_day_mean"] = day_mean.get(dstr, np.nan)
        neg_rows.append(rec)
    print(f"negative rows: {len(neg_rows)}", flush=True)

    allrows = rows + neg_rows
    fields = ["label", "src", "incid", "easting", "northing", "slope", "slope_max",
              "slope_p90", "relief", "curv", "rough", "twi", "spi", "elev",
              "lc_tree", "lc_shrub", "lc_grass", "lc_bare", "lc_built", "lc_veg",
              "wx_felsic", "wx_volc", "wx_mid", "wx_res", "wx_class",
              "rain3_max", "rain3_sum", "rain30_max", "rain30_sum",
              "hk_day_max", "hk_day_mean"]
    out = os.path.join(WORK, "train_table.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in allrows:
            w.writerow({k: r.get(k, "") for k in fields})
    print("wrote", out, len(allrows), "rows", flush=True)

    # grid cell table (all valid cells, for prediction)
    gpath = os.path.join(WORK, "grid_cells.csv")
    n = 0
    with open(gpath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "col", "easting", "northing", "slope", "slope_max",
                    "slope_p90", "relief", "curv", "rough", "twi", "spi", "elev",
                    "lc_tree", "lc_shrub", "lc_grass", "lc_bare", "lc_built", "lc_veg",
                    "wx_felsic", "wx_volc", "wx_mid", "wx_res", "wx_class",
                    "rain3_max", "rain3_sum", "rain30_max", "rain30_sum",
                    "hk_day_max", "hk_day_mean"])
        for r in range(NY):
            for c in range(NX):
                if not valid[r, c]:
                    continue
                w.writerow([r, c, X0 + c * CELL, Y0 - r * CELL,
                            slope[r, c], slope_max[r, c], slope_p90[r, c],
                            relief[r, c], curv[r, c], rough[r, c],
                            twi[r, c], spi[r, c], elev[r, c],
                            float(LC_TREE[r, c]), float(LC_SHRUB[r, c]),
                            float(LC_GRASS[r, c]), float(LC_BARE[r, c]),
                            float(LC_BUILT[r, c]), float(LC_VEG[r, c]),
                            float(WX_FELSIC[r, c]), float(WX_VOLC[r, c]),
                            float(WX_MID[r, c]), float(WX_RES[r, c]),
                            int(WX_CLASS[r, c]),
                            "", "", "", "", "", ""])
                n += 1
    print("wrote", gpath, n, "cells", flush=True)


if __name__ == "__main__":
    main()
