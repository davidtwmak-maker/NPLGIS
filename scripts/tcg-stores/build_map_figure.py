#!/usr/bin/env python3
"""Build the static map figure for the Hong Kong trading-card-game shop study.

House style (teaching-figures skill): Times New Roman, a Key box, a scale
bar, a north arrow, a source line, and plain decimal degrees on the axes.
White background.

The figure shows THREE things and each has its own channel:
  1. the 211 census small areas, coloured by the demand-to-supply ratio
     (people aged 15-24 within 1 km, per PLAY VENUE within 1 km);
  2. the 287 card shops, as dots - white where you can actually play,
     gold where the shop only sells cards, pink where it is an official
     Pokemon Gym;
  3. the shop clusters, named in the Key by area, not by callout.

The classes are FIXED CUT-POINTS, and the Key states them, so a reader can
compare two areas directly. A quantile scheme would make the Key's "% of
areas" column identical in every row by construction, which reads as a
result when it is not one.
"""
import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as pe

HERE = Path(__file__).resolve().parent
REPO = Path("/Users/davidhermes/nplgis")
OUT_DIR = REPO / "assets/maps/tcg-stores"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- house font ----------------------------------------------------------
for f in ("Times New Roman.ttf", "Times New Roman Bold.ttf",
          "Times New Roman Italic.ttf"):
    p = Path("/System/Library/Fonts/Supplemental") / f
    if p.exists():
        font_manager.fontManager.addfont(str(p))
plt.rcParams["font.family"] = ["Times New Roman", "DejaVu Sans"]
plt.rcParams["text.parse_math"] = False
plt.rcParams["axes.unicode_minus"] = False

# ---- extent (Hong Kong) --------------------------------------------------
LON0, LON1 = 113.83, 114.45
LAT0, LAT1 = 22.15, 22.58

# The choropleth classes - the same fixed cut-points the web map uses.
CLASSES = [
    (0, "#3a2f4a", "No play venue within 1 km"),
    (200, "#2d4a63", "Under 200 per venue"),
    (600, "#1f6f7a", "200 – 600 per venue"),
    (1500, "#2e9e6b", "600 – 1,500 per venue"),
    (3000, "#b8923a", "1,500 – 3,000 per venue"),
    (None, "#c85a4a", "Over 3,000 per venue"),
]


def class_of(v):
    if v is None:
        return CLASSES[0]
    for c in CLASSES:
        if c[0] is None or v <= c[0]:
            return c
    return CLASSES[-1]


def main():
    areas = json.load(open(HERE / "out/merged_metrics.geojson", encoding="utf-8"))
    metrics = {r["stpug"]: r for r in
               csv.DictReader(open(HERE / "out/merged_metrics.csv", encoding="utf-8"))}
    shops = json.load(open(HERE / "shops_merged.json", encoding="utf-8"))

    fig = plt.figure(figsize=(13.5, 15.0), dpi=200)
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(2, 1, height_ratios=[3.05, 1.0],
                          left=0.045, right=0.965, top=0.935, bottom=0.045,
                          hspace=0.075)
    ax = fig.add_subplot(gs[0])
    axk = fig.add_subplot(gs[1])
    ax.set_facecolor("white")
    axk.set_facecolor("white")

    # ---- the small areas -------------------------------------------------
    for f in areas["features"]:
        st = f["properties"]["id"]
        v = metrics[st]["y1524_per_play_1000m"]
        v = float(v) if v else None
        _, colour, _ = class_of(v)
        geom = f["geometry"]
        polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
                 else geom["coordinates"])
        for poly in polys:
            if not poly:
                continue
            ring = poly[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.fill(xs, ys, facecolor=colour, edgecolor="white",
                    linewidth=0.35, zorder=2)

    # ---- the shops --------------------------------------------------------
    # A shop you can PLAY at is a bigger white dot. A shop that only
    # sells cards is a small gold dot. A shop registered as an official
    # Pokemon Gym gets a pink ring, because a Gym registration means it
    # runs events.
    play, noplay, gym = [], [], []
    for s in shops:
        is_play = bool(s.get("ai_play_space") or s.get("ai_play_tag"))
        if s.get("gym_id"):
            gym.append(s)
        if is_play:
            play.append(s)
        else:
            noplay.append(s)
    for s in noplay:
        if s.get("gym_id"):
            continue
        ax.scatter(s["lon"], s["lat"], s=13, c="#e8c46a", edgecolors="#6b5a1e",
                   linewidths=0.35, zorder=5)
    for s in gym:
        ax.scatter(s["lon"], s["lat"], s=22, c="#ff8fb1", edgecolors="#7a2f4a",
                   linewidths=0.5, zorder=6)
    for s in play:
        ax.scatter(s["lon"], s["lat"], s=26, c="white", edgecolors="#1a1a1a",
                   linewidths=0.55, zorder=7)

    ax.set_xlim(LON0, LON1)
    ax.set_ylim(LAT0, LAT1)
    ax.set_aspect(1.0 / math.cos(math.radians((LAT0 + LAT1) / 2)))
    ax.tick_params(labelsize=8.5)
    ax.set_xlabel("Longitude (°E)", fontsize=9.5)
    ax.set_ylabel("Latitude (°N)", fontsize=9.5)
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.grid(True, color="#dddddd", linewidth=0.4, zorder=1)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_color("#555555")

    # ---- scale bar, drawn in DATA coordinates ------------------------------
    # 20 km of longitude at this latitude.
    lat_mid = (LAT0 + LAT1) / 2
    km20_lon = 20.0 / (111.32 * math.cos(math.radians(lat_mid)))
    sb_x, sb_y = 113.86, 22.175
    ax.plot([sb_x, sb_x + km20_lon], [sb_y, sb_y], color="black",
            linewidth=2.4, solid_capstyle="butt", zorder=10)
    for xx in (sb_x, sb_x + km20_lon):
        ax.plot([xx, xx], [sb_y, sb_y + 0.006], color="black",
                linewidth=1.4, zorder=10)
    ax.text(sb_x + km20_lon / 2, sb_y + 0.009, "20 km", ha="center",
            va="bottom", fontsize=9, zorder=10,
            path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])

    # ---- north arrow ------------------------------------------------------
    nx, ny = 114.36, 22.50
    ax.annotate("N", xy=(nx, ny), xytext=(nx, ny - 0.052),
                ha="center", va="bottom", fontsize=13, zorder=10,
                arrowprops=dict(arrowstyle="-|>", color="black", linewidth=1.7),
                path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])

    # ---- titles ------------------------------------------------------------
    fig.text(0.045, 0.972, "Where can you go to play trading card games in Hong Kong?",
             fontsize=16, ha="left", va="top", fontweight="bold")
    fig.text(0.045, 0.950,
             "287 card shops and 55 play venues against the 2021 Population "
             "Census: the number of 15–24-year-olds within 1 km, per play "
             "venue within 1 km",
             fontsize=10.5, ha="left", va="top", color="#333333")

    # ---- the Key -----------------------------------------------------------
    axk.axis("off")
    axk.set_xlim(0, 100)
    axk.set_ylim(0, 100)

    axk.add_patch(FancyBboxPatch((1.2, 2.0), 97.6, 96.0,
                                  boxstyle="round,pad=0.4,rounding_size=1.2",
                                  facecolor="white", edgecolor="#444444",
                                  linewidth=0.9, zorder=1))
    axk.text(3.0, 92.0, "Key", fontsize=12.5, fontweight="bold",
             va="top", ha="left", zorder=2)
    axk.text(3.0, 85.5, "Census small area, coloured by 15–24-year-olds within "
             "1 km per play venue within 1 km",
             fontsize=9.2, va="top", ha="left", zorder=2)

    y = 76.0
    for cap, colour, label in CLASSES:
        axk.add_patch(plt.Rectangle((3.2, y - 3.4), 5.4, 5.4,
                                     facecolor=colour, edgecolor="#333333",
                                     linewidth=0.6, zorder=2))
        axk.text(10.4, y - 0.7, label, fontsize=9.4, va="center", ha="left",
                 zorder=2)
        y -= 8.6

    y -= 1.0
    axk.text(3.0, y, "Shops and venues", fontsize=10.2, fontweight="bold",
             va="top", ha="left", zorder=2)
    y -= 8.5
    axk.scatter([6.0], [y], s=13, c="#e8c46a", edgecolors="#6b5a1e",
                linewidths=0.35, zorder=3)
    axk.text(10.4, y, "Card shop — sells cards", fontsize=9.4, va="center",
             ha="left", zorder=2)
    y -= 8.5
    axk.scatter([6.0], [y], s=22, c="#ff8fb1", edgecolors="#7a2f4a",
                linewidths=0.5, zorder=3)
    axk.text(10.4, y, "Official Pokemon Gym — runs events", fontsize=9.4,
             va="center", ha="left", zorder=2)
    y -= 8.5
    axk.scatter([6.0], [y], s=26, c="white", edgecolors="#1a1a1a",
                linewidths=0.55, zorder=3)
    axk.text(10.4, y, "Play venue — the places to go to play a deck",
             fontsize=9.4, va="center", ha="left", zorder=2)
    y -= 9.5

    # The headline, inside the Key so it is read with the classes.
    summ = json.load(open(HERE / "out/merged_summary.json", encoding="utf-8"))
    axk.text(3.0, y,
             f"{summ['shops_total']} card shops · "
             f"{summ['play_venues_total']} places to play · "
             f"{summ['share_young_with_no_venue']}% of Hong Kong's "
             f"15–24-year-olds live more than 1 km from any play venue",
             fontsize=9.4, va="top", ha="left", zorder=2,
             bbox=dict(facecolor="#f4f1ea", edgecolor="#cfc7b4",
                       linewidth=0.7, boxstyle="round,pad=0.5"))

    # ---- source line -------------------------------------------------------
    fig.text(0.045, 0.026,
             "Source: BAW VAULT card shop directory (shop names, addresses, games "
             "and services) · Hong Kong Government location search "
             "(map.gov.hk gih-ws2) for building-level coordinates · "
             "Census and Statistics Department 2021 Population Census, "
             "211 small areas. Distances are straight-line from the small area's "
             "centroid, not along the street network.",
             fontsize=7.6, ha="left", va="bottom", color="#555555")

    out = OUT_DIR / "tcg_shops_map.png"
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)
    print("wrote", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
