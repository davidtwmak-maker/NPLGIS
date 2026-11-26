#!/usr/bin/env python3
"""Build the Kowloon Covered Walkways web app data + the ArcGIS deliverables.

Inputs  : work/peninsula_routes_schools.json      (from kowloon_peninsula_routes.py)
          work/peninsula_route_geometry.geojson
          work/peninsula_covered_paths.geojson
          work/peninsula_pti.geojson
Outputs : apps/kowloon-covered-walkways/data/*.json|geojson   (for the Leaflet app)
          assets/data/kowloon-covered-walkways/*               (for the published site)
          assets/data/kowloon-covered-walkways/*.gdb           (ArcGIS Pro)
          Schools_RouteMetrics.csv

Schools are keyed by school_id (dataset_id + OBJECTID), NOT by name: six
schools in the study area share a name with another (two Rudolf Steiner
campuses, two LAI CHACK sites, two BEACON records) and keying on the name
silently merges distinct campuses.
"""
import csv
import gzip
import json
import os
import shutil
import subprocess
import sys

BASE = os.path.expanduser("~/GIS Data/Sun-Rain Exposure")
WORK = os.path.join(BASE, "work")
# The repository the live site is served from.  The script used to write
# to a scratch clone, which meant the published app was built from a
# copy that could drift from the one that is actually deployed.  It
# writes to the real repository now.
REPO = os.path.expanduser("~/nplgis")
APPDATA = os.path.join(REPO, "apps/kowloon-covered-walkways/data")
SITEDATA = os.path.join(REPO, "assets/data/kowloon-covered-walkways")
VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/"
                            "Documents/NPL GIS Team/GIS Projects/最日曬雨淋中學")
QGIS = "/Applications/QGIS-final-4_2_3.app/Contents/MacOS"
OGR2OGR = os.path.join(QGIS, "ogr2ogr")
PROJDATA = "/Applications/QGIS-final-4_2_3.app/Contents/Resources/qgis/proj"

for d in (APPDATA, SITEDATA, os.path.join(VAULT, "arcgis")):
    os.makedirs(d, exist_ok=True)

raw = json.load(open(os.path.join(WORK, "peninsula_routes_schools.json"), encoding="utf-8"))
# access typology (15-min rule): walk-access vs bus/minibus-dependent, with
# the paired bus reference and the priority tier.  Joined by school_id.
typ_path = os.path.join(WORK, "access_typology.json")
typ_by_id = {}
if os.path.exists(typ_path):
    typ_by_id = {r["school_id"]: r for r in json.load(open(typ_path, encoding="utf-8"))}
print("access typology joined:", len(typ_by_id), "schools")
routes = json.load(open(os.path.join(WORK, "peninsula_route_geometry.geojson"), encoding="utf-8"))
covered = json.load(open(os.path.join(WORK, "peninsula_covered_paths.geojson"), encoding="utf-8"))
pti = json.load(open(os.path.join(WORK, "peninsula_pti.geojson"), encoding="utf-8"))

by_id = {r["school_id"]: r for r in raw}
assert len(by_id) == len(raw), "school_id is not unique"

# ---------------------------------------------------------------- app: schools
schools = {"type": "FeatureCollection", "features": []}
summary = []
for r in raw:
    p = {
        "school_id": r["school_id"],
        "name": r["name"],
        "name_tc": r.get("name_tc"),
        "district": r.get("district"),
        "type": r.get("type"),
        "lon": r["lon"], "lat": r["lat"],
        "ai_routable": r.get("ai_routable"),
        "ai_snap_m": r.get("ai_snap_m"),
        "ai_pti_kind": r.get("ai_pti_kind"),
        "ai_pti_name": r.get("ai_pti_name"),
        "ai_direct_m": r.get("ai_direct_m"),
        "ai_route_m": r.get("ai_route_m"),
        "ai_covered_ratio": r.get("ai_covered_ratio"),
        "ai_covered_m": r.get("ai_covered_m"),
        "ai_longest_exposed_m": r.get("ai_longest_exposed_m"),
        "ai_n_exposed_runs": r.get("ai_n_exposed_runs"),
        "ai_best_cov_ratio": r.get("ai_best_cov_ratio"),
        "ai_best_cov_route_m": r.get("ai_best_cov_route_m"),
        "ai_best_cov_kind": r.get("ai_best_cov_kind"),
        "ai_best_cov_pti": r.get("ai_best_cov_pti"),
        "ai_best_cov_longest_exposed_m": r.get("ai_best_cov_longest_exposed_m"),
        "ai_n_pti_candidates": r.get("ai_n_pti_candidates"),
        "ai_ro": r.get("ai_ro"),
    }
    _t = typ_by_id.get(r["school_id"])
    if _t:
        _b = _t["bus_ref"]
        p["ac_access"] = _t["access"]
        p["ac_walk_min"] = _t["walk_minutes"]
        p["ac_bus_stop"] = (_b.get("stop_name") or _b.get("stop_id"))
        p["ac_bus_route_m"] = _b.get("route_m")
        p["ac_bus_cov"] = _b.get("covered_ratio")
        p["ac_bus_gap_m"] = _b.get("longest_exposed_m")
        p["ac_bus_n_routes"] = _b.get("n_routes_at_stop")
        p["ac_bus_routes"] = _b.get("routes_at_stop")
        p["ac_tier"] = _t["priority_tier"]
    schools["features"].append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
        "properties": p,
    })
    summary.append({
        "school_id": r["school_id"],
        "name": r["name"],
        "name_tc": r.get("name_tc"),
        "district": r.get("district"),
        "type": r.get("type"),
        "lon": r["lon"], "lat": r["lat"],
        "best_kind": r.get("ai_best_cov_kind"),
        "best_pti": r.get("ai_best_cov_pti"),
        "best_route_m": r.get("ai_best_cov_route_m"),
        "best_cov": r.get("ai_best_cov_ratio"),
        "best_gap_m": r.get("ai_best_cov_longest_exposed_m"),
        "short_route_m": r.get("ai_route_m"),
        "short_cov": r.get("ai_covered_ratio"),
        "short_gap_m": r.get("ai_longest_exposed_m"),
        "n_cand": r.get("ai_n_pti_candidates"),
        "ro": r.get("ai_ro"),
    })
    if _t:
        summary[-1].update({
            "access": _t["access"],
            "walk_minutes": _t["walk_minutes"],
            "bus_stop": _t["bus_ref"].get("stop_name") or _t["bus_ref"].get("stop_id"),
            "bus_route_m": _t["bus_ref"].get("route_m"),
            "bus_cov": _t["bus_ref"].get("covered_ratio"),
            "bus_gap_m": _t["bus_ref"].get("longest_exposed_m"),
            "bus_n_routes": _t["bus_ref"].get("n_routes_at_stop"),
            "tier": _t["priority_tier"],
        })

# ---------------------------------------------------------------- app: MTR walks
# The worst-case scenario: bus and minibus service is out, so the student
# walks from the nearest MTR station exit.  These are the 164 walks.
mtr_walks = json.load(open(os.path.join(WORK, "mtr_walk_routes.geojson"), encoding="utf-8"))

# ---------------------------------------------------------------- app: routes
# Keep every route (both kinds) and key it by school_id.
app_routes = {"type": "FeatureCollection", "features": []}
for f in routes["features"]:
    pr = dict(f["properties"])
    pr["school_id"] = f["properties"].get("school_id")
    app_routes["features"].append({"type": "Feature",
                                   "geometry": f["geometry"],
                                   "properties": pr})

# ------------------------------------------- app: route options (three per school)
# nearest MTR exit / nearest bus-minibus stop / most shaded metres
ro_src = json.load(open(os.path.join(WORK, "route_options.geojson"), encoding="utf-8"))
app_ro = {"type": "FeatureCollection", "features": []}
for f in ro_src["features"]:
    pr = dict(f["properties"])
    pr["school_id"] = f["properties"].get("school_id")
    app_ro["features"].append({"type": "Feature",
                               "geometry": f["geometry"],
                               "properties": pr})
# THE MTR OPTION MUST COME FROM THE MTR WALK, ALWAYS.
#
# The app draws the worst-case walk as a purple dashed line from
# mtr_walks.geojson (mtr_walk_schools.py: every MTR exit in a 1 km
# buffer, shortest wins) and quotes its length in the map's key text.
# The school's panel must therefore show that same walk, or the line
# and the number beside it describe two different journeys.
#
# The stop-to-school pipeline also solves an MTR route, but with the
# candidate stops capped at 800 m straight-line from the school
# (PTI_SEARCH_M).  For 19 of the 164 schools that cap excludes the
# nearer exit the MTR script found, so the two disagree -- by up to
# 312 m at CARMEL ALISON LAM FOUNDATION SECONDARY SCHOOL.  So the
# option is REPLACED for every school, not just filled in for the 22
# that had no MTR route at all.
#
# The bus and minibus options are untouched: those are the stop-to-
# school question, and the cap is deliberate there.
sum_by_id = {s["school_id"]: s for s in summary}
sch_by_id = {f["properties"]["school_id"]: f["properties"] for f in schools["features"]}

# Drop every nearest_mtr option the stop-to-school pipeline produced.
dropped = [f for f in app_ro["features"]
           if f["properties"].get("ai_route_kind") == "nearest_mtr"]
app_ro["features"] = [f for f in app_ro["features"]
                       if f["properties"].get("ai_route_kind") != "nearest_mtr"]
print("nearest_mtr options replaced from the MTR walks: dropped", len(dropped))

mtr_fallback = 0
for f in mtr_walks["features"]:
    pw = f["properties"]
    sid = pw.get("school_id")
    if not sid:
        continue
    ratio = pw.get("covered_ratio") or 0.0
    route_m = pw.get("walk_m") or 0
    o = {"pti_kind": "mtr",
         "pti_name": (str(pw.get("station") or "") + " " + str(pw.get("exit") or "")).strip(),
         "ai_route_m": route_m, "ai_covered_m": round(route_m * ratio),
         "ai_covered_ratio": ratio, "ai_longest_exposed_m": pw.get("longest_exposed_m")}
    app_ro["features"].append({"type": "Feature", "geometry": f["geometry"],
                               "properties": {"school": pw.get("name"), "school_id": sid,
                                              "ai_route_kind": "nearest_mtr", **o}})
    if sid in sum_by_id and sum_by_id[sid].get("ro") is not None:
        sum_by_id[sid]["ro"]["nearest_mtr"] = o
    if sid in sch_by_id and sch_by_id[sid].get("ai_ro") is not None:
        sch_by_id[sid]["ai_ro"]["nearest_mtr"] = o
    mtr_fallback += 1
print("route-option nearest_mtr taken from the MTR walks:", mtr_fallback)

# ------------------------------------------- weighted shade metric (typology blend)
# Three routes per school: nearest MTR exit, nearest bus stop, nearest minibus.
# Weights depend on the school's access typology (the 15-minute rule):
#   MTR-dependent (walk to MTR <= 15 min):  MTR 70%, minibus 15%, bus 15%
#   bus/minibus-dependent:                  minibus 35%, bus 35%, MTR 30%
# Missing route kinds renormalise the remaining weights to sum 1.
# weighted shaded % = weighted shaded metres / weighted distance.
for s in summary:
    _ro = s.get("ro") or {}
    _dep = s.get("access") == "transit-dependent"
    if _dep:
        _base = {"nearest_minibus": 0.35, "nearest_bus": 0.35, "nearest_mtr": 0.30}
    else:
        _base = {"nearest_mtr": 0.70, "nearest_minibus": 0.15, "nearest_bus": 0.15}
    _have = {k: _ro[k] for k in _base if _ro.get(k)}
    if not _have:
        continue
    _sum = sum(_base[k] for k in _have)
    wd = ws = 0.0
    _wm = {}
    for k, o in _have.items():
        w = _base[k] / _sum
        _wm[k] = round(w, 3)
        wd += w * (o.get("ai_route_m") or 0)
        ws += w * (o.get("ai_covered_m") or 0)
    w = {"group": "bus-dependent" if _dep else "mtr-dependent",
         "weights": _wm,
         "route_m": round(wd, 1), "shaded_m": round(ws, 1),
         "shaded_ratio": round(ws / wd, 3) if wd else 0.0}
    s["w"] = w
    _pp = sch_by_id.get(s["school_id"])
    if _pp is not None:
        _pp["w"] = w

# ---------------------------------------------------------------- write app data
def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))


write_json(os.path.join(APPDATA, "schools.geojson"), schools)
write_json(os.path.join(APPDATA, "routes.geojson"), app_routes)
write_json(os.path.join(APPDATA, "stops.geojson"), pti)
write_json(os.path.join(APPDATA, "covered_paths.geojson"), covered)
write_json(os.path.join(APPDATA, "school_summary.json"), summary)
write_json(os.path.join(APPDATA, "mtr_walks.geojson"), mtr_walks)
write_json(os.path.join(APPDATA, "route_options.geojson"), app_ro)
print("app data: schools=%d routes=%d stops=%d covered=%d mtr_walks=%d route_options=%d" % (
    len(schools["features"]), len(app_routes["features"]),
    len(pti["features"]), len(covered["features"]),
    len(mtr_walks["features"]), len(app_ro["features"])))

# ------------------------------------------------- the map's own headline text
# Every figure the page states is DERIVED from the data written above.
# A hand-typed number in the page goes stale the moment the data is
# rebuilt, and a stale figure in a write-up reads as a finding.  So the
# page carries placeholders and this step fills them in from the files
# that were just written.
def derive_page_figures():
    import statistics as stx
    # the weighted metric: median weighted distance and shade
    rows = json.load(open(os.path.join(APPDATA, "school_summary.json"),
                           encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("schools", rows)
    wd = sorted(float(x["w"]["route_m"]) for x in rows if x.get("w"))
    ws = sorted(float(x["w"]["shaded_ratio"]) for x in rows if x.get("w"))
    # the MTR walk: median length and the median minutes in rain
    mrows = json.load(open(os.path.join(APPDATA, "mtr_walks.geojson"),
                            encoding="utf-8"))
    mrows = mrows.get("features", mrows)
    mv = sorted(float(f["properties"]["walk_m"]) for f in mrows
                if f["properties"].get("walk_m") is not None)
    mm = sorted(float(f["properties"]["walk_minutes"]) for f in mrows
                if f["properties"].get("walk_minutes") is not None)
    # the access typology: how many schools are walk-access to MTR
    wa = sum(1 for x in rows if x.get("access") == "walk-access")
    td = sum(1 for x in rows if x.get("access") == "transit-dependent")

    # The placeholder names in index.html, exactly.  They must match the
    # page character for character, so they are written here in the same
    # form the page uses: {NAME}.
    figs = {
        "N_SCHOOLS": str(len(rows)),
        "N_WALK": str(wa),
        "N_TRANSIT": str(td),
        "W_DIST": "%d m" % round(stx.median(wd)),
        "W_SHADE": "%d%%" % round(stx.median(ws) * 100),
        "MTR_MEDIAN": "%d m" % round(stx.median(mv)),
        "MTR_MINUTES": "%d min" % round(stx.median(mm)),
    }
    idx = os.path.join(REPO, "apps/kowloon-covered-walkways/index.html")
    if not os.path.exists(idx):
        print("index.html not found; page figures left as placeholders")
        return figs
    html = open(idx, encoding="utf-8").read()
    for k, v in figs.items():
        html = html.replace("{%s}" % k, v)
    open(idx, "w", encoding="utf-8").write(html)
    left = [k for k in figs if "{%s}" % k in html]
    print("page figures derived:", ", ".join("%s=%s" % kv
                                            for kv in sorted(figs.items())))
    if left:
        print("  WARNING placeholders still present:", left)
    return figs


derive_page_figures()

# ------------------------------------------------- published site data (gz)
def copy_gz(src, dst):
    # mtime=0 so the gzip header carries no timestamp: otherwise every
    # rebuild produces a byte-different file with identical content, and
    # the repository churns on files that never actually changed.
    with open(src, "rb") as fi:
        with gzip.GzipFile(dst, "wb", compresslevel=9, mtime=0) as fo:
            shutil.copyfileobj(fi, fo)


copy_gz(os.path.join(WORK, "peninsula_route_geometry.geojson"),
        os.path.join(SITEDATA, "peninsula_route_geometry.geojson.gz"))
copy_gz(os.path.join(WORK, "mtr_walk_routes.geojson"),
        os.path.join(SITEDATA, "mtr_walk_routes.geojson.gz"))
copy_gz(os.path.join(WORK, "peninsula_covered_paths.geojson"),
        os.path.join(SITEDATA, "peninsula_covered_paths.geojson.gz"))
copy_gz(os.path.join(WORK, "peninsula_pti.geojson"),
        os.path.join(SITEDATA, "peninsula_pti.geojson.gz"))
# the worst-case MTR walk, per school, as a flat table and as lines
shutil.copyfile(os.path.join(WORK, "mtr_walk_schools.json"),
                os.path.join(SITEDATA, "mtr_walk_schools.json"))
shutil.copyfile(os.path.join(WORK, "mtr_walk_routes.geojson"),
                os.path.join(SITEDATA, "mtr_walk_routes.geojson"))

# The published copy of the school metrics drops the nested per-stop detail:
# it is up to 279 candidate stops per school and turns a 130 kB file into 5.3 MB, for
# data the web map does not use.  The full version lives in the vault and in
# the geodatabase's Route_Candidates class.
PUBLIC_FIELDS = [
    "school_id", "name", "name_tc", "district", "type", "lon", "lat",
    "address", "sid", "dataset_id",
    "ai_routable", "ai_snap_m", "ai_pti_kind", "ai_pti_name", "ai_direct_m",
    "ai_route_m", "ai_covered_ratio", "ai_covered_m", "ai_longest_exposed_m",
    "ai_n_exposed_runs", "ai_unclassified_m", "ai_by_type",
    "ai_best_cov_ratio", "ai_best_cov_route_m", "ai_best_cov_kind",
    "ai_best_cov_pti", "ai_best_cov_longest_exposed_m",
    "ai_n_pti_candidates", "ai_n_pti_reachable",
    "ai_best_covered_ratio", "ai_worst_covered_ratio",
]
public = [{k: r.get(k) for k in PUBLIC_FIELDS} for r in raw]
write_json(os.path.join(SITEDATA, "peninsula_routes_schools.json"), public)
print("published school metrics: %d records, %d bytes (nested per-stop detail dropped)" % (
    len(public), os.path.getsize(os.path.join(SITEDATA, "peninsula_routes_schools.json"))))

# ------------------------------------------------------- flat CSV for Excel
COLS = ["school_id", "name", "name_tc", "district", "type", "lon", "lat",
        "ai_route_m", "ai_direct_m", "ai_covered_ratio", "ai_covered_m",
        "ai_longest_exposed_m", "ai_n_exposed_runs",
        "ai_best_cov_route_m", "ai_best_cov_ratio", "ai_best_cov_kind",
        "ai_best_cov_pti", "ai_best_cov_longest_exposed_m",
        "ai_n_pti_candidates", "ai_snap_m"]
with open(os.path.join(SITEDATA, "Schools_RouteMetrics.csv"), "w",
          newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
    w.writeheader()
    for r in raw:
        w.writerow(r)
print("site data: written to", SITEDATA)

# ------------------------------------------------------------ ArcGIS geodatabase
# Build it from the SAME work/ outputs, in HK 1980 Grid (EPSG:2326).
gdb_dir = os.path.join(VAULT, "arcgis", "Kowloon_Covered_Walkways.gdb")
if os.path.exists(gdb_dir):
    shutil.rmtree(gdb_dir)

env = dict(os.environ)
env["GDAL_DATA"] = os.path.join(PROJDATA, "gdal")
env["PROJ_DATA"] = PROJDATA
env["PROJ_LIB"] = PROJDATA


def ogr(src, layer, geom_type):
    cmd = [OGR2OGR, "-f", "OpenFileGDB", gdb_dir, src, "-nln", layer,
           "-nlt", geom_type, "-t_srs", "EPSG:2326", "-overwrite",
           "-lco", "GEOMETRY_NAME=Shape"]
    if layer == "Route_Candidates":
        cmd += ["-lco", "TARGET_ARCGIS_VERSION=ARCGIS_PRO_3_2_OR_LATER"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print("FAILED", layer, r.stderr[-800:])
        sys.exit(1)
    print("  gdb layer:", layer)


# Flatten the nested per-stop detail into its own feature class.
cand = {"type": "FeatureCollection", "features": []}
for r in raw:
    for d in r.get("ai_pti_detail", []):
        if not d.get("ai_reachable"):
            continue
        cand["features"].append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {
                "school_id": r["school_id"], "school": r["name"],
                "district": r.get("district"), "school_type": r.get("type"),
                "pti_kind": d.get("kind"), "pti_name": d.get("name"),
                "ai_direct_m": d.get("ai_direct_m"),
                "ai_route_m": d.get("ai_route_m"),
                "ai_covered_ratio": d.get("ai_covered_ratio"),
                "ai_longest_exposed_m": d.get("ai_longest_exposed_m"),
            }})
tmp_cand = os.path.join(WORK, "_cand_tmp.geojson")
write_json(tmp_cand, cand)

# The school metrics are a bare JSON array with lon/lat but no geometry, so
# give ogr2ogr a real point layer to work from.
tmp_sch = os.path.join(WORK, "_sch_tmp.geojson")
write_json(tmp_sch, schools)

# Points for the candidate stops need real coordinates — join on stop name.
stop_xy = {}
for f in pti["features"]:
    stop_xy[(f["properties"]["ai_kind"], f["properties"]["ai_name"])] = \
        f["geometry"]["coordinates"]
n_fix = 0
for f in cand["features"]:
    k = (f["properties"]["pti_kind"], f["properties"]["pti_name"])
    if k in stop_xy:
        f["geometry"]["coordinates"] = stop_xy[k]
        n_fix += 1
write_json(tmp_cand, cand)
print("  candidate stops with coordinates: %d of %d" % (n_fix, len(cand["features"])))

ogr(tmp_sch, "Schools_RouteMetrics", "POINT")
ogr(os.path.join(WORK, "peninsula_route_geometry.geojson"), "Routes_To_School", "MULTILINESTRING")
ogr(os.path.join(WORK, "peninsula_covered_paths.geojson"), "Covered_Paths", "MULTILINESTRING")
ogr(os.path.join(WORK, "peninsula_pti.geojson"), "Stops_PTI", "POINT")
ogr(tmp_cand, "Route_Candidates", "POINT")
os.remove(tmp_cand)
os.remove(tmp_sch)

gdb_zip = os.path.join(SITEDATA, "Kowloon_Covered_Walkways.gdb.zip")
if os.path.exists(gdb_zip):
    os.remove(gdb_zip)
# The zip stores each member's mtime, so a rebuild produces a
# byte-different archive with identical content.  Touch every member to
# a fixed date first, so the archive is reproducible and the repository
# only churns when the data actually changes.
subprocess.run(["/bin/bash", "-lc",
                f"find '{os.path.dirname(gdb_dir)}' -exec touch -t "
                f"202601010000 {{}} +"], check=False)
subprocess.run(["/bin/bash", "-lc",
                f"cd '{os.path.dirname(gdb_dir)}' && zip -qr -X '{gdb_zip}' "
                f"'{os.path.basename(gdb_dir)}'"], check=True)
shutil.copyfile(gdb_zip, os.path.join(VAULT, "arcgis",
                                      "Kowloon_Covered_Walkways.gdb.zip"))
print("geodatabase:", gdb_zip, os.path.getsize(gdb_zip), "bytes")
print("done")
