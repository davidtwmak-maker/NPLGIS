#!/usr/bin/env python3
"""Why did a shop get no building match, or a wrong one?

Re-runs the geocoder's own search for one shop and prints every hit it
returned, with the token score the geocoder would give each one. This
is the tool for answering "the geocode failed - was there a hit at
all, and did the token match it?"

Usage:  why_no_match.py <name-substring>
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geocode_shops as G

SCRAPE = HERE / "baw_shops.csv"


def main():
    needle = sys.argv[1]
    rows = list(csv.DictReader(open(SCRAPE, encoding="utf-8")))
    hits = [r for r in rows if needle.lower() in (r.get("name") or "").lower()]
    if not hits:
        print(f"no source row matching {needle!r}")
        return 1
    cache = G.load_cache()
    for r in hits:
        name = r.get("name")
        addr = r.get("address_zh") or r.get("address") or ""
        toks = G.building_tokens(addr)
        print(f"\n=== {name} ===")
        print(f"  address: {addr}")
        print(f"  tokens:  {sorted(toks)}")
        seen = set()
        for kw in G.query_variants(addr, name):
            if kw in seen:
                continue
            seen.add(kw)
            res, err = G.geocode(kw, cache)
            if err:
                print(f"  query {kw!r} -> ERROR {err}")
                continue
            print(f"  query {kw!r} -> {len(res)} hits")
            for h in res[:5]:
                cn, en = h.get("cname"), h.get("ename")
                sc = max((G.token_quality(t, cn, en) for t in toks), default=-1000.0)
                best = (max(toks, key=lambda t: G.token_quality(t, cn, en))
                        if toks else None)
                print(f"      cname={cn!r} ename={en!r}")
                print(f"      addr={h.get('caddress')!r} score={sc:.0f} via {best!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
