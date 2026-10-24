#!/usr/bin/env python3
"""Two-panel 3D relief figure of Kowloon Tong.

Left  : whole-hill 3D relief (Lion Rock -> Kowloon Tsai -> Kowloon Tong
        valley) at 45 degrees, with the district pedestrian network draped on
        the terrain and Festival Walk picked out.
Right : zoom on Festival Walk itself (1.2 km box) at 45 degrees, showing the
        per-floor pedestrian network lifted onto the hill slope.

Ground : CSDI LiDAR DTM 2020 (0.5 m, EPSG:2326 / HK1980 Grid).
Routes : CSDI 3D Pedestrian Network, BuildingID 1108222840 (Festival Walk).
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
from matplotlib.lines import Line2D
from matplotlib.path import Path
from matplotlib.patches import PathPatch

import relief_overlay

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
WORK = pathlib.Path(str(HERE))
DEM = WORK / "lidar_dtm" / "kt_mosaic_2326.tif"
GEODATA = pathlib.Path(str(HERE / "data"))
PEDNET = WORK / "ped_network_kowloontong.geojson"

ELEV_ANGLE = 45.0
AZIMUTH = 225.0
ZSCALE = 0.55          # screen units per metre of relief
VERTICAL_EXAG = 1.6

FLOORS = [
    ("festival_walk_MTR_Level", "港鐵層", "MTR Level", "#ffc233", 0.0),
    ("festival_walk_LG2", "低層地下二樓", "LG2", "#ff4d9d", 5.5),
    ("festival_walk_LG1", "低層地下一樓", "LG1", "#00e5ff", 11.0),
    ("festival_walk_G", "地下", "G", "#7b6bff", 16.5),
    ("festival_walk_UG", "高層地下", "UG", "#c8ff3d", 22.0),
]
VERT_COLOUR = "#ffd21f"
STACK = 80.0            # exploded-view separation per floor, in metres

plt.rcParams["font.sans-serif"] = ["PingFang TC", "PingFang HK", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------- DEM helpers
def load_dem():
    ds = rasterio.open(DEM)
    arr = ds.read(1).astype("float32")
    nod = ds.nodata if ds.nodata is not None else -9999.0
    arr[arr <= nod + 1] = np.nan
    T = ds.transform
    ds.close()
    if np.isnan(arr).any():
        try:
            from scipy.ndimage import distance_transform_edt
            mask = np.isnan(arr)
            idx = distance_transform_edt(mask, return_distances=False, return_indices=True)
            arr = arr[tuple(idx)]
        except ImportError:
            # no scipy: interpolate along rows/columns instead
            arr = _fill_nan_simple(arr)
    return arr, T


def _fill_nan_simple(arr):
    """Nearest-value fill for NaN cells without scipy."""
    out = arr.copy()
    mask = np.isnan(out)
    if not mask.any():
        return out
    # fill by nearest valid row, then nearest valid column
    idx = np.where(~np.isnan(out), np.arange(out.shape[1])[None, :], 0)
    np.maximum.accumulate(idx, axis=1, out=idx)
    # forward fill
    ff = out.copy()
    for c in range(1, ff.shape[1]):
        col = ff[:, c]
        prev = ff[:, c - 1]
        col[np.isnan(col)] = prev[np.isnan(col)]
    # backward fill
    for c in range(ff.shape[1] - 2, -1, -1):
        col = ff[:, c]
        nxt = ff[:, c + 1]
        col[np.isnan(col)] = nxt[np.isnan(col)]
    out = np.where(mask, ff, out)
    return out


def hillshade(arr):
    gy, gx = np.gradient(arr, 0.5, 0.5)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az_r = np.radians(360.0 - 315.0 + 90.0)
    alt_r = np.radians(45.0)
    s = (np.cos(alt_r) * np.cos(slope) +
         np.sin(alt_r) * np.sin(slope) * np.cos(az_r - aspect))
    return np.clip(s, 0, 1)


def terrain_rgb(arr, saturation=0.30, vmax=340):
    shade = hillshade(arr)
    rel = np.clip(arr / vmax, 0, 1)
    colour = cm.terrain(rel)
    rgb = colour[..., :3] * (0.34 + 0.78 * shade[..., None])
    rgb = np.clip(rgb, 0, 1)
    lum = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114)[..., None]
    return np.clip(lum + (rgb - lum) * saturation, 0, 1).astype("float32")


# ------------------------------------------------------------ projection math
class Cam:
    """Oblique 45-degree camera over a raster in HK1980 grid metres."""

    def __init__(self, arr, T, az=AZIMUTH, elev=ELEV_ANGLE, zscale=ZSCALE):
        self.arr, self.T = arr, T
        self.h, self.w = arr.shape
        self.a = math.radians(az)
        self.sin_e = math.sin(math.radians(elev))
        self.cos_e = math.cos(math.radians(elev))
        self.zscale = zscale
        self.vertical_exag = VERTICAL_EXAG
        self.R = np.array([[math.cos(self.a), math.sin(self.a)],
                           [-math.sin(self.a), math.cos(self.a)]])
        self.Rinv = np.linalg.inv(self.R)
        self.cx = T.c + self.w * T.a / 2
        self.cy = T.f + self.h * T.e / 2

    def elev_at(self, mx, my):
        c = int((mx - self.T.c) / self.T.a)
        r = int((my - self.T.f) / self.T.e)
        if 0 <= r < self.h and 0 <= c < self.w:
            v = self.arr[r, c]
            if not np.isnan(v):
                return v
        return 0.0

    def valid_at(self, mx, my):
        """True when (mx, my) lies inside the rendered DEM footprint.

        `elev_at` returns 0.0 for out-of-footprint points, so a line beyond
        the DEM tile would still be projected — onto the black background.
        This is the check that keeps overlays tied to the terrain.
        """
        c = int((mx - self.T.c) / self.T.a)
        r = int((my - self.T.f) / self.T.e)
        return 0 <= r < self.h and 0 <= c < self.w

    def project(self, mx, my, extra_m=0.0):
        ex = mx - self.cx
        ny = my - self.cy
        u = ex * math.cos(self.a) + ny * math.sin(self.a)
        v = -ex * math.sin(self.a) + ny * math.cos(self.a)
        zz = (self.elev_at(mx, my) + extra_m) * VERTICAL_EXAG
        return u, -(v * self.sin_e - zz * self.cos_e * self.zscale)

    def footprint_patch(self, **patch_kw):
        """The ground rectangle's screen quad, usable as an axes clip box.

        The four corners are projected WITH their own elevations, so the quad
        is the exact screen footprint of the DTM. Clipping to it stops roads
        from being drawn on the black background beyond the terrain.

        Note: the convex hull of the rendered pixels is NOT reliable for this —
        the oblique view compresses the far edge of the tile, so the raster
        silhouette is not the true ground footprint.
        """
        h, w = self.h, self.w
        corners = [
            (self.T.c, self.T.f + h * self.T.e),
            (self.T.c + w * self.T.a, self.T.f + h * self.T.e),
            (self.T.c + w * self.T.a, self.T.f),
            (self.T.c, self.T.f),
        ]
        pts = [self.project(x, y) for x, y in corners]
        # A closed polygon needs the first vertex repeated so that codes and
        # vertices have the same length (matplotlib requires 1:1).
        verts = np.array([[p[0], p[1]] for p in pts] + [[pts[0][0], pts[0][1]]])
        codes = [Path.MOVETO] + [Path.LINETO] * 3 + [Path.CLOSEPOLY]
        return PathPatch(Path(verts, codes), **patch_kw)

    def render(self, rgb, out_w=2200, out_h=1700):
        """Rasterise the oblique view of `rgb` (same shape as the DEM).

        Inverse mapping (screen -> source) so the output is gap-free: every
        output pixel takes the colour of the DEM cell it corresponds to. A
        forward scatter was tried and leaves holes because the DEM grid is
        coarser than the output raster.
        """
        h, w = self.h, self.w
        # screen extent from the projected corners of the footprint
        ex_lo = (0 - w / 2) * self.T.a
        ex_hi = (w - w / 2) * self.T.a
        ny_lo = (0 - h / 2) * -self.T.a
        ny_hi = (h - h / 2) * -self.T.a
        corners = []
        for ex in (ex_lo, ex_hi):
            for ny in (ny_lo, ny_hi):
                u = ex * math.cos(self.a) + ny * math.sin(self.a)
                v = -ex * math.sin(self.a) + ny * math.cos(self.a)
                corners.append((u, -(v * self.sin_e)))
        sx_min = min(c[0] for c in corners); sx_max = max(c[0] for c in corners)
        sy_min = min(c[1] for c in corners); sy_max = max(c[1] for c in corners)
        zmax = np.nanmax(self.arr) * VERTICAL_EXAG
        sy_min -= zmax * self.cos_e * self.zscale
        sy_max += zmax * self.cos_e * self.zscale

        gx = np.linspace(sx_min, sx_max, out_w)
        gy = np.linspace(sy_max, sy_min, out_h)
        SX, SY = np.meshgrid(gx, gy)

        v0 = -SY / self.sin_e
        ex0 = self.Rinv[0, 0] * SX + self.Rinv[0, 1] * v0
        ny0 = self.Rinv[1, 0] * SX + self.Rinv[1, 1] * v0
        col0 = ex0 / self.T.a + w / 2
        row0 = -ny0 / self.T.a + h / 2

        rc = np.clip(row0.astype(int), 0, h - 1)
        cc = np.clip(col0.astype(int), 0, w - 1)
        z0 = np.nan_to_num(self.arr[rc, cc], nan=0.0) * VERTICAL_EXAG
        v1 = -(SY + z0 * self.cos_e * self.zscale) / self.sin_e
        ex1 = self.Rinv[0, 0] * SX + self.Rinv[0, 1] * v1
        ny1 = self.Rinv[1, 0] * SX + self.Rinv[1, 1] * v1
        col1 = ex1 / self.T.a + w / 2
        row1 = -ny1 / self.T.a + h / 2

        out = np.zeros((out_h, out_w, 3), dtype="float32")
        inside = (col1 >= 0) & (col1 < w) & (row1 >= 0) & (row1 < h)
        rc1 = np.clip(row1.astype(int), 0, h - 1)
        cc1 = np.clip(col1.astype(int), 0, w - 1)
        out[inside] = rgb[rc1[inside], cc1[inside]]
        return out, inside, (sx_min, sx_max, sy_min, sy_max)


def crop_to(arr, T, mx, my, half_m):
    """Crop the DEM around an HK1980 point; returns (arr, T)."""
    c = int((mx - T.c) / T.a)
    r = int((my - T.f) / T.e)
    n = int(half_m / T.a)
    r0, r1 = max(0, r - n), min(arr.shape[0], r + n)
    c0, c1 = max(0, c - n), min(arr.shape[1], c + n)
    sub = arr[r0:r1, c0:c1]
    T2 = rasterio.Affine(T.a, 0, T.c + c0 * T.a, 0, T.e, T.f + r0 * T.e)
    return sub, T2


def convex_hull(points):
    """Andrew's monotone chain convex hull; returns an (N,2) vertex array."""
    pts = np.unique(points, axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) <= 0:
                    out.pop()
                else:
                    break
            out.append(tuple(p))
        return out

    lower = half(pts)
    upper = half(pts[::-1])
    return np.array(lower[:-1] + upper[:-1])


def draw_surface(ax, cam, rgb, **imshow_kw):
    """Draw the oblique terrain raster and clip the axes to the ground quad.

    The clip is the DTM rectangle's four corners projected WITH their own
    elevations — the true screen footprint. A convex hull of the rendered
    pixels is not usable: the oblique view compresses the far edge of the
    tile, so the raster silhouette sits well inside the real footprint and
    roads then get clipped away or, worse, drawn on the black background.
    """
    out, inside, ext = cam.render(rgb, out_w=imshow_kw.pop("out_w", 2200),
                                   out_h=imshow_kw.pop("out_h", 1700))
    mask3 = np.broadcast_to((~inside)[..., None], out.shape)
    masked = np.ma.masked_array(out, mask=mask3)
    ax.imshow(masked, extent=(ext[0], ext[1], ext[2], ext[3]), origin="upper",
              interpolation="bilinear", zorder=1, aspect="equal", **imshow_kw)
    clip = cam.footprint_patch(transform=ax.transData, facecolor="none",
                               edgecolor="none")
    ax.add_patch(clip)
    ax.set_clip_path(clip)
    return ext, clip


def downsample(arr, T, factor):
    """Block-average a DEM by `factor` cells; returns (arr, T) at the new pitch."""
    if factor <= 1:
        return arr, T
    h, w = arr.shape
    h2, w2 = (h // factor) * factor, (w // factor) * factor
    sub = arr[:h2, :w2].reshape(h2 // factor, factor, w2 // factor, factor)
    out = np.nanmean(sub, axis=(1, 3))
    T2 = rasterio.Affine(T.a * factor, 0, T.c,
                         0, T.e * factor, T.f)
    return out, T2


# ------------------------------------------------------------------ datasets
def load_floor_lines(slug):
    p = GEODATA / f"{slug}.geojson"
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


def load_pednet():
    """All district pedestrian lines as lists of (lon, lat) point lists."""
    if not PEDNET.exists():
        return []
    fc = json.loads(PEDNET.read_text())
    out = []
    for f in fc["features"]:
        g = f.get("geometry") or {}
        coords = g.get("coordinates") or []
        if g.get("type") == "MultiLineString":
            for line in coords:
                if len(line) >= 2:
                    out.append(line)
        elif g.get("type") == "LineString" and len(coords) >= 2:
            out.append(coords)
    return out


def project_lines(cam, lines, extra_m=0.0):
    """Batch-transform pedestrian lines and project them onto the camera.

    One rasterio call for every point at once: transforming 100k+ points one
    at a time dominates the runtime.
    """
    flat = []
    spans = []
    for line in lines:
        spans.append((len(flat), len(flat) + len(line)))
        flat.extend(line)
    if not flat:
        return []
    lons = [p[0] for p in flat]
    lats = [p[1] for p in flat]
    xs, ys = rio_transform("EPSG:4326", "EPSG:2326", lons, lats)
    inside = np.array([cam.valid_at(xs[i], ys[i]) for i in range(len(flat))])
    pts = [cam.project(xs[i], ys[i], extra_m) for i in range(len(flat))]

    # Split each line wherever it leaves the DEM footprint, so a line that
    # runs off the tile does not draw a stray segment across the background.
    out = []
    for (a, b) in spans:
        run = []
        for i in range(a, b):
            if inside[i]:
                run.append(pts[i])
            else:
                if len(run) >= 2:
                    out.append(run)
                run = []
        if len(run) >= 2:
            out.append(run)
    return out


def _lines_in_box(lines, cx, cy, half_m):
    """Keep only the lines with at least one point inside an HK1980 box."""
    out = []
    for line in lines:
        for (lon, lat) in line:
            x, y = wgs_to_2326(lon, lat)
            if abs(x - cx) <= half_m and abs(y - cy) <= half_m:
                out.append([(x, y) for (lon, lat) in line])
                break
    return out


def wgs_to_2326(lon, lat):
    x, y = rio_transform("EPSG:4326", "EPSG:2326", [lon], [lat])
    return x[0], y[0]


def _within(pts, ext, pad=0.0):
    """True if a projected polyline lies inside the rendered raster extent."""
    x0, x1, y0, y1 = ext
    return all(x0 - pad <= p[0] <= x1 + pad and y0 - pad <= p[1] <= y1 + pad
               for p in pts)


def _clip_to_box(cam, lines, half_m):
    """Keep only lines whose points fall inside the camera's ground footprint.

    The projected extent is wider than the DTM footprint (the oblique view
    rotates the rectangle, so its axis-aligned screen bbox is larger), so
    clipping on the screen extent alone still lets lines spill onto black.
    This clips on the ground coordinates instead.
    """
    cx, cy = cam.cx, cam.cy
    out = []
    for line in lines:
        keep = []
        for p in line:
            x, y = wgs_to_2326(p[0], p[1])
            if abs(x - cx) <= half_m and abs(y - cy) <= half_m:
                keep.append(p)
        if len(keep) >= 2:
            out.append(keep)
    return out


# -------------------------------------------------------------------- figure
def main():
    print("loading DEM ...", flush=True)
    arr, T = load_dem()
    print(f"  {arr.shape[1]} x {arr.shape[0]} cells @ {T.a} m", flush=True)

    # The left panel spans ~6 km across ~2200 px -> 2.7 m/px. A 5 m DEM is
    # plenty and keeps the hillshade to a few seconds instead of minutes.
    arr_lo, T_lo = downsample(arr, T, 10)
    print(f"  district DEM downsampled to {arr_lo.shape[1]} x {arr_lo.shape[0]} "
          f"@ {T_lo.a} m", flush=True)

    print("computing hillshade ...", flush=True)
    rgb_full = terrain_rgb(arr_lo)

    FW_LON, FW_LAT = 114.1747, 22.3371
    fw_x, fw_y = wgs_to_2326(FW_LON, FW_LAT)

    fig = plt.figure(figsize=(19.0, 9.6), facecolor="#0a0e16")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.06, 1.0], left=0.028,
                          right=0.976, bottom=0.135, top=0.845, wspace=0.055)

    # ================= LEFT: whole hill =================
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#0a0e16")
    cam1 = Cam(arr_lo, T_lo)
    ext1, sil1 = draw_surface(ax1, cam1, rgb_full)

    # district pedestrian network draped on the terrain
    ped = load_pednet()
    print(f"  {len(ped)} district pedestrian lines", flush=True)
    # Keep the terrain silhouette clip from draw_surface(): a flat ground quad
    # would let the network spill past the visible relief onto the background.
    if sil1 is not None:
        ax1.set_clip_path(sil1)
    for pts in project_lines(cam1, ped):
        ax1.plot([p[0] for p in pts], [p[1] for p in pts],
                 color="#ff6a3d", lw=0.9, alpha=0.42, zorder=4,
                 clip_on=True)

    # Festival Walk footprint marker on the district view
    fwx, fwy = cam1.project(fw_x, fw_y)
    ax1.plot([fwx], [fwy], marker="*", ms=22, mfc="#ffe066", mec="#0a0e16",
             mew=1.8, zorder=15)

    PLACES1 = [
        ("獅子山\nLion Rock", 114.1930, 22.3560, 1.25),
        ("九龍仔山\nKowloon Tsai", 114.1700, 22.3545, 1.10),
        ("九龍塘站\nKowloon Tong MTR", 114.1702, 22.3430, 1.00),
        ("又一城 Festival Walk", FW_LON, FW_LAT, 1.0),
        ("紅磡\nHung Hom", 114.1810, 22.3090, 1.0),
    ]
    for name, lon, lat, ds in PLACES1:
        x, y = wgs_to_2326(lon, lat)
        sx, sy = cam1.project(x, y)
        dx = 60 * ds
        dy = -80 * ds
        ax1.plot([sx, sx + dx], [sy, sy + dy], color="#93a6c4", lw=1.2,
                 alpha=0.95, zorder=11)
        ax1.plot([sx], [sy], marker="o", ms=7, mfc="#ffffff", mec="#0a0e16",
                 mew=1.8, zorder=13)
        ax1.text(sx + dx, sy + dy, name, color="#eef3fb", fontsize=10.5,
                 fontweight="bold", ha="left", va="center", zorder=14,
                 linespacing=1.25,
                 bbox=dict(boxstyle="round,pad=0.42", fc="#0a0e16", ec="#43536f",
                           lw=1.2, alpha=0.97))

    # north arrow
    nx = math.cos(math.radians(AZIMUTH))
    ny = -math.sin(math.radians(AZIMUTH))
    nl = math.hypot(nx, ny) or 1.0
    nx, ny = nx / nl, ny / nl
    ax0 = ext1[0] + (ext1[1] - ext1[0]) * 0.04
    ay0 = ext1[2] + (ext1[3] - ext1[2]) * 0.07
    ax1.annotate("", xy=(ax0 + nx * 560, ay0 + ny * 560), xytext=(ax0, ay0),
                 arrowprops=dict(arrowstyle="-|>", color="#eef3fb", lw=2.4,
                                 mutation_scale=26), zorder=15)
    ax1.text(ax0 + nx * 560 * 1.12, ay0 + ny * 560 * 1.12, "N", color="#eef3fb",
             fontsize=15, fontweight="bold", ha="center", va="center", zorder=15,
             bbox=dict(boxstyle="round,pad=0.28", fc="#0a0e16", ec="#43536f",
                       lw=1.0, alpha=0.95))

    # scale bar (1 km)
    bx1 = ext1[1] - (ext1[1] - ext1[0]) * 0.035
    by1 = ext1[2] + (ext1[3] - ext1[2]) * 0.035
    ax1.plot([bx1 - 1000, bx1], [by1, by1], color="#eef3fb", lw=3.4,
             solid_capstyle="butt", zorder=15)
    for bx in (bx1 - 1000, bx1):
        ax1.plot([bx, bx], [by1 - 50, by1 + 50], color="#eef3fb", lw=1.8, zorder=15)
    ax1.text(bx1 - 500, by1 + 95, "1 km", color="#eef3fb", fontsize=10.5,
             fontweight="bold", ha="center", va="center", zorder=15)

    ax1.set_xlim(ext1[0], ext1[1]); ax1.set_ylim(ext1[2], ext1[3])
    ax1.set_aspect("equal"); ax1.axis("off")
    ax1.set_title("① 全區地形 — 獅子山至九龍塘谷地",
                  color="#9fb2cf", fontsize=11.5, fontweight="bold", pad=6)

    # ================= RIGHT: Festival Walk zoom =================
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#0a0e16")
    sub, T2 = crop_to(arr_lo, T_lo, fw_x, fw_y, 430)
    # Tight vmax: the zoom tile spans only the valley floor up to the
    # hillside, so a district-wide vmax washes the relief out.
    rgb2 = terrain_rgb(sub, vmax=110)
    cam2 = Cam(sub, T2)
    cam2_out_w, cam2_out_h = 2000, 1550
    ext2, sil2 = draw_surface(ax2, cam2, rgb2, out_w=cam2_out_w,
                               out_h=cam2_out_h)

    # district network in the zoom — drawn in RASTER space and pushed through
    # the same inverse projection as the terrain, so it is clipped to the
    # terrain exactly (no lines on the black background).
    ped_local = _lines_in_box(ped, fw_x, fw_y, 430)
    print(f"  {len(ped_local)} pedestrian lines inside the zoom box", flush=True)
    def to_px(x, y):
        return ((x - T2.c) / T2.a, (y - T2.f) / T2.e)
    ov = relief_overlay.draw_overlay_in_raster_space(
        ped_local, sub.shape, T2, to_px, width=2,
        color=(255, 106, 61), alpha=120)
    ov_rgba, _ = relief_overlay.project_overlay(
        ov, cam2, cam2_out_w, cam2_out_h, ext2)
    ax2.imshow(ov_rgba, extent=(ext2[0], ext2[1], ext2[2], ext2[3]),
               origin="upper", interpolation="bilinear", zorder=4, aspect="equal")

    # vertical circulation, on the ground
    for pts in project_lines(cam2, load_floor_lines("festival_walk_vertical")):
        ax2.plot([p[0] for p in pts], [p[1] for p in pts], color="#0a0e16",
                 lw=5.0, alpha=0.9, zorder=5, solid_capstyle="round",
                 clip_on=True)
        ax2.plot([p[0] for p in pts], [p[1] for p in pts], color=VERT_COLOUR,
                 lw=2.6, ls=(0, (1, 1.4)), alpha=1.0, zorder=6,
                 solid_capstyle="round", clip_on=True)

    floor_pts = {}
    for i, (slug, zh, en, col, hh) in enumerate(FLOORS):
        segs = []
        # Exploded view: each floor is lifted clear of the one below it so the
        # five layers read separately. The risers below show the link.
        lift_m = hh + (i + 1) * STACK
        for pts in project_lines(cam2, load_floor_lines(slug), extra_m=lift_m):
            segs.append(pts)
            ax2.plot([p[0] for p in pts], [p[1] for p in pts], color="#04060b",
                     lw=8.0, alpha=0.95, zorder=7, solid_capstyle="round")
            ax2.plot([p[0] for p in pts], [p[1] for p in pts], color=col,
                     lw=3.8, alpha=1.0, zorder=8, solid_capstyle="round")
        floor_pts[en] = (segs, lift_m)

    # risers + floor labels: each floor is linked back to the ground by a
    # yellow dashed riser, and to the floor below by a coloured one.
    # Labels are staggered in x so the five callouts never collide.
    LABEL_DX = [210, 210, 210, 210, 210]
    LABEL_DY = [0, -26, 0, -26, 0]
    for i, (slug, zh, en, col, hh) in enumerate(FLOORS):
        segs, lift_m = floor_pts.get(en, ([], 0))
        if not segs:
            continue
        allp = [p for s in segs for p in s]
        cx = sum(p[0] for p in allp) / len(allp)
        cy = sum(p[1] for p in allp) / len(allp)
        # ground point directly under this floor's footprint
        gx, gy = wgs_to_2326(FW_LON, FW_LAT)
        gsx, gsy = cam2.project(gx, gy)
        # yellow dashed riser: ground -> this floor, with a dark halo so it
        # reads against both the terrain and the coloured floor lines
        ax2.plot([gsx, cx], [gsy, cy], color="#04060b", lw=4.0, alpha=0.8,
                 zorder=6, ls=(0, (5, 3)), solid_capstyle="round")
        ax2.plot([gsx, cx], [gsy, cy], color=VERT_COLOUR, lw=2.2, alpha=1.0,
                 zorder=7, ls=(0, (5, 3)), solid_capstyle="round")
        ax2.plot([gsx], [gsy], marker="o", ms=6, mfc=VERT_COLOUR,
                 mec="#04060b", mew=1.4, zorder=8)
        ax2.text(cx + LABEL_DX[i], cy + LABEL_DY[i], f"{zh}  {en}", color=col,
                 fontsize=11, fontweight="bold", ha="left", va="center", zorder=13,
                 bbox=dict(boxstyle="round,pad=0.42", fc="#0a0e16", ec=col,
                           lw=1.8, alpha=0.98))

    # annotate the slope: uphill / downhill
    def slope_note(lon, lat, text, colour, dy):
        x, y = wgs_to_2326(lon, lat)
        sx, sy = cam2.project(x, y)
        ax2.text(sx, sy + dy, text, color=colour, fontsize=9.5,
                 fontweight="bold", ha="center", va="center", zorder=13,
                 bbox=dict(boxstyle="round,pad=0.34", fc="#0a0e16",
                           ec=colour, lw=1.1, alpha=0.95))

    slope_note(114.1700, 22.3520, "↑ 九龍仔山\n山坡 458 m", "#ff8f6b", 150)
    slope_note(114.1790, 22.3170, "↓ 紅磡\n低地 8 m", "#7fd4ff", 150)

    ax2.set_xlim(ext2[0], ext2[1]); ax2.set_ylim(ext2[2], ext2[3])
    ax2.set_aspect("equal"); ax2.axis("off")
    ax2.set_title("② 又一城放大 — 各樓層出口沿山坡分布（爆炸分解視圖）",
                  color="#9fb2cf", fontsize=11.5, fontweight="bold", pad=6)

    # ① title for the left panel, so the two numbered panels match
    ax1.set_title("① 九龍仔山與獅子山 — 地勢與行人路網全貌",
                  color="#9fb2cf", fontsize=11.5, fontweight="bold", pad=6)

    # 200 m scale bar on the zoom panel
    bx2 = ext2[1] - (ext2[1] - ext2[0]) * 0.045
    by2 = ext2[2] + (ext2[3] - ext2[2]) * 0.04
    ax2.plot([bx2 - 200, bx2], [by2, by2], color="#eef3fb", lw=3.0,
             solid_capstyle="butt", zorder=15)
    for bx in (bx2 - 200, bx2):
        ax2.plot([bx, bx], [by2 - 34, by2 + 34], color="#eef3fb", lw=1.6, zorder=15)
    ax2.text(bx2 - 100, by2 + 72, "200 m", color="#eef3fb", fontsize=10,
             fontweight="bold", ha="center", va="center", zorder=15)

    # ================= legend + titles =================
    handles = [Line2D([], [], color=c, lw=2.8, label=f"{zh}  {en}")
               for _, zh, en, c, _ in FLOORS]
    handles += [
        Line2D([], [], color=VERT_COLOUR, lw=2.0, ls=(0, (2, 1.5)),
               label="垂直交通 升降機/扶手電梯/樓梯"),
        Line2D([], [], color="#ff6a3d", lw=1.8, label="區內行人路網"),
    ]
    # Legend sits at the bottom so it cannot cover the ① / ② panel titles.
    leg = fig.legend(handles=handles, loc="lower left",
                     bbox_to_anchor=(0.028, 0.032), ncol=4, frameon=True,
                     fontsize=10, labelcolor="#e6eefc", columnspacing=1.6,
                     handlelength=2.0)
    leg.get_frame().set_facecolor("#121a2a")
    leg.get_frame().set_edgecolor("#26324a")
    leg.get_frame().set_alpha(0.96)

    fig.suptitle("又一城 Festival Walk — 3D 地形起伏與各樓層出口",
                 color="#eef3fb", fontsize=18, fontweight="bold",
                 x=0.028, ha="left", y=0.972)
    fig.text(0.028, 0.933,
             "45° 視角 · 地形起伏放大 1.6× · CSDI LiDAR DTM 2020 (0.5 m) · "
             "左圖見獅子山 495 m 與谷底 28 m 的落差，右圖見出口沿九龍仔山坡分布",
             color="#7f92b0", fontsize=10.5, ha="left")
    fig.text(0.976, 0.933, "又一城谷底 28 m · 九龍仔山 458 m · 獅子山 495 m",
             color="#7f92b0", fontsize=10.5, ha="right")
    fig.text(0.028, 0.004,
             "地形：CSDI 數碼地形模型 LiDAR DTM 2020 (DTM 0.5 m, HK1980 Grid) · "
             "路網：CSDI 三維行人道路網 landsd_rcd_1637222018065_52265 · "
             "樓層高度為示意，非官方高度",
             color="#5d6f8c", fontsize=9)

    out = WORK / "festival_walk_3d_relief.png"
    fig.savefig(out, dpi=132, facecolor=fig.get_facecolor())
    print("saved:", out, out.stat().st_size, "bytes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
