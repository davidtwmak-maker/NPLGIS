#!/usr/bin/env python3
"""Render the MTR fare-saver map - ZOOMED to fare savers only.

Layout: a map zoomed to fit just the 41 fare-saver locations. Each fare
saver is a colored star (region) with a leader-line callout label. The
label never overlaps a station ring, an MTR line, another label, or
another star.
"""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def load(p):
    return json.load(open(os.path.join(HERE, p), encoding="utf-8"))


def main():
    routes = load("fare_savers_routes.geojson")
    stations_gj = load("fare_savers_stations.geojson")
    savers = load("fare_savers.geojson")

    # station lookup (name -> (lon, lat))
    st_lookup = {f["properties"]["name"].strip().lower(): f["geometry"]["coordinates"]
                 for f in stations_gj["features"]}
    # quick aliases for the station names that come up in the fare-saver list
    st_lookup.update({
        "tsim sha tsui east": st_lookup.get("east tsim sha tsui"),
        "tko": st_lookup.get("tseung kwan o"),
        "tseung kwan o": st_lookup.get("tseung kwan o"),
    })
    st_lookup = {k: v for k, v in st_lookup.items() if v is not None}

    # zh -> en station name map (for parsing the designated field)
    ZH2EN = {
        "中環": "central", "香港": "hong kong", "上環": "sheung wan",
        "炮台山": "fortress hill", "北角": "north point",
        "黃竹坑": "wong chuk hang",
        "柯士甸": "austin", "尖沙咀": "tsim sha tsui", "尖東": "east tsim sha tsui",
        "彩虹": "choi hung", "鑽石山": "diamond hill",
        "何文田": "ho man tin", "黃埔": "whampoa",
        "九龍灣": "kowloon bay", "藍田": "lam tin",
        "美孚": "mei foo",
        "旺角": "mong kok", "奧運": "olympic", "太子": "prince edward",
        "南昌": "nam cheong",
        "石硤尾": "shek kip mei",
        "宋皇臺": "sung wong toi", "土瓜灣": "to kwa wan",
        "黃大仙": "wong tai sin",
        "油麻地": "yau ma tei",
        "第一城": "city one",
        "火炭": "fo tan",
        "坑口": "hang hau",
        "恆安": "heng on", "馬鞍山": "ma on shan",
        "葵興": "kwai hing",
        "大圍": "tai wai",
        "大窩口": "tai wo hau",
        "將軍澳": "tseung kwan o",
        "青衣": "tsing yi",
        "荃灣": "tsuen wan", "荃灣西": "tsuen wan west",
    }

    # parse the designated-station string ("中環／香港／上環") and return candidates
    def candidates(s):
        out = []
        for x in s.replace("／", "/").split("/"):
            x = x.strip()
            if not x: continue
            # exact zh lookup
            en = ZH2EN.get(x)
            if en:
                out.append(en.lower())
                continue
            # try each substring as a zh token
            i = 0
            while i < len(x):
                for j in range(len(x), i, -1):
                    sub = x[i:j]
                    if sub in ZH2EN:
                        out.append(ZH2EN[sub].lower())
                        i = j
                        break
                else:
                    i += 1
        return out

    items = []
    for f in savers["features"]:
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        st_lon = st_lat = None; st_name = ""
        for s in candidates(p["designated"]):
            if s in st_lookup:
                st_lon, st_lat = st_lookup[s]
                st_name = s
                break
        # fall back: nearest station (must be very close)
        if st_lon is None:
            best = None; bd = 1e9
            for sf in stations_gj["features"]:
                slon, slat = sf["geometry"]["coordinates"]
                d = (slon-lon)**2 + (slat-lat)**2
                if d < bd: bd = d; best = (slon, slat, sf["properties"]["name"])
            if best and bd < 0.0005**2:
                st_lon, st_lat, st_name = best
        items.append({"lon": lon, "lat": lat, "p": p,
                      "st_lon": st_lon, "st_lat": st_lat, "st_name": st_name})
    print(f"  items: {len(items)}; with station match: "
          f"{sum(1 for i in items if i['st_lon'])}")

    # ============== build the map ==============
    plt.rcParams["font.sans-serif"] = ["PingFang TC", "PingFang HK", "Hiragino Sans GB",
                                        "STHeiti", "Heiti TC", "Microsoft JhengHei",
                                        "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(14, 12), dpi=110)
    fig.patch.set_facecolor("#f4f5f1")
    ax.set_facecolor("#f4f5f1")

    # bbox: tight around the fare savers (computed from items)
    lons = [i["lon"] for i in items]; lats = [i["lat"] for i in items]
    xmin, xmax = min(lons) - 0.012, max(lons) + 0.012
    ymin, ymax = min(lats) - 0.012, max(lats) + 0.012
    ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)

    # MTR lines drawn FAINT and thin (context only, so labels can pass over them)
    for feat in routes["features"]:
        coords = feat["geometry"]["coordinates"]
        xs = [c[0] for c in coords]; ys = [c[1] for c in coords]
        ax.plot(xs, ys, color=feat["properties"]["color"], lw=1.5, zorder=2,
                alpha=0.55, solid_capstyle="round")

    # collect obstacles for label collision detection
    # MTR line segments
    line_segs = []
    for feat in routes["features"]:
        coords = feat["geometry"]["coordinates"]
        for j in range(len(coords) - 1):
            line_segs.append((coords[j], coords[j+1]))

    # designated station locations (one ring per station, with name)
    station_locs = {}
    for i in items:
        if i["st_lon"] is not None:
            key = (round(i["st_lon"], 5), round(i["st_lat"], 5))
            if key not in station_locs:
                station_locs[key] = i["st_name"]
    ring_pts = list(station_locs.keys())

    # station rings
    for (slon, slat), name in station_locs.items():
        ax.scatter([slon], [slat], s=70, c="white", edgecolors="#222",
                   linewidths=1.0, zorder=4, marker="o")
    # station name labels (small, just below ring)
    for (slon, slat), name in station_locs.items():
        ax.text(slon, slat - 0.0028, name, fontsize=6, ha="center", va="top",
                color="#444", zorder=5)

    # fare-saver stars
    REGION_COLORS = {"Hong Kong Island": "#1f77b4", "Kowloon": "#d62728",
                     "New Territories": "#2ca02c"}
    for i in items:
        region = i["p"]["region"]
        ax.scatter([i["lon"]], [i["lat"]], s=180, c=REGION_COLORS.get(region, "#555"),
                   edgecolors="white", linewidths=1.6, marker="*", zorder=6)

    # ============== label placement ==============
    # collision checks against:
    #  - previously placed labels
    #  - fare-saver star positions
    #  - designated station rings
    #  - MTR line segments
    def line_intersects_rect(p1, p2, rect):
        x0, y0, x1, y1 = rect
        px0, py0 = p1; px1, py1 = p2
        if max(px0, px1) < x0 or min(px0, px1) > x1 or max(py0, py1) < y0 or min(py0, py1) > y1:
            return False
        dx, dy = px1 - px0, py1 - py0
        ts = [0.0, 1.0]
        for edge in range(4):
            if edge == 0:   p, q = -dx, px0 - x0
            elif edge == 1: p, q =  dx, x1 - px0
            elif edge == 2: p, q = -dy, py0 - y0
            else:           p, q =  dy, y1 - py0
            if p == 0:
                if q < 0: return False
            else:
                t = q / p
                if p < 0:
                    if t > ts[1]: return False
                    if t > ts[0]: ts[0] = t
                else:
                    if t < ts[0]: return False
                    if t < ts[1]: ts[1] = t
        return ts[0] <= ts[1]

    def box_overlaps(box, others, margin):
        for b in others:
            if not (box[2] < b[0] - margin or box[0] > b[2] + margin
                    or box[3] < b[1] - margin or box[1] > b[3] + margin):
                return True
        return False

    def box_touches_point(box, pt, r):
        return (box[0] - r < pt[0] < box[2] + r
                and box[1] - r < pt[1] < box[3] + r)

    def box_touches_lines(box, segs):
        edges = [((box[0], box[1]), (box[2], box[1])),
                 ((box[2], box[1]), (box[2], box[3])),
                 ((box[2], box[3]), (box[0], box[3])),
                 ((box[0], box[3]), (box[0], box[1]))]
        for s in segs:
            for e in edges:
                if line_intersects_rect(s[0], s[1], box):
                    return True
        return False

    # sort by density so dense clusters reserve space first
    def density(p):
        return sum(1 for q in items if (p[0]-q["lon"])**2 + (p[1]-q["lat"])**2 < 0.005**2)
    items.sort(key=lambda i: -density((i["lon"], i["lat"])))

    placed = []
    n_unplaced = 0
    for i in items:
        lon, lat = i["lon"], i["lat"]
        p = i["p"]
        text = p["name_zh"]
        n = len(text)
        wlen = 0.0009 * n + 0.0018
        hlen = 0.0028
        angs = np.linspace(0, 2*np.pi, 32, endpoint=False)
        best = None
        for r_deg in [0.005, 0.008, 0.012, 0.018, 0.025, 0.034, 0.045, 0.058, 0.074, 0.092]:
            for ang in angs:
                tx = lon + r_deg * np.cos(ang)
                ty = lat + r_deg * np.sin(ang) * 1.25
                # keep label inside the axes
                if tx - wlen/2 < xmin or tx + wlen/2 > xmax: continue
                if ty - hlen/2 < ymin or ty + hlen/2 > ymax: continue
                box = (tx - wlen/2, ty - hlen/2, tx + wlen/2, ty + hlen/2)
                if box_overlaps(box, placed, 0.0010): continue
                if any(box_touches_point(box, (it["lon"], it["lat"]), 0.0018) for it in items): continue
                if any(box_touches_point(box, (slon, slat), 0.0020) for slon, slat in ring_pts): continue
                if box_touches_lines(box, line_segs): continue
                best = (tx, ty, box); break
            if best: break
        if best:
            tx, ty, box = best
            ax.annotate("", xy=(lon, lat), xytext=(tx, ty),
                        arrowprops=dict(arrowstyle="-", color="#888", lw=0.5))
            ax.text(tx, ty, text, fontsize=7, ha="center", va="center",
                    color="#111", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.2", fc="#fffacd", ec="#888", lw=0.5))
            placed.append(box)
        else:
            n_unplaced += 1
    print(f"  labels placed: {len(placed)} / {len(items)}  (unplaced: {n_unplaced})")

    # ============== title + legend ==============
    fig.suptitle("MTR Fare Saver Stations in Hong Kong",
                 fontsize=20, fontweight="bold", y=0.97)
    ax.set_title("Adult Octopus users who tap a Fare Saver then enter a designated MTR station save $2",
                 fontsize=11, color="#444", pad=12)

    region_handles = [plt.Line2D([0], [0], marker="*", color="w", markerfacecolor=c,
                                 markersize=14,
                                 label=f"{r} ({sum(1 for i in items if i['p']['region']==r)})")
                      for r, c in REGION_COLORS.items()]
    ring_handle = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
                              markeredgecolor="#222", markersize=10,
                              label=f"Designated MTR station ({len(station_locs)})")]
    line_handle = [plt.Line2D([0], [0], color="#999", lw=2, alpha=0.7,
                              label="MTR line (faint context)")]
    leg1 = ax.legend(handles=region_handles + [ring_handle[0]] + line_handle,
                     loc="lower left", fontsize=8, ncol=2,
                     title="Legend", title_fontsize=9, framealpha=0.95)

    ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
    ax.grid(True, lw=0.3, color="#dcd", alpha=0.6)
    ax.set_aspect(1 / np.cos(np.radians(22.34)))
    for s in ax.spines.values(): s.set_color("#aaa")

    # north arrow
    ax.annotate("N", xy=(0.97, 0.94), xycoords="axes fraction", fontsize=14, ha="center")
    ax.annotate("↑", xy=(0.97, 0.90), xycoords="axes fraction", fontsize=18, ha="center")
    fig.text(0.5, 0.012,
             "Data: MTR Corporation (opendata.mtr.com.hk) · MTR line colors (infinityMark/HK_MTR_map) · Geocoded via OpenStreetMap/Nominatim",
             ha="center", fontsize=7, color="#666", style="italic")

    out = os.path.join(HERE, "mtr_fare_saver_map.png")
    plt.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    plt.close()
    print(f"saved: {out}")
    print(f"  MTR lines drawn (faint): {len(routes['features'])}")
    print(f"  Fare savers plotted: {len(items)}")
    print(f"  Designated station rings: {len(station_locs)}")


if __name__ == "__main__":
    main()
