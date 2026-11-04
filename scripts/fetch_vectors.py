#!/usr/bin/env python3
"""Fetch HK landslide + geotechnical variables from CSDI / ArcGIS REST.

Outputs CSV per layer in ./raw/ and a combined points table.
Sources (all keyless ArcGIS REST):
  incidents  : cedd_rcd_1640249280153_17521  (Location of Landslide Incidents)
  entli      : cedd_rcd_1636520697377_96152  (Enhanced Natural Terrain Landslide Inventory)
  geology   : cedd_rcd_1636520962284_7237   (Geological Map 1:100,000, layer 5 GEOLOGY)
  raingauge  : cedd_rcd_1636517963140_47030  (GEO Raingauge Data)
"""
import json, os, sys, time, csv
import urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
os.makedirs(RAW, exist_ok=True)
UA = {"User-Agent": "hermes-gis/1.0"}
CSDI = "https://portal.csdi.gov.hk/server/rest/services/common"


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.loads(urllib.request.urlopen(req, timeout=180).read())
        except Exception as e:
            last = e
            time.sleep(3 * (i + 1))
    raise last


def query_all(base, where="1=1", outfields="*", page=2000):
    """Page through a FeatureServer layer, return list of attribute dicts."""
    feats = []
    offset = 0
    while True:
        p = urllib.parse.urlencode({
            "where": where, "outFields": outfields, "returnGeometry": "false",
            "resultRecordCount": page, "resultOffset": offset, "f": "json"})
        d = get(f"{base}/query?{p}")
        if "error" in d:
            raise RuntimeError(d["error"])
        fs = d.get("features", [])
        feats.extend([f["attributes"] for f in fs])
        if len(fs) < page:
            break
        offset += page
        print(f"   ...{len(feats)} fetched", flush=True)
    return feats


def dump(name, rows, fields=None):
    if not rows:
        print("EMPTY", name); return
    flds = fields or list(rows[0].keys())
    p = os.path.join(RAW, name)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=flds, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {p} ({len(rows)} rows)", flush=True)


def main():
    # 1. Landslide incidents 2000+ (negative+positive labels)
    print("== incidents ==", flush=True)
    inc_base = f"{CSDI}/cedd_rcd_1640249280153_17521/FeatureServer/0"
    inc = query_all(inc_base, outfields="INCID,FAILDATE,CALLDATE,EASTING,NORTHING,LOCATION,FEATTYPE,SCALE,CONSEC,FACAFF")
    dump("incidents.csv", inc)

    # 2. ENTLI historical landslides 1924-2022 (extra positives, with slope/cover)
    print("== ENTLI crown ==", flush=True)
    entli_base = f"{CSDI}/cedd_rcd_1636520697377_96152/FeatureServer/0"
    entli = query_all(entli_base, outfields="SLIDE_TYPE,M_WIDTH,S_LENGTH,SLOPE,COVER,YEAR_1,HEADELEV,TAILELEV,ELE_DIFF,GULLY,CLASS,ENTLI_NO,EASTING,NORTHING")
    dump("entli_crown.csv", entli)

    # 3. Geology polygons (1:100k) - only GEOLOGY layer
    print("== geology ==", flush=True)
    geo_base = f"{CSDI}/cedd_rcd_1636520962284_7237/FeatureServer/5"
    geo = query_all(geo_base, outfields="Geol_Type")
    dump("geology.csv", geo)

    # 4. Raingauge daily rainfall 2000-2026 (heavy tail only for model input)
    print("== raingauge (2005-2026) ==", flush=True)
    rg_base = f"{CSDI}/cedd_rcd_1636517963140_47030/FeatureServer/0"
    rg = query_all(rg_base, where="Date_ >= '20050101'", outfields="Date_,Raingauge_No,Location,Easting,Northing,Rainfall")
    dump("raingauge.csv", rg)


if __name__ == "__main__":
    main()
