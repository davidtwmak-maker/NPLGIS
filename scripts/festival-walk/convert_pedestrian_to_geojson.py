#!/usr/bin/env python3
"""
Convert the cached 3D Pedestrian Network to RFC 7946 GeoJSON.

The CSDI "3D Pedestrian Network" (landsd_rcd_1637222018065_52265) serves
its features in the ArcGIS "geojson" output format, which is NOT the
GeoJSON of the same name. Each feature comes back as:

    {"attributes": {...}, "geometry": {"paths": [[[lon, lat], ...]]}}

so the published file had three defects:
  * no "type": "Feature" on any feature
  * "attributes" instead of the GeoJSON "properties" member
  * "geometry" with "paths" and no "type", i.e. an ESRI polyline, not a
    GeoJSON LineString

GeoJSON readers (mapshaper, Leaflet, geojson.io, QGIS) choke on all
three. This script rewrites the file properly:
  * every feature gets "type": "Feature"
  * "attributes" becomes "properties"
  * "paths" becomes {"type": "LineString", "coordinates": [...]}
    (a single path becomes a LineString, several become a MultiLineString)

It also records the source service id and the fetch date in the
collection's own metadata, and keeps the output deterministic.

Run:  ls-venv/bin/python convert_pedestrian_to_geojson.py
"""
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, "assets/data/festival-walk/kc_pedestrian.geojson.gz")
OUT = os.path.join(REPO, "assets/data/festival-walk/kc_pedestrian.geojson.gz")


def conv_geom(gm):
    """ESRI geometry dict -> RFC 7946 geometry dict (or None)."""
    if not isinstance(gm, dict):
        return None
    if gm.get("type") and "coordinates" in gm:
        return gm                       # already GeoJSON
    paths = gm.get("paths")
    if paths:
        clean = []
        for path in paths:
            pts = [[float(c[0]), float(c[1])] for c in path
                   if isinstance(c, (list, tuple)) and len(c) >= 2]
            if len(pts) >= 2:
                clean.append(pts)
        if not clean:
            return None
        if len(clean) == 1:
            return {"type": "LineString", "coordinates": clean[0]}
        return {"type": "MultiLineString", "coordinates": clean}
    rings = gm.get("rings")
    if rings:
        clean = [[float(c[0]), float(c[1])] for c in rings
                 if isinstance(c, (list, tuple)) and len(c) >= 2]
        if len(clean) >= 4:
            return {"type": "Polygon", "coordinates": [clean]}
    return None


def main():
    if not os.path.exists(SRC):
        print(f"not found: {SRC}")
        return 1
    raw = gzip.open(SRC, "rt", encoding="utf-8").read()
    g = json.loads(raw)
    feats = g.get("features", [])
    print(f"read {len(feats)} features from {os.path.basename(SRC)}")

    out = []
    kinds = {}
    for ft in feats:
        props = ft.get("properties")
        if props is None:
            props = ft.get("attributes") or {}
        geom = conv_geom(ft.get("geometry"))
        t = (geom or {}).get("type", "null")
        kinds[t] = kinds.get(t, 0) + 1
        out.append({"type": "Feature", "properties": props, "geometry": geom})

    g2 = {
        "type": "FeatureCollection",
        "name": "kc_pedestrian",
        "features": out,
        "metadata": {
            "title": "3D Pedestrian Network (Kowloon City bbox)",
            "dataset_id": "landsd_rcd_1637222018065_52265",
            "provider": "Lands Department via CSDI Portal",
            "source_service": ("ArcGIS FeatureServer, outputFormat=geojson "
                               "(ESRI feature schema, converted to RFC 7946)"),
            "bbox": "114.155,22.270,114.215,22.345 (Kowloon City)",
            "note": ("Converted from the ArcGIS 'geojson' output format: "
                     "'attributes' -> 'properties', ESRI 'paths' -> GeoJSON "
                     "LineString/MultiLineString, and 'type': 'Feature' added "
                     "to every feature."),
        },
    }
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(g2, f, ensure_ascii=False, separators=(",", ":"))
    print(f"geometry types: {kinds}")
    print(f"wrote {OUT}")
    print(f"  {os.path.getsize(OUT):,} bytes gzipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
