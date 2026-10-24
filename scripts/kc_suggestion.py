#!/usr/bin/env python3
"""Fare-Saver site suggestion for Kowloon City District.

Datasets (all CSDI ArcGIS REST, no token):
  - Tertiary Planning Unit (TPU) polygons: pland_rcd_1637289585582_55577  (PPU 7 = KC)
  - 2021 Population by Small TPU Group:   censtatd_rcd_1635933193720_58660
  - 3D Pedestrian Network:                landsd_rcd_1637222018065_52265

Outputs in this folder:
  - kc_tpus.geojson
  - kc_population.geojson
  - kc_pedestrian.geojson
  - kc_suggestion_map.png
  - kc_suggestions.csv
"""
import csv, json, math, os, sys
import requests
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://portal.csdi.gov.hk/server/rest/services/common"

TPU_ID = "pland_rcd_1637289585582_55577"
POP_ID = "censtatd_rcd_1635933193720_58660"
PED_ID = "landsd_rcd_1637222018065_52265"
PPU_KC = "2"  # Kowloon City District (PPU 2 in 2021 PlanD boundaries — PPU 7 is Tuen Mun/Yuen Long)
KC_BBOX = (114.155, 22.270, 114.215, 22.345)  # pedestrian bbox

# Named suggested fare-saver sites (TPU code -> (place name, nearest shopping mall))
KC_NAMED = {
    "241": ("靠背壟",     "中華商場"),
    "244": ("大環",       "昇御商場"),
    "243": ("老龍坑",     "昇御商場"),
    "222": ("太子北 (旺角)", "鴻都商場"),
    "227": ("旺角中",     "鴻都商場"),
    "268": ("石硤尾",     "石硤尾商場"),
    "245": ("紅磡灣",     "家維商場"),
    "229": ("旺角西",     "朗豪坊"),
    "228": ("油麻地北",   "玉器市場"),
    "236": ("何文田南",   "何文田廣場"),
    "237": ("土瓜灣北",   "美景街市"),
    "215": ("紅磡",       "黃埔新天地"),
    "287": ("鑽石山",     "荷里活廣場"),
    "251": ("柯士甸站",   "圓方 Elements"),
    "225": ("油麻地",     "油麻地戲院"),
}

KC_MTR = {
    "Ho Man Tin":          (22.3088, 114.1808),
    "Hung Hom":            (22.3028, 114.1817),
    "To Kwa Wan":          (22.3167, 114.1860),
    "Sung Wong Toi":       (22.3083, 114.1902),
    "Kai Tak":             (22.3220, 114.1990),
    "Diamond Hill":        (22.3400, 114.2010),
    "Choi Hung":           (22.3345, 114.2049),
    "Kowloon Tong":        (22.3370, 114.1755),
    "Shek Kip Mei":        (22.3318, 114.1695),
    "Prince Edward":       (22.3248, 114.1690),
    "Mong Kok":            (22.3193, 114.1700),
    "Yau Ma Tei":          (22.3130, 114.1707),
    "Austin":              (22.3050, 114.1665),
    "East Tsim Sha Tsui":  (22.2960, 114.1744),
    "Tsim Sha Tsui":       (22.2980, 114.1722),
    "Whampoa":             (22.3052, 114.1901),
}


def query(layer, params):
    url = f"{BASE}/{layer}/FeatureServer/0/query"
    r = requests.get(url, params={**params, "f": "json"}, timeout=120)
    r.raise_for_status()
    return r.json()


def fetch_all_geojson(layer, where, out_path):
    feats, offset = [], 0
    while True:
        data = query(layer, {"where": where, "outFields": "*", "returnGeometry": "true",
                             "outSR": 4326, "f": "geojson", "resultRecordCount": 2000,
                             "resultOffset": offset})
        b = data.get("features", [])
        feats.extend(b)
        if len(b) < 2000:
            break
        offset += 2000
    # Normalize: if f=json (Esri) was returned (when f=geojson fails), convert.
    if feats and "attributes" in feats[0] and "geometry" in feats[0]:
        feats = [esri_to_geojson(f) for f in feats]
    gj = {"type": "FeatureCollection", "features": feats}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False)
    return feats


def esri_to_geojson(f):
    """Convert Esri JSON feature to GeoJSON feature."""
    geom = f.get("geometry") or {}
    rings = geom.get("rings")
    attrs = f.get("attributes") or {}
    if not rings:
        return {"type": "Feature", "properties": attrs, "geometry": {"type": "Polygon", "coordinates": []}}
    # Esri rings: [[[x,y],...], ...]; first ring is outer, rest are holes (CW vs CCW in Esri).
    # For our purposes (point-in-poly) we just need outer ring.
    if len(rings) == 1:
        coords = rings
    else:
        # treat first as outer, others as holes (GeoJSON supports [outer, hole1, hole2, ...])
        coords = rings
    return {"type": "Feature", "properties": attrs,
            "geometry": {"type": "Polygon", "coordinates": coords}}


def hav(l1, la1, l2, la2):
    R = 6371000
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1); dl = math.radians(l2 - l1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))


def point_in_poly(lon, lat, polygon):
    """Ray-cast. polygon is a list of rings, first ring is outer."""
    x, y = lon, lat
    inside = False
    for ring in polygon:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
    return inside


def main():
    # 1. TPU polygons for Kowloon City (cache if exists)
    print("=== 1. Fetching TPU polygons (Kowloon City, PPU 7)... ===")
    tpu_path = os.path.join(HERE, "kc_tpus.geojson")
    if os.path.exists(tpu_path):
        tpus = json.load(open(tpu_path))["features"]
        print(f"  loaded {len(tpus)} TPUs from cache")
    else:
        tpus = fetch_all_geojson(TPU_ID, f"PPU_NUMBER='{PPU_KC}'", tpu_path)
        print(f"  fetched {len(tpus)} TPUs")

    # 2. Population layer (cache if exists)
    print("=== 2. Fetching 2021 population (all)... ===")
    pop_path = os.path.join(HERE, "kc_population.geojson")
    if os.path.exists(pop_path):
        pop = json.load(open(pop_path))["features"]
        print(f"  loaded {len(pop)} pop polygons from cache")
    else:
        pop = fetch_all_geojson(POP_ID, "t_pop>=0", pop_path)
        print(f"  fetched {len(pop)} pop polygons")

    # 3. Spatial-join population into TPUs (pop polygon centroid inside TPU)
    print("=== 3. Spatial-joining population into TPUs... ===")
    for pf in pop:
        coords = pf["geometry"]["coordinates"]
        polys = [coords] if pf["geometry"]["type"] == "Polygon" else coords
        xs, ys = [], []
        for poly in polys:
            for ring in poly:
                xs.extend(c[0] for c in ring)
                ys.extend(c[1] for c in ring)
        pf["_cx"] = (min(xs)+max(xs))/2
        pf["_cy"] = (min(ys)+max(ys))/2
        pf["_pop"] = int(pf["properties"].get("t_pop") or 0)

    for tf in tpus:
        coords = tf["geometry"]["coordinates"]
        polys = [coords] if tf["geometry"]["type"] == "Polygon" else coords
        # bbox of TPU
        xs, ys = [], []
        for poly in polys:
            for ring in poly:
                xs.extend(c[0] for c in ring)
                ys.extend(c[1] for c in ring)
        tf["_cx"] = (min(xs)+max(xs))/2
        tf["_cy"] = (min(ys)+max(ys))/2
        tf["_bbox"] = (min(xs), min(ys), max(xs), max(ys))
        # sum pop of any pop polygon whose centroid falls inside this TPU
        total = 0
        for pf in pop:
            if pf["_pop"] == 0: continue
            cx, cy = pf["_cx"], pf["_cy"]
            # quick bbox reject
            if not (tf["_bbox"][0] <= cx <= tf["_bbox"][2]
                    and tf["_bbox"][1] <= cy <= tf["_bbox"][3]):
                continue
            if any(point_in_poly(cx, cy, ring) for ring in polys):
                total += pf["_pop"]
        tf["_pop"] = total
        print(f"  TPU {tf['properties'].get('TPU_NUMBER')}: pop={total:>5}")

    # 4. Fetch 3D Pedestrian Network (using spatial filter for KC bbox; cache)
    print("=== 4. Loading 3D Pedestrian Network (KC bbox)... ===")
    ped_path = os.path.join(HERE, "kc_pedestrian.geojson")
    if os.path.exists(ped_path):
        kept = json.load(open(ped_path))["features"]
        print(f"  loaded {len(kept)} features from cache")
    else:
        feats, offset = [], 0
        t0 = __import__("time").time()
        while True:
            data = query(PED_ID, {"where": "1=1",
                                  "geometry": "114.155,22.270,114.215,22.345",
                                  "geometryType": "esriGeometryEnvelope",
                                  "spatialRel": "esriSpatialRelIntersects",
                                  "inSR": 4326,
                                  "outFields": "*", "returnGeometry": "true",
                                  "outSR": 4326, "f": "geojson",
                                  "resultRecordCount": 2000, "resultOffset": offset})
            b = data.get("features", [])
            feats.extend(b)
            if len(b) < 2000:
                break
            offset += 2000
        print(f"  fetched {len(feats)} features in KC bbox ({__import__('time').time()-t0:.1f}s)")
        with open(ped_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)
        kept = feats

    # 5. For each TPU, walk to nearest MTR
    print("=== 5. Walk-distance to nearest MTR (straight-line x 1.4)... ===")
    for tf in tpus:
        nearest = None
        for stn, (lat, lon) in KC_MTR.items():
            d = hav(tf["_cx"], tf["_cy"], lon, lat)
            if nearest is None or d < nearest[1]:
                nearest = (stn, d)
        tf["nearest_mtr"] = nearest[0]
        tf["straight_m"] = round(nearest[1], 0)
        tf["walk_m_est"] = round(nearest[1] * 1.4, 0)
        tf["walk_min"] = round(nearest[1] * 1.4 / 80, 1)

    # 6. Distance to existing fare-saver
    fs = json.load(open(str(HERE / "fare_savers.geojson"), encoding="utf-8"))
    fs_pts = [(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1]) for f in fs["features"]]
    for tf in tpus:
        cdist = min(hav(tf["_cx"], tf["_cy"], p[0], p[1]) for p in fs_pts)
        tf["d_existing_fs_m"] = round(cdist, 0)

    # 7. Score & pick candidates
    print("\n=== 6. Scoring candidates ===")
    candidates = []
    for tf in tpus:
        if tf["_pop"] == 0:
            tf["_status"] = "skip: no population data"
            continue
        if tf["walk_m_est"] > 1000 or tf["walk_m_est"] < 100:
            tf["_status"] = "skip: walk out of 100-1000m band"
            continue
        w = tf["walk_min"]
        # Bell-curve weight around 5 min (peaks at 5 min, 0 at 0 or 10 min)
        weight = max(0, 1 - abs(w - 5) / 5)
        # bonus for areas WITHOUT a close FS at all (more need)
        fs_bonus = 1 + min(1, tf["d_existing_fs_m"] / 600)  # 1.0-2.0
        score = tf["_pop"] * weight * fs_bonus
        tf["_score"] = round(score, 0)
        tf["_status"] = "candidate"
        candidates.append(tf)
    candidates.sort(key=lambda t: -t["_score"])
    print(f"\n  Top {min(15, len(candidates))} candidate TPUs:")
    for c in candidates[:15]:
        print(f"  TPU {c['properties'].get('TPU_NUMBER')}: pop={c['_pop']:>6}  "
              f"walk={c['walk_m_est']:>4.0f}m ({c['walk_min']:.1f}min)  "
              f"nearest_MTR={c['nearest_mtr']:<18}  d_existing_fs={c['d_existing_fs_m']:>4.0f}m  "
              f"score={c['_score']:>7.0f}")
    if not candidates:
        print("  (none)")
    skipped = [t for t in tpus if t.get("_status", "").startswith("skip:")]
    print(f"  Skipped {len(skipped)} TPUs: walk_out_of_band={sum(1 for t in skipped if 'walk' in t['_status'])}  no_pop={sum(1 for t in skipped if 'no pop' in t['_status'])}")

    # 8. CSV
    csv_path = os.path.join(HERE, "kc_suggestions.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "rank", "tpu", "population", "centroid_lon", "centroid_lat",
            "walk_m_est", "walk_min", "nearest_mtr", "d_existing_fs_m", "score"
        ])
        w.writeheader()
        for i, c in enumerate(candidates, 1):
            w.writerow({
                "rank": i, "tpu": c["properties"].get("TPU_NUMBER"),
                "population": c["_pop"],
                "centroid_lon": round(c["_cx"], 5),
                "centroid_lat": round(c["_cy"], 5),
                "walk_m_est": c["walk_m_est"],
                "walk_min": c["walk_min"],
                "nearest_mtr": c["nearest_mtr"],
                "d_existing_fs_m": c["d_existing_fs_m"],
                "score": c["_score"],
            })
    print(f"\n  CSV: {csv_path}")

    # 9. Render map
    print("\n=== 7. Rendering map... ===")
    plt.rcParams["font.sans-serif"] = ["PingFang TC", "Hiragino Sans GB",
                                        "STHeiti", "Microsoft JhengHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(15, 13), dpi=110)
    fig.patch.set_facecolor("#f4f5f1"); ax.set_facecolor("#f4f5f1")

    # pedestrian network
    for f in kept:
        geom = f.get("geometry", {})
        if "rings" in geom:
            continue
        coords = geom.get("coordinates") or geom.get("paths")
        if not coords: continue
        if isinstance(coords[0][0], (int, float)):
            lines = [coords]  # single LineString
        else:
            lines = coords  # MultiLineString
        for line in lines:
            xs = [c[0] for c in line]; ys = [c[1] for c in line]
            ax.plot(xs, ys, color="#b9c3a0", lw=0.3, alpha=0.7, zorder=1)

    # TPU polygons colored
    if candidates:
        top_score = max(c["_score"] for c in candidates)
    else:
        top_score = 1
    for tf in tpus:
        coords = tf["geometry"]["coordinates"]
        polys = [coords] if tf["geometry"]["type"] == "Polygon" else coords
        if tf.get("_status") == "candidate" and candidates:
            ratio = tf["_score"] / top_score if top_score else 0
            color = plt.cm.YlOrBr(0.30 + 0.55 * min(1, ratio))
        elif tf.get("_status", "").startswith("skip:"):
            color = "#bdbdbd"
        else:
            color = "#dfe6d8"
        for poly in polys:
            patch = MplPolygon([(c[0], c[1]) for c in poly[0]], closed=True,
                                facecolor=color, edgecolor="#5a6a4a", lw=0.4, zorder=2)
            ax.add_patch(patch)

    # MTR stations (white circles only; labels only for the "designated" line
    # of each top-5 candidate, plus a few peripheral landmarks)
    mtr_labels = []
    for stn, (lat, lon) in KC_MTR.items():
        ax.scatter([lon], [lat], s=55, c="white", edgecolors="#111",
                   linewidths=1.2, zorder=4, marker="o")
        mtr_labels.append((lon, lat, stn, 0, -0.003))

    # existing fare savers
    for p in fs_pts:
        ax.scatter([p[0]], [p[1]], s=50, c="#d62728", edgecolors="white",
                   linewidths=0.8, marker="*", zorder=5)

    # top-5 candidates
    cand_bboxes = []  # for solver
    for i, c in enumerate(candidates[:5], 1):
        ax.scatter([c["_cx"]], [c["_cy"]], s=380, c="#1f77b4",
                   edgecolors="white", linewidths=1.8, marker="*", zorder=6)
        cand_bboxes.append((c["_cx"], c["_cy"], 0.0035, 0.0025))  # star bbox

    # MTR station labels: only show stations designated for each top candidate,
    # plus a few peripheral anchors. Skip labels for stations that would
    # collide with a candidate star (label solver handles offsets).
    designated_set = set(c["nearest_mtr"] for c in candidates[:5])
    peripheral = {"Diamond Hill", "Kowloon Tong", "Choi Hung", "Kai Tak",
                  "Tsim Sha Tsui", "East Tsim Sha Tsui", "Austin"}
    label_stns = designated_set | peripheral
    placed_bboxes = list(cand_bboxes)  # start with star bboxes
    for lon, lat, stn, dx, dy in mtr_labels:
        if stn not in label_stns:
            continue
        candidates_offsets = [
            (0, -0.0045), (0, 0.0045), (0.0045, 0), (-0.0045, 0),
            (0.0040, 0.0035), (-0.0040, 0.0035), (0.0040, -0.0035), (-0.0040, -0.0035),
            (0.0055, 0), (-0.0055, 0), (0, 0.0060), (0, -0.0060),
        ]
        placed = False
        for ox, oy in candidates_offsets:
            tlon, tlat = lon + ox, lat + oy
            if ox == 0 and oy < 0:
                bb = (tlon - 0.0025, tlat - 0.0024, tlon + 0.0025, tlat - 0.0010)
                ha, va = "center", "top"
            elif ox == 0 and oy > 0:
                bb = (tlon - 0.0025, tlat + 0.0010, tlon + 0.0025, tlat + 0.0024)
                ha, va = "center", "bottom"
            elif ox > 0 and oy == 0:
                bb = (tlon + 0.0008, tlat - 0.0012, tlon + 0.0050, tlat + 0.0012)
                ha, va = "left", "center"
            elif ox < 0 and oy == 0:
                bb = (tlon - 0.0050, tlat - 0.0012, tlon - 0.0008, tlat + 0.0012)
                ha, va = "right", "center"
            else:
                bb = (tlon - 0.0022, tlat - 0.0012, tlon + 0.0022, tlat + 0.0012)
                ha, va = "center", "center"
            pad = 0.0008
            overlap = any(
                not (bb[2] + pad < pb[0] or bb[0] - pad > pb[2] or
                     bb[3] + pad < pb[1] or bb[1] - pad > pb[3])
                for pb in placed_bboxes
            )
            if not overlap:
                ax.text(tlon, tlat, stn, fontsize=8, ha=ha, va=va,
                        color="#222", zorder=5, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#666", lw=0.5))
                placed_bboxes.append(bb)
                placed = True
                break
        if not placed:
            # fallback: place far to the side
            ax.text(lon - 0.006, lat, stn, fontsize=8, ha="right", va="center",
                    color="#222", zorder=5, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="#666", lw=0.5))

    # Candidate #N labels (after MTR labels so they can win the slot)
    for i, c in enumerate(candidates[:5], 1):
        tpu_code = c["properties"].get("TPU_NUMBER")
        place, mall = KC_NAMED.get(tpu_code, (f"TPU {tpu_code}", "—"))
        label = f"#{i}  {place}\n   ↳ {mall}"
        # try positions: right of star, then left, then above, then below
        positions = [
            (c["_cx"] + 0.0048, c["_cy"] + 0.0010, "left", "center"),
            (c["_cx"] - 0.0048, c["_cy"] + 0.0010, "right", "center"),
            (c["_cx"],          c["_cy"] + 0.0055, "center", "bottom"),
            (c["_cx"],          c["_cy"] - 0.0055, "center", "top"),
        ]
        placed = False
        for tlon, tlat, ha, va in positions:
            # rough bbox (taller for two-line label)
            w = 0.0040; h = 0.0040
            if ha == "center" and va == "bottom":
                bb = (tlon - w/2, tlat, tlon + w/2, tlat + h)
            elif ha == "center" and va == "top":
                bb = (tlon - w/2, tlat - h, tlon + w/2, tlat)
            elif ha == "left":
                bb = (tlon, tlat - h/2, tlon + w, tlat + h/2)
            else:
                bb = (tlon - w, tlat - h/2, tlon, tlat + h/2)
            pad = 0.0008
            overlap = any(
                not (bb[2] + pad < pb[0] or bb[0] - pad > pb[2] or
                     bb[3] + pad < pb[1] or bb[1] - pad > pb[3])
                for pb in placed_bboxes
            )
            if not overlap:
                ax.text(tlon, tlat, label, fontsize=8.5, ha=ha, va=va,
                        fontweight="bold", color="#0a4b8c",
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#0a4b8c", lw=1.2),
                        zorder=7)
                placed_bboxes.append(bb)
                placed = True
                break
        if not placed:
            # fallback: above
            ax.text(c["_cx"], c["_cy"] + 0.0055, label, fontsize=8.5, ha="center", va="bottom",
                    fontweight="bold", color="#0a4b8c",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#0a4b8c", lw=1.2),
                    zorder=7)

    # bbox
    lons = [f["_cx"] for f in tpus]; lats = [f["_cy"] for f in tpus]
    pad = 0.008
    ax.set_xlim(min(lons) - pad, max(lons) + pad)
    ax.set_ylim(min(lats) - pad, max(lats) + pad)

    legend_handles = [
        plt.Line2D([0], [0], color="#b9c3a0", lw=2, label="3D Pedestrian Network"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
                   markeredgecolor="#111", markersize=9, label="MTR station"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#d62728",
                   markersize=12, label="Existing Fare Saver"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#1f77b4",
                   markersize=15, label="Top-5 suggested sites"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", fontsize=9,
              title="Kowloon City", title_fontsize=10, framealpha=0.95)

    ax.set_title("Suggested new Fare Saver sites — Kowloon City District\n"
                 "(colored by score; higher = larger TPU population + walking distance to MTR in 1-7 min range)",
                 fontsize=12, pad=10)
    ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
    ax.grid(True, lw=0.3, color="#dcd", alpha=0.5)
    ax.set_aspect(1 / np.cos(np.radians(22.31)))
    for s in ax.spines.values(): s.set_color("#aaa")

    fig.suptitle("New Fare Saver Site Candidates — Kowloon City",
                 fontsize=18, fontweight="bold", y=0.97)
    fig.text(0.5, 0.012,
             "Data: CSDI Portal — TPU boundaries (pland), 2021 Population Census (censtatd), 3D Pedestrian Network (landsd) · MTR station coords: HK MTR opendata",
             ha="center", fontsize=7, color="#666", style="italic")

    out = os.path.join(HERE, "kc_suggestion_map.png")
    plt.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    plt.close()
    print(f"\nsaved: {out}")
    print(f"  {len(tpus)} TPUs analyzed, {len(candidates)} candidates, top 5 marked")


if __name__ == "__main__":
    main()
