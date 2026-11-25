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

HERE = Path(__file__).resolve().parent
CACHE = HERE / "raw" / "geocode_cache.json"
OUT = HERE / "shops_geocoded.json"

ENDPOINT = "https://www.map.gov.hk/gih-ws2/search?keyword={kw}&extent="
HEADERS = {"Referer": "https://www.map.gov.hk/gm/",
           "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

HK = (22.15, 22.58, 113.82, 114.44)
MAX_M = 700.0

# Hong Kong building-name endings.
BUILDING_SUFFIX = re.compile(
    r"(大廈|大厦|大樓|大楼|中心|廣場|广场|商場|商场|工廠大廈|工廠|工廈|"
    r"商務中心|購物中心|購物商場|大塲|寫字樓|屋苑|邨|村|別墅|酒店|戲院|"
    r"會堂|學校|書院|商行|薈館|荟)"
)
STREET_SUFFIX = re.compile(r"(道|街|路|巷|徑|橋|埗|圍)$")

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
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


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


def building_tokens(address):
    """The candidate BUILDING names inside an address.

    Only CJK runs that end in a Hong Kong building word qualify, and a token
    that is a district or street name is rejected.
    """
    toks = set()
    a = address or ""
    for m in re.finditer(r"[一-鿿]{2,}", a):
        run = m.group(0)
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
        words = phrase.split()
        if len(words) > 1:
            toks.add(words[-1])
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
        if cn == tl:
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
        return q
    return -1000.0


def hit_blob(h):
    return " ".join(str(h.get(k) or "") for k in
                     ("ename", "cname", "eaddress", "caddress", "edescription",
                      "cdescription"))


def choose(hits, name, name_zh, tokens, pin_lat, pin_lon):
    """Pick the best hit under the safeguards. Returns a dict or None."""
    if not hits:
        return None
    n = (name or "").strip().lower()
    nz = (name_zh or "").strip().lower()

    cands = []
    for h in hits:
        try:
            lat, lon = float(h["lat"]), float(h["lon"])
        except Exception:
            continue
        if not (HK[0] <= lat <= HK[1] and HK[2] <= lon <= HK[3]):
            continue
        if pin_lat is not None:
            d = metres(pin_lat, pin_lon, lat, lon)
            if d > MAX_M:
                continue                        # safeguard 1: radius
        else:
            d = 0.0
        blob = hit_blob(h)
        blob_l = blob.lower()
        htype = str(h.get("type") or "").upper()
        cn = str(h.get("cname") or "")
        en = str(h.get("ename") or "")

        # safeguard 2: the building token must appear in the hit's OWN name
        # (a building record names itself), or the hit must be the shop.
        token_hit, token_q = None, -1e9
        for t in tokens:
            q = token_quality(t, cn, en)
            if q > token_q and q > 0:
                token_hit, token_q = t, q
        name_hit = bool(nz and (nz in blob or nz in cn.lower())) or bool(n and n in blob_l)
        if token_hit is None and not name_hit:
            continue
        if token_hit is None and htype not in ("B", "S", "PL"):
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
        tokens = building_tokens(addr)

        best = None
        for q in query_variants(addr, name):
            hits, err = geocode(q, cache)
            if not hits:
                continue
            c = choose(hits, name, name_zh, tokens, pin_lat, pin_lon)
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
            rec = {
                "name": name, "name_zh": name_zh,
                "region": r["region"], "area": r["area"],
                "lat": pin_lat, "lon": pin_lon,
                "lat_pin": pin_lat, "lon_pin": pin_lon,
                "games": r["games"], "services": r["services"],
                "checked": r["checked"], "hours": r["hours"],
                "address": addr,
                "geocode_match": None, "geocode_cname": None,
                "geocode_address": None, "geocode_id": None, "geocode_type": None,
                "building_token": None,
                "rule": "directory-pin", "moved_m": 0.0,
                "source": "directory pin (no building match)",
                "url": r["url"],
            }
        out.append(rec)
        rules[rec["rule"]] = rules.get(rec["rule"], 0) + 1
        if i % 25 == 0:
            print(f"  [{i}/{len(rows)}] {name}", flush=True)
        time.sleep(0.25)

    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("\nrules:", rules)
    moved = [o["moved_m"] for o in out]
    print(f"moved: max={max(moved):.0f}m  >150m={sum(1 for m in moved if m>150)}  "
          f">400m={sum(1 for m in moved if m>400)}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
