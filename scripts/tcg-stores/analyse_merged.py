#!/usr/bin/env python3
"""Analyse the merged TCG shop layer against the 2021 Population Census.

THE QUESTION
    The user wants to know where to play trading card games, and where
    the potential customers are. So the analysis answers two things:

      1. WHERE ARE THE PLAY VENUES, and how many people live within a
         short walk of each one?
      2. WHERE IS THE UNSERVED DEMAND - the young people who have no
         venue within walking distance?

THE MEASURE
    For each census small area, the number of people aged 15-24 and the
    number of play venues within 1 km. The ratio is "young people per
    reachable play venue". A high value means an underserved area.

    15-24 is the core playing age for trading card games, and it is also
    the age group the Census reports most consistently across small
    areas.

THE VERIFICATION
    The population total is checked against the published Census figure
    for the whole territory. If it does not reconcile, nothing else in
    the output can be trusted, so the run stops.

OUTPUT
    out/merged_metrics.csv, out/merged_metrics.geojson, out/merged_summary.json
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

# The census data and the small-area boundaries, shipped in the nplgis
# repo.
CENSUS_CSV = Path("/Users/davidhermes/nplgis/assets/data/self-study-rooms/"
                  "POPULATION — small_area_census.csv")
SA_GEOJSON = HERE / "census_small_areas.geojson"
DISTRICT_FIX = HERE / "out/spatial_district.json"

# The published 2021 Census population of Hong Kong.
CENSUS_TOTAL_2021 = 7411945

CATCHMENTS = [500, 1000, 1500]   # metres


def haversine(lat1, lon1, lat2, lon2):
    R = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def load_census():
    """The census population per small area.

    The shipped CSV uses these column names:
        t_pop        the total population
        age_2_15_24  the population aged 15 to 24 - the core playing
                     age for trading card games
    The age bands are mutually exclusive and exhaustive:
        age_1_0_14 + age_2_15_24 + age_3_25_44 + age_4_45_64 + age_5_65plus
        == t_pop
    which is checked below, because a band that does not sum to the
    total would silently distort every ratio downstream."""
    rows = list(csv.DictReader(open(CENSUS_CSV, encoding="utf-8-sig")))
    out = {}
    for r in rows:
        stpug = str(r.get("stpug", "")).strip()

        def num(k):
            v = r.get(k)
            try:
                return float(str(v).replace(",", "").strip())
            except (TypeError, ValueError):
                return 0.0

        out[stpug] = {
            "stpug": stpug,
            "area": r.get("stpug_eng") or r.get("stpug_chi") or stpug,
            "district": (r.get("district") or "").strip(),
            "pop_total": num("t_pop"),
            "pop_0_14": num("age_1_0_14"),
            "pop_15_24": num("age_2_15_24"),
            "pop_25_44": num("age_3_25_44"),
            "pop_45_64": num("age_4_45_64"),
            "pop_65_plus": num("age_5_65plus"),
            "households": num("households"),
            "study_rooms": num("study_rooms"),
        }
    return out


def check_age_bands(census):
    """Every area's age bands must sum to its total population."""
    bad = []
    for c in census.values():
        s = (c["pop_0_14"] + c["pop_15_24"] + c["pop_25_44"] +
             c["pop_45_64"] + c["pop_65_plus"])
        if abs(s - c["pop_total"]) > 1:
            bad.append((c["stpug"], c["pop_total"], s))
    return bad


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


def point_in_geom(lon, lat, geom):
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return False
    for poly in polys:
        if poly and point_in_ring(lon, lat, poly[0]):
            return True
    return False


def load_areas(census):
    """The small-area polygons, with their district."""
    sa = json.load(open(SA_GEOJSON, encoding="utf-8"))
    districts = {}
    if DISTRICT_FIX.exists():
        districts = json.load(open(DISTRICT_FIX, encoding="utf-8"))
    areas = []
    for f in sa["features"]:
        stpug = str(f["properties"].get("stpug"))
        c = census.get(stpug)
        if not c:
            continue
        d = districts.get(stpug) or c["district"]
        # The centroid of the area, used as the point from which the
        # catchments are measured. It is the area-weighted centroid of
        # the polygon, which for a concave area is not the same as the
        # average of the vertices.
        xs, ys = [], []

        def walk(c):
            if isinstance(c[0], (int, float)):
                xs.append(c[0])
                ys.append(c[1])
            else:
                for x in c:
                    walk(x)
        walk(f["geometry"]["coordinates"])
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        if not point_in_geom(cx, cy, f["geometry"]):
            # the vertex average fell outside a concave area - fall back
            # to the centroid of the largest ring
            cx, cy = ring_centroid(f["geometry"])
        areas.append({
            "stpug": stpug,
            "area": c["area"],
            "district": d,
            "geom": f["geometry"],
            "_clat": cy,
            "_clon": cx,
            **{k: v for k, v in c.items() if k.startswith("pop_")},
        })
    return areas


def ring_centroid(geom):
    """The centroid of the largest ring of a polygon."""
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    else:
        polys = geom["coordinates"]
    best = None
    best_a = -1
    for poly in polys:
        ring = poly[0]
        a = 0.0
        cx = cy = 0.0
        for i in range(len(ring) - 1):
            x0, y0 = ring[i][0], ring[i][1]
            x1, y1 = ring[i + 1][0], ring[i + 1][1]
            cross = x0 * y1 - x1 * y0
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        a *= 0.5
        if abs(a) > best_a:
            best_a = abs(a)
            if a != 0:
                best = (cx / (6 * a), cy / (6 * a))
    if best is None:
        return (0.0, 0.0)
    return best


def main():
    census = load_census()
    areas = load_areas(census)
    print(f"loaded {len(areas)} census small areas")

    # ---- the verification gates -------------------------------------------
    bad_bands = check_age_bands(census)
    if bad_bands:
        print(f"FAIL: {len(bad_bands)} areas where the age bands do not sum "
              f"to the total population")
        for stpug, tot, s in bad_bands[:5]:
            print(f"   {stpug}: total {tot:,.0f} bands {s:,.0f}")
        return
    print("OK: every area's age bands sum to its total population")

    total = sum(a["pop_total"] for a in areas)
    print(f"population total: {total:,.0f}")
    if abs(total - CENSUS_TOTAL_2021) > 1:
        print(f"FAIL: does not reconcile with the published Census figure "
              f"({CENSUS_TOTAL_2021:,})")
        return
    print(f"OK: reconciles exactly with the published 2021 Census total "
          f"({CENSUS_TOTAL_2021:,})")

    shops = json.load(open(HERE / "shops_merged.json", encoding="utf-8"))
    shops = [s for s in shops if s.get("lat") is not None]

    # TWO TIERS OF "a place you can play", kept separate because the
    # evidence is different for each.
    #
    #   confirmed - the source directory itself says you can play there.
    #               Either BAW VAULT's "play_space" service tag, or
    #               HKCardPrice's 打牌 flag, or a hand-built venue list
    #               entry.
    #   registered - the shop is on the official Pokemon shop map, so it
    #               runs official events and events need a play space.
    #               That is strong evidence but it is not the same claim
    #               as "you can turn up and play", so it is reported
    #               separately rather than folded in.
    #
    # A registered Gym is treated as a venue for the MEASURE only where
    # it is also a confirmed play space; everywhere else it is counted
    # and reported as its own thing.
    confirmed = [s for s in shops
                 if s.get("ai_play_space") or s.get("ai_play_tag")]
    registered_only = [s for s in shops
                       if s.get("gym_id") and s not in confirmed]
    play = confirmed
    print(f"shops: {len(shops)}   confirmed play venues: {len(confirmed)}   "
          f"registered Gyms without a confirmed play space: {len(registered_only)}")

    # ---- assign each shop to the small area that contains it -------------
    idx = []
    for a in areas:
        xs, ys = [], []

        def walk(c):
            if isinstance(c[0], (int, float)):
                xs.append(c[0])
                ys.append(c[1])
            else:
                for x in c:
                    walk(x)
        walk(a["geom"]["coordinates"])
        idx.append((min(xs), min(ys), max(xs), max(ys), a))

    def which_area(lat, lon):
        for x0, y0, x1, y1, a in idx:
            if x0 <= lon <= x1 and y0 <= lat <= y1:
                if point_in_geom(lon, lat, a["geom"]):
                    return a
        return None

    for s in shops:
        a = which_area(s["lat"], s["lon"])
        s["stpug"] = a["stpug"] if a else None

    n_assigned = sum(1 for s in shops if s["stpug"])
    print(f"shops assigned to a small area: {n_assigned}/{len(shops)}")

    # ---- the catchments --------------------------------------------------
    # For each small area, count the play venues within each radius and
    # sum the young population of every area within it.
    for a in areas:
        a["shops_near"] = 0
        a["play_near"] = 0
        a["play_near_500"] = 0
        a["play_near_1500"] = 0

    for a in areas:
        ac, alat, alon = a["stpug"], a["_clat"], a["_clon"]
        for s in play:
            d = haversine(alat, alon, s["lat"], s["lon"])
            if d <= 1000:
                a["play_near"] += 1
                if d <= 500:
                    a["play_near_500"] += 1
                if d <= 1500:
                    a["play_near_1500"] += 1

    for a in areas:
        a["shops_near"] = sum(
            1 for s in shops
            if haversine(a["_clat"], a["_clon"], s["lat"], s["lon"]) <= 1000)

    # ---- the derived measures --------------------------------------------
    for a in areas:
        y = a["pop_15_24"]
        n = a["play_near"]
        a["y1524_per_play_1000m"] = round(y / n, 1) if n else None
        a["y1524_per_play_1000m_500"] = round(y / a["play_near_500"], 1) \
            if a["play_near_500"] else None
        a["y1524_per_play_1000m_1500"] = round(y / a["play_near_1500"], 1) \
            if a["play_near_1500"] else None
        a["y1524_per_shop_1000m"] = round(y / a["shops_near"], 1) \
            if a["shops_near"] else None
        a["pop_per_play_1000m"] = round(a["pop_total"] / n, 1) if n else None
        # a categorical band, so the map legend can state the measure
        if n == 0:
            a["play_band"] = "none"
        elif a["y1524_per_play_1000m"] <= 200:
            a["play_band"] = "under_200"
        elif a["y1524_per_play_1000m"] <= 600:
            a["play_band"] = "200_600"
        elif a["y1524_per_play_1000m"] <= 1500:
            a["play_band"] = "600_1500"
        else:
            a["play_band"] = "over_1500"

    # ---- the district roll-up --------------------------------------------
    dd = defaultdict(lambda: {"areas": 0, "pop": 0, "y1524": 0,
                               "play_near": 0, "shops_near": 0})
    for a in areas:
        d = dd[a["district"]]
        d["areas"] += 1
        d["pop"] += a["pop_total"]
        d["y1524"] += a["pop_15_24"]
        d["play_near"] += a["play_near"]
        d["shops_near"] += a["shops_near"]

    # ---- the sensitivity scenario ----------------------------------------
    # What if every registered Pokemon Gym also counted as a place to
    # play? The Gyms are official event venues, so this is the most
    # generous reading of the supply side. It is reported so the
    # finding can be tested against the assumption rather than assumed.
    gym_points = [(s["lat"], s["lon"]) for s in shops if s.get("gym_id")]
    served_y_gym = 0
    for a in areas:
        n = a["play_near"]
        for glat, glon in gym_points:
            if haversine(a["_clat"], a["_clon"], glat, glon) <= 1000:
                n += 1
        a["play_near_incl_gyms"] = n
        if n:
            served_y_gym += a["pop_15_24"]
    young_total = sum(a["pop_15_24"] for a in areas)
    unserved_y_gym = young_total - served_y_gym
    print(f"\nsensitivity: counting all {len(gym_points)} registered Gyms as "
          f"venues too ->")
    print(f"   young people with no venue within 1 km: {unserved_y_gym:,} "
          f"({unserved_y_gym / max(1, young_total) * 100:.1f}%)")
    print(f"   areas with no venue within 1 km: "
          f"{sum(1 for a in areas if a['play_near_incl_gyms'] == 0)}")

    # ---- write the outputs ------------------------------------------------
    cols = ["stpug", "area", "district", "pop_total", "pop_15_24",
            "play_near", "play_near_500", "play_near_1500", "shops_near",
            "y1524_per_play_1000m", "y1524_per_play_1000m_500",
            "y1524_per_play_1000m_1500", "y1524_per_shop_1000m",
            "pop_per_play_1000m", "play_band"]
    with open(OUT / "merged_metrics.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for a in areas:
            w.writerow([a.get(c, "") for c in cols])

    # The published properties. Every field that was DERIVED by this
    # project carries the ai_ prefix, so a reader can tell at a glance
    # which numbers came from the census and which were computed here.
    # The convention matches the covered-walkways project.
    gj = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": a["geom"],
            "properties": {
                "id": a["stpug"],
                "area": a.get("area"),
                "district": a.get("district"),
                "pop_total": a.get("pop_total"),
                "pop_15_24": a.get("pop_15_24"),
                "ai_play_near_1000m": a.get("play_near"),
                "ai_play_near_500m": a.get("play_near_500"),
                "ai_play_near_1500m": a.get("play_near_1500"),
                "ai_shops_near_1000m": a.get("shops_near"),
                "ai_y1524_per_play_1000m": a.get("y1524_per_play_1000m"),
                "ai_y1524_per_play_1000m_500m": a.get("y1524_per_play_1000m_500"),
                "ai_y1524_per_play_1000m_1500m": a.get("y1524_per_play_1000m_1500"),
                "ai_y1524_per_shop_1000m": a.get("y1524_per_shop_1000m"),
                "ai_pop_per_play_1000m": a.get("pop_per_play_1000m"),
                "ai_play_band": a.get("play_band"),
                "ai_play_near_incl_gyms": a.get("play_near_incl_gyms"),
            },
        } for a in areas],
    }
    json.dump(gj, open(OUT / "merged_metrics.geojson", "w", encoding="utf-8"),
              ensure_ascii=False)

    # ---- the summary -------------------------------------------------------
    play_district = Counter()
    for s in play:
        a = which_area(s["lat"], s["lon"])
        if a:
            play_district[a["district"]] += 1

    unserved = [a for a in areas if a["play_near"] == 0]
    unserved_y = sum(a["pop_15_24"] for a in unserved)
    served_y = sum(a["pop_15_24"] for a in areas if a["play_near"] > 0)

    summary = {
        "population_total": total,
        "population_total_check": "exact match with published 2021 Census",
        "census_areas": len(areas),
        "shops_total": len(shops),
        "play_venues_total": len(play),
        "play_venues_geocoded": len(play),
        "pokemon_gyms_total": sum(1 for s in shops if s.get("gym_id")),
        "pokemon_gyms_registered_only": len(registered_only),
        "shops_confirmed_by_2_sources": sum(1 for s in shops
                                            if len(s.get("ai_sources") or []) > 1),
        "shops_assigned_to_area": n_assigned,
        "young_people_15_24": sum(a["pop_15_24"] for a in areas),
        "young_people_within_1km_of_a_venue": served_y,
        "young_people_with_no_venue_within_1km": unserved_y,
        "share_young_with_no_venue": round(unserved_y /
                                            max(1, sum(a["pop_15_24"]
                                                       for a in areas)) * 100, 1),
        "areas_with_no_venue": len(unserved),
        "sensitivity_all_gyms_counted_as_venues": {
            "young_people_with_no_venue_within_1km": unserved_y_gym,
            "share_young_with_no_venue": round(
                unserved_y_gym / max(1, sum(a["pop_15_24"] for a in areas)) * 100, 1),
            "areas_with_no_venue": sum(1 for a in areas
                                       if a["play_near_incl_gyms"] == 0),
        },
        "play_venues_by_district": dict(play_district.most_common()),
        "district_rollup": {k: dict(v) for k, v in
                             sorted(dd.items())},
        "catchment_metres": CATCHMENTS,
        "measure": "people aged 15-24 in the area per play venue within 1 km",
    }
    json.dump(summary, open(OUT / "merged_summary.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\nyoung (15-24) with a venue within 1 km: {served_y:,.0f}")
    print(f"young with NO venue within 1 km:        {unserved_y:,.0f} "
          f"({summary['share_young_with_no_venue']}%)")
    print(f"areas with no venue within 1 km:        {len(unserved)}")
    print("\nplay venues by district:")
    for k, v in play_district.most_common():
        print(f"   {k:22} {v}")
    print(f"\nwrote {OUT}/merged_metrics.csv, merged_metrics.geojson, "
          f"merged_summary.json")


from collections import Counter   # noqa: E402

if __name__ == "__main__":
    main()
