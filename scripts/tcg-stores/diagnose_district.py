#!/usr/bin/env python3
"""Assign every census small area to a district by spatial containment, and
test which assignment reconciles with the published district populations.

THE PROBLEM
    The shipped small-area census CSV has a `district` column. For 6 of its
    211 rows that column is EMPTY. And for 15 of the 18 districts the column
    does NOT add up to the published district population - with errors as
    large as 126,036 people (Kwai Tsing).

    Two candidate explanations:
      (a) the CSV's district column is wrong, or
      (b) the district boundary layer disagrees with the small-area layer.

    The test settles it by the numbers: assign all 211 areas to districts
    SPATIALLY, then sum the population. If the spatial assignment
    reconciles, the CSV's column was wrong and the boundaries are right. If
    it does not reconcile either, the two layers cover different territory
    and no district-level figure can be published.

METHOD
    A scanline rasteriser (raster.py) fills a 40 m label grid over Hong
    Kong for the districts. Each small area is rasterised on the SAME grid,
    and its district is the one holding the largest share of its cells.
"""
import csv
import gzip
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from raster import Raster, fill_raster  # noqa: E402

REPO = Path("/Users/davidhermes/nplgis")
CENSUS = REPO / "assets/data/self-study-rooms/POPULATION — small_area_census.csv"
DISTRICT_CSV = REPO / "assets/data/self-study-rooms/POPULATION — district_census_full.csv"
SA_GEO = Path("/Users/davidhermes/GIS Data/HK TCG Stores/census_small_areas.geojson")
DIST_GEO = REPO / "assets/data/self-study-rooms/district_boundaries.geojson.gz"

OUT = Path("/Users/davidhermes/GIS Data/HK TCG Stores/out")


def main():
    t0 = time.time()
    with open(CENSUS, encoding="utf-8-sig") as fh:
        census = {r["stpug"]: r for r in csv.DictReader(fh)}
    with open(DISTRICT_CSV, encoding="utf-8-sig") as fh:
        published = {r["district_en"]: int(r["t_pop"]) for r in csv.DictReader(fh)}

    sa = json.load(open(SA_GEO, encoding="utf-8"))
    with gzip.open(DIST_GEO, "rt", encoding="utf-8") as fh:
        dist = json.load(fh)

    # ---- rasterise the districts ---------------------------------------
    r = Raster()
    names = [df["properties"]["dc_eng"] for df in dist["features"]]
    for i, df in enumerate(dist["features"]):
        fill_raster(r, df["geometry"], i)
    print(f"district raster: {r.nx} x {r.ny} cells, "
          f"{int((r.labels >= 0).sum()):,} land cells, {time.time()-t0:.1f}s")

    # ---- rasterise each small area on the same grid ---------------------
    spatial = {}
    csv_label = {}
    disagree = []
    for f in sa["features"]:
        st = f["properties"]["stpug"]
        csv_label[st] = census[st]["district"].strip()

        area_r = Raster(res=r.res, lon0=r.lon0, lon1=r.lon1,
                        lat0=r.lat0, lat1=r.lat1)
        fill_raster(area_r, f["geometry"], 0)
        mask = area_r.labels == 0
        n_in = int(mask.sum())
        if n_in == 0:
            spatial[st] = None
            continue
        vals = r.labels[mask]
        vals = vals[vals >= 0]
        if vals.size == 0:
            spatial[st] = None
            continue
        counts = np.bincount(vals, minlength=len(names))
        top = int(counts.argmax())
        spatial[st] = names[top]
        share = counts[top] / vals.size * 100
        if csv_label[st] and names[top] != csv_label[st]:
            disagree.append((st, csv_label[st], names[top], round(share, 1)))

    print(f"area raster pass: {time.time()-t0:.1f}s")

    def reconcile(labels):
        tot = {}
        for st, d in labels.items():
            if d:
                tot[d] = tot.get(d, 0) + int(census[st]["t_pop"])
        return tot

    def report(title, tot):
        print(f"\n=== {title} ===")
        print(f"  {'district':20} {'from small areas':>17} {'published':>12} {'diff':>10}")
        worst = 0
        for d, want in sorted(published.items()):
            got = tot.get(d, 0)
            diff = got - want
            worst = max(worst, abs(diff))
            print(f"  {d:20} {got:>17,} {want:>12,} {diff:>+10,}")
        print(f"  worst absolute difference: {worst:,}")
        return worst

    w_csv = report("A. the CSV's own district column", reconcile(csv_label))
    w_spa = report("B. spatial assignment from the district boundary layer",
                   reconcile(spatial))

    print(f"\nareas whose spatial district differs from the CSV label: {len(disagree)}")
    for st, c, s, share in sorted(disagree, key=lambda x: x[0]):
        print(f"  {st:7} csv={c or '(blank)':22} spatial={s:22} ({share}% of area)")

    unresolved = [st for st, d in spatial.items() if not d]
    print(f"\nareas with no district at all: {len(unresolved)} {unresolved}")

    OUT.mkdir(exist_ok=True)
    json.dump(spatial, open(OUT / "spatial_district.json", "w"), ensure_ascii=False, indent=1)
    print(f"\nCSV column worst error:  {w_csv:,}")
    print(f"spatial assignment error: {w_spa:,}")
    print(f"total {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
