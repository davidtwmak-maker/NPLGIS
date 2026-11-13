#!/usr/bin/env python3
"""
Assemble the cached OSM coastline tiles into one coastline file.

The OSM API fetch caches every successful chunk under raw/osm_tiles/. This
script walks that cache, pulls out the natural=coastline ways and writes
raw/osm_coastline_api.json as a list of coordinate lists, each way's
points in order.

The node ids are preserved in the output so the ways can be chained by
their shared endpoints (which is how the coastline is closed into rings).

Run:  python3 assemble_osm_coastline.py
"""
import glob
import json
import os
import re
import sys

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
TILES = os.path.join(RAW, "osm_tiles")
OUTJ = os.path.join(RAW, "osm_coastline_api.json")

NODE_RE = re.compile(r'<node id="(\d+)"[^>]*lat="([-\d.]+)" lon="([-\d.]+)"')
WAY_RE = re.compile(r'<way\b[^>]*>(.*?)</way>', re.S)
TAG_RE = re.compile(r'<tag k="([^"]+)" v="([^"]*)"')
ND_RE = re.compile(r'<nd ref="(\d+)"')


def main():
    files = sorted(glob.glob(os.path.join(TILES, "tile_*.xml")))
    if not files:
        raise SystemExit(f"no cached tiles under {TILES}")
    print(f"{len(files)} cached tiles")

    nodes = {}
    ways = []
    for f in files:
        s = open(f, encoding="utf-8", errors="ignore").read()
        for m in NODE_RE.finditer(s):
            nid = m.group(1)
            if nid not in nodes:
                nodes[nid] = (float(m.group(3)), float(m.group(2)))
        for block in WAY_RE.finditer(s):
            tags = dict(TAG_RE.findall(block.group(1)))
            if tags.get("natural") != "coastline":
                continue
            nd = ND_RE.findall(block.group(1))
            if len(nd) >= 2:
                ways.append(nd)

    print(f"{len(nodes)} nodes, {len(ways)} coastline ways")

    # a way whose node ids appear in two tiles is a way split by the tile
    # grid; OSM returns whole ways, so this should not happen, but drop
    # any way that lost its geometry
    out = []
    dropped = 0
    for w in ways:
        pts = [nodes[r] for r in w if r in nodes]
        if len(pts) != len(w) or len(pts) < 2:
            dropped += 1
            continue
        out.append(pts)
    print(f"{len(out)} ways with full geometry ({dropped} dropped)")

    json.dump(out, open(OUTJ, "w"))
    print(f"wrote {OUTJ} ({os.path.getsize(OUTJ):,} bytes)")

    # the chain test the mask builder relies on
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    key2id = {}
    ids = []
    for pts in out:
        row = []
        for p in pts:
            k = (round(p[0], 7), round(p[1], 7))
            if k not in key2id:
                key2id[k] = len(key2id)
            row.append(key2id[k])
        ids.append(row)
    for row in ids:
        union(row[0], row[-1])
    groups = {}
    for i, row in enumerate(ids):
        groups.setdefault(find(row[0]), []).append(i)
    print(f"{len(groups)} chains")


if __name__ == "__main__":
    main()
