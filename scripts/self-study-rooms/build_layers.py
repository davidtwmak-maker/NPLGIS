#!/usr/bin/env python3
"""
Build the self-study-rooms shipping layers from the working folder.

Rules (from the repo convention):
  - every GeoJSON that ships must be RFC 7946: a FeatureCollection, no "crs"
    member, "properties" (never ArcGIS's "attributes"), and lon/lat order
  - the working folder holds CSDI downloads in the ArcGIS shape, so the
    conversion happens HERE, once, and the shipped file is the RFC 7946 one
  - the census small-area layer carries 211 attributes per unit; the analysis
    uses 9 of them, so the shipped layer is SLIMMED to those 9 plus the
    geometry, and the full attribute list is recorded in the note
  - feature counts and byte sizes are measured from the SHIPPED file

Run:  python3 scripts/self-study-rooms/build_layers.py
"""
import csv
import gzip
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.expanduser("~/GIS Data/HK Self Study Rooms")
OUT = os.path.join(REPO, "assets", "data", "self-study-rooms")
MAPS = os.path.join(REPO, "assets", "maps", "self-study-rooms")

# the census attributes the analysis actually uses. Everything else is
# dropped from the shipped layer - the full set is in the project note.
CENSUS_KEEP = [
    "stpug", "stpug_eng", "stpug_chi", "t_pop", "t_wp", "t_nwp",
    "age_1", "age_2", "age_3", "age_4", "age_5",
    "nwp_st", "nwp_re", "nwp_hm", "nwp_care", "nwp_oth",
    "fa_m", "dh",
]


def _props(feature):
    """CSDI serves ArcGIS-shaped features ("attributes"); normalise both."""
    return feature.get("properties") or feature.get("attributes") or {}


def to_rfc7946(feature, keep=None):
    """Return an RFC 7946 Feature, dropping attributes not in `keep`."""
    out = {
        "type": "Feature",
        "properties": {},
        "geometry": feature.get("geometry"),
    }
    props = _props(feature)
    keys = keep if keep is not None else list(props.keys())
    for k in keys:
        if k in props:
            out["properties"][k] = props[k]
    # ArcGIS leaves the id in a separate member
    if "fid" in props:
        out["id"] = props["fid"]
    return out


def collection(features, keep=None):
    return {
        "type": "FeatureCollection",
        "features": [to_rfc7946(f, keep) for f in features],
    }


def write_geojson(fc, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    return path


def write_gz(fc, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    return path


def load(name):
    with open(os.path.join(WORK, "raw", name), encoding="utf-8") as f:
        return json.load(f)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(MAPS, exist_ok=True)
    made = []

    # --- study rooms: 194 points, the core layer
    sr = load("study_rooms_edb.geojson")
    write_geojson(collection(sr["features"]),
                  os.path.join(OUT, "study_rooms.geojson"))
    made.append("study_rooms.geojson")

    # --- secondary enrolment by district and grade.
    # This layer has NO geometry: EDB publishes it as a table keyed by
    # district, not as points. It ships as a CSV, because a GeoJSON whose
    # features carry no geometry fails the repo's RFC 7946 sweep.
    en = load("sec_enrol_district_grade.geojson")
    rows = []
    for feat in en["features"]:
        p = _props(feat)
        rows.append({
            "district_en": p.get("DISTRICT_EN", ""),
            "district_tc": p.get("DISTRICT_TC", ""),
            "school_year": p.get("SCHOOL_YEAR", ""),
            "all_grades": p.get("ALL_GRADES", ""),
            "s1": p.get("S1", ""), "s2": p.get("S2", ""), "s3": p.get("S3", ""),
            "s4": p.get("S4", ""), "s5": p.get("S5", ""), "s6": p.get("S6", ""),
            "s7": p.get("S7", ""),
        })
    csv_path = os.path.join(OUT, "sec_enrol_district_grade.csv")
    os.makedirs(OUT, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    made.append("sec_enrol_district_grade.csv")

    # --- census small areas, slimmed to the attributes the analysis uses
    st = load("census_stpug_2021.geojson")
    write_gz(collection(st["features"], keep=CENSUS_KEEP),
            os.path.join(OUT, "census_small_areas_slim.geojson.gz"))
    made.append("census_small_areas_slim.geojson.gz")

    # --- district boundaries
    dc = load("census_dc_2021.geojson")
    write_gz(collection(dc["features"]),
            os.path.join(OUT, "district_boundaries.geojson.gz"))
    made.append("district_boundaries.geojson.gz")

    # --- the analysis outputs, as published tables
    tables = [
        ("district_table.csv", "work/district_table.csv"),
        ("crowding_small_area.csv", "work/crowding_small_area_named.csv"),
        ("network_walk.csv", "work/network_walk.csv"),
        ("elderly_competition_test.json", "work/elderly_competition_test.json"),
        ("field_decode_audit.json", "work/field_decode_audit.json"),
        ("network_summary.json", "work/network_summary.json"),
        ("crowding_summary.json", "work/crowding_summary.json"),
    ]
    for dest, src in tables:
        src = os.path.join(WORK, src)
        if not os.path.exists(src):
            print(f"  SKIP {dest} - {src} not found", file=sys.stderr)
            continue
        shutil.copy2(src, os.path.join(OUT, dest))
        made.append(dest)

    # --- the two figures
    for fig in ["fig_study_rooms_gap.png", "fig_crowding_small_area.png"]:
        src = os.path.join(WORK, fig)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(MAPS, fig))
            made.append(f"assets/maps/self-study-rooms/{fig}")

    for m in made:
        print(f"  built {m}")
    print(f"\n{len(made)} files written under {OUT}")


if __name__ == "__main__":
    sys.exit(main())
