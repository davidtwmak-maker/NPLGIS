#!/usr/bin/env python3
"""Derive terrain predictors from LandsD DTM 5 m for HK landslide susceptibility.

Reads the ESRI ASCII grid with rasterio, derives slope / curvature / relief /
roughness / TWI / SPI, and aggregates to a 200 m analysis grid in HK1980
(EPSG:2326).

Output: work/terrain_200m.npz
Source: https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip
"""
import os
import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage

BASE = os.path.dirname(os.path.abspath(__file__))
ASC = os.path.join(BASE, "raw", "Whole_HK_DTM_5m.asc")
OUT = os.path.join(BASE, "work", "terrain_200m.npz")
GRID = 200.0            # analysis cell (m)
SRC_CELL = 5.0         # DTM cell size (m)
BLOCK = int(GRID / SRC_CELL)   # 40 DTM cells per analysis cell


def block_reduce(arr, how="mean"):
    """Reduce (nh*BLOCK, nw*BLOCK) -> (nh, nw) using one reshape + transpose."""
    nh = arr.shape[0] // BLOCK
    nw = arr.shape[1] // BLOCK
    trimmed = arr[:nh * BLOCK, :nw * BLOCK]
    t = trimmed.reshape(nh, BLOCK, nw, BLOCK).transpose(0, 2, 1, 3)
    flat = t.reshape(nh, nw, BLOCK * BLOCK)
    with np.errstate(invalid="ignore"):
        if how == "mean":
            out = np.nanmean(flat, axis=2)
        elif how == "std":
            out = np.nanstd(flat, axis=2)
        elif how == "max":
            out = np.nanmax(flat, axis=2)
        elif how == "p90":
            out = np.nanpercentile(flat, 90, axis=2)
        else:
            raise ValueError(how)
    return out.astype(np.float32)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with rasterio.open(ASC) as ds:
        nodata = ds.nodata
        print(f"raster {ds.width}x{ds.height} res={ds.res} nodata={nodata}", flush=True)
        dem = ds.read(1, out_dtype="float32")
    dem = np.where(dem == nodata, np.nan, dem)
    print("loaded", dem.shape, flush=True)

    # --- Horn slope (degrees) + Laplacian curvature on the 5 m grid ---
    z = dem
    w = [z[0:-2, 0:-2], z[0:-2, 1:-1], z[0:-2, 2:],
         z[1:-1, 0:-2], z[1:-1, 2:],
         z[2:, 0:-2], z[2:, 1:-1], z[2:, 2:]]
    center = z[1:-1, 1:-1]
    with np.errstate(invalid="ignore"):
        dzdx = ((w[2] + 2 * w[5] + w[6]) - (w[0] + 2 * w[3] + w[4])) / (8 * SRC_CELL)
        dzdy = ((w[6] + 2 * w[5] + w[4]) - (w[0] + 2 * w[3] + w[2])) / (8 * SRC_CELL)
        slope5 = np.degrees(np.arctan(np.sqrt(dzdx ** 2 + dzdy ** 2)))
        lap5 = (w[0] + w[2] + w[6] + w[4] - 4 * center) / (SRC_CELL ** 2)
    del w, center, dzdx, dzdy
    # Horn/laplacian windows lose the outer 1-cell border -> pad back to full grid
    def pad_full(a):
        out = np.full(dem.shape, np.nan, dtype=np.float32)
        out[1:-1, 1:-1] = a
        return out
    slope5 = pad_full(slope5)
    lap5 = pad_full(lap5)
    print("slope+curvature done", flush=True)

    # --- aggregate 5 m -> 200 m (single vectorised pass per variable) ---
    elev = block_reduce(dem, "mean")
    slope = block_reduce(slope5, "mean")
    curv = block_reduce(lap5, "mean")

    # slope max / p90 inside each block: mean slope dilutes a 40-degree scarp
    # across a 200 m cell, so block statistics are needed as well.
    slope_max = block_reduce(slope5, "max")
    slope_p90 = block_reduce(slope5, "p90")
    del dem, slope5, lap5

    # roughness = elevation std inside each block (re-read source in row strips)
    rough = np.empty_like(elev)
    with rasterio.open(ASC) as ds:
        for i in range(elev.shape[0]):
            b = ds.read(1, window=Window(0, i * BLOCK, ds.width, BLOCK), out_dtype="float32")
            b = np.where(b == ds.nodata, np.nan, b)
            rough[i] = block_reduce(b, "std")[0]
    print(f"aggregated {elev.shape}", flush=True)

    valid = np.isfinite(elev)
    # sea / harbour water sits at ~0 m in this DTM; exclude flat zero blocks
    valid = valid & ~(np.nan_to_num(elev, nan=0) <= 0.5)

    # --- relief: max-min in 3x3 block neighbourhood (600 m) ---
    hi = ndimage.maximum_filter(np.where(valid, elev, -1e9), size=3, mode="nearest")
    lo = ndimage.minimum_filter(np.where(valid, elev, 1e9), size=3, mode="nearest")
    relief = (hi - lo).astype(np.float32)
    relief[~valid] = np.nan

    # --- depression filling (iterative) ---
    f = np.where(valid, elev, -1e9)
    for _ in range(40):
        f = np.where(valid, np.maximum(f, ndimage.maximum_filter(f, size=3, mode="nearest")), f)
    print("filled", flush=True)

    # --- D8 flow direction ---
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    dist = np.array([np.sqrt(2), 1, np.sqrt(2), 1, 1, np.sqrt(2), 1, np.sqrt(2)])
    bestslope = np.full(f.shape, -np.inf, dtype=np.float32)
    best = np.full(f.shape, -1, dtype=np.int8)
    rows, cols = np.indices(f.shape)
    rec_r = np.empty(f.shape, dtype=np.int32)
    rec_c = np.empty(f.shape, dtype=np.int32)
    for i, (dr, dc) in enumerate(offs):
        s = (f - np.roll(np.roll(f, dr, axis=0), dc, axis=1)) / (dist[i] * GRID)
        upd = s > bestslope
        bestslope = np.where(upd, s, bestslope)
        best = np.where(upd, np.int8(i), best)
    for i, (dr, dc) in enumerate(offs):
        m = (best == i)
        rec_r[m] = (rows[m] + dr).clip(0, f.shape[0] - 1)
        rec_c[m] = (cols[m] + dc).clip(0, f.shape[1] - 1)
    del bestslope, rows, cols
    print("D8 done", flush=True)

    # --- flow accumulation ---
    order = np.argsort(np.nan_to_num(f, nan=-1e9), axis=None)[::-1]
    acc = np.ones(f.size, dtype=np.float64)
    recv_flat = rec_r.ravel() * f.shape[1] + rec_c.ravel()
    bi = best.ravel()
    vf = valid.ravel()
    for idx in order:
        if not vf[idx] or bi[idx] < 0:
            continue
        acc[recv_flat[idx]] += acc[idx]
    acc = acc.reshape(f.shape)
    print("accumulation done", flush=True)

    with np.errstate(divide="ignore", invalid="ignore"):
        tanb = np.tan(np.radians(slope))
        twi = np.log(np.where(acc * GRID > 0, acc * GRID, np.nan) / np.where(tanb > 1e-6, tanb, np.nan))
    twi[~valid] = np.nan

    # --- SPI: standardised elevation within 3x3 block window ---
    fm = np.where(valid, elev, np.nanmean(elev[valid]))
    m3 = ndimage.uniform_filter(fm, size=3, mode="nearest")
    m3sq = ndimage.uniform_filter(fm ** 2, size=3, mode="nearest")
    s3 = np.sqrt(np.maximum(m3sq - m3 ** 2, 1e-6))
    spi = ((elev - m3) / s3).astype(np.float32)
    spi[~valid] = np.nan
    print("twi/spi done", flush=True)

    with rasterio.open(ASC) as ds:
        x0 = ds.transform.c + (GRID / 2)
        y0 = ds.transform.f - (GRID / 2)

    np.savez_compressed(
        OUT, slope=slope, slope_max=slope_max, slope_p90=slope_p90,
        relief=relief, curv=curv, rough=rough,
        twi=twi.astype(np.float32), spi=spi, elev=elev.astype(np.float32),
        valid=valid, x0=np.float64(x0), y0=np.float64(y0), cell=np.float64(GRID),
    )
    print("wrote", OUT, flush=True)
    print("valid land cells:", int(valid.sum()), "/", valid.size, flush=True)


if __name__ == "__main__":
    main()
