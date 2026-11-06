#!/usr/bin/env python3
"""Which slope statistic gives coherent >30 deg polygons?

slope_max at 20 m takes the single steepest 5 m cell in each block, so a
single noisy DTM cell (the LandsD DTM carries vegetation height) spawns a
tiny isolated polygon.  Compare the three statistics the project already
computes, plus a DTM-smoothed variant, on:
  - share of land over 30 deg
  - number of regions and how fragmented they are
  - a coherence score: share of the steep area sitting in regions >= 0.1 km2
"""
import os

import numpy as np
from scipy import ndimage

BASE = "/Users/davidhermes/GIS Data/HK Landslide Susceptibility"
d = np.load(f"{BASE}/work/terrain_20m.npz")
valid = d["valid"]
CELL = 20.0
nv = int(valid.sum())
land_km2 = nv * CELL * CELL / 1e6

s8 = ndimage.generate_binary_structure(2, 2)


def coherence(mask, label="", struct=s8):
    lab, n = ndimage.label(mask, structure=struct)
    counts = np.bincount(lab.ravel())
    counts = counts[counts > 0]
    a = np.sort(counts)[::-1] * CELL * CELL / 1e6
    tot = a.sum()
    big = a[a >= 0.1].sum()
    print(f"  {label:28s} >30: {tot:7.2f} km2 ({tot/land_km2*100:5.2f}% of land) | "
          f"{n:>7,} regions | >=0.1km2 holds {big/tot*100:5.1f}% of steep area | "
          f"largest {a[0]:.2f} km2")
    return tot, n


print(f"land {land_km2:.1f} km2\n")
print("--- existing statistics from terrain_20m.npz ---")
for name, key in [("slope (mean)", "slope"), ("slope_p90", "slope_p90"), ("slope_max", "slope_max")]:
    arr = d[key]
    coherence(valid & (arr > 30), name)

# --- DTM-smoothed variant: median filter the 5 m DTM, then recompute ------
print("\n--- from a median-smoothed 5 m DTM (need rasterio) ---")
try:
    import rasterio
    from rasterio.windows import Window
    ASC = f"{BASE}/raw/Whole_HK_DTM_5m.asc"
    SRC_CELL = 5.0
    BLOCK = 4  # 20 m
    sm_mean = np.full(valid.shape, np.nan, np.float32)
    sm_p90 = np.full(valid.shape, np.nan, np.float32)
    with rasterio.open(ASC) as ds:
        H5, W5 = ds.height, ds.width
        nodata = ds.nodata
        nh, nw = H5 // BLOCK, W5 // BLOCK
        RPS = 250
        for r0 in range(0, nh, RPS):
            r1 = min(r0 + RPS, nh)
            h0, h1 = max(r0 * BLOCK - 1, 0), min(r1 * BLOCK + 1, H5)
            b = ds.read(1, window=Window(0, h0, nw * BLOCK, h1 - h0), out_dtype="float32")
            b = np.where(b == nodata, np.nan, b)
            sm = ndimage.median_filter(np.nan_to_num(b, nan=0.0), size=3)
            # Horn slope on the smoothed surface
            w = [sm[0:-2, 0:-2], sm[0:-2, 1:-1], sm[0:-2, 2:],
                 sm[1:-1, 0:-2], sm[1:-1, 2:],
                 sm[2:, 0:-2], sm[2:, 1:-1], sm[2:, 2:]]
            ctr = sm[1:-1, 1:-1]
            dzdx = ((w[2] + 2 * w[5] + w[6]) - (w[0] + 2 * w[3] + w[4])) / (8 * SRC_CELL)
            dzdy = ((w[6] + 2 * w[5] + w[4]) - (w[0] + 2 * w[3] + w[2])) / (8 * SRC_CELL)
            s5 = np.degrees(np.arctan(np.sqrt(dzdx ** 2 + dzdy ** 2)))
            s5 = np.full(b.shape, np.nan, np.float32)
            s5[1:-1, 1:-1] = np.degrees(np.arctan(np.sqrt(dzdx ** 2 + dzdy ** 2)))
            a, c = r0 * BLOCK - h0, r1 * BLOCK - h0
            z = b[a:c]
            s = s5[a:c]
            def red(arr, how):
                t = arr[: (arr.shape[0] // BLOCK) * BLOCK, : (arr.shape[1] // BLOCK) * BLOCK]
                t = t.reshape(t.shape[0] // BLOCK, BLOCK, t.shape[1] // BLOCK, BLOCK)
                t = t.transpose(0, 2, 1, 3).reshape(t.shape[0] // BLOCK, t.shape[1] // BLOCK, BLOCK * BLOCK)
                with np.errstate(invalid="ignore"):
                    if how == "mean":
                        return np.nanmean(t, axis=2)
                    return np.nanpercentile(t, 90, axis=2)
            sm_mean[r0:r1] = red(z, "mean").astype(np.float32)
            sm_p90[r0:r1] = red(s, "p90").astype(np.float32)
        vv = np.isfinite(sm_mean) & valid
        sm_mean[~vv] = np.nan
        sm_p90[~vv] = np.nan
    print("  (computed)")
    coherence(valid & (sm_mean > 30), "smoothed slope mean")
    coherence(valid & (sm_p90 > 30), "smoothed slope p90")
except Exception as e:
    print("  FAILED:", e)
