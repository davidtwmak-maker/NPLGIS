#!/usr/bin/env python3
"""
Sweep EVERY GeoJSON that the repo ships for RFC 7946 compliance.

The check walks coordinates RECURSIVELY, not by geometry type. A checker
that assumes "a ring is a list of [lon,lat]" and then iterates one level too
deep reports every coordinate in a LineString as a bare float and drowns the
real findings in thousands of false positives. Here a coordinate pair is
detected by its SHAPE (a list of at least two numbers) and the walk recurses
until it is reached.

A file passes only if:
  * it is a FeatureCollection
  * it carries NO crs member
  * every feature is type "Feature" with "properties" and a "geometry"
  * the geometry carries "type" and "coordinates"
  * every coordinate pair is inside the lon/lat ranges
  * the features do NOT use the ArcGIS "attributes"/"paths" shape

Run:  python3 sweep_rfc7946.py
"""
import gzip
import io
import json
import os
import sys


def _find_repo_root():
    """Walk up from this script until the repo root is found."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "assets", "data")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


REPO = os.environ.get("NPLGIS_REPO") or _find_repo_root()
if not REPO:
    raise SystemExit("cannot find the repo root")


def walk_coords(node, out):
    """Collect every [lon, lat] pair, recursively."""
    if isinstance(node, (list, tuple)):
        if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
            out.append((float(node[0]), float(node[1])))
            return
        for child in node:
            walk_coords(child, out)


def check(payload, label):
    """Return a list of problems for one GeoJSON payload."""
    problems = []
    if not isinstance(payload, dict):
        return [f"{label}: the payload is not a JSON object"]
    if payload.get("type") != "FeatureCollection":
        problems.append(f"{label}: type is {payload.get('type')!r}, "
                        "not FeatureCollection")
    if "crs" in payload:
        problems.append(f"{label}: carries a crs member")
    feats = payload.get("features")
    if not isinstance(feats, list):
        problems.append(f"{label}: no features list")
        return problems
    for i, ft in enumerate(feats):
        if not isinstance(ft, dict):
            problems.append(f"{label}: feature {i} is not an object")
            break
        if ft.get("type") != "Feature":
            problems.append(f"{label}: feature {i} has type "
                            f"{ft.get('type')!r}, not 'Feature'")
            break
        if "properties" not in ft:
            problems.append(f"{label}: feature {i} has no 'properties'")
            break
        if "attributes" in ft:
            problems.append(f"{label}: feature {i} uses the ArcGIS "
                            "'attributes' shape, not 'properties'")
            break
        geom = ft.get("geometry")
        if not isinstance(geom, dict):
            problems.append(f"{label}: feature {i} has no geometry object")
            break
        if "type" not in geom:
            problems.append(f"{label}: feature {i} geometry has no 'type'")
            break
        if "coordinates" not in geom:
            if "paths" in geom or "rings" in geom:
                problems.append(f"{label}: feature {i} uses the ArcGIS "
                                "'paths'/'rings' shape, not 'coordinates'")
            else:
                problems.append(f"{label}: feature {i} geometry has no "
                                "'coordinates'")
            break
        pairs = []
        walk_coords(geom["coordinates"], pairs)
        if not pairs:
            problems.append(f"{label}: feature {i} has no coordinate pair")
            break
        for lon, lat in pairs:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                problems.append(f"{label}: feature {i} has a coordinate "
                                f"{lon},{lat} outside the lon/lat range")
                break
    return problems


def main():
    found = 0
    bad = 0
    for root, dirs, files in os.walk(os.path.join(REPO, "assets", "data")):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for f in sorted(files):
            if not (f.endswith(".geojson") or f.endswith(".geojson.gz")):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, REPO)
            label = rel
            if f.endswith(".geojson.gz"):
                try:
                    with gzip.open(p, "rt", encoding="utf-8") as fh:
                        payload = json.load(fh)
                except Exception as exc:
                    print(f"FAIL  {rel}: cannot read ({exc})")
                    bad += 1
                    continue
            else:
                try:
                    with open(p, encoding="utf-8") as fh:
                        payload = json.load(fh)
                except Exception as exc:
                    print(f"FAIL  {rel}: cannot read ({exc})")
                    bad += 1
                    continue
            problems = check(payload, label)
            found += 1
            if problems:
                bad += 1
                for pr in problems:
                    print(f"FAIL  {pr}")
            else:
                n = len(payload.get("features", []))
                print(f"ok    {rel}: {n:,} features, no crs member, "
                      "lon/lat confirmed")
    print()
    print(f"swept {found} GeoJSON files, {bad} problems")
    if bad:
        sys.exit(1)
    print("all shipped GeoJSON is RFC 7946 clean")


if __name__ == "__main__":
    main()
