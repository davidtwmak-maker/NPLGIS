#!/usr/bin/env python3
"""
The map for the Hong Kong low-lying land (< 5 m).

DSE-standard white background, Times New Roman, a key, a scale bar, a
north arrow and a source line.

Layers, bottom to top:
  1. the land (light grey)
  2. the land below 5 m (blue), with the ten biggest patches labelled
  3. the named places that anchor the reader

Run:  python3 make_lowland_map.py
"""
import json
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
import numpy as np
import rasterio
from matplotlib.patches import Polygon as MplPoly, Patch, FancyArrow, Rectangle
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
from pyproj import Transformer

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DTM = os.environ.get(
    "HK_DTM_TIF",
    os.path.join(GIS_DATA, "HK Landslide Susceptibility", "raw",
                 "Whole_HK_DTM_5m.tif"))
if not os.path.exists(DTM):
    for _c in (os.path.join(GIS_DATA, "HK Flood Causes", "raw",
                            "Whole_HK_DTM_5m.tif"),
               "/Volumes/Extreme Pro/Download/HK DTM 5m/Whole_HK_DTM_5m.tif"):
        if os.path.exists(_c):
            DTM = _c
            break
MASK = os.path.join(OUT, "hk_land_mask.npy")
PNG = os.path.join(OUT, "hk_lowland_under5m_map.png")

# the house font, registered before pyplot
for f in ("/System/Library/Fonts/Supplemental/Times New Roman.ttf",
          "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"):
    if os.path.exists(f):
        fm.fontManager.addfont(f)
plt.rcParams["font.family"] = ["Times New Roman", "DejaVu Sans"]
plt.rcParams["text.parse_math"] = False

LAND_C = "#e8e8e8"
LOW_C = "#2b7bba"
SEA_C = "#ffffff"
EDGE_C = "#666666"

# the ten biggest patches get a name
PLACES = [
    ("Yuen Long", 114.012, 22.442),
    ("Tuen Mun", 113.980, 22.390),
    ("Tin Shui Wai", 114.030, 22.460),
    ("Sheung Shui", 114.130, 22.490),
    ("Tsuen Wan", 114.100, 22.370),
    ("Kwai Chung", 114.132, 22.357),
    ("Sha Tin", 114.190, 22.380),
    ("Tai Po", 114.170, 22.420),
    ("Tseung Kwan O", 114.260, 22.310),
    ("Sai Kung", 114.270, 22.380),
    ("Lok Ma Chau", 114.073, 22.517),
    ("Kam Tin", 114.060, 22.448),
    ("Tai O", 113.913, 22.246),
    ("Mui Wo", 113.990, 22.265),
    ("Cheung Chau", 114.028, 22.205),
    ("Peng Chau", 114.070, 22.230),
    ("Lamma Island", 114.058, 22.245),
    ("Victoria Harbour", 114.170, 22.293),
    ("Tolo Harbour", 114.265, 22.477),
    ("Aberdeen", 114.160, 22.247),
    ("Ma On Shan", 114.230, 22.423),
    ("Tai Mo Shan", 114.1244, 22.4093),
]


def main():
    with rasterio.open(DTM) as ds:
        H, W = ds.height, ds.width
        z = ds.read(1)
        aff = ds.transform
        nodata = ds.nodata
    valid = z != nodata
    land = np.load(MASK)
    low = land & valid & (z < 5)

    tr = Transformer.from_crs(4326, 2326, always_xy=True)
    trb = Transformer.from_crs(2326, 4326, always_xy=True)

    # --- the map frame in HK1980 metres
    x0, x1 = 801000, 866000
    y0, y1 = 798000, 850000

    fig = plt.figure(figsize=(13.2, 9.4), dpi=200)
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(2, 1, height_ratios=[5.1, 1.25],
                           left=0.035, right=0.965, top=0.875, bottom=0.045,
                           hspace=0.10)
    ax = fig.add_subplot(gs[0])
    axk = fig.add_subplot(gs[1])
    ax.set_facecolor("white")

    # --- the raster
    extent = [x0, x1, y0, y1]
    r = x1 - x0
    c = y1 - y0
    sub = int(np.ceil(max(r, c) / 8))
    img = np.zeros((H, W), dtype=np.uint8)
    img[land] = 1
    img[low] = 2
    from rasterio.windows import Window
    def win_for(xa, xb, ya, yb):
        c0 = max(0, int((xa - 799997.5) / 5))
        c1 = min(W, int((xb - 799997.5) / 5) + 1)
        r0 = max(0, int((848002.5 - yb) / 5))
        r1 = min(H, int((848002.5 - ya) / 5) + 1)
        return c0, c1, r0, r1
    c0, c1, r0, r1 = win_for(x0, x1, y0, y1)
    block = img[r0:r1, c0:c1]
    from matplotlib.colors import ListedColormap
    cm = ListedColormap([SEA_C, LAND_C, LOW_C])
    ax.imshow(block, extent=[799997.5 + c0 * 5, 799997.5 + c1 * 5,
                             848002.5 - r1 * 5, 848002.5 - r0 * 5],
              origin="upper", cmap=cm, vmin=0, vmax=2,
              interpolation="nearest", zorder=2)

    # --- the coastline, from the mask's own edge
    from scipy import ndimage
    edge = land ^ ndimage.binary_erosion(land, np.ones((3, 3)))
    ys, xs = np.nonzero(edge)
    keep = (xs >= c0) & (xs < c1) & (ys >= r0) & (ys < r1)
    ys, xs = ys[keep], xs[keep]
    px = 799997.5 + xs * 5 + 2.5
    py = 848002.5 - ys * 5 - 2.5
    ax.scatter(px, py, s=0.02, c=EDGE_C, marker="s", linewidths=0, zorder=3)

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_autoscale_on(False)
    ax.set_xticks(np.arange(805000, 866000, 10000))
    ax.set_yticks(np.arange(800000, 850001, 10000))
    ax.set_xticklabels([f"{v/1000:g}" for v in ax.get_xticks()], fontsize=9)
    ax.set_yticklabels([f"{v/1000:g}" for v in ax.get_yticks()], fontsize=9)
    ax.set_xlabel("Hong Kong 1980 Grid easting (km)", fontsize=10)
    ax.set_ylabel("northing (km)", fontsize=10)
    ax.grid(True, color="#dddddd", linewidth=0.4, zorder=1)
    for sp in ax.spines.values():
        sp.set_color("#888888")
        sp.set_linewidth(0.8)

    # --- the biggest patches, labelled
    lab, n = ndimage.label(low)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    order = np.argsort(sizes)[::-1][:10]
    for rank, k in enumerate(order, 1):
        m = lab == (k + 1)
        yy, xx = np.nonzero(m)
        px0 = 799997.5 + xx.mean() * 5 + 2.5
        py0 = 848002.5 - yy.mean() * 5 - 2.5
        lo, la = trb.transform(px0, py0)
        area = sizes[k] * 25 / 1e6
        ax.text(px0, py0, str(rank), fontsize=7.5, color="white", ha="center",
                va="center", zorder=12,
                bbox=dict(boxstyle="circle,pad=0.22", facecolor="#14395c",
                          edgecolor="white", linewidth=0.8))

    # --- place names, only the ones that land on the land mask
    placed = []
    for nm, lo, la in PLACES:
        e, nn = tr.transform(lo, la)
        cc = int((e - 799997.5) / 5)
        rr = int((848002.5 - nn) / 5)
        if not (0 <= cc < W and 0 <= rr < H):
            continue
        # Victoria Harbour and Tolo Harbour are water: label them in italic grey
        is_water = nm in ("Victoria Harbour", "Tolo Harbour")
        if not is_water and not land[rr, cc]:
            continue
        placed.append((nm, e, nn, is_water))
    for nm, e, nn, is_water in placed:
        ax.text(e, nn, nm, fontsize=8.2, ha="center", va="center", zorder=11,
                color="#555555" if is_water else "#222222",
                style="italic" if is_water else "normal",
                bbox=dict(facecolor="white", alpha=0.82, edgecolor="none",
                          pad=1.1),
                fontweight="normal")

    # --- the scale bar
    bx, by = x0 + 4500, y0 + 3500
    L = 10000
    ax.plot([bx, bx + L], [by, by], color="#222222", linewidth=3.0,
            solid_capstyle="butt", zorder=14)
    for t in (0, L):
        ax.plot([bx + t, bx + t], [by - 350, by + 350], color="#222222",
                linewidth=1.4, zorder=14)
    ax.text(bx + L / 2, by + 1100, "10 km", fontsize=9, ha="center",
            va="bottom", color="#222222", zorder=14,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.0))

    # --- the north arrow
    nx, ny = x1 - 5200, y1 - 5200
    ax.add_patch(FancyArrow(nx, ny, 0, 4200, width=140, head_width=900,
                            head_length=1900, length_includes_head=True,
                            color="#222222", zorder=14))
    ax.text(nx, ny + 5200, "N", fontsize=11, ha="center", va="bottom",
            fontweight="bold", color="#222222", zorder=14)

    # --- the title
    fig.text(0.035, 0.965, "Low-lying land in Hong Kong: land below 5 metres",
             fontsize=17, ha="left", va="top", color="#111111")
    fig.text(0.035, 0.923,
             f"Land area below 5 m elevation: {low.sum()*25/1e6:,.1f} km² "
             f"({low.sum()/land.sum()*100:.1f}% of Hong Kong's land)",
             fontsize=11.5, ha="left", va="top", color="#333333")

    # --- the key
    axk.set_xlim(0, 100)
    axk.set_ylim(0, 100)
    axk.axis("off")
    axk.add_patch(Rectangle((0, 0), 100, 100, facecolor="white",
                            edgecolor="#888888", linewidth=0.8, zorder=1))
    axk.text(2, 93, "Key", fontsize=12, fontweight="bold", va="top",
             color="#111111", zorder=2)
    rows = [
        (LOW_C, LOW_C, "Land below 5 m elevation (the low-lying land)"),
        (LAND_C, EDGE_C, "Land 5 m and above"),
        (SEA_C, EDGE_C, "Sea and harbours"),
    ]
    y = 76
    for fc, ec, txt in rows:
        axk.add_patch(Rectangle((2.5, y - 3.6), 3.2, 7.2, facecolor=fc,
                                edgecolor=ec, linewidth=0.6, zorder=2))
        axk.text(7.5, y, txt, fontsize=9.5, va="center", color="#222222",
                 zorder=2)
        y -= 13
    axk.text(45, 76, "① … ⑩  the ten largest patches of land below 5 m",
             fontsize=9.5, va="center", color="#222222", zorder=2)

    # --- the source line
    fig.text(0.035, 0.016,
             "Source: LandsD 5 m Digital Terrain Model (landsd_rcd_1638158088368_93806). "
             "Land mask built from the DTM's positive elevation and the verified Hong Kong "
             "coastline; the sea is coded 0 m in the DTM. Projection: Hong Kong 1980 Grid (EPSG:2326).",
             fontsize=7.6, ha="left", va="bottom", color="#555555")

    fig.savefig(PNG, dpi=200, facecolor="white")
    print(f"wrote {PNG}")
    print(f"  size {os.path.getsize(PNG):,} bytes")

    # --- the QC gate
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = []
    for t in fig.findobj(matplotlib.text.Text):
        try:
            bb = t.get_window_extent(r)
        except Exception:
            continue
        if not t.get_text().strip():
            continue
        boxes.append((t.get_text(), bb))
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            ox = max(0, min(a.x1, b.x1) - max(a.x0, b.x0))
            oy = max(0, min(a.y1, b.y1) - max(a.y0, b.y0))
            if ox * oy > 1:
                bad.append((boxes[i][0][:28], boxes[j][0][:28], ox * oy))
    print(f"  text overlap pairs: {len(bad)}")
    for a, b, ar in bad[:12]:
        print(f"     {a!r} x {b!r} = {ar:,.0f} px2")

    W_px, H_px = fig.canvas.get_width_height()
    off = []
    for txt, bb in boxes:
        if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > W_px + 2 or bb.y1 > H_px + 2:
            off.append(txt[:34])
    print(f"  text outside the canvas: {len(off)} {off[:6]}")
    return bad, off


if __name__ == "__main__":
    main()
