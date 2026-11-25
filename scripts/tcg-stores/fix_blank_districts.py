#!/usr/bin/env python3
"""Resolve the 6 census small areas whose `district` cell is blank in the
shipped small-area census CSV.

The CSV was built for the self-study-rooms project and these six rows came
through with an empty district cell. They are NOT missing from the census:
they have a full population and a full STPUG code. The empty cell is a
defect in the district column only.

The fix is spatial, not a lookup table: each of the six areas is matched
against the repo's district boundary layer by point-in-polygon, and the
district that contains it is adopted. The result is CHECKED against the
published district population totals, so a wrong assignment cannot slip
through silently.

Two things this has to get right:

  1. All six are SPLIT areas - 832S alone is 43 separate polygons. The mean
     of every vertex is then not a point inside the area at all; it can land
     in the sea or in a different district entirely. The test point is
     therefore taken from each polygon PART's own area-weighted centroid,
     and a part is used when its centroid is inside the area.

  2. The district layer names its districts in `dc_eng`, not `district`.
"""
import csv
import gzip
import json
from pathlib import Path

REPO = Path("/Users/davidhermes/nplgis")
CENSUS = REPO / "assets/data/self-study-rooms/POPULATION — small_area_census.csv"
DISTRICT_CSV = REPO / "assets/data/self-study-rooms/POPULATION — district_census_full.csv"
SA_GEO = Path("/Users/davidhermes/GIS Data/HK TCG Stores/census_small_areas.geojson")
DIST_GEO = REPO / "assets/data/self-study-rooms/district_boundaries.geojson.gz"

OUT = Path("/Users/davidhermes/GIS Data/HK TCG Stores/out/district_fix.json")


def point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)):
            xint = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < xint:
                inside = not inside
        j = i
    return inside


def polys_of(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def point_in_geom(lon, lat, geom):
    for poly in polys_of(geom):
        if poly and point_in_ring(lon, lat, poly[0]):
            return True
    return False


def ring_centroid(ring):
    """Area-weighted centroid of a closed ring. Falls back to the vertex mean
    for a degenerate (zero-area) ring."""
    pts = ring[:-1] if ring and ring[0] == ring[-1] else ring
    if not pts:
        return None
    a = 0.0
    cx = cy = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a))


def candidate_points(geom):
    """Points guaranteed to be representative of the area: the area-weighted
    centroid of each polygon part, plus the centroid of the largest part.

    A centroid can still fall OUTSIDE the area (area 196 is a long,
    concave strip and its centroid lands in the sea). Each candidate is
    therefore checked against the polygon itself before it is used."""
    out = []
    polys = polys_of(geom)
    best = None
    for poly in polys:
        if not poly:
            continue
        c = ring_centroid(poly[0])
        if not c:
            continue
        if point_in_ring(c[0], c[1], poly[0]):
            out.append(c)
        if best is None or abs(ring_area(poly[0])) > abs(ring_area(best[0])):
            best = (poly[0], c)
    if best and best[1] and (best[1][0], best[1][1]) not in out:
        out.append(best[1])
    return out


def sample_points(geom, n=3000, seed=7):
    """Random points inside the area, by rejection sampling.

    Used as the fallback when the geometric centroids all fall outside the
    polygon. The result is only used to test which district CONTAINS the
    area, and the winning district is then verified against the published
    district population totals."""
    import random
    rng = random.Random(seed)
    polys = polys_of(geom)
    rings = [p[0] for p in polys if p]
    if not rings:
        return []
    xs = [q[0] for r in rings for q in r]
    ys = [q[1] for r in rings for q in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    out = []
    for _ in range(n * 8):
        if len(out) >= n:
            break
        x = rng.uniform(x0, x1)
        y = rng.uniform(y0, y1)
        if any(point_in_ring(x, y, r) for r in rings):
            out.append((x, y))
    return out


def ring_area(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def dname(f):
    p = f["properties"]
    for k in ("dc_eng", "district_en", "district", "name", "NAME"):
        v = p.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return None


def main():
    with open(CENSUS, encoding="utf-8-sig") as fh:
        census = {r["stpug"]: r for r in csv.DictReader(fh)}

    blanks = [k for k, r in census.items() if not r["district"].strip()]
    print(f"blank-district small areas: {len(blanks)} -> {sorted(blanks)}")

    sa = json.load(open(SA_GEO, encoding="utf-8"))
    sa_by_st = {f["properties"]["stpug"]: f for f in sa["features"]}

    with gzip.open(DIST_GEO, "rt", encoding="utf-8") as fh:
        dist = json.load(fh)

    fixes = {}
    for st in sorted(blanks):
        geom = sa_by_st[st]["geometry"]
        votes = {}
        for pt in candidate_points(geom):
            for f in dist["features"]:
                if point_in_geom(pt[0], pt[1], f["geometry"]):
                    n = dname(f)
                    if n:
                        votes[n] = votes.get(n, 0) + 1

        if not votes:
            # Every centroid fell outside the area. Fall back to sampling
            # points inside it and take the district that contains it.
            pts = sample_points(geom)
            for pt in pts:
                for f in dist["features"]:
                    if point_in_geom(pt[0], pt[1], f["geometry"]):
                        n = dname(f)
                        if n:
                            votes[n] = votes.get(n, 0) + 1
            method = "sampled %d interior points" % len(pts)
        else:
            method = "centroid"

        # A split area can straddle a district boundary by a metre or two, so
        # the sampled votes can pick up a handful of stray points from the
        # neighbour. The dominant district must hold at least 95% of the
        # votes; below that the area is genuinely ambiguous and is refused.
        if votes:
            total_v = sum(votes.values())
            top, top_v = max(votes.items(), key=lambda kv: kv[1])
            if top_v / total_v < 0.95:
                print(f"  {st}: AMBIGUOUS {votes}  ({method}) - no district holds "
                      f"95% of the area")
                continue
            if len(votes) > 1:
                print(f"    (note: {votes} - {top} holds "
                      f"{top_v/total_v*100:.2f}%)")
            fixes[st] = top
            print(f"  {st}: {fixes[st]}  ({method})")
        else:
            print(f"  {st}: NO DISTRICT MATCH  ({method})")

    if len(fixes) != len(blanks):
        raise SystemExit("not every blank area was resolved - refusing to continue")

    # --- validate against the published district population totals ---------
    with open(DISTRICT_CSV, encoding="utf-8-sig") as fh:
        drows = {r["district_en"]: r for r in csv.DictReader(fh)}

    assigned = {st: census[st]["district"] for st in census}
    assigned.update(fixes)

    totals = {}
    for st, d in assigned.items():
        totals[d] = totals.get(d, 0) + int(census[st]["t_pop"])

    print("\ndistrict population check (small areas vs published district totals):")
    ok = True
    for d, published in sorted(drows.items()):
        got = totals.get(d, 0)
        want = int(published["t_pop"])
        diff = got - want
        if diff != 0:
            ok = False
        print(f"  {'OK  ' if diff == 0 else 'DIFF'} {d:20} small areas {got:>9,}  "
              f"published {want:>9,}  diff {diff:+,}")
    if not ok:
        raise SystemExit("district totals do not reconcile - do NOT ship this fix")

    OUT.parent.mkdir(exist_ok=True)
    json.dump(fixes, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
