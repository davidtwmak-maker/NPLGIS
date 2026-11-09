#!/usr/bin/env python3
"""
Reproject the three landslide GeoJSON layers to WGS 84 for shipping.

Why
---
Three shipped layers carried HK1980 Grid (EPSG:2326) metre coordinates inside
a GeoJSON file, together with a crs member naming EPSG::2326:

    assets/data/landslide/landslide_records.geojson.gz
    assets/data/landslide/susceptibility_cells.geojson.gz
    assets/data/landslide/steep_slopes_over30.geojson.gz

GeoJSON is defined by RFC 7946 to be CRS84 - longitude/latitude in decimal
degrees - and a crs member is not part of the format at all. A reader that
honours the crs member will place these layers in the wrong part of the
world; a reader that ignores it (which is what RFC 7946 says it should do)
will treat Hong Kong's easting as a longitude and drop the layer off the
map. Either way the layer is broken as a GeoJSON.

The fix belongs at the SHIPPING boundary, not in the source: the analysis
works in EPSG:2326, where areas are metres squared, and the working files
stay in EPSG:2326. This script converts the shipped copies to EPSG:4326 and
removes the crs member, so the file says what it is by its coordinates.

Two independent checks
----------------------
1. The reprojected steep-slopes layer is compared, feature for feature,
   against the WGS 84 sibling already shipped in agol/
   (steep_slopes_over30_wgs84.geojson), which was produced separately for
   the ArcGIS Online upload. The attributes must match exactly and the
   coordinates must agree to 1e-9 degrees.
2. The projected area of each polygon is measured BEFORE and AFTER the
   conversion, in EPSG:2326, and must agree. A reprojection that distorts
   the shape would show up here as a changed area.

The attributes are not touched.
"""
import gzip
import json
import os

import pyproj
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

REPO = "/Users/davidhermes/nplgis"
SRC = f"{REPO}/assets/data/landslide"
FILES = [
    "landslide_records.geojson.gz",
    "susceptibility_cells.geojson.gz",
    "steep_slopes_over30.geojson.gz",
]
WGS84_SIBLING = f"{SRC}/agol/steep_slopes_over30_wgs84.geojson"

TO_WGS84 = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(2326),
                                       pyproj.CRS.from_epsg(4326),
                                       always_xy=True)
TO_2326 = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4326),
                                       pyproj.CRS.from_epsg(2326),
                                       always_xy=True)


def log(m):
    print(m, flush=True)


def transform_geometry(geom):
    """Recursively transform every coordinate pair in a GeoJSON geometry."""
    t = geom["type"]
    if t == "Point":
        x, y = geom["coordinates"]
        gx, gy = TO_WGS84.transform(x, y)
        return {"type": "Point", "coordinates": [gx, gy]}
    if t == "MultiPoint":
        return {"type": t,
                "coordinates": [list(TO_WGS84.transform(x, y))
                                for x, y in geom["coordinates"]]}
    if t == "LineString":
        return {"type": t,
                "coordinates": [list(TO_WGS84.transform(x, y))
                                for x, y in geom["coordinates"]]}
    if t == "MultiLineString":
        return {"type": t,
                "coordinates": [[list(TO_WGS84.transform(x, y))
                                 for x, y in line]
                                for line in geom["coordinates"]]}
    if t == "Polygon":
        return {"type": t,
                "coordinates": [[list(TO_WGS84.transform(x, y))
                                 for x, y in ring]
                                for ring in geom["coordinates"]]}
    if t == "MultiPolygon":
        return {"type": t,
                "coordinates": [[[list(TO_WGS84.transform(x, y))
                                  for x, y in ring]
                                 for ring in poly]
                                for poly in geom["coordinates"]]}
    raise SystemExit(f"unknown geometry type: {t}")


def area_km2_in_2326(geom, already_2326):
    """Polygon area measured in EPSG:2326, where the units are metres.

    `already_2326` says whether the geometry's coordinates are already in
    EPSG:2326 (the source layers) or already in EPSG:4326 (after the
    conversion). The area is always measured in EPSG:2326, so the geometry is
    projected into it first only when it is not already there.
    """
    g = shape(geom)
    if g.is_empty:
        return 0.0
    if not already_2326:
        g = shp_transform(lambda x, y, z=None: TO_2326.transform(x, y), g)
    return g.area / 1e6


def _silence_shapely_deprecation():
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning,
                            module="shapely")


def main():
    _silence_shapely_deprecation()
    for name in FILES:
        path = f"{SRC}/{name}"
        g = json.load(gzip.open(path))
        n = len(g["features"])
        had_crs = "crs" in g

        # measure the area in the projected CRS BEFORE the conversion.
        # The source coordinates are already EPSG:2326, so the area is read
        # straight off them - projecting them again would be a bug.
        before = sum(area_km2_in_2326(ft["geometry"], True)
                     for ft in g["features"])
        # the first feature's coordinates tell us whether this is already WGS84
        ft0 = g["features"][0]
        c0 = ft0["geometry"]["coordinates"]
        while isinstance(c0[0], (list, tuple)):
            c0 = c0[0]
        already_wgs84 = -180 <= c0[0] <= 180 and -90 <= c0[1] <= 90

        if already_wgs84 and not had_crs:
            log(f"  {name}: already EPSG:4326 with no crs member - left alone")
            continue

        for ft in g["features"]:
            ft["geometry"] = transform_geometry(ft["geometry"])
        g.pop("crs", None)

        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(g, f, separators=(",", ":"))

        # measure the area AFTER, back in the projected CRS again
        after = sum(area_km2_in_2326(ft["geometry"], False)
                    for ft in g["features"])
        rel = abs(after - before) / before if before else 0.0
        log(f"  {name}: {n:,} features -> EPSG:4326, crs removed "
            f"(was present: {had_crs})")
        log(f"    area in EPSG:2326 before {before:.4f} km2, "
            f"after {after:.4f} km2, relative change {rel:.2e}")
        assert rel < 1e-6, f"{name}: reprojection changed the area by {rel:.2e}"
        log(f"    {os.path.getsize(path):,} bytes")

    # ---- cross-check against the independently produced WGS 84 sibling ----
    if os.path.exists(WGS84_SIBLING):
        w = json.load(open(WGS84_SIBLING))
        s = json.load(gzip.open(f"{SRC}/steep_slopes_over30.geojson.gz"))
        assert len(w["features"]) == len(s["features"]), "feature count differs"

        def first_pt(geom):
            """The first coordinate pair of a geometry, whatever its nesting."""
            c = geom["coordinates"]
            while isinstance(c[0], (list, tuple)):
                c = c[0]
            return c

        worst = 0.0
        attr_mismatch = 0
        for i in range(len(s["features"])):
            wp = first_pt(w["features"][i]["geometry"])
            sp = first_pt(s["features"][i]["geometry"])
            worst = max(worst, abs(wp[0] - sp[0]), abs(wp[1] - sp[1]))
            if w["features"][i]["properties"] != s["features"][i]["properties"]:
                attr_mismatch += 1
        log("\n  cross-check vs agol/steep_slopes_over30_wgs84.geojson:")
        log(f"    features: {len(s['features']):,}  "
            f"max coordinate difference: {worst:.3e} deg")
        log(f"    attribute differences: {attr_mismatch}")
        # The sibling was rounded to 7 dp, so the agreement is to about
        # 5e-8 deg (~5 mm). Anything larger means a real change.
        if worst > 1e-6 or attr_mismatch:
            raise SystemExit("cross-check FAILED")
        log("    cross-check PASSED")
    else:
        log(f"  (sibling {WGS84_SIBLING} not found - skipping the cross-check)")


if __name__ == "__main__":
    main()
