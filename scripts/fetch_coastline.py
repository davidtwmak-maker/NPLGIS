#!/usr/bin/env python3
"""Fetch HK coastline (OSM natural=coastline) as raw ways, split into sub-bboxes.

Territory-scale: one query over the whole bbox stalls Overpass, so split into
tiles and cache each reply separately. Retry the alternate instance on failure.
"""
import json
import os
import subprocess
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coast")
os.makedirs(OUT, exist_ok=True)

# South, West, North, East (lat/lon) - HK spans 22.15-22.56 N, 113.83-114.44 E.
# Split fine: dense quadrants 502/timeout as one query, so each is small.
# (s1/s2/s3 are the southern strip east of 114.10; n1/n2/n3 the northern half.)
TILES = [
    ("sw", 22.15, 113.83, 22.32, 114.10),
    ("s1", 22.15, 114.10, 22.32, 114.22),
    ("s2", 22.15, 114.22, 22.32, 114.32),
    ("s3", 22.15, 114.32, 22.32, 114.44),
    ("nw", 22.32, 113.83, 22.56, 114.10),
    ("n1", 22.32, 114.10, 22.45, 114.26),
    ("n2", 22.32, 114.26, 22.45, 114.44),
    ("n3", 22.45, 113.83, 22.56, 114.44),
]
INSTANCES = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

for name, s, w, n, e in TILES:
    path = os.path.join(OUT, f"coast_{name}.json")
    if os.path.exists(path) and os.path.getsize(path) > 200:
        d = json.load(open(path))
        print(f"  skip  {name}  ({len(d.get('elements', []))} ways)")
        continue

    q = (
        f'[out:json][timeout:180];way["natural"="coastline"]'
        f"({s},{w},{n},{e});out geom;"
    )
    qfile = os.path.join(OUT, f"q_{name}.txt")
    with open(qfile, "w") as f:
        f.write(q)

    ok = False
    for attempt, inst in enumerate(INSTANCES):
        tmp = path + ".tmp"
        # curl may fail to create the file at all (connection error) - guard the read
        r = subprocess.run(
            ["curl", "-s", "-o", tmp, "-w", "%{http_code}", "-m", "180",
             "-A", "hermes-geo/1.0", "--data-urlencode", f"data@{qfile}", inst],
            capture_output=True, text=True,
        )
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            print(f"  {name}: no response from {inst.split('/')[2]} (HTTP {r.stdout})")
            continue
        try:
            d = json.load(open(tmp))
        except Exception:
            print(f"  {name}: bad JSON from {inst.split('/')[2]} (HTTP {r.stdout})")
            os.remove(tmp)
            continue
        if "elements" not in d:
            print(f"  {name}: no elements from {inst.split('/')[2]}: {str(d)[:120]}")
            os.remove(tmp)
            continue
        n_el = len(d["elements"])
        if n_el == 0:
            print(f"  {name}: 0 ways from {inst.split('/')[2]}")
            os.remove(tmp)
            continue
        os.rename(tmp, path)
        print(f"  {name}: {n_el} ways from {inst.split('/')[2]}")
        ok = True
        break

    if not ok:
        print(f"  {name}: FAILED")
        sys.exit(1)