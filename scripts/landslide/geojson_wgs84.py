#!/usr/bin/env python3
"""
Helpers for writing RFC 7946 GeoJSON.

GeoJSON is defined by RFC 7946 to be CRS84 - longitude/latitude in decimal
degrees - and it has no `crs` member. The Hong Kong projects work in EPSG:2326
(HK1980 Grid, metres), where areas are metres squared, so the analysis stays
in EPSG:2326 and the CONVERSION TO LON/LAT HAPPENS AT THE SHIPPING
BOUNDARY.

Two mistakes this module exists to prevent:

1. Shipping EPSG:2326 metres inside a GeoJSON. A reader that honours a crs
   member will place the layer in the wrong part of the world; a reader that
   follows RFC 7946 and ignores it will treat an easting of 834,597 as a
   longitude and drop Hong Kong off the map.
2. Measuring an area by transforming coordinates that are ALREADY in
   EPSG:2326 a second time, which produces NaN and hides the real area.
   `area_km2_in_2326` takes an explicit flag saying which CRS the geometry is
   currently in.
"""
import json

import pyproj
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

TO_WGS84 = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(2326),
                                       pyproj.CRS.from_epsg(4326),
                                       always_xy=True)
TO_2326 = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4326),
                                       pyproj.CRS.from_epsg(2326),
                                       always_xy=True)


def transform_geometry(geom):
    """Recursively transform every coordinate pair from EPSG:2326 to 4326."""
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
    raise ValueError(f"unknown geometry type: {t}")


def to_wgs84_collection(fc):
    """Return a copy of a FeatureCollection in EPSG:4326, with no crs member.

    The input is assumed to be in EPSG:2326.
    """
    out = {"type": "FeatureCollection", "features": []}
    for ft in fc["features"]:
        out["features"].append({
            "type": "Feature",
            "geometry": transform_geometry(ft["geometry"]),
            "properties": ft.get("properties"),
        })
    return out


def area_km2_in_2326(geom, already_2326):
    """Polygon area in square kilometres, measured in EPSG:2326.

    `already_2326` says whether the geometry's coordinates are already in
    EPSG:2326 (the working layers) or already in EPSG:4326 (after shipping).
    The geometry is projected into EPSG:2326 only when it is not there
    already - projecting twice is the bug that produces NaN.
    """
    g = shape(geom)
    if g.is_empty:
        return 0.0
    if not already_2326:
        g = shp_transform(lambda x, y, z=None: TO_2326.transform(x, y), g)
    return g.area / 1e6


def collection_area_km2(fc, already_2326):
    """Total area of a FeatureCollection, in square kilometres."""
    return sum(area_km2_in_2326(ft["geometry"], already_2326)
               for ft in fc["features"])


def strip_crs(fc):
    """Remove the crs member - RFC 7946 does not allow it."""
    fc.pop("crs", None)
    return fc


def check_rfc7946(fc, label=""):
    """Assert a FeatureCollection is RFC 7946 clean. Returns a report string."""
    problems = []
    if "crs" in fc:
        problems.append("carries a crs member")
    for i, ft in enumerate(fc["features"]):
        geom = ft.get("geometry") or {}
        if "coordinates" not in geom:
            problems.append(f"feature {i}: geometry has no coordinates")
            break
        c = geom["coordinates"]
        while isinstance(c[0], (list, tuple)):
            c = c[0]
        lon, lat = c[0], c[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            problems.append(f"feature {i}: coordinate {lon},{lat} is not lon/lat")
            break
    if problems:
        raise AssertionError(f"{label}: " + "; ".join(problems))
    return (f"{label}: RFC 7946 clean, {len(fc['features']):,} features, "
            f"no crs member, coordinates are lon/lat")
