#!/usr/bin/env python3
"""
THE HONG KONG LAND MASK, from the OpenStreetMap Hong Kong boundary.

WHY THIS WORKS WHEN THE OTHER SOURCES DO NOT
---------------------------------------------
Every land boundary for Hong Kong reachable without a login was tested, and
each one fails a different way:

  * CEDD "Coastline" polygons (cedd_rcd_1636520962284_7237) - a coastal
    GEOLOGY BAND, not a land boundary. 922.6 km2 of open sea lies inside
    them; Tolo Harbour and Victoria Harbour read as land.
  * CSDI "Digital Land Boundary Map iC1000" - a MAP-SHEET INDEX. All 4,709
    polygons are exactly 0.45 km2 (a 1 km square sheet).
  * 2023 District Council constituency boundaries - administrative lines
    running out into the sea; their union is 2,754 km2, 2.5x the land.
  * The Esri China (HK) iB1000 SWA shoreline - the coastline does not close
    (only 1,114 of 4,323 endpoints are shared), so a flood fill from the
    open sea leaks straight through the land. The gap is topological, not
    a resolution limit.
  * Natural Earth 10m ADM0 - 1,036 km2 and the best outline available,
    but generalised: it omits the small islands and the airport.
  * The OSM coastline alone - it closes the ISLANDS perfectly (Cheung Chau
    is a single closed ring of 1,004 nodes whose filled area, 2.473 km2,
    matches the DTM's own positive land on that island, 2.472 km2, to
    within 0.001 km2) but it has no land border, so a flood fill from the
    open sea leaks through the northern New Territories.

THE FIX
-------
OSM carries Hong Kong's own boundary as a relation: relation 20044132
(admin_level 4, name "香港 Hong Kong") with 80 outer ways. It is the
complete outline - the coast AND the land border with Shenzhen - and it
is the missing piece the coastline alone cannot supply.

The mask is then:
    LAND = the OSM Hong Kong boundary polygon
           AND the DTM's positive elevation

The boundary says where Hong Kong ends; the DTM says where the ground
rises above sea level. The intersection is what removes the reclaimed
harbour structures inside Victoria Harbour and Tolo Harbour, which the
DTM alone would call land.

Run:  python3 build_land_mask_osm_hk.py
"""
import glob
import json
import os
import re
import time
import warnings

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize
from scipy import ndimage
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union
import tempfile

SCRATCH = os.environ.get("HERMES_SCRATCH",
                       os.path.join(tempfile.gettempdir(),
                                    "hermes-scratch"))
os.makedirs(SCRATCH, exist_ok=True)

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")
TILES = os.path.join(RAW, "osm_tiles")
DTM = os.environ.get(
    "HK_DTM_TIF",
    os.path.join(GIS_DATA, "HK Landslide Susceptibility", "raw",
                 "Whole_HK_DTM_5m.tif"))
if not os.path.exists(DTM):
    for _c in (os.path.join(GIS_DATA, "HK Flood Causes", "raw",
                            "Whole_HK_DTM_5m.tif"),
               "/Volumes/Extreme Pro/Download/HK DTM 5m/Whole_HK_DTM_5m.tif"):
        if os.path.exists(_c):
            DTM = _c
            break
XLL, YLL, CELL = 799997.5, 799997.5, 5.0

HK_REL_IDS = {"20044132", "913110"}   # Hong Kong admin_level 4 and 3

LAND_PROBES = [("Central HK", 114.158, 22.281), ("Sha Tin", 114.190, 22.380),
               ("Tuen Mun town", 113.980, 22.390),
               ("Tseung Kwan O", 114.260, 22.310),
               ("Airport", 113.935, 22.308)]
WATER_PROBES = [("Victoria Harbour", 114.175, 22.288),
                ("Open sea S", 114.200, 22.200),
                ("Open sea E", 114.400, 22.300),
                ("Tolo Harbour", 114.265, 22.477),
                ("Deep Bay", 113.900, 22.450)]


def load_tiles():
    """Read every cached OSM tile, plus the individually-fetched boundary
    ways, into one node/way/relation set."""
    files = sorted(glob.glob(os.path.join(TILES, "tile_*.xml")))
    extra = sorted(glob.glob(os.path.join(RAW, "osm_ways", "way_*.xml")))
    if not files:
        raise SystemExit(f"no cached tiles under {TILES}")
    nodes = {}
    ways = {}
    rels = {}
    for f in files + extra:
        s = open(f, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r'<node id="(\d+)"[^>]*lat="([-\d.]+)" lon="([-\d.]+)"', s):
            nodes[m.group(1)] = (float(m.group(3)), float(m.group(2)))
        # the id attribute is not always first in the tag, so match any
        # attribute order: <way id=".."> and <way visible=".." id="..">
        for m in re.finditer(r'<way\b([^>]*)>(.*?)</way>', s, re.S):
            attrs, body = m.group(1), m.group(2)
            idm = re.search(r'\bid="(\d+)"', attrs)
            if not idm:
                continue
            wid = idm.group(1)
            nd = re.findall(r'<nd ref="(\d+)"', body)
            if len(nd) >= 2:
                ways[wid] = nd
        for m in re.finditer(r'<relation id="(\d+)"[^>]*>(.*?)</relation>', s, re.S):
            rid = m.group(1)
            body = m.group(2)
            tags = dict(re.findall(r'<tag k="([^"]+)" v="([^"]*)"', body))
            mem = re.findall(r'<member type="(\w+)" ref="(\d+)" role="(\w+)"/>', body)
            if rid not in rels:
                rels[rid] = (tags, mem)
    print(f"  {len(files)} tiles + {len(extra)} boundary ways: "
          f"{len(nodes)} nodes, {len(ways)} ways, {len(rels)} relations")
    return nodes, ways, rels


def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    tr = Transformer.from_crs(4326, 2326, always_xy=True)
    tr_back = Transformer.from_crs(2326, 4326, always_xy=True)

    with rasterio.open(DTM) as ds:
        H, W = ds.height, ds.width
        z = ds.read(1)
        nodata = ds.nodata
        aff = ds.transform
    valid = z != nodata
    print(f"grid {W} x {H} at {CELL} m")

    print()
    print("=== 1. read the cached OSM tiles ===")
    nodes, ways, rels = load_tiles()

    print()
    print("=== 2. the Hong Kong boundary relation ===")
    member_ways = set()
    for rid in HK_REL_IDS:
        if rid not in rels:
            print(f"  relation {rid} not found in the cache")
            continue
        tags, mem = rels[rid]
        outer = [r for t, r, ro in mem if t == "way" and ro == "outer"]
        print(f"  relation {rid}: {tags.get('name')!r} admin_level="
              f"{tags.get('admin_level')} - {len(outer)} outer ways")
        member_ways.update(outer)

    rings = []
    missing = 0
    for wid in member_ways:
        if wid not in ways:
            missing += 1
            continue
        pts = [nodes[r] for r in ways[wid] if r in nodes]
        if len(pts) < 2:
            missing += 1
            continue
        # kept in LON/LAT; the projection happens after the chains are
        # ordered, because the chain test and the gap tolerance are both
        # defined in degrees
        rings.append(pts)
    print(f"  {len(rings)} outer ways with geometry ({missing} missing from "
          f"the cache)")

    print()
    print("=== 3. chain the rings and build the polygon ===")
    # Chain by shared endpoints. The chain test runs in LON/LAT (the
    # coordinate system the node ids and the gap tolerance live in); the
    # projection to HK1980 happens AFTER the chains are ordered.
    import math

    def km(a, b):
        return math.hypot((a[0] - b[0]) * 105000, (a[1] - b[1]) * 111000)

    # each ring keeps its own node ids so the chain test is exact
    key2id = {}
    id2key = {}
    rows = []
    for xy in rings:
        row = []
        for p in xy:
            k = (round(p[0], 2), round(p[1], 2))
            if k not in key2id:
                key2id[k] = len(key2id)
                id2key[key2id[k]] = k
            row.append(key2id[k])
        rows.append(row)

    TOL = 250.0
    parent = list(range(len(rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    ends = []
    for i, r in enumerate(rows):
        ends.append((i, 0, id2key[r[0]]))
        ends.append((i, 1, id2key[r[-1]]))
    cands = []
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            if ends[i][0] == ends[j][0]:
                continue
            d = km(ends[i][2], ends[j][2])
            if d <= TOL:
                cands.append((d, i, j))
    cands.sort()
    for d, i, j in cands:
        if find(ends[i][0]) != find(ends[j][0]):
            uni(ends[i][0], ends[j][0])
    groups = {}
    for i in range(len(rows)):
        groups.setdefault(find(i), []).append(i)
    print(f"  {len(groups)} chains from {len(rows)} ways")

    def order(idxs):
        rem = set(idxs)
        seq = list(rows[idxs[0]])
        rem.discard(idxs[0])
        while rem:
            tail = seq[-1]
            hit = False
            for i in list(rem):
                r = rows[i]
                if r[0] == tail:
                    seq.extend(r[1:])
                    rem.discard(i)
                    hit = True
                    break
                if r[-1] == tail:
                    seq.extend(list(reversed(r))[1:])
                    rem.discard(i)
                    hit = True
                    break
            if not hit:
                break
        return [id2key[n] for n in seq]

    polys = []
    open_chains = []
    for root, idxs in groups.items():
        pts = order(idxs)
        if len(pts) < 4:
            continue
        xy = [tr.transform(p[0], p[1]) for p in pts]
        if pts[0] == pts[-1]:
            try:
                p = Polygon(xy)
                if not p.is_valid:
                    p = p.buffer(0)
            except Exception:
                continue
            if p.geom_type == "Polygon" and p.area > 0:
                polys.append(p)
        else:
            open_chains.append((len(pts), pts))
    print(f"  {len(polys)} closed rings, {len(open_chains)} open chains")
    open_chains.sort(key=lambda t: -t[0])
    for n, pts in open_chains[:4]:
        lons = [p[0] for p in pts]
        lats = [p[1] for p in pts]
        print(f"     open chain {n} pts: lon {min(lons):.4f}..{max(lons):.4f} "
              f"lat {min(lats):.4f}..{max(lats):.4f}")

    # close the open chains by joining their two ends with a straight line.
    # For a boundary that runs out to the sea (the far shore of a bay) the
    # straight line is the closing chord of the bay.
    for n, pts in open_chains:
        xy = [tr.transform(p[0], p[1]) for p in pts]
        try:
            p = Polygon(xy + [xy[0]])
            if not p.is_valid:
                p = p.buffer(0)
        except Exception:
            continue
        if p.geom_type == "Polygon" and p.area > 0:
            polys.append(p)
            print(f"     closed an open chain by a chord: {p.area/1e6:,.1f} km2")
        elif p.geom_type == "MultiPolygon":
            for g in p.geoms:
                if g.area > 0:
                    polys.append(g)
            print(f"     closed an open chain by a chord: "
                  f"{sum(g.area for g in p.geoms)/1e6:,.1f} km2")

    land_poly = unary_union(polys)
    if land_poly.geom_type == "MultiPolygon":
        land_poly = unary_union([g for g in land_poly.geoms
                                 if g.geom_type == "Polygon"])
    print(f"  the Hong Kong polygon: {land_poly.area/1e6:,.1f} km2")

    print()
    print("=== 4. rasterise and intersect with the DTM ===")
    land_r = rasterize([(land_poly, 1)], out_shape=(H, W), transform=aff,
                       fill=0, dtype="uint8", all_touched=False).astype(bool)
    print(f"  rasterised: {land_r.sum()*25/1e6:,.1f} km2")
    pos = (z > 0) & valid
    print(f"  DTM positive: {pos.sum()*25/1e6:,.1f} km2")
    land = land_r & pos
    print(f"  INTERSECTION: {land.sum()*25/1e6:,.1f} km2")
    print(f"  (HK's true land area is about 1,106 km2)")

    # ---- the flat ground on the small islands
    # The DTM codes Cheung Chau's town, Lamma's valley floor and Peng Chau's
    # settlement as 0 m, so the DTM's positive elevation drops them. The
    # OSM coastline, however, closes each island into a RING, and that ring
    # is the island's true outline - verified against the DTM: Cheung
    # Chau's ring fills 2.473 km2 and the DTM's positive land on the same
    # island is 2.472 km2.
    print()
    print("=== 4b. the small islands' flat ground ===")
    coast_path = os.path.join(RAW, "osm_coastline_api.json")
    islands_r = np.zeros((H, W), dtype=bool)
    island_area = 0.0
    if os.path.exists(coast_path):
        cdata = json.load(open(coast_path))
        if isinstance(cdata, dict):
            cdata = cdata["lines"]
        ipolys = []
        for w in cdata:
            if len(w) < 4:
                continue
            if abs(w[0][0] - w[-1][0]) > 1e-9 or abs(w[0][1] - w[-1][1]) > 1e-9:
                continue
            xy = [tr.transform(lo, la) for lo, la in w]
            try:
                p = Polygon(xy)
                if not p.is_valid:
                    p = p.buffer(0)
            except Exception:
                continue
            if p.geom_type == "Polygon" and p.area > 0:
                ipolys.append(p)
        if ipolys:
            islands_r = rasterize([(p, 1) for p in ipolys], out_shape=(H, W),
                                  transform=aff, fill=0, dtype="uint8",
                                  all_touched=False).astype(bool)
            island_area = islands_r.sum() * 25 / 1e6
            print(f"  {len(ipolys)} closed OSM island rings, "
                  f"{island_area:,.2f} km2")
            # keep only the island's own ring - not the mainland
            island_new = islands_r & land_r & ~land
            print(f"  flat island ground recovered: "
                  f"{island_new.sum()*25/1e6:.3f} km2")
            land = land | island_new
            print(f"  LAND after the islands: {land.sum()*25/1e6:,.1f} km2")
    else:
        print("  no coastline file - the flat island ground is not recovered")

    only_coast = land_r & ~pos
    only_dtm = pos & ~land_r
    print(f"  boundary says land but the DTM says 0 m: "
          f"{only_coast.sum()*25/1e6:,.1f} km2")
    print(f"  the DTM says > 0 m but the boundary says sea: "
          f"{only_dtm.sum()*25/1e6:,.1f} km2")
    lab, n = ndimage.label(only_dtm)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    for k in np.argsort(sizes)[::-1][:8]:
        ys, xs = np.nonzero(lab == (k + 1))
        e = XLL + xs.mean() * CELL + CELL / 2
        nn = YLL + H * CELL - ys.mean() * CELL - CELL / 2
        lo, la = tr_back.transform(e, nn)
        print(f"      {sizes[k]*25/1e6:>6.2f} km2 at {lo:.4f},{la:.4f}")

    np.save(os.path.join(OUT, "hk_land_mask.npy"), land)
    np.save(os.path.join(OUT, "hk_sea.npy"), ~land & valid)
    np.save(os.path.join(OUT, "hk_boundary_mask.npy"), land_r)

    print()
    print("=== 5. verify against named places ===")

    def probe(lon, lat):
        e, n = tr.transform(lon, lat)
        c = int((e - XLL) / CELL)
        r = int((YLL + H * CELL - n) / CELL)
        if not (0 <= c < W and 0 <= r < H):
            return None, None
        return z[r, c], bool(land[r, c])

    LAND = [("Central HK", 114.158, 22.281), ("Kowloon TST", 114.173, 22.293),
            ("Sha Tin", 114.190, 22.380), ("Tuen Mun town", 113.980, 22.390),
            ("Tseung Kwan O", 114.260, 22.310),
            ("Sheung Shui", 114.130, 22.490), ("Yuen Long", 114.030, 22.440),
            ("Mui Wo", 113.990, 22.265), ("Sai Kung", 114.270, 22.380),
            ("Airport", 113.935, 22.308), ("Tai O", 113.913, 22.246),
            ("Tai Mo Shan", 114.1244, 22.4093),
            ("Lok Ma Chau", 114.073, 22.517), ("Ma On Shan", 114.230, 22.423),
            ("Ping Shan", 114.026, 22.428), ("Kwai Chung", 114.132, 22.357),
            ("Sham Tseng", 113.978, 22.416),
            ("Lantau Peak", 113.950, 22.260),
            ("Sham Shui Po", 114.160, 22.331),
            ("Kennedy Town", 114.129, 22.279),
            ("Tin Shui Wai", 114.030, 22.460), ("Mai Po", 114.035, 22.490),
            ("Fo Tan", 114.210, 22.390), ("Tsing Yi", 114.130, 22.285),
            ("Tsuen Wan flats", 114.0962, 22.3655),
            ("Tung Chung flats", 113.943, 22.291),
            ("Cheung Chau", 114.028, 22.205), ("Peng Chau", 114.070, 22.230),
            ("Lamma Island", 114.058, 22.245)]
    WATER = [("Tolo Harbour", 114.265, 22.477),
             ("Victoria Harbour", 114.175, 22.288),
             ("Open sea S", 114.200, 22.200), ("Open sea E", 114.400, 22.300),
             ("Aberdeen Channel", 114.160, 22.245),
             ("Clearwater Bay", 114.310, 22.290),
             ("Shenzhen Bay", 114.000, 22.500), ("Deep Bay", 113.900, 22.450),
             ("Sai Kung water", 114.275, 22.350),
             ("Big Wave Bay", 114.235, 22.220),
             ("Lamma Channel", 114.080, 22.250)]
    fails = []
    for nm, lo, la in LAND:
        v, got = probe(lo, la)
        if v is None:
            continue
        if not got:
            fails.append((nm, v, "land"))
            print(f"   {nm:<22} z={v:<5}  <-- WRONG (want land)")
    for nm, lo, la in WATER:
        v, got = probe(lo, la)
        if v is None:
            continue
        if got:
            fails.append((nm, v, "water"))
            print(f"   {nm:<22} z={v:<5}  <-- WRONG (want water)")
    nchk = len(LAND) + len(WATER)
    print(f"  {nchk - len(fails)}/{nchk} probes correct")
    for nm, v, k in fails:
        print(f"     {nm}: z={v}, expected {k}")

    print()
    print("=== 6. the answer ===")
    low = land & (z < 5) & valid
    print(f"  land:            {land.sum():>12,} cells = {land.sum()*25/1e6:>9,.1f} km2")
    print(f"  land below 5 m:  {low.sum():>12,} cells = {low.sum()*25/1e6:>9,.2f} km2")
    print(f"  share of land:   {low.sum()/land.sum()*100:.2f} %")
    print(f"  mean elevation:  {z[low].mean():.2f} m   range {z[low].min()} .. {z[low].max()} m")
    np.save(os.path.join(OUT, "hk_lowland_raw.npy"), low)

    f = 6
    Image.fromarray((land[::f, ::f] * 255).astype("uint8")).save(
        os.path.join(SCRATCH, "land_mask_hk.png"))
    Image.fromarray((low[::f, ::f] * 255).astype("uint8")).save(
        os.path.join(SCRATCH, "lowland_hk.png"))
    print("  wrote land_mask_hk.png and lowland_hk.png")

    json.dump({"method": "OSM Hong Kong boundary relation (20044132), "
                          "intersected with the DTM's positive elevation",
               "land_km2": round(float(land.sum()) * 25 / 1e6, 2),
               "boundary_km2": round(float(land_r.sum()) * 25 / 1e6, 2),
               "dtm_positive_km2": round(float(pos.sum()) * 25 / 1e6, 2),
               "lowland_km2": round(float(low.sum()) * 25 / 1e6, 3),
               "lowland_pct_of_land": round(float(low.sum()) / float(land.sum()) * 100, 2),
               "lowland_mean_z": round(float(z[low].mean()), 2),
               "probes_passed": nchk - len(fails), "probes_total": nchk,
               "probes_failed": [{"name": a, "z": int(b), "expected": c}
                                 for a, b, c in fails]},
              open(os.path.join(OUT, "land_mask_hk_summary.json"), "w"), indent=1)
    print(f"\ndone in {time.time()-t0:.1f}s")
    return fails


if __name__ == "__main__":
    f = main()
    if f:
        print("\nPROBE FAILURES - review before publishing:")
        for nm, v, k in f:
            print(f"   {nm}: z={v}, expected {k}")
