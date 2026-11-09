#!/usr/bin/env python3
"""
Merge the clipped coastline fragments from the cached OSM boxes into
complete ways.

THE BUG THIS FIXES:  the OSM /map endpoint returns ways CLIPPED to the
requested bbox.  A coastline way that crosses a box edge therefore comes
back as two fragments, each with the same way id but different node
sequences.  Collecting them with `all_ways[wid] = fragment` keeps only
the LAST fragment seen, so most of the coastline was silently discarded -
leaving gaps in the barrier, which is why the flood-fill leaked and the
harbour came out as land.

THE FIX:  keep every fragment per way id, then splice the fragments
together by matching their endpoint nodes.  The result is the complete
way, reconstructed across box boundaries.
"""
import json
import os
from collections import defaultdict

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
CACHE = f"{GIS_DATA}/HK Camping Sites/_osm_box_cache"
OUT = f"{GIS_DATA}/HK Camping Sites/_coast_ways.json"
# Bounding box of the study area
LON0, LON1 = 113.74, 114.48
LAT0, LAT1 = 22.10, 22.58


def main():
    frags = defaultdict(list)      # way id -> list of (refs, tags)
    nodes = {}                     # node id -> (lon, lat)

    files = sorted(os.listdir(CACHE))
    print(f"{len(files)} cached boxes")
    for fn in files:
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(CACHE, fn)) as f:
            d = json.load(f)
        nodes.update(d["nodes"])
        for wid, w in d["ways"].items():
            frags[wid].append((w["refs"], w["tags"]))

    print(f"{len(frags)} distinct ways, {sum(len(v) for v in frags.values())} fragments")

    # Only coastline ways matter.
    # NOTE: each fragment is stored as (refs, tags), so the tag dict is
    # the SECOND element.  Reading t.get("tags") looks inside the tags
    # for a key called "tags" and finds nothing.
    coast_ids = [wid for wid, fl in frags.items()
                 if any(tags.get("natural") == "coastline"
                        for _, tags in fl)]
    print(f"{len(coast_ids)} coastline ways")

    def nkey(nid):
        p = nodes.get(nid)
        if p is None:
            return None
        return (round(p[0], 7), round(p[1], 7))

    full = []
    for wid in coast_ids:
        # gather fragments of this way
        fl = frags[wid]
        # a fragment may itself be a list of node sequences if the box
        # clipped it in the middle; treat each ref-list as one piece
        pieces = []
        for refs, tags in fl:
            if refs:
                pieces.append(list(refs))
        if not pieces:
            continue

        # Splice pieces by matching endpoints.
        merged = pieces[0]
        remaining = pieces[1:]
        changed = True
        while remaining and changed:
            changed = False
            for i, p in enumerate(remaining):
                if p[0] == merged[-1]:
                    merged += p[1:]
                elif p[-1] == merged[-1]:
                    merged += list(reversed(p))[1:]
                elif p[-1] == merged[0]:
                    merged = list(reversed(p))[:-1] + merged
                elif p[0] == merged[0]:
                    merged = p[1:] + merged
                else:
                    continue
                remaining.pop(i)
                changed = True
                break
        if remaining:
            # could not splice them all - keep the longest piece and
            # treat the rest as separate fragments
            merged = max([merged] + remaining, key=len)
            for p in remaining:
                if p is not merged and len(p) > 1:
                    full.append((wid, p, None))
        full.append((wid, merged, None))

    # Build coordinate lists, dropping pieces whose nodes are missing.
    ways = []
    for wid, refs, _ in full:
        pts = []
        ok = True
        for nid in refs:
            p = nodes.get(nid)
            if p is None:
                ok = False
                break
            pts.append([p[0], p[1]])
        if ok and len(pts) >= 2:
            ways.append(pts)

    print(f"{len(ways)} coastline segments with complete coordinates")

    # Report how well they close.
    ends = defaultdict(int)
    for w in ways:
        ends[(round(w[0][0], 7), round(w[0][1], 7))] += 1
        ends[(round(w[-1][0], 7), round(w[-1][1], 7))] += 1
    d1 = sum(1 for v in ends.values() if v == 1)
    print(f"endpoints with degree 1 (gaps): {d1}")
    print(f"distinct endpoints: {len(ends)}")

    with open(OUT, "w") as f:
        json.dump(ways, f)
    print("wrote", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
