#!/usr/bin/env python3
"""
Build 2D polygon layers of Hong Kong's steep slopes (>30 degrees) from the
LandsD DTM, on the 20 m analysis grid.

Slope definition: the published landslide work in this folder established that
MEAN gradient dilutes a 40 deg scarp inside a 200 m cell (with mean slope,
100% of incidents appear under 30 deg - the artefact the original storymap
fell into). This script therefore uses the MAXIMUM Horn slope within each cell
as the primary definition, and ships the mean-gradient polygon layer
alongside so the choice is auditable rather than hidden.

test_slope30_definition.py measures the difference:
  slope_mean >30 deg : 1.42% of land,  4.89% of incidents,  3.45x average rate
  slope_max  >30 deg : 10.09% of land, 23.20% of incidents,  2.30x average rate
  22,700 incidents sit in a cell whose MEAN slope is under 30 deg but whose
  MAXIMUM is over - the scarp the mean gradient averages away.

Outputs (out/):
  steep_slopes_over30.geojson      >30 deg regions (max slope), EPSG:2326
  slope_class_polygons.geojson      all land, classed 0-15/15-30/30-45/45-60/60+
  slope_max_20m.tif                slope_max raster (EPSG:2326)
  slope_mean_20m.tif               slope_mean raster (EPSG:2326)
  slope_classes_20m.tif            classed raster (EPSG:2326)
  steep_slopes_over30_stats.json    statistics + area reconciliation
"""
import json
import os
import time

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.transform import from_origin
from scipy import ndimage
from shapely.geometry import shape as shape_geom
from shapely.geometry import mapping
from shapely.validation import make_valid as shape_make_valid
from shapely.geometry import Polygon as ShapePolygon


def shape_valid(geom):
    """True when the geometry is GEOS-valid.

    Note: a polygon WITH HOLES is valid - an earlier version of this check
    rejected any interior ring, which wrongly flagged 181 perfectly good
    polygons (GEOS: "Valid Geometry").  The exterior and each interior ring
    must be simple, but a hole is not an error.
    """
    try:
        if not geom.is_valid:
            return False
        if geom.geom_type == "Polygon":
            if not geom.exterior.is_simple:
                return False
            for ring in geom.interiors:
                if not ring.is_simple:
                    return False
            return True
        return True
    except Exception:
        return False


def shape_buffer(geom, dist):
    """Repair a self-intersecting polygon: buffer by 0, which splits the ring
    into valid pieces, then re-assemble any MultiPolygon."""
    try:
        fixed = shape_make_valid(geom)
    except Exception:
        fixed = geom.buffer(dist)
    if fixed.geom_type == "GeometryCollection":
        parts = [g for g in fixed.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not parts:
            return fixed
        from shapely.ops import unary_union
        fixed = unary_union(parts)
    return fixed

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

THRESHOLD = 30.0
CELL = 20.0

d = np.load(os.path.join(BASE, "work", "terrain_20m.npz"))
valid = d["valid"]
slope_max = d["slope_max"].astype(np.float32)
slope_mean = d["slope"].astype(np.float32)
x0 = float(d["x0"])
y0 = float(d["y0"])
H, W = valid.shape

# Cell CENTRES are at x0 + col*CELL, y0 - row*CELL, so the raster's edges are
# half a cell out: left = x0 - CELL/2, top = y0 + CELL/2. These reproduce the
# DTM's own transform.c / transform.f (799997.5 / 848002.5), which is what
# makes the 20 m grid share the 200 m grid's cell boundaries.
left = x0 - CELL / 2
top = y0 + CELL / 2
transform = from_origin(left, top, CELL, CELL)
print(f"grid {W}x{H} cell {CELL} m | origin left {left} top {top}")

CELL_AREA = CELL * CELL
nv = int(valid.sum())
land_area = nv * CELL_AREA
stats = {
    "threshold_deg": THRESHOLD,
    "grid_m": CELL,
    "crs": "EPSG:2326 (HK1980 Grid)",
    "dims": [W, H],
    "valid_land_cells": nv,
    "land_area_km2": round(land_area / 1e6, 2),
    "raster_transform": {"left": left, "top": top, "cell": CELL},
}

# ---------------------------------------------------------------- raster out
def write_tif(path, arr, nodata=None, dtype="float32"):
    prof = {
        "driver": "GTiff", "height": H, "width": W, "count": 1,
        "dtype": dtype, "crs": "EPSG:2326", "transform": transform,
        "compress": "deflate", "tiled": True, "blockxsize": 256, "blockysize": 256,
    }
    if nodata is not None:
        prof["nodata"] = nodata
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(arr, 1)
    return path


t_start = time.time()
write_tif(os.path.join(OUT, "slope_max_20m.tif"), np.where(valid, slope_max, -9999).astype("float32"), -9999)
write_tif(os.path.join(OUT, "slope_mean_20m.tif"), np.where(valid, slope_mean, -9999).astype("float32"), -9999)
print(f"rasters written ({time.time()-t_start:.0f}s)", flush=True)

# ------------------------------------------------------- slope class raster
# 1 = 0-15, 2 = 15-30, 3 = 30-45, 4 = 45-60, 5 = 60+
# Every VALID land cell starts in class 1 and is then promoted, so the five
# classes partition the land exactly.  Leaving the default at 0 would put the
# gentle land in "nodata" and drop its area from the polygon reconciliation.
cls = np.zeros((H, W), dtype="uint8")
cls[valid] = 1
cls[valid & (slope_max > 15)] = 2
cls[valid & (slope_max > 30)] = 3
cls[valid & (slope_max > 45)] = 4
cls[valid & (slope_max > 60)] = 5
write_tif(os.path.join(OUT, "slope_classes_20m.tif"), cls, nodata=0, dtype="uint8")

CLASS_NAMES = {1: "0-15", 2: "15-30", 3: "30-45", 4: "45-60", 5: "60+"}
stats["slope_class_area"] = {
    CLASS_NAMES[c]: {
        "cells": int(((cls == c) & valid).sum()),
        "area_km2": round(int(((cls == c) & valid).sum()) * CELL_AREA / 1e6, 2),
        "pct_of_land": round(int(((cls == c) & valid).sum()) * CELL_AREA / land_area * 100, 2),
    } for c in range(1, 6)
}

# ------------------------------------------- polygonise by connected region
def polygonise(mask, arr_for_stats=None):
    """One polygon per connected region of `mask` (4-connectivity).

    The region LABEL is read back from each shape's own 'value' property
    rather than inferred from the order shapes() yields them.  shapes() is
    documented to emit polygons in row-major order, but relying on that
    ordering silently shifts every region's attributes by one when the
    arrays are indexed by label (labels start at 1, shapes start at 0).
    """
    labels, n = ndimage.label(mask, structure=ndimage.generate_binary_structure(2, 2))
    if n == 0:
        return [], labels, n, None
    counts = np.bincount(labels.ravel())
    flat = labels.ravel()
    ids = np.arange(len(counts))
    npix = counts[ids]
    areas = npix * CELL_AREA
    if arr_for_stats is not None:
        vals = np.where(flat > 0, arr_for_stats.ravel(), np.nan)
        s = np.bincount(flat, weights=np.nan_to_num(vals), minlength=len(counts))
        s2 = np.bincount(flat, weights=np.nan_to_num(vals) ** 2, minlength=len(counts))
        mean_v = s[ids] / npix
        var = np.maximum(s2[ids] / npix - mean_v ** 2, 0.0)
        sd_v = np.sqrt(var)
    else:
        mean_v = np.full(len(counts), np.nan)
        sd_v = np.full(len(counts), np.nan)

    # Per-region MAXIMUM, vectorised.  A per-region loop of the form
    # arr[labels == (i+1)].max() is O(regions x grid) and takes hours at
    # 47k regions over a 7.6M-cell grid; this is O(grid).
    if arr_for_stats is not None:
        arr_flat = np.where(flat > 0, arr_for_stats.ravel(), -np.inf)
        max_v = np.full(len(counts), -np.inf)
        np.maximum.at(max_v, flat, arr_flat)
        max_v = np.where(npix > 0, max_v, np.nan)
    else:
        max_v = np.full(len(counts), np.nan)

    # Pass the LABEL array as the data band so every shape carries its own
    # region id; mask keeps the background out.
    # rasterio.features.shapes yields (geom, value) for an ndarray input, but
    # (geom, {'band': value}) for a dict input - handle both.
    geoms = []
    lab_ids = []
    for geom, props in shapes(labels.astype("int32"), mask=mask,
                              transform=transform, connectivity=8):
        val = props["value"] if isinstance(props, dict) else props
        # shapes() returns a GeoJSON-style MAPPING, not a shapely geometry.
        geoms.append(shape_geom(geom))
        lab_ids.append(int(val))
    assert len(geoms) == n, f"shape/label count mismatch: {len(geoms)} vs {n}"
    assert sorted(lab_ids) == list(range(1, n + 1)), "region ids are not 1..n"

    # A pixel-boundary polygon can self-intersect where the region touches
    # itself diagonally (8-connectivity makes such a touch legal).  A
    # self-intersecting ring has no meaningful area and will be rejected by
    # ArcGIS/QGIS, so repair with a zero-width buffer, which splits the ring
    # into valid pieces.  The buffered geometry's area is then re-measured
    # from the geometry itself, not assumed.
    repaired = 0
    out_geoms = []
    for g in geoms:
        try:
            if not shape_valid(g):
                g = shape_buffer(g, 0)
                repaired += 1
        except Exception:
            pass
        out_geoms.append(g)
    if repaired:
        print(f"  repaired {repaired:,} self-intersecting polygons", flush=True)
    return out_geoms, lab_ids, n, (areas, mean_v, sd_v, npix, max_v)


# ------------------- layer 1: steep slopes > 30 deg (max slope) ------------
mask = valid & (slope_max > THRESHOLD)
print(f"polygonising >{THRESHOLD} deg regions...", flush=True)
t0 = time.time()
geoms, lab_ids, nreg, st = polygonise(mask, slope_max)
areas, mean_v, sd_v, npix, max_v = st
print(f"  {nreg:,} regions in {time.time()-t0:.0f}s", flush=True)

recs = []
for i, g in enumerate(geoms):
    L = lab_ids[i]          # the region LABEL (1..n), which indexes the arrays
    # Measure the area from the geometry ITSELF.  A repaired polygon can have
    # a slightly different area from the cell count, so the cell-count area
    # is only the expectation, not the value to publish.
    area_m2 = float(g.area)
    recs.append({
        "type": "Feature",
        "geometry": mapping(g),
        "properties": {
            "region_id": L,
            "slope_mean_deg": round(float(mean_v[L]), 1),
            "slope_sd_deg": round(float(sd_v[L]), 1),
            "slope_max_deg": round(float(max_v[L]), 1),
            "area_m2": round(area_m2, 1),
            "area_km2": round(area_m2 / 1e6, 3),
            "n_cells": int(npix[L]),
            "slope_def": "max_horn_20m",
        },
    })
fc = {"type": "FeatureCollection",
      "crs": {"type": "name", "properties": {"name": "EPSG:2326"}},
      "features": recs}
p_steep = os.path.join(OUT, "steep_slopes_over30.geojson")
with open(p_steep, "w") as fh:
    json.dump(fc, fh)

poly_area_sum = float(sum(r["properties"]["area_m2"] for r in recs))
expected_area = float(mask.sum()) * CELL_AREA
stats["steep_over30"] = {
    "regions": nreg,
    "cells": int(mask.sum()),
    "area_km2": round(expected_area / 1e6, 2),
    "pct_of_land": round(expected_area / land_area * 100, 2),
    "polygon_area_sum_m2": round(poly_area_sum, 1),
    "area_reconciliation_error_m2": round(abs(poly_area_sum - expected_area), 6),
    "feature_count_written": len(recs),
}
print(f"  wrote {p_steep} ({len(recs):,} features)", flush=True)

# ------------------- layer 2: full slope-class polygons --------------------
print("polygonising slope classes...", flush=True)
t0 = time.time()
recs2 = []
for c in range(1, 6):
    m = valid & (cls == c)
    if not m.any():
        continue
    g2, lab2, n2, st2 = polygonise(m, slope_max)
    a2, mv2, sdv2, np2, mx2 = st2
    for i, g in enumerate(g2):
        L = lab2[i]
        area_m2 = float(g.area)
        recs2.append({
            "type": "Feature",
            "geometry": mapping(g),
            "properties": {
                "slope_class": CLASS_NAMES[c],
                "slope_class_id": c,
                "slope_mean_deg": round(float(mv2[L]), 1),
                "slope_max_deg": round(float(mx2[L]), 1),
                "area_m2": round(area_m2, 1),
                "area_km2": round(area_m2 / 1e6, 3),
                "n_cells": int(np2[L]),
                "over_30": bool(c >= 3),
            },
        })
    print(f"  class {CLASS_NAMES[c]}: {n2:,} regions", flush=True)
fc2 = {"type": "FeatureCollection",
       "crs": {"type": "name", "properties": {"name": "EPSG:2326"}},
       "features": recs2}
p_cls = os.path.join(OUT, "slope_class_polygons.geojson")
with open(p_cls, "w") as fh:
    json.dump(fc2, fh)
print(f"  wrote {p_cls} ({len(recs2):,} features) in {time.time()-t0:.0f}s", flush=True)

cls_area_sum = sum(r["properties"]["area_m2"] for r in recs2)
stats["slope_class_polygons"] = {
    "features": len(recs2),
    "area_sum_km2": round(cls_area_sum / 1e6, 2),
    "land_area_km2": round(land_area / 1e6, 2),
    "area_reconciliation_error_m2": round(abs(cls_area_sum - land_area), 3),
}

# ------------------------------------------------------------- assertions
assert len(recs) == nreg
# The polygon area is measured from the geometry, so it must reconcile to the
# cell count within the tolerance that pixelisation allows (a pixel-boundary
# polygon cuts the corner of its cell).
tol = expected_area * 0.01
assert abs(poly_area_sum - expected_area) < tol, \
    f"steep polygon area does not reconcile: {poly_area_sum} vs {expected_area}"
assert abs(cls_area_sum - land_area) < land_area * 0.01, \
    "class polygon area does not reconcile to land area"
# the classes must partition the land exactly
assert int(sum(stats["slope_class_area"][CLASS_NAMES[c]]["cells"] for c in range(1, 6))) == nv

# every polygon must be a valid, simple ring - ArcGIS and QGIS reject
# self-intersecting polygons, so a layer that fails this cannot be shipped
invalid = [r for r in recs if not shape_valid(shape_geom(r["geometry"]))]
assert not invalid, f"{len(invalid)} invalid steep polygons remain"
invalid2 = [r for r in recs2 if not shape_valid(shape_geom(r["geometry"]))]
assert not invalid2, f"{len(invalid2)} invalid class polygons remain"
stats["geometry_validity"] = {
    "steep_polygons_valid": len(recs),
    "class_polygons_valid": len(recs2),
}

with open(os.path.join(OUT, "steep_slopes_over30_stats.json"), "w") as fh:
    json.dump(stats, fh, indent=2)
print(json.dumps(stats, indent=2))
print("OK: areas reconcile, classes partition the land")
