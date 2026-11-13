#!/usr/bin/env python3
"""
Fetch the OpenStreetMap coastline for Hong Kong from the OSM API.

The Overpass instances were unavailable for the whole session (HTTP
400/406/502 and timeouts), but the plain OSM API works. Its /map call
returns every node and way in a bbox, including natural=coastline ways.

The API's bbox limit is 0.25 square degrees and the payload gets large,
so the territory is fetched as a grid of tiles and the coastline ways are
extracted from each.

Run:  python3 fetch_osm_coastline_api.py
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

UA = {"User-Agent": "hermes-gis-flood/1.0 (HK low-lying land analysis)"}
API = "https://api.openstreetmap.org/api/0.6/map"

# Hong Kong, with a margin. Split into a grid of small tiles - the OSM API
# rejects a bbox with HTTP 400 once the payload gets too big, so the
# tiles are deliberately small (0.09 x 0.067 degrees).
LON0, LON1 = 113.72, 114.44
LAT0, LAT1 = 22.16, 22.56
NX, NY = 8, 6


def fetch_tile(bbox, tries=3):
    u = API + "?" + urllib.parse.urlencode(
        {"bbox": ",".join(f"{v:.4f}" for v in bbox)})
    for attempt in range(tries):
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # RATE LIMITED. Back off hard and stop for this tile - the
                # server needs minutes, not seconds.
                wait = 45 * (attempt + 1)
                print(f"      429 rate limited, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            print(f"      attempt {attempt+1} failed: {str(e)[:70]}", flush=True)
            return None
        except Exception as e:
            print(f"      attempt {attempt+1} failed: {str(e)[:70]}", flush=True)
            time.sleep(2 * (attempt + 1))
    return None


def fetch_tile_split(bbox, depth=0):
    """Fetch a tile. The OSM API returns HTTP 400 when the payload for a
    bbox is too large, so a failing tile is halved and retried. An empty
    tile (no data) returns an empty string, which is not an error.

    Each successful chunk is cached on disk, so a re-run only fetches what
    is missing."""
    a, c, b, d = bbox
    tag = f"{a:.4f}_{c:.4f}_{b:.4f}_{d:.4f}".replace(".", "p").replace("-", "m")
    cache = os.path.join(RAW, "osm_tiles", f"tile_{tag}.xml")
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if os.path.exists(cache):
        return [open(cache, encoding="utf-8", errors="ignore").read()]
    xml = fetch_tile(bbox)
    if xml is not None:
        open(cache, "w", encoding="utf-8").write(xml)
        return [xml]
    if depth >= 4:
        return []
    midx, midy = (a + b) / 2, (c + d) / 2
    out = []
    for sub in [(a, c, midx, midy), (midx, c, b, midy),
                (a, midy, midx, d), (midx, midy, b, d)]:
        out.extend(fetch_tile_split(sub, depth + 1))
    return out


def parse_coastline(xml):
    """Return the natural=coastline ways as coordinate lists."""
    ways = []
    # split into <way> blocks
    for block in re.findall(r"<way\b[^>]*>(.*?)</way>", xml, re.S):
        if 'k="natural"' not in block or 'v="coastline"' not in block:
            continue
        nd = re.findall(r'<nd ref="(\d+)"', block)
        if len(nd) >= 2:
            ways.append(nd)
    return ways


def parse_nodes(xml):
    nodes = {}
    for m in re.finditer(r'<node id="(\d+)"[^>]*lat="([-\d.]+)" lon="([-\d.]+)"', xml):
        nodes[m.group(1)] = (float(m.group(3)), float(m.group(2)))
    return nodes


def main():
    os.makedirs(RAW, exist_ok=True)
    all_ways = []
    all_nodes = {}
    ntiles = 0
    failed_tiles = []
    for i in range(NX):
        for j in range(NY):
            a = LON0 + (LON1 - LON0) * i / NX
            b = LON0 + (LON1 - LON0) * (i + 1) / NX
            c = LAT0 + (LAT1 - LAT0) * j / NY
            d = LAT0 + (LAT1 - LAT0) * (j + 1) / NY
            print(f"  tile {i},{j}: bbox {a:.3f},{c:.3f},{b:.3f},{d:.3f}", flush=True)
            chunks = fetch_tile_split((a, c, b, d))
            if not chunks:
                # The split recursion gives up after 4 levels. A tile that
                # ends here is MISSING, not empty, and the coastline would
                # have a hole in it - so this must be loud, not a quiet
                # skip. The run is only sound if every tile succeeded.
                print("    *** FAILED - this tile is missing from the "
                      "coastline ***", flush=True)
                failed_tiles.append((i, j))
                continue
            ntiles += 1
            for xml in chunks:
                nodes = parse_nodes(xml)
                all_nodes.update(nodes)
                ways = parse_coastline(xml)
                all_ways.extend(ways)
            nw = sum(parse_coastline(x).__len__() for x in chunks)
            print(f"    {len(chunks)} chunk(s), {nw} coastline ways", flush=True)
            time.sleep(4.0)

    print()
    print(f"{ntiles} tiles fetched, {len(all_ways)} coastline way references, "
          f"{len(all_nodes)} nodes")
    if failed_tiles:
        # A failed tile leaves a HOLE in the coastline, and a hole in the
        # coastline leaks the land mask. Stop here rather than write a
        # coastline file that looks complete.
        raise SystemExit(
            f"{len(failed_tiles)} of {NX * NY} tiles FAILED and are missing "
            f"from the coastline: {failed_tiles}. The cached tiles are kept, "
            f"so re-run this script to fetch only what is missing.")
    if not all_ways:
        raise SystemExit("no coastline ways found - the fetch failed")

    # resolve the node references into coordinate lists
    lines = []
    unresolved = 0
    for refs in all_ways:
        pts = [all_nodes[r] for r in refs if r in all_nodes]
        if len(pts) != len(refs):
            unresolved += 1
        if len(pts) >= 2:
            lines.append(pts)
    print(f"resolved {len(lines)} coastline lines ({unresolved} had a node "
          f"in another tile)")

    p = os.path.join(RAW, "osm_coastline_api.json")
    json.dump(lines, open(p, "w"))
    print(f"wrote {p} ({os.path.getsize(p):,} bytes)")

    # the same endpoint chains check the skill asks for
    def key(pt):
        return (round(pt[0], 4), round(pt[1], 4))
    ends = {}
    for l in lines:
        for e in (key(l[0]), key(l[-1])):
            ends[e] = ends.get(e, 0) + 1
    shared = sum(1 for v in ends.values() if v > 1)
    print(f"  {len(lines)} lines, {len(ends)} distinct endpoints, "
          f"{shared} shared by 2+ lines")
    print(f"  -> the coastline "
          f"{'DOES chain into rings' if shared > len(lines) * 0.5 else 'does NOT chain'}")


if __name__ == "__main__":
    main()
