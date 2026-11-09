#!/usr/bin/env python3
"""
Extend assets/data/MANIFEST.json with the fishing-light seasonal entries.

Rules (from the repo convention):
  - extend IN PLACE: keep existing entries and their order, append new ones
  - every entry's feature count, byte size and sha256 are measured from the
    SHIPPED FILE, never carried over from a build step
  - sha256 is stored as a 16-character prefix, so it must be compared with
    startswith(), never for equality
  - the `files` list is DATA-ONLY by convention; scripts live in the
    separate `scripts` section
"""
import gzip
import hashlib
import json
import os

REPO = "/Users/davidhermes/nplgis"
MANIFEST = f"{REPO}/assets/data/MANIFEST.json"
NEW = "/Users/davidhermes/GIS Data/HK Night Lights/_manifest_entries.json"

DATA_ONLY = "assets/data/"


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    with open(MANIFEST) as f:
        m = json.load(f)
    files = m["files"]
    before = len(files)

    new = json.load(open(NEW))
    added, replaced, scripts_added = [], [], []

    for e in new:
        path = os.path.join(REPO, e["file"])
        assert os.path.exists(path), f"missing {path}"
        # Re-measure everything from the shipped file.
        e["bytes"] = os.path.getsize(path)
        e["mb"] = round(e["bytes"] / 1e6, 3)
        e["sha256"] = sha16(path)
        if e.get("features") is not None and e["file"].endswith(".geojson.gz"):
            with gzip.open(path, "rt") as f:
                e["features"] = len(json.load(f)["features"])

        if e["file"].startswith(DATA_ONLY) or e["file"].startswith("assets/maps/") \
                or e["file"].startswith("notes/"):
            hit = next((i for i, x in enumerate(files)
                        if x["file"] == e["file"]), None)
            if hit is None:
                files.append(e)
                added.append(e["file"])
            else:
                files[hit] = e
                replaced.append(e["file"])
        else:
            # .py build scripts go in the separate scripts section
            m.setdefault("scripts", [])
            hit = next((i for i, x in enumerate(m["scripts"])
                        if x["file"] == e["file"]), None)
            if hit is None:
                m["scripts"].append(e)
                scripts_added.append(e["file"])
            else:
                m["scripts"][hit] = e

    m["generated"] = "2026-11-09"

    have = {s.get("id") for s in m.get("sources", [])}
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
        if sid not in have:
            m["sources"].append({"name": name, "id": sid, "provider": provider,
                                 "url": url})
    if "VIIRS_SNPP_GapFilled_BRDF_Corrected" not in have:
        m["sources"].append({
            "name": "VIIRS Day/Night Band (SNPP), gap-filled BRDF-corrected, NASA GIBS",
            "id": "VIIRS_SNPP_GapFilled_BRDF_Corrected_DayNightBand_Radiance",
            "provider": "NASA Global Imagery Browse Services",
            "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"})

    with open(MANIFEST, "w") as f:
        json.dump(m, f, indent=1)
    print(f"manifest data files: {before} -> {len(files)}")
    print(f"  added:    {added}")
    print(f"  replaced: {replaced}")
    print(f"  scripts/notes added: {scripts_added}")

    # ---- verify every entry against the file on disk -------------------
    bad = []
    for e in files:
        p = os.path.join(REPO, e["file"])
        if not os.path.exists(p):
            bad.append((e["file"], "MISSING"))
            continue
        if os.path.getsize(p) != e["bytes"]:
            bad.append((e["file"], f"size {os.path.getsize(p)} != {e['bytes']}"))
            continue
        if not sha16(p).startswith(e["sha256"]):
            bad.append((e["file"], "sha mismatch"))
    print(f"verified {len(files)} data entries, {len(bad)} problems")
    for b in bad:
        print("  ", b)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
