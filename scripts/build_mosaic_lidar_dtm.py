#!/usr/bin/env python3
"""Download any missing LiDAR DTM tiles for the Kowloon Tong study area and
rebuild the mosaic in HK1980 Grid (EPSG:2326).

LiDAR DTM 2020 comes as 500 m HK1980 grid tiles of GeoTIFF zips:
  https://bulkdata.csdi.gov.hk/cedd/lidar/2020dtm/<tile>.zip
Tile list comes from the CSDI FeatureServer:
  cedd_rcd_1629267205233_87895 / FeatureServer / 0  (DTM_2020)
"""
import glob
import json
import os
import sys
import urllib.request
import zipfile

import rasterio
from rasterio.merge import merge
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

WORK = str(HERE / "lidar_dtm")
TIFFS = os.path.join(WORK, "tifs")
S = ("https://portal.csdi.gov.hk/server/rest/services/common/"
     "cedd_rcd_1629267205233_87895/FeatureServer/0/query")

# Study area: Kowloon Tong valley + Lion Rock + Kowloon Tsai, wide enough that
# the hill the mall sits against is fully in frame.
LON0, LON1, LAT0, LAT1 = 114.145, 114.220, 22.315, 22.375

os.makedirs(TIFFS, exist_ok=True)


def fetch_tiles():
    import requests
    r = requests.get(S, params={
        "where": "1=1", "outFields": "TILE_NAME,Filename,URL",
        "returnGeometry": "false", "f": "json", "resultRecordCount": 3000,
        "geometry": f"{LON0},{LAT0},{LON1},{LAT1}",
        "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects"}, timeout=120)
    feats = r.json().get("features", [])
    print(f"tiles covering study area: {len(feats)}", flush=True)

    n_new = 0
    for f in feats:
        url = f["attributes"]["URL"]
        base = os.path.basename(url)
        tif = os.path.join(TIFFS, base.replace(".zip", ".tif"))
        if os.path.exists(tif):
            continue
        zpath = os.path.join(WORK, base)
        if not os.path.exists(zpath) or os.path.getsize(zpath) < 1000:
            try:
                urllib.request.urlretrieve(url, zpath)
            except Exception as e:
                print(f"  FAIL {base}: {e}", flush=True)
                continue
        try:
            with zipfile.ZipFile(zpath) as z:
                for n in z.namelist():
                    if n.lower().endswith(".tif"):
                        out = os.path.join(TIFFS, os.path.basename(n))
                        if not os.path.exists(out):
                            with z.open(n) as s, open(out, "wb") as d:
                                d.write(s.read())
            n_new += 1
        except zipfile.BadZipFile:
            print(f"  BAD ZIP (partial download): {base}", flush=True)
            try:
                os.remove(zpath)
            except OSError:
                pass
    print(f"new tiles extracted: {n_new}", flush=True)


def build_mosaic():
    b2326 = transform_bounds("EPSG:4326", "EPSG:2326", LON0, LAT0, LON1, LAT1)
    print("study bbox in EPSG:2326:", [round(v, 1) for v in b2326], flush=True)

    srcs = [rasterio.open(p) for p in sorted(glob.glob(os.path.join(TIFFS, "*.tif")))]
    print(f"opened {len(srcs)} tiles", flush=True)

    cropped = []
    for ds in srcs:
        try:
            win = from_bounds(*b2326, transform=ds.transform)
            w = win.intersection(Window(0, 0, ds.width, ds.height))
            if w.width <= 0 or w.height <= 0:
                ds.close()
                continue
            win = w.round_offsets().round_lengths()
            data = ds.read(1, window=win)
            prof = ds.profile.copy()
            prof.update(height=win.height, width=win.width,
                        transform=ds.window_transform(win),
                        driver="GTiff", compress="deflate", count=1, dtype="float32")
            tmp = os.path.join(WORK, "_crop_tmp.tif")
            with rasterio.open(tmp, "w", **prof) as out:
                out.write(data, 1)
            cropped.append(rasterio.open(tmp))
        except Exception as e:
            print(f"  skip {ds.name}: {e}", flush=True)
        finally:
            ds.close()

    print(f"cropped tiles: {len(cropped)}", flush=True)
    mosaic, transform = merge(cropped, method="max", nodata=-9999.0)
    arr = mosaic[0]
    out_tif = os.path.join(WORK, "kt_mosaic_2326.tif")
    prof = {"driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1], "count": 1,
            "dtype": "float32", "crs": "EPSG:2326", "transform": transform,
            "nodata": -9999.0, "compress": "deflate"}
    with rasterio.open(out_tif, "w", **prof) as out:
        out.write(arr, 1)
    for ds in cropped:
        ds.close()
    for p in glob.glob(os.path.join(WORK, "_crop_tmp.tif")):
        os.remove(p)

    valid = arr[arr > -9000]
    print(f"mosaic saved: {out_tif}  {os.path.getsize(out_tif)/1e6:.1f} MB", flush=True)
    print(f"  shape {arr.shape}  elevation {valid.min():.1f} .. {valid.max():.1f} m", flush=True)
    print(f"  bounds: {transform.c} .. {transform.c + arr.shape[1]*transform.a} (x)", flush=True)
    print(f"          {transform.f + arr.shape[0]*transform.e} .. {transform.f} (y)", flush=True)
    return 0


if __name__ == "__main__":
    fetch_tiles()
    sys.exit(build_mosaic())
