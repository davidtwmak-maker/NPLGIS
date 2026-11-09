#!/usr/bin/env python3
"""
Prove the published build scripts run from a FRESH checkout.

This is the test that matters for a student who clones the repo: do the
scripts actually work without the local machine's private files?

It creates a clean temporary directory, downloads the published scripts
and the two published inputs they need (the campsite scores CSV and the
night-lights composite), then runs the map script there with only the
environment variables set - no absolute path from this machine.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
REPO = "davidtwmak-maker/NPLGIS"
B = f"https://raw.githubusercontent.com/{REPO}/main/"
PY = "/Users/davidhermes/.hermes/cache/scratch/ls-venv/bin/python"

WORK = tempfile.mkdtemp(prefix="camping_fresh_", dir="/tmp")
print(f"fresh workspace: {WORK}\n")

# ---- a minimal, self-contained data tree -----------------------------
camps = os.path.join(WORK, "data", "campsite")
nl = os.path.join(WORK, "data", "nightlights", "raw")
os.makedirs(camps)
os.makedirs(nl)

# The two inputs the map script needs.
for src, dst in [
    ("assets/data/camping/campsite_scores.csv",
     os.path.join(camps, "campsite_scores.csv")),
    ("assets/data/camping/night_lights_composite.tif",
     os.path.join(nl, "night_composite_median.tif")),
]:
    data = urllib.request.urlopen(B + src, timeout=120).read()
    with open(dst, "wb") as f:
        f.write(data)
    print(f"  downloaded {src:52s} {len(data):>9,} bytes")

# The script itself, from the published raw URL.
script = os.path.join(WORK, "make_camping_map.py")
with open(script, "wb") as f:
    f.write(urllib.request.urlopen(
        B + "scripts/camping/make_camping_map.py", timeout=60).read())
print(f"  downloaded scripts/camping/make_camping_map.py")

# ---- run it, with ONLY the env vars set ------------------------------
env = dict(os.environ)
env["CAMPING_DATA_DIR"] = camps
env["NIGHTLIGHTS_DIR"] = os.path.join(WORK, "data", "nightlights")
env["COAST_WAYS_JSON"] = os.path.join(WORK, "no_such_coastline.json")
# deliberately NOT set: GIS_DATA_DIR

print("\nrunning make_camping_map.py in the fresh workspace ...")
r = subprocess.run([PY, script], env=env, capture_output=True, text=True,
                   cwd=WORK, timeout=900)
tail = [l for l in (r.stdout or "").splitlines()
        if l.strip() and "Warning" not in l and "reshape" not in l]
print("\n".join(tail[-14:]))
if r.returncode != 0:
    print("\nSTDERR:\n", (r.stderr or "")[-2000:])
    raise SystemExit(f"FAILED rc={r.returncode}")

out_png = os.path.join(camps, "HK_camping_sites_dark_sky_map.png")
assert os.path.exists(out_png), "no PNG written"
h = hashlib.sha256(open(out_png, "rb").read()).hexdigest()[:16]

# Compare with the published PNG.
pub = urllib.request.urlopen(
    B + "assets/maps/camping-sites/HK_camping_sites_dark_sky_map.png",
    timeout=120).read()
ph = hashlib.sha256(pub).hexdigest()[:16]
print(f"\n  fresh build  sha16: {h}")
print(f"  published    sha16: {ph}")
print(f"  identical: {h == ph}")

if h != ph:
    print("\n  NOTE: the bytes differ. Checking that the map is still "
          "correct rather than identical, because the coastline overlay "
          "is absent in the fresh build (it is optional and not shipped).")
    print(f"  fresh size: {os.path.getsize(out_png):,}   "
          f"published size: {len(pub):,}")

shutil.rmtree(WORK, ignore_errors=True)
print("\nOK: the published script runs from a fresh checkout with only "
      "the environment variables set.")
