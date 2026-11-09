#!/usr/bin/env python3
"""
Merge the complete rainfall record with the gauge LOCATIONS.

The two files are complementary:

  rain_gauges_daily.geojson        213,570 rows, 2020-2026, 90 gauges,
                                   WITH geometry (Point, lon/lat)
  rain_gauges_daily_full.geojson  1,126,191 rows, 1984-2026, 95 gauges,
                                   NO geometry, attributes under the key
                                   "attributes" (not "properties")

The full record carries five gauges the 2020 file does not
(H11, H13, H21, H22, H27 - the older Hong Kong Island gauges), and the
2020 file carries the coordinates for every gauge.

This script writes ONE file with the complete 1984-2026 series AND the
coordinates, so the flash-flood rainfall factor is computed from the
whole record rather than from 6 years of it.

Run:  ls-venv/bin/python merge_rain_locations.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

GEOM_SRC = "rain_gauges_daily.geojson"
FULL_SRC = "rain_gauges_daily_full.geojson"
OUT = "rain_gauges_daily_merged.geojson"


def main():
    geo_path = os.path.join(RAW, GEOM_SRC)
    full_path = os.path.join(RAW, FULL_SRC)

    # ---- 1. gauge coordinates from the 2020 file
    locs = {}
    with open(geo_path) as f:
        g = json.load(f)
    for ft in g["features"]:
        p = ft["properties"]
        gid = p.get("Raingauge_No")
        c = (ft.get("geometry") or {}).get("coordinates")
        if gid is not None and c and gid not in locs:
            locs[gid] = (float(c[0]), float(c[1]), p.get("Location"))
    print(f"locations from {GEOM_SRC}: {len(locs)} gauges")

    # ---- 2. the complete record
    with open(full_path) as f:
        full = json.load(f)
    feats = []
    n_with_loc = 0
    gauges_seen = set()
    for ft in full["features"]:
        a = ft.get("attributes") or ft.get("properties")
        if a is None:
            continue
        gid = a.get("Raingauge_No")
        gauges_seen.add(gid)
        loc = locs.get(gid)
        if loc:
            n_with_loc += 1
            geom = {"type": "Point", "coordinates": [loc[0], loc[1]]}
            place = loc[2]
        else:
            geom = None
            place = a.get("Location")
        feats.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "Date_": a.get("Date_"),
                "Raingauge_No": gid,
                "Location": place,
                "Rainfall": a.get("Rainfall"),
            },
        })
    print(f"rows from {FULL_SRC}: {len(feats):,}  ({n_with_loc:,} with a location)")
    print(f"gauges: {len(gauges_seen)}")

    # ---- 3. sanity checks
    dates = [str(f["properties"]["Date_"]) for f in feats]
    print(f"date range: {min(dates)} .. {max(dates)}")
    no_loc = sorted(g for g in gauges_seen if g not in locs)
    if no_loc:
        print(f"gauges WITHOUT a location (excluded from the factor): {no_loc}")

    out = {"type": "FeatureCollection", "features": feats}
    p = os.path.join(RAW, OUT)
    with open(p, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {p}  ({os.path.getsize(p)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
