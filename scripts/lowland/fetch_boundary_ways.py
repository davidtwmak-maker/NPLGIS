#!/usr/bin/env python3
"""
Fetch the missing OSM boundary ways BY ID.

Why this script exists
----------------------
The tiled fetch (`fetch_osm_coastline_api.py`) covers the whole Hong Kong
territory, but the OSM Hong Kong boundary relations (20044132 and 913110)
list member ways that the tiles do NOT contain - the boundary ways run along
the land border with Shenzhen, and the tile grid that covers the sea does not
always carry them.

`build_land_mask_osm_hk.py` reads every way it has from two places: the
cached tiles, and `raw/osm_ways/way_*.xml`. Without this script that second
directory never exists, so the mask cannot be rebuilt from a fresh clone.

The OSM API will fetch a way by its ID:

    https://api.openstreetmap.org/api/0.6/ways?ways=ID1,ID2,...

The API rate-limits hard (HTTP 429), so the calls are paced and retried,
and every way is cached on disk. A rerun fetches only what is missing.

Run:  python3 fetch_boundary_ways.py
"""
import glob
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
RAW = os.path.join(HERE, "raw")
TILES = os.path.join(RAW, "osm_tiles")
WAYS_DIR = os.path.join(RAW, "osm_ways")

API = "https://api.openstreetmap.org/api/0.6"
UA = "hermes-gis-flood/1.0 (HK low-lying land analysis)"

# the Hong Kong boundary relations: admin_level 4 and admin_level 3
HK_REL_IDS = {"20044132", "913110"}

# the OSM API will not serve an unbounded way list, so the ids are fetched
# in batches of 50
BATCH = 50


def log(msg):
    print(msg, flush=True)


def load_tiles():
    """Read the cached tiles into a node/way/relation set."""
    files = sorted(glob.glob(os.path.join(TILES, "tile_*.xml")))
    if not files:
        raise SystemExit(f"no cached tiles under {TILES} - run "
                         "fetch_osm_coastline_api.py first")
    nodes = {}
    ways = {}
    rels = {}
    for f in files:
        s = open(f, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r'<node id="(\d+)"[^>]*lat="([-\d.]+)" '
                             r'lon="([-\d.]+)"', s):
            nodes[m.group(1)] = (float(m.group(3)), float(m.group(2)))
        for m in re.finditer(r'<way\b([^>]*)>(.*?)</way>', s, re.S):
            idm = re.search(r'\bid="(\d+)"', m.group(1))
            if not idm:
                continue
            nd = re.findall(r'<nd ref="(\d+)"', m.group(2))
            if len(nd) >= 2:
                ways[idm.group(1)] = nd
        for m in re.finditer(r'<relation id="(\d+)"[^>]*>(.*?)</relation>',
                             s, re.S):
            rid = m.group(1)
            body = m.group(2)
            tags = dict(re.findall(r'<tag k="([^"]+)" v="([^"]*)"', body))
            mem = re.findall(
                r'<member type="(\w+)" ref="(\d+)" role="(\w+)"/>', body)
            if rid not in rels:
                rels[rid] = (tags, mem)
    log(f"  {len(files)} tiles: {len(nodes)} nodes, {len(ways)} ways, "
        f"{len(rels)} relations")
    return nodes, ways, rels


def fetch_ways(ids):
    """Fetch the given way ids, in batches, with retries. Returns the count
    newly written."""
    os.makedirs(WAYS_DIR, exist_ok=True)
    written = 0
    for wid in ids:
        # /way/<id>/full returns the way TOGETHER WITH ITS NODES AND THEIR
        # COORDINATES. The bulk endpoint /ways?ways=... returns the ways
        # with only <nd ref>, so the geometry cannot be resolved from it -
        # this endpoint is the one that works.
        url = f"{API}/way/{wid}/full"
        xml = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    xml = r.read().decode("utf-8", "ignore")
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 20 * (attempt + 1)
                    log(f"      429 rate limited, waiting {wait}s")
                    time.sleep(wait)
                    continue
                if e.code in (404, 410):
                    log(f"      way {wid}: HTTP {e.code}, gone from OSM")
                    xml = None
                    break
                log(f"      way {wid}: HTTP {e.code}, retrying")
                time.sleep(10 * (attempt + 1))
            except Exception as exc:
                log(f"      way {wid}: {exc}, retrying")
                time.sleep(10 * (attempt + 1))
        else:
            log(f"      way {wid}: failed after 4 attempts")
            continue
        if xml is None:
            continue

        coord = {}
        for m in re.finditer(
                r'<node\b[^>]*\bid="(\d+)"[^>]*lat="([-\d.]+)"'
                r'[^>]*lon="([-\d.]+)"', xml):
            coord[m.group(1)] = (float(m.group(2)), float(m.group(3)))
        wm = re.search(r'<way\b([^>]*)>(.*?)</way>', xml, re.S)
        if not wm:
            log(f"      way {wid}: no way element in the response")
            continue
        body = wm.group(2)
        nd = re.findall(r'<nd ref="(\d+)"', body)
        if len(nd) < 2:
            log(f"      way {wid}: fewer than 2 nodes")
            continue
        if sum(1 for n in nd if n in coord) < 2:
            log(f"      way {wid}: fewer than 2 nodes with coordinates")
            continue
        tags = re.findall(r'<tag k="([^"]+)" v="([^"]*)"', body)
        out = os.path.join(WAYS_DIR, f"way_{wid}.xml")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            fh.write('<osm version="0.6" generator="hermes">\n')
            # the nodes, with their coordinates
            for n in nd:
                if n in coord:
                    lat, lon = coord[n]
                    fh.write(f'  <node id="{n}" lat="{lat}" lon="{lon}"/>\n')
            fh.write(f'  <way id="{wid}">\n')
            for t in tags:
                fh.write(f'    <tag k="{t[0]}" v="{t[1]}"/>\n')
            for n in nd:
                fh.write(f'    <nd ref="{n}"/>\n')
            fh.write("  </way>\n</osm>\n")
        written += 1
        time.sleep(2)
    log(f"  wrote {written} way files")
    return written


def main():
    log("=== 1. read the cached tiles ===")
    nodes, ways, rels = load_tiles()

    log("")
    log("=== 2. find the Hong Kong boundary relations ===")
    for rid in sorted(HK_REL_IDS):
        if rid in rels:
            tags, mem = rels[rid]
            log(f"  relation {rid}: {tags.get('name', '')} "
                f"(admin_level={tags.get('admin_level')}), {len(mem)} members")
        else:
            log(f"  relation {rid}: NOT in the cached tiles")

    # the outer ring members of the two relations
    member_ways = set()
    for rid in HK_REL_IDS:
        if rid not in rels:
            continue
        tags, mem = rels[rid]
        for mtype, ref, role in mem:
            if mtype == "way" and role in ("outer", ""):
                member_ways.add(ref)
    log(f"  {len(member_ways)} member way ids to check")

    log("")
    log("=== 3. work out which are missing ===")
    have = set(ways.keys())
    for f in glob.glob(os.path.join(WAYS_DIR, "way_*.xml")):
        s = open(f, encoding="utf-8", errors="ignore").read()
        m = re.search(r'<way\b[^>]*\bid="(\d+)"', s)
        if m:
            have.add(m.group(1))
    missing = sorted(member_ways - have)
    log(f"  {len(have)} ways have, {len(missing)} of {len(member_ways)} missing")

    if not missing:
        log("  nothing to fetch - the boundary is complete")
        return 0

    log("")
    log("=== 4. fetch the missing ways by ID ===")
    written = fetch_ways(missing)
    log(f"  wrote {written} way files")

    log("")
    log("=== 5. verify ===")
    # The member ways can live in EITHER the tiles OR the fetched directory,
    # so the check has to read both before it can say anything is missing.
    present = set(ways.keys())
    for f in glob.glob(os.path.join(WAYS_DIR, "way_*.xml")):
        s = open(f, encoding="utf-8", errors="ignore").read()
        m = re.search(r'<way\b[^>]*\bid="(\d+)"', s)
        if m:
            present.add(m.group(1))
    still = sorted(member_ways - present)
    log(f"  {len(member_ways) - len(still)} of {len(member_ways)} member ways "
        f"now present")
    if still:
        log(f"  still missing {len(still)}: {still[:20]}")
        return 1
    log("  the Hong Kong boundary is complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
