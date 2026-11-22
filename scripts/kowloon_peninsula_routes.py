#!/usr/bin/env python3
"""Kowloon Peninsula — covered-route analysis to secondary schools.

Question
--------
For each secondary school on the Kowloon Peninsula, how sheltered is the
commute from the nearest public-transport stop (MTR exit / bus stop /
green-minibus stop) to the school gate, walking on the LandsD 3D Pedestrian
Network?

Method
------
1. Study area  = Census 2021 District Council polygons for 深水埗區 (Sham
   Shui Po), 九龍城區 (Kowloon City) and 油尖旺區 (Yau Tsim Mong) — the
   Kowloon Peninsula, excluding Kowloon East.
2. Network    = LandsD 3D Pedestrian Network, clipped to the study area.
   Each segment classified from the source's own fields:
       sheltered     WeatherProof == 1 (Covered)  OR  Location == 2 (Indoor)
       exposed       Location == 1 AND WeatherProof == 2 (NonCovered)
       unclassified  Location == 1 AND WeatherProof == 3 (Unclassified)
3. Graph      = nodes = segment endpoints snapped by rounding to 1e-6 deg
   (~0.1 m); edges = segments, cost = planar length in metres.
4. Routing    = Dijkstra from the school node (scipy.sparse.csgraph).  For
   every PTI within 800 m straight-line of the school, the network route
   back to the school is traced and measured:
       ai_covered_ratio   sheltered length / total length
       ai_longest_exposed_m   longest unbroken exposed run  <-- the rain answer
       ai_n_exposed_runs      how many separate stretches of exposed walking
5. Per school the *commute* = the shortest network route among its
   candidate PTIs (what a student would actually walk).

Outputs (work/)
    peninsula_routes_schools.json    per-school metrics + chosen route
    peninsula_route_geometry.geojson the chosen routes as lines
    peninsula_covered_paths.geojson  sheltered paths in the study area
    peninsula_pti.geojson            MTR exits / bus / minibus stops
"""
import json
import math
import os
import time
from collections import defaultdict

import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import shape, Point
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

BASE = os.path.expanduser("~/GIS Data")
PN = os.path.join(BASE, "3D Pedestrian Network")
RAW = os.path.join(BASE, "Sun-Rain Exposure", "raw")
WORK = os.path.join(BASE, "Sun-Rain Exposure", "work")
OUT = os.path.join(BASE, "Sun-Rain Exposure", "out")
for d in (WORK, OUT):
    os.makedirs(d, exist_ok=True)

DISTRICTS = {"深水埗區": "Sham Shui Po", "九龍城區": "Kowloon City", "油尖旺區": "Yau Tsim Mong"}
PTI_SEARCH_M = 800.0     # A1  straight-line radius for candidate stops
SNAP_MAX_M = 150.0       # A2  max straight-line distance from school to network
LAT0 = 22.32

t0 = time.time()


def log(msg):
    print(f"[{time.time()-t0:6.1f}s] {msg}", flush=True)


# ---------------------------------------------------------------- study area
log("loading Census 2021 DC polygons...")
import gzip
with gzip.open(os.path.join(BASE, "GeoInfo Map/raw/rgeo_highlight_d00/"
                                   "123_CENSUS_2021_DC_POLY.geojson.gz"), "rt") as f:
    dcs = json.load(f)
dc_geoms, dc_names = {}, {}
for ft in dcs["features"]:
    nm = ft["properties"]["DC_CHI"]
    if nm in DISTRICTS:
        dc_names[nm] = DISTRICTS[nm]
        dc_geoms[nm] = shape(ft["geometry"])
peninsula = unary_union(list(dc_geoms.values()))
minx, miny, maxx, maxy = peninsula.bounds
log(f"peninsula: {list(dc_names.values())}  bounds={[round(v,4) for v in peninsula.bounds]}")

# --------------------------------------------------------------- the network
CLS = {}


def classify(p):
    L, W = p.get("Location"), p.get("WeatherProof")
    if W == 1 or L == 2:
        return "sheltered"
    if L == 1 and W == 2:
        return "exposed"
    return "unclassified"


def load_network(fn):
    d = json.load(open(os.path.join(PN, fn)))
    out = []
    for ft in d["features"]:
        g = shape(ft["geometry"])
        if g.bounds[0] > maxx or g.bounds[2] < minx or g.bounds[1] > maxy or g.bounds[3] < miny:
            continue
        if not g.intersects(peninsula):
            continue
        parts = list(g.geoms) if g.geom_type == "MultiLineString" else [g]
        for part in parts:
            if part.geom_type != "LineString" or len(part.coords) < 2:
                continue
            out.append((part, classify(ft["properties"]), ft["properties"]))
    return out


log("loading pedestrian network (exposed + sheltered)...")
segs = load_network("exposed_outdoor_paths.geojson") + load_network("covered_indoor_or_unclassified.geojson")
log(f"segments in study area: {len(segs)}")
from collections import Counter
log("  classes: " + str(Counter(c for _, c, _ in segs)))

# ------------------------------------------------------- graph construction
# Distance measurement
# ------------------
# The graph cost must be a real ground distance.  The earlier version scaled
# a shapely DEGREE length by one constant (M_PER_DEG_LAT), which is wrong for
# east-west movement: at this latitude one degree of longitude is ~102,980 m
# but one degree of latitude is ~110,540 m, so every east-west segment was
# inflated by 7.3%.  Worse, the degree length itself was a plain Euclidean
# distance in degrees, which mixes the two axes.
#
# The fix: project to Hong Kong 1980 Grid (EPSG:2326) — the same CRS the
# rest of the NPL GIS work uses and the same one the ArcGIS deliverable is
# published in — and take the length there.  This is exact for a study area
# this small (< 10 km across), and it removes the approximation entirely.
TO_HK = Transformer.from_crs("EPSG:4326", "EPSG:2326", always_xy=True)


def to_hk(coords):
    """lon/lat array -> HK 1980 Grid x/y array."""
    x, y = TO_HK.transform(coords[:, 0], coords[:, 1])
    return np.column_stack([x, y])


def hk_length(geom):
    """True length of a lon/lat geometry in metres, via EPSG:2326."""
    if geom.geom_type == "MultiLineString":
        return sum(hk_length(g) for g in geom.geoms)
    c = np.asarray(geom.coords, dtype=float)
    if len(c) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(to_hk(c), axis=0), axis=1).sum())


# The equirectangular constants are kept ONLY for the 30 m shelter test and
# the 800 m candidate search, where the error is centimetres.  Everything
# that becomes a REPORTED number (route length, snap distance, detour
# factor) is measured in HK 1980 Grid.
M_PER_DEG_LAT = 110540.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))


def xy(lon, lat):
    """lon/lat -> HK 1980 Grid x/y (metres)."""
    x, y = TO_HK.transform(lon, lat)
    return float(x), float(y)


node_id = {}
node_xy = []
edges = []   # (u, v, length_m, cls, geom)


def nid(lon, lat):
    key = (round(lon, 6), round(lat, 6))
    i = node_id.get(key)
    if i is None:
        i = len(node_xy)
        node_id[key] = i
        node_xy.append(xy(lon, lat))
    return i


for geom, cls, props in segs:
    cs = geom.coords
    u = nid(cs[0][0], cs[0][1])
    v = nid(cs[-1][0], cs[-1][1])
    if u == v:
        continue
    length = hk_length(geom)                    # true metres, EPSG:2326
    if length <= 0:
        continue
    edges.append((u, v, length, cls, geom))
log(f"graph nodes: {len(node_xy)}  edges: {len(edges)}")

n = len(node_xy)
rows = np.array([e[0] for e in edges])
cols = np.array([e[1] for e in edges])
vals = np.array([e[2] for e in edges])
# MINIMUM per node-pair, not the SUM.  coo_matrix ADDS duplicate (u,v)
# entries, so parallel segments between the same two nodes would be added
# together and the shortest-path cost inflated.  (scipy's sparse .minimum()
# is NOT usable here: it treats implicit zeros as the minimum and erases the
# graph.)  Build the pair->cost map explicitly, keeping the cheaper link.
pair_cost = {}
for u, v, L in zip(rows, cols, vals):
    k = (int(u), int(v))
    if k not in pair_cost or L < pair_cost[k]:
        pair_cost[k] = float(L)
pu = np.array([k[0] for k in pair_cost], dtype=np.int32)
pv = np.array([k[1] for k in pair_cost], dtype=np.int32)
pl = np.array(list(pair_cost.values()), dtype=np.float64)
GRAPH = coo_matrix((pl, (pu, pv)), shape=(n, n)).tocsr()
GRAPH = GRAPH + GRAPH.T
log(f"scipy graph built: {GRAPH.shape}, nnz={GRAPH.nnz}, "
    f"parallel-edge pairs collapsed: {len(rows) - len(pair_cost)}")

# edge lookup for path reconstruction
edge_by_pair = defaultdict(list)
for i, (u, v, L, cls, geom) in enumerate(edges):
    edge_by_pair[(u, v)].append(i)
    edge_by_pair[(v, u)].append(i)

# --------------------------------------------------------------- PTI layers
log("loading PTI layers...")
pti = []
for fn, kind in (("mtr_entry_points.geojson", "mtr"), ("td_bus_stops.geojson", "bus"),
                 ("td_gmb_stops.geojson", "minibus")):
    d = json.load(open(os.path.join(RAW, fn)))
    n_in = 0
    for ft in d["features"]:
        g = shape(ft["geometry"])
        if not peninsula.intersects(g):
            continue
        p = ft["properties"]
        if kind == "mtr":
            # the amenity name is the EXIT ("Exit B"); the station is the venue
            name = p.get("venue_name_en") or p.get("amenity_name_en") or ""
            exit_name = p.get("amenity_name_en") or ""
        else:
            name = p.get("STOP_ID") or ""
            exit_name = ""
        pti.append({"kind": kind, "name": str(name), "exit_name": str(exit_name),
                    "lon": g.x, "lat": g.y, "geom": g})
        n_in += 1
    log(f"  {kind}: {n_in} in study area")
log(f"PTI total: {len(pti)}")

# --------------------------------------- sheltered access at each PTI (30 m)
log("computing sheltered access at each PTI...")
shel_geoms = [e[4] for e in edges if e[3] == "sheltered"]
from shapely.strtree import STRtree
shel_tree = STRtree(shel_geoms) if shel_geoms else None
# A buffer distance in shapely is in COORDINATE UNITS.  The geometry here is
# lon/lat, so buffer(30.0) would mean 30 DEGREES - 3,300 km - and every stop
# would appear to touch every path.  The 30 m radius must be converted first.
#
# This is now done properly: the stop and the sheltered paths are projected
# to HK 1980 Grid and the buffer is a true 30 m in metres.  The previous
# degree approximation also stretched the buffer by ~7% east-west, which
# mattered at the margin (a path 31 m away in x but 29 m away overall).
SHELTER_R_M = 30.0

shel_hk = shapely.transform(
    np.array(shel_geoms, dtype=object),
    lambda c: to_hk(c),
    include_z=False) if shel_geoms else []
shel_tree_hk = STRtree(shel_hk) if len(shel_hk) else None

for pt in pti:
    pg = pt["geom"]
    # project the stop to HK 1980 Grid and buffer 30 m there
    px, py = xy(pt["lon"], pt["lat"])
    buf = Point(px, py).buffer(SHELTER_R_M)
    # STRtree.query returns INDEXES, not geometries — and a bbox query can
    # still miss a path that only touches the buffer edge, so the candidates
    # are re-tested with a real intersects() before counting.
    idx = shel_tree_hk.query(buf) if shel_tree_hk is not None else []
    hit = False
    for i in idx:
        if shel_hk[int(i)].intersects(buf):
            hit = True
            break
    pt["ai_sheltered_within_30m"] = hit
    pt["ai_is_covered_station"] = (pt["kind"] == "mtr")

# ------------------------------------------------------------------ schools
log("loading schools...")
sch = json.load(open(os.path.join(RAW, "edb_secondary_schools_merged.geojson")))["features"]
schools = []
for ft in sch:
    g = shape(ft["geometry"])
    if not peninsula.contains(g):
        continue
    p = ft["properties"]
    schools.append({"name": p.get("NameEN"), "name_tc": p.get("NameTC"),
                    "district": p.get("DistrictEN"), "type": p.get("DatasetEN"),
                    # Six schools in the study area share a NAME with another
                    # (two Rudolf Steiner campuses, two LAI CHACK sites, two
                    # BEACON records).  Name alone is therefore NOT a usable
                    # key for joining routes back to a school — it silently
                    # merges three distinct campuses into one.
                    #
                    # OBJECTID alone is not enough either: the EDB schools
                    # arrive as FIVE separate datasets (aided, private, DSS,
                    # government, caput) and each restarts its own OBJECTID
                    # counter, so "S33" is three different schools.
                    # dataset_id + OBJECTID is unique across the merge.
                    "sid": p.get("OBJECTID"),
                    "dataset_id": p.get("dataset_id"),
                    "address": p.get("AddressEN"),
                    "lon": g.x, "lat": g.y, "geom": g})
log(f"schools in study area: {len(schools)}")

# A stable, unique key per school record.
_k = Counter()
for s in schools:
    _k[(s["dataset_id"], s["sid"])] += 1
for s in schools:
    s["school_id"] = f"{s['dataset_id']}-{s['sid']}"
assert max(_k.values()) == 1, "school key is not unique"
log(f"school key (dataset_id + OBJECTID) unique: {len(set(s['school_id'] for s in schools))} of {len(schools)}")

# nearest graph node for each school
# node_xy and the school point are both in HK 1980 Grid, so this is a plain
# Euclidean distance in metres.
sxy = np.array([xy(s["lon"], s["lat"]) for s in schools])
sx = sxy[:, 0]
sy = sxy[:, 1]
nx = np.array([p[0] for p in node_xy])
ny = np.array([p[1] for p in node_xy])
d2 = (sx[:, None] - nx[None, :]) ** 2 + (sy[:, None] - ny[None, :]) ** 2
nearest = np.argmin(d2, axis=1)
nearest_d = np.sqrt(d2[np.arange(len(schools)), nearest])
log(f"school->node snap distance: median {np.median(nearest_d):.1f} m, max {nearest_d.max():.1f} m")

# --------------------------------------------------- dijkstra from each school
log("routing: dijkstra from each school node...")
results = []
route_geoms = []

for si, s in enumerate(schools):
    if nearest_d[si] > SNAP_MAX_M:
        results.append({k: v for k, v in s.items() if k != "geom"})
        results[-1].update({
            "ai_routable": False,
            "ai_snap_m": round(float(nearest_d[si]), 1),
            "ai_note": "no pedestrian network within 150 m"})
        continue
    src = int(nearest[si])
    dist, pred = dijkstra(GRAPH, directed=False, indices=src, return_predecessors=True)

    cands = []
    for pt in pti:
        px, py = xy(pt["lon"], pt["lat"])
        dxy = math.hypot(px - sxy[si][0], py - sxy[si][1])
        if dxy <= PTI_SEARCH_M:
            cands.append((dxy, pt))
    cands.sort(key=lambda t: t[0])

    best = None
    best_cov = None
    per_pti = []
    for dxy, pt in cands:
        # snap the PTI to its nearest graph node (both in HK 1980 Grid)
        pxx, pyy = xy(pt["lon"], pt["lat"])
        j = int(np.argmin((nx - pxx) ** 2 + (ny - pyy) ** 2))
        if not np.isfinite(dist[j]):
            per_pti.append({"kind": pt["kind"], "name": pt["name"],
                            "ai_direct_m": round(dxy, 1), "ai_route_m": None,
                            "ai_covered_ratio": None, "ai_reachable": False})
            continue
        # trace path j -> src
        path_nodes = [j]
        cur = j
        guard = 0
        while cur != src and guard < 200000:
            cur = int(pred[cur])
            if cur < 0:
                break
            path_nodes.append(cur)
            guard += 1
        if cur != src:
            per_pti.append({"kind": pt["kind"], "name": pt["name"],
                            "ai_direct_m": round(dxy, 1), "ai_route_m": None,
                            "ai_covered_ratio": None, "ai_reachable": False})
            continue
        # edge sequence
        seq = []
        for a, b in zip(path_nodes[:-1], path_nodes[1:]):
            cand_edges = edge_by_pair.get((a, b))
            if not cand_edges:
                continue
            best_e = min(cand_edges, key=lambda i: edges[i][2])
            seq.append(best_e)
        tot = sum(edges[i][2] for i in seq)
        cov = sum(edges[i][2] for i in seq if edges[i][3] == "sheltered")
        unc = sum(edges[i][2] for i in seq if edges[i][3] == "unclassified")
        # Longest unbroken run of walking that is NOT known to be covered.
        # WeatherProof=3 (Unclassified) is treated as NOT covered — the
        # conservative reading for a rain-exposure question — but its length is
        # tracked separately so the write-up can state how much of each route
        # rests on an unclassified segment.
        run = 0.0
        longest = 0.0
        n_runs = 0
        unc_len = 0.0
        prev_cov = True
        for i in seq:
            L, cls = edges[i][2], edges[i][3]
            if cls == "sheltered":
                run = 0.0
                prev_cov = True
            else:                      # exposed OR unclassified
                if cls == "unclassified":
                    unc_len += L
                if prev_cov:
                    n_runs += 1
                run += L
                longest = max(longest, run)
                prev_cov = False
        if tot <= 0:
            # the PTI snapped onto the school's own graph node: a zero-length
            # "route" is not a commute, so it is not a candidate
            per_pti.append({"kind": pt["kind"], "name": pt["name"],
                            "ai_direct_m": round(dxy, 1), "ai_route_m": 0,
                            "ai_covered_ratio": None, "ai_reachable": True,
                            "ai_note": "snapped to school node (zero-length route)"})
            continue
        rec = {"kind": pt["kind"], "name": pt["name"],
               "ai_direct_m": round(dxy, 1), "ai_route_m": round(tot, 1),
               "ai_covered_ratio": round(cov / tot, 3),
               "ai_covered_m": round(cov, 1),
               "ai_longest_exposed_m": round(longest, 1),
               "ai_n_exposed_runs": n_runs,
               "ai_unclassified_m": round(unc_len, 1),
               "ai_sheltered_within_30m": pt["ai_sheltered_within_30m"],
               "ai_reachable": True, "_seq": seq}
        per_pti.append(rec)
        if best is None or tot < best["_route_m"]:
            best = {**rec, "_route_m": tot}
        # also keep the most-SHELTERED route: a student would take the sheltered
        # option even if it is longer than the nearest stop
        if best_cov is None or (cov / tot) > (best_cov["_cov"]):
            best_cov = {**rec, "_cov": cov / tot}

    if best is None:
        results.append({k: v for k, v in s.items() if k != "geom"})
        results[-1].update({
            "ai_routable": False,
            "ai_snap_m": round(float(nearest_d[si]), 1),
            "ai_note": "no reachable PTI within 800 m"})
        continue

    # geometry of the chosen route
    geoms = [edges[i][4] for i in best["_seq"]]
    rg = unary_union(geoms) if geoms else None
    route_geoms.append({
        "type": "Feature",
        "geometry": json.loads(json.dumps(rg.__geo_interface__)) if rg is not None else None,
        "properties": {
            "school": s["name"], "school_id": s["school_id"],
            "district": s["district"], "school_type": s["type"],
            "ai_route_kind": "shortest",
            "pti_kind": best["kind"], "pti_name": best["name"],
            "ai_route_m": best["ai_route_m"], "ai_covered_ratio": best["ai_covered_ratio"],
            "ai_covered_m": best["ai_covered_m"],
            "ai_longest_exposed_m": best["ai_longest_exposed_m"],
            "ai_n_exposed_runs": best["ai_n_exposed_runs"],
            "ai_direct_m": best["ai_direct_m"],
        },
    })
    if best_cov is not None:
        cov_geoms = [edges[i][4] for i in best_cov["_seq"]]
        cg = unary_union(cov_geoms) if cov_geoms else None
        if cg is not None:
            route_geoms.append({
                "type": "Feature",
                "geometry": json.loads(json.dumps(cg.__geo_interface__)),
                "properties": {
                    "school": s["name"], "school_id": s["school_id"],
                    "district": s["district"],
                    "school_type": s["type"], "ai_route_kind": "best_covered",
                    "pti_kind": best_cov["kind"], "pti_name": best_cov["name"],
                    "ai_route_m": best_cov["ai_route_m"],
                    "ai_covered_ratio": best_cov["ai_covered_ratio"],
                    "ai_covered_m": best_cov["ai_covered_m"],
                    "ai_longest_exposed_m": best_cov["ai_longest_exposed_m"],
                    "ai_n_exposed_runs": best_cov["ai_n_exposed_runs"],
                    "ai_direct_m": best_cov["ai_direct_m"],
                },
            })

    out = {k: v for k, v in s.items() if k != "geom"}
    out.update({
        "ai_routable": True,
        "ai_snap_m": round(float(nearest_d[si]), 1),
        "ai_pti_kind": best["kind"], "ai_pti_name": best["name"],
        "ai_direct_m": best["ai_direct_m"],
        "ai_route_m": best["ai_route_m"],
        "ai_covered_ratio": best["ai_covered_ratio"],
        "ai_covered_m": best["ai_covered_m"],
        "ai_longest_exposed_m": best["ai_longest_exposed_m"],
        "ai_n_exposed_runs": best["ai_n_exposed_runs"],
        "ai_unclassified_m": best["ai_unclassified_m"],
        # best (most covered) reachable route of each PTI type — a student
        # picks their stop, so each mode gets its own answer
        "ai_by_type": {
            t: {
                "ai_route_m": best_t["ai_route_m"],
                "ai_covered_ratio": best_t["ai_covered_ratio"],
                "ai_longest_exposed_m": best_t["ai_longest_exposed_m"],
                "ai_pti_name": best_t["name"],
            }
            for t, best_t in (
                (t, min([r for r in per_pti
                         if r.get("ai_reachable") and r["kind"] == t
                         and r.get("ai_covered_ratio") is not None],
                        key=lambda r: r["ai_route_m"], default=None))
                for t in ("mtr", "bus", "minibus")
            ) if best_t is not None
        },
        "ai_best_cov_ratio": round(best_cov["ai_covered_ratio"], 3) if best_cov else None,
        "ai_best_cov_route_m": best_cov["ai_route_m"] if best_cov else None,
        "ai_best_cov_kind": best_cov["kind"] if best_cov else None,
        "ai_best_cov_pti": best_cov["name"] if best_cov else None,
        "ai_best_cov_longest_exposed_m": best_cov["ai_longest_exposed_m"] if best_cov else None,
        "ai_n_pti_candidates": len(per_pti),
        "ai_n_pti_reachable": sum(1 for r in per_pti if r.get("ai_reachable")),
        "ai_best_covered_ratio": round(max(
            [r["ai_covered_ratio"] for r in per_pti
             if r.get("ai_reachable") and r.get("ai_covered_ratio") is not None],
            default=0), 3),
        "ai_worst_covered_ratio": round(min(
            [r["ai_covered_ratio"] for r in per_pti
             if r.get("ai_reachable") and r.get("ai_covered_ratio") is not None],
            default=0), 3),
        "ai_pti_detail": [{k: v for k, v in r.items() if not k.startswith("_")}
                          for r in per_pti],
    })
    results.append(out)

log(f"routed {sum(1 for r in results if r.get('ai_routable'))} of {len(results)} schools")

# ------------------------------------------------------------------- outputs
json.dump(results, open(os.path.join(WORK, "peninsula_routes_schools.json"), "w"),
          ensure_ascii=False, indent=1)
json.dump({"type": "FeatureCollection", "features": route_geoms},
          open(os.path.join(WORK, "peninsula_route_geometry.geojson"), "w"), ensure_ascii=False)

# sheltered paths in the study area, tagged with their street name
cov_feats = []
for geom, cls, props in segs:
    if cls == "sheltered":
        cov_feats.append({"type": "Feature",
                          "geometry": json.loads(json.dumps(geom.__geo_interface__)),
                          "properties": {"ai_class": cls,
                                         "ai_street": props.get("StreetNameEN") or ""}})
json.dump({"type": "FeatureCollection", "features": cov_feats},
          open(os.path.join(WORK, "peninsula_covered_paths.geojson"), "w"), ensure_ascii=False)

pti_feats = [{"type": "Feature", "geometry": json.loads(json.dumps(p["geom"].__geo_interface__)),
              "properties": {"ai_kind": p["kind"], "ai_name": p["name"],
                             "ai_exit_name": p["exit_name"],
                             "ai_sheltered_within_30m": p["ai_sheltered_within_30m"]}}
             for p in pti]
json.dump({"type": "FeatureCollection", "features": pti_feats},
          open(os.path.join(WORK, "peninsula_pti.geojson"), "w"), ensure_ascii=False)

log(f"wrote: peninsula_routes_schools.json  peninsula_route_geometry.geojson "
    f"({len(route_geoms)})  peninsula_covered_paths.geojson ({len(cov_feats)})  "
    f"peninsula_pti.geojson ({len(pti_feats)})")
log("done")
