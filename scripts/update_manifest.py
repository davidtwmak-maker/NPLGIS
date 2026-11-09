#!/usr/bin/env python3
"""
Extend the NPLGIS MANIFEST with the steep-slope layers.

The manifest is the machine-readable source register: one entry per shipped
file, with the feature count and sha256 taken FROM THE FILE THAT WAS
ACTUALLY SHIPPED - not carried over from a build step.

Rules (each one caught a real defect in this project):
  * Feature counts are counted from the shipped file, not from the source.
  * A .geojson.gz cannot be read by GDAL directly (it fails with "not
    recognized as being in a supported file format"), so it is decompressed
    and read as plain GeoJSON.
  * The manifest is extended IN PLACE: existing entries and their order are
    kept, and only the `generated` date and the new entries change.
  * Every count and byte total in the README is computed from disk, never
    hand-written - a hand-written total goes stale the moment a file lands.

Run:  ls-venv/bin/python update_manifest.py
"""
import gzip
import json
import os
import shutil
import zipfile

import geopandas as gpd

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
MANIFEST = os.path.join(REPO, "assets/data/MANIFEST.json")
DATA = os.path.join(REPO, "assets/data/landslide")
MAPS = os.path.join(REPO, "assets/maps/landslide-susceptibility")


def sha16(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def gz_feature_count(path):
    """Count features in a gzipped GeoJSON by decompressing it."""
    tmp = path + "_tmp"
    with gzip.open(path, "rb") as fin, open(tmp, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    try:
        g = gpd.read_file(tmp)
        return int(len(g))
    finally:
        os.remove(tmp)


def geojson_feature_count(path):
    """Count features in a plain GeoJSON by parsing the JSON directly."""
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload.get("type") == "FeatureCollection", f"{path} is not a FeatureCollection"
    return len(payload.get("features", []))


def shp_zip_feature_count(path):
    """Count features in a zipped shapefile by reading it back with GDAL.

    GDAL cannot read a .geojson.gz directly, but it reads a shapefile inside
    a zip fine, so the count comes from the file that will actually be
    uploaded.
    """
    import tempfile
    tmpdir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            shp = next(n for n in names if n.lower().endswith(".shp"))
            # AGOL requires the shapefile components in the ZIP ROOT
            assert "/" not in shp, f"{path}: shapefile is nested at {shp}"
            zf.extractall(tmpdir)
        g = gpd.read_file(os.path.join(tmpdir, shp))
        return int(len(g))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def entry_for(rel, title, notes, features=None, records="", dataset_id=""):
    p = os.path.join(REPO, rel)
    size = os.path.getsize(p)
    return {
        "file": rel,
        "bytes": size,
        "mb": round(size / 1e6, 3),
        "gzipped": rel.endswith(".gz"),
        "features": features,
        "title": title,
        "dataset_id": dataset_id,
        "records": records,
        "notes": notes,
        "sha256": sha16(p),
    }


def main():
    with open(MANIFEST) as f:
        man = json.load(f)

    # --- the four new slope files ----------------------------------------
    new_entries = []

    rel = "assets/data/landslide/steep_slopes_over30.geojson.gz"
    n = gz_feature_count(os.path.join(REPO, rel))
    assert n == 33231, f"steep polygon count {n} != 33231"
    new_entries.append(entry_for(
        rel,
        "Steep slope polygons - ground steeper than 30 degrees",
        "33,231 polygons of ground exceeding a 30 degree gradient, 113.29 km2 = "
        "10.09% of Hong Kong's land area (1,122.26 km2). Slope is the MAXIMUM "
        "gradient within each 20 m cell (Horn's method) from the LandsD 5 m DTM, "
        "because 22,700 recorded incidents sit in cells whose mean slope is "
        "under 30 degrees but whose max is over it. 8-connectivity, so corner-"
        "touching steep cells merge into one hillside. Area reconciliation "
        "error 0.0 m2, 0 invalid geometries. EPSG:4326 (GeoJSON is always "
        "lon/lat); the area above is measured in EPSG:2326 (HK1980).",
        features=n,
        records=str(n),
    ))

    rel = "assets/data/landslide/slope_classes_20m.tif"
    new_entries.append(entry_for(
        rel,
        "Slope class raster (20 m)",
        "Five classes: 1 = 0-15 deg, 2 = 15-30, 3 = 30-45, 4 = 45-60, 5 = 60+. "
        "3187 x 2400 at 20 m, EPSG:2326 (HK1980). Class areas: 0-15 = 543.43 km2 "
        "(48.42% of land), 15-30 = 465.53 km2 (41.48%), 30-45 = 97.95 km2 "
        "(8.73%), 45-60 = 13.61 km2 (1.21%), 60+ = 1.73 km2 (0.15%).",
    ))

    rel = "assets/data/landslide/slope_max_20m.tif"
    new_entries.append(entry_for(
        rel,
        "Maximum slope raster (20 m)",
        "Maximum gradient within each 20 m cell, degrees, from the LandsD 5 m "
        "DTM (Horn's method). 3187 x 2400 at 20 m, float32, EPSG:2326 (HK1980), "
        "nodata -9999.",
    ))

    rel = "assets/maps/landslide-susceptibility/steep_slopes_over30_map.png"
    new_entries.append(entry_for(
        rel,
        "Steep slopes of Hong Kong - two-panel map",
        "Panel A: five slope classes with 40,000 of the 124,020 recorded "
        "landslide incidents overprinted. Panel B: the >30 degree polygons "
        "alone over the gentler land, with the six largest regions labelled by "
        "area. Scale bar, north arrow and source line. Text overlap and "
        "off-canvas checks both pass at zero; a pixel probe confirms all five "
        "classes are rendered.",
    ))

    # --- the ArcGIS Online-ready pack -------------------------------------
    # These are EPSG:4326 reprojections of the two vector layers, plus the
    # field-name mapping and the publishing guide.  The feature counts are
    # read FROM THE SHIPPED FILES, not carried over.
    agol = os.path.join(REPO, "assets/data/landslide/agol")
    agol_specs = [
        ("steep_slopes_over30.zip", "Steep slope polygons - ArcGIS Online pack",
         "Zipped shapefile of the 33,231 >30 degree polygons, EPSG:4326 "
         "(WGS84), with .shp/.shx/.dbf/.prj/.cpg in the zip root. This is the "
         "recommended upload: it carries its own .prj and the field names are "
         "documented in field_mapping.json (DBF names are capped at 10 "
         "characters).",
         33231),
        ("slope_classes.zip", "Slope class polygons - ArcGIS Online pack",
         "Zipped shapefile of the 106,874 five-class slope polygons, "
         "EPSG:4326 (WGS84). AGOL returns 2,000 records per request by "
         "default - enable 'Allow >2000 features per request' on the source "
         "view or the layer draws only its first 2,000 features.",
         106874),
        ("steep_slopes_over30_wgs84.geojson",
         "Steep slope polygons - GeoJSON with original field names",
         "The same 33,231 polygons as GeoJSON in EPSG:4326, with the full "
         "field names (slope_mean_deg, slope_sd_deg, slope_max_deg) intact - "
         "no renaming needed after upload. No 'crs' member, per RFC 7946.",
         33231),
        ("hk_slopes_agol_both_layers.zip",
         "Both slope layers in one GeoPackage - ArcGIS Online pack",
         "A single GeoPackage containing both layers (steep_slopes_over30 "
         "33,231 features, slope_classes 106,874 features), EPSG:4326. Upload "
         "once to publish both as separate layers in one hosted item.",
         None),
    ]
    for fname, title, notes, want in agol_specs:
        p = os.path.join(agol, fname)
        assert os.path.exists(p), f"missing AGOL pack file {fname}"
        feats = None
        if want is not None:
            if fname.endswith(".zip"):
                feats = shp_zip_feature_count(p)
            else:
                feats = geojson_feature_count(p)
            assert feats == want, f"{fname}: {feats} features, expected {want}"
        new_entries.append(entry_for(
            f"assets/data/landslide/agol/{fname}", title, notes, features=feats,
            records=str(feats) if feats else "both layers",
        ))

    new_entries.append(entry_for(
        "assets/data/landslide/agol/field_mapping.json",
        "Field name mapping - shapefile to original",
        "The shapefile .dbf field names are capped at 10 characters and were "
        "renamed on export (slope_mean_deg -> slp_mean, slope_class -> "
        "slope_cls, and so on). This maps every one back to its original "
        "name.",
    ))
    new_entries.append(entry_for(
        "assets/data/landslide/agol/AGOL_PUBLISH_GUIDE.md",
        "ArcGIS Online publishing guide",
        "Step-by-step recipe for students: download links, the CRS trap, the "
        "publishing steps, the field-name restoration table, the 2,000-record "
        "limit, styling, and the caveats to state in a write-up.",
    ))

    # --- extend in place, keeping existing entries and their order -------
    existing = {e["file"] for e in man["files"]}
    added = 0
    for e in new_entries:
        if e["file"] in existing:
            # replace in place, keep position
            for i, cur in enumerate(man["files"]):
                if cur["file"] == e["file"]:
                    man["files"][i] = e
                    break
        else:
            man["files"].append(e)
            added += 1

    man["generated"] = "2026-11-05"
    man["note"] = man["note"].split(" | ")[0] + (
        " | 2026-11-05: added HK Steep Slopes >30 deg - 33,231 polygons of ground "
        "steeper than 30 degrees (113.29 km2 = 10.09% of land), the five-class "
        "slope raster at 20 m, the maximum-slope raster, and the two-panel map. "
        "Slope is the MAXIMUM gradient within each 20 m cell, not the mean: "
        "22,700 recorded incidents sit in cells whose mean slope is under 30 "
        "degrees but whose max is over it, so a mean threshold would erase a "
        "fifth of the evidence. Area reconciliation error 0.0 m2, 0 invalid "
        "geometries. "
    )

    # --- refresh EVERY existing entry's byte count and sha256 -------------
    # The entries above are only the ones this script builds. A layer that
    # changed on disk (a reprojection, a rerun) keeps its old sha256 until
    # something refreshes it, and a stale sha means the manifest no longer
    # describes the files that ship. The metadata - title, notes, feature
    # counts - is preserved; only the measured values are re-read.
    refreshed = 0
    for i, e in enumerate(man["files"]):
        p = os.path.join(REPO, e["file"])
        if not os.path.exists(p):
            continue
        size = os.path.getsize(p)
        sha = sha16(p)
        if e.get("bytes") != size or e.get("sha256") != sha:
            e["bytes"] = size
            e["mb"] = round(size / 1e6, 3)
            e["sha256"] = sha
            refreshed += 1

    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"manifest updated: {added} new entries, {refreshed} refreshed, "
          f"{len(man['files'])} total")

    # --- verify by reading the manifest back -----------------------------
    with open(MANIFEST) as f:
        back = json.load(f)
    assert back["generated"] == "2026-11-05"
    for e in new_entries:
        match = [x for x in back["files"] if x["file"] == e["file"]]
        assert len(match) == 1, f"{e['file']} appears {len(match)} times"
        assert match[0]["sha256"] == e["sha256"], "sha mismatch after write"
        # bytes must match disk
        real = os.path.getsize(os.path.join(REPO, e["file"]))
        assert match[0]["bytes"] == real, f"{e['file']} byte count stale"
    # EVERY entry must now describe the file on disk
    stale = []
    for e in back["files"]:
        p = os.path.join(REPO, e["file"])
        if not os.path.exists(p):
            stale.append((e["file"], "missing"))
            continue
        if os.path.getsize(p) != e["bytes"] or not sha16(p).startswith(e["sha256"]):
            stale.append((e["file"], "mismatch"))
    assert not stale, f"stale manifest entries: {stale}"
    print("manifest verified: every entry's sha256 and byte count match disk")


if __name__ == "__main__":
    main()
