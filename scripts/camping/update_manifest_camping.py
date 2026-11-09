#!/usr/bin/env python3
"""
Extend assets/data/MANIFEST.json with the camping-site entries.

Rules (from the repo convention):
  - extend IN PLACE: keep existing entries and their order, append new ones
  - every entry's feature count, byte size and sha256 are measured from the
    SHIPPED FILE, never carried over from a build step
  - sha256 is stored as a 16-character prefix, so it must be compared with
    startswith(), never for equality
"""
import hashlib
import json
import os
import subprocess

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
def _find_repo_root():
    """Walk up from this script until the repo root is found.

    The repo is recognised by its assets/data directory, so this works for a
    script in scripts/ and for one in scripts/<project>/ alike.
    """
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "assets", "data")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


REPO = os.environ.get("NPLGIS_REPO") or _find_repo_root() or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
MANIFEST = f"{REPO}/assets/data/MANIFEST.json"
NEW = f"{GIS_DATA}/HK Camping Sites/_manifest_entries.json"


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
    added, replaced = [], []
    for e in new:
        path = os.path.join(REPO, e["file"])
        assert os.path.exists(path), f"missing {path}"
        # Re-measure everything from the shipped file.
        e["bytes"] = os.path.getsize(path)
        e["mb"] = round(e["bytes"] / 1e6, 3)
        e["sha256"] = sha16(path)
        if e.get("features") is not None and e["file"].endswith(".geojson.gz"):
            import gzip
            with gzip.open(path, "rt") as f:
                e["features"] = len(json.load(f)["features"])
        hit = next((i for i, x in enumerate(files)
                    if x["file"] == e["file"]), None)
        if hit is None:
            files.append(e)
            added.append(e["file"])
        else:
            files[hit] = e
            replaced.append(e["file"])

    m["generated"] = "2026-11-09"
    # Record the new sources.
    have = {s.get("id") for s in m.get("sources", [])}
    for sid, name, provider in [
        ("afcd_rcd_1635133060194_82554",
         "Location of campsites in country parks", "AFCD via CSDI Portal"),
        ("afcd_rcd_1635129924112_81508",
         "Country parks", "AFCD via CSDI Portal"),
        ("afcd_rcd_1635133243757_2529",
         "Visitor centres in country parks", "AFCD via CSDI Portal"),
        ("afcd_rcd_1635136427551_29173",
         "Facilities in country parks", "AFCD via CSDI Portal"),
        ("afcd_rcd_1665568199103_4360",
         "Trails in country parks", "AFCD via CSDI Portal"),
    ]:
        if sid not in have:
            m["sources"].append({
                "name": name, "id": sid, "provider": provider,
                "url": f"https://portal.csdi.gov.hk/server/rest/services/"
                       f"common/{sid}/FeatureServer"})
    m["sources"].append({
        "name": "VIIRS Day/Night Band (NOAA-21), NASA GIBS",
        "id": "VIIRS_NOAA21_GapFilled_BRDF_Corrected",
        "provider": "NASA Global Imagery Browse Services",
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"})

    with open(MANIFEST, "w") as f:
        json.dump(m, f, indent=1)
    print(f"manifest: {before} -> {len(files)} entries")
    print(f"  added:    {added}")
    print(f"  replaced: {replaced}")

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
    print(f"verified {len(files)} entries, {len(bad)} problems")
    for b in bad:
        print("  ", b)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
