#!/usr/bin/env python3
"""
Package the Hong Kong low-lying land (< 5 m) deliverables for delivery.

Copies the files to the SSD, builds a ZIP under the Telegram bot's 50 MB
limit, and verifies the ZIP by extracting it to a scratch folder and
re-reading every file.

Run:  python3 package_lowland.py
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import zipfile

import numpy as np
import rasterio
import tempfile

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SSD = os.environ.get("HK_LOWLAND_SSD",
                    os.path.join(GIS_DATA, "HK Low-Lying Land under 5m"))
SCRATCH = os.environ.get("HERMES_SCRATCH",
                       os.path.join(tempfile.gettempdir(), "hermes-scratch"))

FILES = [
    "hk_lowland_under5m.geojson",
    "hk_lowland_under5m.tif",
    "hk_lowland_under5m_map.png",
    "hk_lowland_under5m_patches.csv",
    "hk_lowland_under5m_all_patches.geojson",
    "README_lowland.md",
]

# the scripts that rebuild it all
SCRIPTS = [
    "fetch_osm_coastline_api.py",
    "assemble_osm_coastline.py",
    "build_land_mask_osm_hk.py",
    "build_lowland_deliverables.py",
    "make_lowland_map.py",
]


def main():
    os.makedirs(SSD, exist_ok=True)
    os.makedirs(os.path.join(SSD, "scripts"), exist_ok=True)

    for f in FILES:
        src = os.path.join(OUT, f)
        if not os.path.exists(src):
            raise SystemExit(f"missing {src}")
        shutil.copy2(src, os.path.join(SSD, f))
    for s in SCRIPTS:
        src = os.path.join(HERE, s)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(SSD, "scripts", s))

    # remove AppleDouble files - they break some Windows unzip tools
    removed = 0
    for root, dirs, files in os.walk(SSD):
        for f in files:
            if f.startswith("._"):
                os.remove(os.path.join(root, f))
                removed += 1
    print(f"copied to {SSD}; removed {removed} AppleDouble files")

    # ---- verify the copies
    print()
    print("=== verify the copies on the SSD ===")
    for f in FILES:
        p = os.path.join(SSD, f)
        print(f"  {f:<42} {os.path.getsize(p):>12,} bytes")

    with rasterio.open(os.path.join(SSD, "hk_lowland_under5m.tif")) as ds:
        a = ds.read(1)
        assert str(ds.crs) == "EPSG:2326", ds.crs
        assert ds.width == 12751 and ds.height == 9601
        assert set(np.unique(a).tolist()) <= {0, 1}
        print(f"  the raster: {ds.width} x {ds.height}, {ds.crs}, "
              f"{int(a.sum()):,} lowland cells = {a.sum()*25/1e6:.2f} km2")

    g = json.load(open(os.path.join(SSD, "hk_lowland_under5m.geojson")))
    assert g["type"] == "FeatureCollection"
    print(f"  the GeoJSON: {len(g['features'])} features, "
          f"{sum(f['properties']['area_km2'] for f in g['features']):.2f} km2")

    with open(os.path.join(SSD, "hk_lowland_under5m_patches.csv")) as f:
        rows = list(csv.DictReader(f))
    print(f"  the CSV: {len(rows)} rows")

    # ---- build the zip
    zpath = os.path.join(OUT, "HK_Low_Lying_Land_under_5m.zip")
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in FILES:
            z.write(os.path.join(SSD, f), f)
        for s in SCRIPTS:
            p = os.path.join(SSD, "scripts", s)
            if os.path.exists(p):
                z.write(p, f"scripts/{s}")
    size = os.path.getsize(zpath)
    print()
    print(f"=== {os.path.basename(zpath)}: {size:,} bytes "
          f"({size/1e6:.1f} MB) ===")
    if size > 50 * 1024 * 1024:
        raise SystemExit("the ZIP exceeds the Telegram 50 MB limit")

    # ---- round-trip: extract and re-read
    testdir = os.path.join(SCRATCH, "_ziptest")
    shutil.rmtree(testdir, ignore_errors=True)
    os.makedirs(testdir)
    with zipfile.ZipFile(zpath) as z:
        bad = z.testzip()
        assert bad is None, f"corrupt member {bad}"
        names = z.namelist()
        z.extractall(testdir)
    print(f"  extracted {len(names)} members OK")

    with rasterio.open(os.path.join(testdir, "hk_lowland_under5m.tif")) as ds:
        a = ds.read(1)
        assert str(ds.crs) == "EPSG:2326"
        assert a.sum() == 2423036, int(a.sum())
        print(f"  the extracted raster: {ds.crs}, {int(a.sum()):,} cells OK")
    g = json.load(open(os.path.join(testdir, "hk_lowland_under5m.geojson")))
    assert len(g["features"]) == 106, len(g["features"])
    print(f"  the extracted GeoJSON: {len(g['features'])} features OK")
    with open(os.path.join(testdir, "hk_lowland_under5m_patches.csv")) as f:
        assert len(list(csv.DictReader(f))) == 106
    print(f"  the extracted CSV: 106 rows OK")
    png = os.path.join(testdir, "hk_lowland_under5m_map.png")
    assert os.path.getsize(png) > 100_000
    print(f"  the extracted PNG: {os.path.getsize(png):,} bytes OK")
    readme = open(os.path.join(testdir, "README_lowland.md")).read()
    assert "60.6 km" in readme
    print(f"  the extracted README: {len(readme):,} chars OK")

    shutil.rmtree(testdir, ignore_errors=True)
    print("\nALL CHECKS PASSED")
    return zpath


if __name__ == "__main__":
    main()
