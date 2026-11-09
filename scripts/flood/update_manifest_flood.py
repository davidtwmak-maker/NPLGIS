#!/usr/bin/env python3
"""
Extend assets/data/MANIFEST.json with the flood-prone-areas entries.

Rules (from the repo convention):
  - extend IN PLACE: keep existing entries and their order, append new ones
  - every entry's feature count, byte size and sha256 are measured from the
    SHIPPED FILE, never carried over from a build step
  - sha256 is stored as a 16-character prefix, so it must be compared with
    startswith(), never for equality
  - the `files` list holds DATA + MAPS + NOTES; scripts live in the separate
    `scripts` section
"""
import csv
import gzip
import hashlib
import json
import os

REPO = "/Users/davidhermes/nplgis"
MANIFEST = f"{REPO}/assets/data/MANIFEST.json"

FLOOD = [
    ("assets/data/flood/dsd_flood_prone_areas.geojson.gz",
     "The 267 official Hong Kong flood-prone locations from the Drainage "
     "Services Department's three lists (226 prone to blockage, 15 with "
     "drainage improvement works in progress, 26 coastal low-lying or windy "
     "residential areas), EPSG:4326",
     "Drainage Services Department", "vector"),
    ("assets/data/flood/flood_prone_areas_mechanism.geojson.gz",
     "The same 267 locations with the flood mechanism derived from the "
     "drainage network, the coastline and the 5 m terrain model: local "
     "drainage/blockage (185), channel backflow (48), coastal/tidal (32), "
     "low-lying ponding (2). Carries the distance and elevation evidence "
     "behind each classification, EPSG:4326",
     "derived from DSD, WSD, CEDD and LandsD", "vector"),
    ("assets/data/flood/flood_prone_areas_mechanism.csv",
     "The derived mechanism table: one row per location with its mechanism, "
     "confidence, elevation, distance to the coast, to a major channel, to "
     "the nearest inlet, to the catchment edge, and the evidence sentence",
     "derived", "table"),
    ("assets/maps/flood/HK_flood_mechanism_map.png",
     "The 267 flood-prone locations coloured by derived mechanism over the "
     "drainage network and coastline, with the mechanism counts and the "
     "cross-tab against DSD's own grouping",
     "derived", "map"),
    ("notes/hk-flood-prone-areas — NOTES.md",
     "The flood-prone-areas study note: the data recipe, the official lists, "
     "the derived mechanism method and its validation, the recommended "
     "index methodology, the assumptions and the validation block",
     "derived", "note"),
]

SCRIPTS = [
    ("scripts/flood/derive_mechanism_v2.py",
     "Derives the flood mechanism for all 267 locations from the coastline, "
     "the 5 m DTM, the drainage network and the catchments"),
    ("scripts/flood/make_mechanism_map.py",
     "Builds the flood-mechanism figure"),
    ("scripts/flood/gate_mechanism_map.py",
     "The figure gate: text overlap, off-canvas and pixel probes"),
    ("scripts/flood/fetch_support.sh",
     "Fetches the supporting DSD, WSD and CEDD layers with pagination and "
     "asserted final counts"),
    ("scripts/flood/verify_against_pdf.py",
     "Cross-checks the 226 scraped blockage titles against DSD's own "
     "published PDF"),
    ("scripts/flood/make_overview_map.py",
     "Builds the flood-prone-areas overview map"),
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
    elif rel.endswith(".csv"):
        with open(path) as f:
            e["records"] = sum(1 for _ in csv.reader(f)) - 1
    return e


def main():
    with open(MANIFEST) as f:
        m = json.load(f)
    files = m["files"]
    before = len(files)

    added, replaced, scripts_added = [], [], []
    for rel, desc, src, kind in FLOOD:
        e = measure(rel, desc, src, kind)
        hit = next((i for i, x in enumerate(files) if x["file"] == rel), None)
        if hit is None:
            files.append(e)
            added.append(rel)
        else:
            files[hit] = e
            replaced.append(rel)

    m.setdefault("scripts", [])
    for rel, desc in SCRIPTS:
        e = measure(rel, desc, "derived", "script")
        hit = next((i for i, x in enumerate(m["scripts"]) if x["file"] == rel), None)
        if hit is None:
            m["scripts"].append(e)
            scripts_added.append(rel)
        else:
            m["scripts"][hit] = e

    m["generated"] = "2026-11-09"

    have = {s.get("id") for s in m.get("sources", [])}
    for sid, name, provider, url in [
        ("dsd_rcd_1629267205231_66675",
         "Drainage channels", "DSD via CSDI Portal",
         "https://portal.csdi.gov.hk/server/rest/services/common/"
         "dsd_rcd_1629267205231_66675/FeatureServer"),
        ("dsd_rcd_1742963120722_16615",
         "Engineered channels", "DSD via CSDI Portal",
         "https://portal.csdi.gov.hk/server/rest/services/common/"
         "dsd_rcd_1742963120722_16615/FeatureServer"),
        ("dsd_rcd_1629267205231_69065",
         "Stormwater inlets", "DSD via CSDI Portal",
         "https://portal.csdi.gov.hk/server/rest/services/common/"
         "dsd_rcd_1629267205231_69065/FeatureServer"),
        ("wsd_rcd_1629267205232_5923",
         "Catchment and subcatchment areas", "WSD via CSDI Portal",
         "https://portal.csdi.gov.hk/server/rest/services/common/"
         "wsd_rcd_1629267205232_5923/FeatureServer"),
        ("cedd_rcd_1636520962284_7237",
         "Geological Map 1:100,000 - Coastline", "CEDD via CSDI Portal",
         "https://portal.csdi.gov.hk/server/rest/services/common/"
         "cedd_rcd_1636520962284_7237/FeatureServer"),
    ]:
        if sid not in have:
            m["sources"].append({"name": name, "id": sid, "provider": provider,
                                 "url": url})
    if "landsd_Whole_HK_DTM_5m" not in have:
        m["sources"].append({
            "name": "Whole Hong Kong Digital Terrain Model 5 m",
            "id": "landsd_Whole_HK_DTM_5m",
            "provider": "Lands and Survey Department",
            "url": "https://www.landsd.gov.hk/landsd_psi_data/SMO/data/"
                   "Whole_HK_DTM_5m.zip"})

    with open(MANIFEST, "w") as f:
        json.dump(m, f, indent=1)

    print(f"manifest data files: {before} -> {len(files)}")
    print(f"  added:    {added}")
    print(f"  replaced: {replaced}")
    print(f"  scripts added: {scripts_added}")

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
