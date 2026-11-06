#!/usr/bin/env python3
"""
Map: Hong Kong's steep slopes (>30 degrees) as 2D polygons.

Reads out/steep_slopes_over30.geojson and out/slope_class_polygons.geojson
(both EPSG:2326) and draws a two-panel figure:

  Panel A  Slope class map (0-15 / 15-30 / 30-45 / 45-60 / 60+) with the
           landslide incident points overprinted.
  Panel B  The >30 degree regions alone, over the gentler land as context,
           with the largest regions labelled.

TWO THINGS THAT MATTER HERE, both learned the hard way:

1. PROJECTION. The polygon layers are in HK1980 metres (EPSG:2326).  They
   MUST be reprojected to WGS84 before plotting, or every polygon lands far
   off-canvas and the map renders blank apart from the legend swatches.
   (A pixel probe of the render is how that was caught - the figure looked
   fine to the eye but 88% of the panel was white.)

2. SPEED. The class layer has 106,874 polygons.  geopandas' .plot() builds
   one matplotlib Path per feature and takes minutes; the polygons are drawn
   here with a single PathCollection per class instead.

House style: Times New Roman, white background, key below each map, source
line.  Includes the numeric text-overlap gate.
"""
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.path import Path
import numpy as np
import geopandas as gpd
from shapely import transform as shp_transform
from pyproj import Transformer

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out")

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["text.parse_math"] = False

# --- extent: the 20 m analysis grid, in HK1980 metres ---
W, H = 3187, 2400
CELL = 20.0
X0, Y0 = 800007.5, 847992.5
LEFT = X0 - CELL / 2
TOP = Y0 + CELL / 2

_tr = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True)
LON0, LAT0 = _tr.transform(LEFT, TOP - H * CELL)
LON1, LAT1 = _tr.transform(LEFT + W * CELL, TOP)
print(f"map extent lon {LON0:.4f}..{LON1:.4f}  lat {LAT0:.4f}..{LAT1:.4f}")


def to_wgs84(x, y=None, z=None):
    """Vectorised EPSG:2326 -> EPSG:4326 for shapely's transform().

    shapely 2.x calls the callback with ONE (N,2) array of coordinates;
    shapely 1.x called it with separate x and y arrays.  Handle both, and
    return the same shape that came in - otherwise pyproj raises
    "x, y, z, and time must be same size if included".
    """
    if y is None:
        arr = np.asarray(x, dtype=float)
        xs, ys = arr[:, 0], arr[:, 1]
    else:
        xs, ys = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    lon, lat = _tr.transform(xs, ys)
    if y is None:
        return np.column_stack([lon, lat])
    return lon, lat


class Colors:
    sea = "#FFFFFF"
    c1 = "#B7D3A8"   # 0-15
    c2 = "#E8D08A"   # 15-30
    c3 = "#E5924F"   # 30-45
    c4 = "#C2504F"   # 45-60
    c5 = "#7E2B3C"   # 60+
    land = "#EFE9DC"
    inc = "#1A1A1A"


def paths_from_geoms(geoms):
    """One matplotlib Path per polygon part (exterior + holes).

    A repaired region can be a MultiPolygon (make_valid splits a
    self-touching ring into pieces), so every PART of a geometry gets its
    own Path - a MultiPolygon has no .exterior attribute.
    """
    out = []
    for g in geoms:
        parts = []
        if g.geom_type == "Polygon":
            parts = [g]
        elif g.geom_type == "MultiPolygon":
            parts = list(g.geoms)
        else:
            continue
        for part in parts:
            verts, codes = [], []
            for ring in [part.exterior] + list(part.interiors):
                c = np.asarray(ring.coords, dtype=float)
                if len(c) < 3:
                    continue
                verts.append(c)
                codes.append(np.concatenate(([Path.MOVETO],
                                             np.full(len(c) - 2, Path.LINETO),
                                             [Path.CLOSEPOLY])))
            if verts:
                out.append(Path(np.concatenate(verts), np.concatenate(codes)))
    return out


def draw(ax, geoms, color, zorder, alpha=1.0, edgecolor="none", linewidth=0.0):
    if len(geoms) == 0:
        return
    pc = PathCollection(paths_from_geoms(geoms),
                        facecolors=color, edgecolors=edgecolor,
                        linewidths=linewidth, alpha=alpha, zorder=zorder)
    ax.add_collection(pc)


def main():
    steep = gpd.read_file(os.path.join(OUT, "steep_slopes_over30.geojson"))
    cls = gpd.read_file(os.path.join(OUT, "slope_class_polygons.geojson"))
    inc = gpd.read_file(os.path.join(OUT, "landslide_records.geojson"))
    print("steep regions:", len(steep), "| class polys:", len(cls), "| incidents:", len(inc))

    # --- reproject the polygon layers to WGS84 for the figure ---
    cls_ll = gpd.GeoSeries(shp_transform(cls.geometry.to_numpy(), to_wgs84), crs="EPSG:4326")
    steep_ll = gpd.GeoSeries(shp_transform(steep.geometry.to_numpy(), to_wgs84), crs="EPSG:4326")

    # --- subsample incidents for plotting speed ---
    rng = np.random.default_rng(42)
    n_inc = len(inc)
    if n_inc > 40000:
        inc = inc.iloc[rng.choice(n_inc, 40000, replace=False)]
        print("incidents plotted (subsampled):", len(inc))
    inc_ll = inc.to_crs("EPSG:4326")

    fig = plt.figure(figsize=(12.6, 13.8))
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 0.92], hspace=0.42,
                          left=0.065, right=0.985, top=0.900, bottom=0.060)

    TITLES = [
        ("Slope classes of Hong Kong",
         "Maximum gradient within each 20 m cell, from the LandsD 5 m digital terrain model"),
        ("Slopes steeper than 30°",
         "Regions where the ground exceeds a 30° gradient — 10.1% of the land area"),
    ]
    TITLE_Y = [0.968, 0.470]
    SUB_Y = [0.947, 0.449]

    class_ids = cls["slope_class_id"].to_numpy()

    for gi, (title, sub) in enumerate(TITLES):
        ax = fig.add_subplot(gs[gi])
        ax.set_facecolor(Colors.sea)
        ax.set_xlim(LON0, LON1)
        ax.set_ylim(LAT0, LAT1)
        ax.set_aspect(1.0 / math.cos(math.radians((LAT0 + LAT1) / 2)))
        ax.set_autoscale_on(False)
        ax.ticklabel_format(axis="x", style="plain", useOffset=False)
        ax.tick_params(labelsize=8.5)
        ax.grid(True, lw=0.3, color="#C9C9C9", alpha=0.6, zorder=0)
        for s in ax.spines.values():
            s.set_linewidth(0.8)
            s.set_color("#444444")
        ax.set_xlabel("Longitude (°E)", fontsize=9.5)
        ax.set_ylabel("Latitude (°N)", fontsize=9.5)
        fig.text(0.065, TITLE_Y[gi], title, fontsize=15,
                 ha="left", va="top", fontweight="bold")
        fig.text(0.065, SUB_Y[gi], sub, fontsize=10,
                 ha="left", va="top", color="#333333")

        if gi == 0:
            cmap = {1: Colors.c1, 2: Colors.c2, 3: Colors.c3, 4: Colors.c4, 5: Colors.c5}
            for c, col in cmap.items():
                draw(ax, cls_ll[class_ids == c].to_numpy(), col, zorder=1)
            inc_ll.plot(ax=ax, color=Colors.inc, markersize=0.5, alpha=0.42, zorder=6)
            handles = [
                Patch(facecolor=Colors.c1, label="0–15°"),
                Patch(facecolor=Colors.c2, label="15–30°"),
                Patch(facecolor=Colors.c3, label="30–45°"),
                Patch(facecolor=Colors.c4, label="45–60°"),
                Patch(facecolor=Colors.c5, label="60° and above"),
                Line2D([0], [0], marker="o", color="none", markerfacecolor=Colors.inc,
                       markeredgecolor="none", markersize=3.0,
                       label=f"Recorded landslide ({len(inc):,} of 124,020 shown)"),
            ]
            key_ax = ax.inset_axes([0.0, -0.155, 1.0, 0.085])
            key_ax.axis("off")
            leg = key_ax.legend(handles=handles, loc="upper left", ncol=3, frameon=False,
                                 fontsize=9, handletextpad=0.6, columnspacing=1.8)
            for t in leg.get_texts():
                t.set_color("#111111")
        else:
            # gentle land as context, then the steep regions on top
            draw(ax, cls_ll[class_ids <= 2].to_numpy(), Colors.land, zorder=1)
            draw(ax, steep_ll.to_numpy(), Colors.c3, zorder=3,
                 edgecolor="#B5563A", linewidth=0.10)

            # Label the largest regions.  The resolver works in PIXEL space,
            # where the text's true bounding box comes from the renderer -
            # estimating the box in data units is too crude and lets
            # collisions through.
            big_idx = steep["area_km2"].nlargest(6).index
            big_ll = steep_ll.loc[big_idx]
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            placed = []
            # Minimum clearance between two label boxes, in pixels.  A test
            # for literal overlap is not enough: boxes that merely touch
            # read as one crowded cluster, which is what the first render
            # of this figure did (the 1.36 / 1.20 km2 pair).
            GAP = 7.0

            def grown(bb, pad):
                from matplotlib.transforms import Bbox
                return Bbox.from_extents(bb.x0 - pad, bb.y0 - pad,
                                         bb.x1 + pad, bb.y1 + pad)

            CAND = [(0, 0), (0, 26), (0, -26), (30, 0), (-30, 0), (30, 26),
                    (-30, -26), (0, 52), (0, -52), (60, 0), (-60, 0),
                    (60, 26), (-60, -26), (0, 78), (0, -78), (90, 0), (-90, 0),
                    (90, 26), (-90, -26), (0, 104), (0, -104), (120, 0),
                    (-120, 0), (120, 26), (-120, -26), (60, 52), (-60, -52),
                    (30, 78), (-30, -78)]
            for idx in big_idx:
                p = steep_ll.loc[idx].representative_point()
                txt = f"{steep.loc[idx, 'area_km2']:.2f} km²"
                t = ax.text(p.x, p.y, txt, fontsize=8.5, ha="center",
                            va="center", color="#5A1A24", zorder=8,
                            bbox=dict(facecolor="white", alpha=0.85,
                                      edgecolor="none", pad=1.4))
                base_px = ax.transData.transform((p.x, p.y))
                chosen = None
                for dx, dy in CAND:
                    t.set_position(ax.transData.inverted().transform(
                        (base_px[0] + dx, base_px[1] + dy)))
                    bb = t.get_window_extent(renderer=renderer)
                    ax_bb = ax.get_window_extent(renderer=renderer)
                    if bb.x0 < ax_bb.x0 or bb.x1 > ax_bb.x1:
                        continue
                    if bb.y0 < ax_bb.y0 or bb.y1 > ax_bb.y1:
                        continue
                    clash = False
                    for pb in placed:
                        a = grown(bb, GAP / 2.0)
                        b = grown(pb, GAP / 2.0)
                        ox = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
                        oy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
                        if ox * oy > 1.0:
                            clash = True
                            break
                    if not clash:
                        chosen = (dx, dy)
                        placed.append(bb)
                        break
                if chosen is None:
                    t.set_position((p.x, p.y))
                    placed.append(t.get_window_extent(renderer=renderer))
                    print(f"  WARN: no clear slot for label {txt}")
            handles = [
                Patch(facecolor=Colors.land, label="Land with gentler slopes (below 30°)"),
                Patch(facecolor=Colors.c3, edgecolor="#B5563A", linewidth=0.5,
                      label="Ground steeper than 30°"),
            ]
            key_ax = ax.inset_axes([0.0, -0.155, 1.0, 0.085])
            key_ax.axis("off")
            leg = key_ax.legend(handles=handles, loc="upper left", ncol=2, frameon=False,
                                 fontsize=9, handletextpad=0.6)
            for t in leg.get_texts():
                t.set_color("#111111")

        # scale bar + north arrow
        lat_c = (LAT0 + LAT1) / 2
        km_per_deg = 111.32 * math.cos(math.radians(lat_c))
        bar_deg = 10.0 / km_per_deg
        x0 = LON0 + (LON1 - LON0) * 0.035
        y0 = LAT0 + (LAT1 - LAT0) * 0.05
        ax.plot([x0, x0 + bar_deg], [y0, y0], color="#111111", lw=3.0,
                solid_capstyle="butt", zorder=12)
        ax.text(x0 + bar_deg / 2, y0 + (LAT1 - LAT0) * 0.012, "10 km", fontsize=8.5,
                ha="center", va="bottom", zorder=13,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.2))
        nx, ny = LON1 - (LON1 - LON0) * 0.045, LAT1 - (LAT1 - LAT0) * 0.045
        ax.annotate("", xy=(nx, ny), xytext=(nx, ny - (LAT1 - LAT0) * 0.065),
                    arrowprops=dict(arrowstyle="-|>", color="#111111", lw=1.7), zorder=12)
        ax.text(nx, ny - (LAT1 - LAT0) * 0.085, "N", fontsize=9.5, ha="center", va="top",
                fontweight="bold", zorder=13,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.2))

    fig.text(0.065, 0.008,
             "Source: LandsD Digital Terrain Model 5 m (slope by Horn's method, maximum within each 20 m cell); "
             "CEDD landslide incident and ENTLI crown records. Extents approximate; contours not shown.",
             fontsize=7.4, ha="left", va="bottom", color="#444444")

    outp = os.path.join(OUT, "steep_slopes_over30_map.png")

    # ---- numeric overlap gate ----
    # The gate runs BEFORE savefig on purpose.  An earlier version saved the
    # PNG first and asserted afterwards, so a failing run left a bad figure
    # on disk that looked deliverable.  Now the file is only written once
    # the figure has passed.
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
        if bb.width > 0 and bb.height > 0:
            boxes.append((t.get_text()[:44], bb))
    problems = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            ox = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
            oy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
            if ox * oy > 4.0:
                problems.append((boxes[i][0], boxes[j][0], round(ox * oy, 1)))

    # The in-map area labels ("1.36 km2") must also keep a minimum
    # clearance from each other.  A pure overlap test is not enough:
    # touching boxes read as one crowded cluster, which is what the first
    # render of this figure produced.
    from matplotlib.transforms import Bbox
    CLEAR = 6.0
    area_boxes = [(lbl, bb) for lbl, bb in boxes if lbl.strip().endswith("km²")]
    crowded = []
    for i in range(len(area_boxes)):
        for j in range(i + 1, len(area_boxes)):
            a, b = area_boxes[i][1], area_boxes[j][1]
            ga = Bbox.from_extents(a.x0 - CLEAR / 2, a.y0 - CLEAR / 2,
                                   a.x1 + CLEAR / 2, a.y1 + CLEAR / 2)
            gb = Bbox.from_extents(b.x0 - CLEAR / 2, b.y0 - CLEAR / 2,
                                   b.x1 + CLEAR / 2, b.y1 + CLEAR / 2)
            ox = max(0.0, min(ga.x1, gb.x1) - max(ga.x0, gb.x0))
            oy = max(0.0, min(ga.y1, gb.y1) - max(ga.y0, gb.y0))
            if ox * oy > 1.0:
                crowded.append((area_boxes[i][0], area_boxes[j][0]))

    Wp, Hp = fig.canvas.get_width_height()
    off = [l for l, bb in boxes if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > Wp + 2 or bb.y1 > Hp + 2]
    print(f"text boxes {len(boxes)} | overlaps {len(problems)} | off-canvas {len(off)}")
    print(f"area labels {len(area_boxes)} | clearance violations {len(crowded)}")
    for p in problems:
        print("  OVERLAP:", p)
    for c in crowded:
        print("  CROWDED:", c)
    for o in off:
        print("  OFF-CANVAS:", o)
    assert not problems, "text overlap detected"
    assert not off, "text clipped"
    assert not crowded, "area labels too close together"

    fig.savefig(outp, dpi=190, facecolor="white")
    print("wrote", outp)


if __name__ == "__main__":
    main()
