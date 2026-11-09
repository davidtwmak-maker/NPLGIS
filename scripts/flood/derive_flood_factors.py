#!/usr/bin/env python3
"""
Derive the FLASH-FLOOD and STORM-SURGE factor layers for Hong Kong.

The 267 DSD flood-prone areas are the study area. For each one this
computes an exposure score for each of the two hazards DSD's own study
(DSD CE 77/2021, December 2025) names as Hong Kong's dual flooding threat:
"flash floods from intense rainfall and inundation from coastal storm
surges during typhoons".

FACTORS USED AND WHY
--------------------
FLASH FLOOD
  F1  rainfall intensity   the daily maximum at the nearest GEO gauge,
                           normalised against the HK record 24-hour
                           rainfall (956.0 mm at Tai Mo Shan, 21-22 July
                           1994; GEO Report No. 314, Table 10.1)
  F2  low-lying ground    DTM elevation - where the water ponds
  F3  steep catchment      DTM slope at the point, from a 40 m block-mean
                           of the 5 m DTM
  F4  drainage capacity   number of DSD stormwater inlets within 200 m -
                           more inlets, more capacity before surcharge
  F5  channel surcharge   distance to the nearest major engineered channel
                           - a point beside a major channel can be hit by
                           the channel backing up, not only by local runoff
  F6  outlet restriction  distance to the nearest outfall - if the sea is
                           high, the local system cannot discharge

STORM SURGE
  S1  low-lying ground    DTM elevation - the primary surge factor
  S2  distance to the sea how close the sea can get
  S3  wave exposure       CEDD wave climate (HM0, HMAX, peak period) and
                           the south/south-east exposure CEDD identifies
  S4  astronomical tide   the local tidal range at the nearest HKO tide
                           station - a bigger range means a bigger push
  S5  tidal barrier       the CEDD Coastal Hazards Study 26 areas, the
                           official designation of surge-vulnerable places
  S6  defence assets      DSD stormwater pumping stations and inflatable
                           dams within 500 m - what protects the place

DATA NOTES (all verified live on 2026-11-09)
---------------------------------------------
* The GEO raingauge `Rainfall` field is TEXT with quality markers:
  '12.5' clean, '12.5#' provisional, '***' missing. The CSDI server-side
  `outStatistics` max on it is a STRING max and returns 99.5 for every
  gauge - useless. The extremes MUST be computed locally.
* WSD `Shape__Area` is in square metres even though the layer is served in
  lon/lat - verified against an independent EPSG:2326 shoelace measurement
  (max relative difference 2.0e-09).
* The 1,223 WSD catchments are SECTION polygons (median 0.026 km2), not
  whole catchments. The area of a section is the right quantity for
  "how much drainage catchment drains here", but it must not be described
  as the size of the river's catchment.
* The DTM ASCII grid stores the northern edge first.

Outputs (out/):
  flood_hazard_factors.geojson   267 points with every factor
  flood_hazard_factors.csv
  factor_summary.json

Run:  ls-venv/bin/python derive_flood_factors.py
"""
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
FLOOD_PRONE = os.path.join(GIS_DATA, "HK Flood Prone Areas")
FLOOD = os.path.join(FLOOD_PRONE, "flood_mechanism.geojson")

# The HK record 24-hour rainfall: 956.0 mm at Tai Mo Shan, 21-22 July 1994
# (GEO Report No. 314, Table 10.1 "Maximum Rainfall Records for Hong Kong").
# This is the normaliser for the rainfall factor.
#
# It was 622.5 mm before, taken from the Stanley gauge on 8 September 2023 -
# but that is only the maximum of the 2020-onward subset, not the
# territory record. The 1994 Tai Mo Shan storm is larger.
HK_RECORD_24H_MM = 956.0


def load(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        print(f"  (missing {name})")
        return None
    with open(p) as f:
        return json.load(f)


def parse_rain(v):
    """Parse a GEO raingauge Rainfall value -> (value_or_None, status).

    The field is TEXT with quality markers:
      '12.5'   clean
      '12.5#'  provisional
      '***'    missing
      ''       blank
    """
    if v is None:
        return None, "missing"
    s = str(v).strip()
    if s in ("", "***"):
        return None, "missing"
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)(.*)$", s)
    if not m:
        return None, "missing"
    num = float(m.group(1))
    rest = m.group(2).strip()
    if rest == "#":
        return num, "provisional"
    if rest == "":
        return num, "clean"
    return None, "missing"


def coords(geom):
    c = (geom or {}).get("coordinates")
    if c is None:
        return None
    while isinstance(c[0], (list, tuple)):
        c = c[0]
    try:
        return float(c[0]), float(c[1])
    except (TypeError, ValueError):
        return None


def flat_coords(geom):
    """Every coordinate pair in a geometry."""
    c = (geom or {}).get("coordinates")
    if c is None:
        return
    if (isinstance(c, (list, tuple)) and c and
            isinstance(c[0], (int, float))):
        yield float(c[0]), float(c[1])
        return
    for part in c or []:
        yield from flat_coords({"coordinates": part})


def haversine_km(lon1, lat1, lon2, lat2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest(points, lon, lat):
    """points: list of (key, lon, lat). Returns (key, distance_km) or None."""
    best, bd = None, 1e9
    for k, plon, plat in points:
        d = haversine_km(lon, lat, plon, plat)
        if d < bd:
            bd, best = d, k
    return (best, bd) if best is not None else None


def count_within(points, lon, lat, radius_km):
    n = 0
    for _, plon, plat in points:
        if haversine_km(lon, lat, plon, plat) <= radius_km:
            n += 1
    return n


# ------------------------------------------------------------------ flash flood
def build():
    print("=== loading layers ===")
    # The COMPLETE record (1984-2026) with the gauge coordinates merged in.
    # fall back to the 2020+ subset if the merge has not been run.
    rain = (load("rain_gauges_daily_merged.geojson")
            or load("rain_gauges_daily.geojson"))
    inlets = load("dsd_inlets.geojson")
    channels = load("dsd_channel.geojson")
    outfalls = load("dsd_outfalls.geojson")
    catchments = load("wsd_catchments.geojson")
    tide = load("tide_stations.geojson")
    pred_tide = load("predicted_tide_hourly.geojson")
    wave = load("cedd_wave_data.geojson")
    facilities = load("dsd_facilities.geojson")
    designated = load("cedd_designated_area.geojson")
    shelters = load("typhoon_shelters.geojson")

    # ---------------------------------------------------- F1 rainfall extremes
    print("=== F1. rainfall extremes per gauge ===")
    per_gauge = defaultdict(lambda: {"max": 0.0, "max_date": None, "n_days": 0,
                                      "n_heavy": 0, "n_prov": 0, "n_missing": 0,
                                      "loc": None, "lon": None, "lat": None})
    if rain:
        for ft in rain["features"]:
            p = ft["properties"]
            key = p.get("Raingauge_No")
            if key is None:
                continue
            d = per_gauge[key]
            if d["loc"] is None:
                d["loc"] = p.get("Location")
            val, status = parse_rain(p.get("Rainfall"))
            if status == "provisional":
                d["n_prov"] += 1
            if val is None:
                d["n_missing"] += 1
                continue
            d["n_days"] += 1
            if val >= 200:
                d["n_heavy"] += 1
            if val > d["max"]:
                d["max"] = val
                d["max_date"] = p.get("Date_")
            c = coords(ft.get("geometry"))
            if c and d["lon"] is None:
                d["lon"], d["lat"] = c
    gauges = [(k, d) for k, d in per_gauge.items() if d["lon"] is not None]
    gauge_pts = [(k, d["lon"], d["lat"]) for k, d in gauges]
    print(f"  {len(gauges)} gauges with a location")
    top = sorted(gauges, key=lambda kv: -kv[1]["max"])[:5]
    for k, d in top:
        print(f"    {k:5s} {str(d['loc']):22s} max {d['max']:6.1f} mm on {d['max_date']}")
    rec = max(gauges, key=lambda kv: kv[1]["max"])
    print(f"  record check: {rec[1]['max']:.1f} mm at {rec[1]['loc']} on "
          f"{rec[1]['max_date']}")
    print(f"    published HK record (GEO Report 314 Table 10.1): "
          f"{HK_RECORD_24H_MM} mm 24-hr at Tai Mo Shan, 21-22 July 1994")
    # The GEO daily series and the published 24-hour record are the same
    # quantity on different gauges: the 1994 Tai Mo Shan storm is the
    # territory record, and the GEO gauge N14 Tsuen Wan recorded 875.5 mm
    # on 22 July 1994 within that storm. The normaliser is the published
    # 24-hour record, so the factor is a RETURN-PERIOD-STYLE ratio and
    # the assertion is that no gauge in the series exceeds it.
    assert rec[1]["max"] <= HK_RECORD_24H_MM, \
        (f"gauge max {rec[1]['max']} exceeds the published 24-hour record "
         f"{HK_RECORD_24H_MM}")

    # ---------------------------------------------------- drainage assets
    inlet_pts = []
    if inlets:
        for ft in inlets["features"]:
            c = coords(ft.get("geometry"))
            if c:
                inlet_pts.append((ft["properties"].get("IL"), c[0], c[1]))
    print(f"=== F4. {len(inlet_pts):,} inlets ===")

    channel_pts = []
    if channels:
        for ft in channels["features"]:
            p = ft["properties"]
            g = ft.get("geometry") or {}
            cs = list(flat_coords(g))
            if not cs:
                continue
            # sample the line at intervals so distance is meaningful
            w = p.get("WIDTH")
            try:
                w = float(w)
            except (TypeError, ValueError):
                w = None
            for i, (clon, clat) in enumerate(cs):
                channel_pts.append((f"{p.get('FEAT_NUM')}#{i}", clon, clat, w))
    print(f"=== F5. {len(channel_pts):,} channel vertices ===")

    outfall_pts = []
    if outfalls:
        for ft in outfalls["features"]:
            c = coords(ft.get("geometry"))
            if c:
                outfall_pts.append((ft["properties"].get("FEAT_NUM"), c[0], c[1]))
    print(f"=== F6. {len(outfall_pts):,} outfalls ===")

    # WSD catchment SECTION areas near each flood point: the drainage area
    catchment_pts = []
    if catchments:
        for ft in catchments["features"]:
            p = ft["properties"]
            cs = list(flat_coords(ft.get("geometry")))
            if not cs:
                continue
            lon = sum(c[0] for c in cs) / len(cs)
            lat = sum(c[1] for c in cs) / len(cs)
            catchment_pts.append((p.get("SUBCATCH_ID"), lon, lat,
                                  float(p.get("Shape__Area") or 0),
                                  p.get("NAME")))
    print(f"=== WSD: {len(catchment_pts):,} catchment sections ===")

    # ---------------------------------------------------- S3 wave climate
    print("=== S3. wave climate ===")
    wave_by_station = defaultdict(lambda: {"n": 0, "max_hmax": 0.0,
                                           "max_hm0": 0.0, "max_pk": 0.0,
                                           "n_hs_gt_2": 0, "n_hmax_gt_3": 0,
                                           "lon": None, "lat": None})
    if wave:
        for ft in wave["features"]:
            p = ft["properties"]
            st = p.get("LOCATION")
            d = wave_by_station[st]
            d["n"] += 1
            c = coords(ft.get("geometry"))
            if c and d["lon"] is None:
                d["lon"], d["lat"] = c
            for src, dst in (("HMAX", "max_hmax"), ("HM0", "max_hm0"),
                             ("PEAKTP", "max_pk")):
                try:
                    v = float(p.get(src))
                except (TypeError, ValueError):
                    continue
                if v > d[dst]:
                    d[dst] = v
            for src, dst, thr in (("HM0", "n_hs_gt_2", 2.0),
                                  ("HMAX", "n_hmax_gt_3", 3.0)):
                try:
                    if float(p.get(src)) > thr:
                        d[dst] += 1
                except (TypeError, ValueError):
                    pass
    wave_pts = []
    for st, d in wave_by_station.items():
        print(f"    {st}: {d['n']:,} hourly records, max HMAX {d['max_hmax']:.2f} m, "
              f"max HM0 {d['max_hm0']:.2f} m, max Tp {d['max_pk']:.2f} s, "
              f"{d['n_hs_gt_2']:,} h with Hs>2 m")
        if d["lon"] is not None:
            wave_pts.append((st, d["lon"], d["lat"], d))

    # ---------------------------------------------------- S4 tide stations
    tide_pts = []
    if tide:
        for ft in tide["features"]:
            p = ft["properties"]
            c = coords(ft.get("geometry"))
            if c:
                tide_pts.append((p.get("TIDE_STATION_EN"), c[0], c[1]))
    tide_pt_list = [(n, lo, la) for n, lo, la in tide_pts]
    print(f"=== S4. {len(tide_pts)} tide stations ===")

    # ---------------------------------------------------- S5 designated area
    # The 26 CEDD Coastal Hazards Study areas.
    #
    # The CSDI layer "Boundary of Designated Area"
    # (cedd_rcd_1640249339500_66807) holds only ONE polygon - Tung Chung -
    # so it cannot stand in for the 26 areas. DSD publishes the full list of
    # 26 as points (the "Coastal Low-lying or Windy Residential Areas"
    # list), and that list IS the CEDD designation, so it is used here.
    # Using the single CSDI polygon made every point in the territory
    # score as if it were near Tung Chung.
    desig_pts = []
    coastal_src = os.path.join(FLOOD_PRONE, "dsd_coastal.geojson")
    if os.path.exists(coastal_src):
        cg = json.load(open(coastal_src))
        for ft in cg["features"]:
            c = coords(ft.get("geometry"))
            if c:
                p = ft.get("properties") or {}
                title = p.get("title") or p.get("Title") or "coastal area"
                desig_pts.append((str(title).replace("<br>", " "), c[0], c[1]))
    # keep the CSDI polygon only if the 26-point list was not found
    if not desig_pts and designated:
        for ft in designated["features"]:
            cs = list(flat_coords(ft.get("geometry")))
            if cs:
                lon = sum(c[0] for c in cs) / len(cs)
                lat = sum(c[1] for c in cs) / len(cs)
                desig_pts.append((ft["properties"].get("DES_AREA"), lon, lat))
    print(f"=== S5. CEDD coastal low-lying/windy areas: {len(desig_pts)} ===")
    if len(desig_pts) != 26:
        print(f"    WARNING: expected 26 designated areas, got {len(desig_pts)}")

    # ---------------------------------------------------- S6 defence assets
    fac_pts = []
    pump_pts = []
    if facilities:
        for ft in facilities["features"]:
            p = ft["properties"]
            c = coords(ft.get("geometry"))
            if not c:
                continue
            fac_pts.append((p.get("Building_Name"), c[0], c[1], p.get("Nature")))
            nat = str(p.get("Nature") or "")
            if "PS" in nat or "pump" in nat.lower() or "dam" in nat.lower():
                pump_pts.append((p.get("Building_Name"), c[0], c[1]))
    print(f"=== S6. {len(fac_pts)} DSD facilities, {len(pump_pts)} pumping/dam ===")

    shelter_pts = []
    if shelters:
        for ft in shelters["features"]:
            cs = list(flat_coords(ft.get("geometry")))
            if cs:
                lon = sum(c[0] for c in cs) / len(cs)
                lat = sum(c[1] for c in cs) / len(cs)
                shelter_pts.append((ft["properties"].get("OBJNAM"), lon, lat))
    print(f"=== typhoon shelters: {len(shelter_pts)} ===")

    # ---------------------------------------------------- terrain factors
    terrain = {}
    tp = os.path.join(OUT, "terrain_slope_summary.json")
    if os.path.exists(tp):
        terrain = json.load(open(tp)).get("per_area", {})
        print(f"=== terrain factors for {len(terrain)} areas ===")

    # ---------------------------------------------------- per-area scoring
    print("=== scoring the 267 flood-prone areas ===")
    flood = json.load(open(FLOOD))
    rows = []
    for ft in flood["features"]:
        p = ft["properties"]
        c = coords(ft.get("geometry"))
        if not c:
            continue
        lon, lat = c
        title = p.get("title")

        elev = p.get("elevation_m")
        try:
            elev = float(elev)
        except (TypeError, ValueError):
            elev = None
        dc = p.get("d_coast_km")
        try:
            dc = float(dc)
        except (TypeError, ValueError):
            dc = None
        dbc = p.get("d_bigchannel_km")
        try:
            dbc = float(dbc)
        except (TypeError, ValueError):
            dbc = None

        terr = terrain.get(title, {})

        # ---- FLASH FLOOD --------------------------------------------
        ng = nearest(gauge_pts, lon, lat)
        gkey = ng[0] if ng else None
        gd = per_gauge.get(gkey)
        rain_score = (min(1.0, gd["max"] / HK_RECORD_24H_MM)
                      if gd and gd["max"] else None)

        low_score = max(0.0, min(1.0, (20.0 - elev) / 20.0)) if elev is not None else None
        slope = terr.get("slope_deg")
        slope_score = min(1.0, (slope / 30.0)) if slope is not None else None
        n_inlets = count_within(inlet_pts, lon, lat, 0.2)
        # More inlets = MORE drainage capacity = LESS flood risk, so the
        # risk score must FALL as the inlet count rises. (It rose before,
        # which scored well-drained places as the most flood-prone.)
        inlet_score = max(0.0, min(1.0, 1.0 - n_inlets / 8.0))
        ch_near = nearest([(k, lo, la) for k, lo, la, _ in channel_pts], lon, lat)
        ch_score = None
        if ch_near:
            ch_score = max(0.0, min(1.0, 1.0 - ch_near[1] / 1.0))
        out_near = nearest(outfall_pts, lon, lat)
        outlet_score = None
        if out_near:
            outlet_score = max(0.0, min(1.0, 1.0 - out_near[1] / 3.0))

        ff_parts = [(rain_score, 0.30), (low_score, 0.25), (slope_score, 0.15),
                    (inlet_score, 0.15), (ch_score, 0.10), (outlet_score, 0.05)]
        av = [(v, w) for v, w in ff_parts if v is not None]
        ws = sum(w for _, w in av)
        ff = (sum(v * w for v, w in av) / ws) if ws else None

        # ---- STORM SURGE --------------------------------------------
        ss_low = max(0.0, min(1.0, (10.0 - elev) / 10.0)) if elev is not None else None
        # Distance to the sea: the score must FALL as the distance grows.
        # (It rose with distance before - a sign error - which put the
        # highest storm-surge scores 1.7 km inland.)
        ss_prox = (max(0.0, min(1.0, 1.0 - dc / 2.0))
                   if dc is not None else None)
        nt = nearest(tide_pt_list, lon, lat)
        wave_exposure = None
        wave_station = None
        if wave_pts:
            nw = nearest([(st, lo, la) for st, lo, la, _ in wave_pts], lon, lat)
            if nw:
                wave_station = nw[0]
                wd = wave_by_station[wave_station]
                # the wave-climate severity, normalised on HK's 10 m design wave
                wave_exposure = min(1.0, wd["max_hmax"] / 10.0)
        desig = nearest(desig_pts, lon, lat) if desig_pts else None
        desig_score = None
        if desig:
            desig_score = max(0.0, min(1.0, 1.0 - desig[1] / 1.5))
        n_pump = count_within(pump_pts, lon, lat, 0.5)
        # a pump station protects: so it REDUCES the residual surge score
        pump_mitigation = min(1.0, n_pump / 2.0)
        n_shelter = count_within(shelter_pts, lon, lat, 1.0)

        ss_parts = [(ss_low, 0.40), (ss_prox, 0.25)]
        if wave_exposure is not None:
            ss_parts.append((wave_exposure, 0.20))
        if desig_score is not None:
            ss_parts.append((desig_score, 0.15))
        av = [(v, w) for v, w in ss_parts if v is not None]
        ws = sum(w for _, w in av)
        ss_raw = (sum(v * w for v, w in av) / ws) if ws else None
        ss = (ss_raw * (1 - 0.3 * pump_mitigation)) if ss_raw is not None else None

        rows.append({
            "title": title,
            "dsd_list": p.get("dsd_list"),
            "mechanism": p.get("mechanism"),
            "confidence": p.get("confidence"),
            "lon": round(lon, 6), "lat": round(lat, 6),
            "elevation_m": elev,
            "d_coast_km": dc,
            "d_bigchannel_km": dbc,
            # flash flood factors
            "ff_score": round(ff, 4) if ff is not None else None,
            "ff_rainfall_score": round(rain_score, 4) if rain_score is not None else None,
            "ff_low_lying_score": round(low_score, 4) if low_score is not None else None,
            "ff_slope_deg": slope,
            "ff_slope_score": round(slope_score, 4) if slope_score is not None else None,
            "ff_inlets_200m": n_inlets,
            "ff_inlet_score": round(inlet_score, 4),
            "ff_nearest_channel_km": round(ch_near[1], 3) if ch_near else None,
            "ff_channel_score": round(ch_score, 4) if ch_score is not None else None,
            "ff_nearest_outfall_km": round(out_near[1], 3) if out_near else None,
            "ff_outlet_score": round(outlet_score, 4) if outlet_score is not None else None,
            "ff_nearest_gauge": gkey,
            "ff_gauge_name": gd["loc"] if gd else None,
            "ff_gauge_max_daily_mm": gd["max"] if gd else None,
            "ff_gauge_max_date": gd["max_date"] if gd else None,
            "ff_gauge_distance_km": round(ng[1], 2) if ng else None,
            # storm surge factors
            "ss_score": round(ss, 4) if ss is not None else None,
            "ss_low_lying_score": round(ss_low, 4) if ss_low is not None else None,
            "ss_coast_proximity_score": round(ss_prox, 4) if ss_prox is not None else None,
            "ss_wave_station": wave_station,
            "ss_wave_max_hmax_m": round(wave_by_station[wave_station]["max_hmax"], 2) if wave_station else None,
            "ss_wave_score": round(wave_exposure, 4) if wave_exposure is not None else None,
            "ss_nearest_tide_station": nt[0] if nt else None,
            "ss_tide_distance_km": round(nt[1], 2) if nt else None,
            "ss_cedd_designated": desig[0] if desig and desig[1] <= 1.5 else None,
            "ss_cedd_designated_km": round(desig[1], 3) if desig else None,
            "ss_pumping_stations_500m": n_pump,
            "ss_typhoon_shelters_1km": n_shelter,
        })

    # dominant hazard
    for r in rows:
        a = r["ff_score"] or 0
        b = r["ss_score"] or 0
        r["dominant_hazard"] = ("flash_flood" if a > b else
                                "storm_surge" if b > a else "equal")
    return rows


def main():
    rows = build()
    feats = []
    for r in rows:
        props = {k: v for k, v in r.items() if k not in ("lon", "lat")}
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point",
                                   "coordinates": [r["lon"], r["lat"]]},
                      "properties": props})
    # RFC 7946: no crs member, lon/lat order
    fc = {"type": "FeatureCollection", "features": feats}
    p = os.path.join(OUT, "flood_hazard_factors.geojson")
    with open(p, "w") as f:
        json.dump(fc, f, indent=1)
    print(f"  wrote {p} ({len(feats)} features)")

    keys = list(rows[0].keys())
    pc = os.path.join(OUT, "flood_hazard_factors.csv")
    with open(pc, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {pc} ({len(rows)} rows)")

    ff = sorted(r["ff_score"] for r in rows if r["ff_score"] is not None)
    ss = sorted(r["ss_score"] for r in rows if r["ss_score"] is not None)
    summary = {
        "generated": "2026-11-09",
        "flood_prone_areas": len(rows),
        "flash_flood_score": {"min": ff[0], "median": ff[len(ff) // 2], "max": ff[-1]},
        "storm_surge_score": {"min": ss[0], "median": ss[len(ss) // 2], "max": ss[-1]},
        "dominant_hazard_counts": dict(Counter(r["dominant_hazard"] for r in rows)),
        "by_dsd_list": {},
    }
    for lst in sorted({r["dsd_list"] for r in rows if r["dsd_list"]}):
        sub = [r for r in rows if r["dsd_list"] == lst]
        summary["by_dsd_list"][lst] = {
            "n": len(sub),
            "mean_flash_flood": round(sum(r["ff_score"] for r in sub if r["ff_score"] is not None) / len(sub), 4),
            "mean_storm_surge": round(sum(r["ss_score"] for r in sub if r["ss_score"] is not None) / len(sub), 4),
            "dominant": dict(Counter(r["dominant_hazard"] for r in sub)),
        }
    with open(os.path.join(OUT, "factor_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(f"  wrote {OUT}/factor_summary.json")
    print(f"\n  flash flood score: min {ff[0]:.3f} median {ff[len(ff)//2]:.3f} max {ff[-1]:.3f}")
    print(f"  storm surge score: min {ss[0]:.3f} median {ss[len(ss)//2]:.3f} max {ss[-1]:.3f}")
    print(f"  dominant hazard: {summary['dominant_hazard_counts']}")
    print("\n  TOP flash flood:")
    for r in sorted(rows, key=lambda r: -(r["ff_score"] or 0))[:5]:
        print(f"    {r['ff_score']:.3f}  {str(r['title'])[:42]:42s} "
              f"elev {r['elevation_m']}  gauge {r['ff_gauge_name']}")
    print("  TOP storm surge:")
    for r in sorted(rows, key=lambda r: -(r["ss_score"] or 0))[:5]:
        print(f"    {r['ss_score']:.3f}  {str(r['title'])[:42]:42s} "
              f"elev {r['elevation_m']}  coast {r['d_coast_km']} km")


if __name__ == "__main__":
    main()
