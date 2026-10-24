#!/usr/bin/env python3
"""Quick-look map for the HK volleyball-court dataset (verification, not a deliverable)."""
import json
import os

import matplotlib
from matplotlib import font_manager

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
matplotlib.rcParams["font.family"] = "Times New Roman"
import matplotlib.pyplot as plt

D = os.path.dirname(os.path.abspath(__file__))
ven = json.load(open(os.path.join(D, "venues.geojson")))["features"]
fre = json.load(open(os.path.join(D, "free_outdoor_courts.geojson")))["features"]
ses = json.load(open(os.path.join(D, "sessions.geojson")))["features"]

lons = [f["geometry"]["coordinates"][0] for f in ven]
lats = [f["geometry"]["coordinates"][1] for f in ven]
lon0, lon1 = min(lons) - 0.02, max(lons) + 0.02
lat0, lat1 = min(lats) - 0.02, max(lats) + 0.02

# vacancy share per venue over the booking window
from collections import defaultdict

vac = defaultdict(lambda: [0, 0])
for f in ses:
    p = f["properties"]
    vac[p["venue_name_en"]][1] += 1
    if p["available_courts"] > 0:
        vac[p["venue_name_en"]][0] += 1

import math

# 1 deg lon = 111.32*cos(lat) km; 1 deg lat = 110.57 km. Aspect is the physical
# y:x ratio so the panel is not stretched.
KM_LON = 111.32 * math.cos(math.radians((lat0 + lat1) / 2))
KM_LAT = 110.57

fig, ax = plt.subplots(figsize=(9, 9.5))
ax.set_xlim(lon0, lon1)
ax.set_ylim(lat0, lat1)
# matplotlib's aspect compares y-units to x-units, so it takes the degree spans
# over the km-per-degree ratio to make the panel geographically square.
ax.set_aspect((KM_LAT / KM_LON) * ((lon1 - lon0) / (lat1 - lat0)))
ax.set_facecolor("#dfe9f2")
ax.grid(True, color="#b9c9d6", lw=0.4, zorder=0)

ax.scatter([f["geometry"]["coordinates"][0] for f in fre],
           [f["geometry"]["coordinates"][1] for f in fre],
           marker="^", s=26, c="#8a6d3b", edgecolor="white", lw=0.4,
           label=f"free outdoor / beach courts ({len(fre)})", zorder=3)

sc = ax.scatter([f["geometry"]["coordinates"][0] for f in ven],
                [f["geometry"]["coordinates"][1] for f in ven],
                s=52, c="white", edgecolor="#333", lw=0.7, zorder=4)
sc.set_array([vac[f["properties"]["venue_name_en"]][0] /
              max(vac[f["properties"]["venue_name_en"]][1], 1) * 100 for f in ven])
cb = fig.colorbar(sc, ax=ax, fraction=0.035, pad=0.02)
cb.set_label("% of bookable sessions with vacancy (8-day window)", fontsize=8)
cb.ax.tick_params(labelsize=7)

ax.set_xticks([113.95, 114.05, 114.15, 114.25])
ax.set_yticks([22.2, 22.3, 22.4, 22.5])
ax.tick_params(labelsize=8)
ax.set_title("HK LCSD volleyball courts — venue, price band and live vacancy\n"
             "quick-look check (not a teaching figure)",
             fontsize=11, pad=12)
ax.legend(loc="lower left", fontsize=8, framealpha=0.95)

src = ("Sources: LCSD SmartPLAY available-session feed (fetched 2026-10-22, 13,152 session records); "
       "LCSD CSDI free outdoor & beach volleyball courts; LCSD hire charges 2026.")
fig.text(0.01, 0.012, src, fontsize=6.5, wrap=True)

fig.tight_layout(rect=[0, 0.035, 1, 1])
out = os.path.join(D, "quicklook_map.png")
fig.canvas.draw()
import numpy as np
from PIL import Image

buf = np.ascontiguousarray(np.asarray(fig.canvas.buffer_rgba()).copy())
Image.fromarray(buf, "RGBA").convert("RGB").save(out)
print("wrote", out, "venues", len(ven), "free", len(fre), "sessions", len(ses))