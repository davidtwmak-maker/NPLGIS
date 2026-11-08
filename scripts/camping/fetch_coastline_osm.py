#!/usr/bin/env python3
"""
Fetch Hong Kong's coastline from the OpenStreetMap /map API (v2).

The /map endpoint refuses a bbox with more than ~50k objects (HTTP 400) and
rate-limits with HTTP 429.  Strategy:
  - walk a grid of small boxes
  - on 400 (too dense): split the box into four and recurse
  - on 429 (rate limited): back off hard and retry the SAME box later
  - cache every successful box on disk, so a re-run only fetches what is
    missing (this is what makes the 429 gaps recoverable)

Output: hk_land_boundary.geojson  (MultiPolygon of land, from the
polygonised natural=coastline ways)
"""
import json
import math
import os
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET

OUT = "/Users/davidhermes/GIS Data/HK Camping Sites"
DST = f"{OUT}/hk_land_boundary.geojson"
CACHE = f"{OUT}/_osm_box_cache"
UA = "HermesGIS/1.0 (Hong Kong camping/light-pollution study; educational)"
ctx = ssl.create_default_context()
os.makedirs(CACHE, exist_ok=True)

LON0, LON1 = 113.74, 114.48
LAT0, LAT1 = 22.10, 22.58


def cache_key(lon0, lat0, lon1, lat1):
    return f"{lon0:.5f}_{lat0:.5f}_{lon1:.5f}_{lat1:.5f}".replace(".", "_")


def fetch_box(lon0, lat0, lon1, lat1):
    """Return ('ok', nodes, ways) on success, ('err', reason) on failure.

    A single tagged return removes the bug where the caller unpacked a
    2-tuple as (nodes, ways) but then returned only the first element, so
    every way was silently dropped.
    """
    key = cache_key(lon0, lat0, lon1, lat1)
    cp = f"{CACHE}/{key}.json"
    if os.path.exists(cp):
        with open(cp) as f:
            d = json.load(f)
        return "ok", d["nodes"], d["ways"]

    url = (f"https://api.openstreetmap.org/api/0.6/map?bbox="
           f"{lon0:.5f},{lat0:.5f},{lon1:.5f},{lat1:.5f}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        b = urllib.request.urlopen(req, timeout=180, context=ctx).read()
    except Exception as e:
        return "err", f"{type(e).__name__}: {e}"

    try:
        root = ET.fromstring(b)
    except ET.ParseError as e:
        return "err", f"ParseError {e}"

    nodes = {}
    for n in root.findall("node"):
        nodes[n.get("id")] = [float(n.get("lon")), float(n.get("lat"))]
    ways = {}
    for w in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
        refs = [nd.get("ref") for nd in w.findall("nd")]
        ways[w.get("id")] = {"refs": refs, "tags": tags}
    with open(cp, "w") as f:
        json.dump({"nodes": nodes, "ways": ways}, f)
    return "ok", nodes, ways


def collect(lon0, lat0, lon1, lat1, depth=0, tries=0):
    """Fetch a box, splitting on 400 and backing off on 429.

    Returns a LIST of (nodes, ways) pairs - one per box actually fetched.
    """
    status = fetch_box(lon0, lat0, lon1, lat1)
    if status[0] == "ok":
        return [(status[1], status[2])]

    err = status[1]
    is429 = "429" in (err or "")
    if is429 and tries < 8:
        wait = min(60, 5 * (tries + 1))
        print(f"    429 on {lon0:.4f},{lat0:.4f} - waiting {wait}s",
              flush=True)
        time.sleep(wait)
        return collect(lon0, lat0, lon1, lat1, depth, tries + 1)

    if depth >= 3:
        print(f"    GIVE UP {lon0:.4f},{lat0:.4f}-"
              f"{lon1:.4f},{lat1:.4f} ({err})")
        return []

    mid_lon = (lon0 + lon1) / 2
    mid_lat = (lat0 + lat1) / 2
    print(f"    split {lon0:.4f},{lat0:.4f} ({err})", flush=True)
    time.sleep(2)
    out = []
    for q in [(lon0, lat0, mid_lon, mid_lat), (mid_lon, lat0, lon1, mid_lat),
              (lon0, mid_lat, mid_lon, lat1), (mid_lon, mid_lat, lon1, lat1)]:
        out += collect(*q, depth=depth + 1, tries=0)
    return out


def main():
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    NX, NY = 19, 12
    dlon = (LON1 - LON0) / NX
    dlat = (LAT1 - LAT0) / NY
    print(f"fetching {NX}x{NY} boxes (cached boxes are skipped)")
    all_nodes, all_ways = {}, {}
    nbox = 0
    for i in range(NX):
        for j in range(NY):
            a = LON0 + dlon * i
            b = LON0 + dlon * (i + 1)
            c = LAT0 + dlat * j
            d = LAT0 + dlat * (j + 1)
            for nodes, ways in collect(a, c, b, d):
                all_nodes.update(nodes)
                all_ways.update(ways)
                nbox += 1
            print(f"  box {i+1}/{NX},{j+1}/{NY} "
                  f"(cum {len(all_ways)} ways)", flush=True)
    print(f"fetched {nbox} box payloads, {len(all_ways)} ways")

    coast = []
    for wid, w in all_ways.items():
        if w["tags"].get("natural") != "coastline":
            continue
        pts = [tuple(all_nodes[r]) for r in w["refs"] if r in all_nodes]
        if len(pts) >= 2:
            coast.append(LineString(pts))
    print(f"{len(coast)} coastline ways")
    if not coast:
        raise SystemExit("no coastline ways found")

    merged = unary_union(coast)
    polys = [p for p in polygonize(merged) if p.area > 1e-6]
    print(f"polygonised into {len(polys)} rings")
    u = unary_union(polys)

    a_km2 = u.area * (111.32 ** 2) * math.cos(math.radians(22.3))
    print(f"union area ~{a_km2:.0f} km2 (HK land is ~1106 km2)")

    # Also save the RAW coastline ways so the ring-stitching builder can
    # work from them.  polygonize() alone gives 193 km2 instead of ~1106 km2
    # because OSM coastline ways are open chains, not closed rings.
    raw = [{"pts": [[list(p) for p in line.coords]]} for line in coast]
    with open(f"{OUT}/_coast_ways.json", "w") as f:
        json.dump([[list(p) for p in line.coords] for line in coast], f)
    print(f"saved {len(coast)} raw coastline ways -> _coast_ways.json")

    gj = {"type": "FeatureCollection",
          "features": [{"type": "Feature",
                        "properties": {
                            "name": "Hong Kong land boundary",
                            "source": "OpenStreetMap natural=coastline ways, "
                                      "polygonised (ODbL)",
                            "note": "land only; excludes territorial waters"},
                        "geometry": u.__geo_interface__}]}
    with open(DST, "w") as f:
        json.dump(gj, f)
    print("wrote", DST, os.path.getsize(DST), "bytes")


if __name__ == "__main__":
    main()
