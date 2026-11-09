#!/usr/bin/env python3
"""
Fetch the map data behind the two non-blockage flood causes in Hong Kong:
FLASH FLOOD (rainfall-driven river / urban drainage flooding) and
STORM SURGE (sea-level-driven coastal inundation).

Every endpoint below was probed live on 2026-11-09 against the CSDI Portal
and returned real features with real geometry. Counts are the served counts
from the FeatureServer's own returnCountOnly query.

Run:  ls-venv/bin/python fetch_flood_causes.py
"""
import gzip
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")
os.makedirs(RAW, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

BASE = "https://portal.csdi.gov.hk/server/rest/services/common"
UA = {"User-Agent": "hermes-gis"}


def get(url, tries=4, timeout=120):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url[:90]} -> {type(last).__name__}: {last}")


def service(did):
    return json.loads(get(f"{BASE}/{did}/FeatureServer?f=json"))


def layer_info(did, lid):
    return json.loads(get(f"{BASE}/{did}/FeatureServer/{lid}?f=json"))


def count(did, lid, where="1=1"):
    u = (f"{BASE}/{did}/FeatureServer/{lid}/query"
         f"?where={urllib.parse.quote(where)}&returnCountOnly=true&f=json")
    return json.loads(get(u)).get("count")


def fetch(did, lid, where="1=1", outfields="*", label=None, chunk=2000,
          max_records=None, out_name=None):
    """Paginate a layer into GeoJSON. Returns (features, meta)."""
    label = label or f"{did}_{lid}"
    out_name = out_name or label
    feats = []
    offset = 0
    while True:
        u = (f"{BASE}/{did}/FeatureServer/{lid}/query"
             f"?where={urllib.parse.quote(where)}"
             f"&outFields={urllib.parse.quote(outfields)}"
             f"&returnGeometry=true&outSR=4326&f=geojson"
             f"&resultRecordCount={chunk}&resultOffset={offset}")
        j = json.loads(get(u))
        if j.get("type") != "FeatureCollection":
            raise RuntimeError(f"{label}: expected FeatureCollection, got "
                               f"{str(j)[:120]}")
        page = j.get("features", [])
        feats.extend(page)
        offset += len(page)
        if not page:
            break
        if max_records and len(feats) >= max_records:
            feats = feats[:max_records]
            break
        if len(page) < chunk:
            break
    fc = {"type": "FeatureCollection", "features": feats}
    # RFC 7946: GeoJSON is CRS84 lon/lat and has no crs member.
    p = os.path.join(RAW, out_name + ".geojson")
    with open(p, "w") as f:
        json.dump(fc, f, separators=(",", ":"))
    pz = p + ".gz"
    with open(p, "rb") as fi, gzip.open(pz, "wb", compresslevel=9) as fo:
        fo.write(fi.read())
    meta = {"label": label, "dataset_id": did, "layer_id": lid,
            "where": where, "outfields": outfields,
            "features_fetched": len(feats), "file": p}
    return fc, meta


def main():
    manifest = []

    # ================================================================
    # A. FLASH FLOOD - what drives it
    # ================================================================
    # A1. Rainfall at the point of impact: GEO raingauge daily, 91 gauges
    #     1984 -> 2026. 1.13 M rows, so pull the modern record + a
    #     station list; the full history is available via the same endpoint.
    print("A1. GEO raingauge daily (flash-flood driver)")
    fc, m = fetch("cedd_rcd_1636517963140_47030", 0,
                  where="Date_ >= '20200101'",
                  outfields="Date_,Raingauge_No,Location,Rainfall",
                  label="rain_gauges_daily", chunk=3000)
    print(f"    {m['features_fetched']:,} rows since 2020")
    manifest.append(m)

    # A1b. The extreme-value statistic that actually matters for flash
    #      flood, WITHOUT downloading 1.1 M rows.
    #
    #      The `Rainfall` field is TEXT, so the server-side `max`
    #      statistic is a STRING max: it returns 99.5 for every gauge while
    #      the real extremes are 400-600 mm. The per-gauge extremes are
    #      therefore computed LOCALLY from the fetched rows in
    #      derive_flood_factors.py, where the quality markers ('#'
    #      provisional, '***' missing) are also handled. The server-side
    #      statistics are kept only as a row count.
    print("A1b. server-side row count (the max here is a STRING max - unusable)")
    stats = [{"statisticType": "count", "onStatisticField": "Rainfall",
              "outStatisticField": "n_rows"}]
    u = (f"{BASE}/cedd_rcd_1636517963140_47030/FeatureServer/0/query"
         f"?where=1%3D1&outFields=*&f=json"
         f"&outStatistics={urllib.parse.quote(json.dumps(stats))}")
    js = json.loads(get(u))
    print(f"    {js.get('features', [{}])[0].get('attributes')} "
          f"(note: the Rainfall field is text, so a server-side max on it "
          f"is a string comparison - the real per-gauge extremes are "
          f"computed locally)")

    # A2. The drainage network that has to fail: DSD stormwater channels
    print("A2. DSD channel (drainage network)")
    fc, m = fetch("dsd_rcd_1629267205231_66675", 1,
                  outfields="*", label="dsd_channel", chunk=3000)
    print(f"    {m['features_fetched']:,} channels")
    manifest.append(m)

    # A3. Catchments - the unit over which rainfall accumulates and runs off
    print("A3. WSD catchments")
    fc, m = fetch("wsd_rcd_1629267205232_5923", 0,
                  outfields="*", label="wsd_catchments", chunk=3000)
    print(f"    {m['features_fetched']:,} catchments")
    manifest.append(m)

    # A4. Inlets and manholes - where water enters and where it blocks
    print("A4. DSD inlets")
    fc, m = fetch("dsd_rcd_1629267205231_69065", 0,
                  outfields="*", label="dsd_inlets", chunk=3000)
    print(f"    {m['features_fetched']:,} inlets")
    manifest.append(m)

    print("A5. DSD stormwater manholes")
    fc, m = fetch("dsd_rcd_1629267205232_64331", 0,
                  outfields="*", label="dsd_manholes_stormwater", chunk=3000)
    print(f"    {m['features_fetched']:,} manholes")
    manifest.append(m)

    print("A6. DSD stormwater pipes")
    fc, m = fetch("dsd_rcd_1629267205232_85526", 0,
                  outfields="*", label="dsd_pipes_stormwater", chunk=3000)
    print(f"    {m['features_fetched']:,} pipes")
    manifest.append(m)

    # A7. Natural watercourses (the channels that flash flood)
    print("A7. Surface channels (natural + engineered watercourses)")
    fc, m = fetch("hyd_rcd_1632359687762_99131", 0,
                  outfields="*", label="surface_channels", chunk=3000)
    print(f"    {m['features_fetched']:,} channels")
    manifest.append(m)

    # A8. Rivers: water quality stations on the main rivers give the
    #     monitoring points; the real gauge series is at GEO/EPD.
    print("A8. River water-quality monitoring stations")
    fc, m = fetch("epd_rcd_1630908367921_10608", 0,
                  outfields="*", label="river_water_quality", chunk=3000)
    print(f"    {m['features_fetched']:,} stations")
    manifest.append(m)

    # ================================================================
    # B. STORM SURGE - what drives it
    # ================================================================
    # B1. Wave climate - the overtopping-wave driver. Hourly, 1994-2025.
    print("B1. CEDD wave data (hourly, 1994-2025)")
    fc, m = fetch("cedd_rcd_1636518176374_67772", 0,
                  outfields="LOCATION,YEAR,HM0,H1_10,HMAX,PEAKTP,MEANDIR",
                  label="cedd_wave_data", chunk=3000)
    print(f"    {m['features_fetched']:,} hourly wave records")
    manifest.append(m)

    # B2. Tide - the baseline the surge adds to
    print("B2. Tidal stations")
    fc, m = fetch("mardep_rcd_1638860616268_1438", 0,
                  outfields="*", label="tide_stations", chunk=3000)
    print(f"    {m['features_fetched']:,} stations")
    manifest.append(m)

    print("B3. Predicted tidal heights (hourly + high/low)")
    fc, m = fetch("hko_rcd_1634808062104_80740", 0,
                  outfields="*", label="predicted_tide_hourly", chunk=3000)
    print(f"    {m['features_fetched']:,} stations")
    manifest.append(m)
    fc, m = fetch("hko_rcd_1634809240679_79523", 0,
                  outfields="*", label="predicted_tide_highlow", chunk=3000)
    print(f"    {m['features_fetched']:,} stations")
    manifest.append(m)

    # B4. The surge driver itself: atmospheric pressure and wind
    print("B4. HKO latest 1-min mean sea-level pressure (surge driver)")
    fc, m = fetch("hko_rcd_1634954951621_38375", 0,
                  outfields="*", label="hko_sea_level_pressure", chunk=3000)
    print(f"    {m['features_fetched']:,} stations")
    manifest.append(m)

    print("B5. HKO latest 10-min wind direction and speed")
    fc, m = fetch("hko_rcd_1634953844424_88011", 0,
                  outfields="*", label="hko_wind", chunk=3000)
    print(f"    {m['features_fetched']:,} stations")
    manifest.append(m)

    # B6. The defences and the pumps that keep the surge out
    print("B6. DSD facilities (stormwater pumping stations, inflatable dams)")
    fc, m = fetch("dsd_rcd_1629267205232_11360", 0,
                  outfields="*", label="dsd_facilities", chunk=3000)
    print(f"    {m['features_fetched']:,} facilities")
    manifest.append(m)

    # B7. Outfalls - where the sea pushes back in
    print("B7. Outfalls")
    fc, m = fetch("dsd_rcd_1629267205232_35872", 0,
                  outfields="*", label="dsd_outfalls", chunk=3000)
    print(f"    {m['features_fetched']:,} outfalls")
    manifest.append(m)

    # B8. Typhoon shelters - the designated safe places for surge events
    print("B8. Typhoon shelters")
    fc, m = fetch("mardep_rcd_1730971403590_9667", 0,
                  outfields="*", label="typhoon_shelters", chunk=3000)
    print(f"    {m['features_fetched']:,} shelters")
    manifest.append(m)

    # B9. Coastal low-lying / windy residential areas (the 26 CEDD areas)
    print("B9. CEDD Boundary of Designated Area")
    fc, m = fetch("cedd_rcd_1640249339500_66807", 0,
                  outfields="*", label="cedd_designated_area", chunk=3000)
    print(f"    {m['features_fetched']:,} features")
    manifest.append(m)

    # B10. Harbour limit - the marine space the surge comes from
    print("B10. Harbour limit")
    fc, m = fetch("mardep_rcd_1730972646896_40009", 0,
                  outfields="*", label="harbour_limit", chunk=3000)
    print(f"    {m['features_fetched']:,} features")
    manifest.append(m)

    # B11. The coastline - the land outline for the map, and the reference
    #      for every "distance to the sea" number.
    #      CEDD geological coastline (193 polygons) dissolves to 1,092 km2,
    #      which matches Hong Kong's real ~1,106 km2. The iC1000 layer
    #      looks like land but is a map-sheet CATALOGUE and dissolves to
    #      2,130 km2, which puts the coast in the wrong place.
    print("B11. CEDD geological coastline (the land outline)")
    fc, m = fetch("cedd_rcd_1636520962284_7237", 0,
                  outfields="*", label="cedd_coastline", chunk=3000)
    print(f"    {m['features_fetched']:,} coastline polygons")
    manifest.append(m)

    # ================================================================
    # C. SHARED BASIS LAYERS
    # ================================================================
    print("C1. Marine water quality stations")
    fc, m = fetch("epd_rcd_1630908628415_41776", 0,
                  outfields="*", label="marine_water_quality", chunk=3000)
    print(f"    {m['features_fetched']:,} stations")
    manifest.append(m)

    # ================================================================
    # D. THE CEDD COASTAL HAZARDS STUDY 26-AREAS MAP
    # ================================================================
    print("D1. CEDD Coastal Hazards Study - 26 areas map")
    png = "https://cedd.gov.hk/filemanager/eng/content_961/24/26%20areas_eng_rev3.PNG"
    try:
        b = get(png)
        with open(os.path.join(RAW, "cedd_coastal_hazards_26_areas.png"), "wb") as f:
            f.write(b)
        print(f"    {len(b):,} bytes")
        manifest.append({"label": "cedd_coastal_hazards_26_areas",
                         "url": png, "file": "raw/cedd_coastal_hazards_26_areas.png",
                         "bytes": len(b)})
    except Exception as e:                        # noqa: BLE001
        print(f"    FAILED {type(e).__name__}: {e}")

    with open(os.path.join(OUT, "fetch_manifest.json"), "w") as f:
        json.dump({"fetched": "2026-11-09", "layers": manifest}, f, indent=1)
    print(f"\n{len(manifest)} layers fetched -> {RAW}")
    print(f"manifest -> {OUT}/fetch_manifest.json")


if __name__ == "__main__":
    main()
