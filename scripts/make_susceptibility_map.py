#!/usr/bin/env python3
"""Render the HK landslide susceptibility map (XGBoost) with the house figure
conventions: Times New Roman, white background, key box, scale bar, north
arrow, source line.

Inputs (built by prep_terrain.py / train_model.py):
  work/terrain_200m.npz     land mask + terrain
  out/susceptibility_grid.csv per-cell probability
  raw/incidents.csv, raw/entli_crown.csv  landslide records
"""
import os
import os, csv
import numpy as np
import matplotlib
GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Rectangle

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
matplotlib.rcParams["font.family"] = ["Times New Roman", "STIX Two Text"]
matplotlib.rcParams["text.parse_math"] = False
matplotlib.rcParams["axes.unicode_minus"] = False

BASE = f"{GIS_DATA}/HK Landslide Susceptibility"
OUT = os.path.join(BASE, "out", "landslide_susceptibility_map.png")

# ------------------------------------------------------------------ data
tz = np.load(os.path.join(BASE, "work", "terrain_200m.npz"))
CELL = float(tz["cell"]); X0 = float(tz["x0"]); Y0 = float(tz["y0"])
valid = tz["valid"]
NY, NX = valid.shape

grid = [r for r in csv.DictReader(open(os.path.join(BASE, "out", "susceptibility_grid.csv"), encoding="utf-8")) if r["susceptibility"] not in ("", "nan")]
prob = np.full((NY, NX), np.nan)
for r in grid:
    prob[int(r["row"]), int(r["col"])] = float(r["susceptibility"])

# known landslide records (for the overlay + the key statistics)
inc = list(csv.DictReader(open(os.path.join(BASE, "raw", "incidents.csv"), encoding="utf-8")))
ent = list(csv.DictReader(open(os.path.join(BASE, "raw", "entli_crown.csv"), encoding="utf-8")))
pts = []
for r in inc:
    try:
        pts.append((float(r["EASTING"]), float(r["NORTHING"])))
    except (TypeError, ValueError):
        pass
for r in ent:
    try:
        pts.append((float(r["EASTING"]), float(r["NORTHING"])))
    except (TypeError, ValueError):
        pass
pts = np.array(pts)

# susceptibility classes: quintiles of the scored area
vals = prob[~np.isnan(prob)]
qs = np.percentile(vals, [20, 40, 60, 80])
edges = [0.0] + [float(q) for q in qs] + [1.0001]
labels = ["Very low", "Low", "Moderate", "High", "Very high"]
colors = ["#f7f7f2", "#fee8a6", "#fdbb84", "#e34a33", "#7f0000"]
cmap = ListedColormap(colors)
norm = BoundaryNorm(edges, cmap.N)

# class statistics over the WHOLE grid
cls_grid = np.digitize(prob, qs)
land = np.isfinite(prob)
nland = int(land.sum())
# a cell is "known landslide" if a record falls in it.
# The cell centre is at easting = X0 + col*CELL, northing = Y0 - row*CELL, so
# the containing cell is found by rounding to the NEAREST centre.
rec = np.zeros((NY, NX), dtype=bool)
for x, y in pts:
    c = int((x - X0) / CELL + 0.5)
    r = int((Y0 - y) / CELL + 0.5)
    if 0 <= r < NY and 0 <= c < NX:
        rec[int(r), int(c)] = True
stats = []
for k in range(5):
    m = (cls_grid == k) & land
    n = int(m.sum())
    hits = int((m & rec).sum())
    stats.append((labels[k], n, 100 * n / nland, hits))
# territory-wide landslide rate (per 1,000 land cells) and total hits, used for
# the "risk relative to average" column
total_hits = int((rec & land).sum())
overall_rate = total_hits / nland * 1000
print(f"land cells {nland}, landslide cells {total_hits}, "
      f"overall rate {overall_rate:.1f} per 1000 cells")

# ------------------------------------------------------------------ figure
x_min = X0 - CELL / 2
x_max = X0 + (NX - 1) * CELL + CELL / 2
y_min = Y0 - (NY - 1) * CELL - CELL / 2
y_max = Y0 + CELL / 2
aspect = (y_max - y_min) / (x_max - x_min)

fig = plt.figure(figsize=(11.6, 9.4), dpi=200)
gs = fig.add_gridspec(2, 1, height_ratios=[3.0, 1.22], hspace=0.10,
                      left=0.045, right=0.975, top=0.905, bottom=0.125)
ax = fig.add_subplot(gs[0])
axk = fig.add_subplot(gs[1])
axk.axis("off")

fig.text(0.045, 0.963, "Landslide susceptibility of Hong Kong",
         fontfamily="Times New Roman", fontsize=19, ha="left", va="center")
fig.text(0.045, 0.932,
         "XGBoost model on 200 m cells: terrain, land-cover and weathering-susceptibility "
         "predictors, trained on 19,332 cells with a recorded landslide",
         fontfamily="Times New Roman", fontsize=11.5, ha="left", va="center",
         color="#444444")

# land base + susceptibility
ax.set_facecolor("#eef3f7")
masked = np.ma.masked_invalid(prob)
im = ax.imshow(masked, cmap=cmap, norm=norm, origin="upper",
               extent=(x_min, x_max, y_min, y_max),
               interpolation="nearest", zorder=2)
# coastline-ish land edge
land_edge = valid.astype(float)
ax.contour(x_min + (np.arange(NX) + 0.5) * CELL,
           y_max - (np.arange(NY) + 0.5) * CELL,
           land_edge, levels=[0.5], colors="#5b6770", linewidths=0.7, zorder=3)

# landslide points
ax.scatter(pts[:, 0], pts[:, 1], s=1.6, c="#111111", alpha=0.55,
           linewidths=0, zorder=5, rasterized=True)

ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)
ax.set_aspect("equal")
ax.set_autoscale_on(False)
ax.tick_params(labelsize=9, colors="#333333")
ax.set_xlabel("Easting (Hong Kong 1980 Grid, metres)", fontsize=10.5, labelpad=4)
ax.set_ylabel("Northing (Hong Kong 1980 Grid, metres)", fontsize=10.5, labelpad=4)
for s in ax.spines.values():
    s.set_color("#999999"); s.set_linewidth(0.8)

# scale bar
sb_x, sb_y = x_min + 3500, y_min + 3200
sb_len = 10000
ax.plot([sb_x, sb_x + sb_len], [sb_y, sb_y], color="#222222", lw=3.0,
        solid_capstyle="butt", zorder=10)
for xx in (sb_x, sb_x + sb_len):
    ax.plot([xx, xx], [sb_y - 320, sb_y + 320], color="#222222", lw=1.6, zorder=10)
ax.text(sb_x + sb_len / 2, sb_y + 780, "10 km", ha="center", va="bottom",
        fontsize=10, family="Times New Roman", zorder=11,
        bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.5))

# north arrow
nx, ny = x_max - 2600, y_min + 5200
ax.annotate("", xy=(nx, ny + 2100), xytext=(nx, ny),
            arrowprops=dict(arrowstyle="-|>", color="#222222", lw=1.7), zorder=10)
ax.text(nx, ny + 2450, "N", ha="center", va="bottom", fontsize=12,
        family="Times New Roman", zorder=11,
        bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.5))

# ------------------------------------------------------------------ key
# The classes are EQUAL-AREA QUINTILES of the model score, so "% of land" is
# 20% by construction and carries no information.  The informative columns are
# the share of all recorded landslide cells and the LIFT (landslide rate
# relative to the territory average) - so those are what the key carries.
axk.text(0.0, 0.98, "Key", fontfamily="Times New Roman", fontsize=13,
         ha="left", va="top", transform=axk.transAxes)
axk.text(0.0, 0.84,
         "Susceptibility class (equal-area fifth of the model score)          "
         "landslide cells      % of all landslides      risk relative to average",
         fontfamily="Times New Roman", fontsize=9.6, ha="left", va="top",
         transform=axk.transAxes, color="#333333")
y = 0.70
for (lab, n, pct, hits), col in zip(stats, colors):
    rate = hits / n * 1000
    lift = rate / overall_rate
    axk.add_patch(Rectangle((0.005, y - 0.055), 0.022, 0.075, transform=axk.transAxes,
                             facecolor=col, edgecolor="#666666", linewidth=0.7))
    axk.text(0.040, y - 0.018, lab, fontfamily="Times New Roman", fontsize=10.5,
             ha="left", va="center", transform=axk.transAxes)
    axk.text(0.370, y - 0.018, f"{hits:,}", fontfamily="Times New Roman",
             fontsize=10.5, ha="right", va="center", transform=axk.transAxes)
    axk.text(0.500, y - 0.018, f"{100*hits/total_hits:.1f}%",
             fontfamily="Times New Roman", fontsize=10.5, ha="right",
             va="center", transform=axk.transAxes)
    axk.text(0.600, y - 0.018, f"{lift:.2f}x", fontfamily="Times New Roman",
             fontsize=10.5, ha="right", va="center", transform=axk.transAxes)
    y -= 0.125

axk.text(0.040, y + 0.015,
         f"Each class holds 20% of the land by construction (equal-area quintiles). "
         f"Risk = landslide cells per 1,000 land cells, relative to the "
         f"territory average of {overall_rate:.0f} per 1,000.",
         fontfamily="Times New Roman", fontsize=9.2, ha="left", va="center",
         transform=axk.transAxes, color="#333333", style="italic")
y -= 0.09

axk.scatter([0.008], [y - 0.02], s=9, c="#111111", alpha=0.6,
            transform=axk.transAxes, clip_on=False)
axk.text(0.040, y - 0.038, "Recorded landslide (incident and historical inventory)",
         fontfamily="Times New Roman", fontsize=10.5, ha="left", va="center",
         transform=axk.transAxes)
y -= 0.10
axk.plot([0.008, 0.024], [y - 0.02, y - 0.02], color="#5b6770", lw=1.2,
         transform=axk.transAxes, clip_on=False)
axk.text(0.040, y - 0.038, "Land boundary", fontfamily="Times New Roman",
         fontsize=10.5, ha="left", va="center", transform=axk.transAxes)

fig.text(0.045, 0.012,
         "Source: LandsD Digital Terrain Model 5 m; CEDD Location of Landslide Incidents (CSDI) and\n"
         "Enhanced Natural Terrain Landslide Inventory; ESA WorldCover 2021; CEDD Geological Map\n"
         "(weathering susceptibility derived from lithology). Model: XGBoost, 5-fold spatial blocked\n"
         "cross-validation (5 km blocks), ROC-AUC 0.88.",
         fontfamily="Times New Roman", fontsize=8.6, ha="left", va="bottom",
         color="#333333", linespacing=1.35)

fig.savefig(OUT, dpi=200, facecolor="white")
print("wrote", OUT, os.path.getsize(OUT), "bytes")
print("class stats:")
for s in stats:
    print("  ", s)
