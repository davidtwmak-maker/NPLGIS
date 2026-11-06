#!/usr/bin/env python3
"""
Test slope definition against the recorded landslide incidents.

The >30 degree threshold is ambiguous: "slope" can mean the MEAN gradient of a
cell, or the MAXIMUM gradient anywhere in it. The published landslide work
already showed these differ enormously (mean slope puts 100% of incidents
under 30 deg). This script measures the difference on the 20 m grid and
against the real incident locations, so the >30 degree polygon layer is built
on a defensible definition.

Outputs: work/slope30_definition_test.json
"""
import json
import os

import geopandas as gpd
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
d = np.load(os.path.join(BASE, "work", "terrain_20m.npz"))
valid = d["valid"]
slope_mean = d["slope"]
slope_max = d["slope_max"]
cell = float(d["cell"])
x0 = float(d["x0"])
y0 = float(d["y0"])
H, W = valid.shape

nv = int(valid.sum())
cell_area = cell * cell
land_area = nv * cell_area

# --- incident points -> 20 m cell index (round to NEAREST centre) ---
g = gpd.read_file(os.path.join(BASE, "out", "landslide_records.geojson"))
gx = g.geometry.x.to_numpy()
gy = g.geometry.y.to_numpy()
col = np.floor((gx - x0) / cell + 0.5).astype(int)
row = np.floor((y0 - gy) / cell + 0.5).astype(int)
ok = (col >= 0) & (col < W) & (row >= 0) & (row < H)
col, row = col[ok], row[ok]
inc_cell = valid[row, col]
print(f"incidents {len(g):,} | inside grid {ok.sum():,} | on valid land cell {inc_cell.sum():,}")

res = {"grid_m": cell, "dims": [W, H], "valid_cells": nv,
       "land_area_km2": round(land_area / 1e6, 1),
       "incidents_total": int(len(g)),
       "incidents_on_valid_land": int(inc_cell.sum())}

# ---- area share of each definition ----
areas = {}
for name, arr in [("slope_mean", slope_mean), ("slope_max", slope_max)]:
    areas[name] = {}
    for th in [30, 35, 45]:
        m = valid & (arr > th)
        a = int(m.sum()) * cell_area
        areas[name][f">{th}"] = {
            "cells": int(m.sum()),
            "area_km2": round(a / 1e6, 1),
            "pct_of_land": round(a / land_area * 100, 2),
        }
res["area_share"] = areas

# ---- incident distribution ----
inc = {}
for name, arr in [("slope_mean", slope_mean), ("slope_max", slope_max)]:
    inc[name] = {}
    for th in [30, 35, 45]:
        m = arr[row, col] > th
        n = int(m.sum())
        inc[name][f">{th}"] = {
            "incidents": n,
            "pct_of_incidents": round(n / int(inc_cell.sum()) * 100, 2),
        }
res["incident_share"] = inc

# ---- area-normalised rate: the honest comparison ----
rate = {}
for name, arr in [("slope_mean", slope_mean), ("slope_max", slope_max)]:
    rate[name] = {}
    for th in [30, 35, 45]:
        m = valid & (arr > th)
        n_cells = int(m.sum())
        land_share = n_cells / nv
        inc_share = inc[name][f">{th}"]["pct_of_incidents"] / 100
        rate[name][f">{th}"] = {
            "land_share_pct": round(land_share * 100, 2),
            "incident_share_pct": round(inc_share * 100, 2),
            "rate_ratio_vs_average": round(inc_share / land_share, 2) if land_share > 0 else None,
        }
res["area_normalised_rate"] = rate

# ---- which definition do the incidents actually sit on? ----
sv_mean = slope_mean[row, col]
sv_max = slope_max[row, col]
for label, sv in [("mean", sv_mean), ("max", sv_max)]:
    q = {f"p{q}": float(np.nanpercentile(sv, q)) for q in (10, 25, 50, 75, 90, 99)}
    res[f"incident_slope_{label}_deg"] = {**q, "mean": float(np.nanmean(sv))}
    res[f"incident_slope_{label}_over30_pct"] = round(float(np.nanmean(sv > 30) * 100), 2)
    res[f"incident_slope_{label}_over45_pct"] = round(float(np.nanmean(sv > 45) * 100), 2)

# ---- the case that matters: a steep scarp inside a gently-sloping cell ----
# For every incident, how much steeper is the maximum than the mean of its cell?
gap = sv_max - sv_mean
res["inc_max_minus_mean_gap"] = {
    "median_deg": float(np.nanmedian(gap)),
    "mean_deg": float(np.nanmean(gap)),
    "p90_deg": float(np.nanpercentile(gap, 90)),
    "max_deg": float(np.nanmax(gap)),
}
res["incidents_whose_cell_mean_under30_but_max_over30"] = int(
    np.sum((sv_mean < 30) & (sv_max > 30))
)

with open(os.path.join(BASE, "work", "slope30_definition_test.json"), "w") as fh:
    json.dump(res, fh, indent=2)
print(json.dumps(res, indent=2))
