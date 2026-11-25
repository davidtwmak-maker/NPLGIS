#!/usr/bin/env python3
"""Where does each Chinese area name actually sit?

The Chinese address of a shop names its area - 尖沙咀, 柴灣, 新蒲崗.
The government geocoder knows where those places are, and it knows it
independently of any shop pin. So the area's district is taken from
the geocoder's own answers for the area name, then confirmed against
the District Council boundary layer.

Two rules keep this honest:

  - CONSENSUS, not the first hit. The geocoder returns a street, a
    pier and the area itself; the first hit for 九龍灣 fell outside
    every district, and for 竹園 it landed in Sai Kung. The district
    is the one most hits agree on, and an area with no clear majority
    is left unmapped.
  - CROSS-CHECK against the shop pins. Where the pins agree with the
    geocoder, the mapping is safe. Where they disagree, the area is
    dropped rather than guessed.

Deriving the mapping from shop pins alone would inherit the pins'
own errors - the two 柴灣 shops are pinned in Tsuen Wan, 40 km from
Chai Wan, and a pin-derived map would have said Chai Wan is in Tsuen
Wan.

Usage:  derive_area_dc.py            print the mapping
        derive_area_dc.py --write    also write it into geocode_shops.py
"""
import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geocode_shops as G

DC_PATH = Path("/Users/davidhermes/nplgis/assets/data/self-study-rooms/"
                "district_boundaries.geojson.gz")

AREA_CANDIDATES = [
    "尖沙咀", "油麻地", "旺角", "太子", "深水埗", "長沙灣", "荔枝角",
    "石門", "新蒲崗", "九龍灣", "觀塘", "鑽石山", "紅磡", "土瓜灣",
    "黃大仙", "竹園", "沙田", "大圍", "火炭", "馬鞍山", "荃灣",
    "葵涌", "葵芳", "青衣", "柴灣", "銅鑼灣", "灣仔", "北角", "太古",
    "鰂魚涌", "筲箕灣", "西灣河", "小西灣", "跑馬地", "香港仔",
    "鴨脷洲", "薄扶林", "屯門", "元朗", "天水圍", "錦田", "上水",
    "粉嶺", "沙頭角", "將軍澳", "調景嶺", "西貢", "大埔",
    "海濱", "山頂", "西環", "上環", "中環", "堅尼地城", "大坑",
    "元朗", "慈雲山", "樂富", "日出康城", "太古城", "慈雲山",
]

MIN_SHARE = 0.6      # the area's hits must agree this strongly
MAX_DISAGREE = 0.25  # and the shop pins must not mostly disagree


def dc_districts():
    with gzip.open(DC_PATH, "rt", encoding="utf-8") as f:
        gj = json.load(f)
    out = []
    for feat in gj["features"]:
        g = feat["geometry"]
        rings = ([g["coordinates"][0]] if g["type"] == "Polygon"
                 else [p[0] for p in g["coordinates"]])
        out.append((feat["properties"].get("dc_eng"), rings))
    return out


def dc_of(lat, lon, districts):
    for name, rings in districts:
        for r in rings:
            if G._in_ring(lon, lat, r):
                return name
    return None


def main():
    cache = G.load_cache()
    districts = dc_districts()

    # ---- 1. the geocoder's own answer for each area name -----------
    geo_votes = {}
    for area in dict.fromkeys(AREA_CANDIDATES):
        hits, _err = G.geocode(area, cache)
        c = Counter()
        for h in hits:
            cn = str(h.get("cname") or "")
            en = str(h.get("ename") or "")
            blob = (cn + " " + en).lower()
            if area not in blob and area.lower() not in blob:
                continue
            try:
                la, lo = float(h["lat"]), float(h["lon"])
            except Exception:
                continue
            d = dc_of(la, lo, districts)
            if d:
                c[d] += 1
        geo_votes[area] = c

    # ---- 2. the shop pins' answer, as a cross-check ------------------
    pin_votes = {}
    rows = list(csv.DictReader(open(HERE / "baw_shops.csv", encoding="utf-8")))
    for area in geo_votes:
        c = Counter()
        for r in rows:
            addr = r.get("address_zh") or ""
            if area not in addr:
                continue
            try:
                la = float(r["lat"]) if r.get("lat") else None
                lo = float(r["lng"]) if r.get("lng") else None
            except ValueError:
                continue
            d = dc_of(la, lo, districts)
            if d:
                c[d] += 1
        pin_votes[area] = c

    # ---- 3. agree, or drop ------------------------------------------
    mapping = {}
    print(f"{'area':10} {'geocoder':22} {'pins':22} verdict")
    for area in geo_votes:
        g, p = geo_votes[area], pin_votes[area]
        if not g:
            print(f"{area:10} {'no hits':22} {'':22} dropped")
            continue
        gw, gn = g.most_common(1)[0]
        gshare = gn / sum(g.values())
        if gshare < MIN_SHARE:
            print(f"{area:10} {str(dict(g)):22} {'':22} dropped (no consensus)")
            continue
        if p:
            pw, pn = p.most_common(1)[0]
            pshare = pn / sum(p.values())
            if pw != gw and pshare > MAX_DISAGREE:
                print(f"{area:10} {gw + ' ' + f'{gshare:.2f}':22} "
                      f"{pw + ' ' + f'{pshare:.2f}':22} dropped (pins disagree)")
                continue
            print(f"{area:10} {gw + ' ' + f'{gshare:.2f}':22} "
                  f"{pw + ' ' + f'{pshare:.2f}':22} kept")
        else:
            print(f"{area:10} {gw + ' ' + f'{gshare:.2f}':22} {'(no pins)':22} kept")
        mapping[area] = gw

    print(f"\n# {len(mapping)} areas resolved")
    print("AREA_TO_DC = {")
    for area, d in sorted(mapping.items()):
        print(f'    "{area}": "{d}",')
    print("}")

    if "--write" in sys.argv:
        target = HERE / "geocode_shops.py"
        text = target.read_text(encoding="utf-8")
        start = text.index("AREA_TO_DC = {")
        end = text.index("\n}", start) + 2
        block = ("AREA_TO_DC = {\n"
                 + "".join(f'    "{a}": "{d}",\n' for a, d in sorted(mapping.items()))
                 + "}")
        target.write_text(text[:start] + block + text[end:], encoding="utf-8")
        print(f"\nwrote {target}")


if __name__ == "__main__":
    sys.exit(main())
