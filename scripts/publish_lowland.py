#!/usr/bin/env python3
"""
Publish the Hong Kong low-lying land (< 5 m) layer into NPLGIS.

The analysis stays in EPSG:2326 (HK1980 Grid, metres) because that is where
the areas are metres squared. The CONVERSION TO LON/LAT HAPPENS AT THE
SHIPPING BOUNDARY - GeoJSON is RFC 7946, so it carries lon/lat in decimal
degrees and has no `crs` member.

What this ships:
  assets/data/lowland/hk_lowland_under5m.geojson.gz   the 106 patches
  assets/data/lowland/hk_lowland_under5m_all_patches.geojson.gz  all 9,060
  assets/data/lowland/hk_lowland_under5m.tif             the binary raster
  assets/data/lowland/hk_lowland_under5m_patches.csv      the table
  assets/maps/lowland/HK_lowland_under5m_map.png          the map

The source files live in the working folder:
  $GIS_DATA_DIR/HK Flood Causes/out/

Run:  python3 publish_lowland.py
"""
import csv
import gzip
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "landslide"))

from geojson_wgs84 import (  # noqa: E402
    check_rfc7946,
    collection_area_km2,
    to_wgs84_collection,
)

import numpy as np  # noqa: E402
import rasterio  # noqa: E402

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
SRC = os.path.join(GIS_DATA, "HK Flood Causes", "out")

def _find_repo_root():
    """Walk up from this script until the repo root is found.

    The repo is recognised by its assets/data directory, so this works for a
    script in scripts/ and for one in scripts/<project>/ alike.
    """
    d = HERE
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "assets", "data")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


REPO = os.environ.get("NPLGIS_REPO") or _find_repo_root()
if not REPO:
    raise SystemExit("cannot find the repo root")

DEST = os.path.join(REPO, "assets", "data", "lowland")
MAPS = os.path.join(REPO, "assets", "maps", "lowland")


def log(msg):
    print(msg, flush=True)


def _find_repo_root():
    """Walk up from this script until the repo root is found.

    The repo is recognised by its assets/data directory, so this works for a
    script in scripts/ and for one in scripts/<project>/ alike.
    """
    d = HERE
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "assets", "data")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def write_gz(path, collection):
    """Write a GeoJSON collection gzipped, with the RFC 7946 check first."""
    check_rfc7946(collection, os.path.basename(path))
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(collection, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return os.path.getsize(path)


def main():
    os.makedirs(DEST, exist_ok=True)
    os.makedirs(MAPS, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. the cleaned 106 patches
    # ------------------------------------------------------------------
    src = os.path.join(SRC, "hk_lowland_under5m.geojson")
    with open(src, encoding="utf-8") as fh:
        fc = json.load(fh)
    log(f"read {src}")
    log(f"  {len(fc['features'])} features, "
        f"source crs {fc.get('metadata', {}).get('crs')}")

    # the source is EPSG:2326 metres - it MUST be reprojected, not shipped
    # as-is, or a reader following RFC 7946 drops Hong Kong off the map
    area_before = collection_area_km2(fc, already_2326=True)
    wgs = to_wgs84_collection(fc)
    wgs["name"] = "Hong Kong land below 5 m elevation"
    wgs["metadata"] = {
        "title": "Hong Kong land below 5 m elevation",
        "source": "LandsD DTM 5 m (landsd_rcd_1638158088368_93806)",
        "threshold_m": 5.0,
        "crs": "EPSG:4326 (GeoJSON is always lon/lat, RFC 7946)",
        "land_mask": "OSM Hong Kong boundary relation 20044132 / 913110 "
                     "AND the DTM's positive elevation",
        "note": "Patches >= 0.05 km2. The sea is coded 0 m in the DTM and "
                "flat land is also 0 m, so a land mask is essential; without "
                "it the query returns the whole ocean.",
    }
    area_after = collection_area_km2(wgs, already_2326=False)
    log(f"  area measured in EPSG:2326 before {area_before:.4f} km2, "
        f"after reprojection {area_after:.4f} km2, "
        f"difference {abs(area_before - area_after):.6f} km2")
    assert abs(area_before - area_after) < 0.01, "the reprojection changed the area"

    rel = os.path.join("assets", "data", "lowland",
                       "hk_lowland_under5m.geojson.gz")
    size = write_gz(os.path.join(REPO, rel), wgs)
    log(f"  wrote {rel} ({size:,} bytes)")

    # ------------------------------------------------------------------
    # 2. every patch, including the slivers
    # ------------------------------------------------------------------
    src_all = os.path.join(SRC, "hk_lowland_under5m_all_patches.geojson")
    with open(src_all, encoding="utf-8") as fh:
        fc_all = json.load(fh)
    all_wgs = to_wgs84_collection(fc_all)
    all_wgs["name"] = "Hong Kong land below 5 m elevation - every patch"
    all_wgs["metadata"] = dict(wgs["metadata"])
    all_wgs["metadata"]["note"] = (
        "Every contiguous patch, including the slivers under 0.05 km2 that "
        "the cleaned layer drops. The sea is coded 0 m in the DTM and flat "
        "land is also 0 m, so a land mask is essential.")
    rel_all = os.path.join("assets", "data", "lowland",
                           "hk_lowland_under5m_all_patches.geojson.gz")
    size_all = write_gz(os.path.join(REPO, rel_all), all_wgs)
    log(f"  wrote {rel_all} ({size_all:,} bytes, {len(fc_all['features']):,} features)")

    # ------------------------------------------------------------------
    # 3. the raster - copied as-is, it already carries EPSG:2326
    # ------------------------------------------------------------------
    rel_tif = os.path.join("assets", "data", "lowland",
                           "hk_lowland_under5m.tif")
    shutil.copy2(os.path.join(SRC, "hk_lowland_under5m.tif"),
                 os.path.join(REPO, rel_tif))
    with rasterio.open(os.path.join(REPO, rel_tif)) as ds:
        arr = ds.read(1)
        assert str(ds.crs) == "EPSG:2326", ds.crs
        assert set(np.unique(arr).tolist()) <= {0, 1}
        km2 = float(arr.sum()) * 25 / 1e6
        log(f"  wrote {rel_tif} ({ds.width} x {ds.height}, {ds.crs}, "
            f"{km2:.2f} km2 of lowland)")
        assert abs(km2 - 60.58) < 0.05, f"the raster area moved: {km2}"

    # ------------------------------------------------------------------
    # 4. the table
    # ------------------------------------------------------------------
    rel_csv = os.path.join("assets", "data", "lowland",
                           "hk_lowland_under5m_patches.csv")
    shutil.copy2(os.path.join(SRC, "hk_lowland_under5m_patches.csv"),
                 os.path.join(REPO, rel_csv))
    with open(os.path.join(REPO, rel_csv), encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    log(f"  wrote {rel_csv} ({len(rows)} rows)")

    # ------------------------------------------------------------------
    # 5. the map
    # ------------------------------------------------------------------
    rel_png = os.path.join("assets", "maps", "lowland",
                           "HK_lowland_under5m_map.png")
    shutil.copy2(os.path.join(SRC, "hk_lowland_under5m_map.png"),
                 os.path.join(REPO, rel_png))
    log(f"  wrote {rel_png} "
        f"({os.path.getsize(os.path.join(REPO, rel_png)):,} bytes)")

    # ------------------------------------------------------------------
    # 6. the note
    # ------------------------------------------------------------------
    rel_note = "notes/lowland-under5m — NOTES.md"
    shutil.copy2(os.path.join(SRC, "README_lowland.md"),
                 os.path.join(REPO, rel_note))
    log(f"  wrote {rel_note}")

    # ------------------------------------------------------------------
    # 7. verify by reading everything back
    # ------------------------------------------------------------------
    log("")
    log("=== verify by reading the shipped files back ===")
    for f in (rel, rel_all, rel_tif, rel_csv, rel_png, rel_note):
        p = os.path.join(REPO, f)
        assert os.path.exists(p), f"missing {f}"
        log(f"  {f}  {os.path.getsize(p):,} bytes")

    for f, want in ((rel, 106), (rel_all, 9060)):
        with gzip.open(os.path.join(REPO, f), "rt", encoding="utf-8") as fh:
            back = json.load(fh)
        assert back["type"] == "FeatureCollection"
        assert len(back["features"]) == want, f"{f}: {len(back['features'])} != {want}"
        assert "crs" not in back, f"{f} carries a crs member"
        for ft in back["features"]:
            assert ft["type"] == "Feature"
            assert "properties" in ft and "geometry" in ft
            assert "coordinates" in ft["geometry"]
        # the first coordinate must be a lon/lat pair
        c = back["features"][0]["geometry"]["coordinates"]
        while isinstance(c[0], (list, tuple)):
            c = c[0]
        assert -180 <= c[0] <= 180 and -90 <= c[1] <= 90, c
        log(f"  {f}: {len(back['features']):,} features, no crs member, "
            f"lon/lat confirmed")

    log("")
    log("published. now run update_manifest_lowland.py")


if __name__ == "__main__":
    main()
