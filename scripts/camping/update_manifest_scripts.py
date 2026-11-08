#!/usr/bin/env python3
"""
Record the build scripts in assets/data/MANIFEST.json.

The `files` list holds DATA assets only, so the scripts that produced them
were untracked.  They are the more valuable part for a student who wants
to rebuild the study, so they get their own `scripts` section with the
same size and sha16 checks as the data.

Every entry is measured from the file on disk, never carried over.
"""
import hashlib
import json
import os

REPO = "/Users/davidhermes/nplgis"
MANIFEST = f"{REPO}/assets/data/MANIFEST.json"

SCRIPTS = [
    ("scripts/camping/fetch_nights.py",
     "Fetch and validate the VIIRS night-lights nights. Rejects blank "
     "(all-zero) rasters by CONTENT, not by HTTP status, because GIBS "
     "returns 200 with an empty raster for unserved dates."),
    ("scripts/camping/score_campsites.py",
     "Score the 41 campsites on darkness, access, facilities and horizon. "
     "Asserts every factor is populated, no score is NaN, and that the "
     "access term yields more than 20 distinct values."),
    ("scripts/camping/make_camping_map.py",
     "Build the two-panel figure. Checks text overlap and off-canvas text "
     "BEFORE saving, then verifies the rendered pixels over the bright "
     "city, the dark country and the dark sea each match the source "
     "raster value at that location."),
    ("scripts/camping/export_to_repo.py",
     "Copy the outputs into the repo layout and verify each shipped file."),
    ("scripts/camping/update_manifest_camping.py",
     "Extend this manifest with the camping entries and verify every "
     "entry against the file on disk."),
    ("scripts/camping/fetch_coastline_osm.py",
     "Fetch the OSM coastline via /map, with adaptive bbox splitting on "
     "HTTP 400 and backoff on HTTP 429. The coastline is an orientation "
     "overlay only - it is NOT used as a land mask."),
    ("scripts/camping/merge_coast_fragments.py",
     "Merge the bbox-clipped coastline fragments into complete ways. "
     "Merging by way id instead of node sequence keeps only the last "
     "fragment of any way crossing a box boundary, which guts the "
     "coastline."),
    ("scripts/camping/land_mask_flood.py",
     "Flood-fill the land from the sea over a rasterised coastline. "
     "Kept for the record: it fails where the coastline is not closed, "
     "which is why the shipped map applies no land mask at all."),
    ("scripts/camping/update_manifest_scripts.py",
     "Record the build scripts in this manifest and verify each one "
     "against the file on disk."),
    ("scripts/camping/verify_fresh_checkout.py",
     "Download the published script and its two inputs into a fresh "
     "temporary directory and run the build there with only the "
     "environment variables set. Proves the repo copy works off the "
     "author's machine, which is the thing a student actually needs."),
]


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    with open(MANIFEST) as f:
        m = json.load(f)
    m.setdefault("scripts", [])
    have = {s["file"] for s in m["scripts"]}

    for rel, desc in SCRIPTS:
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            print(f"  MISSING {rel} - skipped")
            continue
        e = {"file": rel, "bytes": os.path.getsize(p),
             "sha256": sha16(p), "description": desc}
        if rel in have:
            m["scripts"] = [e if s["file"] == rel else s for s in m["scripts"]]
            print(f"  updated {rel}")
        else:
            m["scripts"].append(e)
            print(f"  added    {rel}")

    m["generated"] = "2026-11-09"
    with open(MANIFEST, "w") as f:
        json.dump(m, f, indent=1)

    bad = []
    for s in m["scripts"]:
        p = os.path.join(REPO, s["file"])
        if not os.path.exists(p):
            bad.append((s["file"], "MISSING"))
            continue
        if os.path.getsize(p) != s["bytes"]:
            bad.append((s["file"], "size"))
            continue
        if not sha16(p).startswith(s["sha256"]):
            bad.append((s["file"], "sha"))
    print(f"scripts recorded: {len(m['scripts'])}, {len(bad)} problems {bad}")
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
