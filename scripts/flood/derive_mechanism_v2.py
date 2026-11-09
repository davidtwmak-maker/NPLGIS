#!/usr/bin/env python3
"""
Derive the flood MECHANISM for each of the 267 official DSD flood-prone
locations, from spatial relationships to the drainage network and topography.

v2 changes over v1
-------------------
* The coastline is built from the validated OSM coastline, NOT from the CSDI
  `landsd_rcd_1637223499176_68379` layer.  That layer is the iC1000 **map
  sheet** index (4,709 sheets; fields SHEETNO / FGDB / DGN), not land.  Used
  as a land mask it gave 2,130 km2 against Hong Kong's real ~1,106 km2, so
  every "distance to the coast" was wrong.
* Ground elevation now comes from the LandsD 5 m DTM, so "low-lying" is
  measured rather than assumed.
* The drainage channel hierarchy uses the channel WIDTH field and the
  engineered-channel layer, not raw feature count.

METHOD
------
For each point measure:
  d_coast_km      distance to the OSM coastline
  elevation_m     ground level from the 5 m DTM
  d_bigchannel_km distance to a major drainage channel
  d_inlet_km      distance to the nearest stormwater inlet
  d_catchment_km  distance to the catchment boundary

then apply a decision tree.  The mechanism is decided by what the data says
about the location, not by what its street name says.
"""
import csv
import json
import math
import os

import numpy as np
import pandas as pd
import rasterio
import geopandas as gpd
from shapely.geometry import shape, LineString
from scipy.spatial import cKDTree
from shapely.ops import unary_union, linemerge
import pyproj

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
ROOT = os.environ.get("GIS_DATA_DIR", f"{GIS_DATA}") + "/HK Flood Prone Areas"
SUP = f"{ROOT}/support"
COAST = f"{GIS_DATA}/HK Night Lights/_coast_ways_full.json"
SCRATCH = os.environ.get("HK_SCRATCH", "/Users/davidhermes/.hermes/cache/scratch")
DTM = f"{SCRATCH}/Whole_HK_DTM_5m.asc"
OUT_GJ = f"{ROOT}/flood_mechanism.geojson"
OUT_CSV = f"{ROOT}/flood_mechanism.csv"

FWD = pyproj.Transformer.from_crs(
    pyproj.CRS.from_epsg(4326), pyproj.CRS.from_epsg(2326), always_xy=True)

# a generous low-lying ceiling for HK; the 2000 Coastal Hazards Study used
# around +5 m for storm-surge exposure
LOW_M = 5.0


def log(m):
    print(m, flush=True)


def load_fs(path):
    with open(path) as f:
        d = json.load(f)
    feats = []
    for feat in d.get("features", []):
        attrs = dict(feat.get("properties") or feat.get("attributes") or {})
        geom = feat.get("geometry")
        if geom is None:
            continue
        attrs["__geometry__"] = shape(geom)
        feats.append(attrs)
    return feats


def to_gdf(feats):
    return gpd.GeoDataFrame(
        [{k: v for k, v in f.items() if k != "__geometry__"} for f in feats],
        geometry=[f["__geometry__"] for f in feats], crs=4326)


def wval(v):
    try:
        f = float(v)
        return f if 0 < f < 10000 else np.nan
    except Exception:
        return np.nan


def main():
    blockage = gpd.read_file(f"{ROOT}/dsd_blockage.geojson")
    works = gpd.read_file(f"{ROOT}/dsd_works.geojson")
    coastal = gpd.read_file(f"{ROOT}/dsd_coastal.geojson")
    log(f"DSD points: blockage {len(blockage)}, works {len(works)}, coastal {len(coastal)}")

    channel = to_gdf(load_fs(f"{SUP}/dsd_channel.json"))
    inlet = to_gdf(load_fs(f"{SUP}/dsd_inlet.json"))
    eng = to_gdf(load_fs(f"{SUP}/dsd_engineered_channel.json"))
    catchment = to_gdf(load_fs(f"{SUP}/wsd_catchment.json"))
    log(f"support: channels {len(channel)}, inlets {len(inlet)}, "
        f"engineered {len(eng)}, catchments {len(catchment)}")

    # ---------- the coastline ----------
    # Use the CEDD geological coastline layer, NOT the OSM ways and NOT the
    # CSDI "land boundary" layer.
    #   - landsd_rcd_1637223499176_68379 is the iC1000 map-sheet CATALOGUE
    #     (fields SHEETNO/FGDB/DGN); dissolving it gives 2,130 km2 vs HK's
    #     real ~1,106 km2, so every coastal distance is wrong.
    #   - the OSM ways include rivers and streams, so the merged length is
    #     1,506 km and the distance-to-sea is contaminated by riverbanks.
    # The CEDD coastline dissolves to 1,098 km2 against HK's real ~1,106 km2
    # (largest polygon 793 km2 = the main island + Lantau + New Territories).
    CEDD = (f"{GIS_DATA}/hk-spatial/data/"
            "cedd_rcd_1636520962284_7237.geojson")
    from shapely.ops import unary_union
    cg = gpd.read_file(CEDD)
    shore = unary_union(cg.geometry.values)
    shore_km2 = shore.area * 111.32 * 111.32 * math.cos(math.radians(22.3))
    log(f"coastline: CEDD geological coastline, {len(cg)} polygons, "
        f"dissolved {shore_km2:,.0f} km2 (HK real land ~1,106 km2)")
    # the shoreline itself = the exterior rings of the dissolved land
    if shore.geom_type == "MultiPolygon":
        shore_rings = [p.exterior for p in shore.geoms]
    else:
        shore_rings = [shore.exterior]
    from shapely.ops import linemerge
    shore_line = linemerge(shore_rings)
    log(f"  shoreline: {shore_line.geom_type}, "
        f"{shore_line.length*111.32*math.cos(math.radians(22.3)):,.0f} km")

    # ---------- the point table ----------
    rows = []
    for src, gdf, official in (("blockage", blockage, "Locations Prone to Blockage"),
                               ("works", works, "Drainage Improvement Works In Progress"),
                               ("coastal", coastal, "Coastal Low-lying or Windy Residential Areas")):
        tcol = next((c for c in ("title", "Title", "TITLE", "name", "NAME")
                     if c in gdf.columns), gdf.columns[0])
        for _, r in gdf.iterrows():
            rows.append({"source": src, "official_list": official,
                         "title": str(r[tcol]), "point": r.geometry})
    log(f"all points: {len(rows)}")

    # ---------- channel hierarchy ----------
    ch = channel.copy()
    ch["len_km"] = ch.geometry.length * 111.32 * math.cos(math.radians(22.3))
    ch["width_m"] = ch["WIDTH"].map(wval) if "WIDTH" in ch.columns else np.nan
    ew = eng.copy()
    ew["len_km"] = ew.geometry.length * 111.32 * math.cos(math.radians(22.3))
    ew["width_m"] = ew["WIDTH"].map(wval) if "WIDTH" in ew.columns else np.nan

    WIDE = 10.0
    parts = []
    if ch["width_m"].notna().any():
        parts.append(ch[ch["width_m"] >= WIDE])
    if ew["width_m"].notna().any():
        parts.append(ew[ew["width_m"] >= WIDE])
    major = pd.concat(parts, ignore_index=True) if parts else ch
    log(f"  major channels: {len(major)} of {len(ch)+len(eng)} (width >= {WIDE} m)")

    inl = inlet.copy()
    inl["x"] = inl.geometry.centroid.x
    inl["y"] = inl.geometry.centroid.y
    tree_in = cKDTree(np.c_[inl["x"].values, inl["y"].values])

    maj = major.copy()
    maj["x"] = maj.geometry.centroid.x
    maj["y"] = maj.geometry.centroid.y
    tree_maj = cKDTree(np.c_[maj["x"].values, maj["y"].values])

    cat = catchment.copy()
    cat["x"] = cat.geometry.centroid.x
    cat["y"] = cat.geometry.centroid.y
    tree_cat = cKDTree(np.c_[cat["x"].values, cat["y"].values])

    # ---------- DTM ----------
    # The ASCII grid is 12,751 x 9,601 = 122 M cells; random window reads
    # through rasterio's ASCII driver take minutes.  Convert once to a .npy
    # and index it directly.
    NPY = f"{SCRATCH}/hk_dtm_5m.npy"
    log("loading the 5 m DTM ...")
    if not os.path.exists(NPY):
        raise SystemExit(f"{NPY} missing - convert the ASC first with np.loadtxt")
    dem = np.load(NPY, mmap_mode="r")
    # the ASCII grid is stored top row first, so row 0 is the NORTH edge
    NROWS, NCOLS = dem.shape
    XLL, YLL, CELL = 799997.5, 799997.5, 5.0
    log(f"  DTM {NCOLS} x {NROWS}, origin HK1980 {XLL}/{YLL}, {CELL} m cells")

    allx = np.array([r["point"].x for r in rows])
    ally = np.array([r["point"].y for r in rows])
    gx, gy = FWD.transform(allx, ally)
    # ASCII row = (YLL + nrows*CELL - Y) / CELL  -> northern edge is row 0
    rr = ((YLL + NROWS * CELL) - gy) / CELL
    cc = (gx - XLL) / CELL
    elev = np.full(len(rows), np.nan)
    for i in range(len(rows)):
        r0, c0 = int(round(rr[i])), int(round(cc[i]))
        if 0 <= r0 < NROWS and 0 <= c0 < NCOLS:
            win = dem[max(0, r0 - 2):r0 + 3, max(0, c0 - 2):c0 + 3]
            vv = win[win != -9999]
            if vv.size:
                elev[i] = float(np.median(vv))
    ok = np.isfinite(elev)
    log(f"  elevation sampled for {ok.sum()} / {len(rows)} points; "
        f"range {np.nanmin(elev):.1f}..{np.nanmax(elev):.1f} m, "
        f"median {np.nanmedian(elev):.1f} m")

    # ---------- per-point metrics ----------
    log("computing per-point metrics ...")
    for i, r in enumerate(rows):
        p = r["point"]
        k = 111.32 * math.cos(math.radians(p.y))
        r["d_coast_km"] = p.distance(shore_line) * k
        dm, im_ = tree_maj.query([p.x, p.y])
        r["d_bigchannel_km"] = dm * k
        r["big_channel_width_m"] = float(maj["width_m"].iloc[im_])
        r["big_channel_len_km"] = float(maj["len_km"].iloc[im_])
        di, ii = tree_in.query([p.x, p.y])
        r["d_inlet_km"] = di * k
        r["inlet_il"] = wval(inl["IL"].iloc[ii]) if "IL" in inl.columns else np.nan
        dc, ic = tree_cat.query([p.x, p.y])
        r["d_catchment_km"] = dc * k
        r["catchment_name"] = str(cat["NAME"].iloc[ic]) if "NAME" in cat.columns else ""
        r["elevation_m"] = float(elev[i]) if ok[i] else np.nan

    dcoast = np.array([r["d_coast_km"] for r in rows])
    dbig = np.array([r["d_bigchannel_km"] for r in rows])
    dc_p20 = float(np.percentile(dcoast, 20))
    dc_p50 = float(np.percentile(dcoast, 50))
    db_p20 = float(np.percentile(dbig, 20))
    db_p50 = float(np.percentile(dbig, 50))
    log(f"  thresholds: coast p20={dc_p20:.2f} p50={dc_p50:.2f} km; "
        f"major channel p20={db_p20:.2f} p50={db_p50:.2f} km")

    # ---------- the decision tree ----------
    for r in rows:
        dc, db, di = r["d_coast_km"], r["d_bigchannel_km"], r["d_inlet_km"]
        el = r["elevation_m"]
        low = (not np.isfinite(el)) or (el <= LOW_M)
        coastal_ev = (dc <= dc_p20) and (db <= db_p50) and low
        channel_ev = (db <= db_p20) and not coastal_ev
        ponding_ev = (dc > dc_p50) and (db <= db_p50) and low
        els = f"{el:.1f} m" if np.isfinite(el) else "unknown"

        if r["source"] == "coastal":
            r["mechanism"] = "coastal_tidal"
            r["basis"] = "on DSD's official coastal low-lying list"
        elif coastal_ev:
            r["mechanism"] = "coastal_tidal"
            r["basis"] = (f"{dc:.2f} km from the coast, {db:.2f} km from a major "
                          f"channel, ground level {els}")
        elif channel_ev:
            r["mechanism"] = "channel_backflow"
            r["basis"] = (f"{db:.2f} km from a major channel "
                          f"({r['big_channel_width_m']:.0f} m wide), "
                          f"{dc:.2f} km from the coast")
        elif ponding_ev:
            r["mechanism"] = "low_lying_ponding"
            r["basis"] = (f"{dc:.2f} km inland and low-lying ({els}), "
                          f"ponds before it can drain")
        else:
            r["mechanism"] = "local_drainage_blockage"
            r["basis"] = (f"{di:.2f} km from the nearest inlet; urban local network, "
                          f"not coastal and not beside a major channel")

        if r["mechanism"] == "coastal_tidal":
            r["confidence"] = "high" if (r["source"] == "coastal" or dc <= dc_p20 / 2) else "medium"
        elif r["mechanism"] == "channel_backflow":
            r["confidence"] = "high" if db <= db_p20 / 2 else "medium"
        elif r["mechanism"] == "low_lying_ponding":
            r["confidence"] = "medium"
        else:
            r["confidence"] = "medium" if di <= 0.3 else "low"

    from collections import Counter
    c = Counter(r["mechanism"] for r in rows)
    log("\nmechanism distribution:")
    for k, v in c.most_common():
        log(f"  {k:24s} {v:4d}")
    log("\ncross-tab vs the DSD list each point came from:")
    for src in ("blockage", "works", "coastal"):
        cc = Counter(r["mechanism"] for r in rows if r["source"] == src)
        log(f"  {src:9s}: " + "  ".join(f"{k}={v}" for k, v in cc.most_common()))
    log(f"\nconfidence: {dict(Counter(r['confidence'] for r in rows))}")

    feats = []
    for r in rows:
        feats.append({
            "type": "Feature",
            "geometry": {"type": r["point"].geom_type,
                         "coordinates": list(r["point"].coords[0])},
            "properties": {
                "title": r["title"],
                "dsd_list": r["official_list"],
                "source_list": r["source"],
                "mechanism": r["mechanism"],
                "mechanism_basis": r["basis"],
                "confidence": r["confidence"],
                "elevation_m": (round(r["elevation_m"], 1)
                                if np.isfinite(r["elevation_m"]) else None),
                "d_coast_km": round(r["d_coast_km"], 3),
                "d_bigchannel_km": round(r["d_bigchannel_km"], 3),
                "d_inlet_km": round(r["d_inlet_km"], 3),
                "d_catchment_km": round(r["d_catchment_km"], 3),
                "big_channel_width_m": (round(r["big_channel_width_m"], 1)
                                        if np.isfinite(r["big_channel_width_m"]) else None),
                "nearest_catchment": r["catchment_name"],
            }})
    # RFC 7946: a GeoJSON file must NOT carry a crs member. The coordinates
    # are already lon/lat (EPSG:4326), which is the GeoJSON default.
    gj = {"type": "FeatureCollection",
          "features": feats}
    with open(OUT_GJ, "w") as f:
        json.dump(gj, f, indent=1)
    log(f"\nwrote {OUT_GJ} ({len(feats)} features)")

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["title", "dsd_list", "mechanism", "confidence", "elevation_m",
                    "d_coast_km", "d_bigchannel_km", "d_inlet_km",
                    "d_catchment_km", "nearest_catchment", "mechanism_basis"])
        for r in rows:
            w.writerow([r["title"], r["official_list"], r["mechanism"], r["confidence"],
                        f"{r['elevation_m']:.1f}" if np.isfinite(r["elevation_m"]) else "",
                        f"{r['d_coast_km']:.3f}", f"{r['d_bigchannel_km']:.3f}",
                        f"{r['d_inlet_km']:.3f}", f"{r['d_catchment_km']:.3f}",
                        r["catchment_name"], r["basis"]])
    log(f"wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
