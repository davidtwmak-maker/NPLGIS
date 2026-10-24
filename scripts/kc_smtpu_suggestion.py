#!/usr/bin/env python3
"""Fare-Saver site suggestion for Kowloon City — Small TPU granularity.

Uses TPUSBVC_2006 (pland_rcd_1636535383021_30595): 1,342 small-TPU polygons
at PPU=2 (Kowloon City), about 5–10× finer than the TPU layer.
Population join: spatial (pop polygon centroid inside small TPU).
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

# Layers
SMTPU_ID = "pland_rcd_1636535383021_30595"  # TPUSBVC_2006 (small TPU)
POP_ID   = "censtatd_rcd_1635933193720_58660"  # 2021 pop by stpug
PED_ID   = "landsd_rcd_1637222018065_52265"   # 3D Pedestrian Network

PPU_KC = "2"  # Kowloon City
KC_BBOX = (114.155, 22.270, 114.215, 22.345)

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

# Named place + nearest shopping mall for top suggestions (small TPU, lookup by parent TPU code)
# (will be filled in by the script from the same lookup as the coarse map)
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


def query(layer, params):
    r = requests.get(f"{BASE}/{layer}/FeatureServer/0/query",
        params={**params, "f": "json"}, timeout=120)
    r.raise_for_status()
    return r.json()


def esri_to_geojson_feature(feat):
    geom = feat.get("geometry") or {}
    attrs = feat.get("attributes") or {}
    rings = geom.get("rings") or []
    if not rings:
        return {"type": "Feature", "properties": attrs, "geometry": None}
    return {"type": "Feature", "properties": attrs,
            "geometry": {"type": "Polygon", "coordinates": rings}}


def fetch_geojson(layer, where, out_path, geom_bbox=None):
    feats, offset = [], 0
    while True:
        params = {"where": where, "outFields": "*", "returnGeometry": "true",
                  "outSR": 4326, "f": "json",
                  "resultRecordCount": 2000, "resultOffset": offset}
        if geom_bbox:
            x0, y0, x1, y1 = geom_bbox
            params.update({
                "geometry": f"{x0},{y0},{x1},{y1}",
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
                "inSR": 4326,
            })
        data = query(layer, params)
        b = data.get("features", [])
        feats.extend(b)
        if len(b) < 2000:
            break
        offset += 2000
    gj_feats = [esri_to_geojson_feature(f) for f in feats]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": gj_feats}, f, ensure_ascii=False)
    return gj_feats


def hav(l1, la1, l2, la2):
    R = 6371000
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1); dl = math.radians(l2 - l1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))


def point_in_poly(lon, lat, polygon_rings):
    x, y = lon, lat; inside = False
    for ring in polygon_rings:
        if not isinstance(ring, (list, tuple)) or not ring: continue
        # Robust: each element should be a 2-tuple/list; if it's a scalar, skip
        try:
            n = len(ring)
        except TypeError:
            continue
        j = n - 1
        for i in range(n):
            pi, pj = ring[i], ring[j]
            if not (isinstance(pi, (list, tuple)) and isinstance(pj, (list, tuple))):
                continue
            if len(pi) < 2 or len(pj) < 2:
                continue
            xi, yi = pi[0], pi[1]; xj, yj = pj[0], pj[1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
    return inside


def polygon_centroid(coords):
    """Bbox midpoint of any nested GeoJSON polygon structure."""
    rings = _rings(coords)
    xs, ys = [], []
    for ring in rings:
        for c in ring:
            if isinstance(c, (list, tuple)) and len(c) >= 2:
                xs.append(c[0]); ys.append(c[1])
    if not xs: return (0, 0)
    return (min(xs)+max(xs))/2, (min(ys)+max(ys))/2


def _rings(coords):
    """Return list of rings from any nested GeoJSON polygon structure.

    Handles three real cases seen in CSDI:
      - Polygon depth-3 = list of rings (e.g. smtpu, coarse TPU)
      - Polygon depth-3 = list of polygons, each 1 ring (e.g. population)
      - MultiPolygon depth-4 = list of polygons, each list of rings
    Detection: if coords[0][0] looks like a point [x, y] (numbers), then
    coords is list-of-rings. If it's a list, coords is list-of-polygons.
    """
    if not coords: return []
    # First element inspection
    e0 = coords[0]
    if not e0: return []
    # If first element's first element is a number, e0 is a point → coords is list of rings
    if isinstance(e0[0], (int, float)):
        return coords  # coords is already list of rings
    # Otherwise coords is list of polygons; flatten one level
    rings = []
    for poly in coords:
        if not poly: continue
        # poly may be a list of rings, or a single ring
        if isinstance(poly[0], (list, tuple)) and len(poly[0]) >= 1 and isinstance(poly[0][0], (list, tuple)):
            rings.extend(poly)
        else:
            rings.append(poly)
    return rings


def depth(x):
    if not isinstance(x, (list, tuple)) or not x: return 0
    return 1 + depth(x[0])


def main():
    # 1. Small TPU polygons
    smtpu_path = os.path.join(HERE, "kc_smtpus.geojson")
    if os.path.exists(smtpu_path):
        smtpus = json.load(open(smtpu_path))["features"]
        print(f"=== 1. Small TPUs: {len(smtpus)} from cache")
    else:
        print("=== 1. Fetching small TPUs (PPU=2, KC bbox)... ===")
        smtpus = fetch_geojson(SMTPU_ID, f"PPU={PPU_KC}", smtpu_path, geom_bbox=KC_BBOX)
        print(f"  {len(smtpus)} small TPUs")

    # 2. Population (already cached)
    pop_path = os.path.join(HERE, "kc_population.geojson")
    pop = json.load(open(pop_path))["features"]
    print(f"=== 2. Population: {len(pop)} from cache")

    # 3. Centroids + spatial join
    print("=== 3. Spatial-joining population into small TPUs (area-weighted)...")
    # Pre-compute pop polygon (using shapely for robustness)
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    pop_shapes = []
    for pf in pop:
        g = pf["geometry"]
        if not g: continue
        try:
            s = shape(g)
            if not s.is_valid:
                s = s.buffer(0)  # make valid
            pop_shapes.append((s, int(pf["properties"].get("t_pop") or 0), pf["properties"].get("stpug")))
        except Exception:
            continue
    print(f"  {len(pop_shapes)} pop shapes built")
    pop_idx = STRtree([p[0] for p in pop_shapes])

    n_with_pop = 0
    n_checked = 0
    for tf in smtpus:
        g = tf["geometry"]
        if not g: continue
        polys = g["coordinates"] if g["type"] == "Polygon" else g["coordinates"]
        if not polys: continue
        # shapely geometry
        try:
            smt_shape = shape(g)
            if not smt_shape.is_valid:
                smt_shape = smt_shape.buffer(0)
        except Exception:
            continue
        smt_area = smt_shape.area
        if smt_area == 0: continue
        cx, cy = smt_shape.centroid.x, smt_shape.centroid.y
        tf["_cx"], tf["_cy"] = cx, cy
        # find pop candidates
        total = 0
        try:
            cand = pop_idx.query(smt_shape)
        except Exception:
            cand = []
        for idx in cand:
            ps, t_pop, stpug = pop_shapes[idx]
            if t_pop == 0: continue
            try:
                if not smt_shape.intersects(ps): continue
                inter = smt_shape.intersection(ps)
                if inter.area > 0:
                    total += t_pop * (inter.area / smt_area)
            except Exception:
                continue
        tf["_pop"] = total
        n_checked += 1
        if total > 0:
            n_with_pop += 1
    print(f"  smtpus with pop > 0: {n_with_pop}/{n_checked}")

    # 4. Pedestrian network
    ped_path = os.path.join(HERE, "kc_pedestrian.geojson")
    kept = json.load(open(ped_path))["features"]
    print(f"=== 4. 3D Pedestrian Network: {len(kept)} from cache")

    # 5. Walk to nearest MTR
    for tf in smtpus:
        nearest = None
        for stn, (lat, lon) in KC_MTR.items():
            d = hav(tf["_cx"], tf["_cy"], lon, lat)
            if nearest is None or d < nearest[1]:
                nearest = (stn, d)
        tf["nearest_mtr"] = nearest[0]
        tf["straight_m"] = round(nearest[1], 0)
        tf["walk_m_est"] = round(nearest[1] * 1.4, 0)
        tf["walk_min"] = round(nearest[1] * 1.4 / 80, 1)

    # 6. Distance to existing FS
    fs = json.load(open(os.path.join(HERE, "fare_savers.geojson")))
    fs_pts = [(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1]) for f in fs["features"]]
    for tf in smtpus:
        cdist = min(hav(tf["_cx"], tf["_cy"], p[0], p[1]) for p in fs_pts)
        tf["d_existing_fs_m"] = round(cdist, 0)

    # 7. Score & pick candidates
    print("=== 5. Scoring candidates (small TPU granularity)... ===")
    candidates = []
    for tf in smtpus:
        if tf["_pop"] < 500:
            tf["_status"] = "skip: pop<500"
            continue
        if tf["walk_m_est"] > 1000 or tf["walk_m_est"] < 50:
            tf["_status"] = "skip: walk out of 50-1000m band"
            continue
        w = tf["walk_min"]
        weight = max(0, 1 - abs(w - 5) / 5)
        fs_bonus = 1 + min(1, tf["d_existing_fs_m"] / 500)  # tighter since small
        score = tf["_pop"] * weight * fs_bonus
        tf["_score"] = round(score, 0)
        tf["_status"] = "candidate"
        candidates.append(tf)
    candidates.sort(key=lambda t: -t["_score"])
    print(f"  {len(candidates)} small-TPU candidates")

    # 8. CSV
    csv_path = os.path.join(HERE, "kc_smtpu_suggestions.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "rank", "PPU", "SPU", "TPU", "SB_VC", "population",
            "centroid_lon", "centroid_lat", "walk_m_est", "walk_min",
            "nearest_mtr", "d_existing_fs_m", "score"
        ])
        w.writeheader()
        for i, c in enumerate(candidates, 1):
            a = c["properties"]
            w.writerow({
                "rank": i, "PPU": a["PPU"], "SPU": a["SPU"], "TPU": a["TPU"], "SB_VC": a["SB_VC"],
                "population": c["_pop"],
                "centroid_lon": round(c["_cx"], 5),
                "centroid_lat": round(c["_cy"], 5),
                "walk_m_est": c["walk_m_est"],
                "walk_min": c["walk_min"],
                "nearest_mtr": c["nearest_mtr"],
                "d_existing_fs_m": c["d_existing_fs_m"],
                "score": c["_score"],
            })
    print(f"  CSV: {csv_path}")
    print("  Top 10:")
    for c in candidates[:10]:
        a = c["properties"]
        place, mall = KC_NAMED.get(str(a["TPU"]), ("", "—"))
        print(f"   #{1+candidates.index(c):<3} TPU {a['TPU']}.{a['SB_VC']:<2}  pop={c['_pop']:>5}  "
              f"walk={c['walk_m_est']:>4}m ({c['walk_min']}min)  → {c['nearest_mtr']:<18}  "
              f"d_fs={c['d_existing_fs_m']:>4}m  score={c['_score']:>6.0f}  {place} {mall}")

    # 9. Render map
    print("\n=== 6. Rendering map... ===")
    plt.rcParams["font.sans-serif"] = ["PingFang TC", "Hiragino Sans GB",
                                        "STHeiti", "Microsoft JhengHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(15, 13), dpi=110)
    fig.patch.set_facecolor("#f4f5f1"); ax.set_facecolor("#f4f5f1")

    # pedestrian
    for f in kept:
        g = f.get("geometry", {}) or {}
        if g.get("type") == "MultiLineString":
            for line in g["coordinates"]:
                xs = [c[0] for c in line]; ys = [c[1] for c in line]
                ax.plot(xs, ys, color="#b9c3a0", lw=0.3, alpha=0.7, zorder=1)
        elif g.get("type") == "LineString":
            xs = [c[0] for c in g["coordinates"]]; ys = [c[1] for c in g["coordinates"]]
            ax.plot(xs, ys, color="#b9c3a0", lw=0.3, alpha=0.7, zorder=1)

    # Small TPU polygons
    if candidates:
        top_score = max(c["_score"] for c in candidates)
    else:
        top_score = 1
    for tf in smtpus:
        g = tf["geometry"]
        if not g: continue
        polys = g["coordinates"] if g["type"] == "Polygon" else g["coordinates"]
        if tf.get("_status") == "candidate" and candidates:
            ratio = tf["_score"] / top_score if top_score else 0
            color = plt.cm.YlOrBr(0.30 + 0.55 * min(1, ratio))
        elif tf.get("_status", "").startswith("skip:"):
            color = "#d6d6d6"
        else:
            color = "#e8ece0"
        for ring in _rings(polys):
            patch = MplPolygon([(c[0], c[1]) for c in ring if isinstance(c, (list, tuple)) and len(c) >= 2],
                                closed=True,
                                facecolor=color, edgecolor="#888", lw=0.15, zorder=2)
            ax.add_patch(patch)

    # MTR stations
    mtr_labels = []
    for stn, (lat, lon) in KC_MTR.items():
        ax.scatter([lon], [lat], s=35, c="white", edgecolors="#111",
                   linewidths=1.0, zorder=4, marker="o")
        mtr_labels.append((lon, lat, stn, 0, -0.003))

    # existing fare savers
    for p in fs_pts:
        ax.scatter([p[0]], [p[1]], s=30, c="#d62728", edgecolors="white",
                   linewidths=0.6, marker="*", zorder=5)

    # MTR station labels: designated for top-5 + peripheral
    designated_set = set(c["nearest_mtr"] for c in candidates[:5])
    peripheral = {"Diamond Hill", "Kowloon Tong", "Choi Hung", "Kai Tak",
                  "Tsim Sha Tsui", "East Tsim Sha Tsui", "Austin"}
    label_stns = designated_set | peripheral
    cand_bboxes = [(c["_cx"], c["_cy"], 0.0018, 0.0012) for c in candidates[:8]]  # top-N star bboxes
    placed_bboxes = list(cand_bboxes)
    for lon, lat, stn, dx, dy in mtr_labels:
        if stn not in label_stns: continue
        candidates_offsets = [
            (0, -0.0040), (0, 0.0040), (0.0040, 0), (-0.0040, 0),
            (0.0035, 0.0030), (-0.0035, 0.0030), (0.0035, -0.0030), (-0.0035, -0.0030),
            (0.0050, 0), (-0.0050, 0), (0, 0.0055), (0, -0.0055),
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
            pad = 0.0006
            overlap = any(
                not (bb[2] + pad < pb[0] or bb[0] - pad > pb[2] or
                     bb[3] + pad < pb[1] or bb[1] - pad > pb[3])
                for pb in placed_bboxes
            )
            if not overlap:
                ax.text(tlon, tlat, stn, fontsize=7.5, ha=ha, va=va,
                        color="#222", zorder=5, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#666", lw=0.4))
                placed_bboxes.append(bb)
                placed = True
                break
        if not placed:
            ax.text(lon - 0.0055, lat, stn, fontsize=7.5, ha="right", va="center",
                    color="#222", zorder=5, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#666", lw=0.4))

    # Top-8 candidate labels (small TPU; show more because they're tiny)
    n_show = min(8, len(candidates))
    for i, c in enumerate(candidates[:n_show], 1):
        ax.scatter([c["_cx"]], [c["_cy"]], s=180, c="#1f77b4",
                   edgecolors="white", linewidths=1.0, marker="*", zorder=6)

    # Place #N labels with name+mall in second pass (so they can win the slot)
    label_objs = []
    for i, c in enumerate(candidates[:n_show], 1):
        a = c["properties"]
        tpu_code = str(a["TPU"])
        place, mall = KC_NAMED.get(tpu_code, (f"TPU {tpu_code}.{a['SB_VC']}", "—"))
        label = f"#{i}  {place}\n   ↳ {mall}"
        positions = [
            (c["_cx"] + 0.0038, c["_cy"] + 0.0006, "left", "center"),
            (c["_cx"] - 0.0038, c["_cy"] + 0.0006, "right", "center"),
            (c["_cx"],          c["_cy"] + 0.0045, "center", "bottom"),
            (c["_cx"],          c["_cy"] - 0.0045, "center", "top"),
        ]
        placed = False
        for tlon, tlat, ha, va in positions:
            w, h = 0.0040, 0.0040
            if ha == "center" and va == "bottom":
                bb = (tlon - w/2, tlat, tlon + w/2, tlat + h)
            elif ha == "center" and va == "top":
                bb = (tlon - w/2, tlat - h, tlon + w/2, tlat)
            elif ha == "left":
                bb = (tlon, tlat - h/2, tlon + w, tlat + h/2)
            else:
                bb = (tlon - w, tlat - h/2, tlon, tlat + h/2)
            pad = 0.0005
            overlap = any(
                not (bb[2] + pad < pb[0] or bb[0] - pad > pb[2] or
                     bb[3] + pad < pb[1] or bb[1] - pad > pb[3])
                for pb in placed_bboxes
            )
            if not overlap:
                t = ax.text(tlon, tlat, label, fontsize=7.5, ha=ha, va=va,
                             fontweight="bold", color="#0a4b8c",
                             bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#0a4b8c", lw=0.8),
                             zorder=7)
                placed_bboxes.append(bb)
                label_objs.append(t)
                placed = True
                break
        if not placed:
            ax.text(c["_cx"], c["_cy"] + 0.0045, label, fontsize=7.5, ha="center", va="bottom",
                    fontweight="bold", color="#0a4b8c",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#0a4b8c", lw=0.8),
                    zorder=7)

    # bbox from smtpus
    lons = [tf["_cx"] for tf in smtpus if tf.get("_cx") is not None]
    lats = [tf["_cy"] for tf in smtpus if tf.get("_cy") is not None]
    pad = 0.005
    ax.set_xlim(min(lons) - pad, max(lons) + pad)
    ax.set_ylim(min(lats) - pad, max(lats) + pad)

    legend_handles = [
        plt.Line2D([0], [0], color="#b9c3a0", lw=2, label="3D Pedestrian Network"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
                   markeredgecolor="#111", markersize=7, label="MTR station"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#d62728",
                   markersize=9, label="Existing Fare Saver"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#1f77b4",
                   markersize=11, label=f"Top-{n_show} suggested sites (small TPU)"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", fontsize=8,
              title="Kowloon City (Small TPU)", title_fontsize=9, framealpha=0.95)

    ax.set_title("Suggested new Fare Saver sites — Kowloon City (Small TPU granularity)\n"
                 f"1,100 small-TPU polygons (PlanD 2021), 1,342 in PPU 2 · "
                 f"{len(candidates)} candidate small-TPUs · top {n_show} marked",
                 fontsize=11, pad=10)
    ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
    ax.grid(True, lw=0.3, color="#dcd", alpha=0.5)
    ax.set_aspect(1 / np.cos(np.radians(22.31)))
    for s in ax.spines.values(): s.set_color("#aaa")

    fig.suptitle("Fare-Saver site suggestions — Kowloon City, Small-TPU analysis",
                 fontsize=16, fontweight="bold", y=0.97)
    fig.text(0.5, 0.012,
             "Data: CSDI Portal — TPUSBVC_2006 small-TPU boundaries · 2021 Population Census (spatial-joined) · 3D Pedestrian Network",
             ha="center", fontsize=7, color="#666", style="italic")

    out = os.path.join(HERE, "kc_smtpu_suggestion_map.png")
    fig.savefig(out, dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"\nsaved: {out}")
    print(f"  {len(smtpus)} small TPUs · {len(candidates)} candidates · top {n_show} marked")


if __name__ == "__main__":
    main()
