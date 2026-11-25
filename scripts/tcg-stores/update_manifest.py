#!/usr/bin/env python3
"""Extend assets/data/MANIFEST.json with the tcg-stores entries.

Every byte size, feature count and sha256 is MEASURED FROM THE SHIPPED
FILE, not carried over from a build step. The manifest is the claim
about what is in the repository, so it has to be checked against the
repository, not against the process that made it.

Run from the repository root:
    python3 scripts/tcg-stores/update_manifest.py
"""
import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "assets/data/MANIFEST.json"

CENSUS_ID = "censtatd_rcd_1635933193720_58660"
DC_ID = "censtatd_rcd_1635932856094_19982"


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def count_features(path):
    """The number of features in a GeoJSON file, read from the file."""
    if path.suffix == ".gz":
        import gzip
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return len(data["features"])
    return None


def count_records(path):
    """The number of rows in a JSON array or a CSV file."""
    if path.suffix == ".csv":
        with open(path, encoding="utf-8-sig") as f:
            return sum(1 for _ in f) - 1
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return len(data)
    return None


def entry(rel, title, notes, dataset_id="", records="", features="auto"):
    path = REPO / rel
    size = path.stat().st_size
    rec = {
        "file": rel,
        "bytes": size,
        "mb": round(size / (1024 * 1024), 3),
        "gzipped": rel.endswith(".gz"),
        "features": None,
        "title": title,
        "dataset_id": dataset_id,
        "records": "",
        "notes": notes,
        "sha256": sha16(path),
    }
    if features == "auto":
        if path.suffix in (".geojson", ".geojson.gz"):
            rec["features"] = count_features(path)
    if records == "auto":
        rec["records"] = count_records(path) if path.suffix in (".csv", ".json") else ""
    else:
        rec["records"] = records
    return rec


def script_entry(rel, description):
    path = REPO / rel
    return {
        "file": rel,
        "bytes": path.stat().st_size,
        "sha256": sha16(path),
        "description": description,
    }


# The counts that appear in a description are read from the published
# summary, never typed in. A hand-written count goes stale the moment the
# pipeline is rerun, and a stale count in a manifest is a false claim.
SUMMARY_PATH = REPO / "assets/data/tcg-stores/tcg_summary.json"


def _summary():
    with open(SUMMARY_PATH, encoding="utf-8") as f:
        return json.load(f)


def merged_shops_note():
    """The description of the merged layer, with its counts from the data."""
    s = _summary()
    return (
        "{n} shops merged from the BAW VAULT directory (205), the HKCardPrice "
        "PTCG directory (117) and a hand-built list of card-game and "
        "board-game venues (23). Each record carries its coordinates, the "
        "District Council district confirmed against the boundary layer, "
        "whether a play space is confirmed by the source, any official "
        "Pokemon Gym id, and which directories list it. {c} shops are "
        "confirmed by two or more sources. A hand-built venue that is the "
        "same shop as a directory listing is merged into it rather than "
        "counted twice. EPSG:4326."
    ).format(n=s["shops_total"], c=s["shops_confirmed_by_2_sources"])


def summary_note():
    """The description of the summary file, with its counts from the data."""
    s = _summary()
    sens = s["sensitivity_all_gyms_counted_as_venues"]
    return (
        "The figures quoted in the web map and the notes: {shops} shops, "
        "{play} confirmed play venues, {gyms} registered Pokemon Gyms, "
        "{y1524:,.0f} people aged 15-24, {near:,.0f} of them within 1 km of "
        "a venue, and {far:,.0f} ({pct}%) with no venue within 1 km. Also the "
        "sensitivity scenario in which every registered Gym is counted as a "
        "venue, which still leaves {spct}% of young people unserved."
    ).format(
        shops=s["shops_total"],
        play=s["play_venues_total"],
        gyms=s["pokemon_gyms_total"],
        y1524=s["young_people_15_24"],
        near=s["young_people_within_1km_of_a_venue"],
        far=s["young_people_with_no_venue_within_1km"],
        pct=s["share_young_with_no_venue"],
        spct=sens["share_young_with_no_venue"],
    )


def hkcardprice_geocode_note():
    """The description of the HKCardPrice geocode file, counts from the data."""
    s = _summary()
    n_total = 117
    n_geocoded = _hkp_geocoded_count()
    return (
        "The {total} HKCardPrice shops, each with the geocode evidence: the "
        "building the address matched, the district from the District Council "
        "boundary layer, whether the district agreed with the directory's own "
        "label, and the score. {geocoded} of the {total} are geocoded to the "
        "building level; the {rest} that are not are mall addresses with no "
        "street number, or an address the government index does not carry."
    ).format(total=n_total, geocoded=n_geocoded, rest=n_total - n_geocoded)


def _hkp_geocoded_count():
    """How many HKCardPrice shops carry a building-level geocode."""
    path = REPO / "assets/data/tcg-stores/tcg_shops_hkcardprice.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data if isinstance(data, list) else data.get("features", [])
    n = 0
    for r in rows:
        props = r.get("properties", r)
        if props.get("geocoded") or props.get("ai_geocode_rule"):
            n += 1
    return n


FILES = [
    ("assets/data/tcg-stores/tcg_shops_merged.json",
     "Every card shop in Hong Kong, geocoded to the building level",
     merged_shops_note(),
     "", "auto", ""),
    ("assets/data/tcg-stores/tcg_small_area_metrics.geojson",
     "2021 Census small areas with the card-game supply measure",
     "The 211 census small areas, each with its total population, its "
     "population aged 15-24, the number of play venues within 500 m, 1 km "
     "and 1.5 km, and ai_y1524_per_play_1000m - the 15-to-24-year-olds per "
     "play venue within 1 km. The geometry is simplified for the browser "
     "(worst vertex shift 13.3 m against a 60 m gate). EPSG:4326.",
     CENSUS_ID, "", "auto"),
    ("assets/data/tcg-stores/POPULATION — tcg_small_area_metrics.csv",
     "The card-game supply measure as a table",
     "One row per census small area: the population, the 15-24 population, "
     "the count of play venues and card shops near the area at each "
     "catchment radius, and the derived measures. The population total "
     "reconciles exactly with the published 2021 Census figure of "
     "7,411,945.",
     CENSUS_ID, "auto", ""),
    ("assets/data/tcg-stores/tcg_summary.json",
     "The headline numbers for the card-game project",
     summary_note(),
     CENSUS_ID, "", ""),
    ("assets/data/tcg-stores/tcg_shops_hkcardprice.json",
     "The HKCardPrice directory with its geocodes",
     hkcardprice_geocode_note(),
     DC_ID, "auto", ""),
    ("assets/data/tcg-stores/tcg_shops_hkcardprice_directory.json",
     "The raw HKCardPrice directory scrape",
     "The directory as scraped, before any geocoding, so the provenance of "
     "every later record can be checked. 117 shops with their address, the "
     "purchase and play tags, the verified date and the official Pokemon "
     "Gym id.",
     "", "auto", ""),
    ("assets/data/tcg-stores/tcg_play_venues.json",
     "The hand-built list of card-game and board-game venues",
     "23 venues with their addresses and building names, 19 of them "
     "geocoded. Each carries the District Council district checked against "
     "the boundary layer. Six turned out to be the same shop the "
     "directories already list and were merged rather than counted twice.",
     DC_ID, "auto", ""),
]

SCRIPTS = [
    ("scripts/tcg-stores/parse_baw.py",
     "Parse the BAW VAULT Hong Kong card-shop directory into baw_shops.csv, keeping the raw provenance file. The directory's address field is the Chinese one and its building_token names the building the shop sits in."),
    ("scripts/tcg-stores/geocode_shops.py",
     "Geocode the 205 BAW VAULT shops to the building level with the Hong Kong Government location search service, matching on the building token with a strict token-quality rule. Asserts every accepted hit is within about 700 m of its source pin."),
    ("scripts/tcg-stores/scrape_hkcardprice.py",
     "Scrape the HKCardPrice Hong Kong PTCG directory, 117 shops, then fetch every shop's own detail page for the official Pokemon Gym id and the verification date. Rejects a detail page that does not resolve to its own slug."),
    ("scripts/tcg-stores/geocode_hkcardprice.py",
     "Geocode the 117 HKCardPrice shops with the same evidence ranking as the other geocoder: building name match, then street number, then street name as credit only, with the district as a confirmatory check and never a veto. Handles mall addresses with no street number, and the directory's variant character for a shopping centre."),
    ("scripts/tcg-stores/geocode_venues.py",
     "Geocode the hand-built venue list. Handles duplicate building names in Hong Kong by separating them on the street number in the hit's own address, and treats the District Council district as confirmatory rather than a veto because hand-written district columns are guesses."),
    ("scripts/tcg-stores/play_venues.py",
     "The source of truth for the hand-built venue list: name, Chinese name, English and Chinese address, building name, area and District Council district."),
    ("scripts/tcg-stores/merge_shops.py",
     "Merge the three directories into one shop-level layer. A shop is the same shop only when its name AND its building agree, so a mall's separate branches stay separate. A hand-built venue that is already a directory play venue in the same building is absorbed into it rather than added twice."),
    ("scripts/tcg-stores/analyse_merged.py",
     "The spatial analysis: assign every shop to its census small area, count play venues within 500 m, 1 km and 1.5 km, and derive the young-people-per-venue measure. Refuses to write output unless the population reconciles exactly with the published 2021 Census total of 7,411,945 and every area's age bands sum to its own total. Also runs the sensitivity scenario in which every registered Pokemon Gym counts as a venue."),
    ("scripts/tcg-stores/build_app_data.py",
     "Build the browser data for the web map: the simplified area polygons, the shop points, the legend and the summary. Gates the polygon simplification at 60 m of vertex shift and 2% of area change, with an absolute gate for the smallest areas."),
    ("scripts/tcg-stores/build_map_figure.py",
     "Build the static map figure: the census small areas in six classes, the shops, the confirmed play venues and the registered Pokemon Gyms, with a key and the headline numbers."),
    ("scripts/tcg-stores/raster.py",
     "A scanline rasteriser for point-in-polygon over many polygons at once, used to assign the census population to small areas."),
    ("scripts/tcg-stores/fix_blank_districts.py",
     "Re-derive the district of every census small area from its own geometry, because the district column in the shipped population CSV is wrong for 15 of the 18 districts."),
    ("scripts/tcg-stores/diagnose_district.py",
     "Diagnose the district column defect in the shipped census CSV by comparing it against the spatially derived district, area by area."),
]


def main():
    with open(MANIFEST, encoding="utf-8") as f:
        m = json.load(f)

    # ---- the sources ------------------------------------------------------
    have = {s.get("name") for s in m["sources"]}
    new_sources = [
        {"name": "BAW VAULT Hong Kong card-shop directory",
         "id": "bawvault",
         "provider": "BAW VAULT",
         "url": "https://bawvault.com/card-shops/hong-kong/"},
        {"name": "HKCardPrice Hong Kong PTCG shop directory",
         "id": "hkcardprice",
         "provider": "HKCardPrice",
         "url": "https://hkcardprice.com/shops/"},
        {"name": "Hong Kong Government location search service (GeoInfo Map)",
         "id": "gih-ws2",
         "provider": "Government of the Hong Kong SAR, GeoInfo Map",
         "url": "https://www.map.gov.hk/gm/"},
    ]
    for s in new_sources:
        if s["name"] not in have:
            m["sources"].append(s)

    # ---- the files --------------------------------------------------------
    # The entries are REPLACED, not skipped. The manifest is a claim
    # about what is in the repository, so it has to be re-measured every
    # time, otherwise it quietly goes stale the moment a file changes.
    by_file = {f["file"]: f for f in m["files"]}
    for rel, title, notes, did, recs, feats in FILES:
        new = entry(rel, title, notes, did, recs, feats)
        if rel in by_file:
            by_file[rel].update(new)
        else:
            m["files"].append(new)

    # ---- the scripts ------------------------------------------------------
    by_script = {s["file"]: s for s in m["scripts"]}
    for rel, desc in SCRIPTS:
        new = script_entry(rel, desc)
        if rel in by_script:
            by_script[rel].update(new)
        else:
            m["scripts"].append(new)

    m["generated"] = "2026-11-25"

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print(f"sources: {len(m['sources'])}  files: {len(m['files'])}  "
          f"scripts: {len(m['scripts'])}")
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
