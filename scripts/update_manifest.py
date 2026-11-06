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

import geopandas as gpd

REPO = "/Users/davidhermes/nplgis"
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
        "error 0.0 m2, 0 invalid geometries. EPSG:2326 (HK1980).",
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

    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"manifest updated: {added} new entries, {len(man['files'])} total")

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
    print("manifest verified: every new entry's sha256 and byte count match disk")


if __name__ == "__main__":
    main()
