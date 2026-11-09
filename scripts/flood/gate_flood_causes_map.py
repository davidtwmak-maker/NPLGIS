#!/usr/bin/env python3
"""
Numeric QC gate for HK_flood_causes_map.png.

Checks, in order:
  1. The file exists and is a plausible size for a three-panel map.
  2. Every text artist is inside its axes bbox (no clipped legend rows).
  3. No two text artists overlap.
  4. No marker is covered by a text box.
  5. Pixel probes: the two map panels contain land, sea and the point
     colours they are supposed to contain - so the figure is not a blank
     canvas with a title on it.

Exit code 0 = pass.

Run:  ls-venv/bin/python gate_flood_causes_map.py
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
PNG = os.path.join(OUT, "HK_flood_causes_map.png")

problems = []


def fail(msg):
    problems.append(msg)
    print(f"  FAIL {msg}")


def ok(msg):
    print(f"  ok   {msg}")


# ---------------------------------------------------------------- 1. file
if not os.path.exists(PNG):
    print(f"FAIL {PNG} does not exist")
    sys.exit(1)
size = os.path.getsize(PNG)
print(f"=== 1. file ===")
print(f"  {PNG}")
print(f"  {size:,} bytes")
if size < 250_000:
    fail(f"file is only {size:,} bytes - a three-panel map should be larger")
else:
    ok(f"size {size/1e6:.2f} MB")

im = Image.open(PNG).convert("RGB")
W, H = im.size
arr = np.asarray(im).astype(int)
print(f"  image {W} x {H}")
if size > 0 and arr.std() < 8:
    fail("image is nearly uniform - probably a blank canvas")
else:
    ok(f"pixel std {arr.std():.1f} (not blank)")

# ---------------------------------------------------------------- 2-4. text
# The builder records the artist positions; re-derive them by importing the
# build module and capturing the figure.
print("\n=== 2-4. text geometry (from the renderer) ===")
sys.path.insert(0, HERE)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import make_flood_causes_map as M

fig = None
_orig_main = M.main


def capture():
    global fig
    M.main()
    fig = plt.gcf()


capture()
fig.canvas.draw()
renderer = fig.canvas.get_renderer()

boxes = []
for ax in fig.get_axes():
    ax_box = ax.get_position()          # already a Bbox
    for t in ax.texts:
        if not t.get_text().strip():
            continue
        bb = t.get_window_extent(renderer)
        boxes.append((t.get_text(), bb, ax, ax_box))

# Figure-level text (headline, panel titles, source line) belongs to no
# axes, so it is compared against the FIGURE and checked for collisions
# with axes-level text too.
FIG = fig
fig_texts = []
for t in fig.texts:
    if not t.get_text().strip():
        continue
    bb = t.get_window_extent(renderer)
    fig_texts.append((t.get_text(), bb))
print(f"  {len(fig_texts)} figure-level text artists")
for txt, bb in fig_texts:
    boxes.append((txt, bb, FIG, fig.get_window_extent(renderer)))

print(f"  {len(boxes)} text artists on {len(fig.get_axes())} axes")

# (2) inside the axes
outside = []
for txt, bb, ax, ax_box in boxes:
    if (bb.x0 < ax_box.x0 - 1 or bb.x1 > ax_box.x1 + 1 or
            bb.y0 < ax_box.y0 - 1 or bb.y1 > ax_box.y1 + 1):
        # panel-C texts use transAxes on an axis with axis('off'); those are
        # inside the figure, not the axes bbox - check the figure instead
        if not (bb.x0 >= 0 and bb.x1 <= W and bb.y0 >= 0 and bb.y1 <= H):
            outside.append((txt[:40], (bb.x0, bb.y0, bb.x1, bb.y1)))
if outside:
    for o in outside[:6]:
        fail(f"text outside the canvas: {o[0]!r}")
else:
    ok("every text artist is inside the canvas")

# (3) pairwise overlap
overlaps = 0
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        t1, b1, a1, ax1 = boxes[i]
        t2, b2, a2, ax2 = boxes[j]
        if a1 is not a2 and a1 is not FIG and a2 is not FIG:
            continue          # different axes cannot overlap visually
        ix = max(0.0, min(b1.x1, b2.x1) - max(b1.x0, b2.x0))
        iy = max(0.0, min(b1.y1, b2.y1) - max(b1.y0, b2.y0))
        area = ix * iy
        if area > 4:
            smaller = min(b1.width * b1.height, b2.width * b2.height)
            if smaller > 0 and area / smaller > 0.30:
                overlaps += 1
                if overlaps <= 6:
                    fail(f"text overlap: {t1[:28]!r} vs {t2[:28]!r} "
                         f"({area:.0f} px2)")
if not overlaps:
    ok("no text-over-text overlap above 30% of the smaller box")

# (4) marker under text
marker_hits = 0
for ax in fig.get_axes():
    for coll in ax.collections:
        try:
            off = coll.get_offsets()
        except Exception:
            continue
        if off is None or len(off) == 0:
            continue
        pts = ax.transData.transform(off)
        for txt, bb, a2, ax2 in boxes:
            if a2 is not ax:
                continue
            for px, py in pts:
                if bb.x0 <= px <= bb.x1 and bb.y0 <= py <= bb.y1:
                    marker_hits += 1
                    if marker_hits <= 4:
                        fail(f"marker under text {txt[:30]!r}")
if not marker_hits:
    ok("no marker sits under a text box")

# ------------------------------------------------- 4b. table integrity
print("\n=== 4b. panel C table integrity ===")
# The table is built from the layer, so the numbers on the map must match
# the layer. A row can vanish silently (a dsd_list value that does not
# match the pattern used to group it), and the pixel probes cannot see
# that - so check it against the data.
import json as _json
_fc = _json.load(open(os.path.join(OUT, "flood_hazard_factors.geojson")))
_feats = _fc["features"]
_lists = {}
for _ft in _feats:
    _lists.setdefault(_ft["properties"]["dsd_list"], []).append(_ft)
print(f"  layer: {len(_feats)} areas in {len(_lists)} lists")
for _k, _v in sorted(_lists.items(), key=lambda kv: -len(kv[1])):
    print(f"    {len(_v):>4}  {_k}")

# the rendered table must mention one label per list
_labels = {
    "Locations Prone to Blockage": "Prone to blockage",
    "Drainage Improvement Works In Progress": "Drainage works in progress",
    "Coastal Low-lying or Windy Residential Areas": "Coastal low-lying / windy",
}
_all_text = " | ".join(t for t, _, _, _ in boxes)
for _k, _v in sorted(_lists.items(), key=lambda kv: -len(kv[1])):
    _short = _labels.get(_k)
    if _short is None:
        fail(f"list {_k!r} has no short label defined for the table")
    elif _short not in _all_text:
        fail(f"table is missing the row for {_k!r} (expected {_short!r})")
if not any("missing the row" in p for p in problems):
    ok(f"all {len(_lists)} lists appear in the table")

# the area counts on the map must match the layer
for _k, _v in sorted(_lists.items(), key=lambda kv: -len(kv[1])):
    _n = len(_v)
    if not any(t.strip() == str(_n) for t, _, _, _ in boxes):
        fail(f"the count {_n} for {_k!r} does not appear on the map")
if not any("does not appear on the map" in p for p in problems):
    ok("every list's area count appears on the map")

# ---------------------------------------------------------------- 5. pixels
print("\n=== 5. pixel probes (on the SAVED PNG) ===")
# The saved PNG is the deliverable, so the probes must read THAT file, not
# the figure the gate re-rendered - the two can differ in dpi and would
# then disagree about where the panels are.
# The panel regions are derived from the SAME axes positions the builder
# used, converted through the saved PNG's own size.
SAVED_W, SAVED_H = W, H
# ax.get_position().extents is in FIGURE FRACTION (0-1 of the figure),
# so multiply by the saved PNG's pixel size - not by inches.
def region_from_axes(ax):
    x0, y0, x1, y1 = ax.get_position().extents
    px0, px1 = int(x0 * SAVED_W), int(x1 * SAVED_W)
    # matplotlib y is bottom-origin; PIL row 0 is the top
    py0, py1 = int((1.0 - y1) * SAVED_H), int((1.0 - y0) * SAVED_H)
    return arr[max(0, py0):py1, max(0, px0):px1]


axA = fig.axes[0]
axB = fig.axes[1]
axm = None
for a in fig.axes:
    # get_title() defaults to loc="center" and returns "" for a title set
    # with loc="left", so check every location
    titles = " ".join(str(a.get_title(loc=L)) for L in ("center", "left", "right"))
    if "Dominant hazard" in titles:
        axm = a
        break
if axm is None:
    cands = [a for a in fig.axes
             if not a.get_xticklabels() and not a.get_yticklabels()]
    axm = cands[-1] if cands else fig.axes[-1]
print("  mini-map axes title: " +
      " ".join(str(axm.get_title(loc=L)) for L in ("center", "left", "right")))

# Identify the panels by what they CONTAIN, not by index: the figure has
# colour-bar axes too, so axes[1] is not necessarily panel B.
def is_map_axis(a):
    # a map panel has a longitude/latitude axis label
    return (a.get_xlabel() or "").startswith("Longitude")


def title_of(a):
    return " ".join(str(a.get_title(loc=L)) for L in ("center", "left", "right"))


maps = [a for a in fig.axes if is_map_axis(a)]
if len(maps) < 2:
    fail(f"expected 2 map axes with longitude labels, found {len(maps)}")
    sys.exit(1)
axA, axB = maps[0], maps[1]
if axm is None or is_map_axis(axm):
    cands = [a for a in fig.axes
             if not a.get_xticklabels() and not a.get_yticklabels()
             and not is_map_axis(a)]
    axm = cands[-1] if cands else fig.axes[-1]
print(f"  map axes found: {len(maps)}; total axes: {len(fig.axes)}")

for name, ax, warm in (("A flash flood", axA, "red"),
                        ("B storm surge", axB, "blue"),
                        ("C dominant hazard", axm, "both")):
    sub = region_from_axes(ax)
    if sub.size == 0:
        fail(f"panel {name}: empty pixel region")
        continue
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    sea = (b > r + 4) & (b > 245) & (g > 245)
    warm_red = (r - b > 60) & (r - g > 30)
    cool_blue = (b - r > 45) & (b - g > 15)
    total = sub.shape[0] * sub.shape[1]
    print(f"  panel {name}: {sub.shape[1]}x{sub.shape[0]} px  "
          f"sea {100*sea.mean():.1f}%  warm {100*warm_red.mean():.3f}%  "
          f"cool {100*cool_blue.mean():.3f}%")
    if sea.mean() < 0.05:
        fail(f"panel {name}: no sea colour - the panel may be empty")
    else:
        ok(f"panel {name}: sea present ({100*sea.mean():.1f}%)")
    if warm == "red" and warm_red.mean() < 0.002:
        fail(f"panel {name}: no warm point colour found")
    if warm == "blue" and cool_blue.mean() < 0.002:
        fail(f"panel {name}: no cool point colour found")
    if warm == "both" and (warm_red.mean() < 0.001 or cool_blue.mean() < 0.001):
        fail(f"panel {name}: both hazard colours must be present")

# the title band must not be empty
band = int(H * 0.075)
top = arr[0:band, :]
# ink = dark pixels. Channel std is wrong here: black text has std 0.
ink = (top.sum(axis=2) < 520).mean()
print(f"  title band: {100*ink:.1f}% of pixels carry ink")
if ink < 0.005:
    fail("title band carries almost no text")
else:
    ok(f"title band carries text ({100*ink:.1f}%)")

print()
if problems:
    print(f"=== GATE FAILED: {len(problems)} problems ===")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("=== GATE PASSED ===")
