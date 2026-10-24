#!/usr/bin/env python3
"""Raster-space overlay helper.

Drawing vector lines on top of an oblique (projected) terrain raster means
clipping them to the terrain silhouette, which is fiddly: the screen quad of
the DTM rectangle is not the same as the visible terrain, because ridges
protrude beyond it and the oblique view compresses the far edge.

The reliable way is to draw the overlay in the DEM's OWN raster space (a
top-down image of the tile) and then push that image through the same
inverse projection used for the terrain. Everything that is outside the
terrain then disappears automatically, because the projection only samples
where the tile actually is.
"""
import numpy as np
from PIL import Image, ImageDraw


def draw_overlay_in_raster_space(lines, arr_shape, T, pixel_fn,
                                 width=2, color=(255, 106, 61), alpha=140):
    """Render vector lines into a transparent PIL image in DEM raster space.

    `lines`   : list of lists of (x, y) in HK1980 grid metres
    `arr_shape`: (rows, cols) of the DEM the overlay will be projected onto
    `T`       : rasterio Affine of that DEM
    `pixel_fn`: (x, y) -> (col, row) float pixel coords in raster space

    Returns an RGBA PIL image of arr_shape.
    """
    h, w = arr_shape
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    for line in lines:
        if len(line) < 2:
            continue
        pts = []
        for (x, y) in line:
            col, row = pixel_fn(x, y)
            if 0 <= col < w and 0 <= row < h:
                pts.append((float(col), float(row)))
        if len(pts) >= 2:
            dr.line(pts, fill=color + (alpha,), width=width, joint="curve")
    return img


def project_overlay(overlay_img, cam, out_w, out_h, ext):
    """Push a raster-space overlay through the camera's inverse projection.

    Returns (out_rgba, inside_mask) at (out_h, out_w).
    """
    h, w = cam.h, cam.w
    ov = np.asarray(overlay_img).astype("float32") / 255.0

    sx_min, sx_max, sy_min, sy_max = ext
    gx = np.linspace(sx_min, sx_max, out_w)
    gy = np.linspace(sy_max, sy_min, out_h)
    SX, SY = np.meshgrid(gx, gy)

    v0 = -SY / cam.sin_e
    ex0 = cam.Rinv[0, 0] * SX + cam.Rinv[0, 1] * v0
    ny0 = cam.Rinv[1, 0] * SX + cam.Rinv[1, 1] * v0
    col0 = ex0 / cam.T.a + w / 2
    row0 = -ny0 / cam.T.a + h / 2

    rc = np.clip(row0.astype(int), 0, h - 1)
    cc = np.clip(col0.astype(int), 0, w - 1)
    z0 = np.nan_to_num(cam.arr[rc, cc], nan=0.0) * cam.vertical_exag
    v1 = -(SY + z0 * cam.cos_e * cam.zscale) / cam.sin_e
    ex1 = cam.Rinv[0, 0] * SX + cam.Rinv[0, 1] * v1
    ny1 = cam.Rinv[1, 0] * SX + cam.Rinv[1, 1] * v1
    col1 = ex1 / cam.T.a + w / 2
    row1 = -ny1 / cam.T.a + h / 2

    inside = (col1 >= 0) & (col1 < w) & (row1 >= 0) & (row1 < h)
    rc1 = np.clip(row1.astype(int), 0, h - 1)
    cc1 = np.clip(col1.astype(int), 0, w - 1)

    out = np.zeros((out_h, out_w, 4), dtype="float32")
    out[inside] = ov[rc1[inside], cc1[inside]]
    out[..., 3] *= inside
    return out, inside
