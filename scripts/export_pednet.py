#!/usr/bin/env python3
"""Export the CSDI 3D Pedestrian Network (landsd_rcd_1637222018065_52265)
full layer to GeoJSON (WGS84), paged at 3000 features, streaming to disk.

Target class for the "exposed to sun & rain" map: Location=1 (Outdoor) AND
WeatherProof=2 (NonCovered). The full layer is exported so covered/indoor
segments can be symbolised for contrast.
"""
import json
import pathlib
HERE = pathlib.Path(__file__).resolve().parent
import sys
import time
import urllib.parse
import urllib.request

SERVICE = ("https://portal.csdi.gov.hk/server/rest/services/common/"
           "landsd_rcd_1637222018065_52265/FeatureServer/0/query")
OUTDIR = str(HERE)
OUT = f"{OUTDIR}/pedestrian_network_hk.geojson"
PAGE = 3000
FIELDS = ("PedestrianRouteID,FeatureType,WeatherProof,Location,"
          "StreetNameEN,StreetNameTC,Gradient,CrossingFeature,LevelSource")


def fetch(offset, attempts=5):
    params = {
        "where": "1=1",
        "outFields": FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": str(PAGE),
        "resultOffset": str(offset),
    }
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"offset {offset} failed after {attempts}: {last}")


def main():
    offset = 0
    total = 0
    first = True
    started = time.time()
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","features":[')
        while True:
            page = fetch(offset)
            feats = page.get("features", [])
            if not feats:
                break
            for f in feats:
                fh.write("" if first else ",")
                first = False
                json.dump(f, fh, ensure_ascii=False, separators=(",", ":"))
            total += len(feats)
            offset += PAGE
            elapsed = time.time() - started
            print(f"[{elapsed:6.0f}s] {total} features exported", flush=True)
            if len(feats) < PAGE:
                break
        fh.write("]}")
    print(f"DONE {total} features -> {OUT}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
