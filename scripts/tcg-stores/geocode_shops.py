#!/usr/bin/env python3
"""Geocode each card shop's street address with the Hong Kong Government's own
location search service (LandsD GeoInfo Map, gih-ws2/search).

Why this and not Nominatim / OSM Overpass:
  * OSM does not tag these shops at all. A full-territory sweep of the OSM API
    (205 tiles over the whole bbox) found ZERO shop=cards / game / board_game
    nodes with a card-game name - Hong Kong's card shops are simply not in
    OSM's POI layer.
  * The HK geocoder resolves a Chinese street address to the BUILDING
    ("偉昌工業中心" / "天悅廣場 Block B"), which is the level a shop inside a
    shopping arcade sits at. That disambiguates the many shops that share one
    mall pin.

SAFEGUARDS, because an unconstrained geocoder is worse than none:
  1. RADIUS - a candidate hit must fall within MAX_M of the shop's own
     directory pin. Unconstrained, the service answered a different question
     and moved shops up to 25 km ("利寶商場" -> a Tai Po mall, "ARENA" ->
     "Regency Arena").
  2. BUILDING - the hit's OWN name must carry the building named in the
     shop's address ("偉昌工業中心", "寶富大樓", "百美工廠大廈"), and the hit
     must be a building record (type B) or the shop's own name. Without this,
     a Tuen Mun shop matched "Tuen Mun Industrial Centre" - the right town,
     the wrong building - and a Wan Chai shop matched a defibrillator.
  3. TOKEN PRIORITY - a token is scored by how SPECIFICALLY it names a
     building, not by how long it is. A long token that is really a district
     or a street ("屯門", "青山道", "Hing Fong Road") is a worse building
     match than a short specific one ("偉昌工業中心"). The token's own
     length is only a weak tie-break, and a token that matches a hit's
     Chinese name EXACTLY beats one that merely appears inside a longer name.

Every shop records WHICH rule produced its point and the displacement from
the directory pin, so a reader can see what was refined and what was not.
"""
import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from atomic_write import write_json_atomic

HERE = Path(__file__).resolve().parent
CACHE = HERE / "raw" / "geocode_cache.json"
OUT = HERE / "shops_geocoded.json"

ENDPOINT = "https://www.map.gov.hk/gih-ws2/search?keyword={kw}&extent="
HEADERS = {"Referer": "https://www.map.gov.hk/gm/",
           "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

HK = (22.15, 22.58, 113.82, 114.44)
MAX_M = 700.0

# The bounding box above is NOT a land test. Hong Kong is not a
# rectangle, and a point at 22.43 N, 114.09 E sits inside the box while
# being in the Pearl River estuary, outside Hong Kong altogether. So a
# directory pin is only trusted when it falls inside a District Council
# district polygon - the authoritative boundary.
DC_PATH = Path("/Users/davidhermes/nplgis/assets/data/self-study-rooms/"
                "district_boundaries.geojson.gz")
_DC = None
_DC_BBOX = None


def dc_districts():
    """The 18 District Council districts, as a list of (name, rings)."""
    global _DC, _DC_BBOX
    if _DC is None:
        import gzip
        with gzip.open(DC_PATH, "rt", encoding="utf-8") as f:
            gj = json.load(f)
        out = []
        boxes = []
        for feat in gj["features"]:
            g = feat["geometry"]
            rings = ([g["coordinates"][0]] if g["type"] == "Polygon"
                     else [p[0] for p in g["coordinates"]])
            out.append((feat["properties"].get("dc_eng"), rings))
            # A bounding box per district. Testing a point against all
            # 18 polygons took 9 ms; the box rejects almost every
            # district in a comparison, which makes the lookup fast
            # enough to run inside the geocode loop.
            xs = [p[0] for r in rings for p in r]
            ys = [p[1] for r in rings for p in r]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        _DC = out
        _DC_BBOX = boxes
    return _DC


def _in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def address_area_dc(addr):
    """The District Council district the address names, if it names one.

    A Chinese address carries the area it is in. If the address says
    尖沙咀 and the directory's pin lands in Yuen Long, the pin is wrong
    - and a pin is all that survives when no building can be matched.
    """
    for area, dc in AREA_TO_DC.items():
        if area in (addr or ""):
            return dc
    return None


def in_hong_kong(lat, lon):
    """Is this point inside a District Council district?"""
    return dc_of(lat, lon) is not None


def dc_of(lat, lon):
    """The District Council district this point falls in, or None."""
    if lat is None or lon is None:
        return None
    districts = dc_districts()
    for (name, rings), (x0, y0, x1, y1) in zip(districts, _DC_BBOX):
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        for r in rings:
            if _in_ring(lon, lat, r):
                return name
    return None


# The Chinese area names a directory address can carry, and the District
# Council district each one falls in. A pin whose district contradicts
# the address is a wrong pin - the BAW VAULT pin for HobbyX Plus (K11
# Art Mall) sat in Yuen Long while the address said 尖沙咀.
#
# DERIVED, not written by hand: derive_area_dc.py asks the government
# geocoder where each area name is, takes the district its hits agree
# on, and cross-checks that against the shop pins. An area where the
# geocoder's hits do not agree, or where the pins disagree with the
# geocoder, is left out - an unmapped area simply never triggers the
# check, while a wrongly mapped area would reject a correct pin.
AREA_TO_DC = {
    "上水": "North",
    "上環": "Central and Western",
    "中環": "Central and Western",
    "九龍灣": "Kwun Tong",
    "元朗": "Yuen Long",
    "北角": "Eastern",
    "土瓜灣": "Kowloon City",
    "堅尼地城": "Central and Western",
    "大圍": "Sha Tin",
    "大埔": "Tai Po",
    "天水圍": "Yuen Long",
    "太古": "Eastern",
    "太古城": "Eastern",
    "將軍澳": "Sai Kung",
    "小西灣": "Eastern",
    "尖沙咀": "Yau Tsim Mong",
    "屯門": "Tuen Mun",
    "山頂": "Central and Western",
    "慈雲山": "Wong Tai Sin",
    "新蒲崗": "Wong Tai Sin",
    "日出康城": "Sai Kung",
    "旺角": "Yau Tsim Mong",
    "樂富": "Wong Tai Sin",
    "沙田": "Sha Tin",
    "沙頭角": "North",
    "油麻地": "Yau Tsim Mong",
    "深水埗": "Sham Shui Po",
    "灣仔": "Wan Chai",
    "火炭": "Sha Tin",
    "石門": "Sha Tin",
    "筲箕灣": "Eastern",
    "粉嶺": "North",
    "紅磡": "Kowloon City",
    "荃灣": "Tsuen Wan",
    "荔枝角": "Sham Shui Po",
    "葵涌": "Kwai Tsing",
    "葵芳": "Kwai Tsing",
    "薄扶林": "Southern",
    "西灣河": "Eastern",
    "西環": "Central and Western",
    "西貢": "Sai Kung",
    "觀塘": "Kwun Tong",
    "調景嶺": "Sai Kung",
    "跑馬地": "Wan Chai",
    "銅鑼灣": "Wan Chai",
    "錦田": "Yuen Long",
    "鑽石山": "Wong Tai Sin",
    "長沙灣": "Sham Shui Po",
    "青衣": "Kwai Tsing",
    "香港仔": "Southern",
    "馬鞍山": "Sha Tin",
    "鰂魚涌": "Eastern",
    "鴨脷洲": "Southern",
    "黃大仙": "Wong Tai Sin",
}

# Hong Kong building-name endings.
BUILDING_SUFFIX = re.compile(
    r"(大廈|大厦|大樓|大楼|中心|廣場|广场|商場|商场|工廠大廈|工廠|工廈|"
    r"商務中心|購物中心|購物商場|大塲|寫字樓|屋苑|邨|村|別墅|酒店|戲院|"
    r"會堂|學校|書院|商行|薈館|荟|新城|新邨|花園|園|臺|台|薈|薈城|"
    r"廣場|廣廈|大廈|苑|閣|軒|府|邸|臺|堡|鎮|匯|坊|里|舍)"
)
# The characters that follow a building name in an address and are part
# of the ADDRESS, not of the name: 第1期 (phase 1), 地下 (ground
# floor), 1樓 (first floor). "恒豐工業大廈第1期" is the building
# 恒豐工業大廈; the tokeniser that produced "工業大廈第" matched
# every industrial building in Hong Kong.
ADDRESS_TAIL = re.compile(r"(第[一二三四五六七八九十\d]*[期座幢座期]|地下|地舖|地下舖|"
                          r"[地下]*[樓層][A-Za-z0-9]*|[0-9]*樓|[A-Za-z]室|號鋪|號舖)$")
# "恒豐工業大廈第1期" - the phase marker sits BETWEEN the building name
# and the end of the run, so the run has to be cut at 第 as well as at
# the end.
PHASE_MARK = re.compile(r"第[一二三四五六七八九十\d]*[期座幢期]")
STREET_SUFFIX = re.compile(r"(道|街|路|巷|徑|橋|埗|圍|段)$")

# District / area names that must never be used as a building token.
DISTRICT_TOKENS = {
    "屯門", "元朗", "荃灣", "葵青", "深水埗", "黃大仙", "觀塘", "九龍城",
    "油尖旺", "沙田", "西貢", "北區", "大埔", "葵涌", "青衣", "旺角",
    "灣仔", "香港", "九龍", "新界", "港島", "尖沙咀", "銅鑼灣", "長沙灣",
    "荔枝角", "土瓜灣", "紅磡", "佐敦", "樂富", "九龍灣", "慈雲山",
    "鑽石山", "牛頭角", "鯉魚門", "將軍澳", "調景嶺", "日出康城", "太古城",
    "太古", "筲箕灣", "西灣河", "北角", "鰂魚涌", "跑馬地", "小西灣",
    "柴灣", "淺水灣", "石澳", "薄扶林", "西環", "上環", "中環", "半山",
    "堅尼地城", "鴨脷洲", "仔沙頭", "大圍", "火炭", "何文田", "石硤尾",
    "美孚", "九龍塘", "竹園", "彩虹", "牛池灣", "藍田", "平田", "啟德",
    "油麻地", "太子", "天水圍", "屯門藍地", "大良", "錦田", "八鄉", "石崗",
    "上水", "粉嶺", "沙頭角", "龍躍頭", "古洞", "打鼓嶺", "馬鞍山", "葵芳",
    "沙咀", "愉景新城", "象山", "青衣城", "荃西", "石圍角", "愉景", "德華",
    "荃興", "川龍", "三棟屋", "侯王古道", "海濱", "香港仔", "赤柱", "大坑",
    "九肚山", "青山公路", "青山道", "彌敦道", "通菜街", "富明街", "開源道",
}

# Area names - districts and neighbourhoods - that the geocoder also
# has records for. They are not buildings, and a token that names one
# must not outscore a token that names the building.
AREA_TOKENS = {
    # English
    "mong kok", "kowloon bay", "kwun tong", "tsim sha tsui",
    "yau ma tei", "prince edward", "sham shui po", "cheung sha wan",
    "lai chi kok", "shek mun", "san po kong", "diamond hill",
    "hung hom", "to kwa wan", "wong tai sin", "chuk yuen",
    "sha tin", "tai wai", "fo tan", "ma on shan", "tsuen wan",
    "kwai chung", "kwai fong", "tsing yi", "chai wan",
    "causeway bay", "wan chai", "north point", "tai koo",
    "quarry bay", "shau kei wan", "sai wan ho", "siu sai wan",
    "happy valley", "aberdeen", "ap lei chau", "pok fu lam",
    "tuen mun", "yuen long", "tin shui wai", "kam tin",
    "sheung shui", "fanling", "sha tau kok", "junk bay",
    "tiu keng leng", "sai kung", "tai po", "the peak",
    "sai wan", "sheung wan", "central", "kennedy town",
    "tai hang", "tsz wan", "shek shui", "mei foo",
    "ho man tin", "kowloon city", "sham shui po", "tung chung",
    "ma on shan", "tiu keng leng",
    # Chinese
    "旺角", "尖沙咀", "油麻地", "太子", "深水埗", "長沙灣", "荔枝角",
    "石門", "新蒲崗", "九龍灣", "觀塘", "鑽石山", "紅磡", "土瓜灣",
    "黃大仙", "竹園", "沙田", "大圍", "火炭", "馬鞍山", "荃灣",
    "葵涌", "葵芳", "青衣", "柴灣", "銅鑼灣", "灣仔", "北角", "太古",
    "鰂魚涌", "筲箕灣", "西灣河", "小西灣", "跑馬地", "香港仔",
    "鴨脷洲", "薄扶林", "屯門", "元朗", "天水圍", "錦田", "上水",
    "粉嶺", "沙頭角", "將軍澳", "調景嶺", "西貢", "大埔", "東涌",
    "香港", "九龍", "新界", "港島",
}

STOP = set("""香港 hk hong kong kong 號 室 鋪 舖 店 樓 层 層 地舖 地下
一二三四五六七八九十樓層字樓號室舖鋪店舖位 g f b a m 樓上 樓下
市 區 城 鎮 購物 廣場 road street road rd st ave avenue
shop shops unit floor block tower wing phase room rm no nr company limited ltd
mall plaza tower centre center building arcade
""".split())


def load_cache():
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(c):
    # Atomic write. A plain write_text() leaves a truncated, unparseable
    # cache if the run is killed mid-write, and the cache is what makes a
    # re-run cheap - losing it means re-querying every address.
    write_json_atomic(CACHE, c, indent=1)


def metres(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * 111320.0
    dx = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def geocode(keyword, cache):
    """Query the HK geocoder. Returns (hits, error_string).

    A short timeout: this service intermittently accepts a request and then
    never sends a body, which hangs the run. A stalled read must fail fast.
    """
    if keyword in cache:
        return cache[keyword], None
    url = ENDPOINT.format(kw=urllib.parse.quote(keyword))
    last = None
    for attempt in range(3):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
            hits = json.loads(body.decode("utf-8"))
            if not isinstance(hits, list):
                hits = []
            cache[keyword] = hits
            save_cache(cache)
            return hits, None
        except Exception as ex:
            last = ex
            time.sleep(1.5 * (attempt + 1))
    cache[keyword] = []
    save_cache(cache)
    return [], f"error: {last}"


def building_tokens(address, shop_name=None):
    """The candidate BUILDING names inside an address.

    Only CJK runs that end in a Hong Kong building word qualify, and a token
    that is a district or street name is rejected.

    The shop's OWN NAME is not a building. "League Castle" is a shop;
    "Castle" is not the building it stands in, and letting it act as a
    token made "League Castle (D-Park)" match CASTLE PEAK ROAD - a
    road, 645 m from the shop - while the real building, 愉景新城,
    scored nothing because no building word matched it.
    """
    toks = set()
    a = address or ""
    for m in re.finditer(r"[一-鿿]{2,}", a):
        run = m.group(0)
        # Strip the address tail from the run before cutting it into
        # suffixes, so that "恒豐工業大廈第1期" yields 恒豐工業大廈 and
        # not 工業大廈第 - a token that matches every industrial
        # building in Hong Kong.
        run = ADDRESS_TAIL.sub("", run)
        # A phase marker splits the run: the building name is what
        # comes BEFORE it. "恒豐工業大廈第1期" -> 恒豐工業大廈. The
        # digits after 第 end the CJK run, so the marker often sits at
        # the very end of the run - "2G號恒豐工業大廈第".
        pm = PHASE_MARK.search(run)
        if pm:
            run = run[:pm.start()]
        elif run.endswith("第"):
            run = run[:-1]
        if len(run) < 3:
            continue
        for i in range(len(run)):
            suf = run[i:]
            if len(suf) < 3:
                continue
            if not BUILDING_SUFFIX.search(suf):
                continue
            if STREET_SUFFIX.match(suf):
                continue
            if suf in DISTRICT_TOKENS:
                continue
            toks.add(suf)
        if (len(run) >= 3 and not STREET_SUFFIX.match(run)
                and BUILDING_SUFFIX.search(run) and run not in DISTRICT_TOKENS):
            toks.add(run)
    for m in re.finditer(r"\b([A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]{2,}){0,3})\b", a):
        phrase = m.group(1)
        if phrase.lower() in STOP:
            continue
        toks.add(phrase)
        # The LAST word of the phrase is a building name only when it is
        # a building word in its own right. "K11 Art Mall" must not give
        # the token "Art" - it matched 富雅花園 (Full Art Garden Block
        # 11), a housing estate on Lantau, and put the shop 40 km from
        # K11 Art Mall. A generic word is not a building name.
        words = phrase.split()
        last = words[-1]
        if len(words) > 1 and last.lower() not in STOP and len(last) >= 4:
            toks.add(last)
        # A STANDALONE one-word phrase is a building name only if it is
        # a building word. "Art" on its own, split off by the word
        # boundary, is a description, not a building.
        if len(words) == 1 and phrase.lower() not in STOP and len(phrase) < 5:
            toks.discard(phrase)
    # A name that starts with digits - "K11 Art Mall" - is not caught by
    # the rule above, because the phrase begins with a number and the
    # word boundary splits "K11" from "Art", leaving "Art" as a
    # standalone phrase. The boundary here is a digit, not a word edge.
    for m in re.finditer(r"(?<![A-Za-z0-9])([A-Z]?\d+[A-Za-z]*(?:\s+[A-Z][A-Za-z]{2,}){0,3})", a):
        phrase = m.group(1)
        if phrase.lower() in STOP or len(phrase) < 4:
            continue
        toks.add(phrase)

    # Drop anything that is only the SHOP's own name, not the building.
    # "League Castle" is the shop; "Castle" is not the building it
    # stands in. Two guards keep this from eating the building:
    #   - only WHOLE words are dropped, so "HobbyX Plus (K11 Art Mall)"
    #     keeps the token "K11 Art Mall";
    #   - a token LONGER than the shop's own name is never dropped,
    #     because a longer phrase is a building the shop sits in, not
    #     the shop's name repeated.
    if shop_name:
        words = set(w.lower() for w in re.findall(r"[A-Za-z0-9]+", shop_name))
        # A token that repeats the shop's name is not a building. But a
        # shop may be NAMED after its building - "HobbyX Plus (K11 Art
        # Mall)" - and then the building's own name is the best token
        # there is. The test is therefore not "does the name appear in
        # the shop's name" but "does the token come from the ADDRESS".
        # A token the shop's own name introduced, and which the address
        # does not repeat, is the shop's name and not a building.
        kept = set()
        for t in toks:
            tl = t.lower()
            if tl in words:
                continue                      # the shop's own name
            tw = re.findall(r"[A-Za-z0-9]+", tl)
            if tw and set(tw) <= words and tl not in a.lower():
                continue                      # only in the name, not the address
            kept.add(t)
        toks = kept
    return {t for t in toks if t and t.lower() not in STOP and len(t) >= 2}


def token_quality(token, hit_cname, hit_ename):
    """How specifically does this token name the hit's building?

    A token that does NOT appear in the hit's own name scores NEGATIVE, and
    is therefore never a match. This matters: the token set contains every
    suffix of every CJK run in the address, so "天悅廣場", "灣天悅廣場" and
    "號天悅廣場" are all candidates. Only the one the geocoder's record
    actually carries may match, and an EXACT match against the record's own
    name is the strongest signal.
    """
    cn = (hit_cname or "").lower()
    en = (hit_ename or "").lower()
    tl = token.lower()
    if not cn and not en:
        return -1000.0
    if tl in cn or tl in en:
        q = 50.0
        # A record may carry a qualifier: "天悅廣場 (別稱)" is the
        # building 天悅廣場 under another name, and "Block A (Other
        # Name)" is one of its blocks. The qualifier is not part of
        # the building's name, so it is stripped before the names are
        # compared - otherwise a plain exact match looks like a
        # partial one.
        cn_bare = re.sub(r"\s*[(（][^)）]*[)）]\s*$", "", cn).strip()
        en_bare = re.sub(r"\s*[(（][^)）]*[)）]\s*$", "", en).strip()
        if cn_bare == tl:
            q = 100.0
        elif en_bare == tl:
            q = 95.0
        elif cn == tl:
            q = 100.0
        elif en == tl:
            q = 95.0
        # A generic building word is a weak identifier; a distinctive name
        # is a strong one.
        generic = {"工廠大廈", "大廈", "工業中心", "商場", "中心", "廣場", "商務中心",
                   "工業大廈", "購物中心", "寫字樓"}
        if tl in generic:
            q -= 45
        elif len(tl) >= 4 and tl.endswith(("大廈", "大樓", "中心", "廣場", "商場", "大塲")):
            q += 25
        # An AREA is not a building. The geocoder has a record for every
        # district and neighbourhood ("旺角", type PL), and an address
        # that ends "...Hong Kong, Mong Kok" gives that area as a
        # candidate token. Matching it exactly scored 95 and beat the
        # real building, 華懋王子大廈, which scored 75 - so "Have Card"
        # was placed at the Mong Kok district centroid, 679 m from the
        # shop. An area token cannot outscore a building token.
        if tl in AREA_TOKENS:
            q -= 60
        return q
    return -1000.0


def hit_blob(h):
    return " ".join(str(h.get(k) or "") for k in
                     ("ename", "cname", "eaddress", "caddress", "edescription",
                      "cdescription"))


def choose(hits, name, name_zh, tokens, pin_lat, pin_lon, addr=None):
    """Pick the best hit under the safeguards. Returns a dict or None."""
    if not hits:
        return None
    n = (name or "").strip().lower()
    nz = (name_zh or "").strip().lower()

    # A pin in a district that contradicts the address cannot anchor a
    # radius. The BAW VAULT pin for HobbyX Plus (K11 Art Mall) sat in
    # Yuen Long while the address said 尖沙咀; anchoring on it threw
    # away the correct geocode, which is 40 km away in Tsim Sha Tsui.
    # The address is the better evidence of where the shop is.
    addr_dc = address_area_dc(addr)
    pin_dc = dc_of(pin_lat, pin_lon)
    pin_contradicts = (addr_dc is not None and pin_dc is not None
                       and addr_dc != pin_dc)

    cands = []
    for h in hits:
        try:
            lat, lon = float(h["lat"]), float(h["lon"])
        except Exception:
            continue
        if not (HK[0] <= lat <= HK[1] and HK[2] <= lon <= HK[3]):
            continue
        # The bounding box is not enough. A hit outside a District
        # Council district is not in Hong Kong, so it cannot be the
        # shop's building however well its name matches.
        if not in_hong_kong(lat, lon):
            continue
        # The token score decides how much the hit's own name has to
        # say about the building, so it is computed BEFORE the distance
        # gate - the gate uses it to decide whether a far hit may still
        # be the right building.
        blob = hit_blob(h)
        blob_l = blob.lower()
        htype = str(h.get("type") or "").upper()
        cn = str(h.get("cname") or "")
        en = str(h.get("ename") or "")

        token_hit, token_q = None, -1e9
        for t in tokens:
            q = token_quality(t, cn, en)
            if q > token_q and q > 0:
                token_hit, token_q = t, q

        if pin_lat is not None and not pin_contradicts:
            d = metres(pin_lat, pin_lon, lat, lon)
            # A building may be further from the directory pin than the
            # radius allows - "Have Card" is at 旺角道97-99號華懋王子大廈
            # and the pin sits 735 m away. The pin is a street-level
            # approximation; the address names the building. So a hit
            # whose district matches the address's district is allowed
            # past the radius - but only just past it. A hit 1.4 km away
            # in the same district is a DIFFERENT building: "Rapp
            # Collect" is at 恒豐工業大廈 and was matched to 德威大廈
            # (Tak Wai Mansion), and "Lok Fung Ka Se" is at 和宜商場 and
            # was matched to 恆景商場.
            if d > MAX_M:
                hit_dc = dc_of(lat, lon)
                if addr_dc is None or hit_dc is None or hit_dc != addr_dc:
                    continue                    # safeguard 1: radius
                if d > MAX_M * 1.5:
                    # Past 1.5x the radius, the hit has to earn it: the
                    # token must match the hit's own name EXACTLY, and
                    # the hit must be a building. "Cardlos" is listed
                    # at 173號, 1樓, of 天悅廣場 - the address names
                    # the mall outright - and its directory pin is a
                    # copy of another shop's, 1.2 km away. The exact
                    # name match is better evidence than the pin.
                    if not (token_q >= 90 and htype == "B"):
                        continue
            # The directory pin itself has to be in Hong Kong. The
            # BAW VAULT pin for HobbyX Plus (K11 Art Mall) sat in the
            # Pearl River estuary, in Yuen Long, 40 km from the shop.
            # A pin that is not in Hong Kong cannot anchor a radius.
            if not in_hong_kong(pin_lat, pin_lon):
                d = 0.0
        elif pin_lat is not None and pin_contradicts:
            # The pin is in the wrong district. The radius it implies
            # is meaningless, so fall back on the address's district:
            # a hit in the district the address names is right.
            hit_dc = dc_of(lat, lon)
            if addr_dc is not None and hit_dc is not None and hit_dc != addr_dc:
                continue
            d = 0.0
        else:
            d = 0.0

        # A STREET is not a building. "CASTLE PEAK ROAD - TSUEN WAN" is
        # type ST, and it matched the shop's own name, so "League Castle
        # (D-Park)" was placed on the road 645 m from 愉景新城 - the
        # building its address actually gives.
        if htype in ("ST", "RD", "STREET", "ROAD"):
            continue

        # safeguard 2: the building token must appear in the hit's OWN name
        # (a building record names itself), or the hit must be the shop.
        # token_hit and token_q were computed above, before the distance
        # gate.
        name_hit = bool(nz and (nz in blob or nz in cn.lower())) or bool(n and n in blob_l)
        if token_hit is None and not name_hit:
            continue
        if token_hit is None and htype not in ("B", "S", "PL"):
            continue

        # A hit whose own name IS an area is not a building, whatever
        # token matched it. "旺角" / "Mong Kok" is type PL and is a
        # neighbourhood record; a shop matched there is placed at the
        # neighbourhood centroid, which can be hundreds of metres from
        # the shop. The building record - 華懋王子大廈 - is the answer.
        if token_hit is not None and token_hit.lower() in AREA_TOKENS \
                and cn.lower().strip() in AREA_TOKENS:
            continue

        s = 0.0
        rule = "building-match"
        if nz and (nz in blob or nz in cn.lower()):
            s += 1000
            rule = "name-match-zh"
        elif n and n in blob_l:
            s += 600
            rule = "name-match-en"
        if htype in ("B", "S", "PL"):
            s += 150                     # a building record is the target
        elif htype == "F":
            s -= 200                     # a facility merely mentions it
        s += token_q
        s += min(float(h.get("score") or 0), 200) / 20.0
        s -= d / 800.0
        cands.append((s, rule, d, h, token_hit))
    if not cands:
        return None
    cands.sort(key=lambda x: -x[0])
    s, rule, d, h, tok = cands[0]
    return {"hit": h, "rule": rule, "dist": d, "token": tok}


def query_variants(address, name):
    """Candidate search strings for one shop, best-first."""
    a = re.sub(r"\s+", " ", (address or "").strip()).strip(" ,")
    a = re.sub(r"^Hong Kong\s*", "", a, flags=re.I)
    for sep in (" ", "，", ","):
        if name and sep in a and a.split(sep)[0].strip().lower() == name.strip().lower():
            a = a.split(sep, 1)[1].strip()
            break

    out = []

    def add(s):
        s = s.strip(" ,，")
        if s and s not in out:
            out.append(s)

    add(a)
    m = re.search(r"^(.*?)([\dA-Za-z\-]{0,4}\s*(?:樓|层|字樓)\s*[0-9A-Za-z\-]*\s*[號号铺舖室].*)$", a)
    if m:
        add(m.group(1))
    m = re.search(r"^(.*?)[,，]\s*(?:SHOP|UNIT|KIOSK|STORE)\s*[A-Za-z0-9\-]+.*$", a, re.I)
    if m:
        add(m.group(1))
    m = re.search(r"^(.*?)[,，]?\s*[A-Za-z]?\d*\s*[Ff]\s*/\s*[Ff].*$", a)
    if m:
        add(m.group(1))
    m = re.search(r"^(.*?)[,，]\s*[A-Za-z]?\d*\s*[Ff]\b.*$", a)
    if m:
        add(m.group(1))
    m = re.search(r"^(.*?)[\dA-Za-z\-]{0,4}\s*(?:樓|层)\s*[0-9A-Za-z\-]*\s*[號号铺舖室](.*)$", a)
    if m:
        add(m.group(1) + " " + m.group(2))
    # A MALL whose name carries a number or a lower-case letter - "i
    # SQUARE", "K11 Art Mall", "MOKO" - needs its own query, because
    # the phrase rule above cannot see it. "Players' Club TCG" is at
    # 尖沙咀i SQUARE 2樓210 and went unlocated until this query was
    # added; the geocoder's answer is 國際廣場 / I Square, 尖沙咀彌敦
    # 道63號.
    for m in re.finditer(r"\b([A-Za-z]{0,3}\d{0,3}[A-Za-z]*\s+[A-Z][A-Za-z]{2,}"
                         r"(?:\s+[A-Z][A-Za-z]{2,}){0,2})\b", a):
        phrase = m.group(1).strip()
        if len(phrase) >= 4 and phrase.lower() not in STOP:
            add(phrase)
    # A lower-case letter or a digit can START the name: "i SQUARE",
    # "K11 Art Mall", "2/F". The word-boundary rule above cannot see
    # them, because a single lower-case letter does not start a word
    # match and a digit does not start a letter match.
    for m in re.finditer(r"(?<![A-Za-z0-9])([a-z]{1,2}\s+[A-Z][A-Za-z]{2,}"
                         r"(?:\s+[A-Z][A-Za-z]{2,}){0,2})(?![a-z])", a):
        phrase = m.group(1).strip()
        if len(phrase) >= 4 and phrase.lower() not in STOP:
            add(phrase)
    if re.search(r"[一-鿿]", a):
        add("".join(re.findall(r"[一-鿿0-9A-Za-z\-]{2,}", a)[-2:]))
    return out


def main():
    rows = list(csv.DictReader(open(HERE / "baw_shops.csv", encoding="utf-8")))
    cache = load_cache()
    out = []
    rules = {}

    for i, r in enumerate(rows):
        name, name_zh = r["name"], r["name_zh"]
        addr = (r["address_zh"] or "").strip()
        pin_lat = float(r["lat"]) if r["lat"] else None
        pin_lon = float(r["lng"]) if r["lng"] else None
        tokens = building_tokens(addr, name)

        best = None
        for q in query_variants(addr, name):
            hits, err = geocode(q, cache)
            if not hits:
                continue
            c = choose(hits, name, name_zh, tokens, pin_lat, pin_lon, addr)
            if c is None:
                continue
            if best is None:
                best = c
            if c["rule"] in ("name-match-zh", "name-match-en"):
                best = c
                break
            time.sleep(0.2)

        if best:
            h = best["hit"]
            rec = {
                "name": name, "name_zh": name_zh,
                "region": r["region"], "area": r["area"],
                "lat": float(h["lat"]), "lon": float(h["lon"]),
                "lat_pin": pin_lat, "lon_pin": pin_lon,
                "games": r["games"], "services": r["services"],
                "checked": r["checked"], "hours": r["hours"],
                "address": addr,
                "geocode_match": h.get("ename") or h.get("cname"),
                "geocode_cname": h.get("cname"),
                "geocode_address": h.get("caddress") or h.get("eaddress"),
                "geocode_id": h.get("id"),
                "geocode_type": h.get("type"),
                "building_token": best["token"],
                "rule": best["rule"],
                "moved_m": round(best["dist"], 1),
                "source": "HK Gov geocoder (building level)",
                "url": r["url"],
            }
        else:
            # A directory pin is the last resort, and only when it is
            # actually in Hong Kong and agrees with the address. A pin
            # in the Pearl River estuary, or in a district the address
            # contradicts, would put the shop on the map in the wrong
            # place with no way to tell from the pin alone.
            addr_dc = address_area_dc(addr)
            pin_dc = dc_of(pin_lat, pin_lon)
            bad_pin = (pin_lat is None
                       or not in_hong_kong(pin_lat, pin_lon)
                       or (addr_dc is not None and pin_dc is not None
                           and addr_dc != pin_dc))
            if bad_pin:
                lat = lon = lat_pin = lon_pin = None
                rule = "unresolved"
                source = ("no building match, and the directory pin is "
                          "outside Hong Kong or contradicts the address")
            else:
                lat, lon = pin_lat, pin_lon
                rule = "directory-pin"
                source = "directory pin (no building match)"
            rec = {
                "name": name, "name_zh": name_zh,
                "region": r["region"], "area": r["area"],
                "lat": lat, "lon": lon,
                "lat_pin": pin_lat, "lon_pin": pin_lon,
                "games": r["games"], "services": r["services"],
                "checked": r["checked"], "hours": r["hours"],
                "address": addr,
                "geocode_match": None, "geocode_cname": None,
                "geocode_address": None, "geocode_id": None, "geocode_type": None,
                "building_token": None,
                "rule": rule, "moved_m": 0.0,
                "source": source,
                "url": r["url"],
            }
        out.append(rec)
        rules[rec["rule"]] = rules.get(rec["rule"], 0) + 1
        if i % 25 == 0:
            print(f"  [{i}/{len(rows)}] {name}", flush=True)
        time.sleep(0.25)

    # Atomic write: a run killed here must not leave a half-written file
    # that a later step reads as complete.
    write_json_atomic(OUT, out, indent=1)
    print("\nrules:", rules)
    moved = [o["moved_m"] for o in out]
    print(f"moved: max={max(moved):.0f}m  >150m={sum(1 for m in moved if m>150)}  "
          f">400m={sum(1 for m in moved if m>400)}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
