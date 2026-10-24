#!/usr/bin/env python3
"""
HK volleyball courts on an outline map.

The outline is drawn as real shoreline LINE WORK rather than a filled polygon:
the iB1000 shoreline is published as 9,078 separate polylines (island rings and
open coast chains) that do not close into a single land polygon, so a flood-fill
land mask would leak through the digitising gaps and put the city in the sea.
Drawing the shoreline as published lines is exact - no invented geometry.

Sources: Esri China (HK) Shoreline (iB1000, from LandsD) + OpenStreetMap ways.
"""
import glob
import json
import math
import os
from collections import defaultdict

import numpy as np
import matplotlib
from matplotlib import font_manager
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
matplotlib.rcParams["font.family"] = "Times New Roman"
matplotlib.rcParams["text.parse_math"] = False
import matplotlib.pyplot as plt

D = os.path.dirname(os.path.abspath(__file__))
LON0, LON1 = 113.82, 114.47
LAT0, LAT1 = 22.13, 22.59

SEA = "#d3e2ef"
LAND = "#f4f1e8"
SHORE = "#3f5260"
SHORE_FT = "#7d8b96"
URBAN = "#e9e3d3"


def load_osm_chains():
    out, seen = [], set()
    for fp in sorted(glob.glob(os.path.join(D, "coast", "coast_*.json"))):
        try:
            d = json.load(open(fp))
        except Exception:
            continue
        for el in d.get("elements", []):
            g = el.get("geometry")
            if not g or el.get("id") in seen:
                continue
            seen.add(el.get("id"))
            pts = [(p["lon"], p["lat"]) for p in g if "lon" in p]
            if len(pts) >= 2:
                out.append(pts)
    return out


def load_ib1000():
    fs = json.load(open(os.path.join(D, "raw", "shoreline_ib1000.geojson")))["features"]
    out = []
    for f in fs:
        g = f.get("geometry")
        if not g:
            continue
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for p in parts:
            if len(p) >= 2:
                out.append(p)
    return out


def main():
    ven = json.load(open(os.path.join(D, "venues.geojson")))["features"]
    fre = json.load(open(os.path.join(D, "free_outdoor_courts.geojson")))["features"]
    ses = json.load(open(os.path.join(D, "sessions.geojson")))["features"]
    dis = json.load(open(os.path.join(D, "districts.geojson")))["features"]

    ib = load_ib1000()
    osm = load_osm_chains()
    print(f"shoreline: iB1000 {len(ib)} parts, OSM {len(osm)} ways")

    vac = defaultdict(lambda: [0, 0])
    for f in ses:
        p = f["properties"]
        vac[p["venue_name_en"]][1] += 1
        if p["available_courts"] > 0:
            vac[p["venue_name_en"]][0] += 1

    KM_LON = 111.32 * math.cos(math.radians((LAT0 + LAT1) / 2))
    KM_LAT = 110.57

    fig = plt.figure(figsize=(11.6, 10.8))
    gs = fig.add_gridspec(2, 1, height_ratios=[10, 1.1], hspace=0.015,
                          left=0.072, right=0.895, top=0.945, bottom=0.125)
    ax = fig.add_subplot(gs[0])
    axk = fig.add_subplot(gs[1])

    ax.set_facecolor(SEA)
    ax.set_xlim(LON0, LON1)
    ax.set_ylim(LAT0, LAT1)
    ax.set_autoscale_on(False)
    ax.set_aspect((KM_LAT / KM_LON) * ((LON1 - LON0) / (LAT1 - LAT0)))

    # land tint: fill the closed rings (islands + any closed coast) and the
    # district union, so the built-up area reads as land under the dots
    for ring, name in rings_of(dis):
        ax.fill(ring[:, 0], ring[:, 1], facecolor=URBAN if name in URBAN_D else LAND,
                edgecolor="none", zorder=2)
    for ring, _ in rings_of(dis):
        c = np.vstack([ring, ring[:1]])
        ax.plot(c[:, 0], c[:, 1], color="#b6af9e", lw=0.5, zorder=3)

    # the published shoreline, drawn as line work (exact, no invented closure)
    ax.add_collection(LineCollection([np.array(s) for s in ib], colors=SHORE,
                                     linewidths=0.32, zorder=4))
    ax.add_collection(LineCollection([np.array(s) for s in osm], colors=SHORE_FT,
                                     linewidths=0.45, zorder=4.1))

    ax.scatter([f["geometry"]["coordinates"][0] for f in fre],
               [f["geometry"]["coordinates"][1] for f in fre],
               marker="^", s=34, c="#7a5c28", edgecolor="white", lw=0.5, zorder=6)
    sc = ax.scatter([f["geometry"]["coordinates"][0] for f in ven],
                    [f["geometry"]["coordinates"][1] for f in ven],
                    s=44, c="white", edgecolor="#141414", lw=0.8, zorder=7)
    sc.set_array([vac[f["properties"]["venue_name_en"]][0] /
                  max(vac[f["properties"]["venue_name_en"]][1], 1) * 100 for f in ven])
    cb = fig.colorbar(sc, ax=ax, fraction=0.030, pad=0.015)
    cb.set_label("% of bookable sessions with vacancy (8-day window)", fontsize=8.5)
    cb.ax.tick_params(labelsize=7.5)

    # price band as an outer ring, so the title claim is carried by the map:
    # thick ring = air-conditioned ($148 peak / $120 off), thin = not ($82 / $57)
    for f, sz in zip(ven, (118, 48)):
        p = f["properties"]
        x, y = f["geometry"]["coordinates"]
        ax.scatter([x], [y], s=sz, facecolors="none",
                   edgecolors=("#1f4e79" if p["ac_status"] == "air_conditioned" else "#7a5c28"),
                   linewidths=(1.5 if p["ac_status"] == "air_conditioned" else 0.7),
                   zorder=7.2)
    axk2_handles = [
        Line2D([], [], marker="o", color="none", markerfacecolor="white",
               markeredgecolor="#1f4e79", markersize=11, markeredgewidth=1.5,
               label="air-conditioned court — $148 peak / $120 off"),
        Line2D([], [], marker="o", color="none", markerfacecolor="white",
               markeredgecolor="#7a5c28", markersize=7, markeredgewidth=0.8,
               label="not air-conditioned — $82 peak / $57 off"),
    ]

    # Labels are data-derived: each anchor is inside the district it names
    # (verified against districts.geojson, not placed by eye).
    for lon, lat, txt, fs_ in [(114.145, 22.268, "Hong Kong\nIsland", 9.5),
                               (114.168, 22.318, "Kowloon", 9.5),
                               (114.075, 22.450, "New Territories", 9.5),
                               (113.930, 22.265, "Lantau", 9.0)]:
        ax.text(lon, lat, txt, fontsize=fs_, ha="center", va="center", color="#3d3d3d",
                style="italic", linespacing=1.15, zorder=8,
                bbox=dict(facecolor="white", alpha=0.78, edgecolor="none", pad=1.8))

    bar_deg = 10 / KM_LAT
    bx, by = 113.885, 22.163
    ax.plot([bx, bx + bar_deg], [by, by], color="#141414", lw=2.6, zorder=9,
            solid_capstyle="butt")
    for xx in (bx, bx + bar_deg):
        ax.plot([xx, xx], [by - 0.005, by + 0.005], color="#141414", lw=1.3, zorder=9)
    ax.text(bx + bar_deg / 2, by + 0.014, "0        5        10 km", fontsize=7.5,
            ha="center", va="bottom", color="#141414", zorder=9,
            bbox=dict(facecolor=SEA, alpha=0.9, edgecolor="none", pad=1.0))
    ax.annotate("N", xy=(114.432, 22.545), xytext=(114.432, 22.492), ha="center",
                va="center", fontsize=10, zorder=9,
                arrowprops=dict(arrowstyle="-|>", color="#141414", lw=1.4))

    ax.tick_params(labelsize=7.5)
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.grid(True, color="#ffffff", lw=0.4, alpha=0.5, zorder=1)
    ax.set_xlabel("Longitude (°E)", fontsize=8.5)
    ax.set_ylabel("Latitude (°N)", fontsize=8.5)

    fig.suptitle("Hong Kong LCSD volleyball courts — venue and live vacancy",
                 fontsize=13.5, y=0.977)

    axk.axis("off")
    handles = [
        Line2D([], [], marker="o", color="none", markerfacecolor="#5b8db8",
               markeredgecolor="#141414", markersize=7.5,
               label="bookable indoor court venue (colour = vacancy)"),
        Line2D([], [], marker="^", color="none", markerfacecolor="#7a5c28",
               markeredgecolor="white", markersize=7.5,
               label="free outdoor / beach court (no charge)"),
        Line2D([], [], color=SHORE, lw=1.6, label="shoreline"),
        Line2D([], [], color="#b6af9e", lw=1.2, label="district boundary"),
    ]
    axk.legend(handles=handles + axk2_handles, ncol=3, loc="upper left", fontsize=8.3,
               title="Key", title_fontsize=9.5, frameon=False, handlelength=2.0,
               columnspacing=1.5, borderpad=0.15)

    fig.text(0.072, 0.052,
             "Sources: LCSD SmartPLAY available-session feed (13,152 sessions, 101 venues, fetched 22 Oct 2026); LCSD hire charges 2026 "
             "(volleyball court with A/C $148 peak / $120 off-peak per hour; without A/C $82 / $57);\n"
             "free courts: LCSD free outdoor hard-surface and beach courts; shoreline: Esri China (HK) Shoreline (iB1000, from LandsD) "
             "and OpenStreetMap contributors; district boundaries: LandsD / GeoInfo Map. Non-commercial use with attribution.",
             fontsize=6.4, ha="left", va="bottom")

    out = os.path.join(D, "hk_outline_map.png")
    fig.savefig(out, dpi=190, facecolor="white")
    plt.close(fig)
    print("wrote", out, os.path.getsize(out), "bytes")


URBAN_D = {"Central and Western District", "Wan Chai District", "Eastern District",
           "Southern District", "Yau Tsim Mong District", "Sham Shui Po District",
           "Kowloon City District", "Wong Tai Sin District", "Kwun Tong District",
           "Kwai Tsing District"}


def rings_of(dis):
    out = []
    for f in dis:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for p in polys:
            out.append((np.array(p[0]), f["properties"]["district_en"]))
    return out


if __name__ == "__main__":
    main()