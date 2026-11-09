#!/usr/bin/env python3
"""
Map the flash-flood and storm-surge factors for Hong Kong.

Three panels:
  A  Flash flood - the rainfall and terrain side
  B  Storm surge - the sea-level and wave side
  C  The two scores side by side per flood-prone area, and the factor
     inventory

Every panel is built from the fetched data, not from recalled geography.
The land outline is the CEDD geological coastline (193 polygons, dissolves
to 1,092 km2) - NOT the iC1000 map-sheet catalogue, which dissolves to
2,130 km2 and puts HK in the wrong place.

Layout is done in FIGURE FRACTIONS with explicit rectangles, not with
gridspec. Two reasons, both learned the hard way:

  - the panel title and the panel subtitle are placed as figure-level text,
    so the gap between them is the same on every panel. As axes-level text
    they collided with the axes title.
  - the table has SIX columns (a row label plus five numbers) and every
    one needs its own right-aligned edge, so the numbers cannot run off
    into the next column.

House style: Times New Roman, white background, key box, scale bar,
north arrow, source line.

Run:  ls-venv/bin/python make_flood_causes_map.py
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon as MplPolygon

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")

# ------------------------------------------------------------------ font
TNR = "/System/Library/Fonts/Supplemental/Times New Roman.ttf"
if os.path.exists(TNR):
    font_manager.fontManager.addfont(TNR)
    plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["text.parse_math"] = False
plt.rcParams["axes.unicode_minus"] = False

LON0, LON1 = 113.82, 114.45
LAT0, LAT1 = 22.15, 22.58
ASPECT = 1.0 / math.cos(math.radians((LAT0 + LAT1) / 2))

INK = "#1a1a1a"
SEA = "#f4f7fa"
LAND = "#efe9dc"
CHAN = "#b9c4cc"
RED = "#d7301f"
BLUE = "#2c7fb8"

# ---------------------------------------------------------------- layout
# Every rectangle is [x0, y0, width, height] in FIGURE FRACTIONS.
FIG_W, FIG_H = 13.6, 9.4

Y_TITLE = 0.977          # headline, top-aligned
Y_SUB = 0.947            # headline subtitle, top-aligned

RECT_A = [0.055, 0.455, 0.395, 0.400]
RECT_B = [0.530, 0.455, 0.395, 0.400]
CBAR_A = [0.458, 0.515, 0.012, 0.280]
CBAR_B = [0.933, 0.515, 0.012, 0.280]

Y_PANEL_TITLE = 0.903     # panel title baseline
Y_PANEL_SUB = 0.878      # panel subtitle baseline

Y_C_TITLE = 0.392        # panel C title baseline
Y_C_SUB = 0.366          # panel C subtitle baseline

RECT_TAB = [0.055, 0.095, 0.430, 0.240]
RECT_KEY = [0.495, 0.095, 0.105, 0.240]
RECT_MINI = [0.620, 0.100, 0.330, 0.200]
Y_MINI_TITLE = 0.318


def load(name, raw=True):
    p = os.path.join(RAW if raw else OUT, name)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def rings(geom):
    """Every polygon ring of a geometry as a list of (lon, lat)."""
    t = (geom or {}).get("type")
    c = (geom or {}).get("coordinates")
    if c is None:
        return []
    if t == "Polygon":
        return [[(float(x), float(y)) for x, y in r] for r in c]
    if t == "MultiPolygon":
        return [[(float(x), float(y)) for x, y in r]
                for poly in c for r in poly]
    return []


def draw_coast(ax, fc, color, z=1):
    for ft in fc["features"]:
        for ring in rings(ft.get("geometry")):
            if len(ring) < 3:
                continue
            ax.add_patch(MplPolygon(ring, closed=True, facecolor=color,
                                    edgecolor="none", zorder=z))


def draw_lines(ax, fc, color, lw=0.3, z=2):
    for ft in fc["features"]:
        g = ft.get("geometry") or {}
        c = g.get("coordinates")
        if not c:
            continue
        typ = g.get("type")
        if typ == "LineString":
            ax.plot([p[0] for p in c], [p[1] for p in c],
                    color=color, lw=lw, zorder=z)
        elif typ == "MultiLineString":
            for part in c:
                ax.plot([p[0] for p in part], [p[1] for p in part],
                        color=color, lw=lw, zorder=z)


def scalebar(ax, x, y, length_deg, label, colour=INK, lw=1.6):
    """A scale bar drawn in degrees; the label carries the true length."""
    ax.plot([x, x + length_deg], [y, y], color=colour, lw=lw,
            solid_capstyle="butt", zorder=20)
    for xx in (x, x + length_deg):
        ax.plot([xx, xx], [y - 0.008, y + 0.008], color=colour, lw=lw, zorder=20)
    ax.text(x + length_deg / 2, y + 0.017, label, ha="center", va="bottom",
            fontsize=7.5, color=colour, zorder=21)


def north_arrow(ax, x, y, size=0.055):
    ax.annotate("", xy=(x, y + size), xytext=(x, y),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2),
                zorder=20)
    ax.text(x, y + size + 0.012, "N", ha="center", va="bottom", fontsize=8,
            color=INK, zorder=21)


def build_map_panel(fig, rect, cbar_rect, fc_flood, coast, chans,
                    title, subtitle, mode):
    """A map panel plus its own colour bar, both in figure fractions."""
    ax = fig.add_axes(rect)
    ax.set_facecolor(SEA)
    draw_coast(ax, coast, LAND)
    draw_lines(ax, chans, CHAN, lw=0.25, z=2)

    xs = [ft["geometry"]["coordinates"][0] for ft in fc_flood["features"]]
    ys = [ft["geometry"]["coordinates"][1] for ft in fc_flood["features"]]
    key = "ff_score" if mode == "ff" else "ss_score"
    vals = [ft["properties"][key] for ft in fc_flood["features"]]
    vmin, vmax = min(vals), max(vals)

    cmap = plt.get_cmap("YlOrRd") if mode == "ff" else plt.get_cmap("YlGnBu")
    norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
    sc = ax.scatter(xs, ys, s=26, c=vals, cmap=cmap, norm=norm,
                    edgecolors="white", linewidths=0.4, zorder=6)

    ax.set_xlim(LON0, LON1)
    ax.set_ylim(LAT0, LAT1)
    ax.set_aspect(ASPECT)
    ax.set_xlabel("Longitude (°E)", fontsize=8)
    ax.set_ylabel("Latitude (°N)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    for s in ax.spines.values():
        s.set_linewidth(0.6)
        s.set_color("#666666")

    scalebar(ax, LON0 + 0.02, LAT0 + 0.028, 0.104, "10 km")
    north_arrow(ax, LON1 - 0.035, LAT1 - 0.10)

    # the colour bar in its own axes, so the map keeps its rectangle
    cax = fig.add_axes(cbar_rect)
    cb = fig.colorbar(sc, cax=cax,
                       ticks=[vmin, (vmin + vmax) / 2, vmax])
    cb.ax.tick_params(labelsize=7, length=2)
    cb.outline.set_linewidth(0.5)
    label = ("flash-flood\nexposure score" if mode == "ff"
             else "storm-surge\nexposure score")
    fig.text(cbar_rect[0], cbar_rect[1] + cbar_rect[3] + 0.008, label,
             fontsize=7, color="#333333", va="bottom", ha="left",
             linespacing=1.2)

    # titles as figure text, clear of the axes
    fig.text(rect[0], Y_PANEL_TITLE, title, fontsize=10.5,
             fontweight="bold", va="bottom", ha="left")
    fig.text(rect[0], Y_PANEL_SUB, subtitle, fontsize=7.8,
             color="#444444", va="bottom", ha="left")
    return ax


def main():
    fc_flood = load("flood_hazard_factors.geojson", raw=False)
    coast = load("cedd_coastline.geojson")
    chans = load("dsd_channel.geojson")
    if fc_flood is None or coast is None:
        raise SystemExit("missing inputs - run fetch_flood_causes.py first")

    dom = {}
    for ft in fc_flood["features"]:
        d = ft["properties"]["dominant_hazard"]
        dom[d] = dom.get(d, 0) + 1

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=170)
    fig.patch.set_facecolor("white")

    build_map_panel(
        fig, RECT_A, CBAR_A, fc_flood, coast, chans,
        "A. Flash flood: rainfall and terrain",
        "Scored from daily rainfall extremes, ground elevation, slope, "
        "drainage capacity and channel proximity",
        "ff")
    build_map_panel(
        fig, RECT_B, CBAR_B, fc_flood, coast, chans,
        "B. Storm surge: sea level and waves",
        "Scored from ground elevation, distance to the sea, wave climate and "
        "the CEDD coastal-hazard designation",
        "ss")

    # ---------------- panel C: the comparison -------------------------
    fig.text(RECT_TAB[0], Y_C_TITLE,
             "C. Which hazard dominates each of DSD's three lists",
             fontsize=10.5, fontweight="bold", va="bottom", ha="left")
    fig.text(RECT_TAB[0], Y_C_SUB,
             "A score of 1.0 is the worst value among the 267 flood-prone "
             "areas; 0.0 is the best. The scores are means over each list.",
             fontsize=7.8, color="#444444", va="bottom", ha="left")

    # Group by the ACTUAL dsd_list values. Matching on a guessed phrase
    # ("Locations with Drainage Improvement Works in Progress") silently
    # matched ZERO rows, because the real value is
    # "Drainage Improvement Works In Progress" - the table lost a row
    # without any error. Match the exact values instead.
    LIST_ORDER = [
        "Locations Prone to Blockage",
        "Drainage Improvement Works In Progress",
        "Coastal Low-lying or Windy Residential Areas",
    ]
    present = {ft["properties"]["dsd_list"] for ft in fc_flood["features"]}
    rows = []
    for lst in LIST_ORDER:
        if lst not in present:
            continue
        sub = [ft for ft in fc_flood["features"]
               if ft["properties"]["dsd_list"] == lst]
        rows.append((lst, len(sub),
                     sum(ft["properties"]["ff_score"] for ft in sub) / len(sub),
                     sum(ft["properties"]["ss_score"] for ft in sub) / len(sub),
                     sum(1 for ft in sub
                         if ft["properties"]["dominant_hazard"] == "flash_flood"),
                     sum(1 for ft in sub
                         if ft["properties"]["dominant_hazard"] == "storm_surge")))
    # a missing list must not pass silently
    listed = sum(r[1] for r in rows)
    if listed != len(fc_flood["features"]):
        raise SystemExit(
            f"table lists {listed} areas but the layer has "
            f"{len(fc_flood['features'])} - a dsd_list value is unmatched")

    # ---- the table
    axT = fig.add_axes(RECT_TAB)
    axT.set_facecolor("white")
    axT.axis("off")

    # right-aligned edge of every numeric column, in transAxes
    EDGES = [0.42, 0.55, 0.68, 0.82, 0.96]
    hdr = ["Areas", "Flash-flood\nscore", "Storm-surge\nscore",
           "Flash flood\ndominates", "Storm surge\ndominates"]

    axT.text(0.02, 0.965, "DSD flood-prone-area list", transform=axT.transAxes,
             fontsize=8.5, fontweight="bold", va="top", ha="left")
    y = 0.855
    for h, cx in zip(hdr, EDGES):
        axT.text(cx, y, h, transform=axT.transAxes, fontsize=7.0,
                 va="top", ha="right", color="#333333", linespacing=1.3)
    y -= 0.215
    axT.plot([0.02, 0.965], [y + 0.055, y + 0.055],
             transform=axT.transAxes, color="#999999", lw=0.6)

    for lst, n_, ff_, ss_, nff, nss in rows:
        short = lst.replace("Locations Prone to Blockage", "Prone to blockage")
        short = short.replace(
            "Drainage Improvement Works In Progress",
            "Drainage works in progress")
        short = short.replace(
            "Coastal Low-lying or Windy Residential Areas",
            "Coastal low-lying / windy")
        axT.text(0.02, y, short, transform=axT.transAxes, fontsize=7.8,
                 va="center", ha="left")
        cells = (f"{n_}", f"{ff_:.2f}", f"{ss_:.2f}", f"{nff}", f"{nss}")
        for cx, v in zip(EDGES, cells):
            axT.text(cx, y, v, transform=axT.transAxes, fontsize=7.8,
                     va="center", ha="right")
        y -= 0.155

    axT.plot([0.02, 0.965], [y + 0.075, y + 0.075],
             transform=axT.transAxes, color="#999999", lw=0.6)
    axT.text(0.02, y + 0.020,
             f"All 267 areas: {dom.get('flash_flood', 0)} are dominated by "
             f"flash flood and {dom.get('storm_surge', 0)} by storm surge.",
             transform=axT.transAxes, fontsize=7.8, va="top", ha="left")

    # ---- the key, in its own column between the table and the mini-map
    axK = fig.add_axes(RECT_KEY)
    axK.set_facecolor("white")
    axK.axis("off")
    axK.text(0.0, 0.965, "Key", transform=axK.transAxes, fontsize=9,
             fontweight="bold", va="top", ha="left")
    keys = [
        ("Flash flood", RED, "score in A; dominant in C"),
        ("Storm surge", BLUE, "score in B; dominant in C"),
        ("Drainage channel", CHAN, "DSD stormwater network"),
        ("Flood-prone area", "#444444", "point, not extent"),
    ]
    ky = 0.855
    for lab, col, note in keys:
        axK.add_patch(plt.Rectangle((0.0, ky - 0.045), 0.115, 0.075,
                                    transform=axK.transAxes, facecolor=col,
                                    edgecolor="none"))
        axK.text(0.175, ky + 0.012, lab, transform=axK.transAxes, fontsize=7.6,
                 fontweight="bold", va="center", ha="left")
        axK.text(0.175, ky - 0.045, note, transform=axK.transAxes,
                 fontsize=6.6, color="#555555", va="center", ha="left")
        ky -= 0.175

    # ---- the mini-map of the dominant hazard
    axm = fig.add_axes(RECT_MINI)
    axm.set_facecolor(SEA)
    draw_coast(axm, coast, LAND)
    draw_lines(axm, chans, CHAN, lw=0.2, z=2)
    for ft in fc_flood["features"]:
        p = ft["properties"]
        cc = ft["geometry"]["coordinates"]
        col = RED if p["dominant_hazard"] == "flash_flood" else BLUE
        axm.scatter([cc[0]], [cc[1]], s=14, c=col, edgecolors="white",
                    linewidths=0.3, zorder=6)
    axm.set_xlim(LON0, LON1)
    axm.set_ylim(LAT0, LAT1)
    axm.set_aspect(ASPECT)
    axm.set_xticks([])
    axm.set_yticks([])
    for s in axm.spines.values():
        s.set_linewidth(0.6)
        s.set_color("#666666")
    fig.text(RECT_MINI[0], Y_MINI_TITLE,
             "Dominant hazard at each of the 267 areas",
             fontsize=8.2, fontweight="bold", va="bottom", ha="left")

    # ---------------- headline and source ------------------------------
    fig.text(0.055, Y_TITLE, "Causes of flooding in Hong Kong: flash flood "
             "and storm surge", fontsize=15.5, fontweight="bold", va="top",
             ha="left")
    fig.text(0.055, Y_SUB,
             "Factor layers and map data for the two non-blockage flood "
             "mechanisms, scored at the 267 Drainage Services Department "
             "flood-prone areas",
             fontsize=9.5, color="#333333", va="top", ha="left")

    src = ("Source: Drainage Services Department flood-prone areas (226 "
           "blockage, 15 works in progress, 26 coastal); GEO raingauge daily "
           "rainfall (CEDD, 90 gauges, 1984-2026); CEDD wave data (hourly, "
           "1994-2025); HKO tidal predictions and latest weather; DSD "
           "stormwater channels, inlets, manholes, outfalls and pumping "
           "stations; WSD catchments; LandsD 5 m DTM; CEDD Coastal Hazards "
           "Study (CE 74/2018) and DSD Strategic Planning Study on Flood "
           "Management (CE 77/2021). Points mark the location of each "
           "designated area, not its extent.")
    # wrap it - a single long line runs off the right edge of the canvas
    import textwrap
    wrapped = textwrap.fill(src, width=150)
    fig.text(0.055, 0.030, wrapped, fontsize=6.4, color="#444444",
             va="bottom", ha="left", linespacing=1.5)

    p = os.path.join(OUT, "HK_flood_causes_map.png")
    fig.savefig(p, dpi=170, facecolor="white")
    print(f"wrote {p}")
    print(f"  {os.path.getsize(p)/1e6:.2f} MB")


if __name__ == "__main__":
    main()
