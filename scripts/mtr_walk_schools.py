#!/usr/bin/env python3
"""Walk from the nearest MTR station exit to each secondary school.

Scenario: bus and minibus service is unavailable (outage) or the roads are
congested, so the student must walk the whole way from the station.  This is
the worst case for distance and for time in the rain.

For every school:
  - find the nearest MTR station exit (the pedestrian-network walk, not a
    straight line)
  - solve the shortest path on the LandsD 3D Pedestrian Network
  - measure the total walk, the longest uncovered stretch, the covered share,
    and the climb

Outputs work/mtr_walk_schools.json
"""
import collections, json, math, os
import numpy as np
from shapely.geometry import shape, Point
from shapely.ops import transform as shp_transform
from shapely.strtree import STRtree
from pyproj import Transformer
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = os.path.expanduser("~/GIS Data/Sun-Rain Exposure")
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
NET = os.path.expanduser("~/GIS Data/3D Pedestrian Network")

_tr = Transformer.from_crs("EPSG:4326", "EPSG:2326", always_xy=True)


def proj(g):
    return shp_transform(lambda x, y, z=None: _tr.transform(x, y), g)


def classify(p):
    """Same rules as kowloon_peninsula_routes.py:
       sheltered  WeatherProof == 1 (Covered) or Location == 2 (Indoor)
       exposed    Location == 1 and WeatherProof == 2
       unclassified Location == 1 and WeatherProof == 3  -> counted as NOT covered
    """
    W, loc = p.get("WeatherProof"), p.get("Location")
    if W == 1 or loc == 2:
        return "sheltered"
    if loc == 1 and W == 2:
        return "exposed"
    if loc == 1 and W == 3:
        return "unclassified"
    return "other"


def load_network():
    segs = []
    for fn in ("covered_outdoor_paths.geojson", "exposed_outdoor_paths.geojson",
               "covered_indoor_or_unclassified.geojson"):
        path = os.path.join(NET, fn)
        if not os.path.exists(path):
            continue
        for ft in json.load(open(path, encoding="utf-8"))["features"]:
            g = shape(ft["geometry"])
            if not (114.10 < g.bounds[0] < 114.25 and 22.25 < g.bounds[1] < 22.40):
                continue
            p = ft["properties"]
            segs.append((g, p.get("Gradient") or 0.0, classify(p), p.get("StreetNameEN") or ""))
    nid, xy, edges = {}, [], []

    def N(x, y):
        k = (round(x, 6), round(y, 6))
        if k not in nid:
            nid[k] = len(xy)
            xy.append((x, y))
        return nid[k]

    for g, gr, cls, street in segs:
        c = g.coords
        u, v = N(c[0][0], c[0][1]), N(c[-1][0], c[-1][1])
        if u != v:
            # keep the full polyline so the exported route follows the street
            # instead of cutting the corner
            edges.append((u, v, proj(g).length, gr, cls, street, list(c)))
    n = len(xy)
    # Every parallel edge between the same node pair is kept.  The graph
    # cost is the minimum (coo_matrix would SUM duplicates and inflate the
    # path), but the geometry used for measurement and export must be the
    # SAME edge that provided that cost.
    best = {}
    by_pair = collections.defaultdict(list)
    for idx, (u, v, L, gr, cls, street, coords) in enumerate(edges):
        for a, b in ((u, v), (v, u)):
            k = (a, b)
            by_pair[k].append(idx)
            if k not in best or L < best[k][0]:
                cc = list(coords) if a == u else list(reversed(coords))
                best[k] = (L, gr, cls, street, cc)
    G = coo_matrix((np.array([v[0] for v in best.values()]),
                    (np.array([k[0] for k in best]), np.array([k[1] for k in best]))),
                   shape=(n, n)).tocsr()
    G = G + G.T
    return xy, best, G, edges, by_pair


def main():
    xy, edge, G, edges, by_pair = load_network()
    print("network: %d nodes, %d edges" % (len(xy), len(edge)), flush=True)

    # ---- MTR exits -------------------------------------------------------
    mtr = json.load(open(os.path.join(RAW, "mtr_entry_points.geojson"), encoding="utf-8"))
    exits = []
    for f in mtr["features"]:
        pr = f["properties"]
        c = f["geometry"]["coordinates"]
        exits.append({"station": pr.get("venue_name_en"), "station_zh": pr.get("venue_name_zh"),
                      "exit": pr.get("amenity_name_en"), "lon": c[0], "lat": c[1],
                      "z": c[2] if len(c) > 2 else None,
                      "level": pr.get("level_name_en")})
    print("MTR exits in layer: %d" % len(exits), flush=True)

    node_pts = [Point(x, y) for x, y in xy]
    node_tree = STRtree(node_pts)
    node_hk = [proj(p) for p in node_pts]

    # Snap each exit to the network.  An exit may sit on an elevated
    # concourse that the pedestrian network represents on a different level,
    # so the nearest node in XY can be far away in practice.  Keep the XY snap
    # for reporting, but require the snap to be short, and fall back to the
    # exit's own location for the path search.
    for e in exits:
        i = node_tree.nearest(Point(e["lon"], e["lat"]))
        e["node"] = i
        e["snap_m"] = node_hk[i].distance(proj(Point(e["lon"], e["lat"])))
    snaps = [e["snap_m"] for e in exits]
    print("exit snap distance: median %.1f m | max %.1f m | <=60 m: %d of %d"
          % (np.median(snaps), max(snaps), sum(1 for s in snaps if s <= 60), len(snaps)), flush=True)
    bad = sorted(exits, key=lambda e: -e["snap_m"])[:8]
    print("worst snaps:", [(e["station"], e["exit"], round(e["snap_m"])) for e in bad], flush=True)

    # ---- schools ---------------------------------------------------------
    schools = json.load(open(os.path.join(WORK, "peninsula_routes_schools.json"), encoding="utf-8"))

    # ---- the walk -------------------------------------------------------
    out = []
    for s in schools:
        sp = proj(Point(s["lon"], s["lat"]))
        snode = node_tree.nearest(Point(s["lon"], s["lat"]))
        # dijkstra FROM the school over the network
        dist, pred = dijkstra(G, directed=False, indices=snode, return_predecessors=True)
        # rank exits by network distance
        cand = sorted(((float(dist[e["node"]]), e["node"], i) for i, e in enumerate(exits)
                       if np.isfinite(dist[e["node"]]) and e["snap_m"] <= 120),
                      key=lambda t: (t[0], t[1]))
        if not cand:
            continue
        best_d, _, best_i = cand[0]
        best_e = exits[best_i]
        # Trace the path from the exit back to the school.
        # `pred` points TOWARD the source (the school), so walking pred from
        # the exit gives the exit -> school order.  Keep that order.
        path_nodes = [best_e["node"]]
        cur = best_e["node"]
        guard = 0
        while cur != snode and guard < 200000:
            cur = int(pred[cur])
            if cur < 0:
                break
            path_nodes.append(cur)
            guard += 1
        if cur != snode:
            log("  %s: path trace failed" % s["name"][:36])
            continue
        # profile
        total = 0.0
        covered = 0.0
        longest_exp = 0.0
        run = 0.0
        n_run = 0
        climb = 0.0
        streets = collections.Counter()
        # the geometry edge must be the one that supplied the graph cost
        seq = []      # (edge index, from node, to node) along the path
        for a, b in zip(path_nodes[:-1], path_nodes[1:]):
            idxs = by_pair.get((a, b))
            if not idxs:
                continue
            i = min(idxs, key=lambda j: edges[j][2])
            seq.append((i, a, b))
        for i, a, b in seq:
            u, v, L, gr, cls, street, _c = edges[i]
            total += L
            streets[street] += 1
            if cls == "sheltered":
                covered += L
                run = 0.0
            else:
                run += L
                if run > longest_exp:
                    longest_exp = run
                n_run += 1
            climb += gr * L
        # splice each edge's full polyline so the drawn line follows the
        # street and its length equals the measured length
        # Splice each edge's full polyline so the drawn line follows the
        # street and its length equals the measured length.
        #
        # Orientation must be decided by NODE ID, not by comparing
        # coordinates: nodes are snapped by rounding to 1e-6 deg, so two
        # entries for the same node can differ in the 7th decimal and an exact
        # coordinate test wrongly reverses an edge.  A wrongly reversed edge
        # makes the line jump back to where it came from, which roughly
        # doubles the drawn length against the walked length.
        chain_xy = []
        for i, a, b in seq:
            u, v, L, gr, cls, street, cc = edges[i]
            if u != a:                       # the path traverses it v -> u
                cc = list(reversed(cc))
            chain_xy.extend([(c[0], c[1]) for c in cc[:-1]])
        if chain_xy:
            chain_xy.append((xy[snode][0], xy[snode][1]))
        else:
            chain_xy = [[xy[snode][0], xy[snode][1]]]
        # walking time: 1.25 m/s on the flat (Hong Kong urban pedestrian speed),
        # 0.9 m/s when the route climbs, 0.7 m/s when it descends steeply
        if climb > 6:
            speed = 0.9
        elif climb < -6:
            speed = 0.85
        else:
            speed = 1.25
        minutes = total / speed / 60.0
        out.append({
            "_chain": chain_xy,
            "school_id": s["school_id"], "name": s["name"], "name_tc": s.get("name_tc"),
            "district": s["district"], "address": s.get("address"),
            "lon": s["lon"], "lat": s["lat"],
            "station": best_e["station"], "station_zh": best_e["station_zh"],
            "exit": best_e["exit"], "exit_snap_m": round(best_e["snap_m"], 1),
            "walk_m": round(total, 1),
            "straight_m": round(best_e["snap_m"] + 0, 1),
            "covered_m": round(covered, 1),
            "covered_ratio": round(covered / total, 3) if total else None,
            "longest_exposed_m": round(longest_exp, 1),
            "n_exposed_runs": n_run,
            "climb_m": round(climb, 1),
            "n_streets": len(streets),
            "top_streets": ", ".join("%s (%.0f m)" % (k, v) for k, v in streets.most_common(3)),
            "walk_minutes": round(minutes, 1),
            "walk_speed_ms": speed,
        })
        print("  %-44s %6.0f m from %s %s" % (s["name"][:44], total, best_e["station"], best_e["exit"]), flush=True)

    json.dump([{k: v for k, v in r.items() if not k.startswith("_")} for r in out],
              open(os.path.join(WORK, "mtr_walk_schools.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print("\nwrote mtr_walk_schools.json", flush=True)

    # ---- route geometry, for the map and the geodatabase --------------------
    # The path chain was collected during the single pass above, so the
    # geometry and the metrics can never disagree.
    geo = []
    for rec in out:
        coords = rec.pop("_chain")
        geo.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {k: v for k, v in rec.items() if not k.startswith("_")},
        })
    gj = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
          "features": geo}
    json.dump(gj, open(os.path.join(WORK, "mtr_walk_routes.geojson"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("wrote mtr_walk_routes.geojson (%d features)" % len(geo), flush=True)

    import statistics as stx
    v = [r["walk_m"] for r in out]
    g = [r["longest_exposed_m"] for r in out]
    c = [r["covered_ratio"] for r in out]
    print("\nwalk from nearest MTR exit: median %.0f m | p90 %.0f m | max %.0f m"
          % (stx.median(v), stx.quantiles(v, n=10)[8], max(v)))
    print("longest uncovered stretch: median %.0f m | max %.0f m" % (stx.median(g), max(g)))
    print("covered share: median %.2f | min %.2f" % (stx.median(c), min(c)))
    print("schools with 0 m of cover: %d" % sum(1 for r in out if r["covered_m"] == 0))
    print("fully covered walks: %d" % sum(1 for r in out if r["covered_ratio"] == 1.0))
    mins = [r["walk_minutes"] for r in out]
    print("walk time at 1.25 m/s (0.9 uphill): median %.0f min | p90 %.0f min | max %.0f min"
          % (stx.median(mins), stx.quantiles(mins, n=10)[8], max(mins)))
    print("schools needing over 15 min: %d | over 20 min: %d"
          % (sum(1 for m in mins if m > 15), sum(1 for m in mins if m > 20)))
    print("worst 10 by longest uncovered stretch:")
    for r in sorted(out, key=lambda x: -x["longest_exposed_m"])[:10]:
        print("   %-42s %6.0f m walk from %-26s | gap %5.0f m | cover %.2f"
              % (r["name"][:42], r["walk_m"], (r["station"] or "")[:26], r["longest_exposed_m"], r["covered_ratio"]))


if __name__ == "__main__":
    main()
