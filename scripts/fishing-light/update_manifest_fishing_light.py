#!/usr/bin/env python3
"""
Extend assets/data/MANIFEST.json with the fishing-light entries, and REMOVE
the entries for files that the corrected analysis superseded.

The first version of this study shipped these files, all computed with the
broken land mask and the uncontrolled comparison:
  assets/maps/fishing-light/HK_fishing_light_seasonal_map.png
  assets/data/fishing-light/fishing_light_seasonal.json
  assets/data/fishing-light/night_lights_may_aug.tif
  assets/data/fishing-light/night_lights_sep_apr.tif
  assets/data/fishing-light/night_lights_change_may_minus_sep.tif
  assets/data/fishing-light/permitted_areas_seasonal_change.geojson.gz
They have been deleted from the repo, so their manifest entries must go too -
a manifest that lists a file that is not in the repo is worse than useless.

Rules (from the repo convention):
  - extend IN PLACE: keep existing entries and their order, append new ones
  - every entry's feature count, byte size and sha256 are measured from the
    SHIPPED FILE, never carried over from a build step
  - sha256 is stored as a 16-character prefix, so it must be compared with
    startswith(), never for equality
  - the `files` list holds DATA + MAPS + NOTES; scripts live in the separate
    `scripts` section
"""
import gzip
import hashlib
import json
import os

REPO = os.environ.get("NPLGIS_REPO", os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
MANIFEST = f"{REPO}/assets/data/MANIFEST.json"

DATA_PREFIXES = ("assets/data/", "assets/maps/", "notes/")

# the superseded first-version artefacts: removed from disk, removed here
SUPERSEDED = [
    "assets/maps/fishing-light/HK_fishing_light_seasonal_map.png",
    "assets/data/fishing-light/fishing_light_seasonal.json",
    "assets/data/fishing-light/night_lights_may_aug.tif",
    "assets/data/fishing-light/night_lights_sep_apr.tif",
    "assets/data/fishing-light/night_lights_change_may_minus_sep.tif",
    "assets/data/fishing-light/permitted_areas_seasonal_change.geojson.gz",
]

# the superseded first-version scripts: they computed the wrong results and
# reference files that no longer exist
SUPERSEDED_SCRIPTS = [
    "scripts/fishing-light/analyse_fishing_light.py",
    "scripts/fishing-light/make_fishing_light_map.py",
]

# the fishing-light files that SHOULD be in the manifest after the correction
FISHING_LIGHT = [
    ("assets/data/fishing-light/permitted_bright_light_fishing_areas.geojson.gz",
     "Areas in Hong Kong waters where bright-light fishing is permitted",
     "Marine Department via CSDI Portal", "vector"),
    ("assets/data/fishing-light/fishing_operation_distribution.geojson.gz",
     "Distribution of fishing operations of local vessels by grid and vessel class",
     "AFCD via CSDI Portal", "vector"),
    ("assets/data/fishing-light/nightly_measurements.csv.gz",
     "Per-night night-lights measurements 2012-2026: the bright-cell rate in "
     "the permitted deep water and in the control deep water, the within-night "
     "contrast, and the moon phase. Corrected analysis - deep water only, the "
     "LNG terminal and the Ma Liu Shui cable excluded", "NASA GIBS", "table"),
    ("assets/data/fishing-light/nightly_measurements.csv",
     "The same per-night table as plain CSV, for spreadsheet use",
     "NASA GIBS", "table"),
    ("assets/data/fishing-light/fishing_light_seasonal_CORRECTED.json",
     "Corrected fishing-light results: seasonal effect with a year-block "
     "confidence interval, vessel validation, per-area breakdown, active-night "
     "list and the full robustness sweep", "derived", "table"),
    ("assets/data/fishing-light/fishing_light_active_nights.csv",
     "The 20 nights in 2012-2026 that carried the fishing-light signal, with "
     "the excess bright-cell count against the control water", "derived", "table"),
    ("assets/data/fishing-light/fishing_light_monthly.csv",
     "Monthly median excess of single-night bright cells in the permitted deep "
     "water, and the number of active nights per month", "derived", "table"),
    ("assets/maps/fishing-light/HK_fishing_light_seasonal_map_CORRECTED.png",
     "The corrected four-panel figure: permitted areas and excluded structures, "
     "the active nights, the monthly profile and the headline statistics",
     "derived", "map"),
    ("notes/hk-fishing-light-seasonal \u2014 NOTES.md",
     "The study note, corrected: the fishing-light signal is episodic and "
     "clusters in the May-August moratorium window", "derived", "note"),
]

SCRIPTS = [
    ("scripts/fishing-light/fetch_seasonal.py",
     "Downloads the 693 nightly VIIRS rasters from NASA GIBS"),
    ("scripts/fishing-light/definitive_analysis.py",
     "The main corrected analysis: land mask, distance control, structure "
     "exclusion, within-night contrast, seasonal double difference, vessel "
     "validation and the per-area breakdown"),
    ("scripts/fishing-light/final_summary.py",
     "The active-night list and the spatial description of the largest night"),
    ("scripts/fishing-light/robustness.py",
     "Leave-one-year-out, leave-one-night-out and threshold sensitivity"),
    ("scripts/fishing-light/check_2023_break.py",
     "Tests whether the GIBS product changed around 2023"),
    ("scripts/fishing-light/persistence_test.py",
     "Separates fixed structures from moving boats by nights-per-cell"),
    ("scripts/fishing-light/moon_phase_test.py",
     "The dark-moon test on the transient bright cells"),
    ("scripts/fishing-light/make_corrected_map.py",
     "Builds the corrected four-panel figure"),
    ("scripts/fishing-light/gate_corrected_map.py",
     "The figure gate: text overlap, off-canvas and pixel probes"),
    ("scripts/fishing-light/variance_and_averaging.py",
     "The variance decomposition: how much of the night-to-night swing is "
     "nuisance, and a comparison of four ways to average it"),
]


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def measure(rel, desc, src, kind):
    path = os.path.join(REPO, rel)
    e = {"file": rel, "description": desc, "source": src, "type": kind,
         "bytes": os.path.getsize(path), "sha256": sha16(path)}
    e["mb"] = round(e["bytes"] / 1e6, 3)
    if rel.endswith(".geojson.gz"):
        with gzip.open(path, "rt") as f:
            e["features"] = len(json.load(f)["features"])
    elif rel.endswith(".csv.gz"):
        import csv
        import gzip as gz
        with gz.open(path, "rt") as f:
            e["records"] = sum(1 for _ in csv.reader(f)) - 1
    elif rel.endswith(".csv"):
        import csv
        with open(path) as f:
            e["records"] = sum(1 for _ in csv.reader(f)) - 1
    elif rel.endswith(".json"):
        e["records"] = None
    return e


def main():
    with open(MANIFEST) as f:
        m = json.load(f)
    files = m["files"]
    before = len(files)

    # ---- 1. drop the superseded entries --------------------------------
    have = {x["file"] for x in files}
    removed = []
    for s in SUPERSEDED:
        if s in have:
            files[:] = [x for x in files if x["file"] != s]
            removed.append(s)
    m.setdefault("scripts", [])
    for s in SUPERSEDED_SCRIPTS:
        if s in {x["file"] for x in m["scripts"]}:
            m["scripts"][:] = [x for x in m["scripts"] if x["file"] != s]
            removed.append(s + " (scripts)")
    for s in SUPERSEDED:
        if s in {x["file"] for x in m["scripts"]}:
            m["scripts"][:] = [x for x in m["scripts"] if x["file"] != s]
            removed.append(s + " (scripts)")

    # ---- 2. add or replace the current entries -------------------------
    added, replaced = [], []
    for rel, desc, src, kind in FISHING_LIGHT:
        e = measure(rel, desc, src, kind)
        hit = next((i for i, x in enumerate(files) if x["file"] == rel), None)
        if hit is None:
            files.append(e)
            added.append(rel)
        else:
            files[hit] = e
            replaced.append(rel)

    scripts_added = []
    for rel, desc in SCRIPTS:
        e = measure(rel, desc, "derived", "script")
        hit = next((i for i, x in enumerate(m["scripts"]) if x["file"] == rel), None)
        if hit is None:
            m["scripts"].append(e)
            scripts_added.append(rel)
        else:
            m["scripts"][hit] = e

    m["generated"] = "2026-11-09"

    have_src = {s.get("id") for s in m.get("sources", [])}
    for sid, name, provider, url in [
        ("mardep_rcd_1730952503222_38811",
         "Areas where bright-light fishing is permitted in Hong Kong waters",
         "Marine Department via CSDI Portal",
         "https://portal.csdi.gov.hk/server/rest/services/common/"
         "mardep_rcd_1730952503222_38811/FeatureServer"),
        ("afcd_rcd_1697167244880_33192",
         "Distribution of fishing operation in Hong Kong waters",
         "AFCD via CSDI Portal",
         "https://portal.csdi.gov.hk/server/rest/services/common/"
         "afcd_rcd_1697167244880_33192/FeatureServer"),
    ]:
        if sid not in have_src:
            m["sources"].append({"name": name, "id": sid, "provider": provider,
                                 "url": url})
    if "VIIRS_SNPP_GapFilled_BRDF_Corrected" not in have_src:
        m["sources"].append({
            "name": "VIIRS Day/Night Band (SNPP), gap-filled BRDF-corrected, NASA GIBS",
            "id": "VIIRS_SNPP_GapFilled_BRDF_Corrected_DayNightBand_Radiance",
            "provider": "NASA Global Imagery Browse Services",
            "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"})

    with open(MANIFEST, "w") as f:
        json.dump(m, f, indent=1)

    print(f"manifest data files: {before} -> {len(files)}")
    print(f"  removed:  {removed}")
    print(f"  added:    {added}")
    print(f"  replaced: {replaced}")
    print(f"  scripts added: {scripts_added}")

    # ---- 3. verify EVERY entry against the file on disk ----------------
    bad = []
    for e in files + m["scripts"]:
        p = os.path.join(REPO, e["file"])
        if not os.path.exists(p):
            bad.append((e["file"], "MISSING"))
            continue
        if os.path.getsize(p) != e["bytes"]:
            bad.append((e["file"], f"size {os.path.getsize(p)} != {e['bytes']}"))
            continue
        if not sha16(p).startswith(e["sha256"]):
            bad.append((e["file"], "sha mismatch"))
    print(f"verified {len(files)} data entries + {len(m['scripts'])} scripts, "
          f"{len(bad)} problems")
    for b in bad:
        print("  ", b)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
