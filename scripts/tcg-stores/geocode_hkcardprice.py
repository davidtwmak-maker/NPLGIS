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
from atomic_write import write_json_atomic
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

# The floor and unit part at the end of an address. Stripped off to
# leave the building name.
_FLOOR_UNIT = re.compile(
    r"("
    r"地下.*|地庫.*|地窖.*|樓上.*|樓下.*|"
    r"G\s*/\s*F.*|GF.*|"
    r"LG\s*\d+.*|UG\s*\d+.*|"
    # Chinese floor numerals: 二樓, 三字樓, 廿三樓
    r"[一二三四五六七八九十廿零兩]+\s*[字]?\s*[樓层F].*|"
    r"\d+[A-Za-z]?\s*[樓层F室舖铺座檔鋪位號].*|"
    r"[A-Za-z]{0,3}\s*\d+[A-Za-z]?\s*[室舖铺座檔鋪位號].*"
    r")$")
_LATIN = re.compile(r"[A-Za-z]")

# The gazetteer's record types that can stand for a place a shop is in.
#   B  building            S  shopping centre     PL complex
#   F  facility inside one P  place (a named building the index
#                             classifies as a place - 喜利商場 is type
#                             P, and excluding it lost the shop)
#   SS shopping centre / street
# ST is a STREET and is never a place a shop is inside.
PLACE_TYPES = ("B", "S", "PL", "F", "P", "SS")

BUILDING_WORDS = [
    "中心", "大廈", "廣場", "商場", "大樓", "工廈", "工業中心", "工業大廈",
    "工商中心", "工廠大廈", "花園", "別墅", "地帶",
    # Added after the first pass dropped shops whose buildings end in
    # one of these: 都會駅 (Metro Town, a shopping mall), 雙子匯 (The
    # Twins, a commercial building), 唐二樓 (a tonglau block). Without
    # them the address produced no building token at all and the shop
    # was silently dropped from the layer.
    "駅", "匯", "樓", "閣", "臺", "台",
]
# The suffixes that carry no identifying information. Two sources may call
# the same building 工業大廈 or 工廠大廈, so the distinctive part is what
# gets compared.
GENERIC_SUFFIX = [
    "工業大廈", "工廠大廈", "工業中心", "商業大廈", "商業中心", "工商中心",
    "貿易大廈", "工業大廈", "廣場", "商場", "大廈", "大樓", "中心", "花園",
    "別墅", "工廈", "地帶", "樓宇",
    # The SIMPLIFIED forms. A directory writes 美聯工業大厦 where the
    # gazetteer has 美聯工業大廈, and the suffix must be stripped from
    # both or the two never compare equal.
    "工业大厦", "工商中心", "商业大厦", "商业中心", "贸易大厦", "工业中心",
    "工厂大厦", "广场", "商场", "大厦", "大楼", "中心", "花园", "别墅",
    "工厦", "地带", "楼宇",
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
    """The part of a building name that identifies it.

    Strips the generic suffix (大廈, 中心, 廣場...) AND the gazetteer's
    qualifier. The gazetteer records a building's former name as
    "喜利商場 (別稱)" - a qualifier the directory never writes - and
    without stripping it the hit's core is "喜利商場 (別稱)", which
    matches nothing.

    The suffix list must cover the SIMPLIFIED forms too: a directory
    writes 美聯工業大厦 where the gazetteer has 美聯工業大廈.

    The English generic words are normalised as well, because the two
    sources disagree on them: the directory writes "Everest Industrial
    Building" and the gazetteer "Everest Industrial Centre".
    """
    n = (name or "").strip()
    # The gazetteer's own qualifier: 喜利商場 (別稱)
    n = re.sub(r"[（(]\s*別稱\s*[)）]", "", n).strip()
    # A directory mixes the scripts freely: 美聯工業大厦 writes 工業 in
    # traditional and 厦 in simplified, so neither the traditional
    # suffix 工業大廈 nor the simplified 工业大厦 matches it. Normalise
    # the characters that differ between the two spellings FIRST, so
    # that only one form of each suffix has to be listed.
    n = (n.replace("厦", "廈").replace("业", "業").replace("场", "場")
          .replace("楼", "樓").replace("广", "廣").replace("带", "帶")
          .replace("园", "園").replace("别", "別"))
    # The LONGEST matching suffix wins. "工業大廈" must be stripped
    # before "大廈", or 美聯工業大廈 and 美聯工業 both reduce to the
    # same core and stop being distinguishable.
    for suf in sorted(GENERIC_SUFFIX, key=len, reverse=True):
        if n.endswith(suf) and len(n) > len(suf) + 1:
            n = n[: -len(suf)]
            break
    n = n.strip()
    if re.search(r"[A-Za-z]", n):
        n = re.sub(r"\b(CENTRE|CENTER|BUILDING|BLDG|PLAZA|MALL|TOWER|HOUSE|"
                   r"ESTATE|ARCADE|FACTORY|INDUSTRIAL|WORKS|GARDENS|COURT|"
                   r"CTR|CENT)\b", "", n, flags=re.I)
        n = re.sub(r"\s+", " ", n).strip()
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
# An English building name whose KEYWORD is not the last word, and the
# abbreviated forms directories use. "Everest Industrial Building" has
# the keyword in the middle, and "Hewlett Ctr" abbreviates "Centre" -
# neither matched the patterns above, so those two shops produced no
# building token and were dropped from the layer.
EN_BUILDING_MID = re.compile(
    r"\b([A-Z][A-Za-z0-9'&\-]+)\s+"
    r"(INDUSTRIAL|COMMERCIAL|TRADE|CENTRAL)\s+"
    r"(CENTRE|CENTER|BUILDING|BLDG|PLAZA|MALL|TOWER|HOUSE|ESTATE|FACTORY|"
    r"WORKS|COURT)\b",
    re.I,
)
EN_BUILDING_ABBR = re.compile(
    r"\b([A-Z][A-Za-z0-9'&\-]*(?:\s+[A-Z][A-Za-z0-9'&\-]*){0,2})\s+"
    r"(CTR|CENT|BLDG|IND|EST)\b",
    re.I,
)


def variant_forms(name):
    """The other spellings of a building name that the gazetteer may hold.

    Hong Kong directories are inconsistent about a few characters. The
    gazetteer always uses the standard form, so a token written the
    other way finds nothing - and a shop with no location is dropped
    from the layer without ever being reported as missing.

      埸 -> 場   in mall names   (天悅廣埸 -> 天悅廣場)
      厦 -> 廈   in building names (美聯工業大厦 -> 美聯工業大廈)

    Returns every distinct alternative, including the original.
    """
    swaps = [("廣埸", "廣場"), ("商埸", "商場"), ("大厦", "大廈"),
             ("廣场", "廣場"), ("商场", "商場")]
    out = [name]
    for a, b in swaps:
        if a in name:
            out.append(name.replace(a, b))
    # A simplified 厦 anywhere, paired with 大厦 or 工業大厦.
    if "厦" in name:
        out.append(name.replace("厦", "廈"))
    seen, res = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res


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
    for w in ("廣場", "商場", "中心", "大廈", "大樓", "地帶", "城", "匯", "駅"):
        for m in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9]{2,8}" + w + ")", addr):
            run = m.group(1)
            # Keep the FULL run as a candidate, not just the part left
            # after the area prefix. "將軍澳廣場" is the name of the
            # mall in Tseung Kwan O, and "銅鑼灣地帶" is the name of
            # the mall in Causeway Bay - stripping the area leaves
            # "廣場" and "地帶", which are not buildings, and the
            # candidate is then discarded for being too short. The
            # shops were then silently dropped from the layer.
            if len(run) >= 3:
                buildings.append(run)
            b = strip_area_prefix(run)
            if len(b) >= 3:
                buildings.append(b)
    # A MALL address carries the mall name but no street number of its
    # own ("旺角信和中心21樓05室", "長沙灣天悅廣場1樓159B"). The unit
    # number is the floor, not the street, so it must not be read as a
    # street number. The mall name is the FIRST building-like word in the
    # address, before any floor marker.
    if not nums:
        # The floor marker can follow the mall name with NO separator:
        # "將軍澳廣場1樓1081號舖". The pattern below requires up to four
        # NON-digit characters between the mall name and the floor, so
        # a digit straight after 廣場 broke the match and no building
        # token was produced at all.
        m = re.search(r"([\u4e00-\u9fff]{2,12}?(?:廣場|商場|中心|大廈|大樓|地帶))"
                      r"[^0-9]{0,4}(?:\d|[A-Za-z])\s*(?:樓|层|F|/[0-9])", addr)
        if m:
            run = m.group(1)
            if len(run) >= 3:
                buildings.append(run)
            b = strip_area_prefix(run)
            if len(b) >= 3:
                buildings.append(b)
        else:
            # a bare mall name and a unit: "天悅廣埸 1樓133A店"
            m = re.search(r"([\u4e00-\u9fff]{2,12}?(?:廣場|廣埸|商場))", addr)
            if m:
                run = m.group(1)
                if len(run) >= 3:
                    buildings.append(run)
                b = strip_area_prefix(run)
                if len(b) >= 3:
                    buildings.append(b)

    # A building name that comes AFTER the street number. The Chinese
    # run then starts with the 號 marker itself - "號唐二樓",
    # "號美聯工業大厦" - so the run does not look like a building name
    # and no token is produced. Two of the shops that failed to
    # geocode had their building named this way.
    for m in re.finditer(r"號\s*([一-鿿]{2,10}?(?:大廈|大厦|工廈|工業大廈|"
                         r"工商中心|中心|廣場|商場|大樓|花園|別墅|地帶|"
                         r"匯|駅|樓|閣|臺|台))", addr):
        run = m.group(1)
        if len(run) >= 3:
            buildings.append(run)
        b = strip_area_prefix(run)
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
    for m in EN_BUILDING_MID.finditer(addr):
        buildings.append(" ".join(x.title() for x in m.groups()))
    for m in EN_BUILDING_ABBR.finditer(addr):
        b = " ".join(x.title() for x in m.groups())
        buildings.append(b)
        # "Hewlett Ctr" is "Hewlett Centre" in the gazetteer. Try the
        # expansion as well as the abbreviation.
        exp = {"Ctr": "Centre", "Cent": "Centre", "Bldg": "Building",
               "Ind": "Industrial", "Est": "Estate"}.get(m.group(2).title())
        if exp:
            buildings.append(m.group(1).title() + " " + exp)

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


def _strip_floor_unit(tail):
    """Strip the floor and unit part off the end of an address tail.

    "THE HEDON16樓" -> "THE HEDON"
    "天悅廣場地下A9舖" -> "天悅廣場"
    "凱源工業大廈1/f C室" -> "凱源工業大廈"
    """
    prev = None
    while prev != tail:
        prev = tail
        tail = _FLOOR_UNIT.sub("", tail).strip(" ,;-·、")
    return tail


def building_after_ha(addr):
    """The building an address names after a street-number marker.

    The building sits after the 號 that follows the street number:
    "九龍九龍城區蕪湖街53-59號金輝行12樓2-3室" -> 金輝行
    "尖沙咀河內道 18 號 K11 購物藝術館地庫 1 樓" -> K11 購物藝術館
    """
    if not addr:
        return None
    cands = []
    for m in re.finditer(r"號\s*", addr):
        tail = addr[m.end():].strip()
        if not tail:
            continue
        tail = _strip_floor_unit(tail)
        if len(tail) < 2:
            continue
        cands.append(tail)
    if not cands:
        return None
    # Prefer a name that carries Latin letters (K11, THE HEDON), then
    # the longest.
    return max(cands, key=lambda c: len(c) + (2 if _LATIN.search(c) else 0))


def gazetteer_building(cand, lat, lon, cache=None):
    """The gazetteer's OWN record for the building called `cand`.

    The gazetteer is the authority on building names - it is the same
    index the position came from - so the label is looked up there
    rather than guessed from the address text.
    """
    if not cand:
        return None
    best, bd = None, 1e9
    for h in hits_of(query(cand, cache if cache is not None else load_cache())):
        if h.get("type") not in ("B", "S", "PL", "P", "SS"):
            continue
        try:
            la, lo = float(h["lat"]), float(h["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        d = abs(la - lat) + abs(lo - lon)
        if d < bd:
            bd, best = d, h
    # Only accept a record that is essentially at the same point.
    if best is not None and bd <= 0.0015:
        return best
    return None


def building_label(hit, shop_addr, lat, lon, cache=None):
    """The building a matched facility record should be reported as.

    A type-F record is a business INSIDE a building - a clinic, a
    7-Eleven, a WiFi hotspot. Its own address names the building it is
    in: "新界西貢區唐德街1號將軍澳廣場2樓2089舖" is a medical centre on
    the 2nd floor of 將軍澳廣場.

    Matching a shop to one of these puts it in the right place, but the
    published label then says the card shop IS the clinic. So the
    building is read out of the facility's own address, and from the
    SHOP's address when the facility's does not repeat it ("屯門建泰街
    6號" for a clinic, where the shop's address names 恒威工業中心).
    """
    hit_addr = str(hit.get("caddress") or hit.get("eaddress") or "")
    cands = [c for c in (building_after_ha(hit_addr),
                         building_after_ha(shop_addr)) if c]
    if not cands:
        return None
    # Prefer a building the gazetteer confirms, which also gives its
    # official spelling.
    for c in cands:
        rec = gazetteer_building(c, lat, lon, cache)
        if not rec:
            continue
        name = rec.get("cname") or rec.get("ename")
        if not name:
            continue
        # The gazetteer appends "(別稱)" to an alternative name.
        name = re.sub(r"\s*\(別稱\)\s*$", "", name).strip()
        # The gazetteer's Chinese name for iSQUARE is 國際廣場, which
        # drops the brand the shop's own address writes (iSQUARE國際
        # 廣場). Where one name contains the other, the longer one is
        # the more complete statement of the same building.
        if c != name and name in c:
            c = _strip_floor_unit(c)
            if c and name in c:
                return c
        return name
    # No gazetteer record: fall back to the address reading, with the
    # floor part stripped off.
    c = _strip_floor_unit(cands[0])
    return c or cands[0]


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


def is_area_hit(hit, addr=""):
    """Is this gazetteer record an AREA rather than a place?

    The gazetteer holds a record for every district and neighbourhood
    (元朗, 旺角), and its coordinate is the area's CENTROID - not a
    building. Such a record must never be the answer when the address
    names a building.

    A shopping centre is also type PL, so the type alone does not tell
    them apart. The test is the record's own NAME against the address:
    an area record is named exactly like the area the address names,
    and carries no street address of its own. 精靈谷's address is
    "元朗喜利商場一樓9號舖" - the hit called 元朗 is the area, and the
    hit called 喜利商場 is the building. Matching the area put the shop
    at the 元朗 centroid, 700 m from the mall.
    """
    if hit.get("type") not in ("PL", "P"):
        return False
    cn = str(hit.get("cname") or "").strip()
    en = str(hit.get("ename") or "").strip()
    # The hit names a district: every District Council district ends
    # in 區 and has a "District" English name.
    if cn.endswith("區") or en.endswith("District"):
        return True
    # The hit's name IS an area named in the address, and the hit
    # carries no street address of its own.
    if addr:
        for area in AREA_PREFIX:
            if cn == area and area in addr:
                if not str(hit.get("caddress") or "").strip():
                    return True
    return False


def name_hit(hit, want_names):
    """Does the hit's name contain one of the wanted building names?

    Compared on the DISTINCTIVE part, because the directory and the
    government index differ on the generic suffix: the directory writes
    寶富大廈 where the index writes 寶富大樓.

    A hit's distinctive core must MATCH the wanted core, not merely be
    a part of it. The wanted name is often still carrying its area
    prefix - "咀加連威老道嘉威大廈" for 嘉威大廈 - and a loose
    containment test let the street 富明街 score as a match for
    "銅鑼灣富明街寶富大廈", while the real building 寶富大樓 was
    rejected because its core is a prefix, not the whole thing.

    The comparison is therefore made on the SUFFIX: the distinctive
    part of a building name sits at its end (寶富大樓 -> 寶富, 新貿
    中心 -> 新貿), so a hit matches when the wanted core ENDS with the
    hit's core.
    """
    blob = " ".join(str(hit.get(k) or "") for k in
                    ("cname", "ename", "caddress", "eaddress"))
    bl = blob.lower()
    for w in want_names:
        wl = w.lower()
        if len(wl) >= 3 and wl in bl:
            return True
        if re.search(r"[一-鿿]", w):
            core = distinctive(w)
            if len(core) >= 2 and core in bl:
                return True
            # the hit may carry a qualifier: 嘉康中心 (前稱)
            for hn in (str(hit.get("cname") or ""), str(hit.get("ename") or "")):
                hd = distinctive(hn)
                if not hd or len(hd) < 2:
                    continue
                # The hit's core must BE the wanted core, or be the
                # tail of it: "寶富" is the tail of "富明街寶富".
                # A hit whose core is only a prefix of the wanted core
                # is a different building - "元朗" is a prefix of
                # "元朗喜利", and matching it put the shop at 元朗大廈
                # instead of 喜利商場.
                if core == hd or core.endswith(hd):
                    return True
                if hd == core:
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
        # The directory sometimes writes a building name with a variant
        # character. Query the corrected form too:
        #   天悅廣埸  -> 天悅廣場   (埸 for 場)
        #   美聯工業大厦 -> 美聯工業大廈 (simplified 厦 for 廈)
        # Each of these is a building the gazetteer holds under the
        # other form, so without the correction the shop is unlocated
        # and silently dropped.
        extra = []
        for t in tokens:
            for fixed in variant_forms(t):
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
            if h.get("type") not in PLACE_TYPES:
                continue
            # The hit must be in Hong Kong. A bounding box is not a
            # land test, so this asks the District Council boundary
            # layer directly: a hit outside every district is not a
            # building in Hong Kong and cannot be the shop.
            try:
                hlat = float(h["lat"]) + HK80_TO_WGS[0]
                hlon = float(h["lon"]) + HK80_TO_WGS[1]
            except (KeyError, TypeError, ValueError):
                continue
            if not district_of(hlat, hlon):
                continue
            hn = hit_numbers(h)
            named = name_hit(h, buildings)
            # An AREA record is not a building. The gazetteer holds a
            # record for every district and neighbourhood (元朗,
            # type PL), and the hit sits at the area's centroid. When
            # the address names a building that is also a candidate, the
            # area must not win: 精靈谷 was placed at the 元朗
            # centroid, 700 m from 喜利商場, the mall its address
            # names. The area scores lower than any building.
            if is_area_hit(h, s.get("addr", "")):
                named = False
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

        # A type-F record is a business inside a building. The match is
        # to the right place, but the published name must be the
        # BUILDING, not the clinic or the convenience store that
        # happens to sit at that point. The facility is kept as the
        # evidence for the match.
        hit_name = h.get("cname") or h.get("ename") or ""
        hit_type = h.get("type")
        match_name = hit_name
        if hit_type == "F":
            bld = building_label(h, s.get("addr", ""), lat, lon, cache)
            if bld:
                match_name = bld

        out.append({
            **s,
            "geocoded": True,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "geocode_match": match_name,
            "geocode_evidence": hit_name,
            "geocode_address": h.get("caddress") or h.get("eaddress") or "",
            "geocode_type": hit_type,
            "geocode_district": d,
            "geocode_district_expected": want_d,
            "geocode_district_ok": same,
            "geocode_score": round(sc, 1),
        })
        mark = "ok " if same else "DIF"
        print(f"  [{i:3}/{len(shops)}] {s['name'][:30]:32} -> "
              f"{str(match_name)[:16]:18} "
              f"({lat:.5f},{lon:.5f}) {mark}[{d}]")

    write_json_atomic(OUT, out, indent=1)
    ok = sum(1 for o in out if o.get("geocoded"))
    dok = sum(1 for o in out if o.get("geocoded") and
              o.get("geocode_district") and o.get("geocode_district_expected") and
              o["geocode_district"].lower() == o["geocode_district_expected"].lower())
    print(f"\nwrote {OUT}: {ok}/{len(out)} geocoded, {dok} district-consistent")


if __name__ == "__main__":
    main()
