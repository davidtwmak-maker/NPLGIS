#!/usr/bin/env python3
"""Publish the card-game venues project into the nplgis repository.

WHAT IT WRITES
    assets/data/tcg-stores/   the data files the notes refer to
      tcg_summary.json              the headline figures
      tcg_shops_merged.json         every shop and venue, with the
                                    ai_ prefixed fields
      tcg_play_venues.json          the hand-built play venue list
      tcg_shops_hkcardprice.json    the HKCardPrice shops as geocoded
      tcg_shops_hkcardprice_directory.json   the raw directory listing
      POPULATION - tcg_small_area_metrics.csv   the small area table
      tcg_small_area_metrics.geojson  the same, as a polygon layer

    The geometry in the GeoJSON is SIMPLIFIED, with the same fidelity
    gate the browser build uses: no vertex may move more than 60 m.
    The unsimplified layer is 31 MB; the simplified one is 1.2 MB, and
    the browser can draw it.

WHY IT IS A SCRIPT AND NOT A ONE-OFF
    The published files must be re-derivable from the pipeline. A file
    that was produced by hand cannot be checked by anyone else, and the
    numbers in the notes would be unfalsifiable.

Usage:  publish_data.py
"""
from atomic_write import write_json_atomic
import csv
import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The browser build already has a tested simplifier and its fidelity
# gate. Reusing it means the published layer and the browser layer are
# simplified by the SAME code, so they cannot drift apart.
import build_app_data as B  # noqa: E402

REPO = Path("/Users/davidhermes/nplgis")
OUT = REPO / "assets/data/tcg-stores"

TOL = B.TOL           # the simplification tolerance, in degrees
MAX_SHIFT_M = 60.0    # the fidelity gate: no vertex may move further


def simplify_ring(ring, tol, lat):
    """Simplify one ring. Delegates to the browser build's tested code."""
    return B.simplify_ring(ring, tol, lat)


def simplify_geom(geom, tol):
    """Simplify a polygon or multipolygon. Delegates to the browser build."""
    g, shift, rel, m2 = B.simplify_geom(geom, tol)
    return g, (shift, rel, m2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- the summary -------------------------------------------------
    summary = json.load(open(HERE / "out/merged_summary.json", encoding="utf-8"))
    summary["published_from"] = "analyse_merged.py"
    write_json_atomic(OUT / "tcg_summary.json", summary, indent=1)

    # ---- the merged shops ---------------------------------------------
    shops = json.load(open(HERE / "shops_merged.json", encoding="utf-8"))
    write_json_atomic(OUT / "tcg_shops_merged.json", shops, indent=1)

    # ---- the play venues ----------------------------------------------
    venues = json.load(open(HERE / "play_venues_geocoded.json", encoding="utf-8"))
    write_json_atomic(OUT / "tcg_play_venues.json", venues, indent=1)

    # ---- the HKCardPrice shops -----------------------------------------
    hkp = json.load(open(HERE / "shops_hkcardprice_geocoded.json", encoding="utf-8"))
    write_json_atomic(OUT / "tcg_shops_hkcardprice.json", hkp, indent=1)
    raw_hkp = json.load(open(HERE / "raw/hkcardprice_shops.json", encoding="utf-8"))
    write_json_atomic(OUT / "tcg_shops_hkcardprice_directory.json", raw_hkp, indent=1)

    # ---- the small area metrics ----------------------------------------
    rows = list(csv.DictReader(open(HERE / "out/merged_metrics.csv",
                                    encoding="utf-8")))
    fields = list(rows[0].keys())
    with open(OUT / "POPULATION — tcg_small_area_metrics.csv", "w",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- the polygon layer, simplified ----------------------------------
    gj = json.load(open(HERE / "out/merged_metrics.geojson", encoding="utf-8"))
    worst_shift = worst_rel = worst_abs = 0.0
    out_feats = []
    for feat in gj["features"]:
        geom, (shift, rel, abs_m2) = simplify_geom(feat["geometry"], TOL)
        worst_shift = max(worst_shift, shift)
        worst_rel = max(worst_rel, rel)
        worst_abs = max(worst_abs, abs_m2)
        out_feats.append({"type": "Feature", "properties": feat["properties"],
                           "geometry": geom})
    out = {"type": "FeatureCollection", "features": out_feats}
    write_json_atomic(OUT / "tcg_small_area_metrics.geojson", out, indent=None)

    size = (OUT / "tcg_small_area_metrics.geojson").stat().st_size
    print(f"simplification fidelity (published layer):")
    print(f"   worst vertex shift: {worst_shift:.1f} m  "
          f"(gate {MAX_SHIFT_M:.0f} m)  "
          f"{'PASS' if worst_shift <= MAX_SHIFT_M else 'FAIL'}")
    print(f"   worst area change:  {worst_rel * 100:.3f}%  "
          f"absolute {worst_abs:,.0f} m2  "
          f"{'PASS' if worst_abs <= 2_000_000 else 'FAIL'}")
    print(f"   tcg_small_area_metrics.geojson  {size:,} bytes")
    print(f"\nwrote {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"   {p.name:44} {p.stat().st_size:>12,}")
    return 0 if worst_shift <= MAX_SHIFT_M else 1


if __name__ == "__main__":
    sys.exit(main())
