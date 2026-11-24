#!/usr/bin/env python3
"""
Extend assets/data/MANIFEST.json with the self-study-rooms entries.

Rules (from the repo convention, each one caught a real defect elsewhere):
  - extend IN PLACE: keep existing entries and their order, append new ones
  - every entry's feature count, byte size and sha256 are measured from the
    SHIPPED FILE, never carried over from a build step
  - sha256 is stored as a 16-character prefix, so it must be compared with
    startswith(), never for equality
  - the `files` list holds DATA + MAPS + NOTES; scripts live in the separate
    `scripts` section
  - a .geojson.gz cannot be read by GDAL directly, so it is decompressed and
    read as plain GeoJSON to count its features

Run:  python3 scripts/self-study-rooms/update_manifest.py
"""
import gzip
import hashlib
import json
import os


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
MANIFEST = os.path.join(REPO, "assets", "data", "MANIFEST.json")


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def count_features(path):
    """Count the features in a GeoJSON, transparently handling .gz."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        d = json.load(f)
    return len(d.get("features", []))


def entry(rel, title, dataset_id, notes, records=""):
    p = os.path.join(REPO, rel)
    size = os.path.getsize(p)
    e = {
        "file": rel,
        "bytes": size,
        "mb": round(size / 1048576, 3),
        "gzipped": rel.endswith(".gz"),
        "features": None,
        "title": title,
        "dataset_id": dataset_id,
        "records": records,
        "notes": notes,
        "sha256": sha16(p),
    }
    if rel.endswith(".geojson") or rel.endswith(".geojson.gz"):
        e["features"] = count_features(p)
    return e


def note_entry(rel, name, description):
    p = os.path.join(REPO, rel)
    size = os.path.getsize(p)
    return {
        "name": name,
        "file": rel,
        "description": description,
        "format": "markdown",
        "bytes": size,
        "mb": round(size / 1048576, 3),
        "sha256": sha16(p),
    }


def script_entry(rel, description):
    p = os.path.join(REPO, rel)
    return {
        "file": rel,
        "bytes": os.path.getsize(p),
        "sha256": sha16(p),
        "description": description,
    }


EDB_ROOMS = "edb_rcd_1633320468580_185"
EDB_ENROL = "edb_rcd_1633336508088_48919"
CSDI_STPUG = "censtatd_rcd_1635933193720_58660"
CSDI_DC = "censtatd_rcd_1635932856094_19982"

FILES = [
    ("assets/data/self-study-rooms/study_rooms.geojson",
     "Every self-study room in Hong Kong, with its name and address",
     EDB_ROOMS,
     "Education Bureau 'List of Study Room'. The only layer that lists all 194 rooms "
     "with coordinates. It carries NO seat count and NO utilisation - those come "
     "from the Government's LegCo reply CSTB217 (Q. 3479, 24 Jun 2026)."),
    ("assets/data/self-study-rooms/census_small_areas_slim.geojson.gz",
     "Census small areas, slimmed to the 18 attributes the analysis uses",
     CSDI_STPUG,
     "C&SD 2021 census small areas (STPUG). The source layer carries 211 attributes "
     "per unit; this ships 18: the five age bands, the working/non-working totals, "
     "the non-working student / retired / homemaker / carer / other counts, the "
     "median floor area (fa_m) and the household count. The field codes are opaque "
     "and were PROVED by recomputing published C&SD figures - see "
     "field_decode_audit.json."),
    ("assets/data/self-study-rooms/district_boundaries.geojson.gz",
     "District Council district boundaries", CSDI_DC,
     "C&SD 2021 district boundaries, for the district-level join."),
    ("assets/data/self-study-rooms/sec_enrol_district_grade.csv",
     "Senior-secondary enrolment by district and grade", EDB_ENROL,
     "Education Bureau enrolment by district and grade S1-S7 for 2025/26. EDB "
     "publishes this as a TABLE with no geometry, so it ships as a CSV rather than "
     "a GeoJSON. The total of all grades sums to 347,820, which matches the "
     "published total exactly."),
    ("assets/data/self-study-rooms/district_table.csv",
     "The master district table: supply, demand and crowding",
     "",
     "18 rows. Senior-secondary enrolment (S1-S7 and S4-S6), library seats and 2025 "
     "utilisation from the LegCo reply, census student and retired counts, median "
     "floor area, students per household and the crowding index."),
    ("assets/data/self-study-rooms/crowding_small_area.csv",
     "Per small area: median floor area, students and study rooms",
     CSDI_STPUG,
     "211 rows. The crowding measure: residents aged 15-24 per study room in each "
     "census small area, with the median floor area of the households there."),
    ("assets/data/self-study-rooms/network_walk.csv",
     "Every secondary school and its nearest study room, walked on the network",
     "landsd_rcd_1637222018065_52265",
     "514 schools. The walk is a Dijkstra shortest path on the full LandsD 3D "
     "pedestrian network (465,892 features, 1.42M graph nodes), NOT a straight "
     "line. Four schools are unroutable and are flagged, not counted as zero."),
    ("assets/data/self-study-rooms/elderly_competition_test.json",
     "The regression and partial correlations behind the elderly-competition test",
     "",
     "Records the spurious shared-denominator correlation (r = +0.866) AND the "
     "corrected test on counts (retired persons per 1,000 students: beta = -0.064, "
     "CI includes zero; adjusted R2 = -0.024, n = 18), plus the exam-period "
     "admission-card applications for 2023-2025."),
    ("assets/data/self-study-rooms/field_decode_audit.json",
     "The seven proofs that decode the opaque C&SD field codes", CSDI_STPUG,
     "Each field code is proved by recomputing a published C&SD figure, not "
     "guessed. The decisive check: the five age bands sum to the population total "
     "in all 18 districts and the residual of -1,125 is exactly the institutional "
     "(hospital) population the land-based census definition excludes."),
    ("assets/data/self-study-rooms/network_summary.json",
     "Distance-band counts and the route summary", "",
     "The walk-distance bands (159 / 292 / 382 / 436 / 484 schools within 400 m to "
     "1,500 m) against the straight-line counts, the detour factors and the snap "
     "distances."),
    ("assets/data/self-study-rooms/crowding_summary.json",
     "The crowding thresholds", CSDI_STPUG,
     "The territory median floor area (46 m2), the number of small areas below it, "
     "the students and study rooms they hold, and the number with no study room "
     "at all (128 of 211)."),
]

MAPS = [
    ("assets/maps/self-study-rooms/fig_study_rooms_gap.png",
     "Self-study rooms: supply gap and demand-vs-supply scatter",
     "Two panels. Left: the 194 study rooms and 514 secondary schools, with the "
     "three most contended districts shaded. Right: senior-secondary students per "
     "100 seats against 2025 library utilisation for all 18 districts, with the "
     "trend line."),
    ("assets/maps/self-study-rooms/fig_crowding_small_area.png",
     "Crowding: residents aged 15-24 per study room, by census small area",
     "211 census small areas coloured by residents aged 15-24 per study room. The "
     "128 small areas with NO study room inside are hatched, and the study rooms "
     "are marked as red squares."),
]

NOTES = [
    ("notes/hk-self-study-rooms — NOTES.md",
     "HK self-study rooms — seat supply, student demand and walking access",
     "The full method note: every layer with its CSDI id and record count, the "
     "field-code proofs, the three findings (no evidence of elderly competition; "
     "the seats are not full but are unevenly placed; 128 of 211 small areas have "
     "no study room), the network-vs-straight-line result, the reproducibility "
     "chain and the caveats to declare."),
]

SCRIPTS = [
    ("scripts/self-study-rooms/build_layers.py",
     "Build the shipping layers from the working folder: convert the CSDI ArcGIS "
     "shaped downloads to RFC 7946, slim the census small areas to the attributes "
     "the analysis uses, and copy the analysis tables and figures into the repo."),
    ("scripts/self-study-rooms/verify_notes.py",
     "Check every number in the published notes against the shipped layers - 136 "
     "assertions covering the district table, both walk-band table orientations, "
     "the crowding thresholds and each prose claim. The patterns CAPTURE the "
     "number the note states, so a swapped or drifted value fails."),
]


def main():
    m = json.load(open(MANIFEST, encoding="utf-8"))

    have_files = {e["file"] for e in m["files"]}
    have_scripts = {e["file"] for e in m["scripts"]}

    added = 0
    for rel, title, dsid, notes in FILES:
        if rel in have_files:
            print(f"  skip (already listed) {rel}")
            continue
        m["files"].append(entry(rel, title, dsid, notes))
        print(f"  added {rel}")
        added += 1

    for rel, title, notes in MAPS:
        if rel in have_files:
            print(f"  skip (already listed) {rel}")
            continue
        m["files"].append(entry(rel, title, "", notes))
        print(f"  added {rel}")
        added += 1

    for rel, name, desc in NOTES:
        if rel in have_files:
            print(f"  skip (already listed) {rel}")
            continue
        m["files"].append(note_entry(rel, name, desc))
        print(f"  added {rel}")
        added += 1

    for rel, desc in SCRIPTS:
        if rel in have_scripts:
            print(f"  skip (already listed) {rel}")
            continue
        m["scripts"].append(script_entry(rel, desc))
        print(f"  added {rel}")
        added += 1

    # the new sources
    have_sources = {s.get("id") for s in m["sources"]}
    new_sources = [
        {"name": "List of Study Room", "id": EDB_ROOMS,
         "provider": "Education Bureau via CSDI Portal",
         "url": f"https://portal.csdi.gov.hk/server/rest/services/common/{EDB_ROOMS}/FeatureServer"},
        {"name": "Student Enrolment in Secondary Day Schools by District and Grade",
         "id": EDB_ENROL, "provider": "Education Bureau via CSDI Portal",
         "url": f"https://portal.csdi.gov.hk/server/rest/services/common/{EDB_ENROL}/FeatureServer"},
        {"name": "Census 2021 small areas (STPUG) with theme statistics",
         "id": CSDI_STPUG, "provider": "Census and Statistics Department via CSDI Portal",
         "url": f"https://portal.csdi.gov.hk/server/rest/services/common/{CSDI_STPUG}/FeatureServer"},
        {"name": "District Council district boundaries", "id": CSDI_DC,
         "provider": "Census and Statistics Department via CSDI Portal",
         "url": f"https://portal.csdi.gov.hk/server/rest/services/common/{CSDI_DC}/FeatureServer"},
        {"name": "Reply to LegCo Question 3479 (CSTB217) — library study-room seats and utilisation",
         "id": "CSTB217", "provider": "Government reply to the Legislative Council",
         "url": "https://hkpl.gov.hk/en/library-notices/Resumption_20220421.html"},
    ]
    for s in new_sources:
        if s["id"] in have_sources:
            continue
        m["sources"].append(s)
        print(f"  added source {s['id']}")

    m["generated"] = "2026-11-24"
    m["note"] = m.get("note", "") + (
        " | 2026-11-24: added the Hong Kong self-study rooms project - 194 study "
        "rooms, 211 census small areas, 18 district boundaries, the district "
        "master table, the small-area crowding table, the network walk for 514 "
        "schools, the elderly-competition test and the field-code audit, plus two "
        "maps and a student worksheet. Seat counts and utilisation come from the "
        "Government's LegCo reply CSTB217, not from any dataset. The census field "
        "codes are opaque and were PROVED by recomputing published figures "
        "(7/7 checks). The obvious elderly-competition correlation of +0.866 is a "
        "shared-denominator artefact; the corrected test on counts finds no "
        "effect (adjusted R2 = -0.024, n = 18)."
    )

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, ensure_ascii=False)
    print(f"\n{added} files added; manifest now holds {len(m['files'])} files "
          f"and {len(m['scripts'])} scripts")


if __name__ == "__main__":
    main()
