#!/usr/bin/env python3
"""Build an ArcGIS-ready File Geodatabase from the Kowloon covered-walkway analysis.

Why this exists
---------------
The analysis output was a bare JSON array.  ArcGIS Pro can open a .json as a
standalone table, but it carries no geometry and no spatial reference, so it
will never draw.  This script converts the outputs into proper feature
classes:

    Kowloon_Covered_Walkways.gdb
        Schools_RouteMetrics   point   103  school + the exposure metrics
        Route_Candidates        point 16387  every candidate stop per school
        Routes_To_School       line    206  shortest + best-covered routes
        Covered_Paths          line  14761  the sheltered network
        Stops_PTI              point  1778  MTR exits / bus / minibus stops

CRS: Hong Kong 1980 Grid System (EPSG:2326) — the same native CRS the CSDI
layers carry, so these layers overlay the team's map without a spatial-
reference warning.  (The source files were exported as WGS84 and are
projected here.)

Nested JSON (ai_by_type, ai_pti_detail) is FLATTENED — a FileGeodatabase field
cannot hold a nested object.  Every derived field keeps its ai_ prefix.
"""
import json
import os
import shutil
import subprocess
import tempfile

from pyproj import Transformer

BASE = os.path.expanduser("~/GIS Data/Sun-Rain Exposure")
WORK = os.path.join(BASE, "work")
VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/"
                            "Documents/NPL GIS Team/GIS Projects/最日曬雨淋中學")
OUTDIR = os.path.join(VAULT, "arcgis")
GDB = os.path.join(OUTDIR, "Kowloon_Covered_Walkways.gdb")
QGIS_APP = "/Applications/QGIS-final-4_2_3.app"
OGR2OGR = os.path.join(QGIS_APP, "Contents/MacOS/ogr2ogr")
# GDAL needs to find proj.db for the EPSG:2326 lookup; this build of QGIS keeps
# it inside the app bundle, so the data path has to be set explicitly or the
# SRS definition fails with "Cannot find proj.db".
GDAL_ENV = dict(os.environ)
GDAL_ENV["PROJ_DATA"] = os.path.join(QGIS_APP, "Contents/Resources/qgis/proj")
GDAL_ENV["PROJ_LIB"] = GDAL_ENV["PROJ_DATA"]
GDAL_ENV["GDAL_DATA"] = os.path.join(QGIS_APP, "Contents/Resources/gdal")
if os.path.isdir(GDAL_ENV["GDAL_DATA"]):
    pass
else:
    GDAL_ENV.pop("GDAL_DATA")

# EPSG:4326 (WGS84) -> EPSG:2326 (Hong Kong 1980 Grid)
tr = Transformer.from_crs("EPSG:4326", "EPSG:2326", always_xy=True)


def proj_xy(lon, lat):
    # GeoJSON is defined as EPSG:4326 (WGS84 lon/lat).  The projection to
    # EPSG:2326 is done by ogr2ogr via -t_srs, so the coordinate written here
    # must stay in WGS84 — projecting in Python AND telling GDAL to reproject
    # would apply the transform twice.
    return [round(lon, 7), round(lat, 7)]


def log(m):
    print(m, flush=True)


schools = json.load(open(os.path.join(WORK, "peninsula_routes_schools.json"), encoding="utf-8"))
pti = json.load(open(os.path.join(WORK, "peninsula_pti.geojson"), encoding="utf-8"))["features"]
routes = json.load(open(os.path.join(WORK, "peninsula_route_geometry.geojson"), encoding="utf-8"))["features"]
covpaths = json.load(open(os.path.join(WORK, "peninsula_covered_paths.geojson"), encoding="utf-8"))["features"]

tmp = tempfile.mkdtemp(prefix="kowloon_gdb_")
log(f"temp: {tmp}")


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def write_gj(name, obj):
    p = os.path.join(tmp, name + ".geojson")
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


# --------------------------------------------------- 1. Schools_RouteMetrics
log("Schools_RouteMetrics ...")
sch_feats = []
for r in schools:
    p = {k: v for k, v in r.items() if k not in ("lon", "lat", "ai_pti_detail", "ai_by_type")}
    p["name_tc"] = r.get("name_tc")
    # flatten the per-stop-type summary
    for kind in ("mtr", "bus", "minibus"):
        t = (r.get("ai_by_type") or {}).get(kind)
        for fld in ("ai_route_m", "ai_covered_ratio", "ai_longest_exposed_m", "ai_pti_name"):
            p[f"{kind}_{fld}"] = (t.get(fld) if t else None)
    sch_feats.append({"type": "Feature",
                       "geometry": {"type": "Point", "coordinates": proj_xy(r["lon"], r["lat"])},
                       "properties": p})
p1 = write_gj("schools", fc(sch_feats))

# ------------------------------------------------------ 2. Route_Candidates
log("Route_Candidates ...")
# join each candidate record back to the stop's own location
stop_xy = {}
for f in pti:
    pr = f["properties"]
    stop_xy[(pr["ai_kind"], pr["ai_name"])] = f["geometry"]["coordinates"]
cand_feats = []
miss = 0
for r in schools:
    for c in r.get("ai_pti_detail", []):
        xy = stop_xy.get((c["kind"], c["name"]))
        if xy is None:
            miss += 1
            continue
        p = dict(c)
        p["school"] = r["name"]
        p["district"] = r["district"]
        p["school_type"] = r["type"]
        p["school_lon"] = r["lon"]
        p["school_lat"] = r["lat"]
        cand_feats.append({"type": "Feature",
                            "geometry": {"type": "Point", "coordinates": proj_xy(xy[0], xy[1])},
                            "properties": p})
log(f"  {len(cand_feats)} candidate records, {miss} without a matched stop location")
p2 = write_gj("candidates", fc(cand_feats))

# ------------------------------------------------------ 3. Routes_To_School
log("Routes_To_School ...")
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform
rt_feats = []
for f in routes:
    g = shape(f["geometry"])
    parts = list(g.geoms) if g.geom_type == "MultiLineString" else [g]
    for part in parts:
        if part.geom_type != "LineString" or len(part.coords) < 2:
            continue
        xy = [proj_xy(x, y) for x, y in part.coords]
        rt_feats.append({"type": "Feature",
                         "geometry": {"type": "LineString", "coordinates": xy},
                         "properties": dict(f["properties"])})
log(f"  {len(rt_feats)} route lines")
p3 = write_gj("routes", fc(rt_feats))

# ---------------------------------------------------------- 4. Covered_Paths
log("Covered_Paths ...")
cp_feats = []
for f in covpaths:
    g = shape(f["geometry"])
    if g.geom_type != "LineString" or len(g.coords) < 2:
        continue
    xy = [proj_xy(x, y) for x, y in g.coords]
    cp_feats.append({"type": "Feature",
                     "geometry": {"type": "LineString", "coordinates": xy},
                     "properties": dict(f["properties"])})
log(f"  {len(cp_feats)} covered path segments")
p4 = write_gj("covered", fc(cp_feats))

# ------------------------------------------------------------- 5. Stops_PTI
log("Stops_PTI ...")
sp_feats = []
for f in pti:
    g = shape(f["geometry"])
    pr = dict(f["properties"])
    pr["ai_sheltered_30m"] = pr.pop("ai_sheltered_within_30m", None)
    sp_feats.append({"type": "Feature",
                     "geometry": {"type": "Point", "coordinates": proj_xy(g.x, g.y)},
                     "properties": pr})
p5 = write_gj("stops", fc(sp_feats))

# ------------------------------------------------------- write the FileGDB
if os.path.exists(GDB):
    shutil.rmtree(GDB)
os.makedirs(OUTDIR, exist_ok=True)

LAYERS = [
    (p1, "Schools_RouteMetrics", "POINT"),
    (p2, "Route_Candidates", "POINT"),
    (p3, "Routes_To_School", "LINESTRING"),
    (p4, "Covered_Paths", "LINESTRING"),
    (p5, "Stops_PTI", "POINT"),
]
for src, name, gtype in LAYERS:
    cmd = [OGR2OGR, "-f", "OpenFileGDB", GDB, src,
           "-nln", name,
           "-s_srs", "EPSG:4326",
           "-t_srs", "EPSG:2326",
           "-overwrite",
           "-nlt", gtype,
           "-lco", "GEOMETRY_NAME=Shape",
           "-lco", "FID=OBJECTID"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=GDAL_ENV)
    status = "OK " if r.returncode == 0 else "FAIL"
    log(f"  {status} {name}")
    if r.returncode != 0:
        print(r.stdout[-1500:]); print(r.stderr[-1500:])
        raise SystemExit(f"ogr2ogr failed for {name}")

# ---------------------------------------------------------------- verify
OG="/Applications/QGIS-final-4_2_3.app/Contents/MacOS/ogrinfo"
r = subprocess.run([OG, "-so", "-al", GDB], capture_output=True, text=True, env=GDAL_ENV)
log("\n--- ogrinfo ---")
print(r.stdout[:3500])

# also a flat CSV of the school metrics, for anyone who wants to pivot it
import csv
with open(os.path.join(OUTDIR, "Schools_RouteMetrics.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(sch_feats[0]["properties"].keys()))
    w.writeheader()
    for ft in sch_feats:
        w.writerow(ft["properties"])
log(f"\nCSV written: {os.path.join(OUTDIR, 'Schools_RouteMetrics.csv')}")

shutil.rmtree(tmp, ignore_errors=True)
log("done")
