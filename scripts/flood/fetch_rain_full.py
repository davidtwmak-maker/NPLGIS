#!/usr/bin/env python3
"""
Fetch the COMPLETE GEO raingauge daily record (1984-2026, 1,126,191 rows).

Why this is a separate script
-----------------------------
The first fetch deliberately pulled only `Date_ >= '20200101'` (213,570
rows) to keep the download small. That is fine for the modern record but
it is NOT enough for the flash-flood rainfall factor: the extreme daily
totals that define the risk sit in the older record too, and the HK record
day (Stanley, 8 September 2023) is inside the window - but a gauge's
*own* long-run maximum may not be. Scoring a gauge on 6 years instead of
42 systematically understates the wettest locations.

The server holds all 1,126,191 rows (verified: 1984 -> 2026, ~32,900 per
year for the full gauge network). This pulls all of it.

The Rainfall field is TEXT with quality markers:
  '12.5'   clean
  '12.5#'  provisional
  '***'    missing
  ''       blank
They are preserved verbatim in the raw file and parsed in
derive_flood_factors.py.

Run:  ls-venv/bin/python fetch_rain_full.py
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

DATASET = "cedd_rcd_1636517963140_47030"
BASE = (f"https://portal.csdi.gov.hk/server/rest/services/common/"
        f"{DATASET}/FeatureServer/0/query")
CHUNK = 3000


def get(url, tries=4, timeout=300):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "hermes-gis-flood"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:                     # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)

    # how many rows are there, really?
    st = [{"statisticType": "count", "onStatisticField": "Date_",
           "outStatisticField": "n"}]
    u = (f"{BASE}?where=1%3D1&outFields=*&f=json&outStatistics="
         f"{urllib.parse.quote(json.dumps(st))}")
    total = json.loads(get(u))["features"][0]["attributes"]["COUNT_EXPR0"]
    print(f"server holds {total:,} rows")

    feats = []
    off = 0
    t0 = time.time()
    while True:
        u = (f"{BASE}?where=1%3D1&outFields=Date_,Raingauge_No,Location,"
             f"Rainfall&returnGeometry=false&f=json"
             f"&resultRecordCount={CHUNK}&resultOffset={off}")
        js = json.loads(get(u))
        if "features" not in js:
            print("ERROR response:", str(js)[:300])
            raise SystemExit(1)
        batch = js["features"]
        feats.extend(batch)
        off += len(batch)
        if off % 60000 == 0 or not batch:
            print(f"  {off:,} / {total:,}  ({time.time()-t0:.0f}s)")
        if not batch or off >= total:
            break

    # arcgis returns a dict for the first row and a list for the rest
    norm = []
    for f in feats:
        a = f["attributes"]
        if isinstance(a, dict):
            a = [a]
        for row in a:
            norm.append({"attributes": row})

    print(f"fetched {len(norm):,} rows")
    if len(norm) != total:
        print(f"  NOTE: expected {total:,}, got {len(norm):,}")

    out = {"type": "FeatureCollection", "features": norm}
    p = os.path.join(RAW, "rain_gauges_daily_full.geojson")
    with open(p, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {p}  ({os.path.getsize(p)/1e6:.1f} MB)")

    pz = p + ".gz"
    with open(p, "rb") as fi, gzip.open(pz, "wb", compresslevel=9) as fo:
        fo.write(fi.read())
    print(f"wrote {pz}  ({os.path.getsize(pz)/1e6:.1f} MB)")

    # a quick self-check: the number of gauges and the date range
    gauges = set()
    dates = []
    for f in norm:
        r = f["attributes"]
        gauges.add(r.get("Raingauge_No"))
        dates.append(str(r.get("Date_")))
    print(f"gauges: {len(gauges)}")
    print(f"dates: {min(dates)} .. {max(dates)}")


if __name__ == "__main__":
    main()
