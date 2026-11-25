#!/usr/bin/env python3
"""Geocode the HKCardPrice shop addresses with the Hong Kong Government's
own address index.

WHY THIS DATASET IS DIFFERENT
    The earlier shop list (BAW VAULT) carried its own latitude and
    longitude pins, which were already good enough for a choropleth. The
    HKCardPrice addresses are written the way an address is written on an
    envelope, and the government index keys on exactly that - so these
    geocode cleanly and the match can be VERIFIED rather than assumed.

THE MATCH
    A candidate hit must be a BUILDING (type=B) whose own address carries
    the street number we are looking for, and whose name or address
    carries the building name. A hit that states a different number is a
    different building and is rejected outright.

    The result is checked a second way: the matched point must fall in
    the district the directory says, using the authoritative District
    Council boundary polygons.

OUTPUT
    shops_hkcardprice_geocoded.json
"""
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from geocode_venues import (  # noqa: E402
    HK80_TO_WGS, district_of, hits_of, load_cache, query, save_cache,
)

RAW = HERE / "raw/hkcardprice_shops.json"
OUT = HERE / "shops_hkcardprice_geocoded.json"

# The District Council district names, in Chinese and English. The
# directory gives the Chinese name; the government boundary layer gives
# the English one, so the two are translated before they are compared.
DC_EN = {
    "中西區": "Central and Western",
    "灣仔區": "Wan Chai",
    "東區": "Eastern",
    "南區": "Southern",
    "油尖旺區": "Yau Tsim Mong",
    "深水埗區": "Sham Shui Po",
    "九龍城區": "Kowloon City",
    "黃大仙區": "Wong Tai Sin",
    "觀塘區": "Kwun Tong",
    "葵青區": "Kwai Tsing",
    "荃灣區": "Tsuen Wan",
    "屯門區": "Tuen Mun",
    "元朗區": "Yuen Long",
    "北區": "North",
    "大埔區": "Tai Po",
    "沙田區": "Sha Tin",
    "西貢區": "Sai Kung",
    "離島區": "Islands",
}

BUILDING_WORDS = [
    "中心", "大廈", "廣場", "商場", "大樓", "工廈", "工業中心", "工業大廈",
    "工商中心", "工廠大廈", "花園", "別墅", "地帶",
]
# The suffixes that carry no identifying information. Two sources may call
# the same building 工業大廈 or 工廠大廈, so the distinctive part is what
# gets compared.
GENERIC_SUFFIX = [
    "工業大廈", "工廠大廈", "工業中心", "商業大廈", "商業中心", "工商中心",
    "貿易大廈", "工業大廈", "廣場", "商場", "大廈", "大樓", "中心", "花園",
    "別墅", "工廈", "地帶", "樓宇",
]
# District and area names that appear at the front of a Chinese address.
AREA_PREFIX = [
    "深水埗", "旺角", "尖沙咀", "銅鑼灣", "灣仔", "柴灣", "香港仔", "鰂魚涌",
    "太古", "筲箕灣", "小西灣", "新蒲崗", "九龍灣", "觀塘", "黃大仙",
    "鑽石山", "慈雲山", "牛頭角", "藍田", "秀茂坪", "紅磡", "土瓜灣",
    "大圍", "沙田", "石門", "火炭", "荃灣", "葵涌", "葵芳", "葵興",
    "元朗", "天水圍", "屯門", "將軍澳", "西貢", "大埔", "上水", "粉嶺",
    "東涌", "離島", "九龍城", "九龍", "香港", "新界", "港島", "山東",
    "沙咀", "調景嶺", "啟德", "青衣", "長沙灣", "荔枝角", "石門", "火炭",
    "西貢", "大埔", "沙田", "馬鞍山", "天水圍", "元朗", "屯門", "將軍澳",
]


def strip_area_prefix(run):
    """Drop a district or area name from the front of a Chinese run.

    "尖沙咀加連威老道嘉威大廈" is Tsim Sha Tsui + Granville Road +
    嘉威大廈, so the building is 嘉威大廈, not the whole run."""
    for pre in sorted(AREA_PREFIX, key=len, reverse=True):
        if run.startswith(pre):
            return run[len(pre):]
    return run


def distinctive(name):
    """The part of a building name that identifies it."""
    n = (name or "").strip()
    for suf in GENERIC_SUFFIX:
        if n.endswith(suf) and len(n) > len(suf) + 1:
            n = n[: -len(suf)]
            break
    return n.strip()
EN_BUILDING = re.compile(
    r"\b([A-Z][A-Za-z0-9'&\-]*(?:\s+[A-Z][A-Za-z0-9'&\-]*){0,3})\s+"
    r"(CENTRE|CENTER|BUILDING|BLDG|PLAZA|MALL|TOWER|HOUSE|ESTATE|ARCADE|"
    r"FACTORY|INDUSTRIAL|WORKS|GARDENS|COURT)\b"
)
EN_MALL = re.compile(
    r"\b([A-Z][A-Za-z0-9'&\-]*(?:\s+[A-Z][A-Za-z0-9'&\-]*){0,2})\s+"
    r"(PLAZA|MALL|TOWER|HOUSE|ESTATE)\b"
)


def parse_address(addr):
    """Pull (numbers, building names, street cores) out of an address.

    The address may be Chinese ("新蒲崗大有街1號勤達中心12樓1室") or
    English ("Room R3, 11/F Everest Industrial Building, 396 Kwun Tong
    Road"), so both are parsed."""
    nums, zh_cores, buildings = [], [], []

    # --- Chinese -----------------------------------------------------
    for m in re.finditer(r"([\u4e00-\u9fff]{2,10})\s*"
                         r"(\d+(?:\s*[-–]\s*\d+)?[A-Za-z]?)\s*號", addr):
        run, num = m.group(1), m.group(2)
        nums.append(num)
        run = strip_area_prefix(run)
        for w in BUILDING_WORDS:
            if w in run:
                idx = run.rfind(w)
                if idx > 0:
                    buildings.append(run[:idx + len(w)])
                break
        core = run
        for L in (3, 4, 5):
            if len(core) >= L:
                zh_cores.append(core[-L:])
    # a mall name in the address, e.g. 天悅廣場
    for w in ("廣場", "商場", "中心", "大廈", "大樓", "地帶", "城"):
        for m in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9]{2,8}" + w + ")", addr):
            b = strip_area_prefix(m.group(1))
            if len(b) >= 3:
                buildings.append(b)
    # A MALL address carries the mall name but no street number of its
    # own ("旺角信和中心21樓05室", "長沙灣天悅廣場1樓159B"). The unit
    # number is the floor, not the street, so it must not be read as a
    # street number. The mall name is the FIRST building-like word in the
    # address, before any floor marker.
    if not nums:
        m = re.search(r"([\u4e00-\u9fff]{2,12}?(?:廣場|商場|中心|大廈|大樓|地帶))"
                      r"[^0-9]{0,4}(?:\d|[A-Za-z])\s*(?:樓|层|F|/[0-9])", addr)
        if m:
            b = strip_area_prefix(m.group(1))
            if len(b) >= 3:
                buildings.append(b)
        else:
            # a bare mall name and a unit: "天悅廣埸 1樓133A店"
            m = re.search(r"([\u4e00-\u9fff]{2,12}?(?:廣場|廣埸|商場))", addr)
            if m:
                b = strip_area_prefix(m.group(1))
                if len(b) >= 3:
                    buildings.append(b)

    # --- English -----------------------------------------------------
    for m in re.finditer(r"(\d+(?:\s*[-–]\s*\d+)?[A-Za-z]?)\s*"
                         r"(?:[A-Za-z][A-Za-z0-9 ,.'&-]*?)\s*"
                         r"\b(ROAD|STREET|AVENUE|LANE|DRIVE|WAY|PLACE|"
                         r"SQUARE|TERRACE|CRESCENT|WALK|PATH|PARADE|BOULEVARD|"
                         r"QUAY|PIER|GARDENS|BOULEVARD)\b", addr, re.I):
        nums.append(m.group(1))
    for m in EN_BUILDING.finditer(addr):
        buildings.append(m.group(1) + " " + m.group(2))
    for m in EN_MALL.finditer(addr):
        buildings.append(m.group(1) + " " + m.group(2))

    seen, bn = set(), []
    for b in buildings:
        if b not in seen:
            seen.add(b)
            bn.append(b)
    return nums, zh_cores, bn


def number_set(nums):
    out = set()
    for n in nums:
        for part in re.split(r"[-–]", str(n)):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
    return out


def hit_numbers(hit):
    blob = " ".join(str(hit.get(k) or "") for k in
                    ("caddress", "eaddress", "address"))
    out = set()
    for m in re.finditer(r"(\d+)\s*[-–]?\s*([0-9]*[A-Za-z]?)\s*號", blob):
        a = m.group(1)
        out.add(int(a))
    for m in re.finditer(r"(?:^|[,\s])(\d+)\s*[-–]\s*(\d+)(?=[,\s]|$)", blob):
        out.add(int(m.group(1)))
        out.add(int(m.group(2)))
    for m in re.finditer(r"(?:^|[,\s])(\d+)(?=[,\s]|$)", blob):
        out.add(int(m.group(1)))
    return out


def hit_cores(hit):
    """The Chinese street cores of a hit."""
    blob = str(hit.get("caddress") or "")
    cores = []
    for m in re.finditer(r"([\u4e00-\u9fff]{2,10})\s*"
                         r"(\d+(?:\s*[-–]\s*\d+)?[A-Za-z]?)\s*號", blob):
        run = m.group(1)
        for L in (3, 4, 5):
            if len(run) >= L:
                cores.append(run[-L:])
    return cores


def name_hit(hit, want_names):
    """Does the hit's name contain one of the wanted building names?

    Compared on the DISTINCTIVE part, because the directory and the
    government index differ on the generic suffix: the directory writes
    寶富大廈 where the index writes 寶富大樓."""
    blob = " ".join(str(hit.get(k) or "") for k in
                    ("cname", "ename", "caddress", "eaddress"))
    bl = blob.lower()
    for w in want_names:
        wl = w.lower()
        if len(wl) >= 3 and wl in bl:
            return True
        if re.search(r"[\u4e00-\u9fff]", w):
            core = distinctive(w)
            if len(core) >= 2 and core in bl:
                return True
            # the hit may carry a qualifier: 嘉康中心 (前稱)
            for hn in (str(hit.get("cname") or ""), str(hit.get("ename") or "")):
                hd = distinctive(hn)
                if hd and len(hd) >= 2 and (hd in core or core in hd):
                    return True
    return False


def main():
    cache = load_cache()
    shops = json.load(open(RAW, encoding="utf-8"))
    out = []
    for i, s in enumerate(shops, 1):
        addr = s["addr"]
        nums, zh_cores, buildings = parse_address(addr)
        want_nums = number_set(nums)

        # --- queries ---------------------------------------------------
        tokens = []
        # the full address
        if addr:
            tokens.append(addr)
        # the street + number in Chinese, which the index keys on best
        for m in re.finditer(r"([\u4e00-\u9fff]{2,10})\s*"
                             r"(\d+(?:\s*[-–]\s*\d+)?[A-Za-z]?)\s*號", addr):
            tokens.append(f"{m.group(2)}號{m.group(1)}")
            break
        # the building name on its own
        for b in buildings[:3]:
            if len(b) >= 3:
                tokens.append(b)
        # the English building name
        for b in buildings:
            if re.match(r"^[A-Za-z]", b) and len(b) > 5:
                tokens.append(b)
        # A MALL has no street number of its own - the address gives the
        # mall and the unit ("旺角信和中心21樓05室"). The mall name alone
        # is the query that finds it.
        for m in re.finditer(r"([\u4e00-\u9fff]{2,8}(?:廣場|商場|中心|大廈|城))",
                             addr):
            tokens.append(m.group(1))
        for m in re.finditer(r"\b([A-Z][A-Za-z0-9']{2,}\s+"
                             r"(?:Plaza|Centre|Center|Mall|Tower|Arcade|"
                             r"Estate|Court|Building|Bldg))\b", addr):
            tokens.append(m.group(1))
        tokens = list(dict.fromkeys(t for t in tokens if t))
        # The directory sometimes writes a mall name with a variant
        # character (天悅廣埸 for 天悅廣場). Query the corrected form too.
        extra = []
        for t in tokens:
            fixed = t.replace("廣埸", "廣場").replace("商埸", "商場")
            if fixed != t:
                extra.append(fixed)
        tokens = list(dict.fromkeys(tokens + extra))

        cands = {}
        for t in tokens:
            for h in hits_of(query(t, cache)):
                key = h.get("id") or (h.get("cname"), h.get("ename"),
                                      h.get("lat"), h.get("lon"))
                cands[key] = h

        best = None
        best_score = -1e9
        for h in cands.values():
            # type=B is a building, type=S/PL is a shopping centre or a
            # complex, type=F is a facility inside one. All three are
            # legitimate places to find a shop. A mall address has no
            # street number of its own, so the mall hit is what
            # identifies it.
            if h.get("type") not in ("B", "S", "PL", "F"):
                continue
            hn = hit_numbers(h)
            named = name_hit(h, buildings)
            # A hit that states a number and it is not ours is a DIFFERENT
            # building of the same name - skip it entirely. But if the hit
            # IS the building we asked for by name (a mall, whose unit
            # number is in the address but not in the building's address),
            # the number is not evidence against it.
            if want_nums and hn and not named:
                if not (want_nums & hn):
                    continue
            sc = 0.0
            if named:
                sc += 4.0
            if want_nums & hn:
                sc += 3.0
            hc = hit_cores(h)
            if hc and zh_cores:
                if any(a in b or b in a for a in hc for b in zh_cores):
                    sc += 2.0
            if sc > best_score:
                best_score = sc
                best = (h, sc)

        if not best or best_score < 4.0:
            out.append({**s, "geocoded": False,
                        "reason": "no building match",
                        "tokens": tokens})
            print(f"  [{i:3}/{len(shops)}] {s['name'][:30]:32} NO MATCH")
            continue

        h, sc = best
        lat = float(h["lat"]) + HK80_TO_WGS[0]
        lon = float(h["lon"]) + HK80_TO_WGS[1]
        d = district_of(lat, lon)
        want_d = DC_EN.get(s.get("district_zh", "").strip(), "")
        same = bool(want_d and d and d.lower() == want_d.lower())
        out.append({
            **s,
            "geocoded": True,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "geocode_match": h.get("cname") or h.get("ename") or "",
            "geocode_address": h.get("caddress") or h.get("eaddress") or "",
            "geocode_type": h.get("type"),
            "geocode_district": d,
            "geocode_district_expected": want_d,
            "geocode_district_ok": same,
            "geocode_score": round(sc, 1),
        })
        mark = "ok " if same else "DIF"
        print(f"  [{i:3}/{len(shops)}] {s['name'][:30]:32} -> "
              f"{str(h.get('cname') or h.get('ename'))[:16]:18} "
              f"({lat:.5f},{lon:.5f}) {mark}[{d}]")

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for o in out if o.get("geocoded"))
    dok = sum(1 for o in out if o.get("geocoded") and
              o.get("geocode_district") and o.get("geocode_district_expected") and
              o["geocode_district"].lower() == o["geocode_district_expected"].lower())
    print(f"\nwrote {OUT}: {ok}/{len(out)} geocoded, {dok} district-consistent")


if __name__ == "__main__":
    main()
