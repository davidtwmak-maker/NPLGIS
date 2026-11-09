#!/usr/bin/env python3
"""
Seasonal night-lights over Hong Kong: do the lit fishing fleets make the
sky brighter during the fishing moratorium?

THE QUESTION
  Bright-light fishing is permitted ALL YEAR in designated areas of HK
  waters (the law sets no month limit).  The South China Sea summer
  fishing moratorium (1 May - 16 Aug) instead PUSHES mainland fleets
  into HK's eastern and southern waters, where their deck lights are
  visible from shore.  So the seasonal signal should be a BRIGHTENING
  of the permitted areas during May-Aug, and the clearest months for
  dark-sky stargazing in Sai Kung / Lantau South should be Sep-Apr.

THE DATA
  NASA GIBS, VIIRS Day/Night Band:
    VIIRS_SNPP_GapFilled_BRDF_Corrected_DayNightBand_Radiance
      -> 2012-01-19 onward, continuous.  This is the long series.
    VIIRS_NOAA20_GapFilled_BRDF_Corrected_DayNightBand_Radiance
      -> 2018-01-05 onward.  Independent cross-check.
  Marine Department permitted bright-light fishing areas:
    mardep_rcd_1730952503222_38811  (16 polygons)

THE MEASURE
  For every night, for every permitted polygon, the mean DNB value.
  The CONTRAST is measured against a CONTROL region of open sea that is
  (a) never bright, (b) far from the city, (c) far from every permitted
  area.  The control is chosen FROM THE DATA (cells whose maximum over
  all sampled nights stays below a threshold) and then VERIFIED: if the
  control is not stable across nights, it is contaminated and the run
  fails loudly.

  Difference-in-differences:
      excess(t) = mean over permitted polygons at night t
                - mean over control cells at night t
  Moonlight raises BOTH, so it cancels.  City glow barely reaches the
  offshore permitted areas and cancels to the same degree.

GATES (fail loudly, never ship a plausible wrong answer)
  - a night whose raster is all zero is BLANK, not dark
  - urban/open-sea contrast must exceed 4x, else the night is
    cloud-contaminated and the ratios are meaningless
  - the control must be stable: its per-night spread must be small
  - the final monthly means must be backed by enough nights
"""
import io
import json
import math
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
OUT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(OUT, "raw_seasonal")
os.makedirs(RAW, exist_ok=True)

GIBS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
# WMS 1.3.0 + EPSG:4326 => axis order is LAT,LON => BBOX is S,W,N,E
BBOX_S, BBOX_W, BBOX_N, BBOX_E = 22.15, 113.72, 22.60, 114.45
WIDTH, HEIGHT = 1200, 840

CSDI = f"{GIS_DATA}/hk-spatial/data"
PERMITTED = f"{CSDI}/mardep_rcd_1730952503222_38811.geojson"

SNPP = "VIIRS_SNPP_GapFilled_BRDF_Corrected_DayNightBand_Radiance"
NOAA20 = "VIIRS_NOAA20_GapFilled_BRDF_Corrected_DayNightBand_Radiance"

YEAR_FROM, YEAR_TO = 2012, 2026
NIGHTS_PER_MONTH = 4
NIGHT_DAYS = [5, 13, 21, 28]

# Mainland South China Sea summer moratorium: 1 May - 16 Aug.
MORATORIUM_MONTHS = (5, 6, 7, 8)

URBAN_CORE = (114.17, 22.319)        # Mong Kok
MIN_URBAN_DIST_KM = 20.0
CONTROL_MAX_VALUE = 60               # cell must never exceed this
CONTROL_MIN_DIST_KM = 1.5            # from any permitted-area cell

_print_lock = threading.RLock()   # REENTRANT: log() may be called while held


def log(m):
    with _print_lock:
        print(m, flush=True)


# ---------------------------------------------------------------- moon
def moon_illumination(date: datetime) -> float:
    """Synodic approximation of the moon's illuminated fraction (%).

    Reference new moon 2000-01-06 18:14 UTC; synodic month 29.530588853 d.
    An approximation used ONLY to label nights as dark or moonlit - it is
    not an ephemeris and nothing else depends on it.
    """
    new_moon = datetime(2000, 1, 6, 18, 14)
    days = (date - new_moon).total_seconds() / 86400.0
    phase = (days % 29.530588853) / 29.530588853
    return ((1 - math.cos(2 * math.pi * phase)) / 2) * 100.0


# ---------------------------------------------------------------- fetch
def fetch_night(layer, date_str, path, tag):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return True, "cached"
    url = (f"{GIBS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0"
           f"&LAYERS={layer}&STYLES=default&FORMAT=image/tiff"
           f"&TRANSPARENT=FALSE&TIME={date_str}"
           f"&WIDTH={WIDTH}&HEIGHT={HEIGHT}&CRS=EPSG:4326"
           f"&BBOX={BBOX_S},{BBOX_W},{BBOX_N},{BBOX_E}")
    for attempt in range(4):
        try:
            raw = urllib.request.urlopen(url, timeout=180).read()
            if raw[:4] not in (b"II*\x00", b"MM\x00*"):
                return False, "not-a-tiff"
            ds = rasterio.open(io.BytesIO(raw))
            a = ds.read(1)
            if a.max() == 0:
                return False, "blank"
            with rasterio.open(path, "w", driver="GTiff", height=HEIGHT,
                               width=WIDTH, count=1, dtype=a.dtype, crs=ds.crs,
                               transform=ds.transform, compress="deflate") as o:
                o.write(a, 1)
            return True, "ok"
        except Exception as e:
            if attempt == 3:
                return False, f"{type(e).__name__}"
            time.sleep(3 * (attempt + 1))
    return False, "exhausted"


# ---------------------------------------------------------------- masks
def build_polygon_masks():
    import geopandas as gpd

    g = gpd.read_file(PERMITTED)
    if g.crs is None:
        g = g.set_crs(4326)
    if g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)

    xres = (BBOX_E - BBOX_W) / WIDTH
    yres = (BBOX_N - BBOX_S) / HEIGHT
    transform = from_origin(BBOX_W, BBOX_N, xres, yres)

    masks = []
    for i, geom in enumerate(g.geometry):
        m = rasterize([(geom, 1)], out_shape=(HEIGHT, WIDTH), transform=transform,
                      fill=0, dtype="uint8").astype(bool)
        masks.append(m)
    union = np.zeros((HEIGHT, WIDTH), dtype=bool)
    for m in masks:
        union |= m
    log(f"permitted areas: {len(g)} polygons, {union.sum():,} px "
        f"({100 * union.mean():.2f}% of grid)")
    return g, masks, union, transform


# ---------------------------------------------------------------- geometry
def km_per_pixel(transform):
    lat0 = (BBOX_S + BBOX_N) / 2
    xres = abs(transform.a)
    yres = abs(transform.e)
    return (xres * 111.320 * math.cos(math.radians(lat0)),
            yres * 110.574)


def distance_km_grid(transform, lon, lat):
    """Approximate distance in km from every cell to (lon, lat)."""
    rows, cols = np.indices((HEIGHT, WIDTH))
    xs = transform.c + cols * transform.a + transform.a / 2
    ys = transform.f + rows * transform.e + transform.e / 2
    lat0 = (BBOX_S + BBOX_N) / 2
    dx = (xs - lon) * 111.320 * math.cos(math.radians(lat0))
    dy = (ys - lat) * 110.574
    return np.hypot(dx, dy)


# ---------------------------------------------------------------- main
def main():
    only_year = int(sys.argv[1]) if len(sys.argv) > 1 else None

    g, masks, union, transform = build_polygon_masks()
    kx, ky = km_per_pixel(transform)

    # ---- which nights to fetch -------------------------------------
    jobs = []
    for year in range(YEAR_FROM, YEAR_TO + 1):
        if only_year and year != only_year:
            continue
        for month in range(1, 13):
            for day in NIGHT_DAYS:
                try:
                    d = datetime(year, month, day)
                except ValueError:
                    continue
                ds_str = d.strftime("%Y-%m-%d")
                jobs.append((SNPP, ds_str, os.path.join(RAW, f"SNPP_{ds_str}.tif"), "SNPP"))
    log(f"{len(jobs)} nights to fetch (SNPP {YEAR_FROM}-{YEAR_TO})")

    # ---- fetch in parallel -----------------------------------------
    ok_paths = {}
    done = [0]

    def do(job):
        layer, ds_str, path, tag = job
        good, why = fetch_night(layer, ds_str, path, tag)
        with _print_lock:
            done[0] += 1
            if done[0] % 40 == 0 or not good:
                # NB: log() takes _print_lock itself, so print directly here
                print(f"  {done[0]:4d}/{len(jobs)}  {ds_str} {tag}: {why}", flush=True)
        return ds_str, path, good, why

    with ThreadPoolExecutor(8) as ex:
        for ds_str, path, good, why in ex.map(do, jobs):
            if good:
                ok_paths[ds_str] = path
    log(f"fetched {len(ok_paths)}/{len(jobs)} nights")

    if len(ok_paths) < 100:
        raise SystemExit("too few nights - refusing to continue")

    # ---- pass 1: running maximum + sums, to pick the control ------
    log("pass 1: building the running maximum for control selection")
    runmax = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    total = np.zeros((HEIGHT, WIDTH), dtype=np.float64)
    ncount = 0
    for ds_str, path in sorted(ok_paths.items()):
        with rasterio.open(path) as ds:
            a = ds.read(1)
        runmax = np.maximum(runmax, a)
        total += a
        ncount += 1
    mean_all = total / max(ncount, 1)
    log(f"  max over {ncount} nights: {runmax.max()}")

    # ---- choose the control ----------------------------------------
    urban_dist = distance_km_grid(transform, URBAN_CORE[0], URBAN_CORE[1])

    # Distance from every cell to the nearest PERMITTED cell, in km.
    # A permitted cell is one covered by any of the 16 polygons.  The
    # control must be far enough away that no deck light can leak into it.
    from scipy import ndimage
    perm_cells = union
    # distance_transform_edt returns an array in recent scipy but a
    # (distance, indices) tuple in older versions - handle both.
    # The SAMPLING must be in kilometres, so the result is in km.
    lat_mid = (BBOX_S + BBOX_N) / 2
    km_per_deg_lon = 111.320 * math.cos(math.radians(lat_mid))
    km_per_deg_lat = 110.574
    edt = ndimage.distance_transform_edt(
        ~perm_cells,
        sampling=(abs(transform.e) * km_per_deg_lat,
                  abs(transform.a) * km_per_deg_lon))
    nearest = edt[0] if isinstance(edt, tuple) else edt
    assert nearest.shape == (HEIGHT, WIDTH), f"EDT shape {nearest.shape}"
    per_dist_km = nearest
    log(f"  permitted cells: {perm_cells.sum():,}; "
        f"distance-to-permitted max {per_dist_km.max():.1f} km")

    candidate = ((runmax <= CONTROL_MAX_VALUE) & (~union)
                 & (urban_dist >= MIN_URBAN_DIST_KM)
                 & (per_dist_km >= CONTROL_MIN_DIST_KM))
    if candidate.sum() < 500:
        raise SystemExit(f"control candidate cells too few ({candidate.sum()})")
    log(f"control candidates: {candidate.sum():,} cells "
        f"(max<={CONTROL_MAX_VALUE}, urban dist >{MIN_URBAN_DIST_KM} km, outside permitted)")

    # restrict the control to open sea: cells whose max is low AND whose
    # neighbourhood mean is low (rural land would be low too, but it is
    # excluded by the urban-distance rule only for the metro core, so we
    # additionally require the local 5x5 mean to be very low -> open water)
    from numpy.lib.stride_tricks import sliding_window_view
    win = sliding_window_view(mean_all, (5, 5))
    local_mean = win.mean(axis=(-1, -2))
    local_mean = np.pad(local_mean, 2, mode="edge")
    open_sea = local_mean <= 25
    candidate &= open_sea
    log(f"  after open-water filter: {candidate.sum():,} cells")
    if candidate.sum() < 300:
        raise SystemExit("not enough open-water control cells")

    control = candidate
    np.save(os.path.join(OUT, "control_mask.npy"), control)

    # ---- pass 2: per-night sampling --------------------------------
    log("pass 2: sampling")
    rows = []
    for ds_str, path in sorted(ok_paths.items()):
        d = datetime.strptime(ds_str, "%Y-%m-%d")
        with rasterio.open(path) as ds:
            arr = ds.read(1).astype(np.float32)
            bounds = ds.bounds
        # float tolerance: GIBS returns 22.149999999999995 for 22.15
        if (abs(bounds.left - BBOX_W) > 1e-6 or abs(bounds.bottom - BBOX_S) > 1e-6
                or abs(bounds.right - BBOX_E) > 1e-6 or abs(bounds.top - BBOX_N) > 1e-6):
            log(f"  {ds_str}: bbox mismatch {bounds} - SKIP")
            continue

        # georeference check: urban vs open sea contrast
        def bm(lon, lat, half=0.03):
            c = int((lon - bounds.left) / (bounds.right - bounds.left) * WIDTH)
            r = int((bounds.top - lat) / (bounds.top - bounds.bottom) * HEIGHT)
            c0, c1 = max(c - 6, 0), min(c + 6, WIDTH)
            r0, r1 = max(r - 6, 0), min(r + 6, HEIGHT)
            if c1 <= c0 or r1 <= r0:
                return None
            return float(arr[r0:r1, c0:c1].mean())

        urban = bm(URBAN_CORE[0], URBAN_CORE[1])
        sea = bm(113.76, 22.19)
        if urban is None or sea is None or sea <= 0:
            continue
        contrast = urban / sea
        if contrast < 4:
            continue

        per_means = [float(arr[m].mean()) for m in masks if m.sum() > 0]
        per_max = [float(arr[m].max()) for m in masks if m.sum() > 0]
        ctl_mean = float(arr[control].mean())
        ctl_max = float(arr[control].max())
        pol_mean = float(np.mean(per_means))
        pol_max = float(np.max(per_max))

        rows.append({
            "date": ds_str,
            "year": d.year, "month": d.month, "day": d.day,
            "moon_pct": round(moon_illumination(d), 1),
            "contrast": round(contrast, 2),
            "control_mean": round(ctl_mean, 3),
            "control_max": round(ctl_max, 1),
            "permitted_mean": round(pol_mean, 3),
            "permitted_max": round(pol_max, 1),
            "excess": round(pol_mean - ctl_mean, 3),
            "per_polygon": [round(v, 2) for v in per_means],
        })

    log(f"kept {len(rows)} nights")
    if len(rows) < 200:
        raise SystemExit("too few clean nights")

    # ---- control stability gate ------------------------------------
    cm = np.array([r["control_mean"] for r in rows])
    log(f"control stability: mean {cm.mean():.2f} sd {cm.std():.2f} "
        f"p95 {np.percentile(cm, 95):.2f} max {cm.max():.2f}")
    if cm.max() > 8 * max(cm.mean(), 0.5):
        raise SystemExit("control is contaminated - refusing to publish")

    with open(os.path.join(OUT, "seasonal_nights.json"), "w") as f:
        json.dump(rows, f, indent=1)

    # ---- monthly climatology ---------------------------------------
    import statistics
    by_month = {m: [] for m in range(1, 13)}
    for r in rows:
        by_month[r["month"]].append(r)

    print("\nMONTH  n   permitted  control   excess   ratio  morat")
    summary = []
    for m in range(1, 13):
        rr = by_month[m]
        if not rr:
            continue
        pm = statistics.mean(x["permitted_mean"] for x in rr)
        cmn = statistics.mean(x["control_mean"] for x in rr)
        em = statistics.mean(x["excess"] for x in rr)
        ratios = [x["permitted_mean"] / x["control_mean"] for x in rr
                  if x["control_mean"] > 0]
        rm = statistics.mean(ratios) if ratios else None
        mor = "MORATORIUM" if m in MORATORIUM_MONTHS else ""
        print(f"  {m:2d}  {len(rr):4d}   {pm:8.2f}  {cmn:8.2f}  {em:+7.2f}  "
              f"{(rm or 0):6.2f}  {mor}")
        summary.append({
            "month": m, "n": len(rr),
            "permitted_mean": round(pm, 3), "control_mean": round(cmn, 3),
            "excess_mean": round(em, 3),
            "ratio_mean": round(rm, 3) if rm else None,
            "in_moratorium": m in MORATORIUM_MONTHS,
        })

    with open(os.path.join(OUT, "seasonal_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)

    # ---- NOTICE -----------------------------------------------------
    # The numbers printed below are the RAW brightness difference between
    # the permitted polygons and the control water, over ALL cells in the
    # polygons - including the land they overlap. They are NOT the result.
    #
    # This was the first version of the study, and it was WITHDRAWN on
    # 2026-11-09. It measured the city glow on the shore, not fishing
    # vessels: the polygons overlap the coast, so "permitted" was mostly
    # measuring Hong Kong's own lights, and the apparent monthly curve was
    # the seasonal drift of that glow.
    #
    # The published result comes from `definitive_analysis.py`, which
    # restricts to DEEP WATER only (>3 km from land), excludes the fixed
    # bright structures (the LNG terminal and the Ma Liu Shui power cable),
    # and counts only transient single-night cells. Run that script, not
    # this table.
    print("\n" + "!" * 74)
    print("! SUPERSEDED OUTPUT - the table below is NOT the published result.")
    print("! These are raw brightness differences over ALL cells in the permitted")
    print("! polygons, including the land they overlap, so they measure the city")
    print("! glow on the shore rather than fishing vessels. The published result")
    print("! is produced by definitive_analysis.py. See the note's section 8.")
    print("!" * 74)

    # ---- the headline test (SUPERSEDED - see the notice above) -------
    mor = [r["excess"] for r in rows if r["month"] in MORATORIUM_MONTHS]
    non = [r["excess"] for r in rows if r["month"] not in MORATORIUM_MONTHS]
    print(f"\nMORATORIUM (May-Aug) excess: mean {statistics.mean(mor):+.3f} "
          f"n={len(mor)}")
    print(f"NON-MORATORIUM      excess: mean {statistics.mean(non):+.3f} "
          f"n={len(non)}")
    diff = statistics.mean(mor) - statistics.mean(non)
    print(f"DIFFERENCE: {diff:+.3f} DN units")

    # also the ratio version
    mor_r = [r["permitted_mean"] / r["control_mean"] for r in rows
             if r["month"] in MORATORIUM_MONTHS and r["control_mean"] > 0]
    non_r = [r["permitted_mean"] / r["control_mean"] for r in rows
             if r["month"] not in MORATORIUM_MONTHS and r["control_mean"] > 0]
    print(f"ratio  mor {statistics.mean(mor_r):.2f}x  non {statistics.mean(non_r):.2f}x")
    print("\nOK (fetch complete; the analysis above is superseded)")


if __name__ == "__main__":
    main()
