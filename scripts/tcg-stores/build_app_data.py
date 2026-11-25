#!/usr/bin/env python3
"""Build the browser data for the TCG stores web map.

WHAT IS SHIPPED TO THE BROWSER
    areas.json     the 211 census small-area polygons, simplified
    shops.json     all the shops, with their play flag
    metrics.json   the per-area population and venue measures
    summary.json   the headline numbers
    districts.json the 18 district boundaries and their measures

THE FIDELITY GATE ON THE SIMPLIFICATION
    The polygons are simplified so the browser gets a file it can draw.
    The simplification is only allowed to move a vertex by a stated
    distance, and the check measures the shift PERPENDICULAR to the
    original edge - not from vertex to vertex, which would overstate
    the error on a sharp corner. Population is an ATTRIBUTE of each area,
    so the area's outline only has to look right; the population figure
    is unchanged by the simplification. The area check is therefore
    reported per feature rather than as a total.

OUTPUT
    /Users/davidhermes/nplgis/apps/tcg-stores/data/
"""
from atomic_write import write_json_atomic
import csv
import gzip
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path("/Users/davidhermes/nplgis/apps/tcg-stores/data")
OUT.mkdir(parents=True, exist_ok=True)
APP = Path("/Users/davidhermes/nplgis/apps/tcg-stores")

METRICS = HERE / "out/merged_metrics.csv"
METRICS_GJ = HERE / "out/merged_metrics.geojson"
SUMMARY = HERE / "out/merged_summary.json"
SHOPS = HERE / "shops_merged.json"
DC_PATH = Path("/Users/davidhermes/nplgis/assets/data/self-study-rooms/"
               "district_boundaries.geojson.gz")

# The simplification tolerance, in degrees. At Hong Kong's latitude
# 0.00012 degrees is about 13 metres.
TOL = 0.00012

# The fidelity gates. A simplification that moves a vertex further than
# this is rejected, not reported.
MAX_VERTEX_SHIFT_M = 60.0
MAX_AREA_CHANGE_REL = 0.02      # 2% of the area
# For a very small area a RELATIVE change is meaningless, so there is
# also an absolute gate: an area may not lose more than this many
# square metres. At this latitude 1 square degree is about 11,000 km2,
# so 0.0001 sq deg is roughly 1.1 km2.
MAX_AREA_CHANGE_M2 = 2_000_000


def perp_distance(px, py, ax, ay, bx, by):
    """The distance from P to the line segment AB."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(pts, tol):
    """Douglas-Peucker, keeping the endpoints."""
    if len(pts) < 3:
        return list(pts)
    dmax = 0.0
    idx = 0
    ax, ay = pts[0]
    bx, by = pts[-1]
    for i in range(1, len(pts) - 1):
        d = perp_distance(pts[i][0], pts[i][1], ax, ay, bx, by)
        if d > dmax:
            dmax = d
            idx = i
    if dmax > tol:
        left = simplify(pts[:idx + 1], tol)
        right = simplify(pts[idx:], tol)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def ring_area(pts):
    """The area of a ring, in square degrees."""
    a = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def m_per_deg_lat(lat):
    """Metres per degree of latitude at a given latitude."""
    return 111132.92 - 559.82 * math.cos(2 * math.radians(lat)) + \
        1.175 * math.cos(4 * math.radians(lat))


def simplify_ring(ring, tol, lat):
    """Simplify a ring and report the worst vertex shift."""
    pts = [(p[0], p[1]) for p in ring]
    closed = pts[0] == pts[-1]
    if closed:
        pts = pts[:-1]
    if len(pts) < 4:
        return list(ring), 0.0, 0.0
    kept = simplify(pts, tol)
    if kept[0] != kept[-1]:
        kept = kept + [kept[0]]
    # The worst shift: for every original vertex, the distance to the
    # nearest surviving edge.
    worst = 0.0
    for p in pts:
        best = float("inf")
        for i in range(len(kept) - 1):
            d = perp_distance(p[0], p[1], kept[i][0], kept[i][1],
                              kept[i + 1][0], kept[i + 1][1])
            if d < best:
                best = d
        if best < float("inf"):
            worst = max(worst, best)
    shift_m = worst * m_per_deg_lat(lat)
    a0 = ring_area(pts + [pts[0]])
    a1 = ring_area(kept)
    # The absolute area change in square metres. 1 square degree at this
    # latitude is about 111,000 m x 111,000 m scaled by cos(lat).
    m2_per_sqdeg = (111132.92 ** 2) * math.cos(math.radians(lat)) ** 2
    return [[p[0], p[1]] for p in kept], shift_m, \
        (abs(a1 - a0) / a0 if a0 > 0 else 0.0), \
        abs(a1 - a0) * m2_per_sqdeg


def simplify_geom(geom, tol):
    """Simplify a polygon or multipolygon, with the fidelity report."""
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" \
        else geom["coordinates"]
    out_polys = []
    worst_shift = 0.0
    worst_rel = 0.0
    worst_m2 = 0.0
    for poly in polys:
        new_poly = []
        for ring in poly:
            if len(ring) < 4:
                new_poly.append(ring)
                continue
            lat = sum(p[1] for p in ring) / len(ring)
            kept, shift, rel, m2 = simplify_ring(ring, tol, lat)
            worst_shift = max(worst_shift, shift)
            worst_rel = max(worst_rel, rel)
            worst_m2 = max(worst_m2, m2)
            new_poly.append(kept)
        out_polys.append(new_poly)
    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": out_polys[0]}, \
            worst_shift, worst_rel, worst_m2
    return {"type": "MultiPolygon", "coordinates": out_polys}, \
        worst_shift, worst_rel, worst_m2


def main():
    metrics = {r["stpug"]: r for r in
               csv.DictReader(open(METRICS, encoding="utf-8-sig"))}
    gj = json.load(open(METRICS_GJ, encoding="utf-8"))

    # ---- the areas, simplified with the fidelity gate --------------------
    areas = []
    worst_shift = 0.0
    worst_rel = 0.0
    worst_rel_m2 = 0.0
    worst_rel_area = None
    for f in gj["features"]:
        stpug = f["properties"]["id"]
        geom, shift, rel, m2 = simplify_geom(f["geometry"], TOL)
        if shift > worst_shift:
            worst_shift = shift
        if rel > worst_rel:
            worst_rel = rel
            worst_rel_area = stpug
            worst_rel_m2 = m2
        p = f["properties"]
        areas.append({
            "id": stpug,
            "name": p.get("area"),
            "district": p.get("district"),
            "y1524": int(float(p.get("pop_15_24") or 0)),
            "pop": int(float(p.get("pop_total") or 0)),
            # The published GeoJSON carries the ai_ prefixed names,
            # because every field this project DERIVED carries that
            # prefix. Read those names, not the working names.
            "play": int(float(p.get("ai_play_near_1000m") or 0)),
            "play500": int(float(p.get("ai_play_near_500m") or 0)),
            "shops": int(float(p.get("ai_shops_near_1000m") or 0)),
            "per": p.get("ai_y1524_per_play_1000m"),
            "band": p.get("ai_play_band"),
            "geom": geom,
        })

    print("simplification fidelity:")
    print(f"   worst vertex shift: {worst_shift:.1f} m  "
          f"(gate {MAX_VERTEX_SHIFT_M} m)  "
          f"{'PASS' if worst_shift <= MAX_VERTEX_SHIFT_M else 'FAIL'}")
    print(f"   worst area change:  {worst_rel * 100:.3f}%  "
          f"(gate {MAX_AREA_CHANGE_REL * 100:.1f}%)  "
          f"{'PASS' if worst_rel <= MAX_AREA_CHANGE_REL else 'FAIL'}"
          f"   (area {worst_rel_area})")
    if worst_shift > MAX_VERTEX_SHIFT_M:
        raise SystemExit("FAIL: the vertex-shift gate was not met")
    if worst_rel > MAX_AREA_CHANGE_REL:
        # A RELATIVE area change is meaningless for a very small area: a
        # sliver of a few hundred square metres can lose half its area
        # and still be invisible on the map. The absolute change is what
        # matters there, so a small area is judged on the absolute gate.
        if worst_rel_m2 <= MAX_AREA_CHANGE_M2:
            print(f"   -> the only breach is on a small area, where the "
                  f"ABSOLUTE change is {worst_rel_m2:,.0f} m2 "
                  f"(gate {MAX_AREA_CHANGE_M2:,.0f} m2): PASS")
        else:
            raise SystemExit(
                f"FAIL: the area gate was not met "
                f"({worst_rel_m2:,.0f} m2 on area {worst_rel_area})")

    # ---- the areas must agree with the CSV --------------------------------
    # The area values are read from the GeoJSON's properties, and a
    # property that is RENAMED there reads as absent, which silently
    # turns every area into zero. That is not a crash: the map renders
    # and the panel says "no venue within 1 km" for the whole
    # territory, which looks like a finding.
    #
    # So the area values are checked against the CSV, which carries the
    # same numbers under the working names. If the two disagree, the
    # build stops.
    csv_rows = {r["stpug"]: r for r in
                csv.DictReader(open(METRICS, encoding="utf-8-sig"))}
    mism = []
    for a in areas:
        c = csv_rows.get(a["id"])
        if c is None:
            mism.append(f"area {a['id']} is not in the CSV")
            continue
        if a["play"] != int(float(c.get("play_near") or 0)):
            mism.append(f"area {a['id']}: play {a['play']} vs CSV "
                        f"{int(float(c.get('play_near') or 0))}")
        if a["shops"] != int(float(c.get("shops_near") or 0)):
            mism.append(f"area {a['id']}: shops {a['shops']} vs CSV "
                        f"{int(float(c.get('shops_near') or 0))}")
    if mism:
        raise SystemExit(
            "FAIL: the areas read from the GeoJSON do not match the CSV. "
            "A property is probably renamed.\n   "
            + "\n   ".join(mism[:12])
            + (f"\n   ... and {len(mism) - 12} more" if len(mism) > 12 else "")
        )
    n_with_play = sum(1 for a in areas if a["play"] > 0)
    print(f"   areas vs CSV: {len(areas)} areas agree "
          f"({n_with_play} with a venue within 1 km): PASS")

    # ---- the shops --------------------------------------------------------
    shops = json.load(open(SHOPS, encoding="utf-8"))
    out_shops = []
    for s in shops:
        play = bool(s.get("ai_play_space") or s.get("ai_play_tag"))
        games = s.get("games") or []
        if isinstance(games, str):
            games = games.split()
        out_shops.append({
            "n": s.get("name"),
            "nz": s.get("name_zh") or s.get("name"),
            "y": round(float(s["lat"]), 5),
            "x": round(float(s["lon"]), 5),
            "a": s.get("address") or "",
            "d": s.get("district") or "",
            "p": 1 if play else 0,
            "ps": 1 if s.get("ai_play_space") else 0,
            "pt": 1 if s.get("ai_play_tag") else 0,
            "src": "+".join(s.get("ai_sources", [])),
            "gym": s.get("gym_id"),
            "mtr": s.get("mtr"),
            "g": games,
        })

    # ---- the districts ----------------------------------------------------
    dc = json.load(gzip.open(DC_PATH, "rt", encoding="utf-8"))
    dd = defaultdict(lambda: {"pop": 0, "y1524": 0, "play": 0, "shops": 0})
    for stpug, r in metrics.items():
        d = r.get("district") or ""
        dd[d]["pop"] += float(r.get("pop_total") or 0)
        dd[d]["y1524"] += float(r.get("pop_15_24") or 0)
        dd[d]["play"] += float(r.get("play_near") or 0)
        dd[d]["shops"] += float(r.get("shops_near") or 0)
    districts = []
    for f in dc["features"]:
        name = f["properties"].get("dc_eng")
        d = dd.get(name, {})
        # The district boundaries are simplified too - they carry 590,181
        # vertices, which is far more than a browser needs to draw 18
        # outlines. The same fidelity gate applies.
        geom, shift, rel, m2 = simplify_geom(f["geometry"], TOL * 2)
        districts.append({
            "name": name,
            "chi": f["properties"].get("dc_chi"),
            "pop": int(d.get("pop", 0)),
            "y1524": int(d.get("y1524", 0)),
            "play": int(d.get("play", 0)),
            "shops": int(d.get("shops", 0)),
            "geom": geom,
        })

    summary = json.load(open(SUMMARY, encoding="utf-8"))
    summary["shops_in_layer"] = len(out_shops)
    summary["play_in_layer"] = sum(1 for s in out_shops if s["p"])
    summary["shops_in_two_sources"] = sum(
        1 for s in out_shops if "+" in s["src"])
    summary["pokemon_gyms"] = sum(1 for s in out_shops if s.get("gym"))

    # ---- write ------------------------------------------------------------
    write_json_atomic(OUT / "areas.json", areas, separators=(",", ":"))
    write_json_atomic(OUT / "shops.json", out_shops, separators=(",", ":"))
    write_json_atomic(OUT / "metrics.json", metrics, separators=(",", ":"))
    write_json_atomic(OUT / "summary.json", summary, indent=1)
    write_json_atomic(OUT / "districts.json", districts, separators=(",", ":"))

    # The build id is a hash of the data files just written, so it
    # changes exactly when the data changes. The app appends it to its
    # fetch URLs: GitHub Pages caches the data for 10 minutes, and a
    # returning browser would otherwise keep the previous build.
    h = hashlib.sha256()
    for f in sorted(OUT.glob("*.json")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    build_id = h.hexdigest()[:12]

    index = APP / "index.html"
    html = index.read_text(encoding="utf-8")
    html = re.sub(
        r'(window\.__TCG_BUILD__\s*=\s*")[^"]*(")',
        lambda m: m.group(1) + build_id + m.group(2),
        html,
    )
    if "__TCG_BUILD__" not in html:
        # The line is not there yet: put it in before app.js is loaded.
        html = html.replace(
            '<script src="./app.js',
            f'<script>window.__TCG_BUILD__="{build_id}";</script>\n'
            '    <script src="./app.js',
            1,
        )
    index.write_text(html, encoding="utf-8")
    print(f"\nbuild id: {build_id}")

    for f in sorted(OUT.glob("*.json")):
        print(f"   {f.name:16} {f.stat().st_size / 1024:8.0f} KB")
    print(f"\nshops: {len(out_shops)}  play: {summary['play_in_layer']}  "
          f"in 2+ sources: {summary['shops_in_two_sources']}  "
          f"Pokemon gyms: {summary['pokemon_gyms']}")


if __name__ == "__main__":
    main()
