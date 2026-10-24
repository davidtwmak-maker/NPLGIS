#!/usr/bin/env python3
"""Stitch iB1000 shoreline segments into closed rings with a union-find over endpoints."""
import json
import math
import os
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
TOL = 0.0004  # ~40 m at HK latitude

fs = json.load(open(os.path.join(D, "raw", "shoreline_ib1000.geojson")))["features"]
segs = []
for f in fs:
    g = f.get("geometry")
    if not g:
        continue
    parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
    for p in parts:
        if len(p) >= 2:
            segs.append([(c[0], c[1]) for c in p])
print("segments:", len(segs))


def key(pt, tol):
    return (round(pt[0] / tol), round(pt[1] / tol))


# bucket endpoints on a grid, then union segments whose ends fall in the same cell
parent = list(range(len(segs)))


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra


grid = defaultdict(list)
for i, s in enumerate(segs):
    for pt in (s[0], s[-1]):
        grid[key(pt, TOL)].append((i, pt))

pairs = 0
for cell, items in grid.items():
    for x in range(len(items)):
        for y in range(x + 1, len(items)):
            (i, pi), (j, pj) = items[x], items[y]
            if find(i) == find(j):
                continue
            if (pi[0] - pj[0]) ** 2 + (pi[1] - pj[1]) ** 2 <= TOL * TOL:
                union(i, j)
                pairs += 1
print("endpoint unions:", pairs)

groups = defaultdict(list)
for i in range(len(segs)):
    groups[find(i)].append(segs[i])
print("connected groups:", len(groups))

# within each group, chain the segments by walking from an endpoint
chains = []
for gid, group in groups.items():
    pool = list(group)
    while pool:
        cur = pool.pop()
        progress = True
        while progress and pool:
            progress = False
            for j, cand in enumerate(pool):
                for a, b in ((cand[0], cand[-1]), (cand[-1], cand[0])):
                    for x, y in ((cur[-1], a), (cur[-1], b)):
                        if math.hypot(x[0] - y[0], x[1] - y[1]) <= TOL:
                            cur = cur + (cand if y is a else cand[::-1])
                            pool.pop(j)
                            progress = True
                            break
                    if progress:
                        break
                if progress:
                    break
        chains.append(cur)

closed = [c for c in chains if math.hypot(c[0][0] - c[-1][0], c[0][1] - c[-1][1]) <= TOL]
print(f"chains: {len(chains)}  closed rings: {len(closed)}")
tot = sum(len(c) for c in chains)
print(f"total vertices: {tot}")

# are the closed rings real land outlines? check one against a known shore point
if closed:
    biggest = max(closed, key=len)
    xs = [p[0] for p in biggest]
    ys = [p[1] for p in biggest]
    print(f"largest ring: {len(biggest)} pts  lon {min(xs):.4f}..{max(xs):.4f}  lat {min(ys):.4f}..{max(ys):.4f}")

out = os.path.join(D, "raw", "shoreline_chains.json")
json.dump({"chains": chains, "closed_count": len(closed),
           "chain_count": len(chains), "tol": TOL}, open(out, "w"))
print("wrote", out)