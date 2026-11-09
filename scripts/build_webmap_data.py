#!/usr/bin/env python3
"""Build the browser data for the HK landslide susceptibility web map.

Design notes — why a raster overlay plus a score grid, not 29,614 polygons:

  * 29,614 polygon features as SVG paths is unusable in a browser (Leaflet
    builds one path element per feature, so panning stalls). A transparent
    PNG overlay of the 5-class surface pans and zooms instantly.
  * But a PNG cannot be interrogated, and "what is the score of this cell?"
    is the question a reader actually asks. So the scores ship as a flat
    JSON array: the page converts a mouse position to a row/column and
    reads the number back. 76k numbers, ~500 KB raw, and the page can do a
    million lookups a second with them.
  * The vector cells and the recorded landslide points still ship, gzipped,
    in assets/data/landslide/ for anyone opening them in QGIS or ArcGIS Pro.

Writes:
  apps/landslide-susceptibility/data/susceptibility_surface.png  (transparent, 4x)
  apps/landslide-susceptibility/data/susceptibility_grid.json    (scores + cuts + stats)
  apps/landslide-susceptibility/data/landslide_points.geojson.gz (browser points)
"""
import os
import os, csv, json, gzip, shutil
import numpy as np
from pyproj import Transformer
from PIL import Image

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
BASE = f"{GIS_DATA}/HK Landslide Susceptibility"
def _find_repo_root():
    """Walk up from this script until the repo root is found.

    The repo is recognised by its assets/data directory, so this works for a
    script in scripts/ and for one in scripts/<project>/ alike.
    """
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "assets", "data")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


REPO = os.environ.get("NPLGIS_REPO") or _find_repo_root() or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
APPDIR = os.path.join(REPO, "apps", "landslide-susceptibility")
DATADIR = os.path.join(APPDIR, "data")
ASSETDIR = os.path.join(REPO, "assets", "data", "landslide")
os.makedirs(DATADIR, exist_ok=True)
os.makedirs(ASSETDIR, exist_ok=True)

# same five-class palette as the published figure
COLORS = ["#f7f7f2", "#fee8a6", "#fdbb84", "#e34a33", "#7f0000"]
LABELS = ["Very low", "Low", "Moderate", "High", "Very high"]

tz = np.load(os.path.join(BASE, "work", "terrain_200m.npz"))
CELL = float(tz["cell"]); X0 = float(tz["x0"]); Y0 = float(tz["y0"])
valid = tz["valid"]
NY, NX = valid.shape

# ------------------------------------------------------------------ scores
prob = np.full((NY, NX), np.nan)
with open(os.path.join(BASE, "out", "susceptibility_grid.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["susceptibility"] not in ("", "nan"):
            prob[int(r["row"]), int(r["col"])] = float(r["susceptibility"])

vals = prob[~np.isnan(prob)]
cuts = [float(q) for q in np.percentile(vals, [20, 40, 60, 80])]
cls = np.digitize(prob, cuts)

# ------------------------------------------------------------------ surface PNG
rgba = np.zeros((NY, NX, 4), dtype=np.uint8)
for i, hexcol in enumerate(COLORS):
    r_, g_, b_ = int(hexcol[1:3], 16), int(hexcol[3:5], 16), int(hexcol[5:7], 16)
    m = (cls == i) & np.isfinite(prob)
    rgba[m, 0], rgba[m, 1], rgba[m, 2] = r_, g_, b_
    rgba[m, 3] = 232
rgba[~np.isfinite(prob), 3] = 0

SCALE = 4
big = Image.fromarray(rgba, "RGBA").resize((NX * SCALE, NY * SCALE), Image.NEAREST)
png = os.path.join(DATADIR, "susceptibility_surface.png")
big.save(png, optimize=True)
print(f"surface png: {big.size[0]}x{big.size[1]}  {os.path.getsize(png)/1024:.0f} KB")

# ------------------------------------------------------------------ points PNG
# 124,020 point markers as Leaflet circleMarkers would create 124,020 DOM
# elements and stall the browser, so they are baked into a transparent PNG
# overlay on the same pixel grid as the surface.
tr = Transformer.from_crs(2326, 4326, always_xy=True)
pts_png = Image.new("RGBA", (NX * SCALE, NY * SCALE), (0, 0, 0, 0))
from PIL import ImageDraw
dr = ImageDraw.Draw(pts_png)
n_pts = 0
for fn in ("incidents.csv", "entli_crown.csv"):
    with open(os.path.join(BASE, "raw", fn), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                x, y = float(r["EASTING"]), float(r["NORTHING"])
            except (KeyError, TypeError, ValueError):
                continue
            c = int((x - X0) / CELL + 0.5)
            rr = int((Y0 - y) / CELL + 0.5)
            if 0 <= rr < NY and 0 <= c < NX:
                px = c * SCALE + SCALE // 2
                py = rr * SCALE + SCALE // 2
                dr.ellipse((px - 1, py - 1, px + 1, py + 1), fill=(20, 20, 20, 190))
                n_pts += 1
pp = os.path.join(DATADIR, "landslide_points.png")
pts_png.save(pp, optimize=True)
print(f"points png: {pts_png.size[0]}x{pts_png.size[1]}  "
      f"{os.path.getsize(pp)/1024:.0f} KB  ({n_pts} points)")

# ------------------------------------------------------------------ bounds + fit
x_lo = X0 - CELL / 2
x_hi = X0 + (NX - 0.5) * CELL
y_hi = Y0 + CELL / 2
y_lo = Y0 - (NY - 0.5) * CELL
tr = Transformer.from_crs(2326, 4326, always_xy=True)
(lon_lo, lat_lo), (lon_hi, lat_hi) = tr.transform(x_lo, y_lo), tr.transform(x_hi, y_hi)
print(f"bounds WGS84: {lon_lo:.6f},{lat_lo:.6f} .. {lon_hi:.6f},{lat_hi:.6f}")

# Local affine fit EPSG:2326 -> EPSG:4326 over the grid corners, so the
# browser can invert it without a projection library. Fit on 4 corners by
# least squares and report the residual.
import numpy as np2
corners = np2.array([(x_lo, y_lo), (x_hi, y_lo), (x_lo, y_hi), (x_hi, y_hi)])
ll = np2.array([tr.transform(x, y) for x, y in corners])
A = np2.column_stack([corners[:, 0], corners[:, 1], np2.ones(4)])
coef_lon = np2.linalg.lstsq(A, ll[:, 0], rcond=None)[0]
coef_lat = np2.linalg.lstsq(A, ll[:, 1], rcond=None)[0]
pred = A @ np2.vstack([coef_lon, coef_lat]).T
resid_m = np2.linalg.norm(ll - pred, axis=1).max()
print(f"affine fit residual: max {resid_m*1000:.2f} mm (over {((x_hi-x_lo)/1000):.0f} km)")
assert resid_m < 0.01, "affine fit too coarse for a 200 m cell"

# forward:  (east, north) -> (lon, lat)
# inverse:  (lon, lat)  -> (east, north), needed by the browser probe
M = np2.array([[coef_lon[0], coef_lon[1]], [coef_lat[0], coef_lat[1]]])
t = np2.array([coef_lon[2], coef_lat[2]])
Minv = np2.linalg.inv(M)
tinv = -Minv @ t

fit = {
    # forward coefficients: lon = f[0]*east + f[1]*north + f[2]; lat = f[3]*east + f[4]*north + f[5]
    "f": [float(coef_lon[0]), float(coef_lon[1]), float(coef_lon[2]),
          float(coef_lat[0]), float(coef_lat[1]), float(coef_lat[2])],
    # inverse coefficients: east = i[0]*lon + i[1]*lat + i[2]; north = i[3]*lon + i[4]*lat + i[5]
    "i": [float(Minv[0, 0]), float(Minv[0, 1]), float(tinv[0]),
          float(Minv[1, 0]), float(Minv[1, 1]), float(tinv[1])],
    "max_residual_m": float(resid_m),
    "note": "local affine fit, EPSG:2326 <-> EPSG:4326, over the grid corners",
}

# ------------------------------------------------------------------ class stats
rec = np.zeros((NY, NX), dtype=bool)
for fn in ("incidents.csv", "entli_crown.csv"):
    with open(os.path.join(BASE, "raw", fn), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                x, y = float(r["EASTING"]), float(r["NORTHING"])
            except (KeyError, TypeError, ValueError):
                continue
            c = int((x - X0) / CELL + 0.5); rr = int((Y0 - y) / CELL + 0.5)
            if 0 <= rr < NY and 0 <= c < NX:
                rec[rr, c] = True

land = np.isfinite(prob)
nland = int(land.sum())

# the cell (row, col) has its CENTRE at easting = X0 + col*CELL,
# northing = Y0 - row*CELL -> round to the NEAREST centre
rec = np.zeros((NY, NX), dtype=bool)
for fn in ("incidents.csv", "entli_crown.csv"):
    with open(os.path.join(BASE, "raw", fn), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                x, y = float(r["EASTING"]), float(r["NORTHING"])
            except (KeyError, TypeError, ValueError):
                continue
            c = int((x - X0) / CELL + 0.5); rr = int((Y0 - y) / CELL + 0.5)
            if 0 <= rr < NY and 0 <= c < NX:
                rec[rr, c] = True
total_hits = int((land & rec).sum())
overall = total_hits / nland * 1000

classes = []
for i, lab in enumerate(LABELS):
    m = (cls == i) & land
    n = int(m.sum()); hits = int((m & rec).sum())
    rate = hits / n * 1000 if n else 0.0
    classes.append({
        "code": i, "label": lab, "color": COLORS[i],
        "cells": n, "share_pct": round(100 * n / nland, 1),
        "landslide_cells": hits,
        "share_of_landslides_pct": round(100 * hits / total_hits, 1),
        "rate_per_1000": round(rate, 0),
        "risk_vs_average": round(rate / overall, 2),
    })
    print(f"  {lab:11s} n={n:6d} hits={hits:6d} rate={rate:6.0f}/1000  "
          f"risk {rate/overall:5.2f}x")

# ------------------------------------------------------------------ feature importance
fi_path = os.path.join(BASE, "out", "feature_importance.csv")
NICE = {
    "rough": "roughness", "slope": "slope (mean)", "slope_max": "slope (max)",
    "slope_p90": "slope (90th pct)", "relief": "relief", "curv": "curvature",
    "elev": "elevation", "twi": "wetness index", "spi": "stream power index",
    "lc_tree": "tree cover", "lc_shrub": "shrub cover", "lc_grass": "grass cover",
    "lc_bare": "bare ground", "lc_built": "built-up", "lc_veg": "vegetation",
    "wx_felsic": "felsic weathering", "wx_volc": "volcanic weathering",
    "wx_mid": "moderate weathering", "wx_res": "resistant weathering",
}
feature_importance = []
if os.path.exists(fi_path):
    with open(fi_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            feature_importance.append({
                "feature": r["feature"],
                "label": NICE.get(r["feature"], r["feature"]),
                "gain_pct": float(r["gain_pct"]),
            })

# ------------------------------------------------------------------ grid json
flat = []
for rr in range(NY):
    for cc in range(NX):
        v = prob[rr, cc]
        flat.append(round(float(v), 4) if np.isfinite(v) else None)

grid = {
    "rows": NY, "cols": NX, "cell_m": CELL,
    "x0": X0, "y0": Y0, "crs": "EPSG:2326",
    "bounds": {"south": round(lat_lo, 6), "west": round(lon_lo, 6),
               "north": round(lat_hi, 6), "east": round(lon_hi, 6)},
    "bounds_lonlat": {"lon_min": round(lon_lo, 6), "lat_min": round(lat_lo, 6),
                      "lon_max": round(lon_hi, 6), "lat_max": round(lat_hi, 6)},
    "fit": fit,
    "cut_points": [round(c, 4) for c in cuts],
    "class_labels": LABELS,
    "class_colors": COLORS,
    "classes": classes,
    "feature_importance": feature_importance,
    "overall_rate_per_1000": round(overall, 0),
    "total_landslide_cells": total_hits,
    "land_cells": nland,
    "scores": flat,
}
gj = os.path.join(DATADIR, "susceptibility_grid.json")
with open(gj, "w", encoding="utf-8") as f:
    json.dump(grid, f, separators=(",", ":"))
print(f"grid json: {os.path.getsize(gj)/1024:.0f} KB")

# ------------------------------------------------------------------ points
pts = []
for fn, kind in (("incidents.csv", "incident"), ("entli_crown.csv", "entli")):
    with open(os.path.join(BASE, "raw", fn), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                x, y = float(r["EASTING"]), float(r["NORTHING"])
            except (KeyError, TypeError, ValueError):
                continue
            lon, lat = tr.transform(x, y)
            props = {"s": kind}
            for k in ("FAILDATE", "LOCATION", "SLIDE_TYPE", "COVER", "CLASS"):
                if r.get(k):
                    props[k.lower()] = r[k]
            pts.append({"type": "Feature",
                        "geometry": {"type": "Point",
                                     "coordinates": [round(lon, 6), round(lat, 6)]},
                        "properties": props})
pts.sort(key=lambda p: (p["properties"]["s"], p["geometry"]["coordinates"]))
fc = {"type": "FeatureCollection", "features": pts}
pj = os.path.join(DATADIR, "landslide_points.geojson")
with gzip.open(pj + ".gz", "wt", encoding="utf-8") as f:
    json.dump(fc, f, separators=(",", ":"))
print(f"points: {len(pts)} features, gz {os.path.getsize(pj+'.gz')/1024:.0f} KB")

# ------------------------------------------------------------------ GIS copies
for src, dst in (("susceptibility_cells.geojson", "susceptibility_cells.geojson.gz"),
                 ("landslide_records.geojson", "landslide_records.geojson.gz"),
                 ("landslide_susceptibility.tif", "landslide_susceptibility.tif")):
    s = os.path.join(BASE, "out", src); d = os.path.join(ASSETDIR, dst)
    if dst.endswith(".gz"):
        with open(s, "rb") as fi, gzip.open(d, "wb") as fo:
            shutil.copyfileobj(fi, fo)
    else:
        shutil.copy2(s, d)
    print(f"  asset {dst}: {os.path.getsize(d)/1024/1024:.2f} MB")

# the published figure for the site gallery
os.makedirs(os.path.join(REPO, "assets", "maps", "landslide-susceptibility"), exist_ok=True)
shutil.copy2(os.path.join(BASE, "out", "landslide_susceptibility_map.png"),
             os.path.join(REPO, "assets", "maps", "landslide-susceptibility",
                          "landslide_susceptibility_map.png"))
print("done")
