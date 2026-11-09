#!/usr/bin/env python3
"""
Build the camping-site figure: night sky quality over Hong Kong.

Two panels:
  A  The VIIRS night-lights composite for Hong Kong with the 41 campsites
     marked and labelled by rank.
  B  The campsites ranked by a composite score, as a horizontal bar chart,
     with the four factor terms shown as a stacked bar.

Figure style follows the established house rules for David's figures:
  - facts only, no decoration
  - full term first ("30 degrees", not "30°")
  - nothing drawn over text
  - a pixel probe to prove the map is not blank
  - a text-overlap gate BEFORE the file is written

Run:  ls-venv/bin/python make_camping_map.py
"""
import json
import os

import matplotlib
GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.patches import Patch
from rasterio.plot import reshape_as_image
from rasterio.transform import rowcol

# Paths can be overridden from the environment so that the copy in the
# NPLGIS repo runs on another machine:
#   CAMPING_DATA_DIR   where campsite_scores.csv lives
#   NIGHTLIGHTS_DIR    where raw/night_composite_median.tif lives
BASE = os.environ.get("GIS_DATA_DIR", f"{GIS_DATA}")
OUT = os.environ.get("CAMPING_DATA_DIR", f"{BASE}/HK Camping Sites")
NL = os.environ.get("NIGHTLIGHTS_DIR", f"{BASE}/HK Night Lights")
N_COMP = f"{NL}/raw/night_composite_median.tif"
# The OSM coastline is an optional orientation overlay only.  It is not
# shipped, and the map is correct without it.
COAST_WAYS = os.environ.get("COAST_WAYS_JSON",
                            f"{OUT}/_coast_ways.json")

LAND = "#EFE9DC"
SEA = "#FFFFFF"
DARK = "#2C3E50"
ACCENT = "#C1666B"
GOOD = "#4E7A5A"


def log(m):
    print(m, flush=True)


def build():
    df = pd.read_csv(f"{OUT}/campsite_scores.csv")
    log(f"loaded {len(df)} scored campsites")

    ds = rasterio.open(N_COMP)
    arr = ds.read(1)
    log(f"composite {ds.width}x{ds.height} {ds.crs} range {arr.min()}-{arr.max()}")
    assert arr.max() > 0, "night-lights composite is BLANK"

    # The composite is an 8-bit display render: stretch so the dark rural
    # areas are legible, and state that in the source line.
    v = arr.astype(np.float32)
    lo, hi = np.percentile(v, 2), np.percentile(v, 99.5)
    v = np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)

    # NO land mask is applied, and none is needed.  Every Hong Kong land
    # polygon in the public set includes territorial waters (LandsD iC1000
    # ~2130 km2, DC constituencies ~2768 km2, OSM relation 913110
    # ~2770 km2, against ~1106 km2 of real land), and the alternatives
    # fail their own point tests.  The sea is genuinely dark in this
    # raster (open sea 13 against Mong Kok 255), so masking would remove
    # information rather than add it.  The coastline is drawn below as a
    # thin orientation line only.

    fig = plt.figure(figsize=(17.5, 14.4), facecolor="white")
    gs = fig.add_gridspec(2, 1, height_ratios=[1.28, 1.0],
                          hspace=0.34, left=0.195, right=0.968,
                          top=0.902, bottom=0.175)

    # ------------------------------------------------------------ PANEL A
    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(SEA)

    # raster: use the stretched value directly.
    #
    # CRITICAL: the raster is already (rows=lat, cols=lon).  imshow with
    # origin='upper' expects exactly that layout, so it must NOT be
    # transposed.  An earlier version transposed it, which silently
    # MIRRORED the image across the diagonal - Mong Kok's bright urban
    # core was being drawn over Sai Kung and the map looked plausible
    # while being completely wrong.
    #
    # NO LAND MASK IS APPLIED, and that is deliberate.  A light-pollution
    # map should show the sea as dark, because the sea really is dark -
    # the raster already encodes that (open sea 13, Mong Kok 255).  Every
    # candidate land mask failed: LandsD iC1000, the 2023 District
    # Council constituencies and the OSM administrative relation all
    # include territorial waters, the DTM validity mask interpolates the
    # harbour, and Natural Earth is too coarse.  Masking would have
    # REMOVED information rather than added it.
    disp = np.ma.masked_invalid(v)
    im = ax.imshow(disp, extent=[ds.bounds.left, ds.bounds.right,
                                 ds.bounds.bottom, ds.bounds.top],
                   origin="upper", cmap="magma", vmin=0, vmax=1,
                   alpha=1.0, zorder=1, interpolation="bilinear")

    # The coastline as a thin line, for orientation only.
    try:
        import json as _json
        cw = COAST_WAYS
        if os.path.exists(cw):
            segs = _json.load(open(cw))
            for s in segs:
                if len(s) >= 2:
                    xs = [p[0] for p in s]
                    ys = [p[1] for p in s]
                    ax.plot(xs, ys, color="#7A6A55", lw=0.35, alpha=0.55,
                            zorder=2)
            log(f"  coastline overlay: {len(segs)} segments")
    except Exception as e:
        log(f"  coastline overlay skipped: {e}")

    ax.set_xlim(ds.bounds.left, ds.bounds.right)
    ax.set_ylim(ds.bounds.bottom, ds.bounds.top)
    ax.set_xlabel("Longitude (degrees E)", fontsize=10)
    ax.set_ylabel("Latitude (degrees N)", fontsize=10)
    ax.tick_params(labelsize=9)
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)

    # campsites
    top = df.head(10)
    for _, r in df.iterrows():
        is_top = r["rank"] <= 10
        ax.scatter(r["lon"], r["lat"], s=46 if is_top else 20,
                   c=ACCENT if is_top else "#FFFFFF",
                   edgecolors="#2C1013" if is_top else "#4A4A4A",
                   linewidths=1.0 if is_top else 0.6,
                   zorder=5 if is_top else 4, alpha=1.0 if is_top else 0.85)

    # Label the top 6 only, with rank.  The two darkest sites (Wan Tsai
    # South and West) sit ~700 m apart, so a fixed offset makes their
    # labels collide.  The position is resolved in PIXEL space, trying
    # candidate offsets until the rendered box clears everything placed
    # so far.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    placed = []
    CAND = [(0, 16), (0, -16), (0, 30), (0, -30), (26, 14), (-26, 14),
            (26, -14), (-26, -14), (0, 44), (0, -44), (42, 14), (-42, 14),
            (42, -14), (-42, -14), (0, 58), (0, -58)]

    def grown(bb, pad):
        from matplotlib.transforms import Bbox
        return Bbox.from_extents(bb.x0 - pad, bb.y0 - pad,
                                 bb.x1 + pad, bb.y1 + pad)

    for _, r in df.nsmallest(6, "rank").iterrows():
        txt = f"#{int(r['rank'])}"
        t = ax.text(r["lon"], r["lat"], txt, fontsize=8.5, fontweight="bold",
                    color="#2C1013", ha="center", va="center", zorder=8,
                    bbox=dict(facecolor="white", alpha=0.9,
                              edgecolor="#2C1013", linewidth=0.5, pad=1.8))
        base_px = ax.transData.transform((r["lon"], r["lat"]))
        chosen = None
        for dx, dy in CAND:
            t.set_position(ax.transData.inverted().transform(
                (base_px[0] + dx, base_px[1] + dy)))
            bb = t.get_window_extent(renderer=renderer)
            clash = False
            for pb in placed:
                a = grown(bb, 3.0)
                b = grown(pb, 3.0)
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
            t.set_position((r["lon"], r["lat"]))
            placed.append(t.get_window_extent(renderer=renderer))
            log(f"  WARN: no clear slot for label {txt}")

    # legend
    handles = [
        Patch(facecolor="#FFFFFF", edgecolor="#4A4A4A", label="Campsite"),
        Patch(facecolor=ACCENT, edgecolor="#2C1013", label="Top 10 darkest"),
        Patch(facecolor="#3B2A5A", label="Brighter sky (light pollution)"),
        Patch(facecolor="#0B0718", label="Darkest sky"),
    ]
    lg = ax.legend(handles=handles, loc="lower left", fontsize=9.5,
                   frameon=True, framealpha=0.95, ncol=2,
                   borderpad=0.8, handlelength=1.4, columnspacing=1.4)
    lg.get_frame().set_edgecolor("#CCCCCC")

    # scale bar + north arrow
    # The scale bar sits bottom-RIGHT: an earlier version put it bottom-left,
    # directly under the legend, and the two text boxes collided.
    km_per_deg = 111.32 * np.cos(np.radians(22.37))
    bx, by = 114.12, 22.185
    seg = 10.0 / km_per_deg
    ax.plot([bx, bx + seg], [by, by], color="#222222", lw=3.0,
            solid_capstyle="butt", zorder=9)
    ax.text(bx + seg / 2, by + 0.006, "10 km", ha="center", va="bottom",
            fontsize=9, fontweight="bold", zorder=9,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.2))
    nx, ny = 114.42, 22.56
    ax.annotate("", xy=(nx, ny), xytext=(nx, ny - 0.048),
                arrowprops=dict(arrowstyle="-|>", color="#222222", lw=1.8), zorder=9)
    ax.text(nx, ny + 0.004, "N", ha="center", va="bottom", fontsize=10,
            fontweight="bold", zorder=9,
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1.2))

    # ------------------------------------------------------------ PANEL B
    ax2 = fig.add_subplot(gs[1])
    d = df.sort_values("score", ascending=True).tail(20)
    y = np.arange(len(d))
    # stacked contributions
    w_light, w_access, w_facility, w_view = 0.50, 0.20, 0.20, 0.10
    # recompute the weighted terms from the stored normalised scores
    contrib_light = w_light * df.set_index("site").loc[d["site"], "s_dark"].values
    contrib_access = w_access * (1 - (d["walk_to_vc_m"] - df["walk_to_vc_m"].min())
                                 / max(df["walk_to_vc_m"].max() - df["walk_to_vc_m"].min(), 1e-9))
    tent_pts = {"Less than 20": 1, "20-50": 2, "More than 50": 3}
    water_pts = {"TAP": 3, "FLUSHING TOILET": 3, "STREAM WATER (SEASONAL SUPPLY)": 1}
    def normv(s):
        lo, hi = float(s.min()), float(s.max())
        return (s - lo) / (hi - lo) if hi > lo else s * 0 + 0.5
    dfx = df.set_index("site")
    contrib_fac = w_facility * (0.6 * normv(dfx.loc[d["site"], "tent_space"].map(tent_pts).astype(float)).values
                              + 0.4 * normv(dfx.loc[d["site"], "water"].map(water_pts).astype(float)).values)
    rel = dfx.loc[d["site"], "relief_500m"].astype(float)
    contrib_view = w_view * (1 - normv(rel).values)

    ax2.barh(y, contrib_light, color="#2C3E50", label="Darkness (50%)", height=0.68)
    ax2.barh(y, contrib_access, left=contrib_light, color="#6B8EAD",
             label="Access (20%)", height=0.68)
    ax2.barh(y, contrib_fac, left=contrib_light + contrib_access,
             color="#D9A15B", label="Facilities (20%)", height=0.68)
    ax2.barh(y, contrib_view, left=contrib_light + contrib_access + contrib_fac,
             color="#8FB996", label="Open horizon (10%)", height=0.68)

    labels = [f"{int(r['rank'])}. {r['site']}" for _, r in d.iterrows()]
    ax2.set_yticks(y)
    ax2.set_yticklabels(labels, fontsize=9)
    ax2.set_xlabel("Weighted score contribution", fontsize=10)
    ax2.set_xlim(0, 1.0)
    ax2.grid(axis="x", alpha=0.25, linewidth=0.7)
    ax2.set_axisbelow(True)
    for sp in ("top", "right"):
        ax2.spines[sp].set_visible(False)
    lg2 = ax2.legend(loc="lower right", fontsize=9, frameon=True, ncol=2)
    lg2.get_frame().set_edgecolor("#CCCCCC")

    # annotate the DNB value at the end of each bar
    for i, (_, r) in enumerate(d.iterrows()):
        ax2.text(r["score"] + 0.012, i, f"DNB {int(r['dnb'])}",
                 va="center", fontsize=8.5, color="#333333")

    # ------------------------------------------------------------- titles
    # Panel titles are placed as FIGURE text, not axes titles: an axes
    # title sits directly above the axes and collides with the top row of
    # tick labels (and with in-map rank labels).
    fig.text(0.065, 0.968,
             "Light pollution across Hong Kong, and every country-park campsite",
             fontsize=16, fontweight="bold", va="bottom", ha="left")
    fig.text(0.065, 0.948,
             "Brighter sky = more light pollution.  Each marker is a campsite; "
             "the six darkest are numbered by rank.",
             fontsize=10.5, color="#555555", va="bottom", ha="left")

    # Panel B title, placed above the second axes but clear of panel A's
    # x-axis label.
    b0 = ax2.get_position()
    fig.text(0.065, b0.y1 + 0.030,
             "The 20 best campsites: what earns each one its place",
             fontsize=15, fontweight="bold", va="bottom", ha="left")

    # ------------------------------------------------------------- footer
    # Split into short lines: at 8.2 pt across a 17.5 inch figure, a long
    # sentence overflows the right margin and the gate catches it.
    fig.text(0.065, 0.012,
             "Light pollution: VIIRS Day/Night Band, NOAA-21, median of 12 nights "
             "27 Oct - 7 Nov 2026, NASA GIBS.\n"
             "Brightness is an 8-bit display render, not calibrated radiance. "
             "No land mask is applied - the sea is genuinely dark, and every\n"
             "official Hong Kong land-boundary dataset includes territorial waters.\n"
             "Campsites: AFCD, Location of campsites in country parks "
             "(41 sites, 13 country parks). Visitor centres: AFCD.\n"
             "Terrain: LandsD 5 m DTM via the 20 m grid. "
             "Analysis: Hermes Agent, 6 Nov 2026.",
             fontsize=8.2, color="#555555", va="bottom", ha="left", linespacing=1.45)

    # Record the exact pixel geometry for the pixel probe.
    #
    # The probe has to map lon/lat onto PNG pixels.  Doing that by hand
    # from the axes box is WRONG: imshow sets aspect='equal', so
    # matplotlib letterboxes the plot area inside the axes rectangle and
    # the data does not fill it.  The only exact way is to ask the
    # transform itself, so the builder records the display coordinates of
    # each probe point (and the colour the source raster should give).
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    bb = ax.get_window_extent(renderer=r)
    fig_w_px = fig.get_figwidth() * fig.dpi
    fig_h_px = fig.get_figheight() * fig.dpi

    import geopandas as gpd
    from shapely.geometry import Point

    # --- sample points across the whole bbox, land AND sea ------------
    # No land mask is applied (see the build notes), so the raster must be
    # correct EVERYWHERE - over the bright city, over dark country and
    # over the dark sea alike.  A stratified sample checks all three.
    import matplotlib
    ds_probe = rasterio.open(N_COMP)
    arr_p = ds_probe.read(1).astype(np.float32)
    lo_p, hi_p = np.percentile(arr_p, 2), np.percentile(arr_p, 99.5)
    cmap_p = matplotlib.colormaps["magma"]
    ALPHA_P = 1.0

    def expect_at(lon, lat):
        rr, cc = rowcol(ds_probe.transform, lon, lat)
        if not (0 <= rr < arr_p.shape[0] and 0 <= cc < arr_p.shape[1]):
            return None
        v = float(np.clip((arr_p[rr, cc] - lo_p) / max(hi_p - lo_p, 1e-6), 0, 1))
        rgba = cmap_p(v)
        return [ALPHA_P * rgba[i] * 255 + (1 - ALPHA_P) * 255 for i in range(3)]

    # Bright city, dark country, dark sea - one group each.
    GROUPS = {
        "city": [(114.170, 22.319), (114.175, 22.310), (114.160, 22.325),
                 (114.165, 22.300), (114.180, 22.315)],
        "country": [(114.271, 22.381), (114.120, 22.410), (114.030, 22.440),
                    (113.930, 22.250), (114.290, 22.333), (114.190, 22.380)],
        "sea": [(114.400, 22.200), (114.140, 22.275), (113.800, 22.220),
                (114.430, 22.450), (114.200, 22.165), (114.340, 22.230)],
    }
    probes = []
    for grp, pts in GROUPS.items():
        for lon, lat in pts:
            exp = expect_at(lon, lat)
            if exp is None:
                continue
            dx, dy = ax.transData.transform((lon, lat))
            probes.append({"group": grp, "lon": lon, "lat": lat,
                           "disp_x": dx, "disp_y": dy, "expect_rgb": exp})

    geom = {
        "dpi": fig.dpi,
        "fig_w_in": fig.get_figwidth(),
        "fig_h_in": fig.get_figheight(),
        "fig_w_px": fig_w_px,
        "fig_h_px": fig_h_px,
        "panelA_px": [bb.x0, bb.y0, bb.x1, bb.y1],
        "panelB_px": list(ax2.get_window_extent(renderer=r).extents),
        "data_bounds": [ds.bounds.left, ds.bounds.bottom,
                        ds.bounds.right, ds.bounds.top],
        "probes": probes,
    }
    with open(os.path.join(OUT, "_figure_geometry.json"), "w") as f:
        json.dump(geom, f, indent=1)
    log(f"panel A pixel box: {[round(v) for v in geom['panelA_px']]}")
    log(f"recorded {len(probes)} land probe points with exact display coords")

    return fig, ax, ax2


def gate_and_save(fig, ax, ax2, outp):
    """Text-overlap and off-canvas gate, run BEFORE the file is written."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    import matplotlib
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
    Wp, Hp = fig.canvas.get_width_height()
    off = [l for l, bb in boxes
           if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > Wp + 2 or bb.y1 > Hp + 2]
    print(f"text boxes {len(boxes)} | overlaps {len(problems)} | off-canvas {len(off)}",
          flush=True)
    for p in problems:
        print("  OVERLAP:", p)
    for o in off:
        print("  OFF-CANVAS:", o)
    assert not problems, "text overlap detected"
    assert not off, "text clipped"

    fig.savefig(outp, dpi=190, facecolor="white")
    print("wrote", outp)


def probe_pixels(png):
    """Prove the map is not blank AND that the raster is drawn where it should be.

    Checking "the panel is not white" is not enough: this bbox is mostly
    sea, which is deliberately masked white.  And a single white pixel over
    land does not mean failure - a campsite marker can sit on the sample
    point.

    So this does the strong check: for many points sampled from INSIDE the
    land polygon, compute the colour the source raster should produce
    (magma colormap + the same percentile stretch + the same 0.88 alpha
    over a white background) and compare it with the actual PNG pixel.
    If the raster were missing, mis-registered, or blank, the colours
    would not match.
    """
    from PIL import Image
    geom = json.load(open(os.path.join(OUT, "_figure_geometry.json")))
    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    x0, y0, x1, y1 = geom["panelA_px"]

    # Display px (matplotlib, y UP) -> PNG px (y DOWN).  The builder stored
    # the exact display coordinates of each probe point, because imshow's
    # aspect='equal' letterboxes the data inside the axes box and a
    # hand-rolled lon/lat mapping lands on the wrong pixels.
    sx = w / geom["fig_w_px"]
    sy = h / geom["fig_h_px"]

    match = 0
    checked = 0
    white = 0
    diffs = []
    by_group = {}
    for p in geom["probes"]:
        x = int(round(p["disp_x"] * sx))
        y = int(round((geom["fig_h_px"] - p["disp_y"]) * sy))
        if not (0 <= x < w and 0 <= y < h):
            continue
        checked += 1
        got = px[x, y]
        exp = p["expect_rgb"]
        if got == (255, 255, 255):
            white += 1
        d = float(np.sqrt(sum((got[i] - exp[i]) ** 2 for i in range(3))))
        diffs.append(d)
        g = by_group.setdefault(p.get("group", "?"), [0, 0])
        g[1] += 1
        if d < 42:
            match += 1
            g[0] += 1

    print(f"probe points checked: {checked} | colour matches: {match} "
          f"({match/max(checked,1)*100:.0f}%) | pure white: {white} | "
          f"median RGB distance {np.median(diffs):.1f}")
    for gname, (m, t) in sorted(by_group.items()):
        print(f"    {gname:8s}: {m}/{t} match")
    assert checked >= 12, f"only checked {checked} probe points"
    assert match / checked > 0.85, \
        f"only {match}/{checked} probe pixels match the source raster - it is NOT drawn correctly"
    # Every group must be right, otherwise a systematic error (e.g. the
    # transpose bug) could hide inside an overall average.
    #
    # A campsite marker can legitimately sit on top of a probe pixel, so a
    # single mismatch is tolerated per group.  More than that means the
    # raster itself is wrong.
    for gname, (m, t) in by_group.items():
        assert m >= t - 1, \
            f"group {gname}: only {m}/{t} pixels match the raster"

    # Colour variety across the whole panel A (catches a blank panel).
    counts = {}
    px_top = int(round((geom["fig_h_px"] - y1) * sy))
    px_bot = int(round((geom["fig_h_px"] - y0) * sy))
    for yy in range(px_top, px_bot, 4):
        for xx in range(int(x0 * sx), int(x1 * sx), 4):
            c = px[xx, yy]
            counts[c] = counts.get(c, 0) + 1
    total = sum(counts.values())
    print(f"panel A probe: {total:,} sampled, {len(counts)} distinct colours")
    assert len(counts) > 400, f"only {len(counts)} distinct colours - the raster did not render"


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fig, ax, ax2 = build()
    outp = os.path.join(OUT, "HK_camping_sites_dark_sky_map.png")
    gate_and_save(fig, ax, ax2, outp)
    probe_pixels(outp)
    print("OK")
