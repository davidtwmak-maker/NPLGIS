#!/usr/bin/env python3
"""Package the Hong Kong card-game venues project as a zip for delivery.

WHAT THIS PACKS
    The whole project as it stands: the web map application, the
    published data files, the static map figure, the written notes, and
    every pipeline script that produced them. Anyone who opens the zip
    can see what was done, check the numbers, and re-run the analysis.

    The raw provenance files - the geocoder's raw responses, the
    directory scrapes, the OpenStreetMap tile cache - are included too,
    but they are large, so they go in a separate archive and the
    manifest says so.

Usage:  package_tcg.py [--with-raw] [--out DIR]
"""
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/Users/davidhermes/nplgis")
OUT_DIR = Path("/Volumes/Extreme Pro/Download")

PROJECT = "hk-card-game-venues"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(with_raw):
    """The files that make up the project, as (arcname, path) pairs."""
    items = []

    # The web map application.
    #
    # The zip MIRRORS THE REPOSITORY LAYOUT rather than flattening it.
    # The app's HTML refers to ../../assets/style.css, ../../favicon.png
    # and ../../notes/... , because in the repository it sits at
    # apps/tcg-stores/. Flattening it to app/ breaks every one of those
    # paths, and the app then renders unstyled with no notes link. So
    # the zip keeps apps/, assets/ and notes/ where they are, and the
    # published data goes under assets/data/tcg-stores/ where the
    # repository puts it.
    for p in sorted((REPO / "apps/tcg-stores").rglob("*")):
        if p.is_file():
            items.append((str(p.relative_to(REPO)), p))

    # The published data, where the repository keeps it.
    for p in sorted((REPO / "assets/data/tcg-stores").rglob("*")):
        if p.is_file():
            items.append((f"assets/data/tcg-stores/{p.name}", p))

    # The static map figure.
    for p in sorted((REPO / "assets/maps/tcg-stores").rglob("*")):
        if p.is_file():
            items.append((f"assets/maps/tcg-stores/{p.name}", p))

    # The written notes.
    notes = REPO / "notes/hk-tcg-stores — NOTES.md"
    if notes.exists():
        items.append(("notes/hk-tcg-stores — NOTES.md", notes))

    # Every pipeline script.
    for p in sorted((REPO / "scripts/tcg-stores").rglob("*")):
        if p.is_file():
            items.append((f"scripts/tcg-stores/{p.name}", p))

    # The manifest entry for this project.
    man = REPO / "assets/data/MANIFEST.json"
    if man.exists():
        items.append(("assets/data/MANIFEST.json", man))

    # The shared assets the app's HTML refers to by a path that walks
    # up out of the app folder: ../../assets/style.css and
    # ../../favicon.png. They are copied into the same relative shape
    # inside the zip, so the app folder works as it is, unpacked and
    # served, without editing a single line.
    for rel in ("assets/style.css", "favicon.png"):
        p = REPO / rel
        if p.exists():
            items.append((rel, p))

    raw = []
    if with_raw:
        for name in ("raw/hkcardprice_shops.json", "raw/osm_tcg_shops.json",
                     "raw/tile_fetch_log.json"):
            p = HERE / name
            if p.exists():
                raw.append((f"raw/{p.name}", p))
        for p in sorted((HERE / "raw/osm_tiles").glob("*.json")):
            raw.append((f"raw/osm_tiles/{p.name}", p))
    return items, raw


def write_readme(items, raw, with_raw):
    lines = [
        "HONG KONG TRADING CARD GAME SHOPS AND PLAY VENUES",
        "=" * 56,
        "",
        "A spatial analysis of where card-game shops and play venues are in",
        "Hong Kong, and where the 15-24 year old population is underserved.",
        "",
        f"Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        "WHAT IS HERE",
        "",
        "  This zip mirrors the repository layout, so the app folder works",
        "  as it stands, unpacked and served, without editing a line.",
        "",
        "  apps/tcg-stores/   The interactive web map. Open",
        "             apps/tcg-stores/index.html in a browser, or serve",
        "             the folder over HTTP - the app loads its data files",
        "             with fetch(), which a file:// URL blocks. The",
        "             published copy is online at",
        "             https://davidtwmak-maker.github.io/NPLGIS/apps/tcg-stores/",
        "",
        "  assets/data/       The published data: shop and venue points,",
        "             the small area metrics, the district boundaries,",
        "             the summary, and the repository manifest.",
        "",
        "  assets/maps/       The static map figure, as a PNG.",
        "",
        "  notes/             The written notes: method, sources, the",
        "             checks that were run, and the defects that were",
        "             found.",
        "",
        "  scripts/tcg-stores/  Every script in the pipeline, in the order",
        "             they run. These produce the data files from the raw",
        "             sources.",
        "",
        "  assets/style.css   and  favicon.png  - the shared assets the",
        "             app's HTML refers to.",
        "",
    ]
    if with_raw:
        lines += [
            "  raw/       The raw provenance: the directory scrape, the",
            "             geocoder's raw responses, the OpenStreetMap tile",
            "             cache and the log of the tile fetches.",
            "",
        ]
    lines += [
        "THE HEADLINE FINDING",
        "",
        "  409,921 of Hong Kong's 591,073 people aged 15 to 24 - 69.4% -",
        "  live more than 1 km from any confirmed card-game play venue.",
        "  152 of the 211 census small areas have no venue within 1 km.",
        "",
        "  The figure is a lower bound on the problem, and a sensitivity",
        "  scenario is included: counting every registered Pokemon Gym as a",
        "  venue brings the unserved share to 66.2%.",
        "",
        "  The supply side: 282 shops and play venues were located, of which",
        "  49 are confirmed play spaces and 63 are official Pokemon Gyms. 47",
        "  shops are listed by two independent directories. Supply is",
        "  concentrated - Sham Shui Po 9 venues, Yau Tsim Mong 9, Kwun Tong 7,",
        "  Wan Chai 6, Wong Tai Sin 5 - and the North, Tuen Mun, Tsuen Wan,",
        "  Sai Kung and Yuen Long districts have none at all.",
        "",
        "HOW TO CHECK IT",
        "",
        "  The population total reconciles exactly with the published",
        "  Census and Statistics Department figure for 2021. Every number",
        "  in data/ can be re-derived from data/ by running the scripts in",
        "  scripts/. The notes record the checks that were run and the",
        "  defects that were found and fixed - including silent ones that",
        "  no error message would have revealed.",
        "",
        "  The scripts run in this order:",
        "",
        "    parse_baw.py           the BAW VAULT directory -> baw_shops.csv",
        "    geocode_shops.py       those addresses -> the government geocoder",
        "    derive_area_dc.py      derives the area -> district mapping",
        "    scrape_hkcardprice.py  the HKCardPrice directory -> raw JSON",
        "    geocode_hkcardprice.py those addresses -> the government geocoder",
        "    play_venues.py         the hand-built play venue list",
        "    geocode_venues.py      those addresses -> the government geocoder",
        "    merge_shops.py         all three sources -> shops_merged.json",
        "    analyse_merged.py      the census join and the catchment measure",
        "    build_app_data.py      the browser data, with the fidelity gate",
        "    build_map_figure.py    the static map figure",
        "    publish_data.py        the published data files in the repository",
        "",
        "  Four checks can be run on their own at any point:",
        "",
        "    check_districts.py     every shop point against the DC boundary",
        "    check_coverage.py      every source shop against the merged layer",
        "    why_no_match.py        why a shop did not geocode",
        "    why_this_match.py      why a shop matched the building it did",
        "",
        "AI USE DISCLOSURE",
        "",
        "  The analysis code was written with AI assistance. Every field",
        "  in the published data that the analysis derived carries an",
        "  'ai_' prefix, so an AI-derived value is never presented as a",
        "  measured one. The data itself is government and directory",
        "  source data; the AI wrote the code and the method.",

        "FILE INVENTORY",
        "",
    ]
    for arc, path in items:
        try:
            size = path.stat().st_size
            digest = sha256(path)
        except OSError:
            size, digest = 0, ""
        lines.append(f"  {arc:44} {size:>12,} bytes  sha256 {digest[:16]}")
    if raw:
        lines.append("")
        lines.append("  (raw provenance files are listed in raw/MANIFEST-raw.json)")
    lines.append("")
    return "\n".join(lines)


def main():
    out_dir = OUT_DIR
    with_raw = "--with-raw" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--out":
            out_dir = Path(sys.argv[i + 1])
    out_dir.mkdir(parents=True, exist_ok=True)

    items, raw = collect(with_raw)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    zip_path = out_dir / f"{PROJECT}-{stamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as z:
        for arc, path in items:
            z.write(path, f"{PROJECT}/{arc}")
        if raw:
            for arc, path in raw:
                z.write(path, f"{PROJECT}/{arc}")
        z.writestr(f"{PROJECT}/README.txt",
                   write_readme(items, raw, with_raw))
        if raw:
            man = [{"file": a, "bytes": p.stat().st_size}
                   for a, p in raw]
            z.writestr(f"{PROJECT}/raw/MANIFEST-raw.json",
                       json.dumps(man, indent=1, ensure_ascii=False))

    size = zip_path.stat().st_size
    print(f"wrote {zip_path}")
    print(f"  {len(items) + len(raw)} files, {size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
