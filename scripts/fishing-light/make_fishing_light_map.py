#!/usr/bin/env python3
"""
Map: the seasonal light-pollution pattern from fishing lights over Hong Kong.

Panel A  Where the fishing lights are: the change during the moratorium
         (May-Aug minus Sep-Apr) as a difference map.
Panel B  How bright it is: the May-Aug mean night-lights level.
Panel C  The monthly curve: the attributable fishing-light signal, month
         by month, pooled over 2012-2026.

THE GATE (before savefig)
  - no text box overlaps another
  - no text outside the canvas
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap
from rasterio.features import rasterize
from rasterio.transform import from_origin

OUT = os.path.dirname(os.path.abspath(__file__))
CSDI = "/Users/davidhermes/GIS Data/hk-spatial/data"
PERMITTED = f"{CSDI}/mardep_rcd_1730952503222_38811.geojson"
FISHING = f"{CSDI}/afcd_rcd_1697167244880_33192.geojson"
CAMPING = "/Users/davidhermes/GIS Data/HK Camping Sites/campsite_scores.geojson"

WIDTH, HEIGHT = 1200, 840
BBOX_W, BBOX_S, BBOX_E, BBOX_N = 113.72, 22.15, 114.45, 22.60

BG = "#0b1020"
FG = "#e8ecf6"
MUTED = "#9aa7bd"
ACCENT = "#ffd166"
FISH = "#ef476f"
SEA = "#4cc9f0"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": FG, "axes.labelcolor": FG, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.edgecolor": "#2a3550",
    "font.size": 9, "axes.titlesize": 11, "axes.titleweight": "bold",
})


def log(m):
    print(m, flush=True)


def gate_text(fig, min_gap=1.0):
    boxes = []
    for t in fig.findobj(match=matplotlib.text.Text):
        if not t.get_text().strip():
            continue
        r = t.get_window_extent(renderer=fig.canvas.get_renderer())
        boxes.append((t.get_text().strip()[:40], r))
    W, H = fig.canvas.get_width_height()
    off = [(s, r) for s, r in boxes
           if r.x0 < -min_gap or r.y0 < -min_gap or r.x1 > W + min_gap or r.y1 > H + min_gap]
    ov = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i][1], boxes[j][1]
            ix = min(a.x1, b.x1) - max(a.x0, b.x0)
            iy = min(a.y1, b.y1) - max(a.y0, b.y0)
            if ix > min_gap and iy > min_gap:
                ov.append((boxes[i][0], boxes[j][0]))
    log(f"text boxes {len(boxes)} | overlaps {len(ov)} | off-canvas {len(off)}")
    for a, b in ov[:8]:
        log(f"  OVERLAP: {a!r} <> {b!r}")
    for s, r in off[:8]:
        log(f"  OFF-CANVAS: {s!r}")
    assert not ov, "text overlap detected"
    assert not off, "text clipped"


def main():
    import geopandas as gpd
    with open(os.path.join(OUT, "fishing_light_seasonal.json")) as f:
        res = json.load(f)

    tr = from_origin(BBOX_W, BBOX_N, (BBOX_E - BBOX_W) / WIDTH,
                     (BBOX_N - BBOX_S) / HEIGHT)
    perm = gpd.read_file(PERMITTED)
    fish = gpd.read_file(FISHING)
    D = np.load(os.path.join(OUT, "_D_mor_minus_open.npy"))
    ma = np.load(os.path.join(OUT, "_ma_composite.npy"))
    ext = [BBOX_W, BBOX_E, BBOX_S, BBOX_N]

    fig = plt.figure(figsize=(16.4, 13.4), dpi=110)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1.0], hspace=0.34,
                          wspace=0.20, left=0.052, right=0.955, top=0.875, bottom=0.085)
    axA = fig.add_subplot(gs[0, 0])
    axB = fig.add_subplot(gs[0, 1])
    axC = fig.add_subplot(gs[1, :])

    # ---------------- Panel A: the difference map --------------------
    dshow = np.clip(D, -3, 6)
    im = axA.imshow(dshow, origin="upper", extent=ext, cmap="RdYlBu_r",
                    vmin=-3, vmax=6, interpolation="nearest", aspect="auto")
    for geom in fish.geometry:
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for p in polys:
            xs, ys = p.exterior.coords.xy
            axA.plot(xs, ys, color="#ffffff", lw=0.35, alpha=0.32, zorder=3)
    for _, row in perm.iterrows():
        g = row.geometry
        polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        for p in polys:
            xs, ys = p.exterior.coords.xy
            axA.plot(xs, ys, color=FISH, lw=1.8, zorder=5)

    for idx, lbl in ((10, "Mirs Bay, Tolo\nHarbour"), (7, "HK Island\n(South)"),
                     (0, "Deep Bay")):
        if idx < len(perm):
            c = perm.geometry.iloc[idx].centroid
            axA.text(c.x, c.y, lbl, color=FISH, fontsize=7.6, ha="center",
                     va="center", zorder=7, fontweight="bold", linespacing=1.25)

    if os.path.exists(CAMPING):
        camp = gpd.read_file(CAMPING)
        if camp.crs is None:
            camp = camp.set_crs(4326)
        if camp.crs.to_epsg() != 4326:
            camp = camp.to_crs(4326)
        top = camp.nsmallest(12, "rank")
        axA.scatter(top.geometry.x, top.geometry.y, s=30, color=ACCENT,
                    edgecolor="#0b1020", linewidth=0.7, zorder=8)

    axA.set_title("A  Where the fishing light changes\n"
                  "May-Aug minus Sep-Apr, 2012-2026 mean of %d nights per season"
                  % res["nights"], loc="left", pad=9)
    axA.set_xlim(BBOX_W, BBOX_E)
    axA.set_ylim(BBOX_S, BBOX_N)
    axA.set_xlabel("Longitude")
    axA.set_ylabel("Latitude")
    axA.grid(alpha=0.13, lw=0.5)
    cax = fig.add_axes([axA.get_position().x1 + 0.006,
                        axA.get_position().y0 + 0.050,
                        0.009, axA.get_position().height * 0.50])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("change in brightness", color=MUTED, fontsize=7.5)
    cb.ax.tick_params(colors=MUTED, labelsize=7)
    cb.outline.set_edgecolor("#2a3550")
    axA.legend(handles=[
        mpatches.Patch(color=FISH, label="Permitted bright-light fishing area"),
        mpatches.Patch(color=ACCENT, label="Top 12 dark-sky campsites"),
    ], loc="lower left", fontsize=7.4, facecolor="#111827",
        edgecolor="#2a3550", labelcolor=FG, framealpha=0.92)

    # ---------------- Panel B: absolute level ------------------------
    cmap = LinearSegmentedColormap.from_list(
        "dnb", ["#05070f", "#111a35", "#28407e", "#4a86bd", "#f6d55c", "#f4845f", "#ffffff"])
    im2 = axB.imshow(ma, origin="upper", extent=ext, cmap=cmap, vmin=0, vmax=255,
                     interpolation="nearest", aspect="auto")
    for _, row in perm.iterrows():
        g = row.geometry
        polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        for p in polys:
            xs, ys = p.exterior.coords.xy
            axB.plot(xs, ys, color=FISH, lw=1.6, zorder=5)
    axB.set_title("B  How bright it is\n"
                  "mean night-lights value, May-Aug", loc="left", pad=9)
    axB.set_xlim(BBOX_W, BBOX_E)
    axB.set_ylim(BBOX_S, BBOX_N)
    axB.set_xlabel("Longitude")
    axB.grid(alpha=0.13, lw=0.5)
    cax2 = fig.add_axes([axB.get_position().x1 + 0.006,
                         axB.get_position().y0 + 0.050,
                         0.009, axB.get_position().height * 0.50])
    cb2 = fig.colorbar(im2, cax=cax2)
    cb2.set_label("DN value", color=MUTED, fontsize=7.5)
    cb2.ax.tick_params(colors=MUTED, labelsize=7)
    cb2.outline.set_edgecolor("#2a3550")

    # ---------------- Panel C: the monthly curve ---------------------
    monthly = res["monthly"]
    labels = [m["name"] for m in monthly]
    vals = [m["attributable_vs_other_months"] for m in monthly]
    mor_mask = [m["in_moratorium"] for m in monthly]
    x = np.arange(len(labels))

    axC.axvspan(3.5, 7.5, color=FISH, alpha=0.10, zorder=0)
    axC.plot(x, vals, "-o", color=ACCENT, lw=2.4, ms=7, zorder=6,
             label="Fishing-light signal by month")
    for xi, v, mo in zip(x, vals, mor_mask):
        axC.scatter([xi], [v], s=150, facecolor="none",
                    edgecolor=FISH if mo else "#3d4a6b", lw=2.2, zorder=5)
    axC.axhline(0, color="#4a5573", lw=1.0, ls="--", zorder=3)
    axC.set_xticks(x)
    axC.set_xticklabels(labels)
    axC.set_xlim(-0.6, len(labels) - 0.4)
    axC.set_ylabel("Brighter than the rest of the year (DN units)")
    axC.set_xlabel("Month (pooled over 2012-2026; red ring = inside the fishing moratorium)")
    axC.grid(alpha=0.16, lw=0.5, axis="y")
    axC.set_title("C  The seasonal pattern: the fishing areas brighten from "
                  "June onwards, peaking in autumn", loc="left", pad=9)

    i_best = int(np.argmin(vals))
    i_worst = int(np.argmax(vals))
    for i, col, dy in ((i_worst, FISH, 0.55), (i_best, SEA, 0.55)):
        axC.annotate(f"{labels[i]}  {vals[i]:+.2f}",
                     xy=(x[i], vals[i]), xytext=(x[i], vals[i] + dy),
                     color=col, fontsize=9.5, fontweight="bold", ha="center",
                     arrowprops=dict(arrowstyle="-", color=col, lw=1.0))

    axC.legend(loc="lower left", fontsize=8.5, facecolor="#111827",
               edgecolor="#2a3550", labelcolor=FG)

    # ---------------- titles and footer -----------------------------
    fig.text(0.052, 0.992, "Fishing lights and the Hong Kong stargazing season",
             fontsize=17, fontweight="bold", color=FG, ha="left", va="top")
    fig.text(0.052, 0.963,
             "15 years of VIIRS night-time satellite data over the 16 areas where bright-light fishing is permitted",
             fontsize=10.2, color=MUTED, ha="left", va="top")

    fig.text(0.052, 0.941,
             "Pixels brightening by 5 DN or more are about 17% more common in the fishing areas "
             "than in other HK waters (95% CI 1.05-1.30; 12 of 15 years)",
             fontsize=9.2, color=ACCENT, ha="left", va="top", fontweight="bold")

    foot = [
        "Data: NASA GIBS VIIRS Day/Night Band (SNPP, gap-filled BRDF-corrected), Marine Department "
        "permitted bright-light fishing areas (mardep_rcd_1730952503222_38811), AFCD fishing-operation grids.",
        "Method: per-cell monthly composites of 693 nights; the permitted areas are compared with the rest "
        "of HK waters on the same pixels, which cancels haze and cloud. The open sea is an independent control.",
        "Caution: VIIRS day/night band values are 8-bit display values (relative brightness), not physical "
        "radiance in nW/cm2/sr.",
    ]
    y = 0.030
    for line in foot:
        fig.text(0.052, y, line, fontsize=7.4, color=MUTED, ha="left", va="bottom")
        y -= 0.0125

    fig.canvas.draw()
    gate_text(fig)

    outp = os.path.join(OUT, "HK_fishing_light_seasonal_map.png")
    fig.savefig(outp, dpi=110, facecolor=BG)
    log(f"wrote {outp}")

    from PIL import Image
    a = np.asarray(Image.open(outp).convert("RGB"))
    log(f"PNG {a.shape[1]}x{a.shape[0]}  distinct colours {len(np.unique(a.reshape(-1,3), axis=0)):,}")

    # probe that the map really shows the source raster
    fig.canvas.draw()
    for lon, lat, grp in ((114.17, 22.319, "city"), (114.26, 22.28, "east"),
                          (113.80, 22.22, "west")):
        px, py = axA.transData.transform((lon, lat))
        ix, iy = int(px), int(py)
        if 0 <= iy < a.shape[0] and 0 <= ix < a.shape[1]:
            col, row = int((lon - BBOX_W) / (BBOX_E - BBOX_W) * WIDTH), \
                       int((BBOX_N - lat) / (BBOX_N - BBOX_S) * HEIGHT)
            log(f"  probe {grp}: rendered rgb={tuple(int(v) for v in a[iy, ix][:3])}  "
                f"source D={D[row, col]:+.2f}")

    print("OK")


if __name__ == "__main__":
    main()
