#!/usr/bin/env python3
"""Render Festival Walk (又一城) pedestrian network per floor as a layered map.

Two panels:
  1. Top view  — every floor's network overlaid, one colour per floor, so the
     ground plan of each exit route is readable.
  2. Exploded side view — the same floors separated vertically, showing how the
     vertical circulation (lifts / escalators / stairs) links them.

Data: CSDI 3D Pedestrian Network, BuildingID 1108222840 (Festival Walk).
"""
import json
import pathlib
import sys
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path(str(HERE))
DATA = WORK / "data"

FLOORS = [
    # (slug, Chinese, English, colour, height_m)
    ("festival_walk_MTR_Level", "港鐵層", "MTR Level", "#f5a524", 0.0),
    ("festival_walk_LG2", "低層地下二樓", "LG2", "#ff6b9d", 5.5),
    ("festival_walk_LG1", "低層地下一樓", "LG1", "#3fe0d0", 11.0),
    ("festival_walk_G", "地下", "G", "#7c8cff", 16.5),
    ("festival_walk_UG", "高層地下", "UG", "#8ce99a", 22.0),
]
VERT_COLOUR = "#ffd43b"
GROUND_M = 58.0

plt.rcParams["font.sans-serif"] = ["PingFang TC", "PingFang HK", "Heiti TC", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def load(slug):
    p = DATA / f"{slug}.geojson"
    if not p.exists():
        return []
    fc = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for f in fc["features"]:
        g = f.get("geometry") or {}
        if g.get("type") == "MultiLineString":
            for line in g["coordinates"]:
                out.append((line, f["properties"]))
        elif g.get("type") == "LineString":
            out.append((g["coordinates"], f["properties"]))
    return out


def main():
    layers = [(slug, zh, en, col, h, load(slug)) for slug, zh, en, col, h in FLOORS]
    vert = load("festival_walk_vertical")
    for slug, zh, en, col, h, lines in layers:
        print(f"{en:11s} {zh:8s} {len(lines):3d} segments")

    # --- shared extent ---
    allpts = [p for _, _, _, _, _, lines in layers for line, _ in lines for p in line]
    allpts += [p for line, _ in vert for p in line]
    if not allpts:
        print("no data"); return 1
    xs = [p[0] for p in allpts]; ys = [p[1] for p in allpts]
    pad = 0.0004
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad

    fig = plt.figure(figsize=(17, 9.2), facecolor="#0b1018")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.32, 1], wspace=0.14,
                          left=0.045, right=0.985, top=0.845, bottom=0.075)

    # ---------- Panel 1: top view, all floors overlaid ----------
    ax = fig.add_subplot(gs[0, 0], facecolor="#0b1018")
    for slug, zh, en, col, h, lines in layers:
        for line, _ in lines:
            ax.plot([p[0] for p in line], [p[1] for p in line], color=col, lw=1.7,
                    solid_capstyle="round", alpha=0.95, zorder=3)
    for line, _ in vert:
        ax.plot([p[0] for p in line], [p[1] for p in line], color=VERT_COLOUR, lw=0.9,
                ls=(0, (1, 2.4)), alpha=0.45, zorder=1)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_facecolor("#0b1018")
    ax.tick_params(colors="#5d6f8c", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#25314a")
    ax.set_xlabel("經度 longitude", color="#93a7c4", fontsize=9)
    ax.set_ylabel("緯度 latitude", color="#93a7c4", fontsize=9)
    ax.set_title("各樓層平面疊圖  Top view — all floors overlaid",
                 color="#e6eefc", fontsize=12, pad=10, loc="left")
    ax.grid(color="#1b2438", lw=0.6, alpha=0.55)
    ax.set_axisbelow(True)

    # label each floor's cluster near its own centroid, nudged apart
    label_off = {  # (en) -> (dx, dy, ha) offsets to stop the callouts colliding
        "UG":  (-0.0016, 0.0011, "right"),
        "G":   (-0.0016, -0.0009, "right"),
        "LG1": ( 0.0020, -0.0009, "left"),
        "LG2": ( 0.0020,  0.0011, "left"),
        "MTR Level": (-0.0016, -0.0016, "right"),
    }
    for slug, zh, en, col, h, lines in layers:
        if not lines:
            continue
        pts = [p for line, _ in lines for p in line]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        dx, dy, ha = label_off.get(en, (0, 0, "center"))
        ax.annotate(f"{zh}\n{en}", xy=(cx + dx, cy + dy), color=col, fontsize=9,
                    fontweight="bold", ha=ha, va="center", zorder=6, linespacing=1.25,
                    bbox=dict(boxstyle="round,pad=0.34", fc="#0b1018", ec=col, lw=1.3, alpha=0.96))

    # ---------- Panel 2: exploded side view ----------
    ax2 = fig.add_subplot(gs[0, 1], facecolor="#0b1018")
    # project each floor onto a slanted plan so the stack reads as 3D
    for slug, zh, en, col, h, lines in layers:
        for line, _ in lines:
            px = [(p[0] - x0) / (x1 - x0) for p in line]
            py = [(p[1] - y0) / (y1 - y0) for p in line]
            # isometric-ish squash: x to the right, y up-and-back
            sx = [0.62 * v for v in px]
            sy = [0.26 * v + h * 1.0 for v in py]
            ax2.plot(sx, sy, color=col, lw=1.15, alpha=0.92, zorder=3,
                     solid_capstyle="round")
    # vertical circulation drawn as risers between the floors they touch
    riser_x = []
    for line, props in vert:
        px = [(p[0] - x0) / (x1 - x0) for p in line]
        py = [(p[1] - y0) / (y1 - y0) for p in line]
        sx = sum(px) / len(px)
        sy = sum(py) / len(py)
        riser_x.append(0.62 * sx)
    # de-clutter: thin the risers so they read as a bundle, not a solid block
    riser_x = sorted(riser_x)
    kept, last = [], -1.0
    for x in riser_x:
        if x - last > 0.012:
            kept.append(x); last = x
    for x in kept:
        ax2.plot([x, x], [0.0, 22.0], color=VERT_COLOUR, lw=0.8,
                 ls=(0, (1.2, 2.4)), alpha=0.5, zorder=2)

    # floor plates + labels
    for slug, zh, en, col, h, lines in layers:
        ax2.plot([0, 0.62], [h, h], color=col, lw=0.9, alpha=0.55, zorder=1)
        ax2.text(-0.035, h, f"{zh}  {en}", color=col, fontsize=9.5, fontweight="bold",
                 ha="right", va="center", zorder=6)
        ax2.text(0.645, h, f"{h:+.1f} m", color="#5d6f8c", fontsize=8,
                 ha="left", va="center", zorder=6)
    # ground reference (label below the line so it cannot collide with the +0.0 m tag)
    ax2.plot([0, 0.62], [0, 0], color="#3a4763", lw=1.1, ls="--", zorder=1)
    ax2.text(0.03, -1.15, "地面 ground  (海平面 58.0 m)", color="#5d6f8c", fontsize=8,
             ha="left", va="center")

    ax2.set_xlim(-0.30, 0.78)
    ax2.set_ylim(-1.5, 24.5)
    ax2.set_facecolor("#0b1018")
    ax2.set_yticks([])
    ax2.tick_params(colors="#5d6f8c", labelsize=8)
    for s in ax2.spines.values():
        s.set_color("#25314a")
    ax2.set_title("立體分解圖  Exploded side view — floors stacked by height",
                  color="#e6eefc", fontsize=12, pad=10, loc="left")
    ax2.set_xlabel("由西至東 west → east（斜視 foreshortened）", color="#93a7c4", fontsize=9)

    # ---------- legend + footer ----------
    handles = [Line2D([], [], color=c, lw=2.4, label=f"{zh}  {en}") for _, zh, en, c, _ in FLOORS]
    handles.append(Line2D([], [], color=VERT_COLOUR, lw=1.4, ls=(0, (2, 2)),
                          label="垂直交通 升降機/扶手電梯/樓梯"))
    leg = fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.042, 0.905),
                      ncol=3, frameon=True, fontsize=9.5, labelcolor="#e6eefc",
                      columnspacing=1.5, handlelength=1.8)
    leg.get_frame().set_facecolor("#131b2b")
    leg.get_frame().set_edgecolor("#25314a")
    leg.get_frame().set_alpha(0.95)

    fig.suptitle("又一城 Festival Walk — 各樓層出口 3D 行人路網分層圖",
                 color="#e6eefc", fontsize=16, fontweight="bold", x=0.045, ha="left", y=0.972)
    fig.text(0.045, 0.938,
             "CSDI 三維行人道路網 · 建築 BuildingID 1108222840（又一城）· 每層一色，左圖疊圖、右圖按高度堆疊",
             color="#7f92b0", fontsize=10, ha="left")
    fig.text(0.985, 0.938,
             "共 207 條路網 · 5 個官方樓層 · 77 條垂直交通",
             color="#7f92b0", fontsize=10, ha="right")
    fig.text(0.045, 0.018,
             "資料：CSDI 三維行人道路網 landsd_rcd_1637222018065_52265 · 樓層名稱取自官方 PedRouteRelFloorPoly 查表 · "
             "層高 5.5 m 為示意，非官方高度",
             color="#5d6f8c", fontsize=8.5)

    out = pathlib.Path(str(HERE / "festival_walk_floors_map.png"))
    fig.savefig(out, dpi=135, facecolor=fig.get_facecolor())
    print("saved:", out, out.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
