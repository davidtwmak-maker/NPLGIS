#!/usr/bin/env python3
"""Fetch one coastline tile; retries across instances. Run detached, poll the log."""
import json
import os
import subprocess
import sys

D = str(HERE / "coast")
INST = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
name, s, w, n, e = sys.argv[1], *map(float, sys.argv[2:6])
p = D + f"coast_{name}.json"
if os.path.exists(p) and os.path.getsize(p) > 200:
    print(f"skip {name} ({len(json.load(open(p))['elements'])} ways)")
    sys.exit(0)

q = f'[out:json][timeout:120];way["natural"="coastline"]({s},{w},{n},{e});out geom;'
qf = D + f"q_{name}.txt"
open(qf, "w").write(q)

for attempt in range(4):
    for inst in INST:
        r = subprocess.run(
            ["curl", "-s", "-o", p + ".tmp", "-w", "%{http_code}", "-m", "100",
             "-A", "hermes-geo/1.0", "--data-urlencode", f"data@{qf}", inst],
            capture_output=True, text=True)
        if not os.path.exists(p + ".tmp") or os.path.getsize(p + ".tmp") == 0:
            print(f"{name}: no response {inst.split('/')[2]} (HTTP {r.stdout})", flush=True)
            continue
        try:
            d = json.load(open(p + ".tmp"))
        except Exception:
            print(f"{name}: bad JSON {inst.split('/')[2]}", flush=True)
            os.remove(p + ".tmp")
            continue
        if "elements" not in d or not d["elements"]:
            print(f"{name}: empty {inst.split('/')[2]}", flush=True)
            os.remove(p + ".tmp")
            continue
        os.rename(p + ".tmp", p)
        print(f"{name}: {len(d['elements'])} ways from {inst.split('/')[2]}", flush=True)
        sys.exit(0)
print(f"{name}: FAILED after {attempt + 1} attempts", flush=True)
sys.exit(1)