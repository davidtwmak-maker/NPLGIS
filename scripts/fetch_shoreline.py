#!/usr/bin/env python3
"""Fetch the Esri China (HK) iB1000 shoreline for Hong Kong as WGS84 GeoJSON.

Layer 19 of Shoreline_view: 9,033 polyline features in EPSG:3857. Paginated at
2,000 per page. Source: Esri China (Hong Kong) Ltd, from LandsD iB1000.
"""
import json
import os
import subprocess

BASE = ("https://services3.arcgis.com/6j1KwZfY2fZrfNMR/arcgis/rest/services/"
        "Shoreline_view/FeatureServer/19/query")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw", "shoreline_ib1000.geojson")
TMP = OUT + ".tmp"
PAGE = 2000

all_feats = []
offset = 0
served = None
while True:
    url = (f"{BASE}?where=1%3D1&outFields=SHORELINETYPE,STATUS&returnGeometry=true"
           f"&outSR=4326&f=geojson&resultOffset={offset}&resultRecordCount={PAGE}")
    r = subprocess.run(["curl", "-s", "-m", "180", "-A", "hermes-gis/1.0", url],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except Exception:
        print(f"  offset {offset}: bad JSON ({len(r.stdout)} bytes)")
        break
    if "features" not in d:
        print(f"  offset {offset}: error -> {str(d)[:150]}")
        break
    feats = d["features"]
    print(f"  offset {offset}: {len(feats)} features")
    all_feats.extend(feats)
    if len(feats) < PAGE:
        break
    offset += PAGE
    if offset > 12000:
        print("  safety stop")
        break

fc = {
    "type": "FeatureCollection",
    "name": "shoreline_ib1000",
    "metadata": {
        "source": "Esri China (Hong Kong) Ltd - Shoreline (iB1000), from LandsD",
        "service": "https://services3.arcgis.com/6j1KwZfY2fZrfNMR/arcgis/rest/services/Shoreline_view/FeatureServer/19",
        "served_count": 9033,
        "fetched_count": len(all_feats),
        "fetched_on": "2026-10-22",
        "note": "polyline shoreline, reprojected to WGS84 on export (outSR=4326)",
    },
    "features": all_feats,
}
json.dump(fc, open(TMP, "w"), ensure_ascii=False)
os.rename(TMP, OUT)
print(f"wrote {OUT}  ({len(all_feats)} features, {os.path.getsize(OUT)} bytes)")