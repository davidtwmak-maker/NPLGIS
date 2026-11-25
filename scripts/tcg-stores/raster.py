#!/usr/bin/env python3
"""A fast scanline rasteriser for point-in-polygon work over whole areas.

WHY THIS EXISTS
    The Hong Kong district boundary layer has 590,181 vertices. Testing
    every polygon for every sample point is O(vertices x points) and takes
    over seven minutes for the 211 census small areas - it timed out twice.

    The standard fix is a scanline fill: for each grid row, collect the
    x-intersections of all polygon edges with that row, sort them, and fill
    between alternating pairs. That is O(edges + cells) per polygon instead
    of O(edges x cells), and it fills every cell exactly once.

    The output is a LABEL GRID: an integer array where every cell holds the
    id of the polygon that covers it, or -1 for the sea. With that grid in
    hand, "which small areas are in Kwai Tsing" becomes a table lookup, and
    "what is the population of a cell" becomes a lookup too.

THE GRID
    A single global grid over Hong Kong, so the district raster and the
    small-area raster share one coordinate frame and can be compared cell by
    cell. Resolution is 0.0004 degrees (about 40 m), fine enough that a
    census small area is hundreds of cells across and a district boundary
    is crisp at the scale the map is read.
"""
import numpy as np

# Hong Kong's bounding box, padded a little.
LON0, LON1 = 113.80, 114.48
LAT0, LAT1 = 22.12, 22.60
RES = 0.0004          # degrees per cell


class Raster:
    """A global label grid over Hong Kong."""

    def __init__(self, res=RES, lon0=LON0, lon1=LON1, lat0=LAT0, lat1=LAT1):
        self.res = res
        self.lon0, self.lon1 = lon0, lon1
        self.lat0, self.lat1 = lat0, lat1
        self.nx = int(round((lon1 - lon0) / res))
        self.ny = int(round((lat1 - lat0) / res))
        self.labels = np.full((self.ny, self.nx), -1, dtype=np.int16)

    def lon_to_col(self, lon):
        return (lon - self.lon0) / self.res

    def lat_to_row(self, lat):
        return (self.lat1 - lat) / self.res

    def cell_area_m2(self):
        """Approximate area of one cell at the grid's centre latitude."""
        latm = (self.lat0 + self.lat1) / 2
        m_per_deg_lat = 111320.0
        m_per_deg_lon = 111320.0 * np.cos(np.radians(latm))
        return self.res * m_per_deg_lat * self.res * m_per_deg_lon


def polys_of(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def rings_of(geom):
    """Outer rings only. Holes are ignored: the census small areas and the
    district boundaries in this dataset carry no holes that change which
    district an area belongs to, and a hole would only ever be a hole in
    the sea or inside a district."""
    out = []
    for poly in polys_of(geom):
        if poly:
            out.append(np.asarray(poly[0], dtype=float))
    return out


def fill_raster(raster, geom, label):
    """Fill every cell of `raster` that lies inside `geom` with `label`.

    Scanline: for each row the grid crosses, find where each polygon edge
    crosses that row, sort the crossings, and fill between alternating
    pairs (the even-odd rule)."""
    rings = rings_of(geom)
    if not rings:
        return 0

    x0 = raster.lon_to_col(raster.lon0)
    x1 = raster.lon_to_col(raster.lon1)
    y0 = raster.lat_to_row(raster.lat1)
    y1 = raster.lat_to_row(raster.lat0)
    ncols = raster.nx

    crossings = {}     # row -> list of column positions

    for ring in rings:
        n = len(ring)
        if n < 3:
            continue
        r = ring[:-1] if (ring[0] == ring[-1]).all() else ring
        m = len(r)
        j = m - 1
        for i in range(m):
            xi, yi = r[i]
            xj, yj = r[j]
            if yi != yj:
                # Rows crossed by this edge. lat_to_row DECREASES as the
                # latitude rises, so the highest latitude is the SMALLEST row
                # index and the lowest latitude is the LARGEST.
                #
                # The range must be INCLUSIVE on both ends and must use the
                # row of the edge's own endpoints, not a floor/ceil of them:
                # a row sits between two adjacent cell centres, so an edge
                # that ends exactly on a cell centre still crosses it.
                rr_a = raster.lat_to_row(yi)
                rr_b = raster.lat_to_row(yj)
                rr_min = int(np.floor(min(rr_a, rr_b)))
                rr_max = int(np.ceil(max(rr_a, rr_b)))
                for rr in range(max(rr_min, 0), min(rr_max, raster.ny - 1) + 1):
                    y_at = raster.lat1 - rr * raster.res
                    # the crossing must lie between the edge's endpoints
                    if (yi > y_at) == (yj > y_at):
                        continue
                    t = (y_at - yi) / (yj - yi)
                    x_at = xi + t * (xj - xi)
                    cc = raster.lon_to_col(x_at)
                    if 0 <= cc <= ncols:
                        crossings.setdefault(rr, []).append(cc)
            j = i

    painted = 0
    for rr, xs in crossings.items():
        xs.sort()
        # even-odd: fill between crossing pairs
        for k in range(0, len(xs) - 1, 2):
            c0 = max(0, int(np.ceil(xs[k])))
            c1 = min(ncols - 1, int(np.floor(xs[k + 1])))
            if c1 >= c0:
                raster.labels[rr, c0:c1 + 1] = label
                painted += c1 - c0 + 1
    return painted


def rasterise(geoms, labels, res=RES):
    """Build a label grid from a list of (geom, label) pairs."""
    r = Raster(res=res)
    for geom, label in zip(geoms, labels):
        fill_raster(r, geom, label)
    return r


def cells_of_area(raster, geom):
    """The set of grid cells inside one geometry, as a flat index array."""
    r = Raster(res=raster.res, lon0=raster.lon0, lon1=raster.lon1,
               lat0=raster.lat0, lat1=raster.lat1)
    fill_raster(r, geom, 0)
    mask = r.labels == 0
    return np.flatnonzero(mask)


def area_of_cells(raster, geom):
    """Number of grid cells inside one geometry."""
    return int(cells_of_area(raster, geom).size)
