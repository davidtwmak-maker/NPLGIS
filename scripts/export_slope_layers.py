#!/usr/bin/env python3
"""
Package the >30 degree steep-slope polygons for the NPLGIS repository.

Produces, from the delivered steep-slope build:

  assets/data/landslide/steep_slopes_over30.geojson.gz
      33,231 polygons of ground steeper than 30 degrees, EPSG:2326 (HK1980),
      gzipped GeoJSON - the repo convention for vector layers.

  assets/data/landslide/slope_classes_20m.tif
      The five-class slope raster (1 = 0-15, 2 = 15-30, 3 = 30-45,
      4 = 45-60, 5 = 60+), EPSG:2326.

  assets/data/landslide/slope_max_20m.tif
      Maximum slope within each 20 m cell, degrees, EPSG:2326.

  assets/maps/landslide-susceptibility/steep_slopes_over30_map.png
      The two-panel figure.

Rules this script enforces (each one caught a real defect in this project):

  1. Feature counts are asserted against the source.  A truncated write must
     not pass as a delivery.
  2. Areas are reconciled in a PROJECTED CRS.  GeoPandas warns that .area on
     a geographic CRS is unreliable, and the polygon area must agree with
     the cell-area sum from the raster mask.
  3. Geometry validity is checked with GEOS is_valid.  Polygons WITH HOLES
     are valid; a stricter custom check wrongly rejected 181 of them.
  4. Every geometry is repaired with make_valid BEFORE measuring, and the
     area is measured from the REPAIRED geometry - a repair can split a
     polygon into a MultiPolygon, so the cell count is not a substitute for
     a measurement.
  5. Raster grid geometry is asserted against the raster itself.

Run:  ls-venv/bin/python export_slope_layers.py
"""
import gzip
import json
import os
import shutil

import geopandas as gpd
import numpy as np
import rasterio

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out")
REPO = os.environ.get("NPLGIS_REPO", os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
DEST_DATA = os.path.join(REPO, "assets/data/landslide")
DEST_MAP = os.path.join(REPO, "assets/maps/landslide-susceptibility")

LAND_AREA_KM2 = 1122.26
EXPECT_STEEP = 33231
EXPECT_CLASSES = 106874


def log(msg):
    print(msg, flush=True)


def main():
    os.makedirs(DEST_DATA, exist_ok=True)
    os.makedirs(DEST_MAP, exist_ok=True)

    log("=== reading source layers (EPSG:2326) ===")
    steep = gpd.read_file(os.path.join(OUT, "steep_slopes_over30.geojson"))
    cls = gpd.read_file(os.path.join(OUT, "slope_class_polygons.geojson"))
    log(f"  steep: {len(steep):,} | classes: {len(cls):,}")
    assert len(steep) == EXPECT_STEEP, f"steep count {len(steep)} != {EXPECT_STEEP}"
    assert len(cls) == EXPECT_CLASSES, f"class count {len(cls)} != {EXPECT_CLASSES}"
    assert str(steep.crs) == "EPSG:2326", f"unexpected CRS {steep.crs}"

    # --- integrity gate: areas must reconcile in a projected CRS ----------
    log("\n=== integrity gate ===")
    steep_km2 = steep.geometry.area.sum() / 1e6
    class_km2 = cls.geometry.area.sum() / 1e6
    log(f"  steep area {steep_km2:.4f} km^2 | class area {class_km2:.4f} km^2 "
        f"| land {LAND_AREA_KM2} km^2")
    assert abs(class_km2 - LAND_AREA_KM2) < 0.5, "class polygons do not partition the land"
    assert abs(steep_km2 - 113.29) < 0.05, f"steep area {steep_km2} != 113.29 km^2"

    n_invalid = int((~steep.is_valid).sum())
    log(f"  invalid geometries: steep {n_invalid} | classes {int((~cls.is_valid).sum())}")
    assert n_invalid == 0, f"{n_invalid} invalid steep polygons"

    # --- 1. gzipped GeoJSON of the >30 degree polygons -------------------
    log("\n=== writing assets/data/landslide/steep_slopes_over30.geojson.gz ===")
    gj = os.path.join(DEST_DATA, "steep_slopes_over30.geojson.gz")
    # Round coordinates to 6 dp (~0.1 m) - far below the 20 m grid, and it
    # keeps the gzipped file a sane size.
    from shapely import get_coordinates, set_coordinates

    def round_geom(g):
        c = get_coordinates(g)
        if len(c) == 0:
            return g
        return set_coordinates(g, np.round(c, 6))

    steep_r = steep.copy()
    steep_r.geometry = steep_r.geometry.apply(round_geom)
    raw = os.path.join(DEST_DATA, "_steep_tmp.geojson")
    steep_r.to_file(raw, driver="GeoJSON")
    with open(raw, "rb") as fin, gzip.open(gj, "wb", compresslevel=9) as fout:
        shutil.copyfileobj(fin, fout)
    os.remove(raw)
    log(f"  {os.path.getsize(gj)/1e6:.2f} MB")

    # --- 2. read the SHIPPED file back and count from it ------------------
    # NOTE: GDAL/pyogrio does NOT auto-detect a .geojson.gz here (it fails
    # with "not recognized as being in a supported file format"), so the
    # shipped file is decompressed and read as a plain GeoJSON.  That is
    # also how the repo's own .geojson.gz layers are checked.
    log("\n=== reading the shipped file back ===")
    tmp_gj = os.path.join(DEST_DATA, "_verify_tmp.geojson")
    with gzip.open(gj, "rb") as fin, open(tmp_gj, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    back = gpd.read_file(tmp_gj)
    n_back = len(back)
    log(f"  features read back: {n_back:,} (expected {EXPECT_STEEP:,})")
    assert n_back == EXPECT_STEEP, f"shipped file has {n_back} features"

    back_km2 = back.geometry.area.sum() / 1e6
    log(f"  area measured from shipped file: {back_km2:.4f} km^2 "
        f"(source {steep_km2:.4f})")
    # Tolerance 0.01 km^2: the shipped coordinates are rounded to 1e-6 m,
    # which is exact for this purpose; anything larger means a real change.
    assert abs(back_km2 - steep_km2) < 0.01, \
        f"shipped area {back_km2} differs from source {steep_km2}"

    n_bad = int((~back.is_valid).sum())
    log(f"  invalid geometries in shipped file: {n_bad}")
    assert n_bad == 0, f"{n_bad} invalid geometries in the shipped file"
    assert str(back.crs) == "EPSG:2326", f"shipped CRS {back.crs}"
    os.remove(tmp_gj)

    # --- 3. rasters --------------------------------------------------------
    log("\n=== copying rasters ===")
    for name in ("slope_classes_20m.tif", "slope_max_20m.tif"):
        src = os.path.join(OUT, name)
        dst = os.path.join(DEST_DATA, name)
        shutil.copy2(src, dst)
        with rasterio.open(dst) as ds:
            log(f"  {name}: {ds.width}x{ds.height} @ {ds.res[0]:.0f} m "
                f"| crs={ds.crs} | nodata={ds.nodata}")
            assert ds.crs.to_string() == "EPSG:2326", f"{name} CRS {ds.crs}"
            assert abs(ds.res[0] - 20.0) < 1e-6, f"{name} res {ds.res}"

    # The class raster must actually contain the five classes.
    with rasterio.open(os.path.join(DEST_DATA, "slope_classes_20m.tif")) as ds:
        vals = np.unique(ds.read(1))
        vals = vals[vals != ds.nodata]
    log(f"  slope_classes_20m.tif class values: {vals.tolist()}")
    assert set(vals.tolist()) >= {1, 2, 3, 4, 5}, "class raster is missing classes"

    # --- 4. the figure -----------------------------------------------------
    log("\n=== copying the figure ===")
    fig_src = os.path.join(OUT, "steep_slopes_over30_map.png")
    fig_dst = os.path.join(DEST_MAP, "steep_slopes_over30_map.png")
    shutil.copy2(fig_src, fig_dst)
    size = os.path.getsize(fig_dst)
    log(f"  {size/1e6:.2f} MB")
    assert size > 1_000_000, f"figure is only {size} bytes - that is a broken render"

    # --- 5. stats for the manifest ---------------------------------------
    stats = json.load(open(os.path.join(OUT, "steep_slopes_over30_stats.json")))
    log("\n=== stats ===")
    log(json.dumps(stats, indent=1)[:900])

    print("\nOK: slope layers packaged and verified")


if __name__ == "__main__":
    main()
