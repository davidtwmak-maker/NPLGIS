#!/usr/bin/env python3
"""Check every shop point against the authoritative District Council layer.

A bounding box is not a land test. Hong Kong's territory is not a
rectangle, and a point at 22.43 N, 114.09 E sits in the Pearl River
estuary inside the HK bounding box while being outside Hong Kong
altogether. The only test that settles it is the government boundary.

The script reports:
  - shops whose point falls in no District Council district at all
    (i.e. outside Hong Kong, or on a tile boundary)
  - shops whose point falls in a district DIFFERENT from the district
    the source directory claims, which is a cross-check on the geocode
    and on the directory's own address
"""
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DC = Path("/Users/davidhermes/nplgis/assets/data/self-study-rooms/"
          "district_boundaries.geojson.gz")


def rings_of(geom):
    """Every polygon ring of a geometry as a list of (x, y)."""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"][0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []


def point_in_ring(x, y, ring):
    """Ray casting. ring is a list of [x, y]."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xint:
                inside = not inside
    return inside


def district_of(x, y, districts):
    for name, rings in districts:
        for r in rings:
            if point_in_ring(x, y, r):
                return name
    return None


def main():
    with gzip.open(DC, "rt", encoding="utf-8") as f:
        dc = json.load(f)
    districts = []
    for feat in dc["features"]:
        p = feat["properties"]
        districts.append((p.get("dc_eng"), rings_of(feat["geometry"])))
    print(f"{len(districts)} district polygons loaded")

    shops = json.load(open(HERE / "shops_merged.json", encoding="utf-8"))
    outside = []
    mismatch = []
    for s in shops:
        if s.get("lat") is None:
            continue
        d = district_of(s["lon"], s["lat"], districts)
        claimed = s.get("district")
        if d is None:
            outside.append((s, claimed))
        elif claimed and d != claimed:
            mismatch.append((s, claimed, d))

    print(f"\nshops: {len(shops)}")
    print(f"points OUTSIDE every district (i.e. not in Hong Kong): {len(outside)}")
    for s, claimed in outside:
        print(f"  {str(s.get('name'))[:34]:36} ({s.get('lat'):.4f},{s.get('lon'):.4f})"
              f"  claimed district: {claimed}")
        print(f"      addr: {str(s.get('address'))[:60]}")
        print(f"      src: {'+'.join(s.get('ai_sources') or [])}")

    print(f"\npoints in a DIFFERENT district from the source claim: {len(mismatch)}")
    for s, claimed, d in mismatch:
        print(f"  {str(s.get('name'))[:32]:34} claimed {claimed:20} actually {d}")
        print(f"      addr: {str(s.get('address'))[:60]}")


if __name__ == "__main__":
    sys.exit(main())
