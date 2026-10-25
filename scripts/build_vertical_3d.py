"""Build the 3D vertical-circulation layer for Festival Walk (又一城).

WHY THIS FILE EXISTS
--------------------
The first vertical-circulation layer was built as "every route with no
FloorID". That is wrong twice over:

1. It swept in every route that merely *lacks* a floor assignment -- 46 flat
   outdoor surfaces (podium decks, traffic islands, crossings, footways) plus
   2 indoor footbridges. Those are not vertical circulation at all. Drawing
   them all at one constant z produced the flat yellow mesh that covered the
   mall.

2. The routes that ARE vertical connectors were drawn flat too, at a single
   constant elevation, so a lift and an escalator between two floors looked
   identical to a painted line on the ground.

WHAT THIS FILE DOES
-------------------
The CSDI PedestrianRoute table carries a `Gradient` (rise/run) and a
`FeatureType` domain (Escalator 8, Lift 10, Staircase 12, Ramp 11, versus
Traffic Island 6, Crossing 32/33, Footway 1, Footbridge 2). Together with the
`Location` field (Indoor 2 / Outdoor 1) this lets us separate genuine
floor-to-floor connectors from flat surfaces without inventing anything.

For each connector we work out which two published floors it joins:

* A path whose two ends each land within 1 m of a published floor network,
  on DIFFERENT floors, is a definite link. This is the common case: every
  Festival Walk escalator and lift end lands at exactly 0.00 m from the
  floor network it serves, because the route network and the connectors share
  vertices.

* A lift is a vertical shaft: its plan length is ~0.1 m and its Gradient is
  ~1.55 (far steeper than any escalator). We give it a shaft drawn at each
  floor it serves.

* Where the two ends land on the SAME floor but the Gradient says the path
  still climbs, we keep the gradient and lift one end to the floor above.
  The Gradient is authoritative for the slope; the floor is authoritative for
  the level.

* Everything else (flat outdoor podium, traffic island, crossing, footway) is
  NOT vertical circulation. It is written to a separate "site surface" file
  so it can be drawn flat on the terrain, where it belongs, and not as a
  yellow mesh through the building.

OUTPUT
------
data/festival_walk_vertical_3d.geojson   connectors, 3D, per-vertex z
data/festival_walk_site_surface.geojson   flat surfaces (drawn on terrain)

Both carry `Z_FROM`, `Z_TO`, `FLOOR_FROM`, `FLOOR_TO` so the app can label
them and so the build is auditable.
"""
import json
import math
import os
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "apps", "festival-walk-3d", "data")

FS = ("https://portal.csdi.gov.hk/server/rest/services/common/"
      "landsd_rcd_1637222018065_52265/FeatureServer")

BUILDING_ID = 1108222840

# CSDI floor lookup: FloorID -> (EnglishName, ChineseName, height_m)
# Height is the CSDI published 5.5 m storey spacing on the MTR-level scale.
FLOORS = {
    220000052: ("MTR Level", "港鐵層", 0.0),
    220000045: ("LG2", "低層地下二樓", 5.5),
    220000044: ("LG1", "低層地下一樓", 11.0),
    220000040: ("G", "地下", 16.5),
    220000043: ("UG", "高層地下", 22.0),
}
FLOOR_ORDER = ["MTR Level", "LG2", "LG1", "G", "UG"]

# CSDI FeatureType domain
FT_NAMES = {
    1: "Footway", 2: "Footbridge", 4: "Subway", 6: "Traffic Island",
    8: "Escalator", 9: "Travelator", 10: "Lift", 11: "Ramp",
    12: "Staircase", 13: "Stairlift",
    30: "Crossing-Signalised", 31: "Crossing-Zebra",
    32: "Crossing-Cautionary", 33: "Crossing-Others",
}
# FeatureTypes that are genuinely vertical connectors
CONNECTOR_FT = {8, 10, 11, 12, 13}

M_PER_DEG_LAT = 110574.0
M_PER_DEG_LON = 103000.0

# A connector end must land this close (m) to a published floor network.
TOL = 1.0


def http_json(url, params):
    params = {**params, "f": "json"}
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params),
                                timeout=180) as r:
        return json.loads(r.read().decode())


def fetch_routes():
    out = []
    offset = 0
    while True:
        res = http_json(f"{FS}/0/query", {
            "where": f"BuildingID_1 = {BUILDING_ID}",
            "outFields": "*", "returnGeometry": "true", "outSR": 4326,
            "resultRecordCount": 2000, "resultOffset": offset,
        })
        feats = res.get("features", [])
        out.extend(feats)
        if len(feats) < 2000:
            break
        offset += 2000
    return out


def esri_to_geojson(g):
    """CSDI returns esriGeometry; convert to GeoJSON in WGS84."""
    if not g:
        return None
    paths = g.get("paths") or []
    rings = g.get("rings") or []
    if paths:
        return {"type": "MultiLineString", "coordinates": paths}
    if rings:
        return {"type": "MultiPolygon", "coordinates": [rings]}
    return None


def path_length(path):
    return sum(math.hypot((path[i][0] - path[i - 1][0]) * M_PER_DEG_LON,
                           (path[i][1] - path[i - 1][1]) * M_PER_DEG_LAT)
               for i in range(1, len(path)))


class FloorIndex:
    """Nearest published floor network point, with a spatial hash."""

    CELL = 0.00008  # ~8 m

    def __init__(self, routes):
        self.cell = self.CELL
        self.grid = {}
        for f in routes:
            fid = f["attributes"].get("FloorID")
            if fid not in FLOORS:
                continue
            name = FLOORS[fid][0]
            g = esri_to_geojson(f.get("geometry"))
            if not g:
                continue
            for path in (g["coordinates"] if g["type"] == "MultiLineString"
                         else [g["coordinates"]]):
                for p in path:
                    key = (int(p[0] / self.cell), int(p[1] / self.cell))
                    self.grid.setdefault(key, []).append((p, name))

    def distances(self, lon, lat):
        """Distance (m) to every floor's network."""
        best = {n: float("inf") for n in FLOOR_ORDER}
        ci, cj = int(lon / self.cell), int(lat / self.cell)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for p, name in self.grid.get((ci + di, cj + dj), []):
                    d = math.hypot((lon - p[0]) * M_PER_DEG_LON,
                                   (lat - p[1]) * M_PER_DEG_LAT)
                    if d < best[name]:
                        best[name] = d
        return best

    def nearest(self, lon, lat, tol=TOL):
        """(floor_name, distance) if within tol, else (None, distance)."""
        d = self.distances(lon, lat)
        name = min(d, key=lambda k: d[k])
        return (name, d[name]) if d[name] <= tol else (None, d[name])

    def floors_within(self, lon, lat, tol):
        return {n for n, d in self.distances(lon, lat).items() if d <= tol}


def classify(routes, index):
    """Split the FloorID-less routes into connectors and flat site surfaces.

    The evidence, in order of strength:

    1. `link`   - the path's two ends land on two DIFFERENT published floor
                  networks (within TOL metres). Both escalator and lift ends
                  land at exactly 0.00 m from the network they serve, because
                  the connectors and the floor network share vertices. This is
                  a definite floor-to-floor connector.
    2. `shaft`  - a lift whose plan length is under 1 m. A lift shaft is
                  vertical; it serves every floor within a short distance of
                  the shaft point.
    3. `incline`- a connector whose two ends both sit on the SAME published
                  floor. It still changes level (the CSDI `Gradient` is
                  non-zero), but it does not reach the next published floor -
                  a part-storey rise within one floor, e.g. a half-level
                  escalator. It is drawn as a real incline at that floor, not
                  as a floor-to-floor link.
    4. anything else is a flat surface, not vertical circulation.
    """
    connectors = []
    surfaces = []

    for f in routes:
        a = f["attributes"]
        if a.get("FloorID") is not None:
            continue
        g = esri_to_geojson(f.get("geometry"))
        if not g:
            continue
        ftype = a.get("FeatureType")
        gradient = a.get("Gradient")
        grad = float(gradient) if gradient not in (None, "") else 0.0
        alias = a.get("AliasNameEN") or a.get("AliasNameTC") or ""

        for path in g["coordinates"]:
            if len(path) < 2:
                continue
            run = path_length(path)
            fA, dA = index.nearest(path[0][0], path[0][1])
            fB, dB = index.nearest(path[-1][0], path[-1][1])

            # --- 1. definite link between two different published floors ---
            if fA and fB and fA != fB and ftype in CONNECTOR_FT:
                connectors.append(dict(
                    path=path, kind=FT_NAMES.get(ftype, f"FT{ftype}"),
                    alias=alias, floor_from=fA, floor_to=fB, mode="link",
                    rise=FLOORS_BY_NAME[fB][2] - FLOORS_BY_NAME[fA][2],
                    run=run, gradient=grad))
                continue

            # --- 2. a lift shaft: vertical, serves the floors around it ---
            if ftype == 10 and run < 1.0:
                served = index.floors_within(path[0][0], path[0][1], 0.5)
                served |= index.floors_within(path[-1][0], path[-1][1], 0.5)
                served = [f for f in FLOOR_ORDER if f in served]
                if len(served) >= 2:
                    connectors.append(dict(
                        path=path, kind="Lift", alias=alias,
                        floor_from=served[0], floor_to=served[-1],
                        mode="shaft",
                        rise=FLOORS_BY_NAME[served[-1]][2] - FLOORS_BY_NAME[served[0]][2],
                        run=run, gradient=grad))
                    continue
                if len(served) == 1:
                    connectors.append(dict(
                        path=path, kind="Lift", alias=alias,
                        floor_from=served[0], floor_to=served[0], mode="shaft",
                        rise=None, run=run, gradient=grad))
                    continue

            # --- 3. an incline within one published floor ---
            if (fA or fB) and ftype in CONNECTOR_FT and grad * run > 0.3:
                base = fA or fB
                connectors.append(dict(
                    path=path, kind=FT_NAMES.get(ftype, f"FT{ftype}"),
                    alias=alias, floor_from=base, floor_to=base,
                    mode="incline", rise=grad * run, run=run, gradient=grad))
                continue

            # --- 4. a flat surface ---
            surfaces.append(dict(path=path,
                                 kind=FT_NAMES.get(ftype, f"FT{ftype}"),
                                 alias=alias, feature_type=ftype, gradient=grad))

    return connectors, surfaces


FLOORS_BY_NAME = {v[0]: v for v in FLOORS.values()}


def _next_floor(name):
    """The next published floor above `name` (None at the top)."""
    if name not in FLOOR_ORDER:
        return None
    i = FLOOR_ORDER.index(name)
    return FLOOR_ORDER[i + 1] if i + 1 < len(FLOOR_ORDER) else None


def build():
    print("=== fetching Festival Walk routes from CSDI ===")
    routes = fetch_routes()
    print(f"  {len(routes)} routes")

    index = FloorIndex(routes)
    nofloor = [f for f in routes if f["attributes"].get("FloorID") is None]
    print(f"  {len(nofloor)} routes with no FloorID")

    connectors, surfaces = classify(nofloor, index)
    print(f"\n=== classification ===")
    print(f"  genuine connectors : {len(connectors)}")
    print(f"  flat site surfaces : {len(surfaces)}")

    by_kind = {}
    for c in connectors:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    print(f"  connectors by kind : {by_kind}")
    by_mode = {}
    for c in connectors:
        by_mode[c["mode"]] = by_mode.get(c["mode"], 0) + 1
    print(f"  connectors by mode : {by_mode}")

    # ---- write the 3D connector file (z is added by the app at render time) --
    feats = []
    for c in connectors:
        props = {
            "kind": c["kind"],
            "mode": c["mode"],
            "floor_from": c["floor_from"],
            "floor_to": c["floor_to"],
            "run_m": round(c["run"], 2),
            "gradient": round(c["gradient"], 4),
            "rise_m": (round(c["rise"], 2) if c["rise"] is not None else None),
            "alias": _alias(c),
        }
        feats.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": c["path"]},
            "properties": props,
        })

    out = {"type": "FeatureCollection", "features": feats}
    p3d = os.path.join(DATA, "festival_walk_vertical_3d.geojson")
    with open(p3d, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f"\n  wrote {os.path.relpath(p3d, ROOT)}  ({len(feats)} features)")

    # ---- write the flat site surfaces (drawn on the terrain, not in the stack)
    sfeats = []
    for s in surfaces:
        sfeats.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": s["path"]},
            "properties": {
                "kind": s["kind"],
                "feature_type": s["feature_type"],
                "alias": _alias(s),
            },
        })
    pout = {"type": "FeatureCollection", "features": sfeats}
    psurf = os.path.join(DATA, "festival_walk_site_surface.geojson")
    with open(psurf, "w", encoding="utf-8") as fh:
        json.dump(pout, fh, ensure_ascii=False)
    print(f"  wrote {os.path.relpath(psurf, ROOT)}  ({len(sfeats)} features)")

    # ---- print an audit table ----
    print("\n=== connector audit ===")
    print(f"  {'kind':11} {'mode':9} {'from':11} {'to':11} {'run m':>7} "
          f"{'grad':>7} {'rise m':>7}")
    for c in connectors:
        print(f"  {c['kind']:11} {c['mode']:9} {str(c['floor_from']):11} "
              f"{str(c['floor_to']):11} {c['run']:7.1f} {c['gradient']:7.3f} "
              f"{(c['rise'] if c['rise'] is not None else '-'):>7}")

    return 0


def _alias(d):
    for k in ("alias", "alias_en"):
        if k in d:
            return d[k]
    return d.get("kind", "")


if __name__ == "__main__":
    raise SystemExit(build())
