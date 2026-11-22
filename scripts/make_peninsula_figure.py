#!/usr/bin/env python3
"""Kowloon Peninsula — covered pedestrian pathways and school-route shelter.

Two panels:
  A  the covered (sheltered) pedestrian network in the study area, with the
     PTI points, so the reader sees WHERE the shelter is and where it is not
  B  every secondary school's best-covered walking route, drawn on the
     network, with the worst schools labelled

House style: Times New Roman, Key box, scale bar, north arrow, no findfont
warnings, manual PNG encode.
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf")
font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf")
matplotlib.rcParams["font.family"] = ["Times New Roman", "DejaVu Sans"]
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon
from PIL import Image
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

BASE = os.path.expanduser("~/GIS Data/Sun-Rain Exposure")
WORK = os.path.join(BASE, "work")
OUTDIR = os.path.join(BASE, "out")
FIGDIR = os.path.join(BASE, "figures")
os.makedirs(FIGDIR, exist_ok=True)
PNG = os.path.join(FIGDIR, "kowloon_peninsula_covered_routes.png")
PDF = os.path.join(FIGDIR, "kowloon_peninsula_covered_routes.pdf")

LAT0 = 22.32
M_PER_DEG_LAT = 110540.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))

# ------------------------------------------------------------------ load
import gzip
with gzip.open(os.path.expanduser(
        "~/GIS Data/GeoInfo Map/raw/rgeo_highlight_d00/123_CENSUS_2021_DC_POLY.geojson.gz"), "rt") as f:
    dcs = json.load(f)
DISTRICTS = {"深水埗區": "Sham Shui Po", "九龍城區": "Kowloon City", "油尖旺區": "Yau Tsim Mong"}
dc_geoms = {DISTRICTS[k]: shape(v["geometry"])
            for k, v in ((f["properties"]["DC_CHI"], f) for f in dcs["features"])
            if k in DISTRICTS}
study = unary_union(list(dc_geoms.values()))

cov = json.load(open(os.path.join(WORK, "peninsula_covered_paths.geojson")))["features"]
pti = json.load(open(os.path.join(WORK, "peninsula_pti.geojson")))["features"]
routes = json.load(open(os.path.join(WORK, "peninsula_route_geometry.geojson")))["features"]
schools = json.load(open(os.path.join(WORK, "peninsula_routes_schools.json")))

best_by_school = {}
for r in schools:
    if r.get("ai_routable"):
        best_by_school[r["name"]] = r

routes_best = [f for f in routes if f["properties"].get("ai_route_kind") == "best_covered"]
routes_short = [f for f in routes if f["properties"].get("ai_route_kind") == "shortest"]

# ------------------------------------------------------------------ figure
fig = plt.figure(figsize=(15.2, 8.6))
fig.patch.set_facecolor("white")
gs = fig.add_gridspec(1, 2, left=0.045, right=0.985, top=0.885, bottom=0.075,
                      wspace=0.06)
axA = fig.add_subplot(gs[0, 0])
axB = fig.add_subplot(gs[0, 1])

minx, miny, maxx, maxy = study.bounds
padx = (maxx - minx) * 0.035
pady = (maxy - miny) * 0.045


def draw_base(ax, title):
    # sea
    ax.set_facecolor("#DCE9F2")
    for name, g in dc_geoms.items():
        polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
        for poly in polys:
            ax.add_patch(MplPolygon(np.array(poly.exterior.coords),
                                    closed=True, facecolor="#F3EFE4",
                                    edgecolor="#8A8272", lw=0.9, zorder=2))
    # street / network context: the exposed network in pale grey
    exp = json.load(open(os.path.expanduser(
        "~/GIS Data/3D Pedestrian Network/exposed_outdoor_paths.geojson")))["features"]
    from shapely.strtree import STRtree
    exp_in = []
    for ft in exp:
        g = shape(ft["geometry"])
        if g.bounds[0] > maxx or g.bounds[2] < minx or g.bounds[1] > maxy or g.bounds[3] < miny:
            continue
        if g.intersects(study):
            exp_in.append(g)
    segs = [np.array(g.coords) for g in exp_in]
    from matplotlib.collections import LineCollection
    ax.add_collection(LineCollection(segs, colors="#C9C2B4", linewidths=0.22,
                                     zorder=3, alpha=0.85))
    ax.set_xlim(minx - padx, maxx + padx)
    ax.set_ylim(miny - pady, maxy + pady)
    ax.set_aspect(1 / M_PER_DEG_LON * M_PER_DEG_LAT)
    ax.ticklabel_format(axis="both", style="plain", useOffset=False)
    ax.tick_params(labelsize=6.5)
    # Pin explicit ticks: matplotlib generates tick labels OUTSIDE the axes
    # limits, and a generated one at 114.24 fell off the canvas.
    xt = [round(v, 2) for v in np.arange(math.ceil(minx * 100) / 100,
                                         maxx + 0.005, 0.01)]
    yt = [round(v, 2) for v in np.arange(math.ceil(miny * 100) / 100,
                                         maxy + 0.005, 0.01)]
    ax.set_xticks(xt)
    ax.set_yticks(yt)
    ax.set_xticklabels([f"{v:.2f}" for v in xt])
    ax.set_yticklabels([f"{v:.2f}" for v in yt])
    ax.set_xlabel("Longitude (°E)", fontsize=7.5, labelpad=1.5)
    ax.set_ylabel("Latitude (°N)", fontsize=7.5, labelpad=1.5)
    ax.set_title(title, fontsize=9.5, pad=5)


print("panel A base...", flush=True)
draw_base(axA, "A   Covered pedestrian pathways on the Kowloon Peninsula")

# ---- A: covered paths + PTI
cov_segs = [np.array(shape(f["geometry"]).coords) for f in cov
            if f["geometry"]["type"] == "LineString"]
from matplotlib.collections import LineCollection
axA.add_collection(LineCollection(cov_segs, colors="#1F6FB2", linewidths=1.5,
                                   zorder=6, capstyle="round"))
print(f"  covered segs {len(cov_segs)}", flush=True)

kinds = {"mtr": ("#C0392B", "s", 13), "bus": ("#E08A1E", "^", 15),
         "minibus": ("#6B4E9E", "o", 12)}
for kind, (col, mkr, sz) in kinds.items():
    pts = [(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1])
           for f in pti if f["properties"]["ai_kind"] == kind]
    if pts:
        axA.scatter([p[0] for p in pts], [p[1] for p in pts], s=sz, c=col,
                    marker=mkr, zorder=9, linewidths=0.3, edgecolors="white")

# MTR station names — the anchors a reader needs to orient
mtr_names = {}
for f in pti:
    if f["properties"]["ai_kind"] == "mtr":
        nm = f["properties"]["ai_name"]
        if nm and nm not in mtr_names:
            mtr_names[nm] = (f["geometry"]["coordinates"][0],
                             f["geometry"]["coordinates"][1])
for nm, (x, y) in list(mtr_names.items()):
    axA.annotate(nm, (x, y), fontsize=5.4, color="#7B241C", zorder=14,
                 ha="center", va="bottom",
                 bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.6))

print("panel B base...", flush=True)
draw_base(axB, "B   Best-sheltered walking route from a stop to each school")

# ---- B: best-covered routes, coloured by covered ratio
cmap = plt.get_cmap("RdYlGn")
lv = [f for f in routes_best]
vals = [f["properties"]["ai_covered_ratio"] for f in lv]
norm = plt.Normalize(0, 1)
segs_by = {}
for f in lv:
    g = shape(f["geometry"])
    parts = list(g.geoms) if g.geom_type == "MultiLineString" else [g]
    for p in parts:
        if p.geom_type == "LineString":
            segs_by.setdefault(round(f["properties"]["ai_covered_ratio"], 2), []).append(
                np.array(p.coords))
for ratio in sorted(segs_by):
    axB.add_collection(LineCollection(segs_by[ratio], colors=[cmap(norm(ratio))],
                                      linewidths=1.7, zorder=6, capstyle="round"))

# school markers — taken from the school table (lon/lat), not from the route
# geometry, whose coordinates are MultiLineString and not a flat pair
routed = [r for r in schools if r.get("ai_routable")]
axB.scatter([r["lon"] for r in routed], [r["lat"] for r in routed], s=15,
            c="#1A1A1A", marker="o", zorder=11,
            linewidths=0.5, edgecolors="white")

# label the worst schools (longest uncovered stretch on their best route)

# ------------------------------------------------------------------ key
key_rows = [
    ("Covered pedestrian path (sheltered from sun and rain)", "line", "#1F6FB2", "s"),
    ("Open pedestrian path (exposed)", "line", "#C9C2B4", "s"),
    ("MTR station exit", "mkr", "#C0392B", "s"),
    ("Bus stop", "mkr", "#E08A1E", "^"),
    ("Green minibus stop", "mkr", "#6B4E9E", "o"),
    ("Secondary school", "mkr", "#1A1A1A", "o"),
]
handles = []
for t, kind, c, m in key_rows:
    if kind == "line":
        handles.append(Line2D([], [], color=c, lw=2.4, label=t))
    else:
        handles.append(Line2D([], [], color=c, marker=m, ls="none", ms=5.0,
                              label=t))
leg = axA.legend(handles=handles,
                 loc="lower left", fontsize=6.2, frameon=True, framealpha=0.95,
                 edgecolor="#666666", borderpad=0.7, labelspacing=0.55,
                 handlelength=1.9, title="Key")
leg.get_title().set_fontsize(7.2)
leg.get_title().set_fontweight("bold")

# panel B needs its own key: the black dot is a school, and the lines are routes
axB.legend(handles=[
    Line2D([], [], color="#777777", lw=2.0, label="Walking route from a stop to the school"),
    Line2D([], [], color="#1A1A1A", marker="o", ls="none", ms=5.0, label="Secondary school"),
], loc="upper left", fontsize=6.2, frameon=True, framealpha=0.95,
    edgecolor="#666666", borderpad=0.7, labelspacing=0.55, handlelength=1.9,
    title="Key").get_title().set_fontsize(7.2)

# colour bar for covered ratio on panel B
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
cb = fig.colorbar(sm, ax=axB, orientation="horizontal", fraction=0.045,
                  pad=0.14, aspect=38)
cb.set_label("Share of the walking route that is covered", fontsize=7)
cb.ax.tick_params(labelsize=6.2)
cb.outline.set_linewidth(0.5)

# ------------------------------------------------- scale bar + north arrow
def scale_bar(ax, lon, lat, length_m, label):
    x1 = lon
    x2 = lon + length_m / M_PER_DEG_LON
    y = lat
    ax.plot([x1, x2], [y, y], color="#111111", lw=2.6, zorder=20,
            solid_capstyle="butt")
    ax.plot([x1, x1], [y - 0.00035, y + 0.00035], color="#111111", lw=1.4, zorder=20)
    ax.plot([x2, x2], [y - 0.00035, y + 0.00035], color="#111111", lw=1.4, zorder=20)
    ax.text((x1 + x2) / 2, y + 0.0007, label, fontsize=6.2, ha="center",
            va="bottom", color="#111111", zorder=21,
            bbox=dict(fc="white", ec="none", alpha=0.85, pad=0.8))


def north_arrow(ax, lon, lat):
    ax.annotate("N", (lon, lat), fontsize=8.5, fontweight="bold", ha="center",
                va="center", zorder=21, color="#111111",
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.0))
    ax.arrow(lon, lat - 0.0012, 0, 0.0030, head_width=0.0016, head_length=0.0012,
             fc="#111111", ec="#111111", zorder=20, length_includes_head=True)


scale_bar(axA, minx + padx * 0.9, miny + pady * 0.55, 1000, "1 km")
north_arrow(axA, maxx - padx * 1.1, maxy - pady * 0.9)
scale_bar(axB, minx + padx * 0.9, miny + pady * 0.55, 1000, "1 km")
north_arrow(axB, maxx - padx * 1.1, maxy - pady * 0.9)

def boxes_overlap(a, b, pad=1.0):
    # The QC gate flags a pair when the overlap exceeds 3 pt in BOTH axes, so
    # this test must be STRICTER than that: reject any pair overlapping by more
    # than 1 pt in both axes.  A LARGER pad would be looser, and a pair that
    # slips through here is exactly the pair the QC then reports.
    return (min(a.x1, b.x1) - max(a.x0, b.x0) > pad and
            min(a.y1, b.y1) - max(a.y0, b.y0) > pad)


def inflate(bb, m=2.0):
    # the white annotation bbox extends past the measured text extent, so
    # measure against the box the reader actually sees
    from matplotlib.transforms import Bbox
    return Bbox.from_extents(bb.x0 - m, bb.y0 - m, bb.x1 + m, bb.y1 + m)


# every other artist's text box is a collision target for the school labels
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
label_boxes = [inflate(t.get_window_extent(renderer)) for t in fig.findobj(
    matplotlib.text.Text) if t.get_text().strip() and t.get_visible()]

# ------------------------------------------------------------------ titles
fig.text(0.045, 0.955, "Sheltered walking to school on the Kowloon Peninsula",
         fontsize=14.5, fontweight="bold", ha="left", va="center")
fig.text(0.045, 0.920,
         "Covered pedestrian pathways, and how much of the walk from a bus / minibus / MTR stop to each secondary school is under cover",
         fontsize=9.2, ha="left", va="center", color="#333333")

# ------------------------------------------------------------ source line
n_cov = len(cov)
n_pti = len(pti)
n_sch = len([r for r in schools if r.get("ai_routable")])
fig.text(0.045, 0.012,
         f"Data: LandsD 3D Pedestrian Network (CSDI landsd_rcd_1637222018065_52265, WeatherProof + Location fields) · "
         f"MTR 3D Indoor Map entry points (HK Maps WFS) · Transport Department bus stops (td_rcd_1638874475129_49745) and green minibus stops (td_rcd_1638874728005_80512) · "
         f"EDB secondary schools (5 CSDI datasets) · Census and Statistics Department 2021 District Council boundaries.\n"
         f"Analysis: {n_cov:,} covered path segments and {n_pti:,} stops in the study area; routes computed by shortest path on the pedestrian network (not straight lines); "
         f"{n_sch} schools routed.  A path is 'covered' where WeatherProof = 1 or Location = 2 (indoor).  Paths with WeatherProof = 3 (unclassified) are counted as not covered.",
         fontsize=6.0, ha="left", va="bottom", color="#333333")

# Placement is done against the MEASURED text boxes, in display space, after
# the layout is final — eyeballed offsets collide in a dense cluster (which is
# exactly what the Kowloon centre is).  Candidates are tried in order and a
# label that cannot find a clear spot is DROPPED rather than shipped overlapping.
def inside_axes(ax, bb):
    ab = ax.get_window_extent()
    return bb.x0 >= ab.x0 - 1 and bb.x1 <= ab.x1 + 1 and \
        bb.y0 >= ab.y0 - 1 and bb.y1 <= ab.y1 + 1


OFFSETS = [(0, 0.0046), (0.0060, -0.0046), (-0.0060, -0.0046),
           (0.0060, 0.0046), (-0.0060, 0.0046), (0, -0.0060),
           (0.0080, 0), (-0.0080, 0), (0.0080, -0.0090), (-0.0080, -0.0090),
           (0.0080, 0.0090), (-0.0080, 0.0090), (0.0105, -0.0040),
           (-0.0105, -0.0040), (0.0105, 0.0040), (-0.0105, 0.0040),
           (0, 0.0098), (0, -0.0102)]

n_dropped = 0
worst = sorted([r for r in schools if r.get("ai_routable")],
                key=lambda r: -r["ai_best_cov_longest_exposed_m"])[:8]
for r in worst:
    x, y = r["lon"], r["lat"]
    txt = f"{r['name'][:28]}\n{r['ai_best_cov_longest_exposed_m']:.0f} m uncovered"
    placed_ok = False
    for dx, dy in OFFSETS:
        cand = (x + dx, y + dy)
        ann = axB.annotate(
            txt, cand, fontsize=5.2, color="#111111", zorder=16,
            ha="center", va="center",
            bbox=dict(fc="white", ec="#BBBBBB", alpha=0.93, pad=1.6),
            arrowprops=dict(arrowstyle="-", lw=0.6, color="#666666",
                            shrinkA=0, shrinkB=2))
        fig.canvas.draw()
        bb = inflate(ann.get_window_extent(renderer))
        if inside_axes(axB, ann.get_window_extent(renderer)) and \
                not any(boxes_overlap(bb, ob) for ob in label_boxes):
            label_boxes.append(bb)
            placed_ok = True
            break
        ann.remove()
    if not placed_ok:
        n_dropped += 1

fig.canvas.draw()
buf = np.ascontiguousarray(np.asarray(fig.canvas.buffer_rgba()).copy())
Image.fromarray(buf, "RGBA").convert("RGB").save(PNG)
fig.savefig(PDF)
print("saved", PNG, os.path.getsize(PNG))
print("saved", PDF, os.path.getsize(PDF))
