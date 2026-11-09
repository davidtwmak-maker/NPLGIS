#!/usr/bin/env python3
"""
Fetch the LandsD Whole HK DTM 5 m and convert it to a fast .npy cache.

Why this script exists
----------------------
`derive_mechanism_v2.py` needs the ground elevation for all 267 flood-prone
points, and the only source is the LandsD Whole HK DTM 5 m. Two problems
made it awkward to use directly:

1. It ships as a 302 MB ESRI ASCII grid (`Whole_HK_DTM_5m.asc`, 12,751 x
   9,601 cells). Reading a small window out of an ASCII grid with rasterio
   takes MINUTES per call, because the driver parses the whole file to find
   the header offsets.

2. The CSDI file-api returns 403 for this dataset, so it has to come from
   the LandsD site directly.

So: download the zip once, convert the ASCII grid to a .npy array once, and
sample that array with numpy afterwards. The conversion takes about a minute
and the whole file is ~490 MB as float32.

Usage
-----
    python3 scripts/flood/fetch_dtm.py
    python3 scripts/flood/fetch_dtm.py --out /some/other/dir

The cache path defaults to $HK_SCRATCH (the Hermes scratch directory), and
falls back to the same location the derivation script looks in.
"""
import argparse
import os
import subprocess
import sys
import time
import zipfile

URL = ("https://www.landsd.gov.hk/landsd_psi_data/SMO/data/"
       "Whole_HK_DTM_5m.zip")
ASC = "Whole_HK_DTM_5m.asc"
NPY = "hk_dtm_5m.npy"
DEFAULT_SCRATCH = "/Users/davidhermes/.hermes/cache/scratch"


def log(m):
    print(m, flush=True)


def download(dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    zip_path = os.path.join(dst_dir, "Whole_HK_DTM_5m.zip")
    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 28_000_000:
        log(f"  zip already present ({os.path.getsize(zip_path):,} bytes)")
        return zip_path
    log(f"  downloading {URL}")
    # curl with a resume-friendly invocation; -L follows redirects
    rc = subprocess.call([
        "curl", "-sL", "--fail", "-o", zip_path, URL,
        "-w", "  HTTP %{http_code}  %{size_download} bytes\\n",
    ])
    if rc != 0 or not os.path.exists(zip_path):
        raise SystemExit(f"download failed (curl exit {rc})")
    log(f"  downloaded {os.path.getsize(zip_path):,} bytes")
    return zip_path


def extract(zip_path, dst_dir):
    asc_path = os.path.join(dst_dir, ASC)
    if os.path.exists(asc_path) and os.path.getsize(asc_path) > 300_000_000:
        log(f"  ASCII grid already present ({os.path.getsize(asc_path):,} bytes)")
        return asc_path
    log("  extracting")
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if ASC not in names:
            raise SystemExit(f"{ASC} not in the zip; contents: {names}")
        z.extract(ASC, dst_dir)
    log(f"  extracted {os.path.getsize(asc_path):,} bytes")
    return asc_path


def convert(asc_path, npy_path):
    if os.path.exists(npy_path):
        log(f"  npy cache already present ({os.path.getsize(npy_path):,} bytes)")
        return npy_path
    import numpy as np
    log("  converting the ASCII grid to a numpy array (about 15 seconds)")
    t0 = time.time()
    # The ESRI ASCII grid starts with a 6-line header:
    #     ncols, nrows, xllcorner, yllcorner, cellsize, NODATA_value
    # np.loadtxt cannot parse those, so they are skipped.
    arr = np.loadtxt(asc_path, dtype=np.float32, skiprows=6)
    log(f"  parsed {arr.shape[0]:,} x {arr.shape[1]:,} in {time.time()-t0:.0f}s")
    # sanity: the shape must match the header
    hdr = {}
    with open(asc_path) as f:
        for _ in range(6):
            parts = f.readline().split()
            hdr[parts[0].lower()] = float(parts[1])
    if arr.shape != (int(hdr["nrows"]), int(hdr["ncols"])):
        raise SystemExit(
            f"shape {arr.shape} does not match the header "
            f"({int(hdr['nrows'])}, {int(hdr['ncols'])})")
    np.save(npy_path, arr)
    log(f"  wrote {npy_path} ({os.path.getsize(npy_path):,} bytes)")
    return npy_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="where to put the zip, the ASCII grid and the .npy")
    args = ap.parse_args()

    dst = args.out or os.environ.get("HK_SCRATCH") or DEFAULT_SCRATCH
    log(f"destination: {dst}")

    zip_path = download(dst)
    asc_path = extract(zip_path, dst)
    npy_path = convert(asc_path, os.path.join(dst, NPY))

    log("\nDone. The flood derivation script reads the .npy:")
    log(f"  {npy_path}")
    log("\nThe grid is in EPSG:2326 (HK1980 Grid, metres), origin")
    log("799997.5/799997.5, 5 m cells, NODATA -9999.")


if __name__ == "__main__":
    main()
