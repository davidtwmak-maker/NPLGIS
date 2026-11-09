#!/usr/bin/env python3
"""Export the HK landslide susceptibility layer as GeoJSON for the vault.

Two outputs:
  1. susceptibility_cells.geojson  - one 200 m square polygon per cell with
     its susceptibility score and class, in EPSG:2326 (HK1980 grid) so it
     drops straight into ArcGIS Pro / QGIS alongside the other CSDI layers.
  2. landslide_records.geojson     - the recorded landslide points.

Both are written with the feature count asserted, because a silently
truncated GeoJSON is the classic failure here.
"""
import os
import os, csv, json
import numpy as np

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
BASE = f"{GIS_DATA}/HK Landslide Susceptibility"
WORK = os.path.join(BASE, "work")
OUT = os.path.join(BASE, "out")

tz = np.load(os.path.join(WORK, "terrain_200m.npz"))
CELL = float(tz["cell"]); X0 = float(tz["x0"]); Y0 = float(tz["y0"])
valid = tz["valid"]
NY, NX = valid.shape

# ---------------------------------------------------------------- cells
# grid_cells.csv carries the full predictor set for every land cell;
# susceptibility_grid.csv carries the model score. Join on (row, col).
grid = [r for r in csv.DictReader(open(os.path.join(OUT, "susceptibility_grid.csv"),
                                       encoding="utf-8"))
        if r["susceptibility"] not in ("", "nan")]
print(f"grid rows with a score: {len(grid)}")

attrs = {}
for r in csv.DictReader(open(os.path.join(WORK, "grid_cells.csv"), encoding="utf-8")):
    attrs[(int(r["row"]), int(r["col"]))] = r
print(f"grid_cells.csv rows: {len(attrs)}")
missing = [k for k in ((int(r["row"]), int(r["col"])) for r in grid)
           if k not in attrs]
assert not missing, f"{len(missing)} scored cells have no attribute row"

prob = np.full((NY, NX), np.nan)
for r in grid:
    prob[int(r["row"]), int(r["col"])] = float(r["susceptibility"])
vals = prob[~np.isnan(prob)]
qs = np.percentile(vals, [20, 40, 60, 80])
cls = np.digitize(prob, qs)
CLASS_NAMES = ["Very low", "Low", "Moderate", "High", "Very high"]


def f(row, key, nd=2):
    try:
        return round(float(row[key]), nd)
    except (KeyError, TypeError, ValueError):
        return None


feats = []
for r in grid:
    row, col = int(r["row"]), int(r["col"])
    p = float(r["susceptibility"])
    a = attrs[(row, col)]
    x0 = X0 + col * CELL - CELL / 2
    y0 = Y0 - row * CELL - CELL / 2
    feats.append({
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [x0, y0], [x0 + CELL, y0], [x0 + CELL, y0 + CELL],
                [x0, y0 + CELL], [x0, y0],
            ]],
        },
        "properties": {
            "suscept": round(p, 4),
            "class": CLASS_NAMES[int(cls[row, col])],
            "cls_code": int(cls[row, col]),
            "slope_deg": f(a, "slope"),
            "slope_max": f(a, "slope_max"),
            "relief_m": f(a, "relief"),
            "elev_m": f(a, "elev"),
            "wx_felsic": f(a, "wx_felsic", 3),
            "wx_volc": f(a, "wx_volc", 3),
            "wx_class": int(a.get("wx_class", -1)),
            "easting": round(float(r["easting"]), 1),
            "northing": round(float(r["northing"]), 1),
        },
    })
cells_path = os.path.join(OUT, "susceptibility_cells.geojson")
with open(cells_path, "w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection",
               "crs": {"type": "name",
                       "properties": {"name": "urn:ogc:def:crs:EPSG::2326"}},
               "features": feats}, f)
print(f"wrote {cells_path}: {len(feats)} features, "
      f"{os.path.getsize(cells_path)/1e6:.1f} MB")
assert len(feats) == len(grid) and len(feats) > 29000, "cell export truncated"

# ---------------------------------------------------------------- points
pts = []
n_inc = n_ent = 0
for fn, xk, yk, kind in (("incidents.csv", "EASTING", "NORTHING", "incident"),
                         ("entli_crown.csv", "EASTING", "NORTHING", "entli")):
    for r in csv.DictReader(open(os.path.join(BASE, "raw", fn), encoding="utf-8")):
        try:
            x, y = float(r[xk]), float(r[yk])
        except (TypeError, ValueError):
            continue
        props = {"source": kind}
        for k in ("INCID", "FAILDATE", "FEATTYPE", "SCALE", "LOCATION",
                  "SLIDE_TYPE", "M_WIDTH", "COVER", "CLASS", "YEAR_1", "ENTLI_NO"):
            if k in r and r[k] not in ("", None):
                props[k] = r[k]
        pts.append({"type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [x, y]},
                    "properties": props})
        if kind == "incident":
            n_inc += 1
        else:
            n_ent += 1
pt_path = os.path.join(OUT, "landslide_records.geojson")
with open(pt_path, "w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection",
               "crs": {"type": "name",
                       "properties": {"name": "urn:ogc:def:crs:EPSG::2326"}},
               "features": pts}, f)
print(f"wrote {pt_path}: {len(pts)} features "
      f"(incidents {n_inc}, entli {n_ent}), {os.path.getsize(pt_path)/1e6:.1f} MB")
assert n_inc > 10000 and n_ent > 100000, "point export truncated"

# ---------------------------------------------------------------- GeoTIFF
try:
    import rasterio
    from rasterio.transform import Affine
    tr = Affine(CELL, 0.0, X0 - CELL / 2, 0.0, -CELL, Y0 + CELL / 2)
    arr = np.where(np.isfinite(prob), prob, -9999).astype(np.float32)
    tif = os.path.join(OUT, "landslide_susceptibility.tif")
    with rasterio.open(tif, "w", driver="GTiff", height=NY, width=NX, count=1,
                       dtype="float32", crs="EPSG:2326", transform=tr,
                       nodata=-9999, compress="deflate") as dst:
        dst.write(arr, 1)
        dst.update_tags(
            title="HK landslide susceptibility (XGBoost)",
            source="LandsD DTM 5m; CEDD landslide incidents; ENTLI; ESA WorldCover 2021; CEDD Geological Map",
            model="XGBoost, 5-fold spatial blocked CV (5 km blocks), ROC-AUC 0.858")
    print(f"wrote {tif}: {os.path.getsize(tif)/1e6:.2f} MB")
except Exception as e:
    print("GeoTIFF export skipped:", e)
