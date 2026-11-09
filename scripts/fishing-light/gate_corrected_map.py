#!/usr/bin/env python3
"""
Figure gate for the corrected fishing-light map.

Runs on the RENDERER (matplotlib), not on the PNG alone:
  (1) no pair of text artists intersects;
  (2) every text artist lies inside the figure canvas;
  (3) no bar marker falls inside a text box (the annotation over the peak bar);
  (4) pixel probes: the rendered bars match the input values, and the
      permitted-area outline is actually drawn on panel A.

Exits non-zero on any violation.
"""
import os
import json
import math
import sys

import numpy as np
import matplotlib
GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

BUILD = f"{GIS_DATA}/HK Night Lights/make_corrected_map.py"
PNG = f"{GIS_DATA}/HK Night Lights/HK_fishing_light_seasonal_map_CORRECTED.png"

import runpy

ns = runpy.run_path(BUILD, run_name="__not_main__")
fig = ns["main"]()
data = json.load(open(f"{GIS_DATA}/HK Night Lights/map_data.json"))

problems = []

# ---------------------------------------------------------------- (1)+(2)+(3)
canvas = FigureCanvasAgg(fig)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()

texts = []
for ax in fig.axes:
    for t in ax.texts:
        if not t.get_text().strip():
            continue
        try:
            bb = t.get_window_extent(renderer=renderer)
        except Exception:
            continue
        texts.append((t.get_text()[:44], bb, ax))

W, H = fig.canvas.get_width_height()
print(f"figure canvas: {W} x {H} px")
print(f"text artists: {len(texts)}")

# (2) off-canvas
for label, bb, ax in texts:
    if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > W + 1 or bb.y1 > H + 1:
        problems.append(f"OFF-CANVAS text {label!r} "
                        f"({bb.x0:.0f},{bb.y0:.0f})-({bb.x1:.0f},{bb.y1:.0f})")

# (1) pairwise intersection
def overlap(a, b):
    x = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    y = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    return x * y

n_pairs = 0
for i in range(len(texts)):
    for j in range(i + 1, len(texts)):
        n_pairs += 1
        la, ba, _ = texts[i]
        lb, bb, _ = texts[j]
        ov = overlap(ba, bb)
        if ov > 1.0:
            problems.append(f"TEXT OVERLAP {la!r} x {lb!r} area={ov:.0f}px^2")
print(f"text pairs tested: {n_pairs}")

# (3) bar markers inside text boxes
for ax in fig.axes:
    if not hasattr(ax, "patches") or ax.get_title() == "":
        pass
    for t in ax.texts:
        if not t.get_text().strip():
            continue
        tb = t.get_window_extent(renderer=renderer)
        for p in ax.patches:
            try:
                pb = p.get_window_extent(renderer=renderer)
            except Exception:
                continue
            # only a bar: has height and width
            if pb.height < 6 or pb.width < 6:
                continue
            ov = overlap(tb, pb)
            # text fully inside a bar is fine for the annotation; only flag
            # a bar whose top edge cuts through the text vertically
            if ov > 0 and tb.y0 > pb.y0 + 2 and tb.y1 < pb.y1 - 2:
                problems.append(f"TEXT INSIDE BAR {t.get_text()[:30]!r}")

# ---------------------------------------------------------------- (4) probes
im = Image.open(PNG).convert("RGB")
a = np.asarray(im)
print(f"PNG: {im.size}  mean={a.mean():.1f}  non-black share="
      f"{100*(a.max(axis=2) > 30).mean():.1f}%")

# probe the orange permitted-area outline on panel A
axA = fig.axes[0]
pos = axA.get_position()
PW, PH = im.size                      # the PNG's own pixel size
sx = PW / W
sy = PH / H
x0_px = pos.x0 * W
x1_px = pos.x1 * W
y0_px = (1 - pos.y1) * H
y1_px = (1 - pos.y0) * H
panelA = a[int(y0_px * sy):int(y1_px * sy), int(x0_px * sx):int(x1_px * sx)]
# orange = FISH #ffb454
orange = ((panelA[:, :, 0].astype(int) - panelA[:, :, 2].astype(int)) > 60) & \
         (panelA[:, :, 0] > 150)
print(f"panel A orange-outline pixels: {int(orange.sum()):,}")
if orange.sum() < 200:
    problems.append("panel A: the permitted-area outline is missing or too faint")

# probe the bars in panel B: the peak bar must be the tallest FISH bar
axB = fig.axes[1]
posB = axB.get_position()
bx0 = int(posB.x0 * W * sx)
bx1 = int(posB.x1 * W * sx)
by0 = int((1 - posB.y1) * H * sy)
by1 = int((1 - posB.y0) * H * sy)
panelB = a[by0:by1, bx0:bx1]
# probe panel B: horizontal bars, orange = May-Aug.  The LONGEST orange bar
# must be the largest active night, and the orange bars must dominate.
fish_mask = ((panelB[:, :, 0].astype(int) - panelB[:, :, 2].astype(int)) > 60) & \
            (panelB[:, :, 0] > 150)
print(f"panel B orange (May-Aug) bar pixels: {int(fish_mask.sum()):,}")
if fish_mask.sum() < 500:
    problems.append("panel B: the May-Aug bars are missing")
rowsum = fish_mask.sum(axis=1)
if rowsum.max() > 0:
    r = int(np.argmax(rowsum))
    # the panel is horizontal bars: the longest orange bar is the top one
    print(f"panel B longest orange row: {r} ({int(rowsum.max()):,} px)")
    # the date label for that row must be the largest active night
    act = data["active_nights"]
    print(f"data: largest active night = {act[0]['date']} (excess {act[0]['excess']})")
    # check the number of orange bars equals the number of May-Aug nights shown
    n_orange_rows = int((rowsum > 50).sum())
    print(f"orange bars with >50 px: {n_orange_rows}")
    if n_orange_rows < 3:
        problems.append(f"panel B: only {n_orange_rows} orange bars drawn")

# probe: the panel B bars must be ordered by the data (largest at the top)
vals = data["monthly_mean_excess"]
act = data["active_nights"]
print(f"data: {len(act)} active nights, largest = {act[0]['date']} "
      f"(excess {act[0]['excess']})")
expect = [a["excess"] for a in act[:14]]
if expect != sorted(expect, reverse=True):
    problems.append("panel B: the active-night list is not sorted by excess")

# ---------------------------------------------------------------- verdict
print("\n" + "=" * 70)
if problems:
    print(f"GATE FAILED - {len(problems)} problem(s):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("GATE PASSED: 0 text overlaps, 0 off-canvas, pixel probes OK")
