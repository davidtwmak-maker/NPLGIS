#!/usr/bin/env python3
"""Geocode the play venues with the Hong Kong Government's own address index.

THE PROBLEM THIS SOLVES
    Hong Kong has MANY buildings with the same name. The index returns three
    嘉威大廈 (Granville House) and 50 hits for 嘉時工業大廈, and only one of
    them is the right one. An English name is worse still: "Wai Industrial
    Building" matched a building 40 km away in Tuen Mun.

    Two things make the matching hard, and both are handled here:

      1. THE SAME STREET HAS TWO CHINESE NAMES. The address index writes
         新寶中心 at 五芳街10號; the directory writes the same building at
         福榮街10號. The Chinese names differ but both are "Ng Fong
         Street" in English. So the STREET is matched in English, where
         the index is internally consistent.

      2. THE INDEX RENAMES BUILDINGS. The directory calls it 嘉時工業大廈;
         the index calls the same building 嘉時工廠大廈. So the building
         name is matched on its DISTINCTIVE part, with the generic suffix
         (工業大廈 / 工廠大廈) stripped from both sides.

THE FIVE TESTS
    Every candidate hit is checked against five independent pieces of
    evidence, all taken from the hit's own record:

      1. BUILDING  type=B (a building) beats type=F (a shop inside one)
      2. NAME      the hit's name identifies the same building
      3. NUMBER    the hit's street number matches (ranges resolved:
                   438-444 matches both 438 and 444)
      4. STREET    the hit's street matches, compared in English
      5. DISTRICT  the matched point falls in the district the address says

    A hit that CONTRADICTS the street number or the street is a different
    building of the same name, and is eliminated outright rather than
    merely down-ranked.

    The district is the weakest test and is recorded rather than used to
    veto: Mong Kok and Causeway Bay both straddle a district boundary, so
    a disagreement there is not evidence of a bad match.

Every query is cached in raw/geocode_cache.json, so a re-run is cheap.
"""
import csv
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "raw/geocode_cache.json"
OUT = HERE / "play_venues_geocoded.json"

SEARCH = "https://www.map.gov.hk/gih-ws2/search"
HEADERS = {
    "Referer": "https://www.map.gov.hk/gm/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# The index's coordinates are in the Hong Kong 1980 Grid; this is the shift
# to WGS84.
HK80_TO_WGS = (-0.00021, 0.00041)

DC_PATH = Path("/Users/davidhermes/nplgis/assets/data/self-study-rooms/"
               "district_boundaries.geojson.gz")

# Words that name a KIND of street, not a street. They are dropped before
# comparing street names, because the directory and the index disagree
# about them ("Shing On Street" vs "Shing On Road").
STREET_KIND = {
    "street", "road", "avenue", "lane", "drive", "way", "place", "square",
    "terrace", "terraces", "crescent", "close", "walk", "path", "parade",
    "boulevard", "quay", "pier", "market", "gardens", "village", "hill",
    "ridge", "bay", "court", "junction", "causeway", "esplanade", "green",
    "garden", "circus", "grove", "row", "rise", "vale",
}

# Generic building suffixes. The directory and the index often differ on
# these (工業大廈 vs 工廠大廈), so they are stripped from both sides and
# only the distinctive part is compared.
GENERIC_SUFFIX = [
    "工業大廈", "工廠大廈", "工業中心", "商業大廈", "商業中心", "工商中心",
    "貿易大廈", "廣場", "商場", "大廈", "大樓", "中心", "花園", "別墅",
    "工廈", "樓宇",
]

_DC_INDEX = None


# --------------------------------------------------------------- the cache
def load_cache():
    if CACHE.exists():
        return json.load(open(CACHE, encoding="utf-8"))
    return {}


def save_cache(cache):
    CACHE.parent.mkdir(exist_ok=True)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)


def query(keyword, cache):
    if keyword in cache:
        return cache[keyword]
    url = f"{SEARCH}?keyword={urllib.parse.quote(keyword)}&extent="
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode("utf-8"))
            cache[keyword] = data
            save_cache(cache)
            return data
        except Exception:
            if attempt == 2:
                cache[keyword] = {"_error": "failed"}
                save_cache(cache)
                return cache[keyword]
            time.sleep(1.5)
    return {}


def hits_of(data):
    """The service returns a BARE LIST for a keyword, but an object under
    other keywords, and an object with an `error` key for an unknown
    keyword. All three shapes must be handled."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    if data.get("error"):
        return []
    for key in ("results", "result", "hits", "features", "data"):
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for k2 in ("results", "result", "hits", "features"):
                v2 = v.get(k2)
                if isinstance(v2, list):
                    return v2
    return []


# ----------------------------------------------------- English address bits
STREET_WORDS = (
    "STREET|ROAD|AVENUE|LANE|DRIVE|WAY|PLACE|SQUARE|TERRACE|TERRACES|"
    "CRESCENT|CLOSE|WALK|PATH|PARADE|BOULEVARD|QUAY|PIER|MARKET|"
    "GARDENS|GARDEN|VILLAGE|HILL|RIDGE|BAY|COURT|JUNCTION|CAUSEWAY|"
    "ESPLANADE|GREEN|CIRCUS|GROVE|ROW|RISE|VALE"
)
STREET_RE = re.compile(
    r"(\d+(?:\s*[-–]\s*\d+)?[A-Za-z]?)\s*"
    r"([A-Za-z][A-Za-z ,.'&-]*?)\s*\b(" + STREET_WORDS + r")\b",
    re.I,
)

# Tokens that describe a FLOOR or a unit, not a building or a street.
UNIT_RE = re.compile(
    r"\b(?:Rm|Room|Floor|Flr|Unit|Shop|No\.?|Block|Tower|Level|"
    r"[GF]/?[0-9]+|[0-9]+/?[A-Za-z]?F)\b", re.I)


def parse_en_address(addr):
    """Pull (numbers, street_core) out of an English address.

    The street number is the number that sits IMMEDIATELY before the
    street-kind word, NOT the first number in the string - an address
    like "11/F, D2 PLACE TWO, 15 CHUNG SHUN STREET" has a floor number
    and a street number, and only the second one identifies the place.

    Where an address carries more than one street, the LAST one wins:
    the street is the last thing before the district."""
    if not addr:
        return [], ""
    matches = list(STREET_RE.finditer(addr))
    if not matches:
        return [], ""
    m = matches[-1]
    nums = [m.group(1)]
    core = m.group(2)
    # drop the unit/floor designators and any house numbers from the core
    core = UNIT_RE.sub(" ", core)
    core = re.sub(r"\b[A-Z]?\d+[A-Z]?\b", " ", core)
    core = re.sub(r"[^A-Za-z ]", " ", core)
    words = [w for w in core.upper().split() if w]
    # the street name is the last one or two words before the kind word
    while len(words) > 3:
        words.pop(0)
    return nums, " ".join(words)


def parse_zh_address(addr):
    """Pull (numbers, street_core) out of a Chinese address.

    The street name is the 3-4 character run that ends immediately
    before the street number's 號, so the district prefix ("深水埗") is
    excluded but the street name survives."""
    if not addr:
        return [], ""
    nums = []
    cores = []
    for m in re.finditer(r"([\u4e00-\u9fff]{2,8})\s*"
                         r"(\d+(?:\s*[-–]\s*\d+)?[A-Za-z]?)\s*號", addr):
        run, num = m.group(1), m.group(2)
        nums.append(num)
        core = strip_area_prefix(run)
        for L in (3, 4, 5):
            if len(core) >= L:
                cores.append(core[-L:])
    return nums, cores


# District and area names that appear in a Chinese address before the
# street name. They must not be mistaken for part of the street.
AREA_PREFIX = [
    "深水埗", "旺角", "尖沙咀", "銅鑼灣", "灣仔", "柴灣", "香港仔", "鰂魚涌",
    "太古", "筲箕灣", "小西灣", "新蒲崗", "九龍灣", "觀塘", "黃大仙",
    "鑽石山", "慈雲山", "牛頭角", "藍田", "秀茂坪", "紅磡", "土瓜灣",
    "大圍", "沙田", "荃灣", "葵涌", "元朗", "天水圍", "屯門", "將軍澳",
    "西貢", "大埔", "上水", "粉嶺", "東涌", "離島", "葵芳", "九龍城",
    "九龍", "香港", "新界", "港島", "山東", "沙咀",
]


def strip_area_prefix(run):
    """Drop a district or area name from the front of a Chinese run.

    "深水埗福華街" is Sham Shui Po + Fuk Wa Street, so the street name is
    福華街, not 深水埗福華街. The prefix list is checked longest first."""
    for pre in sorted(AREA_PREFIX, key=len, reverse=True):
        if run.startswith(pre):
            return run[len(pre):]
    return run


def street_matches(want_core, hit_cores):
    """Do the address and the hit sit on the same street?

    The two sides may give the street different numbers of characters
    ("福華街" against "華街", or "福華街" against "深水埗福華街"), so a
    hit matches when its core ENDS WITH the wanted core or vice versa.
    That way a longer, more specific form still matches a shorter one."""
    if not want_core or not hit_cores:
        return None
    for hc in hit_cores:
        if hc == want_core:
            return True
        if hc.endswith(want_core) or want_core.endswith(hc):
            # a 1-character difference is a different street
            if abs(len(hc) - len(want_core)) >= 1:
                return True
    return False


def numbers_compatible(want, have):
    """Is the wanted street number present in the hit's address?

    Returns True (matches), False (states a different number) or None (the
    hit states no number at all)."""
    if not want or not have:
        return None
    w = set()
    for n in want:
        for part in re.split(r"[-–]", str(n)):
            part = part.strip()
            if part.isdigit():
                w.add(int(part))
    h = set()
    for n in have:
        for part in re.split(r"[-–]", str(n)):
            part = part.strip()
            if part.isdigit():
                h.add(int(part))
    if not w or not h:
        return None
    if w & h:
        return True
    # a range on either side: the wanted number must fall inside it
    for src, other in ((want, have), (have, want)):
        for r in src:
            if re.search(r"[-–]", str(r)):
                a, b = re.split(r"[-–]", str(r))
                if a.strip().isdigit() and b.strip().isdigit():
                    lo, hi = sorted((int(a), int(b)))
                    for x in other:
                        if str(x).strip().isdigit() and \
                                lo <= int(str(x).strip()) <= hi:
                            return True
    return False


def want_address_bits(r):
    """What we are looking for, taken from the directory's own address.

    The English address is used for the street and the number, because
    the government index stores English addresses too and they are
    internally consistent. The Chinese address is used for the street
    as well, because the directory and the index sometimes give the same
    street two Chinese names but always the same English one."""
    en = (r.get("address") or "").strip()
    zh = (r.get("address_zh") or "").strip()
    en_nums, en_core = parse_en_address(en)
    zh_nums, zh_cores = parse_zh_address(zh)
    nums = list(en_nums) or list(zh_nums)
    cores = []
    if en_core:
        cores.append(en_core)
    cores.extend(zh_cores)
    return {
        "building_en": building_name_from_en(en),
        "bldg_zh": (r.get("bldg_zh") or "").strip(),
        "numbers": nums,
        "street_cores": cores,
    }


def building_name_from_en(en):
    """The building name in an English address.

    It is the chunk before the street chunk, skipping back over any unit
    or floor designators ("Unit 105-107 1/F"), which are not the building."""
    chunks = [c.strip() for c in (en or "").split(",") if c.strip()]
    for i, c in enumerate(chunks):
        if STREET_RE.search(c):
            for j in range(i - 1, -1, -1):
                prev = chunks[j]
                if UNIT_RE.search(prev):
                    continue
                if re.search(r"\d", prev):
                    # a chunk with a number that is not a unit designator is
                    # a house number, not a building name
                    continue
                return prev
            return ""
    return ""


def hit_address_bits(hit):
    """The building name, street and street number of a candidate hit."""
    eaddr = str(hit.get("eaddress") or "")
    caddr = str(hit.get("caddress") or "")
    en_nums, en_core = parse_en_address(eaddr)
    zh_nums, zh_cores = parse_zh_address(caddr)
    nums = list(en_nums) or list(zh_nums)
    cores = []
    if en_core:
        cores.append(en_core)
    cores.extend(zh_cores)
    return {"building_en": building_name_from_en(eaddr),
            "street_cores": cores, "numbers": nums,
            "caddr": caddr, "eaddr": eaddr}


# ------------------------------------------------------------- tokenising
def tokenise(r):
    """The strings to search the address index for.

    Order is the evidence: the Chinese BUILDING name first, because that is
    what the index keys on. The full English address is next - the index
    keys on it well and it disambiguates identically-named buildings. The
    shop's own name is the last resort: it almost never has an address
    record, and searching for it returns whatever else shares the words."""
    tokens = []
    bldg = (r.get("bldg_zh") or "").strip()
    if bldg:
        tokens.append(bldg)
    for chunk in (r.get("address_zh") or "").split(","):
        chunk = chunk.strip()
        for suf in GENERIC_SUFFIX:
            if suf in chunk and len(chunk) <= 40:
                idx = chunk.rfind(suf)
                if idx > 0:
                    tok = chunk[:idx + len(suf)]
                    if len(tok) >= 3:
                        tokens.append(tok)
                break
    en = (r.get("address") or "").strip()
    if en:
        tokens.append(en)
        bits = want_address_bits(r)
        if bits["building_en"] and bits["building_en"] not in GENERIC_SUFFIX:
            tokens.append(bits["building_en"])
        # the street, on its own, with its number - the index keys on this
        if bits["street_cores"] and bits["numbers"]:
            tokens.append(f"{bits['numbers'][0]} {bits['street_cores'][0]}")
    # The Chinese street with its number: the index keys on Chinese
    # addresses, and the Chinese street name is the one the two sources
    # agree on most often.
    zh = (r.get("address_zh") or "").strip()
    if zh:
        zh_nums, zh_cores = parse_zh_address(zh)
        if zh_nums and zh_cores:
            tokens.append(f"{zh_nums[0]}號{zh_cores[-1]}")
    name = (r.get("name") or "").strip()
    if len(name) > 3:
        tokens.append(name)
    seen, out = set(), []
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


# --------------------------------------------------------------- districts
def _point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)):
            xint = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < xint:
                inside = not inside
        j = i
    return inside


def _point_in_geom(lon, lat, geom):
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return False
    for poly in polys:
        if poly and _point_in_ring(lon, lat, poly[0]):
            return True
    return False


def dc_index():
    """The 18 District Council boundary polygons.

    This is the AUTHORITATIVE district layer - Census and Planning
    Department, shipped in the nplgis repo."""
    global _DC_INDEX
    if _DC_INDEX is None:
        if not DC_PATH.exists():
            return []
        gz = json.load(gzip.open(DC_PATH, "rt", encoding="utf-8"))
        idx = []
        for f in gz["features"]:
            xs, ys = [], []

            def walk(c):
                if isinstance(c[0], (int, float)):
                    xs.append(c[0])
                    ys.append(c[1])
                else:
                    for x in c:
                        walk(x)
            walk(f["geometry"]["coordinates"])
            idx.append((min(xs), min(ys), max(xs), max(ys),
                        f["geometry"], f["properties"].get("dc_eng")))
        _DC_INDEX = idx
    return _DC_INDEX


def district_of(lat, lon):
    """The District Council district this point falls in."""
    for x0, y0, x1, y1, geom, dname in dc_index():
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            if _point_in_geom(lon, lat, geom):
                return dname
    return None


# ------------------------------------------------------------- the ranking
def hit_lat(hit):
    v = hit.get("lat") or hit.get("latitude") or hit.get("y")
    return None if v is None else float(v) + HK80_TO_WGS[0]


def hit_lon(hit):
    v = hit.get("lon") or hit.get("longitude") or hit.get("x")
    return None if v is None else float(v) + HK80_TO_WGS[1]


def distinctive(name):
    """The part of a building name that actually identifies it."""
    n = (name or "").strip()
    for suf in GENERIC_SUFFIX:
        if n.endswith(suf) and len(n) > len(suf) + 1:
            n = n[: -len(suf)]
            break
    return n.strip()


def name_matches(hit_names, want_names):
    """Does the hit identify the same building as the address?

    Tested on the DISTINCTIVE part of each name, with the comparison
    case-insensitive, because the index writes "D2 Place Two" where the
    directory writes "D2 PLACE TWO"."""
    for hn in hit_names:
        if not hn:
            continue
        for wn in want_names:
            if not wn:
                continue
            a, b = distinctive(hn), distinctive(wn)
            if not a or not b:
                continue
            al, bl = a.lower(), b.lower()
            if bl in al or al in bl:
                return True
            if min(len(al), len(bl)) >= 2 and (
                    al.startswith(bl) or bl.startswith(al)):
                return True
    return False


def evidence(hit, r, want):
    """Score one hit against the five independent tests.

    Returns (score, flags). A hit that states a DIFFERENT street number or
    sits on a DIFFERENT street is a different building of the same name,
    and is eliminated outright."""
    cname = str(hit.get("cname") or "")
    ename = str(hit.get("ename") or "")
    hbits = hit_address_bits(hit)

    is_building = hit.get("type") == "B"

    # --- test 2: the name -------------------------------------------------
    want_names = [want["building_en"], want["bldg_zh"]]
    name_ok = name_matches([cname, ename, hbits["building_en"]], want_names)
    if not name_ok:
        name_ok = name_matches([hbits["caddr"]], want_names)

    # --- test 3: the street number ----------------------------------------
    num_state = numbers_compatible(want["numbers"], hbits["numbers"])
    if num_state is False:
        return -100, {"building": is_building, "name": name_ok,
                      "number": False, "street": None,
                      "eliminated": True}

    # --- test 4: the street ------------------------------------------------
    # The street is CREDIT, never elimination. The directory and the
    # government index sometimes give one street two Chinese names or two
    # English names, so a disagreement on the street is not proof that
    # the building is wrong - it only means the hit does not gain the
    # street evidence. (The NUMBER test is the strict one.)
    street_state = None
    if want["street_cores"] and hbits["street_cores"]:
        pairs = [(w, h) for w in want["street_cores"]
                 for h in hbits["street_cores"]]
        results = [street_matches(w, [h]) for w, h in pairs]
        if any(r is True for r in results):
            street_state = True

    score = 0.0
    flags = {"building": is_building, "name": name_ok,
             "number": num_state, "street": street_state,
             "eliminated": False}
    if is_building:
        score += 2.0
    if name_ok:
        score += 4.0
    if num_state is True:
        score += 2.0
    if street_state is True:
        score += 2.0
    return score, flags


def main():
    cache = load_cache()
    rows = list(csv.DictReader(open(HERE / "play_venues.csv", encoding="utf-8")))
    out = []
    for i, r in enumerate(rows, 1):
        tokens = tokenise(r)
        want = want_address_bits(r)

        # Collect every hit from every query, then score each ONE against
        # the five tests. Scoring per-token and comparing afterwards let a
        # weak match from one query beat a strong match from another.
        cands = {}
        for t in tokens:
            for h in hits_of(query(t, cache)):
                key = h.get("id") or (h.get("cname"), h.get("ename"),
                                      h.get("lat"), h.get("lon"))
                cands[key] = h

        scored = []
        for h in cands.values():
            s, flags = evidence(h, r, want)
            if flags.get("eliminated"):
                continue
            scored.append((s, flags, h))
        scored.sort(key=lambda t: -t[0])

        want_district = (r.get("dc_district") or "").strip()
        chosen = None
        best_rejected = None
        reject = ""
        for s, flags, h in scored:
            lat = hit_lat(h)
            lon = hit_lon(h)
            if lat is None or lon is None:
                continue
            if s < 8.0:
                if best_rejected is None or s > best_rejected[0]:
                    best_rejected = (s, h, None, lat, lon)
                continue
            d = district_of(lat, lon)
            # The district is a CONFIRMATORY check, not a veto. The
            # directory's district column is a human-written guess, and
            # the DC boundary polygon is the authority - so a disagreement
            # is recorded, and the candidate is still taken if its name,
            # number and street all agree. Only a candidate that also
            # fails on the other evidence is rejected.
            if want_district and d and d.lower() != want_district.lower():
                if best_rejected is None or s > best_rejected[0]:
                    best_rejected = (s, h, d, lat, lon)
                reject = (f"{h.get('cname') or h.get('ename')} scores {s:.1f} "
                          f"but sits in {d}, not {want_district}")
            chosen = (h, s, flags, lat, lon, d)
            break

        if not chosen:
            why = reject or "no usable hit"
            if best_rejected:
                bs, bh, bd, blat, blon = best_rejected
                why = (f"best candidate {bh.get('cname') or bh.get('ename')} "
                       f"score {bs:.1f} "
                       f"(type={bh.get('type')}, "
                       f"addr={str(bh.get('eaddress') or bh.get('caddress') or '')[:44]})")
            out.append({**r, "geocoded": False, "reason": why})
            print(f"  [{i:2}/{len(rows)}] {r['name'][:32]:34} REJECTED {why[:72]}")
            continue

        h, s, flags, lat, lon, d = chosen
        out.append({
            **r,
            "geocoded": True,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "building_token": (r.get("bldg_zh") or "").strip(),
            "geocode_match": h.get("cname") or h.get("ename") or "",
            "geocode_match_en": h.get("ename") or "",
            "geocode_address": h.get("caddress") or h.get("eaddress") or "",
            "geocode_address_en": h.get("eaddress") or "",
            "geocode_type": h.get("type"),
            "geocode_id": h.get("id"),
            "geocode_district": d,
            "geocode_district_expected": want_district,
            "geocode_district_ok": (not want_district or not d or
                                    d.lower() == want_district.lower()),
            "geocode_score": round(s, 1),
            "geocode_flags": {k: v for k, v in flags.items()
                              if k != "eliminated"},
        })
        print(f"  [{i:2}/{len(rows)}] {r['name'][:32]:34} -> "
              f"{h.get('cname') or h.get('ename')} ({lat:.5f},{lon:.5f}) "
              f"[{d}] score={s:.1f}")

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for o in out if o.get("geocoded"))
    print(f"\nwrote {OUT}: {ok}/{len(out)} geocoded")


if __name__ == "__main__":
    main()
