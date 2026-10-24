#!/usr/bin/env python3
"""Build the MTR fare-saver map.

Inputs (in this folder):
  - mtr_lines_and_stations.csv   (official MTR opendata, station order per line)
  - mtrStationsCoord.json        (github: lat/lon for every named MTR station)
  - MTRMap.js                    (github: official MTR line colors)
  - fare_savers.csv              (manually entered from mtr.com.hk)

Outputs:
  - fare_savers.geojson
  - fare_savers_routes.geojson
  - mtr_fare_saver_map.png
"""
import csv, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
MAPS_CANDIDATES = [
    os.path.expanduser("~/.hermes/skills/productivity/maps/scripts/maps_client.py"),
    os.path.expanduser("~/.hermes/skills/maps/scripts/maps_client.py"),
]
MAPS = next(p for p in MAPS_CANDIDATES if os.path.exists(p))
PY = sys.executable  # same interpreter that's running this script (handles the masked dir name)

# --- official MTR line colors (from infinityMark/HK_MTR_map) ---
LINE_COLORS = {
    "AEL": "#007278",   # Airport Express
    "DRL": "#F582A8",   # Disneyland Resort
    "EAL": "#61B4E4",   # East Rail
    "ISL": "#0071CE",   # Island
    "KTL": "#00AB4E",   # Kwun Tong
    "SIL": "#B5BD00",   # South Island
    "TKL": "#A35EB5",   # Tseung Kwan O
    "TML": "#9A3820",   # Tuen Ma
    "TCL": "#F3A112",   # Tung Chung
    "TWL": "#E2231A",   # Tsuen Wan
}


def load_station_coords():
    """MTR opendata station_code -> (lat, lon, name_en, name_tc)."""
    coords = {}
    for s in json.load(open(os.path.join(HERE, "mtrStationsCoord.json"))):
        coords[s["name"]] = (float(s["lat"]), float(s["long"]))
    # extras the github JSON may not have (newer stations)
    extras = {
        "Hin Keng":      (22.3625, 114.1767),
        "Kai Tak":       (22.3220, 114.1990),
        "Sung Wong Toi": (22.3085, 114.1905),
        "To Kwa Wan":    (22.3166, 114.1858),
        "Ho Man Tin":    (22.3086, 114.1808),
        "Whampoa":       (22.3053, 114.1906),
        "East Tsim Sha Tsui": (22.2958, 114.1744),
        "Austin":        (22.3050, 114.1665),
        "Tung Chung":    (22.2890, 113.9418),
        "LOHAS Park":    (22.2922, 114.2700),
        "Ocean Park":    (22.2487, 114.1743),
        "Wong Chuk Hang": (22.2483, 114.1680),
        "Lei Tung":      (22.2419, 114.1556),
        "South Horizons": (22.2430, 114.1486),
        "Exhibition Centre": (22.2821, 114.1757),
        "AsiaWorld-Expo": (22.3215, 113.9416),
        "Airport":       (22.3170, 113.9366),
        "Disneyland Resort": (22.3153, 114.0453),
        "Sunny Bay":     (22.3329, 114.0289),
    }
    for k, v in extras.items():
        coords.setdefault(k, v)
    return coords


def load_routes(coords):
    """MTR opendata CSV: (line_code, station_name_en) per direction -> one polyline per line."""
    seen = set()
    lines = []
    with open(os.path.join(HERE, "mtr_lines_and_stations.csv"), encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            lc = row["Line Code"]
            d = row["Direction"]
            seq_s = row["Sequence"].strip()
            if not seq_s:
                continue
            seq = int(float(seq_s))
            name = row["English Name"].strip()
            if not name:
                continue
            key = (lc, d)
            if key not in seen:
                seen.add(key)
                lines.append((lc, d, []))
            # find index, insert by sequence
            lines[-1][2].append((seq, name))
    # For each (line, direction), emit a polyline ordered by sequence,
    # keeping only the first occurrence of each direction (so DT and UT give the same line)
    out_features = []
    used = set()
    for lc, d, stations in lines:
        stations.sort()
        names = [n for _, n in stations]
        pts = []
        missing = []
        for n in names:
            if n in coords:
                pts.append([coords[n][1], coords[n][0]])  # lon, lat
            else:
                missing.append(n)
        if pts and lc not in used:
            used.add(lc)
            out_features.append({
                "type": "Feature",
                "properties": {"line": lc, "color": LINE_COLORS.get(lc, "#555"),
                               "stations": len(pts), "missing": missing},
                "geometry": {"type": "LineString", "coordinates": pts},
            })
    return out_features, used


def geocode(name_zh, name_en):
    """Geocode a fare-saver. Tries multiple queries and picks a Hong Kong result.
    Returns (lat, lon) or None."""
    queries = [name_zh, name_en, f"{name_en} Hong Kong", f"{name_zh} 香港"]
    for q in queries:
        try:
            r = subprocess.run([PY, MAPS, "search", q],
                               capture_output=True, text=True, timeout=30)
        except Exception as e:
            print(f"  geocode err {q}: {e}", file=sys.stderr); continue
        try:
            j = json.loads(r.stdout)
        except Exception:
            continue
        results = j.get("results") or []
        if not results: continue
        # prefer results that mention Hong Kong or Kowloon or New Territories
        for res in results:
            disp = (res.get("display_name") or "")
            if any(k in disp for k in ("Hong Kong", "九龍", "Kowloon", "新界", "Hong Kong Island")):
                return float(res["lat"]), float(res["lon"])
        # fall back to the first result
        first = results[0]
        return float(first["lat"]), float(first["lon"])
    return None


def main():
    coords = load_station_coords()
    routes, used = load_routes(coords)
    print(f"routes emitted: {sorted(used)}  ({len(routes)} lines)")
    print(f"stations in coord table: {len(coords)}")
    # write routes geojson
    gj = {"type": "FeatureCollection", "features": routes}
    with open(os.path.join(HERE, "fare_savers_routes.geojson"), "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False)

    # write stations geojson
    st_features = []
    for name, (lat, lon) in coords.items():
        st_features.append({"type": "Feature",
                            "properties": {"name": name},
                            "geometry": {"type": "Point", "coordinates": [lon, lat]}})
    with open(os.path.join(HERE, "fare_savers_stations.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": st_features}, f, ensure_ascii=False)

    # fare savers
    savers = []
    with open(os.path.join(HERE, "fare_savers.csv"), encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            row["name_zh"], row["name_en"] = row["name_zh"], row["name_en"]
            ll = geocode(row["name_zh"], row["name_en"])
            if ll:
                row["lat"], row["lon"] = ll
            else:
                row["lat"], row["lon"] = "", ""
            savers.append(row)
            time.sleep(1.05)  # Nominatim ToS

    with open(os.path.join(HERE, "fare_savers.geojson"), "w", encoding="utf-8") as f:
        feats = []
        for s in savers:
            if s["lat"] and s["lon"]:
                feats.append({
                    "type": "Feature",
                    "properties": {k: v for k, v in s.items() if k not in ("lat", "lon")},
                    "geometry": {"type": "Point", "coordinates": [float(s["lon"]), float(s["lat"])]},
                })
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False, indent=2)

    # CSV with coords
    with open(os.path.join(HERE, "fare_savers_geocoded.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(savers[0].keys()))
        w.writeheader()
        for s in savers:
            w.writerow(s)
    print(f"fare savers: {len(savers)}; geocoded: {sum(1 for s in savers if s['lat'])}")
    for s in savers:
        if not s["lat"]:
            print(f"  MISS: {s['name_en']} / {s['name_zh']}  stations={s['designated']}")


if __name__ == "__main__":
    main()
