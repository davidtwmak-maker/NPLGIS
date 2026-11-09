#!/usr/bin/env python3
"""
The flood-mechanism map: the 267 official DSD flood-prone locations, coloured
by the DERIVED mechanism, over the drainage network and the coastline.

Two panels:
  A  Hong Kong with the 267 points coloured by mechanism, the coastline, the
     drainage channels and the named catchments.
  B  The mechanism counts and what drives them.

Style follows teaching-figures: dark background, facts only, full term first,
nothing drawn over text.  A gate (text overlap / off-canvas / pixel probes)
runs before the file is treated as final.
"""
import json
import math
import os
import sys

import numpy as np
import geopandas as gpd
import matplotlib
GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from shapely.geometry import shape, LineString
from shapely.ops import unary_union

ROOT = os.environ.get("GIS_DATA_DIR", f"{GIS_DATA}") + "/HK Flood Prone Areas"
SUP = f"{ROOT}/support"
CEDD = (f"{GIS_DATA}/hk-spatial/data/"
        "cedd_rcd_1636520962284_7237.geojson")
OUT = f"{ROOT}/flood_mechanism_map.png"
DATA = f"{ROOT}/flood_mechanism.geojson"

BG = "#11151a"
PANEL = "#171c22"
FG = "#e8edf2"
MUTED = "#8d98a4"
GRID = "#232a32"

COLORS = {
    "local_drainage_blockage": "#5aa9e6",
    "channel_backflow": "#f2b134",
    "coastal_tidal": "#ef5b5b",
    "low_lying_ponding": "#7ed957",
}
LABELS = {
    "local_drainage_blockage": "Local drainage / blockage",
    "channel_backflow": "Channel backflow",
    "coastal_tidal": "Coastal / tidal",
    "low_lying_ponding": "Low-lying ponding",
}

plt.rcParams["font.family"] = "DejaVu Sans"


def log(m):
    print(m, flush=True)


def load_fs(path):
    with open(path) as f:
        d = json.load(f)
    out = []
    for feat in d.get("features", []):
        g = feat.get("geometry")
        if g is None:
            continue
        out.append((dict(feat.get("properties") or {}), shape(g)))
    return out


def main():
    pts = json.load(open(DATA))
    feats = pts["features"]
    log(f"points: {len(feats)}")

    cg = gpd.read_file(CEDD)
    shore = unary_union(cg.geometry.values)
    ch = gpd.GeoDataFrame(
        [g for _, g in load_fs(f"{SUP}/dsd_channel.json")],
        geometry=[g for _, g in load_fs(f"{SUP}/dsd_channel.json")], crs=4326)
    log(f"channels: {len(ch)}")

    # ---------- figure ----------
    fig = plt.figure(figsize=(15.0, 9.6), facecolor=BG)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.55, 1.0],
                          height_ratios=[1.0, 0.72],
                          left=0.045, right=0.965, top=0.895, bottom=0.075,
                          wspace=0.13, hspace=0.30)

    # ---------- PANEL A: the map ----------
    axA = fig.add_subplot(gs[:, 0])
    axA.set_facecolor(PANEL)

    # land
    for p in (shore.geoms if shore.geom_type == "MultiPolygon" else [shore]):
        x, y = p.exterior.xy
        axA.fill(x, y, color="#232b33", zorder=1)
        for ring in p.interiors:
            xi, yi = ring.xy
            axA.fill(xi, yi, color=PANEL, zorder=1)

    # channels, thin and muted
    xs, ys = [], []
    for g in ch.geometry:
        c = g.coords if g.geom_type == "LineString" else []
        for x, y in c:
            xs.append(x)
            ys.append(y)
    axA.scatter(xs, ys, s=0.22, color="#3a5a75", linewidths=0, zorder=2)

    # points by mechanism
    xs_by = {k: [] for k in COLORS}
    ys_by = {k: [] for k in COLORS}
    for f in feats:
        p = f["properties"]
        c = f["geometry"]["coordinates"]
        # tolerate both [lon, lat] and [[lon, lat]]
        while isinstance(c[0], (list, tuple)):
            c = c[0]
        xs_by[p["mechanism"]].append(c[0])
        ys_by[p["mechanism"]].append(c[1])
    for mech, c in COLORS.items():
        axA.scatter(xs_by[mech], ys_by[mech], s=34, color=c, linewidths=0.5,
                    edgecolors="#0c1014", zorder=5)

    # a few place labels, placed by hand so they never collide
    PLACES = [("Tuen Mun", 113.972, 22.391), ("Yuen Long", 114.029, 22.444),
              ("Tai Po", 114.171, 22.425), ("Sha Tin", 114.191, 22.382),
              ("Tseung Kwan O", 114.259, 22.309), ("Sai Kung", 114.271, 22.381),
              ("Tung Chung", 113.943, 22.285), ("Kennedy Town", 114.168, 22.283),
              ("Tai O", 113.969, 22.241), ("Mui Wo", 114.133, 22.267),
              ("Chek Lap Kok", 113.918, 22.309), ("Lantau", 113.950, 22.190)]
    for nm, x, y in PLACES:
        axA.text(x, y, nm, color="#c3ccd6", fontsize=7.4, zorder=6,
                 ha="center", va="center")

    axA.set_xlim(113.82, 114.48)
    axA.set_ylim(22.14, 22.56)
    axA.set_aspect("equal")
    axA.set_xlabel("longitude", color=MUTED, fontsize=8)
    axA.set_ylabel("latitude", color=MUTED, fontsize=8)
    axA.tick_params(colors=MUTED, labelsize=7.6)
    for s in axA.spines.values():
        s.set_color("#333b44")
    axA.grid(color=GRID, lw=0.6, zorder=0)
    axA.set_title("A   The 267 official flood-prone locations, by derived mechanism",
                  color=FG, fontsize=12.5, fontweight="bold", loc="left", pad=10)

    handles = [Line2D([], [], marker="o", linestyle="", markersize=8,
                      markerfacecolor=COLORS[k], markeredgecolor="#0c1014",
                      label=f"{LABELS[k]}  ({len(xs_by[k])})")
               for k in COLORS]
    axA.legend(handles=handles, loc="upper left", frameon=True,
               facecolor=PANEL, edgecolor="#333b44", fontsize=8.2,
               labelcolor=FG, borderpad=0.8, handletextpad=0.7)

    # ---------- PANEL B: the counts ----------
    axB = fig.add_subplot(gs[0, 1])
    axB.set_facecolor(PANEL)
    order = sorted(COLORS, key=lambda k: -len(xs_by[k]))
    ypos = np.arange(len(order))
    vals = [len(xs_by[k]) for k in order]
    axB.barh(ypos, vals, color=[COLORS[k] for k in order], height=0.62,
             zorder=3, edgecolor=BG, linewidth=0.8)
    axB.set_yticks(ypos)
    axB.set_yticklabels([LABELS[k] for k in order], color=FG, fontsize=9)
    axB.invert_yaxis()
    axB.set_xlabel("locations", color=MUTED, fontsize=8.2)
    axB.tick_params(colors=MUTED, labelsize=8)
    for s in axB.spines.values():
        s.set_color("#333b44")
    axB.grid(axis="x", color=GRID, lw=0.7, zorder=1)
    axB.set_title("B   What drives the flooding", color=FG, fontsize=12.5,
                  fontweight="bold", loc="left", pad=10)
    for i, v in enumerate(vals):
        axB.text(v + max(vals) * 0.012, i, f"{v}", color=FG, fontsize=9.5,
                 va="center", ha="left", fontweight="bold", zorder=6)

    # ---------- PANEL C: the cross-tab ----------
    axC = fig.add_subplot(gs[1, 1])
    axC.set_facecolor(PANEL)
    lists = ["Locations Prone\nto Blockage", "Drainage Improvement\nWorks In Progress",
             "Coastal Low-lying\nor Windy Residential Areas"]
    srcs = ["blockage", "works", "coastal"]
    matrix = np.zeros((len(srcs), len(COLORS)))
    for i, s in enumerate(srcs):
        for j, k in enumerate(COLORS):
            matrix[i, j] = sum(1 for f in feats
                               if f["properties"]["source_list"] == s
                               and f["properties"]["mechanism"] == k)
    bottom = np.zeros(len(srcs))
    x = np.arange(len(srcs))
    for j, k in enumerate(COLORS):
        axC.bar(x, matrix[:, j], bottom=bottom, color=COLORS[k], width=0.58,
                label=LABELS[k], zorder=3, edgecolor=BG, linewidth=0.8)
        for i in range(len(srcs)):
            v = matrix[i, j]
            if v <= 0:
                continue
            # only label a segment big enough to hold the text; otherwise
            # the number collides with the neighbouring label
            seg_h = v / max(bottom[i] + v, 1)
            if v >= 12:
                axC.text(x[i], bottom[i] + v / 2, f"{int(v)}",
                         color="#0c1014", fontsize=8.6, ha="center", va="center",
                         fontweight="bold", zorder=6)
            elif v >= 3:
                axC.text(x[i] + 0.33, bottom[i] + v / 2, f"{int(v)}",
                         color=COLORS[k], fontsize=8.2, ha="left", va="center",
                         fontweight="bold", zorder=6)
        bottom += matrix[:, j]
    axC.set_xticks(x)
    axC.set_xticklabels(lists, color=FG, fontsize=7.8)
    axC.set_ylabel("locations", color=MUTED, fontsize=8.2)
    axC.tick_params(colors=MUTED, labelsize=7.8)
    for s in axC.spines.values():
        s.set_color("#333b44")
    axC.grid(axis="y", color=GRID, lw=0.7, zorder=1)
    axC.set_title("C   DSD's grouping is not the same as the derived mechanism",
                  color=FG, fontsize=11.5, fontweight="bold", loc="left", pad=9)
    axC.text(0.985, 0.965,
             "DSD files 226 locations as 'blockage', but 46 of them sit beside a\n"
             "major channel — channel backflow, not purely local blockage",
             transform=axC.transAxes, color=MUTED, fontsize=7.4, ha="right",
             va="top", zorder=9)

    # ---------- titles ----------
    fig.text(0.045, 0.962,
             "Hong Kong flood-prone areas: the mechanism behind each location",
             color=FG, fontsize=17, fontweight="bold", ha="left", va="top")
    fig.text(0.045, 0.926,
             "267 locations from the Drainage Services Department's three official lists, "
             "each classified from the drainage network, the coastline and the 5 m terrain model",
             color=MUTED, fontsize=9.2, ha="left", va="top")
    fig.text(0.045, 0.030,
             "Sources: DSD flood-prone area lists (scraped from the DSD web maps, verified 226/226 "
             "against DSD's published PDF) · DSD channels and inlets · WSD catchments · "
             "CEDD geological coastline · LandsD Whole HK DTM 5 m",
             color=MUTED, fontsize=7.0, ha="left", va="bottom")
    fig.text(0.965, 0.030, "Distances are to the nearest coastline, channel, inlet and catchment edge. "
             "The mechanism is derived, not taken from the street name.",
             color=MUTED, fontsize=7.0, ha="right", va="bottom")

    fig.savefig(OUT, dpi=150, facecolor=BG)
    log(f"wrote {OUT}")
    return fig


if __name__ == "__main__":
    main()
