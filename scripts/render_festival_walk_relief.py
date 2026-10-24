#!/usr/bin/env python3
"""3D relief map of Kowloon Tong at a 45-degree view, with Festival Walk's
per-floor pedestrian exits draped on the terrain.

Ground: CSDI LiDAR DTM 2020 (0.5 m, EPSG:2326 / HK1980 Grid).
Exits:  CSDI 3D Pedestrian Network, BuildingID 1108222840 (Festival Walk),
        one colour per official floor.

The hill matters here: Festival Walk sits in the valley at ~28 m while
Kowloon Tsai rises to ~222 m immediately north — so a 2D plan view hides the
fact that most of the catchment walks uphill to reach the station.
"""
import json
import math
import os
import pathlib
import sys

import numpy as np
import rasterio
from rasterio.warp import transform as rio_transform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import LightSource
from matplotlib.patches import FancyArrowPatch

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path(str(HERE))
DEM = WORK / "lidar_dtm" / "kt_mosaic_2326.tif"
GEO = WORK / "hk-spatial" / "data"

# 45-degree viewing angle, as requested.
ELEV_ANGLE = 45.0
AZIMUTH = 225.0          # looking from the south-west, so Lion Rock is behind
VERTICAL_EXAG = 2.0      # relief exaggeration (m -> plotted units)

FLOORS = [
    ("festival_walk_MTR_Level", "港鐵層", "MTR Level", "#f5a524", 0.0),
    ("festival_walk_LG2", "低層地下二樓", "LG2", "#ff6b9d", 5.5),
    ("festival_walk_LG1", "低層地下一樓", "LG1", "#3fe0d0", 11.0),
    ("festival_walk_G", "地下", "G", "#7c8cff", 16.5),
    ("festival_walk_UG", "高層地下", "UG", "#8ce99a", 22.0),
]
VERT_COLOUR = "#ffd43b"

plt.rcParams["font.sans-serif"] = ["PingFang TC", "PingFang HK", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False


def load_dem():
    ds = rasterio.open(DEM)
    arr = ds.read(1).astype("float32")
    nod = ds.nodata if ds.nodata is not None else -9999.0
    arr[arr <= nod + 1] = np.nan
    T = ds.transform
    ds.close()
    # fill interior no-data holes (missing tiles) with the nearest valid cell,
    # so the surface has no black voids
    if np.isnan(arr).any():
        try:
            from scipy.ndimage import distance_transform_edt
        except ImportError:
            distance_transform_edt = None
        if distance_transform_edt is None:
            arr = np.nan_to_num(arr, nan=float(np.nanmin(arr)))
        else:
            mask = np.isnan(arr)
            idx = distance_transform_edt(mask, return_distances=False,
                                        return_indices=True)
            arr = arr[tuple(idx)]
            print(f"  filled {int(mask.sum())} no-data cells", flush=True)
    return arr, T


def hillshade_rgb(arr, T, saturation=0.35):
    """Hillshaded RGB, cached to an .npy so re-renders are quick.

    The DEM is 205 M cells; computing the shaded relief each run costs minutes.
    `saturation` desaturates the terrain so the coloured exit network on top
    of it stays legible (a full-saturation rainbow hillshade reads as data).
    """
    cache = DEM.with_suffix(f".hillshade_s{int(saturation*100)}.npz")
    if cache.exists():
        print("  loading cached hillshade ...", flush=True)
        d = np.load(cache)
        if d["shape"].tolist() == list(arr.shape):
            return d["rgb"], d["rel"]
        print("  cache shape mismatch, recomputing", flush=True)

    print("  computing hillshade (this takes a few minutes) ...", flush=True)
    shade = hillshade(arr, az=315, alt=45)
    vmin, vmax = 0, 320
    rel = np.clip((arr - vmin) / (vmax - vmin), 0, 1)
    colour = cm.terrain(rel)          # low = green, high = brown/white
    rgb = colour[..., :3] * (0.35 + 0.75 * shade[..., None])
    rgb = np.clip(rgb, 0, 1)
    # desaturate toward its own luminance
    lum = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114)[..., None]
    rgb = np.clip(lum + (rgb - lum) * saturation, 0, 1).astype("float32")
    np.savez(cache, rgb=rgb, rel=rel.astype("float32"),
             shape=np.array(list(arr.shape)))
    print(f"  hillshade cached -> {cache.name}", flush=True)
    return rgb, rel


def hillshade(arr, az=315.0, alt=45.0):
    gy, gx = np.gradient(arr, 0.5, 0.5)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az_r = np.radians(360.0 - az + 90.0)
    alt_r = np.radians(alt)
    shaded = (np.cos(alt_r) * np.cos(slope) +
              np.sin(alt_r) * np.sin(slope) * np.cos(az_r - aspect))
    return np.clip(shaded, 0, 1)


def rot_xy(x, y, az_deg):
    """Rotate a map (x east, y north) into the tilted viewing frame."""
    a = math.radians(az_deg)
    u = x * math.cos(a) + y * math.sin(a)
    v = -x * math.sin(a) + y * math.cos(a)
    return u, v


def load_floor_lines(slug):
    p = GEO / f"{slug}.geojson"
    if not p.exists():
        return []
    fc = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for f in fc["features"]:
        g = f.get("geometry") or {}
        if g.get("type") == "MultiLineString":
            out.extend(g["coordinates"])
        elif g.get("type") == "LineString":
            out.append(g["coordinates"])
    return out


def main():
    print("loading DEM ...", flush=True)
    arr, T = load_dem()
    h, w = arr.shape
    print(f"  DEM {w} x {h} cells @ {T.a} m", flush=True)

    # map extent in HK1980 grid -> WGS84
    xs_2326 = [T.c, T.c + w * T.a]
    ys_2326 = [T.f + h * T.e, T.f]
    lons, lats = rio_transform("EPSG:2326", "EPSG:4326", xs_2326, ys_2326)
    lon0, lon1 = min(lons), max(lons)
    lat0, lat1 = min(lats), max(lats)
    print(f"  extent lon {lon0:.4f}..{lon1:.4f}  lat {lat0:.4f}..{lat1:.4f}", flush=True)

    # --- hillshade + colour ---
    rgb, rel = hillshade_rgb(arr, T)

    # --- vertical exaggeration + 45-degree tilt ---
    # Rotate the DEM raster in map space, then squash vertically by sin(45) so
    # the plane is seen at 45 degrees. Done on the raster itself (a single
    # oblique transform) rather than per-quad, which keeps the render fast and
    # avoids a 4,400 x 5,100 pcolormesh.

    z = np.nan_to_num(arr, nan=0.0) * VERTICAL_EXAG
    a = math.radians(AZIMUTH)
    sin_e = math.sin(math.radians(ELEV_ANGLE))
    cos_e = math.cos(math.radians(ELEV_ANGLE))
    ZSCALE = 0.55            # vertical squash of the 3D relief (screen units per metre)

    # source pixel -> world (x east, y north) -> camera u,v -> screen
    # screen_x = u ; screen_y = -(v*sin_e - z*cos_e*ZSCALE)
    # Build the inverse: screen -> source
    #   u = sx ; v = -(sy + z*cos_e*ZSCALE)/sin_e
    #   ex =  u*cos(a) - v*sin(a) ; ny = u*sin(a) + v*cos(a)
    #   ex = (col - w/2)*T.a ; ny = -(row - h/2)*T.a
    # so:
    #   col = ex/T.a + w/2 ; row = -ny/T.a + h/2
    R = np.array([[math.cos(a), math.sin(a)],
                   [-math.sin(a), math.cos(a)]])
    Minv = np.linalg.inv(R)
    # screen(x,y) -> (u,v) -> world offset (ex,ny) -> source (col,row)
    # v depends on z, which depends on the source — one Newton pass is enough
    # for a 45-degree view, so solve with z = 0 then refine.
    def screen_to_source(sx, sy):
        u = sx
        v = -sy / sin_e
        ex = Minv[0, 0] * u + Minv[0, 1] * v
        ny = Minv[1, 0] * u + Minv[1, 1] * v
        col = ex / T.a + w / 2
        row = -ny / T.a + h / 2
        return col, row

    # rasterise the output screen grid
    OUT_W, OUT_H = 2400, 1900
    # provisional extent
    ex_all = (np.arange(w) - w / 2) * T.a
    ny_all = -(np.arange(h) - h / 2) * T.a
    corners = []
    for ex in (ex_all[0], ex_all[-1]):
        for ny in (ny_all[0], ny_all[-1]):
            u = ex * math.cos(a) + ny * math.sin(a)
            v = -ex * math.sin(a) + ny * math.cos(a)
            corners.append((u, -(v * sin_e)))
    sx_min = min(c[0] for c in corners); sx_max = max(c[0] for c in corners)
    sy_min = min(c[1] for c in corners); sy_max = max(c[1] for c in corners)
    # widen for the height contribution
    sy_min -= z.max() * cos_e * ZSCALE
    sy_max += z.max() * cos_e * ZSCALE

    gx = np.linspace(sx_min, sx_max, OUT_W)
    gy = np.linspace(sy_max, sy_min, OUT_H)   # screen y grows downward
    SX, SY = np.meshgrid(gx, gy)

    col0, row0 = screen_to_source(SX, SY)
    # refine once using the elevation at the first-guess source position
    z0 = arr[np.clip(row0.astype(int), 0, h - 1), np.clip(col0.astype(int), 0, w - 1)]
    z0 = np.nan_to_num(z0, nan=0.0) * VERTICAL_EXAG
    v1 = -(SY + z0 * cos_e * ZSCALE) / sin_e
    ex1 = Minv[0, 0] * SX + Minv[0, 1] * v1
    ny1 = Minv[1, 0] * SX + Minv[1, 1] * v1
    col1 = ex1 / T.a + w / 2
    row1 = -ny1 / T.a + h / 2

    out_rgb = np.zeros((OUT_H, OUT_W, 3), dtype="float32")
    out_valid = np.zeros((OUT_H, OUT_W), dtype=bool)
    rc = np.clip(row1.astype(int), 0, h - 1)
    cc = np.clip(col1.astype(int), 0, w - 1)
    inside = (col1 >= 0) & (col1 < w) & (row1 >= 0) & (row1 < h)
    src_valid = ~np.isnan(arr[rc, cc])
    keep = inside & src_valid
    out_rgb[keep] = rgb[rc[keep], cc[keep]]
    out_valid[keep] = True

    X, Y = SX, SY
    Z = None
    C = out_rgb
    valid = out_valid
    print(f"  plot grid {X.shape}", flush=True)

    fig = plt.figure(figsize=(16.5, 10.2), facecolor="#0b1018")
    ax = fig.add_axes([0.035, 0.075, 0.93, 0.775])
    ax.set_facecolor("#0b1018")

    # the terrain surface (single oblique-transformed raster)
    masked = np.ma.masked_array(C, mask=np.broadcast_to(~valid[..., None], C.shape))
    ax.imshow(masked, extent=(X.min(), X.max(), Y.min(), Y.max()),
              origin="upper", interpolation="bilinear", zorder=1, aspect="equal")

    # --- drape the exits ---
    def to_map(lon, lat):
        X2, Y2 = rio_transform("EPSG:4326", "EPSG:2326", [lon], [lat])
        return X2[0], Y2[0]

    def z_at(mx, my):
        c = int((mx - T.c) / T.a)
        r = int((my - T.f) / T.e)
        if 0 <= r < h and 0 <= c < w:
            val = arr[r, c]
            if not np.isnan(val):
                return val * VERTICAL_EXAG
        return 0.0

    def to_screen(mx, my, extra_m=0.0):
        """Map (HK1980) -> screen, using the same oblique transform as the raster."""
        ex = mx - (T.c + w * T.a / 2)
        ny = my - (T.f + h * T.e / 2)
        u = ex * math.cos(a) + ny * math.sin(a)
        v = -ex * math.sin(a) + ny * math.cos(a)
        zz = (z_at(mx, my) + extra_m) * VERTICAL_EXAG
        sxx = u
        syy = -(v * sin_e - zz * cos_e * ZSCALE)
        return sxx, syy

    # vertical circulation first (under the floors)
    for line in load_floor_lines("festival_walk_vertical"):
        pts = [to_screen(*to_map(p[0], p[1]), extra_m=0.0) for p in line]
        if len(pts) < 2:
            continue
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#0b1018",
                lw=4.2, alpha=0.75, zorder=5, solid_capstyle="round")
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=VERT_COLOUR,
                lw=2.0, ls=(0, (1, 1.6)), alpha=0.98, zorder=6, solid_capstyle="round")

    floor_pts = {}
    for slug, zh, en, col, hh in FLOORS:
        segs = []
        for line in load_floor_lines(slug):
            pts = [to_screen(*to_map(p[0], p[1]), extra_m=hh) for p in line]
            if len(pts) < 2:
                continue
            segs.append(pts)
            # dark casing first, then the bright core: the halo is what makes a
            # 2 px line readable on top of a textured hillshade
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#080b12",
                    lw=6.0, alpha=0.9, zorder=7, solid_capstyle="round")
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col,
                    lw=3.0, alpha=1.0, zorder=8, solid_capstyle="round")
        floor_pts[en] = segs

    # --- vertical risers linking the floors (the "exits at different levels") ---
    # lift each floor's network to a visible exploded height so the stack reads
    STACK = 26.0   # extra metres between floors in the 3D view
    for i, (slug, zh, en, col, hh) in enumerate(FLOORS):
        segs = floor_pts.get(en, [])
        if not segs:
            continue
        # riser from the ground up to this floor's stack height, at the floor's centroid
        allp = [p for s in segs for p in s]
        cx = sum(p[0] for p in allp) / len(allp)
        cy = sum(p[1] for p in allp) / len(allp)
        ztop = (i + 1) * STACK
        ax.plot([cx, cx], [cy, cy - ztop * cos_e * ZSCALE],
                color=col, lw=1.4, alpha=0.55, zorder=7)

    # floor labels, stacked above their network
    for i, (slug, zh, en, col, hh) in enumerate(FLOORS):
        segs = floor_pts.get(en, [])
        if not segs:
            continue
        allp = [p for s in segs for p in s]
        cx = sum(p[0] for p in allp) / len(allp)
        cy = sum(p[1] for p in allp) / len(allp)
        lift = (i + 1) * STACK * cos_e * ZSCALE + 30
        ax.text(cx + 150, cy - lift, f"{zh}\n{en}", color=col, fontsize=10,
                fontweight="bold", ha="left", va="center", zorder=12, linespacing=1.3,
                bbox=dict(boxstyle="round,pad=0.38", fc="#0b1018", ec=col, lw=1.4, alpha=0.95))

    # --- key terrain features, located by their own elevation ---
    PLACES = [
        ("獅子山\nLion Rock", 114.1930, 22.3560),
        ("九龍仔山\nKowloon Tsai", 114.1700, 22.3540),
        ("九龍塘站\nKowloon Tong MTR", 114.1702, 22.3430),
        ("又一城\nFestival Walk", 114.1747, 22.3371),
        ("紅磡\nHung Hom", 114.1810, 22.3090),
    ]
    for name, lon, lat in PLACES:
        mx, my = to_map(lon, lat)
        sxx, syy = to_screen(mx, my)
        zt = z_at(mx, my)
        if name.startswith("獅子山"):
            zt = max(zt, 460 * VERTICAL_EXAG)
        # leader line from the label box to the point
        lx, ly = sxx + 40, syy - 70
        ax.plot([sxx, lx], [syy, ly], color="#7f92b0", lw=1.0, alpha=0.8, zorder=11)
        ax.plot([sxx], [syy], marker="o", ms=6.5, mfc="#ffffff", mec="#0b1018",
                mew=1.6, zorder=13)
        ax.text(lx, ly, name, color="#e6eefc", fontsize=9.5, fontweight="bold",
                ha="left", va="center", zorder=13, linespacing=1.25,
                bbox=dict(boxstyle="round,pad=0.36", fc="#0b1018", ec="#3a4763",
                          lw=1.0, alpha=0.96))

    # --- north arrow + scale bar (the view is rotated, so orientation matters) ---
    # North in screen space: rotate the north vector by the same camera azimuth.
    nx, ny = rot_xy(0.0, 1.0, AZIMUTH)      # unit north in camera u,v
    # screen: u -> +x ; v -> -y*sin_e
    n_sx, n_sy = nx, -ny * sin_e
    nlen = math.hypot(n_sx, n_sy) or 1.0
    n_sx, n_sy = n_sx / nlen, n_sy / nlen
    arrow_len = 620
    ax0 = X.min() + (X.max() - X.min()) * 0.035
    ay0 = Y.min() + (Y.max() - Y.min()) * 0.06
    ax.annotate("", xy=(ax0 + n_sx * arrow_len, ay0 + n_sy * arrow_len),
                xytext=(ax0, ay0),
                arrowprops=dict(arrowstyle="-|>", color="#e6eefc", lw=2.0,
                                mutation_scale=22), zorder=14)
    ax.text(ax0 + n_sx * arrow_len * 0.5, ay0 + n_sy * arrow_len * 0.5 + 70, "N",
            color="#e6eefc", fontsize=13, fontweight="bold", ha="center",
            va="center", zorder=14)

    # scale bar: 1 km along the screen-x axis
    km = 1000.0
    bar = km * 1.0
    bx1 = X.max() - (X.max() - X.min()) * 0.035
    by1 = Y.min() + (Y.max() - Y.min()) * 0.035
    ax.plot([bx1 - bar, bx1], [by1, by1], color="#e6eefc", lw=3.0,
            solid_capstyle="butt", zorder=14)
    for bx in (bx1 - bar, bx1):
        ax.plot([bx, bx], [by1 - 55, by1 + 55], color="#e6eefc", lw=1.6, zorder=14)
    ax.text(bx1 - bar / 2, by1 + 95, "1 km", color="#e6eefc", fontsize=10,
            fontweight="bold", ha="center", va="center", zorder=14)

    # --- frame the view on the data ---
    pad = 0.04
    xr = (X.min(), X.max())
    yr = (Y.min(), Y.max())
    ax.set_xlim(xr[0] - (xr[1]-xr[0])*pad, xr[1] + (xr[1]-xr[0])*pad)
    ax.set_ylim(yr[0] - (yr[1]-yr[0])*pad, yr[1] + (yr[1]-yr[0])*pad)
    ax.set_aspect("equal")
    ax.axis("off")

    # --- legend ---
    handles = []
    from matplotlib.lines import Line2D
    for slug, zh, en, col, hh in FLOORS:
        handles.append(Line2D([], [], color=col, lw=2.6, label=f"{zh}  {en}"))
    handles.append(Line2D([], [], color=VERT_COLOUR, lw=1.4, ls=(0, (2, 2)),
                          label="垂直交通 升降機/扶手電梯/樓梯"))
    leg = fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.035, 0.905),
                      ncol=3, frameon=True, fontsize=9.5, labelcolor="#e6eefc",
                      columnspacing=1.5, handlelength=1.8)
    leg.get_frame().set_facecolor("#131b2b")
    leg.get_frame().set_edgecolor("#25314a")
    leg.get_frame().set_alpha(0.95)

    fig.suptitle("又一城 Festival Walk — 3D 地形起伏與各樓層出口",
                 color="#e6eefc", fontsize=16, fontweight="bold", x=0.035, ha="left", y=0.972)
    fig.text(0.035, 0.938,
             f"45° 視角 · 地形起伏放大 {VERTICAL_EXAG:g}× · LiDAR DTM 0.5 m · 地面等高線陰影",
             color="#7f92b0", fontsize=10, ha="left")
    fig.text(0.965, 0.938,
             "獅子山 495 m ← 谷底 28 m",
             color="#7f92b0", fontsize=10, ha="right")
    fig.text(0.035, 0.018,
             "地形：CSDI LiDAR 數碼地形模型 2020 (DTM 0.5 m, HK1980 Grid) · "
             "路網：CSDI 三維行人道路網 landsd_rcd_1637222018065_52265 · 出口分層高度為示意",
             color="#5d6f8c", fontsize=8.5)

    out = WORK / "festival_walk_3d_relief.png"
    fig.savefig(out, dpi=135, facecolor=fig.get_facecolor())
    print("saved:", out, out.stat().st_size, "bytes", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
