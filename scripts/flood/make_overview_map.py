#!/usr/bin/env python3
"""
Build the overview map for the HK flood-prone-areas study.

Inputs (all fetched live and verified - see NOTES.md):
  dsd_blockage.geojson   226 points  DSD "Locations Prone to Blockage"
  dsd_works.geojson       15 points  DSD "Drainage Improvement Works in Progress"
  dsd_coastal.geojson     26 points  DSD/CEDD "Coastal Low-lying or Windy Residential Areas"
  support/landsd_land_boundary.json  4709 polygons (land mask)
  support/dsd_engineered_channel.json 2719 lines
  support/dsd_channel.json            9247 lines

House style: Times New Roman, white background, key below the map, source line.
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

W = os.path.dirname(os.path.abspath(__file__))

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["text.parse_math"] = False

LON0, LON1 = 113.83, 114.45
LAT0, LAT1 = 22.15, 22.60

COL = {
    "blockage": "#C0392B",
    "works": "#E67E22",
    "coastal": "#1F6FB4",
    "channel": "#7F8C8D",
    "land": "#EDE7DC",
    "sea": "#FFFFFF",
}


def load(name):
    with open(os.path.join(W, name), encoding="utf-8") as fh:
        return json.load(fh)["features"]


def rings(feat):
    g = feat["geometry"]
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    return []


def build():
    land = load("support/landsd_land_boundary.json")
    channels = load("support/dsd_channel.json")
    eng = load("support/dsd_engineered_channel.json")
    blockage = load("dsd_blockage.geojson")
    works = load("dsd_works.geojson")
    coastal = load("dsd_coastal.geojson")

    fig = plt.figure(figsize=(11.0, 9.4))
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(2, 1, height_ratios=[9.6, 1.9], hspace=0.40,
                          left=0.065, right=0.985, top=0.905, bottom=0.055)
    ax = fig.add_subplot(gs[0])
    axk = fig.add_subplot(gs[1])
    axk.axis("off")

    ax.set_facecolor(COL["sea"])

    # --- land mask (drawn first, base) ---
    for feat in land:
        for poly in rings(feat):
            xs = [c[0] for c in poly[0]]
            ys = [c[1] for c in poly[0]]
            ax.fill(xs, ys, facecolor=COL["land"], edgecolor="none", zorder=1)

    # --- drainage channels ---
    for feat in channels + eng:
        g = feat["geometry"]
        lines = [g["coordinates"]] if g["type"] == "LineString" else g.get("coordinates", [])
        for ln in lines:
            if len(ln) < 2:
                continue
            ax.plot([c[0] for c in ln], [c[1] for c in ln],
                    color=COL["channel"], lw=0.35, alpha=0.75, zorder=2, solid_capstyle="round")

    def pts(feats):
        return ([f["geometry"]["coordinates"][0] for f in feats],
                [f["geometry"]["coordinates"][1] for f in feats])

    bx, by = pts(blockage)
    wx, wy = pts(works)
    cx, cy = pts(coastal)

    ax.scatter(bx, by, s=9, c=COL["blockage"], marker="o",
               linewidths=0.30, edgecolors="white", zorder=6)
    ax.scatter(wx, wy, s=34, c=COL["works"], marker="s",
               linewidths=0.40, edgecolors="white", zorder=7)
    ax.scatter(cx, cy, s=52, c=COL["coastal"], marker="^",
               linewidths=0.45, edgecolors="white", zorder=8)

    ax.set_xlim(LON0, LON1)
    ax.set_ylim(LAT0, LAT1)
    ax.set_aspect(1.0 / math.cos(math.radians(22.35)))
    ax.set_autoscale_on(False)
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    ax.tick_params(labelsize=9)
    ax.grid(True, lw=0.35, color="#C9C9C9", alpha=0.65, zorder=0)
    for s in ax.spines.values():
        s.set_linewidth(0.8)
        s.set_color("#444444")

    ax.set_xlabel("Longitude (°E)", fontsize=10)
    ax.set_ylabel("Latitude (°N)", fontsize=10)

    # scale bar (10 km)
    lat0 = (LAT0 + LAT1) / 2
    km_per_deg_lon = 111.32 * __import__("math").cos(__import__("math").radians(lat0))
    bar_deg = 10.0 / km_per_deg_lon
    x0 = LON0 + 0.035
    y0 = LAT0 + 0.035
    ax.plot([x0, x0 + bar_deg], [y0, y0], color="#111111", lw=3.0,
            solid_capstyle="butt", zorder=12)
    ax.text(x0 + bar_deg / 2, y0 + 0.012, "10 km", fontsize=9, ha="center",
            va="bottom", zorder=13,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.2))

    # north arrow
    nx, ny = LON1 - 0.055, LAT1 - 0.055
    ax.annotate("", xy=(nx, ny), xytext=(nx, ny - 0.038),
                arrowprops=dict(arrowstyle="-|>", color="#111111", lw=1.8), zorder=12)
    ax.text(nx, ny - 0.052, "N", fontsize=10, ha="center", va="top",
            fontweight="bold", zorder=13,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.2))

    # --- titles ---
    fig.text(0.065, 0.962, "Flood-prone areas in Hong Kong",
             fontsize=17, ha="left", va="top", fontweight="bold")
    fig.text(0.065, 0.928,
             "Drainage Services Department designated flood-prone areas and the supporting drainage network",
             fontsize=10.5, ha="left", va="top", color="#333333")

    # --- key ---
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COL["blockage"],
               markeredgecolor="white", markersize=5.0,
               label="Location prone to blockage (226)"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor=COL["works"],
               markeredgecolor="white", markersize=7.0,
               label="Drainage improvement works in progress (15)"),
        Line2D([0], [0], marker="^", color="none", markerfacecolor=COL["coastal"],
               markeredgecolor="white", markersize=8.0,
               label="Coastal low-lying or windy residential area (26)"),
        Line2D([0], [0], color=COL["channel"], lw=1.0,
               label="Drainage channel (DSD)"),
        Patch(facecolor=COL["land"], edgecolor="none", label="Land (LandsD iC1000)"),
    ]
    leg = axk.legend(handles=handles, loc="upper left", ncol=3, frameon=False,
                     fontsize=9.5, handletextpad=0.7, columnspacing=2.2,
                     bbox_to_anchor=(0.0, 1.30))
    for t in leg.get_texts():
        t.set_color("#111111")

    fig.text(0.065, 0.012,
             "Source: Drainage Services Department (DSD) flood-prone areas; "
             "LandsD Digital Land Boundary Map iC1000; DSD drainage channel records. "
             "Points mark the location of each designated area, not its extent.",
             fontsize=7.6, ha="left", va="bottom", color="#444444")

    out = os.path.join(W, "flood_prone_areas_overview.png")
    fig.savefig(out, dpi=200, facecolor="white")

    # --- Step 3 gate: run the overlap check on the renderer, not by eye ---
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []
    for t in fig.findobj(matplotlib.text.Text):
        if not t.get_text().strip():
            continue
        try:
            bb = t.get_window_extent(renderer=renderer)
        except Exception:
            continue
        if bb.width <= 0 or bb.height <= 0:
            continue
        boxes.append((t.get_text()[:44], bb))
    problems = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            ox = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
            oy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
            if ox * oy > 4.0:
                problems.append((boxes[i][0], boxes[j][0], round(ox * oy, 1)))
    W_, H_ = fig.canvas.get_width_height()
    off = []
    for label, bb in boxes:
        if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > W_ + 2 or bb.y1 > H_ + 2:
            off.append(label)
    print(f"text boxes: {len(boxes)} | overlaps: {len(problems)} | off-canvas: {len(off)}")
    for p in problems:
        print("  OVERLAP:", p)
    for o in off:
        print("  OFF-CANVAS:", o)
    assert not problems, "text overlap detected"
    assert not off, "text clipped off canvas"

    print("wrote", out)
    print("counts: blockage", len(blockage), "works", len(works), "coastal", len(coastal))


if __name__ == "__main__":
    build()
