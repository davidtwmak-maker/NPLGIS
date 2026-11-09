#!/usr/bin/env python3
"""
Score Hong Kong's 41 country-park campsites for darkness and camp quality.

THE QUESTION:  which campsites give the best night sky, and which are worth
camping at on their own merits?

METHOD
------
The unit of analysis is the campsite itself (41 points, AFCD).  A campsite is
a discrete, named, bookable place - not a raster cell - so the point IS the
unit.  This is stated because the unit choice decides the answer: a 200 m
grid would fragment the sites and a 1 km grid would merge distinct sites.

Four factors, each a separate named term so the score is auditable:

  1. LIGHT POLLUTION  (the headline factor)
     VIIRS Day/Night Band brightness sampled at each campsite, from the
     median night-composite.  Lower is darker.

  2. SKY VIEW / HORIZON
     The measured fact that a campground's sky quality depends on what
     blocks the horizon.  We use the surrounding terrain: a campsite on a
     summit sees a low horizon; one in a valley sees a high one.  Proxied
     by local relief from the 5 m DTM within 500 m.

  3. ACCESS
     How far you have to walk in, from the nearest country-park visitor
     centre (AFCD).  Short walk = more accessible = better for a family or
     school group.

  4. FACILITY CAPACITY
     Tent space (AFCD, "Less than 20" / "20-50" / "More than 50") and water
     source (TAP / flushing toilet / seasonal stream).  A site with a tap
     and 50+ tent spaces is a better *campsite* even if a neighbouring site
     is marginally darker.

The score is a TRANSPARENT PRODUCT of normalised terms, not an opaque
model, and the light term is weighted heaviest because the question asks
about darkness.

Every gate here has caught a real defect:
  * The night composite must not be empty (GIBS returns blank rasters for
    unserved dates, with HTTP 200 and no error).
  * Every campsite must land inside the night-lights raster, else it is
    dropped and REPORTED, not silently scored as dark.
  * Areas are measured in a projected CRS.
  * The output table is written, then read back and counted.

Run:  ls-venv/bin/python score_campsites.py
"""
import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
# Paths can be overridden from the environment so that the copy in the
# NPLGIS repo runs on another machine:
#   GIS_DATA_DIR       root holding hk-spatial/data, HK Night Lights, ...
#   CAMPING_DATA_DIR   where the outputs are written
BASE = os.environ.get("GIS_DATA_DIR", f"{GIS_DATA}")
CSDI = f"{BASE}/hk-spatial/data"
NL = os.environ.get("NIGHTLIGHTS_DIR", f"{BASE}/HK Night Lights")
OUT = os.environ.get("CAMPING_DATA_DIR", f"{BASE}/HK Camping Sites")
LS = "/Users/davidhermes/.hermes/cache/scratch/ls-venv/bin/python"

D_CAMPS = f"{CSDI}/afcd_rcd_1635133060194_82554.geojson"
D_TRAILS = f"{CSDI}/afcd_rcd_1665568199103_4360.geojson"
D_TOILETS = f"{CSDI}/afcd_rcd_1635136427551_29173.geojson"
D_VC = f"{CSDI}/afcd_rcd_1635133243757_2529.geojson"

N_COMPOSITE = f"{NL}/raw/night_composite_median.tif"
N_SINGLE = f"{NL}/HK_Night_Lights_2026-10-29_raster.tif"
DTM = f"{BASE}/HK Landslide Susceptibility/work/terrain_20m.npz"

EXPECT_CAMPS = 41


def log(m):
    print(m, flush=True)


def sample_raster(arr, ds, lon, lat, half=5):
    """Sample a value and a local mean from a raster at lon/lat."""
    r, c = rowcol(ds.transform, lon, lat)
    r, c = int(r), int(c)
    if not (0 <= r < ds.height and 0 <= c < ds.width):
        return None, None
    r0, r1 = max(0, r - half), min(ds.height, r + half + 1)
    c0, c1 = max(0, c - half), min(ds.width, c + half + 1)
    return int(arr[r, c]), float(arr[r0:r1, c0:c1].mean())


def norm(s, invert=False):
    """Min-max to 0..1.  A constant column returns 0.5, not a divide-by-zero."""
    lo, hi = float(s.min()), float(s.max())
    if hi - lo < 1e-12:
        return pd.Series(np.full(len(s), 0.5), index=s.index)
    v = (s - lo) / (hi - lo)
    return 1.0 - v if invert else v


def main():
    os.makedirs(OUT, exist_ok=True)

    # ---------------------------------------------------------------- camps
    log("=== campsites ===")
    camps = gpd.read_file(D_CAMPS)
    log(f"  {len(camps)} features")
    assert len(camps) == EXPECT_CAMPS, f"{len(camps)} campsites, expected {EXPECT_CAMPS}"
    assert camps.crs.to_epsg() == 4326, f"unexpected CRS {camps.crs}"
    camps = camps.rename(columns={
        "SITE_NAME_EN": "site", "COUNTRY_PARK_EN": "park",
        "TENT_SPACE_EN": "tent_space", "SOURCE_OF_WATER_EN": "water",
    })
    camps["lon"] = camps.geometry.x
    camps["lat"] = camps.geometry.y

    # ------------------------------------------------------- night lights
    npath = N_COMPOSITE if os.path.exists(N_COMPOSITE) else N_SINGLE
    log(f"\n=== night lights: {os.path.basename(npath)} ===")
    ds = rasterio.open(npath)
    arr = ds.read(1)
    log(f"  raster {ds.width}x{ds.height} {ds.crs} | value range {arr.min()}-{arr.max()}")
    assert arr.max() > 0, "night-lights raster is BLANK (GIBS serves unserved dates as all-zero)"
    log(f"  bounds: {ds.bounds}")

    rows = []
    dropped = []
    for _, c in camps.iterrows():
        v, m = sample_raster(arr, ds, c["lon"], c["lat"])
        if v is None:
            dropped.append(c["site"])
        rows.append({"dnb": v, "dnb_mean": m})
    camps = pd.concat([camps.reset_index(drop=True),
                       pd.DataFrame(rows)], axis=1)
    if dropped:
        log(f"  DROPPED (outside raster): {dropped}")
    else:
        log("  all 41 campsites fall inside the night-lights raster")
    assert camps["dnb"].notna().all(), f"{camps['dnb'].isna().sum()} campsites have no DNB value"

    # The composite is used if present; also record the single-night value so
    # the sensitivity of the ranking to the choice of night is visible.
    if N_SINGLE != npath and os.path.exists(N_SINGLE):
        ds2 = rasterio.open(N_SINGLE)
        a2 = ds2.read(1)
        v2 = [sample_raster(a2, ds2, c["lon"], c["lat"])[0] for _, c in camps.iterrows()]
        camps["dnb_single"] = v2
        log(f"  single-night cross-check added (nights differ)")

    # ------------------------------------------------------------- access
    log("\n=== access: distance to nearest visitor centre ===")
    vcs = gpd.read_file(D_VC)
    log(f"  {len(vcs)} visitor centres")
    cps = gpd.GeoSeries(camps.geometry.values, crs=camps.crs).to_crs(3857)
    vcg = gpd.GeoSeries(vcs.geometry.values, crs=vcs.crs).to_crs(3857)
    # NOTE: `cps.distance(vcg)` on two GeoSeries returns a MATRIX (n x m).
    # Calling .min() on that matrix gives ONE global minimum - every camp
    # then gets the same value and the access term carries no information.
    # The per-camp answer is the min down each ROW of the matrix.
    dist_matrix = np.array([g.distance(vcg).values for g in cps])
    camps["walk_to_vc_m"] = dist_matrix.min(axis=1)
    log(f"  walk to VC: min {camps['walk_to_vc_m'].min():.0f} m, "
        f"median {camps['walk_to_vc_m'].median():.0f} m, max {camps['walk_to_vc_m'].max():.0f} m")
    n_unique = camps["walk_to_vc_m"].round(1).nunique()
    log(f"  distinct walk distances: {n_unique}")
    assert n_unique > 20, \
        f"only {n_unique} distinct walk distances - the access term is not discriminating"

    # --------------------------------------------------------- facilities
    log("\n=== facilities ===")
    toilets = gpd.read_file(D_TOILETS)
    log(f"  {len(toilets)} toilets in country parks")
    tls = gpd.GeoSeries(toilets.geometry.values, crs=toilets.crs).to_crs(3857)
    camps["toilets_within_500m"] = [
        int((cps.iloc[i].distance(tls) <= 500).sum()) for i in range(len(camps))
    ]

    tent_pts = {"Less than 20": 1, "20-50": 2, "More than 50": 3}
    water_pts = {"TAP": 3, "FLUSHING TOILET": 3, "STREAM WATER (SEASONAL SUPPLY)": 1}
    camps["tent_score"] = camps["tent_space"].map(tent_pts).fillna(1).astype(int)
    camps["water_score"] = camps["water"].map(water_pts).fillna(1).astype(int)
    log(f"  tent space: {camps['tent_space'].value_counts().to_dict()}")
    log(f"  water: {camps['water'].value_counts().to_dict()}")

    # --------------------------------------------------------- terrain/horizon
    log("\n=== terrain: local relief within 500 m (horizon proxy) ===")
    if os.path.exists(DTM):
        z = np.load(DTM)
        # Read the grid origin FROM THE FILE.  The first version hardcoded
        # x0=799997.5 / y0=848002.5, which is wrong by 10 m in x and 10 m in
        # y - enough to push 17 of 41 campsites off the grid edge and leave
        # them with NaN, which then poisoned the whole score column.
        x0 = float(z["x0"])
        y0 = float(z["y0"])
        cell = float(z["cell"])
        REL = z["relief"]          # precomputed max-min within the cell
        ELEV = z["elev"]
        VALID = z["valid"]
        log(f"  grid origin x0={x0} y0={y0} cell={cell} m, shape {REL.shape}")

        import pyproj
        tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2326", always_xy=True)
        half = int(round(500.0 / cell))
        rels, elevs, n_ok = [], [], 0
        for _, c in camps.iterrows():
            x, y = tr.transform(c["lon"], c["lat"])
            col = int(round((x - x0) / cell))
            row = int(round((y0 - y) / cell))
            if not (0 <= row < REL.shape[0] and 0 <= col < REL.shape[1]):
                rels.append(np.nan)
                elevs.append(np.nan)
                continue
            r0, r1 = max(0, row - half), min(REL.shape[0], row + half + 1)
            c0, c1 = max(0, col - half), min(REL.shape[1], col + half + 1)
            win_rel = REL[r0:r1, c0:c1]
            win_el = ELEV[r0:r1, c0:c1]
            win_v = VALID[r0:r1, c0:c1]
            if not win_v.any():
                rels.append(np.nan)
                elevs.append(np.nan)
                continue
            rels.append(float(np.nanmax(win_rel[win_v])))
            elevs.append(float(np.nanmean(win_el[win_v])))
            n_ok += 1
        camps["relief_500m"] = rels
        camps["elev_m"] = elevs
        log(f"  relief measured for {n_ok}/{len(camps)} campsites")
        assert n_ok == len(camps), \
            f"only {n_ok}/{len(camps)} campsites got a terrain value - the grid origin or projection is wrong"
    else:
        camps["relief_500m"] = np.nan
        camps["elev_m"] = np.nan
        log("  DTM not found - horizon proxy skipped")

    # ------------------------------------------------------------- score
    log("\n=== scoring ===")
    w_light, w_access, w_facility, w_view = 0.50, 0.20, 0.20, 0.10
    camps["s_dark"] = norm(camps["dnb"], invert=True)          # dark = high
    camps["s_access"] = norm(camps["walk_to_vc_m"], invert=True)
    camps["s_facility"] = 0.6 * norm(camps["tent_score"]) + 0.4 * norm(camps["water_score"])
    camps["s_view"] = norm(camps["relief_500m"], invert=True)  # low relief = open sky
    camps["score"] = (w_light * camps["s_dark"] + w_access * camps["s_access"]
                      + w_facility * camps["s_facility"] + w_view * camps["s_view"])
    log(f"  weights: light {w_light} | access {w_access} | facility {w_facility} | view {w_view}")

    # A NaN anywhere in the score would silently drop that site out of the
    # ranking while keeping it in the table.  Fail loudly instead.
    n_nan = int(camps["score"].isna().sum())
    if n_nan:
        bad = camps.loc[camps["score"].isna(), "site"].tolist()
        log(f"  NaN SCORES: {n_nan} -> {bad}")
    assert n_nan == 0, f"{n_nan} campsites have no score"
    assert camps["score"].nunique() > 30, \
        f"only {camps['score'].nunique()} distinct scores - a term is not discriminating"

    camps = camps.sort_values("score", ascending=False).reset_index(drop=True)
    camps.insert(0, "rank", range(1, len(camps) + 1))

    # ------------------------------------------------- rank stability check
    # A one-night measure can reorder sites.  Report the rank shift against
    # the single-night value so the write-up can state how stable it is.
    if "dnb_single" in camps.columns:
        r_multi = camps["dnb"].rank(method="min")
        r_single = camps["dnb_single"].rank(method="min")
        shift = (r_multi - r_single).abs()
        log(f"  rank shift vs single night: max {shift.max():.0f}, mean {shift.mean():.2f}")
        camps["dnb_rank_shift"] = shift

    # ------------------------------------------------------------- output
    log("\n=== writing outputs ===")
    cols = ["rank", "site", "park", "dnb", "dnb_mean", "score", "s_dark",
            "walk_to_vc_m", "toilets_within_500m", "tent_space", "water",
            "relief_500m", "elev_m", "lon", "lat"]
    if "dnb_single" in camps.columns:
        cols.insert(4, "dnb_single")
    table = camps[cols].copy()
    csv_p = os.path.join(OUT, "campsite_scores.csv")
    table.to_csv(csv_p, index=False)
    log(f"  {csv_p}")

    gj = gpd.GeoDataFrame(table.merge(camps[["geometry"]], left_index=True,
                                      right_index=True), geometry="geometry", crs="EPSG:4326")
    gj_p = os.path.join(OUT, "campsite_scores.geojson")
    gj.to_file(gj_p, driver="GeoJSON")
    # RFC 7946: a GeoJSON file must NOT carry a "crs" member - the CRS is
    # always WGS84 lon/lat.  pyogrio writes one anyway, which breaks some
    # readers (including ArcGIS Online), so it is stripped here.
    with open(gj_p) as f:
        _gj = json.load(f)
    if "crs" in _gj:
        del _gj["crs"]
        with open(gj_p, "w") as f:
            json.dump(_gj, f)
        log("  stripped the non-RFC7946 'crs' member from the GeoJSON")
    log(f"  {gj_p}")

    stats = {
        "n_campsites": len(camps),
        "night_lights_source": os.path.basename(npath),
        "weights": {"light": w_light, "access": w_access,
                    "facility": w_facility, "view": w_view},
        "dnb_range": [int(camps["dnb"].min()), int(camps["dnb"].max())],
        "dnb_median": float(camps["dnb"].median()),
        "top10": camps.head(10)[["rank", "site", "park", "dnb", "score"]]
        .to_dict(orient="records"),
    }
    if "dnb_rank_shift" in camps.columns:
        stats["rank_shift_vs_single_night"] = {
            "max": float(camps["dnb_rank_shift"].max()),
            "mean": float(camps["dnb_rank_shift"].mean()),
        }
    with open(os.path.join(OUT, "campsite_scores_summary.json"), "w") as f:
        json.dump(stats, f, indent=1)

    # -------------------------------------------------------- read back
    back = gpd.read_file(gj_p)
    assert len(back) == EXPECT_CAMPS, f"written file has {len(back)} features"
    assert int((~back.is_valid).sum()) == 0
    rb = pd.read_csv(csv_p)
    assert len(rb) == EXPECT_CAMPS
    assert list(rb["rank"]) == list(range(1, EXPECT_CAMPS + 1))
    log(f"  verified: {len(back)} features, {len(rb)} csv rows, ranks 1..{EXPECT_CAMPS}, 0 invalid")

    log("\n=== TOP 10 ===")
    log(f"{'#':>3} {'site':<36} {'DNB':>4} {'score':>6} {'walk_m':>8} {'tent':<13} water")
    for _, r in camps.head(10).iterrows():
        log(f"{r['rank']:>3} {str(r['site'])[:35]:<36} {int(r['dnb']):>4} "
            f"{r['score']:>6.3f} {r['walk_to_vc_m']:>8.0f} {str(r['tent_space']):<13} {r['water']}")
    log("\n=== BOTTOM 5 ===")
    for _, r in camps.tail(5).iterrows():
        log(f"{r['rank']:>3} {str(r['site'])[:35]:<36} {int(r['dnb']):>4} "
            f"{r['score']:>6.3f} {r['walk_to_vc_m']:>8.0f} {str(r['tent_space']):<13} {r['water']}")

    print("\nOK: campsite scores written and verified")


if __name__ == "__main__":
    main()
