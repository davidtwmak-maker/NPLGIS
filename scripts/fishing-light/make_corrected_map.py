#!/usr/bin/env python3
"""
CORRECTED MAP: fishing lights over Hong Kong.

Three panels:
  A  Where the light comes from - the 16 permitted bright-light fishing areas
     over Hong Kong, with the deep-water analysis domain marked.
  B  The seasonal signal - the monthly excess of bright deep-water cells
     inside the permitted areas versus the control water.
  C  The active nights - the individual nights on which the signal appeared,
     by month of the year.

All numbers come from definitive_analysis.py / final_summary.py.
"""
import collections
import json
import math
import os
import statistics
from datetime import datetime

import numpy as np
import rasterio
import geopandas as gpd
import matplotlib
GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

ROOT = os.environ.get("GIS_DATA_DIR", f"{GIS_DATA}") + "/HK Night Lights"
RAW = f"{ROOT}/raw_seasonal"
CSDI = f"{GIS_DATA}/hk-spatial/data"
COAST = "/tmp/_coast_ways_full.json"
OUT = f"{ROOT}/HK_fishing_light_seasonal_map_CORRECTED.png"

W, H = 1200, 840
TR = from_origin(113.72, 22.60, (114.45 - 113.72) / W, (22.60 - 22.15) / H)
XRES = abs(TR.a) * 111.32 * math.cos(math.radians(22.375))
YRES = abs(TR.e) * 110.574
THR = 140
MOR = (5, 6, 7, 8)
NEW_MOON = datetime(2000, 1, 6, 18, 14)

BG = "#0d1117"
PANEL = "#131a23"
FG = "#e8edf2"
MUTED = "#8b98a5"
SEA = "#16202b"
FISH = "#ffb454"
ACCENT = "#4fc3f7"
GOOD = "#66bb6a"
BAD = "#ef5350"

MONTHS = list(range(1, 13))
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def log(m):
    print(m, flush=True)


def moon_pct(ds):
    d = datetime.fromisoformat(ds)
    days = (d - NEW_MOON).total_seconds() / 86400.0
    ph = (days % 29.530588853) / 29.530588853
    return (1 - math.cos(2 * math.pi * ph)) / 2 * 100


def build():
    ways = json.load(open(COAST))
    lines = [{"type": "LineString", "coordinates": [(p["lon"], p["lat"]) for p in w]}
             for w in ways]
    coast = rasterize(lines, out_shape=(H, W), transform=TR, fill=0,
                      dtype="uint8", all_touched=True).astype(bool)
    coast = ndimage.binary_dilation(coast, np.ones((7, 7)))
    lab, _ = ndimage.label(~coast)
    sea = (lab == lab[(H - 25, W - 25)])
    land = ~sea
    d2l = ndimage.distance_transform_edt(sea, sampling=(YRES, XRES))
    ri, ci = np.indices((H, W))
    xs = TR.c + ci * TR.a + TR.a / 2
    ys = TR.f + ri * TR.e + TR.e / 2
    fixed = np.zeros((H, W), dtype=bool)
    for lo, la in ((113.9705, 22.1545), (114.38, 22.56)):
        fixed |= np.hypot((xs - lo) * 111.32 * math.cos(math.radians(22.15)),
                          (ys - la) * 110.574) <= 3.0
    perm = gpd.read_file(f"{CSDI}/mardep_rcd_1730952503222_38811.geojson")
    pm = np.zeros((H, W), dtype=bool)
    for g in perm.geometry:
        pm |= rasterize([(g,  1)], out_shape=(H, W), transform=TR, fill=0,
                        dtype="uint8").astype(bool)
    pm &= sea
    return land, sea, d2l, fixed, pm, perm, xs, ys


def main():
    land, sea, d2l, fixed, pm, perm, xs, ys = build()
    dp = sea & (d2l >= 3.0) & pm & ~fixed
    dc = sea & (d2l >= 3.0) & ~pm & ~fixed
    # ---------- gather the numbers ----------
    rows = json.load(open(f"{ROOT}/seasonal_nights.json"))
    nights = [(r["date"], r["year"], r["month"]) for r in rows
              if os.path.exists(f"{RAW}/SNPP_{r['date']}.tif")]
    nights.sort()

    lit_p = collections.defaultdict(list)
    lit_c = collections.defaultdict(list)
    per_night = []
    for (date, year, month) in nights:
        a = rasterio.open(f"{RAW}/SNPP_{date}.tif").read(1)
        bp = dp & (a >= THR)
        bc = dc & (a >= THR)
        for r_, c_ in zip(*np.nonzero(bp)):
            lit_p[(r_, c_)].append(date)
        for r_, c_ in zip(*np.nonzero(bc)):
            lit_c[(r_, c_)].append(date)
        per_night.append({"date": date, "year": year, "month": month,
                          "moon": moon_pct(date),
                          "rp": float(bp.sum()) / int(dp.sum()) * 100,
                          "ro": float(bc.sum()) / int(dc.sum()) * 100})
    tp = collections.Counter(v[0] for v in lit_p.values() if len(v) == 1)
    tc = collections.Counter(v[0] for v in lit_c.values() if len(v) == 1)

    # monthly excess: MEDIAN over nights (the mean is dominated by the few
    # extreme control-water nights, which made every month look negative)
    mon_excess = []
    for m in MONTHS:
        v = [tp.get(r["date"], 0) - tc.get(r["date"], 0) for r in per_night
             if r["month"] == m]
        mon_excess.append(statistics.median(v))

    # the active nights
    scored = sorted(((r["date"], r["month"], tp.get(r["date"], 0) - tc.get(r["date"], 0))
                     for r in per_night), key=lambda x: -x[2])
    active = [s for s in scored if s[2] >= 20]
    active_by_month = collections.Counter(s[1] for s in active)
    n_active = len(active)
    n_active_mor = sum(1 for s in active if s[1] in MOR)

    json.dump({
        "monthly_mean_excess": {str(m): mon_excess[m - 1] for m in MONTHS},
        "active_by_month": {str(m): active_by_month.get(m, 0) for m in MONTHS},
        "n_active": n_active,
        "n_active_moratorium": n_active_mor,
        "active_nights": [{"date": s[0], "month": s[1], "excess": s[2]} for s in active],
    }, open(f"{ROOT}/map_data.json", "w"), indent=2)
    log(f"  wrote {ROOT}/map_data.json")

    fig = build_figure(mon_excess, active_by_month, active, n_active, n_active_mor,
                       land, sea, d2l, perm)
    fig.savefig(OUT, dpi=150, facecolor=BG)
    log(f"  wrote {OUT}")
    return fig


def build_figure(mon_excess, active_by_month, active, n_active, n_active_mor,
                 land, sea, d2l, perm):
    """Build and return the figure. Split out so the QC gate can inspect it."""
    # ---------- figure ----------
    fig = plt.figure(figsize=(15.5, 10.2), facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.42, 1.0], hspace=0.40,
                          wspace=0.20, left=0.052, right=0.955, top=0.885, bottom=0.085)

    # ---------- PANEL A: where ----------
    axA = fig.add_subplot(gs[0, 0])
    axA.set_facecolor(PANEL)
    axA.imshow(land, extent=[113.72, 114.45, 22.15, 22.60], origin="upper",
               cmap=matplotlib.colors.ListedColormap(["#22282e", "#2a3138"]),
               interpolation="nearest", vmin=0, vmax=1)
    axA.imshow(sea & ~land, extent=[113.72, 114.45, 22.15, 22.60], origin="upper",
               cmap=matplotlib.colors.ListedColormap([SEA, SEA]),
               interpolation="nearest", vmin=0, vmax=1)
    # deep-water analysis domain
    axA.imshow(d2l >= 3.0, extent=[113.72, 114.45, 22.15, 22.60], origin="upper",
               cmap=matplotlib.colors.ListedColormap(["#00000000", "#2b4a5e"]),
               alpha=0.55, interpolation="nearest", vmin=0, vmax=1)
    for g in perm.geometry:
        g2 = g
        axA.plot(*g2.exterior.xy, color=FISH, lw=1.5, zorder=5)
    # fixed structures that were excluded, as NUMBERED markers + a key line
    # (numbered badges, not floating callouts: floating labels collided with
    #  the place names and ran off the axes)
    for num, (lo, la) in ((1, (113.9705, 22.1545)), (2, (114.38, 22.56))):
        axA.plot(lo, la, "o", ms=7.5, mfc=BAD, mec="#1b232c", mew=1.0, zorder=9)
        axA.text(lo, la, str(num), color="#1b232c", fontsize=5.4,
                 fontweight="bold", ha="center", va="center", zorder=10)
    axA.text(0.012, 0.972,
             "orange outline: the 16 permitted bright-light fishing areas\n"
             "blue wash: deep water (>3 km from land) = the analysis domain\n"
             "excluded fixed light sources:  1 HK Offshore LNG terminal   2 Ma Liu Shui–Tung Ping Chau cable",
             transform=axA.transAxes, color=MUTED, fontsize=6.6,
             va="top", ha="left", zorder=11,
             bbox=dict(boxstyle="round,pad=0.35", facecolor="#131a23",
                       edgecolor="none", alpha=0.85))
    # HK place labels
    for nm, lo, la in (("Central", 114.16, 22.28), ("Sai Kung", 114.27, 22.38),
                       ("Mirs Bay", 114.18, 22.42), ("Deep Bay", 113.92, 22.45),
                       ("Lantau", 113.94, 22.24), ("Tolo Harbour", 114.16, 22.45)):
        axA.plot(lo, la, "o", ms=2.4, color=MUTED, zorder=6)
        axA.text(lo + 0.008, la + 0.004, nm, color=MUTED, fontsize=6.6, zorder=6)
    axA.set_xlim(113.72, 114.45)
    axA.set_ylim(22.15, 22.60)
    axA.set_title("A   Where the fishing lights are",
                  color=FG, fontsize=11.5, fontweight="bold", loc="left", pad=8)
    axA.tick_params(colors=MUTED, labelsize=7.5)
    for s in axA.spines.values():
        s.set_color("#333b44")
    axA.set_xlabel("longitude", color=MUTED, fontsize=7.5)
    axA.set_ylabel("latitude", color=MUTED, fontsize=7.5)

    # ---------- PANEL B: the active nights ----------
    # The monthly MEDIAN excess is ~0 in every month: on a typical night there
    # is no signal at all.  So panel B shows the nights that DID carry it.
    axB = fig.add_subplot(gs[0, 1])
    axB.set_facecolor(PANEL)
    top = active[:14][::-1]          # largest at the top
    ypos = np.arange(len(top))
    vals = [s[2] for s in top]
    axB.barh(ypos, vals,
             color=[FISH if s[1] in MOR else "#3d5a6c" for s in top],
             height=0.66, zorder=3, edgecolor=BG, linewidth=0.6)
    axB.set_yticks(ypos)
    axB.set_yticklabels([s[0][2:] for s in top], color=MUTED, fontsize=7.6)
    axB.set_xlabel("extra single-night bright cells inside the permitted areas "
                   "vs the control water", color=MUTED, fontsize=7.6)
    axB.tick_params(colors=MUTED, labelsize=7.6)
    for s in axB.spines.values():
        s.set_color("#333b44")
    axB.grid(axis="x", color="#2a3138", lw=0.7, zorder=1)
    axB.set_title("B   The signal is episodic: it arrives on a few nights",
                  color=FG, fontsize=11.5, fontweight="bold", loc="left", pad=8)
    axB.text(0.012, 0.955,
             "orange = the May–Aug fishing-moratorium window\n"
             "the 14 largest of 20 'active' nights; on a typical night the excess is zero",
             transform=axB.transAxes, color=MUTED, fontsize=7.2,
             va="top", ha="left", zorder=9)
    for i, s in enumerate(top):
        axB.text(s[2] + max(vals) * 0.015, i, f"{s[2]:,}", color=FG,
                 fontsize=7.2, va="center", ha="left", zorder=6)

    # ---------- PANEL C: active nights ----------
    axC = fig.add_subplot(gs[1, 0])
    axC.set_facecolor(PANEL)
    n_by_month = [active_by_month.get(m, 0) for m in MONTHS]
    x2 = np.arange(12)
    axC.bar(x2, n_by_month, color=[FISH if m in MOR else "#3d5a6c" for m in MONTHS],
            width=0.66, zorder=3, edgecolor=BG, linewidth=0.6)
    axC.axhline(0, color=MUTED, lw=0.9, zorder=4)
    axC.set_xticks(x2)
    axC.set_xticklabels(MON, color=MUTED, fontsize=8)
    axC.tick_params(colors=MUTED, labelsize=8)
    for s in axC.spines.values():
        s.set_color("#333b44")
    axC.grid(axis="y", color="#2a3138", lw=0.7, zorder=1)
    axC.set_ylabel("number of active nights\n(2012–2026, 15 years)", color=MUTED, fontsize=7.8)
    axC.set_title("C   The 20 nights the signal actually appeared on",
                  color=FG, fontsize=11.5, fontweight="bold", loc="left", pad=8)
    axC.text(0.012, 0.955,
             "an ‘active night’ = at least 20 more single-night bright cells inside the\n"
             "permitted areas than in the control water  (13 of 20 fall in May–Aug)",
             transform=axC.transAxes, color=MUTED, fontsize=7.2,
             va="top", ha="left", zorder=9)

    # ---------- PANEL D: the summary ----------
    axD = fig.add_subplot(gs[1, 1])
    axD.set_facecolor(PANEL)
    axD.axis("off")
    axD.set_title("D   What the data shows", color=FG, fontsize=11.5,
                  fontweight="bold", loc="left", pad=8)
    lines = [
        ("+0.31 pp", "seasonal excess of bright deep-water cells\ninside the permitted areas (May–Aug)"),
        ("95% CI", "[+0.09, +0.62]   p = 0.001   10 of 15 years"),
        ("+0.19 pp", "same estimate with 2018 removed\n(the single largest year)"),
        ("+0.12 pp", "same estimate with the 10 most extreme\nnights removed"),
        ("33%", "median moon phase of the vessel-like pixels\n(the sky must be dark to see them)"),
        ("20 nights", "out of 693 in 15 years carried the signal\n(about 2 per year, 13 of them in May–Aug)"),
    ]
    y = 0.93
    for big, small in lines:
        axD.text(0.012, y, big, color=FISH, fontsize=12.5, fontweight="bold",
                 va="top", ha="left", transform=axD.transAxes)
        axD.text(0.205, y + 0.012, small, color=MUTED, fontsize=7.6,
                 va="top", ha="left", transform=axD.transAxes)
        y -= 0.125
    axD.text(0.012, 0.045,
             "Where the vessels were found: the Soko Islands and West Lamma\n"
             "Channel and Mirs Bay / Tolo Harbour / Port Shelter — the west and\n"
             "east ends of the permitted area, not the whole of it.",
             color=FG, fontsize=7.6, va="bottom", ha="left", transform=axD.transAxes,
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#1b232c", edgecolor="#333b44"))

    # ---------- titles ----------
    fig.text(0.052, 0.988, "Fishing lights and the Hong Kong stargazing season",
             fontsize=17.5, fontweight="bold", color=FG, ha="left", va="top")
    fig.text(0.052, 0.960,
             "15 years of VIIRS day/night-band satellite data (2012–2026, 693 nights) · "
             "deep water only · fixed light sources excluded · year-block bootstrap",
             fontsize=9.2, color=MUTED, ha="left", va="top")

    fig.text(0.052, 0.026,
             "Source: NASA GIBS VIIRS_SNPP_GapFilled_BRDF_Corrected_DayNightBand_Radiance · "
             "Marine Department permitted bright-light fishing areas · AFCD fishing-operation grids · OSM coastline",
             fontsize=7.0, color=MUTED, ha="left", va="bottom")

    return fig


if __name__ == "__main__":
    main()
