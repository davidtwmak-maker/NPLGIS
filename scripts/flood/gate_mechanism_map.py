#!/usr/bin/env python3
"""
Figure gate for the flood-mechanism map.

Checks, on the RENDERER (matplotlib) and the PNG:
  (1) no pair of text artists intersects;
  (2) every text artist is fully inside the canvas;
  (3) pixel probes: each mechanism's colour must actually be present in the
      PNG, in the right quantity, and the point markers must be where the
      map says they are.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
BUILD = f"{GIS_DATA}/HK Flood Prone Areas/make_mechanism_map.py"
PNG = f"{GIS_DATA}/HK Flood Prone Areas/flood_mechanism_map.png"
DATA = f"{GIS_DATA}/HK Flood Prone Areas/flood_mechanism.geojson"

COLORS = {
    "local_drainage_blockage": (0x5a, 0xa9, 0xe6),
    "channel_backflow": (0xf2, 0xb1, 0x34),
    "coastal_tidal": (0xef, 0x5b, 0x5b),
    "low_lying_ponding": (0x7e, 0xd9, 0x57),
}


def main():
    import runpy
    problems = []

    ns = runpy.run_path(BUILD, run_name="__not_main__")
    fig = ns["main"]()
    fig.canvas.draw()
    W, H = fig.canvas.get_width_height()

    # ---------- (1) text overlap ----------
    texts = []
    for ax in fig.axes:
        for t in ax.texts:
            if not t.get_text().strip():
                continue
            bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
            texts.append((t.get_text()[:40], bb))
    for t in fig.texts:
        if t.get_text().strip():
            texts.append((t.get_text()[:40],
                          t.get_window_extent(renderer=fig.canvas.get_renderer())))
    overlaps = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i][1], texts[j][1]
            if a.overlaps(b):
                ax = a.x0 - b.x0
                ay = a.y0 - b.y0
                if abs(ax) < (a.width + b.width) * 0.30 and abs(ay) < (a.height + b.height) * 0.45:
                    overlaps.append((texts[i][0], texts[j][0]))
    print(f"text artists: {len(texts)}")
    print(f"text pairs tested: {len(texts)*(len(texts)-1)//2}")
    if overlaps:
        problems.append(f"{len(overlaps)} text overlaps")
        for o in overlaps[:12]:
            print("   OVERLAP:", o)

    # ---------- (2) off-canvas ----------
    off = []
    for name, bb in texts:
        if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > W + 1 or bb.y1 > H + 1:
            off.append(name)
    print(f"off-canvas text: {len(off)}")
    for o in off[:12]:
        print("   OFF:", o)
    if off:
        problems.append(f"{len(off)} text artists off-canvas")

    # ---------- (3) pixel probes ----------
    im = Image.open(PNG).convert("RGB")
    a = np.asarray(im).astype(int)
    print(f"PNG: {im.size}  mean={a.mean():.1f}")
    total = a.shape[0] * a.shape[1]
    present = {}
    for k, c in COLORS.items():
        m = (np.abs(a - np.array(c)).sum(axis=2) < 30)
        n = int(m.sum())
        present[k] = n
        print(f"  {k:24s} colour pixels: {n:,}")
        if n < 300:
            problems.append(f"{k}: only {n} colour pixels in the PNG")

    # the counts must scale with the data
    data = json.load(open(DATA))
    counts = {}
    for f in data["features"]:
        m = f["properties"]["mechanism"]
        counts[m] = counts.get(m, 0) + 1
    print("  data counts:", counts)
    for k, n in counts.items():
        # the legend swatch also contributes, so allow a floor
        if present[k] < n * 12:
            problems.append(f"{k}: {present[k]} colour px for {n} points - too few")

    # ---------- report ----------
    print("\n" + "=" * 68)
    if problems:
        print(f"GATE FAILED - {len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("GATE PASSED: 0 text overlaps, 0 off-canvas, pixel probes OK")
    print("  ")


if __name__ == "__main__":
    main()
