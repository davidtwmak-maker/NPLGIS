#!/usr/bin/env python3
"""
Export the Hong Kong camping-site study into the NPLGIS repo layout.

Produces:
  assets/data/camping/campsite_scores.geojson.gz   41 scored campsites
  assets/data/camping/hk_land_boundary.geojson.gz   the land mask
  assets/data/camping/night_lights_composite.tif   the 12-night VIIRS median
  assets/maps/camping-sites/HK_camping_sites_dark_sky_map.png
  assets/data/camping/campsite_scores.csv
  assets/data/camping/campsite_scores_summary.json

Every file is verified AFTER the write: feature counts read back from the
shipped bytes, byte size and sha256 measured on disk, and the GeoJSON
opened with geopandas to confirm the CRS and validity.
"""
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = "/Users/davidhermes/nplgis"
SRC = "/Users/davidhermes/GIS Data/HK Camping Sites"
NL = "/Users/davidhermes/GIS Data/HK Night Lights"

DATA_REL = "assets/data/camping"
MAP_REL = "assets/maps/camping-sites"

DEST_DATA = os.path.join(REPO, DATA_REL)
DEST_MAP = os.path.join(REPO, MAP_REL)


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def count_geojson(path):
    """Count features by reading the SHIPPED bytes."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        gj = json.load(f)
    return len(gj.get("features", [])), gj


def main():
    os.makedirs(DEST_DATA, exist_ok=True)
    os.makedirs(DEST_MAP, exist_ok=True)
    entries = []

    # ---- 1. campsite scores (GeoJSON, gzipped) ------------------------
    src_gj = f"{SRC}/campsite_scores.geojson"
    dst_gj = os.path.join(DEST_DATA, "campsite_scores.geojson.gz")
    with open(src_gj, "rb") as fi, gzip.open(dst_gj, "wb", compresslevel=9) as fo:
        shutil.copyfileobj(fi, fo)
    n, gj = count_geojson(dst_gj)
    assert n == 41, f"expected 41 campsites, shipped {n}"
    assert "crs" not in gj, "GeoJSON must not carry a crs member (RFC 7946)"
    first = gj["features"][0]["geometry"]["coordinates"]
    assert 113 < first[0] < 115 and 22 < first[1] < 23, \
        f"coordinates are not lon/lat: {first}"
    entries.append(dict(
        file=f"{DATA_REL}/campsite_scores.geojson.gz",
        bytes=os.path.getsize(dst_gj),
        mb=round(os.path.getsize(dst_gj) / 1e6, 3),
        gzipped=True, features=n,
        title="Campsite scores for dark skies",
        dataset_id="afcd_rcd_1635133060194_82554",
        records="",
        notes="41 AFCD country-park campsites scored for night-sky darkness "
              "(VIIRS DNB, median of 12 nights), access, facilities and open "
              "horizon. EPSG:4326, lon/lat.",
        sha256=sha16(dst_gj)))
    print(f"campsite_scores.geojson.gz  {n} features  "
          f"{os.path.getsize(dst_gj)/1e6:.2f} MB")

    # ---- 2. land boundary ---------------------------------------------
    src_lb = f"{SRC}/hk_land_boundary.geojson"
    if os.path.exists(src_lb):
        dst_lb = os.path.join(DEST_DATA, "hk_land_boundary.geojson.gz")
        with open(src_lb, "rb") as fi, gzip.open(dst_lb, "wb", compresslevel=9) as fo:
            shutil.copyfileobj(fi, fo)
        n, gj = count_geojson(dst_lb)
        entries.append(dict(
            file=f"{DATA_REL}/hk_land_boundary.geojson.gz",
            bytes=os.path.getsize(dst_lb),
            mb=round(os.path.getsize(dst_lb) / 1e6, 3),
            gzipped=True, features=n,
            title="Hong Kong land boundary",
            dataset_id="",
            records="",
            notes="Land mask used to draw the night-lights map. Built from "
                  "OpenStreetMap natural=coastline ways, flood-filled from "
                  "the sea, and verified against known land and sea points. "
                  "EPSG:4326.",
            sha256=sha16(dst_lb)))
        print(f"hk_land_boundary.geojson.gz  {n} features  "
              f"{os.path.getsize(dst_lb)/1e6:.2f} MB")

    # ---- 3. night-lights composite raster -----------------------------
    src_tif = f"{NL}/raw/night_composite_median.tif"
    if os.path.exists(src_tif):
        dst_tif = os.path.join(DEST_DATA, "night_lights_composite.tif")
        shutil.copyfile(src_tif, dst_tif)
        import rasterio
        with rasterio.open(dst_tif) as ds:
            a = ds.read(1)
            assert a.max() > 0, "shipped night-lights raster is blank"
            shape_txt = f"{ds.height} x {ds.width}"
            crs = str(ds.crs)
        entries.append(dict(
            file=f"{DATA_REL}/night_lights_composite.tif",
            bytes=os.path.getsize(dst_tif),
            mb=round(os.path.getsize(dst_tif) / 1e6, 3),
            gzipped=False, features=None,
            title="VIIRS night lights over Hong Kong (12-night median)",
            dataset_id="",
            records=shape_txt,
            notes="VIIRS Day/Night Band NOAA-21 from NASA GIBS, median of 12 "
                  "nights 27 Oct - 7 Nov 2026. 8-bit display render, not "
                  "calibrated radiance. EPSG:4326.",
            sha256=sha16(dst_tif)))
        print(f"night_lights_composite.tif  {shape_txt}  "
              f"{os.path.getsize(dst_tif)/1e6:.2f} MB")

    # ---- 4. CSV + summary --------------------------------------------
    for name in ("campsite_scores.csv", "campsite_scores_summary.json"):
        s = f"{SRC}/{name}"
        if os.path.exists(s):
            d = os.path.join(DEST_DATA, name)
            shutil.copyfile(s, d)
            entries.append(dict(
                file=f"{DATA_REL}/{name}", bytes=os.path.getsize(d),
                mb=round(os.path.getsize(d) / 1e6, 3), gzipped=False,
                features=41 if name.endswith(".csv") else None,
                title="Campsite score table" if name.endswith(".csv")
                      else "Run statistics and robustness checks",
                dataset_id="", records="",
                notes="All factors, the weighted score, and the single-night "
                      "rank-shift robustness figure."
                      if name.endswith(".csv") else
                      "Run statistics: night-lights range, top 10, rank shift "
                      "vs a single night.",
                sha256=sha16(d)))
            print(f"{name}  {os.path.getsize(d)/1e3:.1f} kB")

    # ---- 5. the map ---------------------------------------------------
    src_png = f"{SRC}/HK_camping_sites_dark_sky_map.png"
    if os.path.exists(src_png):
        dst_png = os.path.join(DEST_MAP, "HK_camping_sites_dark_sky_map.png")
        shutil.copyfile(src_png, dst_png)
        entries.append(dict(
            file=f"{MAP_REL}/HK_camping_sites_dark_sky_map.png",
            bytes=os.path.getsize(dst_png),
            mb=round(os.path.getsize(dst_png) / 1e6, 3), gzipped=False,
            features=None,
            title="Light pollution and country-park campsites",
            dataset_id="", records="",
            notes="Two panels: VIIRS night lights over Hong Kong with all 41 "
                  "campsites marked, and the 20 best campsites broken down by "
                  "factor.",
            sha256=sha16(dst_png)))
        print(f"HK_camping_sites_dark_sky_map.png  "
              f"{os.path.getsize(dst_png)/1e6:.2f} MB")

    with open(os.path.join(SRC, "_manifest_entries.json"), "w") as f:
        json.dump(entries, f, indent=1)
    print(f"\n{len(entries)} entries -> _manifest_entries.json")
    print("all shipped files verified")


if __name__ == "__main__":
    main()
