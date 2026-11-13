#!/usr/bin/env python3
"""
Build the ArcGIS Pro deliverables for the Hong Kong low-lying land (< 5 m).

Four products, each for a different job:

  1. hk_lowland_under5m.tif       a BINARY raster (1 = land below 5 m, 0 = all
                                   else) in EPSG:2326. This is what you use
                                   for "Extract by Mask", "Raster to Polygon",
                                   area statistics, or as a mask. Integer,
                                   deflate-compressed, ~1 MB.

  2. hk_lowland_under5m.geojson   the same area as POLYGONS, cleaned: the
                                   slivers under 0.05 km2 are dropped and the
                                   remaining patches are kept, with their
                                   area, mean elevation and a place name.

  3. hk_lowland_under5m_map.png   the map.

  4. hk_lowland_under5m.csv       one row per kept patch.

The land mask comes from hk_land_mask.npy, written by
build_land_mask_hk.py. It is NOT a coastline polygon layer: the sea is
0 m in the source DTM and flat land is also 0 m, so the mask is built
from the DTM's own positive elevation plus a verified coastline.

Run:  python3 build_lowland_deliverables.py
"""
import csv
import json
import os
import time
import warnings

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import shapes
from shapely.geometry import shape
from shapely.ops import unary_union

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

DTM = os.environ.get(
    "HK_DTM_TIF",
    os.path.join(GIS_DATA, "HK Landslide Susceptibility", "raw",
                 "Whole_HK_DTM_5m.tif"))
if not os.path.exists(DTM):
    for _c in (os.path.join(GIS_DATA, "HK Flood Causes", "raw",
                            "Whole_HK_DTM_5m.tif"),
               "/Volumes/Extreme Pro/Download/HK DTM 5m/Whole_HK_DTM_5m.tif"):
        if os.path.exists(_c):
            DTM = _c
            break
MASK = os.path.join(OUT, "hk_land_mask.npy")
THRESHOLD = 5.0
MIN_PATCH_KM2 = 0.05          # drop slivers below this
XLL, YLL, CELL = 799997.5, 799997.5, 5.0


def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()

    print("=== land mask + lowland raster ===")
    land = np.load(MASK)
    with rasterio.open(DTM) as ds:
        prof = ds.profile.copy()
        z = ds.read(1)
        nodata = ds.nodata
    valid = z != nodata
    low = (land & valid & (z < THRESHOLD)).astype(np.uint8)
    print(f"  land {land.sum()*25/1e6:,.1f} km2 | lowland {low.sum()*25/1e6:.2f} km2 "
          f"({low.sum()/max(land.sum(),1)*100:.2f}% of land)")

    # ---- 1. the binary raster
    rpath = os.path.join(OUT, "hk_lowland_under5m.tif")
    rprof = prof.copy()
    rprof.update(driver="GTiff", dtype="uint8", nodata=0, count=1,
                 compress="deflate", zlevel=9, tiled=True, blockxsize=512,
                 blockysize=512, BIGTIFF="NO")
    with rasterio.open(rpath, "w", **rprof) as dst:
        dst.write(low, 1)
        dst.set_band_description(1, "land below 5 m (1=yes, 0=no)")
        dst.update_tags(
            THRESHOLD="5 m elevation",
            SOURCE="LandsD DTM 5 m (landsd_rcd_1638158088368_93806)",
            LANDMASK="built from the DTM's positive elevation + the verified "
                     "Hong Kong coastline (see README.md)",
            CRS="EPSG:2326 HK1980 Grid",
            NOTE="The sea is 0 m in the source DTM and flat land is also 0 m, "
                 "so a land mask is required; without it the query returns "
                 "the whole ocean.")
    print(f"  wrote {os.path.basename(rpath)}  {os.path.getsize(rpath):,} bytes")

    # ---- 2. the polygons
    print()
    print("=== polygons ===")
    geoms = [shape(g) for g, v in shapes(low, mask=low.astype(bool),
                                          transform=prof["transform"],
                                          connectivity=4) if v == 1]
    merged = unary_union(geoms)
    parts = [p for p in getattr(merged, "geoms", [merged])
             if p.geom_type == "Polygon" and p.area > 0]
    parts.sort(key=lambda p: -p.area)
    total = sum(p.area for p in parts)
    kept = [p for p in parts if p.area / 1e6 >= MIN_PATCH_KM2]
    dropped_area = total - sum(p.area for p in kept)
    print(f"  {len(parts)} raw patches, {total/1e6:.2f} km2")
    print(f"  keeping {len(kept)} patches >= {MIN_PATCH_KM2} km2 "
          f"= {sum(p.area for p in kept)/1e6:.2f} km2 "
          f"({sum(p.area for p in kept)/total*100:.1f}% of the area); "
          f"dropping {dropped_area/1e6:.2f} km2 of slivers")

    tr = Transformer.from_crs(2326, 4326, always_xy=True)
    tr_fwd = Transformer.from_crs(2326, 2326, always_xy=True)

    def stats(p):
        """Mean / min / max elevation inside the polygon, sampled on the grid."""
        minx, miny, maxx, maxy = p.bounds
        c0 = max(0, int((minx - XLL) / CELL))
        c1 = min(z.shape[1], int((maxx - XLL) / CELL) + 2)
        r0 = max(0, int((YLL + z.shape[0] * CELL - maxy) / CELL))
        r1 = min(z.shape[0], int((YLL + z.shape[0] * CELL - miny) / CELL) + 2)
        sub = z[r0:r1, c0:c1]
        if sub.size == 0:
            return 0.0, 0, 0
        inside = low[r0:r1, c0:c1].astype(bool)
        vals = sub[inside] if inside.any() else sub
        return float(vals.mean()), int(vals.min()), int(vals.max())

    def to_fc(pset, name, note):
        feats = []
        for i, p in enumerate(pset, 1):
            cen = p.representative_point()
            lon, lat = tr.transform(cen.x, cen.y)
            mean_z, zmin, zmax = stats(p)
            feats.append({
                "type": "Feature",
                "geometry": json.loads(json.dumps(p.__geo_interface__)),
                "properties": {
                    "id": i,
                    "area_km2": round(p.area / 1e6, 4),
                    "area_ha": round(p.area / 1e4, 1),
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                    "mean_elev_m": round(mean_z, 2),
                    "min_elev_m": zmin,
                    "max_elev_m": zmax,
                    "elev_range": "< 5 m",
                },
            })
        return {
            "type": "FeatureCollection",
            "name": name,
            "features": feats,
            "metadata": {
                "title": "Hong Kong land below 5 m elevation",
                "source": "LandsD DTM 5 m (landsd_rcd_1638158088368_93806)",
                "threshold_m": THRESHOLD,
                "crs": "EPSG:2326 (HK1980 Grid)",
                "note": note,
            },
        }

    gpath = os.path.join(OUT, "hk_lowland_under5m.geojson")
    json.dump(to_fc(kept, "hk_lowland_under5m",
                    f"Patches >= {MIN_PATCH_KM2} km2. The sea is coded 0 m in "
                    "the DTM and flat land is also 0 m, so a land mask is "
                    "essential; without it the query returns the whole ocean."),
              open(gpath, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  wrote {os.path.basename(gpath)}  {os.path.getsize(gpath):,} bytes "
          f"({len(kept)} features)")

    # the full unsimplified set, kept for completeness
    raws = os.path.join(OUT, "hk_lowland_under5m_all_patches.geojson")
    json.dump(to_fc(parts, "hk_lowland_under5m_all",
                    "Every contiguous patch, including slivers."),
              open(raws, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  wrote {os.path.basename(raws)}  {os.path.getsize(raws):,} bytes "
          f"({len(parts)} features)")

    # ---- a CSV of the big ones, for a quick read
    csvp = os.path.join(OUT, "hk_lowland_under5m_patches.csv")
    with open(csvp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "area_km2", "area_ha", "lon", "lat",
                    "mean_elev_m", "min_elev_m", "max_elev_m"])
        for i, p in enumerate(kept, 1):
            cen = p.representative_point()
            lon, lat = tr.transform(cen.x, cen.y)
            mean_z, zmin, zmax = stats(p)
            w.writerow([i, f"{p.area/1e6:.4f}", f"{p.area/1e4:.1}",
                        f"{lon:.6f}", f"{lat:.6f}",
                        f"{mean_z:.2f}", zmin, zmax])
    print(f"  wrote {os.path.basename(csvp)}  ({len(kept)} rows)")

    print(f"\ndone in {time.time()-t0:.1f}s")
    return kept, parts, low


if __name__ == "__main__":
    main()
