#!/usr/bin/env python3
"""Build the mall floor-plate 3D dataset for the Festival Walk viewer.

Each mall floor is drawn as a thin, glass-like horizontal sheet. Crucially the
sheets are NOT all the same shape: every floor's sheet is derived from that
floor's OWN pedestrian-route network (CSDI), buffered outwards a little. Real
floors of a shopping mall have different retail layouts, and using one
identical footprint for all seven levels would make them stack invisibly into
a single slab when seen from above.

Output: apps/festival-walk-3d/data/buildings_3d.geojson
        apps/festival-walk-3d/data/floor_labels.json

Heights are schematic (5.5 m per floor, from the CSDI published floor levels);
the vertical display scale is applied in the viewer, not here.
"""
import json
import math
import os
import re
import sys

from shapely.geometry import MultiLineString, LineString, Point as ShPoint, shape
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "apps", "festival-walk-3d", "data")

STOREY_M = 5.5
GROUND_M = 58.0

# Mall footprint (GeoInfo LSD B1K_Bldg, BuildingID 1108222840 / 又一城).
MALL_GEOJSON = os.path.join(
    "/Users/davidhermes/GIS Data/GeoInfo Map/raw/rgeo_highlight_d00/004_B1K_Bldg.geojson.gz")

# floors: (id, zh, en, height_m, colour, has_routes)
FLOORS = [
    ("festival_walk_MTR_Level", "港鐵層", "MTR Level", 0.0, "#f5a524", True),
    ("festival_walk_LG2",       "低層地下二樓", "LG2", 5.5, "#ff6b9d", True),
    ("festival_walk_LG1",       "低層地下一樓", "LG1", 11.0, "#3fe0d0", True),
    ("festival_walk_G",         "地下", "G", 16.5, "#7c8cff", True),
    ("festival_walk_UG",        "高層地下", "UG", 22.0, "#8ce99a", True),
    ("festival_walk_1F",        "一樓", "1/F", 27.5, "#c8a2ff", False),
    ("festival_walk_2F",        "二樓", "2/F", 33.0, "#ff9f6e", False),
]


def m_per_deg(lat):
    return 110574.0


def load_routes(path):
    with open(path, encoding="utf-8") as fh:
        fc = json.load(fh)
    lines = []
    for ft in fc.get("features", []):
        g = ft.get("geometry")
        if not g:
            continue
        t = g.get("type")
        if t == "MultiLineString":
            lines += [LineString(c) for c in g["coordinates"]]
        elif t == "LineString":
            lines.append(LineString(g["coordinates"]))
    return lines


def shrink(geom, factor):
    """Scale a polygon toward its own centroid."""
    from shapely.ops import transform
    c = geom.centroid
    return transform(
        lambda x, y, z=None: (c.x + (x - c.x) * factor,
                              c.y + (y - c.y) * factor),
        geom)


def to_mp(geom):
    from shapely.ops import transform
    lon0, lat0 = geom.centroid.x, geom.centroid.y
    kx = m_per_deg(lat0) * math.cos(math.radians(lat0))
    ky = m_per_deg(lat0)
    return transform(lambda x, y, z=None: (x * kx, y * ky), geom)


def from_mp(geom, lon0, lat0):
    from shapely.ops import transform
    kx = m_per_deg(lat0) * math.cos(math.radians(lat0))
    ky = m_per_deg(lat0)
    return transform(lambda x, y, z=None: (x / kx, y / ky), geom)


def main():
    features = []
    labels = []

    # ---- the mall footprint ------------------------------------------------
    mall_geom = None
    if os.path.exists(MALL_GEOJSON):
        import gzip
        with gzip.open(MALL_GEOJSON, "rt", encoding="utf-8") as fh:
            fc = json.load(fh)
        for ft in fc.get("features", []):
            pr = ft.get("properties", {})
            if str(pr.get("CHINESEDISPLAYNAME", "")).strip() == "又一城":
                mall_geom = shape(ft["geometry"])
                break
    if mall_geom is None:
        print("mall footprint not found; falling back to route union", file=sys.stderr)

    retail_envelope = None
    for fid, zh, en, h, colour, has_routes in FLOORS:
        path = os.path.join(DATA, fid + ".geojson")
        sheet = None
        routes = []
        if os.path.exists(path):
            routes = load_routes(path)
            if routes:
                u = MultiLineString([list(r.coords) for r in routes])
                # Buffer each floor's own routes by 14 m so the sheet reads as
                # the floor's own extent rather than the whole mall.
                try:
                    mp = to_mp(u)
                    sheet = from_mp(mp.buffer(14.0, cap_style="flat", join_style="round"),
                                    u.centroid.x, u.centroid.y)
                except Exception as e:  # pragma: no cover
                    print(f"buffer failed for {fid}: {e}", file=sys.stderr)
                    sheet = None

        if sheet is None or sheet.is_empty:
            # No published route data for this floor (1/F, 2/F). Using the WHOLE
            # mall footprint here would make the top of the stack the widest
            # plate, which from an oblique camera hides every floor below it.
            # Instead, use the G floor's route-derived extent -- the largest
            # published floor, i.e. the mall's retail envelope -- inset
            # slightly, because a mall's upper floors are normally a little
            # smaller than its ground floor.
            if retail_envelope is None:
                print(f"no footprint available for {fid}", file=sys.stderr)
                continue
            sheet = retail_envelope
            if not has_routes:
                inset = 0.94 if en == "1/F" else 0.88
                sheet = shrink(sheet, inset)

        # Simplify a touch so the extruded edge is not absurdly jagged.
        sheet = sheet.simplify(0.0000125, preserve_topology=True)
        if sheet.geom_type == "Polygon":
            polys = [sheet]
        else:
            polys = [g for g in sheet.geoms if g.geom_type == "Polygon"]

        for poly in polys:
            # Ignore slivers: a stray speck adds a plate that reads as a
            # rendering glitch rather than a floor. The area is in square
            # degrees, so convert to square metres before comparing.
            if poly.is_empty:
                continue
            kx = 111320 * math.cos(math.radians(poly.centroid.y))
            ky = 110574.0
            area_m2 = poly.area * kx * ky
            if area_m2 < 400:
                continue
            ring = list(poly.exterior.coords)  # noqa: E501
            if len(ring) < 4:
                continue
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            features.append({
                "type": "Feature",
                "properties": {
                    "name": "又一城",
                    "zh": zh,
                    "en": en,
                    "role": "floor_plate",
                    "floor_id": fid,
                    "height_m": h,
                    "plate_thickness_m": 1.2,
                    "storey_m": STOREY_M,
                    "colour": colour,
                    "has_routes": has_routes,
                    "schematic": True,
                    "area_m2": round(area_m2, 1),
                    "source": ("floor extent derived from this floor's own CSDI "
                               "pedestrian routes (14 m buffer); height from "
                               "CSDI published floor levels (5.5 m schematic storey)"),
                },
                "geometry": {"type": "Polygon", "coordinates": [[list(c) for c in ring]]},
            })

        # The biggest published floor defines the mall's retail envelope.
        if has_routes and sheet is not None and not sheet.is_empty:
            if retail_envelope is None or sheet.area > retail_envelope.area:
                retail_envelope = sheet

        # ---- label anchor: this floor's own network centroid ----------------
        anchor = None
        if routes:
            c = MultiLineString([list(r.coords) for r in routes]).centroid
            anchor = [round(c.x, 6), round(c.y, 6)]
        else:
            c = sheet.centroid
            anchor = [round(c.x, 6), round(c.y, 6)]
        labels.append({
            "id": fid, "zh": zh, "en": en, "height": h, "colour": colour,
            "anchor": {"lon": anchor[0], "lat": anchor[1]},
            "count": len(routes),
        })

    out = {
        "type": "FeatureCollection",
        "features": features,
    }

    # The scene's camera target is the centre of the whole plate stack. Write it
    # into the app so the camera and the geometry can never drift apart.
    app = os.path.join(ROOT, "apps", "festival-walk-3d", "index.html")
    if features:
        allx = [c[0] for f in features for c in f["geometry"]["coordinates"][0]]
        ally = [c[1] for f in features for c in f["geometry"]["coordinates"][0]]
        cx = (min(allx) + max(allx)) / 2
        cy = (min(ally) + max(ally)) / 2
        with open(app, encoding="utf-8") as fh:
            html = fh.read()
        new_centre = f"const CENTRE = [{cx:.6f}, {cy:.6f}];"
        html = re.sub(r"const CENTRE = \[[^\]]*\];", new_centre, html, count=1)
        with open(app, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"camera centre -> {cx:.6f}, {cy:.6f}")

        # Same for the per-floor label anchors: they come from each floor's own
        # route centroid, so write them into the app as well.
        anchors = {l["id"]: [l["anchor"]["lon"], l["anchor"]["lat"]] for l in labels}
        anchor_js = "const LABEL_ANCHORS = " + json.dumps(
            anchors, ensure_ascii=False, separators=(", ", ": ")) + ";"
        html = re.sub(r"const LABEL_ANCHORS = \{.*?\};", anchor_js, html, count=1, flags=re.S)
        with open(app, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"label anchors -> {len(anchors)} floors")
    with open(os.path.join(DATA, "buildings_3d.geojson"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))

    with open(os.path.join(DATA, "floor_labels.json"), "w", encoding="utf-8") as fh:
        json.dump(labels, fh, ensure_ascii=False, indent=1)

    print(f"floor plates : {len(features)} features")
    for l in labels:
        print(f"  {l['en']:10} h={l['height']:5} anchor={l['anchor']} routes={l['count']}")


if __name__ == "__main__":
    main()
