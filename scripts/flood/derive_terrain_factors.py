#!/usr/bin/env python3
"""
Terrain factors for flash flood: slope and flow accumulation from the
LandsD 5 m DTM.

Why this matters
----------------
A flash flood needs (a) a steep catchment to generate runoff fast and
(b) a low receiving point to pond the water. Both are terrain properties,
and both are derivable from the DTM - the same 5 m grid the flood-mechanism
derivation already uses.

Method
------
1. Slope from a 3x3 Horn neighbourhood on the DTM, in degrees.
2. Flow accumulation (upstream contributing area) by processing the DTM
   cells from HIGH to LOW and pushing each cell's accumulated area into
   its steepest lower neighbour - the classic D8 method, done on the
   full-resolution grid.

The accumulation step is the expensive one. It is done with numpy
vectorised passes (one pass per elevation "level" is too slow), so instead
the grid is sorted by elevation ONCE and processed in descending order
with a small Python loop over the steepest-descent pointers. On a
12,751 x 9,601 grid that is 122 M cells - too many for a Python loop.

Practical compromise used here: the accumulation is computed on a
COARSENED grid (the 5 m DTM decimated to 40 m by block-mean), which is
9,601 x 12,751 -> 1,200 x 1,595 cells = 1.9 M cells. That is fast enough
in Python and entirely appropriate for a catchment-scale factor (the
smallest WSD catchment is far larger than 40 m).

Outputs (out/):
  terrain_slope_summary.json    per-area terrain factors
  terrain_slope_grid.npz        the coarse slope + accumulation grids

Run:  ls-venv/bin/python derive_terrain_factors.py
"""
import json
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

SCRATCH = os.environ.get("SCRATCH_DIR", "/Users/davidhermes/.hermes/cache/scratch")
NPY = os.path.join(SCRATCH, "hk_dtm_5m.npy")
NROWS, NCOLS = 9601, 12751
XLL, YLL, CELL = 799997.5, 799997.5, 5.0
COARSE = 8            # 8 x 5 m = 40 m coarse cells


def load_dem():
    if not os.path.exists(NPY):
        raise SystemExit(
            f"{NPY} missing.\n"
            "Rebuild it with:  ls-venv/bin/python scripts/flood/fetch_dtm.py\n"
            "(download -> extract -> convert; ~40 s, needs 490 MB free)")
    t = time.time()
    dem = np.load(NPY, mmap_mode="r")
    print(f"  DTM {dem.shape} loaded in {time.time()-t:.1f}s")
    return dem


def coarse_mean(dem, k):
    """Block-mean the DTM down by k, ignoring NODATA."""
    r, c = dem.shape
    rc, cc = r // k, c // k
    a = np.asarray(dem[:rc * k, :cc * k], dtype=np.float32).reshape(rc, k, cc, k)
    valid = a != -9999
    a = np.where(valid, a, 0.0)
    cnt = valid.sum(axis=(1, 3))
    tot = a.sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(cnt > 0, tot / np.maximum(cnt, 1), -9999.0)
    return out.astype(np.float32)


def slope_deg(z, cell_size):
    """Horn 3x3 slope in degrees. z is (rows, cols), north edge first.

    The padded array p has shape (r+2, c+2). For output cell (i, j):
        north block = p[0:r, ...]      z[i-1, j-1] .. z[i-1, j+1]
        centre row = p[1:r+1, ...]     z[i,   j-1] .. z[i,   j+1]
        south block = p[2:r+2, ...]    z[i+1, j-1] .. z[i+1, j+1]
    The slope magnitude does not depend on which edge is row 0, but the
    D8 receiver calculation below DOES - see flow_accumulation.
    """
    r, c = z.shape
    p = np.pad(z, 1, mode="edge")

    # d/dx: east block minus west block, over the centre row
    east = p[1:r + 1, 2:c + 2] + 2 * p[1:r + 1, 1:c + 1] + p[1:r + 1, 0:c]
    west = p[1:r + 1, 0:c] + 2 * p[1:r + 1, 1:c + 1] + p[1:r + 1, 2:c + 2]
    dzdx = (east - west) / (8 * cell_size)

    # d/dy: south block minus north block
    south = p[2:r + 2, 0:c] + 2 * p[2:r + 2, 1:c + 1] + p[2:r + 2, 2:c + 2]
    north = p[0:r, 0:c] + 2 * p[0:r, 1:c + 1] + p[0:r, 2:c + 2]
    dzdy = (south - north) / (8 * cell_size)

    return np.degrees(np.arctan(np.sqrt(dzdx ** 2 + dzdy ** 2)))


def flow_accumulation(z, cellsize):
    """D8 flow accumulation, in cells, on a north-edge-first grid.

    Each cell sends its accumulated area to its steepest lower neighbour.
    Cells that are sinks (no lower neighbour) keep their own area.

    The accumulation MUST be done in descending elevation order, because a
    cell's total depends on every cell upstream of it. numpy's add.at
    does not respect that order, so the loop is done over an explicit
    elevation-sorted index.

    For a 1.9 M-cell coarse grid a Python loop over the sorted order is
    acceptable (a few seconds); it is NOT acceptable on the full 122 M
    cell grid, which is why the accumulation runs on the coarse grid.
    """
    r, c = z.shape
    zflat = z.ravel().astype(np.float64)
    valid = zflat != -9999

    # ---- steepest-descent receivers --------------------------------
    p = np.pad(z, 1, mode="edge")
    rr, cc = np.mgrid[0:r, 0:c]
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    dist = np.array([cellsize * np.sqrt(2), cellsize, cellsize * np.sqrt(2),
                     cellsize, cellsize,
                     cellsize * np.sqrt(2), cellsize, cellsize * np.sqrt(2)])
    best_slope = np.full(r * c, -np.inf)
    receiver = np.full(r * c, -1, dtype=np.int64)
    for i, (dr, dc) in enumerate(offs):
        nb = p[1 + rr + dr, 1 + cc + dc]
        with np.errstate(invalid="ignore", divide="ignore"):
            s = (zflat.reshape(r, c) - nb) / dist[i]
        s = np.where((nb != -9999) & (s > 0), s, -np.inf).ravel()
        better = s > best_slope
        tgt = ((rr + dr).clip(0, r - 1) * c + (cc + dc).clip(0, c - 1)).ravel()
        receiver = np.where(better, tgt, receiver)
        best_slope = np.where(better, s, best_slope)

    # ---- accumulate in descending elevation order --------------------
    acc = np.where(valid, 1.0, 0.0)
    order = np.argsort(-zflat, kind="stable")       # high -> low
    for idx in order:
        if not valid[idx]:
            continue
        tgt = receiver[idx]
        if tgt >= 0:
            acc[tgt] += acc[idx]
    return acc.reshape(r, c), receiver.reshape(r, c)


def main():
    print("=== terrain factors for flash flood ===")
    dem = load_dem()

    # ---- coarse grid ------------------------------------------------
    t = time.time()
    zc = coarse_mean(dem, COARSE)
    nrc, ncc = zc.shape
    cellsize = CELL * COARSE
    print(f"  coarse grid {zc.shape} at {cellsize:.0f} m ({time.time()-t:.1f}s)")

    # ---- slope ------------------------------------------------------
    t = time.time()
    slope = slope_deg(zc, cellsize)
    slope[zc == -9999] = np.nan
    print(f"  slope computed ({time.time()-t:.1f}s)")
    v = slope[~np.isnan(slope)]
    print(f"    slope: min {np.nanmin(slope):.1f} median {np.nanmedian(slope):.1f} "
          f"max {np.nanmax(slope):.1f} deg")

    # ---- flow accumulation ------------------------------------------
    # The coarse grid is north-edge-first like the source.
    t = time.time()
    acc, receiver = flow_accumulation(zc, cellsize)
    print(f"  flow accumulation ({time.time()-t:.1f}s)")
    a = acc[acc > 0]
    print(f"    contributing area: median {np.median(a)*cellsize**2/1e6:.3f} km2 "
          f"max {a.max()*cellsize**2/1e6:.1f} km2")

    # ---- per flood-prone-area terrain factors ------------------------
    GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
    F = os.path.join(GIS_DATA, "HK Flood Prone Areas",
                   "flood_mechanism.geojson")
    if not os.path.exists(F):
        print(f"  (skipping per-area factors: {F} not found)")
        per_area = {}
    else:
        import pyproj
        FWD = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4326),
                                           pyproj.CRS.from_epsg(2326),
                                           always_xy=True)
        flood = json.load(open(F))
        per_area = {}
        for ft in flood["features"]:
            p = ft["properties"]
            c = ft["geometry"]["coordinates"]
            gx, gy = FWD.transform(c[0], c[1])
            # coarse grid is north-edge-first, same as the source DTM
            rr = ((YLL + nrc * cellsize) - gy) / cellsize
            cc = (gx - XLL) / cellsize
            i, j = int(round(rr)), int(round(cc))
            if 0 <= i < nrc and 0 <= j < ncc:
                per_area[p.get("title")] = {
                    "slope_deg": round(float(slope[i, j]), 2),
                    "contributing_area_km2": round(float(acc[i, j]) * cellsize ** 2 / 1e6, 4),
                    "is_flow_accumulation_max": bool(acc[i, j] >= acc.max() - 1),
                }
        vals = [d["slope_deg"] for d in per_area.values()]
        ca = [d["contributing_area_km2"] for d in per_area.values()]
        print(f"  per-area terrain factors for {len(per_area)} areas")
        print(f"    slope: min {min(vals):.1f} median {np.median(vals):.1f} max {max(vals):.1f} deg")
        print(f"    contributing area: min {min(ca):.3f} median {np.median(ca):.3f} "
              f"max {max(ca):.1f} km2")

    np.savez_compressed(os.path.join(OUT, "terrain_grids.npz"),
                        slope=slope, acc=acc, z=zc)
    with open(os.path.join(OUT, "terrain_slope_summary.json"), "w") as f:
        json.dump({"generated": "2026-11-09",
                   "grid": {"rows": nrc, "cols": ncc, "cellsize_m": cellsize,
                            "origin_hk1980": [XLL, YLL],
                            "row_order": "north edge first"},
                   "slope_deg": {"min": float(np.nanmin(slope)),
                                 "median": float(np.nanmedian(slope)),
                                 "max": float(np.nanmax(slope))},
                   "per_area": per_area}, f, indent=1)
    print(f"  wrote {OUT}/terrain_grids.npz and terrain_slope_summary.json")


if __name__ == "__main__":
    main()
