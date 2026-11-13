#!/usr/bin/env python3
"""
Extend the NPLGIS MANIFEST with the low-lying land (< 5 m) layer.

The manifest is the machine-readable source register: one entry per shipped
file, with the feature count and sha256 taken FROM THE FILE THAT WAS
ACTUALLY SHIPPED - not carried over from a build step.

Rules (each one caught a real defect in this project):
  * Feature counts are counted from the shipped file, not from the source.
  * A .geojson.gz cannot be read by GDAL directly (it fails with "not
    recognized as being in a supported file format"), so it is decompressed
    and read as plain GeoJSON.
  * The manifest is extended IN PLACE: existing entries and their order are
    kept, and only the `generated` date and the new entries change.
  * EVERY entry's byte count and sha256 are re-read from disk at the end, so
    an entry left stale by another updater is caught here.

Run:  python3 update_manifest_lowland.py
"""
import gzip
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_repo_root():
    """Walk up from this script until the repo root is found."""
    d = HERE
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "assets", "data")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


REPO = os.environ.get("NPLGIS_REPO") or _find_repo_root()
if not REPO:
    raise SystemExit("cannot find the repo root")
MANIFEST = os.path.join(REPO, "assets/data/MANIFEST.json")

GENERATED = "2026-11-13"


def sha16(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def gz_feature_count(path):
    """Count features in a gzipped GeoJSON by decompressing it."""
    tmp = path + "_tmp"
    with gzip.open(path, "rb") as fin, open(tmp, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    try:
        with open(tmp, encoding="utf-8") as fh:
            payload = json.load(fh)
        assert payload.get("type") == "FeatureCollection", \
            f"{path} is not a FeatureCollection"
        assert "crs" not in payload, f"{path} carries a crs member"
        return len(payload.get("features", []))
    finally:
        os.remove(tmp)


def entry_for(rel, title, notes, features=None, records="", dataset_id=""):
    p = os.path.join(REPO, rel)
    size = os.path.getsize(p)
    return {
        "file": rel,
        "bytes": size,
        "mb": round(size / 1e6, 3),
        "gzipped": rel.endswith(".gz"),
        "features": features,
        "title": title,
        "dataset_id": dataset_id,
        "records": records,
        "notes": notes,
        "sha256": sha16(p),
    }


def main():
    with open(MANIFEST) as f:
        man = json.load(f)

    new_entries = []

    # ------------------------------------------------------------------
    rel = "assets/data/lowland/hk_lowland_under5m.geojson.gz"
    n = gz_feature_count(os.path.join(REPO, rel))
    assert n == 106, f"the cleaned layer has {n} features, expected 106"
    new_entries.append(entry_for(
        rel,
        "Hong Kong land below 5 m elevation",
        "The 106 contiguous patches of Hong Kong whose ground level is below 5 m "
        "above the Hong Kong Principal Datum, 60.58 km2 = 5.43% of the land. "
        "Patches under 0.05 km2 are dropped for readability (they hold 10.68 "
        "km2 between them and are in the all-patches layer). Each feature "
        "carries its area in km2 and hectares, its centre point in lon/lat, and "
        "the mean, minimum and maximum elevation within the patch. EPSG:4326 "
        "(GeoJSON is always lon/lat, RFC 7946); the areas are measured in "
        "EPSG:2326 (HK1980) and the reprojection changes them by 0.000000 "
        "km2. The sea is coded 0 m in the source DTM, so the land mask is "
        "essential - without it the query returns the whole ocean.",
        features=n,
        records=str(n),
    ))

    # ------------------------------------------------------------------
    rel = "assets/data/lowland/hk_lowland_under5m_all_patches.geojson.gz"
    n_all = gz_feature_count(os.path.join(REPO, rel))
    assert n_all == 9060, f"the all-patches layer has {n_all} features"
    new_entries.append(entry_for(
        rel,
        "Hong Kong land below 5 m elevation - every patch",
        "All 9,060 contiguous patches of low-lying land, including the slivers "
        "under 0.05 km2 that the cleaned layer drops. The two layers together "
        "hold the same 60.58 km2. EPSG:4326 (RFC 7946).",
        features=n_all,
        records=str(n_all),
    ))

    # ------------------------------------------------------------------
    new_entries.append(entry_for(
        "assets/data/lowland/hk_lowland_under5m.tif",
        "Low-lying land raster (5 m)",
        "Binary raster on the 5 m DTM grid, 12751 x 9601 at 5 m, EPSG:2326 "
        "(HK1980): 1 = land below 5 m, 0 = everything else. 2,423,036 cells = "
        "60.58 km2. Deflate-compressed GeoTIFF.",
    ))

    # ------------------------------------------------------------------
    new_entries.append(entry_for(
        "assets/data/lowland/hk_lowland_under5m_patches.csv",
        "Low-lying land patch table",
        "One row per kept patch: id, area in km2 and hectares, the centre point "
        "in lon/lat, and the mean, minimum and maximum elevation within the "
        "patch.",
        records="106 patches",
    ))

    # ------------------------------------------------------------------
    new_entries.append(entry_for(
        "assets/maps/lowland/HK_lowland_under5m_map.png",
        "Hong Kong land below 5 m - the low-lying land map",
        "The land below 5 m in blue over the 5 m terrain model, with the ten "
        "largest patches numbered and named, a key, a scale bar, a north "
        "arrow and a source line. The text-overlap and off-canvas checks both "
        "pass at zero. Victoria Harbour and Tolo Harbour read as sea, as they "
        "must.",
    ))

    # ------------------------------------------------------------------
    new_entries.append(entry_for(
        "notes/lowland-under5m — NOTES.md",
        "Low-lying land under 5 m - method note",
        "The method note: why the DTM's sea-as-0 m coding makes a land mask "
        "essential, the six land boundaries that were tested and how each one "
        "fails, the OSM Hong Kong boundary that was used, the acceptance test "
        "against Hong Kong's true land area and against 48 named places, the "
        "ArcGIS Pro instructions, and the known limits.",
    ))

    # --- extend in place, keeping existing entries and their order -----
    existing = {e["file"] for e in man["files"]}
    added = 0
    for e in new_entries:
        if e["file"] in existing:
            for i, cur in enumerate(man["files"]):
                if cur["file"] == e["file"]:
                    man["files"][i] = e
                    break
        else:
            man["files"].append(e)
            added += 1

    man["generated"] = GENERATED
    note = man.get("note", "")
    add = (f" | {GENERATED}: added HK Low-Lying Land under 5 m - the land in "
           f"Hong Kong below 5 m above the Principal Datum, 60.58 km2 = 5.43% "
           f"of the land, as 106 cleaned patches, all 9,060 patches, a binary "
           f"5 m raster and the map. The source DTM codes the sea as 0 m, so "
           f"the land mask is essential; it is built from the OSM Hong Kong "
           f"boundary relation 20044132 AND the DTM's positive elevation, and "
           f"gives 1,116.0 km2 of land against a true 1,106 km2. ")
    if "Low-Lying Land under 5 m" not in note:
        man["note"] = note + add

    # --- refresh EVERY existing entry's byte count and sha256 -----------
    refreshed = 0
    for e in man["files"]:
        p = os.path.join(REPO, e["file"])
        if not os.path.exists(p):
            continue
        size = os.path.getsize(p)
        sha = sha16(p)
        if e.get("bytes") != size or e.get("sha256") != sha:
            e["bytes"] = size
            e["mb"] = round(size / 1e6, 3)
            e["sha256"] = sha
            refreshed += 1

    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"manifest updated: {added} new entries, {refreshed} refreshed, "
          f"{len(man['files'])} total")

    # --- verify by reading the manifest back -----------------------------
    with open(MANIFEST) as f:
        back = json.load(f)
    assert back["generated"] == GENERATED
    for e in new_entries:
        match = [x for x in back["files"] if x["file"] == e["file"]]
        assert len(match) == 1, f"{e['file']} appears {len(match)} times"
        assert match[0]["sha256"] == e["sha256"], "sha mismatch after write"
        real = os.path.getsize(os.path.join(REPO, e["file"]))
        assert match[0]["bytes"] == real, f"{e['file']} byte count stale"
    stale = []
    for e in back["files"]:
        p = os.path.join(REPO, e["file"])
        if not os.path.exists(p):
            stale.append((e["file"], "missing"))
            continue
        if os.path.getsize(p) != e["bytes"] or not sha16(p).startswith(e["sha256"]):
            stale.append((e["file"], "mismatch"))
    assert not stale, f"stale manifest entries: {stale}"
    print("manifest verified: every entry's sha256 and byte count match disk")


if __name__ == "__main__":
    main()
