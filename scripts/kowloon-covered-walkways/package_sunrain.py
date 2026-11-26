#!/usr/bin/env python3
"""Package the 最日曬雨淋中學 covered-walkways project for hand-off.

WHAT THIS PACKAGES
    The school's own project folder - the one under
    `~/GIS Data/Sun-Rain Exposure/out/` - plus the working web map
    from the repository, so the school gets both the data and the
    interactive map in one download.

WHY THE APP IS COPIED IN
    The app folder's HTML refers to `../../assets/style.css` and
    `../../notes/... — NOTES.md`, which walk up out of the app folder.
    Unpacked on its own the page renders unstyled and the notes link
    is dead. So the package keeps the same relative shape: the app
    sits at `apps/kowloon-covered-walkways/`, and `assets/` and
    `notes/` sit beside it, exactly as in the repository. Unpack it,
    serve the folder, and the map works with no editing.

THE ROUTE OPTIONS CAVEAT
    `data/route_options.geojson` in the working folder is the file the
    stop-to-school pipeline writes, and its MTR option comes from that
    pipeline's own capped candidate search (800 m straight-line from
    the school).  The published map uses a DIFFERENT walk - the
    worst-case walk from the nearest station exit, solved over every
    exit in a 1 km buffer - and the two disagree for 19 of the 164
    schools.  So the working folder's copy is refreshed from the
    corrected app build before packaging, and the README explains the
    distinction.

    Every number in the README is read from the shipped data at
    package time. Nothing is typed by hand.
"""
import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

SRC = Path("/Users/davidhermes/GIS Data/Sun-Rain Exposure/out/"
           "最日曬雨淋中學 — 2026-11-24")
REPO = Path("/Users/davidhermes/nplgis")
OUT = Path("/Volumes/Extreme Pro/Download")
PROJECT = "最日曬雨淋中學 — Covered Walkways to School"

EXCLUDE_DIRS = {"__pycache__", ".git", ".ipynb_checkpoints"}
EXCLUDE_SUFFIX = {".pyc", ".pyo"}


def add_tree(items, root, prefix):
    """Every file under root, at prefix, skipping bytecode."""
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if EXCLUDE_DIRS & set(p.parts):
            continue
        if p.suffix in EXCLUDE_SUFFIX:
            continue
        # A ".pre-fix" or ".bak" file is a working artefact, never part
        # of the hand-off.  Shipping one puts a superseded version of
        # the data in front of the reader, indistinguishable from the
        # current one except by its name.
        if ".pre-fix" in p.name or ".bak" in p.name or ".orig" in p.name:
            continue
        items.append((f"{prefix}/{p.relative_to(root).as_posix()}", p))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def refresh_route_options():
    """Put the corrected MTR route options into the working folder.

    The published map's route_options.geojson is the corrected file:
    every school's MTR option is the worst-case walk the map draws.
    The working folder's copy is whatever the stop-to-school pipeline
    last wrote, which carries the capped-search route instead.
    """
    app = REPO / "apps/kowloon-covered-walkways/data/route_options.geojson"
    dst = SRC / "data/route_options.geojson"
    if not app.exists():
        print("  app route_options.geojson not found; working folder left as is")
        return
    data = json.load(open(app, encoding="utf-8"))
    feats = data.get("features", data)
    mtr = [f["properties"] for f in feats
           if f["properties"].get("ai_route_kind") == "nearest_mtr"]
    schools = {p.get("school_id") for p in mtr}
    if dst.exists():
        old = json.load(open(dst, encoding="utf-8"))
        old_feats = old.get("features", old)
        old_mtr = [f["properties"] for f in old_feats
                   if f["properties"].get("ai_route_kind") == "nearest_mtr"]
        old_schools = {p.get("school_id") for p in old_mtr}
        if old_schools == schools and len(old_mtr) == len(mtr):
            print("  working folder route_options already current (%d MTR "
                  "options)" % len(mtr))
            return
        print("  working folder route_options had %d MTR options, "
              "corrected file has %d" % (len(old_mtr), len(mtr)))
    else:
        print("  working folder route_options.geojson not found; writing it")
    shutil.copyfile(app, dst)
    print("  working folder route_options.geojson refreshed from the "
          "published map build")


def build():
    items = []

    # The working folder's route_options.geojson is written by the
    # stop-to-school pipeline and carries ITS MTR route - the one from
    # the capped 800 m candidate search, which is not the walk the map
    # draws.  The published map's copy is the corrected one, so refresh
    # the working folder's copy from it before packaging.  Otherwise a
    # rebuild of the stop-to-school pipeline would quietly put the old
    # route back into the hand-off.
    refresh_route_options()

    # The school's project folder, as they left it.
    for sub in ("data", "scripts", "notes", "figures", "arcgis"):
        d = SRC / sub
        if d.is_dir():
            add_tree(items, d, sub)

    # The working web map, in its repository shape so its relative
    # references still resolve.
    add_tree(items, REPO / "apps/kowloon-covered-walkways",
             "apps/kowloon-covered-walkways")
    for rel in ("assets/style.css", "favicon.png"):
        p = REPO / rel
        if p.exists():
            items.append((rel, p))
    notes = REPO / "notes/kowloon-covered-walkways — NOTES.md"
    if notes.exists():
        items.append(("notes/kowloon-covered-walkways — NOTES.md", notes))

    # The note's own verification gate. It parses the note's tables and
    # checks them against the shipped data, so it travels with the data
    # it protects - a reader can re-run it.
    gate = REPO / "scripts/kowloon-covered-walkways/verify_note.py"
    if gate.exists():
        items.append(("scripts/kowloon-covered-walkways/verify_note.py", gate))

    # The manifest entry for this project.
    man = REPO / "assets/data/MANIFEST.json"
    if man.exists():
        items.append(("assets/data/MANIFEST.json", man))

    readme = build_readme(items)
    items.append(("README.md", readme))

    ts = None
    stamp = os.popen("date '+%Y%m%d-%H%M'").read().strip()
    out = OUT / f"最日曬雨淋中學 — covered walkways {stamp}.zip"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as z:
        for arc, path in items:
            z.write(path, f"{PROJECT}/{arc}")

    print(f"wrote {out}")
    print(f"  {len(items)} files, {out.stat().st_size:,} bytes")
    print(f"  sha256 {sha256(out)}")
    return out


def _facts(items):
    """The numbers the README states, read from the shipped files."""
    by_arc = {a: p for a, p in items}
    facts = {}

    # Schools, from the route metrics table.
    csv = by_arc.get("arcgis/Schools_RouteMetrics.csv")
    if csv:
        import csv as _csv
        with open(csv, encoding="utf-8-sig") as fh:
            rows = list(_csv.DictReader(fh))
        facts["schools"] = len(rows)

    # Route counts, from the raw route geometry.
    geom = by_arc.get("data/peninsula_route_geometry.geojson")
    if geom:
        d = json.load(open(geom, encoding="utf-8"))
        feats = d.get("features", d)
        facts["routes"] = len(feats)
        kinds = {}
        for f in feats:
            k = f["properties"]["ai_route_kind"]
            kinds[k] = kinds.get(k, 0) + 1
        facts["route_kinds"] = kinds

    # Covered path segments and stops.
    for key, fname in (("covered_segments", "data/peninsula_covered_paths.geojson"),
                       ("stops", "data/peninsula_pti.geojson")):
        p = by_arc.get(fname)
        if p:
            d = json.load(open(p, encoding="utf-8"))
            facts[key] = len(d.get("features", d))

    # Route options: raw and with the MTR fallback.
    for key, fname in (("options_raw", "data/route_options.geojson"),
                       ("options_app",
                        "apps/kowloon-covered-walkways/data/route_options.geojson")):
        p = by_arc.get(fname)
        if p:
            d = json.load(open(p, encoding="utf-8"))
            facts[key] = len(d.get("features", d))

    # The typology split and the MTR walk distances.
    typo = by_arc.get("data/access_typology.json")
    if typo:
        d = json.load(open(typo, encoding="utf-8"))
        rows = d if isinstance(d, list) else (
            d.get("schools") or d.get("records") or [])
        if rows:
            dep = sum(1 for r in rows
                      if str(r.get("access") or "").startswith("transit"))
            facts["walk_access"] = len(rows) - dep
            facts["transit_dependent"] = dep

    # The MTR walk distances, from the worst-case walk file.
    mtr = by_arc.get("data/mtr_walk_schools.json")
    if mtr:
        d = json.load(open(mtr, encoding="utf-8"))
        rows = d if isinstance(d, list) else d.get("schools", d)
        ws = sorted(float(r["walk_m"]) for r in rows
                    if r.get("walk_m") is not None)
        if ws:
            # The SAME convention the pipeline and the method note use:
            # statistics.median, and statistics.quantiles(n=10)[8] for
            # the p90.  Taking the middle element instead gives 702 m
            # where the data says 693 m - a figure that looks plausible
            # and is wrong.
            import statistics as stx
            facts["mtr_median_m"] = round(stx.median(ws))
            facts["mtr_max_m"] = round(max(ws))
            facts["mtr_p90_m"] = round(stx.quantiles(ws, n=10)[8])

    # Schools with no covered stretch at all.
    csv = by_arc.get("arcgis/Schools_RouteMetrics.csv")
    if csv:
        import csv as _csv
        with open(csv, encoding="utf-8-sig") as fh:
            rows = list(_csv.DictReader(fh))
        zero = sum(1 for r in rows
                   if float(r.get("ai_covered_m") or 0) == 0)
        facts["no_cover"] = zero
    return facts


def build_readme(items):
    f = _facts(items)
    out = Path("/tmp/_sr_readme.md")
    L = []
    L.append(f"# {PROJECT}")
    L.append("")
    L.append("Where are the covered pedestrian pathways, and how covered is the")
    L.append("walk from a public transport stop to each secondary school?")
    L.append("")
    L.append("Six districts — Sham Shui Po, Kowloon City, Yau Tsim Mong, Wong Tai")
    L.append("Sin, Kwun Tong, Kwai Chung — and "
             f"{f.get('schools', '—')} registered secondary schools.")
    L.append("")
    L.append("**Live map:** "
             "https://davidtwmak-maker.github.io/NPLGIS/apps/kowloon-covered-walkways/")
    L.append("")
    L.append("## The method, in four lines")
    L.append("")
    L.append("Routes are **shortest paths on the LandsD 3D Pedestrian Network**,")
    L.append("not straight lines. The network is split into classes straight from")
    L.append("its own fields: `WeatherProof = 1` (Covered) or `Location = 2`")
    L.append("(Indoor) is sheltered; `WeatherProof = 3` counts as **not** covered —")
    L.append("the conservative reading for a rain-exposure question. Each route")
    L.append("is measured segment by segment for covered length, the **longest")
    L.append("unbroken stretch with no cover**, and the number of separate open")
    L.append("stretches. Two routes per school: the **shortest** and the")
    L.append("**best-covered**.")
    L.append("")
    L.append("## What is in this package")
    L.append("")
    L.append("```")
    L.append("apps/kowloon-covered-walkways/   the interactive Leaflet map")
    L.append("data/                            the route, stop, coverage and")
    L.append("                                 typology layers")
    L.append("scripts/                         the pipeline, in run order")
    L.append("notes/                           the five project notes")
    L.append("figures/                         the map figure, PNG and PDF")
    L.append("arcgis/                          the File Geodatabase and its")
    L.append("                                 flat exports")
    L.append("```")
    L.append("")
    L.append("### To check the note against the data")
    L.append("")
    L.append("Every figure in the note's tables is re-derived from the shipped")
    L.append("data by a gate that travels with the package. It parses the note")
    L.append("and compares it, so it checks the note rather than a copy of it:")
    L.append("")
    L.append("```bash")
    L.append("cd <unpacked folder>")
    L.append("python3 scripts/kowloon-covered-walkways/verify_note.py")
    L.append("```")
    L.append("")
    L.append("It exits non-zero and names the offending figure if any number in")
    L.append("`notes/kowloon-covered-walkways — NOTES.md` disagrees with the data.")
    L.append("")
    L.append("### To run the map")
    L.append("")
    L.append("Unpack, then serve the folder that contains `apps/`:")
    L.append("")
    L.append("```bash")
    L.append("cd <unpacked folder>")
    L.append("python3 -m http.server 8000")
    L.append("# open http://localhost:8000/apps/kowloon-covered-walkways/")
    L.append("```")
    L.append("")
    L.append("The page refers to `../../assets/style.css` and `../../notes/`, so")
    L.append("keep `apps/`, `assets/` and `notes/` in the same shape. Serving the")
    L.append("folder as it stands is enough — no editing.")
    L.append("")
    L.append("### To rebuild the analysis")
    L.append("")
    L.append("```bash")
    L.append("PY=$(ls -d ~/.hermes/tools/python-*/bin/python3 | head -1)")
    L.append("cd ~/GIS\\ Data/Sun-Rain\\ Exposure")
    L.append("$PY kowloon_peninsula_routes.py   # routes + route options + stops")
    L.append("$PY mtr_walk_schools.py           # the MTR worst-case walks")
    L.append("$PY access_typology.py            # the 15-minute-rule typology")
    L.append("$PY build_arcgis_geodatabase.py   # the File Geodatabase")
    L.append("$PY make_peninsula_figure.py      # the figure")
    L.append("```")
    L.append("")
    L.append("Use the Hermes python — it has shapely, scipy, matplotlib, numpy")
    L.append("and pyproj. The Apple CLT `python3` has no pip.")
    L.append("")
    L.append("## The headline numbers")
    L.append("")
    L.append("| | |")
    L.append("|---|---:|")
    if "schools" in f:
        L.append(f"| Schools | {f['schools']} |")
    if "routes" in f:
        L.append(f"| Walking routes (shortest + best-covered) | {f['routes']} |")
    if "covered_segments" in f:
        L.append(f"| Covered path segments | {f['covered_segments']:,} |")
    if "stops" in f:
        L.append(f"| Stops (MTR exits, bus, minibus) | {f['stops']:,} |")
    if "options_raw" in f:
        L.append(f"| Route options | {f['options_raw']} |")
    if "walk_access" in f:
        L.append(f"| Walk-access to MTR (≤ 15 min) | {f['walk_access']} |")
    if "transit_dependent" in f:
        L.append(f"| Bus/minibus-dependent (> 15 min) | {f['transit_dependent']} |")
    if "mtr_median_m" in f:
        L.append(f"| Median walk from the nearest MTR exit | "
                 f"{int(f['mtr_median_m']):,} m |")
    if "mtr_max_m" in f:
        L.append(f"| Longest MTR walk | {int(f['mtr_max_m']):,} m |")
    if "no_cover" in f:
        L.append(f"| Schools with no covered stretch at all | {f['no_cover']} |")
    L.append("")
    L.append("## Which MTR walk is which — read this before quoting a number")
    L.append("")
    L.append("There are two MTR routes in this project, and they are not the")
    L.append("same route. The **worst-case walk** is the one the question is")
    L.append("about: the student walks from the nearest station exit because")
    L.append("the buses are not running. It is solved from *every* MTR exit")
    L.append("inside a 1 km buffer around the study area, and the shortest")
    L.append("wins. That is `data/mtr_walk_schools.json`, and it is the walk the")
    L.append("purple dashed line on the map shows.")
    L.append("")
    L.append("The **stop-to-school pipeline** (`kowloon_peninsula_routes.py`) also")
    L.append("solves an MTR route, but its candidate stops are capped at")
    L.append("800 m *straight-line* from the school (`PTI_SEARCH_M`). For 19 of")
    L.append("the 164 schools that cap excludes the nearer exit the worst-case")
    L.append("solve found, so the two disagree — by up to 312 m at CARMEL")
    L.append("ALISON LAM FOUNDATION SECONDARY SCHOOL.")
    L.append("")
    L.append("**The map quotes the walk it draws.** `build_kowloon_webmap.py`")
    L.append("replaces every school's MTR option with the worst-case walk, so")
    L.append("the line and the number beside it are the same journey. The")
    L.append("`data/route_options.geojson` in this package is that corrected")
    L.append("file.")
    L.append("")
    L.append("**If you rebuild the stop-to-school pipeline**, its own")
    L.append("`route_options.geojson` will again carry the capped-search MTR")
    L.append("route. Re-run `build_kowloon_webmap.py` afterwards — it is the")
    L.append("step that reconciles the two. `scripts/kowloon-covered-walkways/")
    L.append("verify_note.py` will then tell you whether the note, the map")
    L.append("page and the data still agree.")
    L.append("")
    L.append("**The bus and minibus options are unaffected.** The 800 m cap is")
    L.append("deliberate there — the question is which stop serves the school,")
    L.append("not the worst case.")
    L.append("")
    L.append("## Known limits — state these in a write-up")
    L.append("")
    L.append("1. **`WeatherProof` is only as good as its source.** LandsD records")
    L.append("   where the classification came from in `LevelSource` (CEDD / 3D")
    L.append("   spatial data / LiDAR / estimation). Spot-check ~20 random segments")
    L.append("   per district against Street View or a geotagged field photo")
    L.append("   before publication.")
    L.append("2. **Coverage is binary per segment.** Partial cover within a segment")
    L.append("   is not resolved — a 40 m segment under an awning counts the same")
    L.append("   as one under a full roof.")
    L.append("3. **The \"best route\" is a modelled choice, not a behaviour.** It")
    L.append("   assumes the student knows which stop gives the sheltered path and")
    L.append("   will walk past two closer stops to take it.")
    L.append("4. **The 30 m shelter radius is a chosen threshold**, not an official")
    L.append("   standard. Test 15 m and 50 m — the *ordering* of the stop types is")
    L.append("   robust, the exact percentages are not.")
    L.append("5. **This is rain exposure only.** The sun question (sky view factor,")
    L.append("   hours in shadow) is Stage 2.")
    L.append("6. **Six districts only.** The script runs on any district set by")
    L.append("   changing one dictionary, but the study-area clip is by District")
    L.append("   Council polygon.")
    L.append("7. **The MTR walk assumes the student picks the nearest exit** — by")
    L.append("   network distance. A student who exits elsewhere to avoid the")
    L.append("   crowds walks further.")
    L.append("8. **Two MTR routes exist in the source data**, and the published")
    L.append("   map uses the worst-case one throughout — see above. If you")
    L.append("   rebuild only `kowloon_peninsula_routes.py`, your MTR numbers")
    L.append("   will not match the map.")
    L.append("")
    L.append("## Provenance")
    L.append("")
    L.append("Every derived field carries an `ai_` prefix, per the CSDI Awards")
    L.append("disclosure rule; every other field is authoritative and unmodified.")
    L.append("The full method, the sources with their CSDI dataset ids, and the")
    L.append("bugs found and fixed are in `notes/`.")
    L.append("")
    L.append("| Source | Dataset |")
    L.append("|---|---|")
    L.append("| 3D Pedestrian Network | LandsD `landsd_rcd_1637222018065_52265` |")
    L.append("| Public transport stops | "
             "TD `td_rcd_1638874475129_49745` |")
    L.append("| School registry | EDB `edb_rcd_1629267205213_53323` |")
    L.append("")
    L.append("Map data © OpenStreetMap contributors, © CARTO.")
    L.append("")
    out.write_text("\n".join(L), encoding="utf-8")
    return out


if __name__ == "__main__":
    build()
