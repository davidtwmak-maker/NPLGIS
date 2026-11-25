#!/usr/bin/env python3
"""Why did a shop match the building it did?

Prints the token, the score, and the competing candidates for one shop,
so a match can be judged rather than guessed at.

Usage:  why_this_match.py <name-substring>
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geocode_shops as G


def main():
    needle = sys.argv[1]
    rows = list(csv.DictReader(open(HERE / "baw_shops.csv", encoding="utf-8")))
    cache = G.load_cache()
    for r in rows:
        if needle.lower() not in (r.get("name") or "").lower():
            continue
        name = r.get("name")
        addr = (r.get("address_zh") or "").strip()
        pin = (float(r["lat"]) if r.get("lat") else None,
               float(r["lng"]) if r.get("lng") else None)
        toks = G.building_tokens(addr, name)
        print(f"\n=== {name} ===")
        print(f"  address: {addr}")
        print(f"  pin: {pin}")
        print(f"  tokens: {sorted(toks)}")
        for q in G.query_variants(addr, name):
            hits, _ = G.geocode(q, cache)
            if not hits:
                continue
            print(f"  query {q!r} -> {len(hits)} hits")
            for h in hits[:12]:
                cn, en = h.get("cname"), h.get("ename")
                best = None
                for t in toks:
                    q_ = G.token_quality(t, cn, en)
                    if q_ > 0 and (best is None or q_ > best[1]):
                        best = (t, q_)
                if best:
                    print(f"      {str(cn)[:20]:22} {str(en)[:22]:24} "
                          f"type={str(h.get('type')):4} score={best[1]:6.0f} "
                          f"via {best[0]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
