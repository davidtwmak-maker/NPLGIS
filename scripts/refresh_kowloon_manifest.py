#!/usr/bin/env python3
"""Refresh the covered-walkway entries in assets/data/MANIFEST.json.

Why this exists
---------------
`update_manifest.py` re-reads every entry's byte count and sha256 from disk,
but it keeps the DESCRIPTIVE metadata - title, notes, feature count - as
written.  That is right for a one-off append and wrong for a study that has
been re-run over a bigger area: the manifest kept saying "103 schools" and
"14,761 covered paths" while the files on disk held 164 and 34,533.  A
manifest that misdescribes the files it ships is worse than no manifest.

So the feature counts are re-derived from the files themselves, every time,
and the prose is rewritten to match.

    python3 scripts/refresh_kowloon_manifest.py

Then `update_manifest.py` is run to re-hash.
"""
import gzip
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "assets", "data", "MANIFEST.json")

SITE = "assets/data/kowloon-covered-walkways"
APP = "apps/kowloon-covered-walkways"


def gz_features(path):
    """Count features in a gzipped GeoJSON by decompressing it."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return len(json.load(f)["features"])


def gj_features(path):
    """Count features in a plain GeoJSON by parsing the JSON directly."""
    return len(json.load(open(path, encoding="utf-8"))["features"])


def json_records(path):
    """Count records in a plain JSON array."""
    return len(json.load(open(path, encoding="utf-8")))


def csv_rows(path):
    """Count data rows in a CSV (minus the header)."""
    with open(path, encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


# (manifest path, counter, title, notes)
ENTRIES = [
    (f"{SITE}/peninsula_routes_schools.json", json_records,
     "School exposure metrics for the six-district covered-walkway study",
     "164 registered whole-day secondary schools (government, aided, direct "
     "subsidy scheme) across Sham Shui Po, Kowloon City, Yau Tsim Mong, Wong "
     "Tai Sin, Kwun Tong and Kwai Chung. Every exposure metric carries an "
     "ai_ prefix; the nested per-stop detail is dropped from this published "
     "copy and kept in the vault and in the geodatabase's Route_Candidates "
     "class. The school universe excludes private, private-independent and "
     "caput schools, evening colleges and A.M./P.M. sections."),

    (f"{SITE}/peninsula_route_geometry.geojson.gz", gz_features,
     "The walking routes - shortest and best-covered per school",
     "328 routes (2 per school) stored as one line per network edge, 12,058 "
     "parts in total. Dissolve on school_id + ai_route_kind to get a whole "
     "route back. EPSG:4326; distances are measured in EPSG:2326 (HK 1980 "
     "Grid) in the source analysis."),

    (f"{SITE}/peninsula_covered_paths.geojson.gz", gz_features,
     "The sheltered pedestrian network with street names",
     "34,533 segments classified covered (WeatherProof = 1 or Location = 2) "
     "from the LandsD 3D Pedestrian Network, 407.3 km. EPSG:4326."),

    (f"{SITE}/peninsula_pti.geojson.gz", gz_features,
     "MTR exits, bus stops and green minibus stops with the shelter flag",
     "3,692 stops - 441 MTR exits, 1,390 bus stops, 1,861 minibus stops - each "
     "with whether a covered path lies within 30 m. The 30 m test is measured "
     "in EPSG:2326, not in degrees. EPSG:4326."),

    (f"{SITE}/mtr_walk_schools.json", json_records,
     "The worst-case walk from the nearest MTR exit, per school",
     "164 schools. Walk distance measured along the pedestrian network from "
     "the station exit that minimises NETWORK distance to the school - not "
     "the station centroid and not straight-line proximity. Walking time uses "
     "Tobler's hiking function per edge plus a 20% rain penalty. The exit's "
     "own coordinates are stored on each record, because exit names alone "
     "are ambiguous (176 (station, exit) pairs in the source layer)."),

    (f"{SITE}/mtr_walk_routes.geojson", gj_features,
     "The 164 worst-case MTR walks as lines",
     "Whole routes, already merged - one feature per school. EPSG:4326."),

    (f"{SITE}/Schools_RouteMetrics.csv", csv_rows,
     "The same school metrics as a flat table",
     "164 rows, one per school, for a spreadsheet or a pivot."),

    (f"{APP}/data/mtr_walks.geojson", gj_features,
     "The worst-case MTR walks, as the web map draws them",
     "164 lines. This is the same geometry as the published mtr_walk_routes "
     "file, trimmed to the fields the map needs. EPSG:4326."),
]


def main():
    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)

    by_file = {e["file"]: e for e in man["files"]}
    added = 0
    changed = 0

    for rel, counter, title, notes in ENTRIES:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            print(f"  MISSING on disk, skipped: {rel}")
            continue
        n = counter(path)
        if rel in by_file:
            e = by_file[rel]
            if e.get("features") != n:
                changed += 1
        else:
            e = {"file": rel, "bytes": os.path.getsize(path), "mb": 0.0,
                 "gzipped": rel.endswith(".gz"), "features": n, "title": title,
                 "notes": notes, "records": str(n)}
            man["files"].append(e)
            by_file[rel] = e
            added += 1
        e["features"] = n
        e["records"] = str(n)
        e["title"] = title
        e["notes"] = notes
        print(f"  {rel}  ->  {n}")

    man["generated"] = "2026-11-22"
    man["note"] = man["note"].split(" | ")[0] + (
        " | 2026-11-22: the covered-walkway study was extended from the "
        "Kowloon Peninsula to six districts - Sham Shui Po, Kowloon City, Yau "
        "Tsim Mong, Wong Tai Sin, Kwun Tong, Kwai Chung - and the school "
        "universe was restricted to registered whole-day government, aided and "
        "direct-subsidy-scheme secondary schools (164 sites, from 103). The "
        "worst-case MTR walk layer and the geodatabase's MTR feature classes "
        "are new. Feature counts above are re-derived from the files on every "
        "run, not carried over."
    )

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"kowloon manifest entries: {added} added, {changed} recount, "
          f"{len(man['files'])} total")


if __name__ == "__main__":
    main()
