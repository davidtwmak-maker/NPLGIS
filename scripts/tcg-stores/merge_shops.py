#!/usr/bin/env python3
"""Merge the three shop directories into ONE layer, and check the overlaps.

THE THREE SOURCES
    1. BAW VAULT (205 shops)  - a hobby-shop directory with its own map
       pins, a games flag and a services flag. Its "play space" flag is
       on only 12 of the 205, because it means "has a table you can play
       at", not "runs card games".
    2. HKCardPrice (117 shops) - a Hong Kong PTCG directory built from the
       official Pokemon shop map, with a 打牌 ("play") tag per shop and an
       official Pokemon Gym id for 67 of them. A Gym registration is a
       first-party statement that the shop runs events.
    3. The hand-built play venue list (23) - card-game cafes and
       board-game cafes that neither directory lists, because they are
       not card shops.

WHY MERGE
    A shop that appears in two directories has been seen by two
    independent observers, which is evidence that it exists and is open.
    A shop that appears in one may have closed. The overlap is therefore
    worth measuring, and the merged layer keeps the best address and the
    best coordinate for each shop.

HOW SHOPS ARE MATCHED
    On the building. Two directories describing the same shop in the same
    building are the same shop - a mall can hold ten card shops and each
    needs its own point. The building is matched on the distinctive part
    of its name, because the two directories and the government index all
    use slightly different suffixes for the same building.

OUTPUT
    shops_merged.json - one record per physical shop
"""
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "shops_merged.json"

GENERIC_SUFFIX = [
    "工業大廈", "工廠大廈", "工業中心", "商業大廈", "商業中心", "工商中心",
    "貿易大廈", "廣場", "商場", "大廈", "大樓", "中心", "花園", "別墅",
    "工廈", "地帶", "樓宇", "工業大廈",
]


def distinctive(name):
    n = (name or "").strip()
    for suf in GENERIC_SUFFIX:
        if n.endswith(suf) and len(n) > len(suf) + 1:
            n = n[: -len(suf)]
            break
    return n.strip()


def norm_zh(s):
    """Normalise a Chinese string for comparison."""
    if not s:
        return ""
    s = s.replace("廣埸", "廣場").replace("商埸", "商場")
    s = re.sub(r"[\s（）()·・,，、。．\.]+", "", s)
    return s


def norm_en(s):
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def building_key(addr_zh, addr_en, name):
    """A key that identifies the BUILDING a shop is in.

    The Chinese building name is preferred because it is what the
    directories and the government index agree on; the English name is
    the fallback. Some directories give only one language, so both are
    always tried."""
    for cand in (addr_zh or "",):
        for suf in ("中心", "廣場", "商場", "大廈", "大樓", "地帶", "工廈"):
            m = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,10}" + suf + r")", cand)
            if m:
                b = norm_zh(m.group(1))
                # drop a leading district/area name
                for pre in ("深水埗", "旺角", "尖沙咀", "銅鑼灣", "灣仔",
                            "柴灣", "香港仔", "鰂魚涌", "太古", "新蒲崗",
                            "九龍灣", "觀塘", "黃大仙", "鑽石山", "牛頭角",
                            "藍田", "秀茂坪", "紅磡", "土瓜灣", "大圍",
                            "沙田", "石門", "火炭", "荃灣", "葵涌", "葵芳",
                            "葵興", "元朗", "天水圍", "屯門", "將軍澳",
                            "西貢", "大埔", "上水", "粉嶺", "東涌", "離島",
                            "九龍城", "九龍", "香港", "新界", "港島",
                            "長沙灣", "荔枝角", "青衣", "馬鞍山", "調景嶺",
                            "啟德"):
                    if b.startswith(pre) and len(b) > len(pre) + 1:
                        b = b[len(pre):]
                        break
                if len(b) >= 3:
                    return "zh:" + b
    # The English building name, which for many directories is the only
    # form available: "41C-D GRANVILLE ROAD, TSIM SHA TSUI" carries the
    # building in a form like "KAM WAI BUILDING".
    m = re.search(r"([A-Z][A-Za-z0-9'&\-]*(?:\s+[A-Z][A-Za-z0-9'&\-]*){0,3})\s+"
                  r"(CENTRE|CENTER|BUILDING|BLDG|PLAZA|MALL|TOWER|HOUSE|"
                  r"ESTATE|ARCADE|FACTORY|INDUSTRIAL|WORKS|GARDENS|COURT)\b",
                  addr_en or "", re.I)
    if m:
        return "en:" + norm_en(m.group(0))
    # A Chinese building name inside an otherwise English address.
    for suf in ("中心", "廣場", "商場", "大廈", "大樓", "地帶", "工廈"):
        m = re.search(r"([\u4e00-\u9fff]{2,10}" + suf + r")", addr_en or "")
        if m:
            b = norm_zh(m.group(1))
            if len(b) >= 3:
                return "zh:" + b
    # fall back to the shop name itself
    return "name:" + norm_zh(name) + "|" + norm_en(name)


def key_aliases(addr_zh, addr_en, name, bldg_zh):
    """Every building key a shop could plausibly be filed under."""
    keys = []
    k = building_key(addr_zh, addr_en, name)
    if k:
        keys.append(k)
    if bldg_zh:
        keys.append("zh:" + norm_zh(bldg_zh))
    # the distinctive part of the building name, without the suffix
    for k2 in list(keys):
        if k2.startswith("zh:"):
            d = distinctive(k2[3:])
            if d and len(d) >= 2:
                keys.append("zh~:" + d)
    return keys


def shop_key(addr, name, name_zh=""):
    """A key that identifies a SHOP, not just a building.

    A mall can hold a dozen card shops and each needs its own point, so
    the building alone is not enough. The shop is keyed on its UNIT
    number within the building when the address gives one ("天悅廣場1樓
    173號鋪" is a different shop from "天悅廣場1樓165店"), and on the
    shop's own name otherwise."""
    unit = ""
    m = re.search(r"(\d+[A-Za-z]?)\s*(?:號|铺|舖|室|铺位|shop|unit)", addr or "")
    if m:
        unit = m.group(1).upper()
    b = building_key(addr, "", name)
    n = norm_en(name)
    # the generic card-game words in a shop name carry no identity
    n = re.sub(r"(tcg|card|cards|shop|store|hk|ltd|limited|company|co)",
               "", n)
    if unit:
        return f"{b}#{unit}|{n}"
    return f"{b}|{n}"


def name_key(name):
    """A key for matching a shop's NAME across directories.

    "ACard TCG" and "ACardTCG" are the same shop; "Brave Soul TCG" and
    "Brave Soul 闘卡魂" are the same shop with a Chinese name added."""
    n = norm_en(name)
    n = re.sub(r"(tcg|cards|card|shop|store|hk|ltd|limited|company|co|"
               r"gaming|hobby|trading)", "", n)
    return n


def main():
    baw = json.load(open(HERE / "shops_geocoded.json", encoding="utf-8"))
    hkp = json.load(open(HERE / "shops_hkcardprice_geocoded.json", encoding="utf-8"))
    venues = json.load(open(HERE / "play_venues_geocoded.json", encoding="utf-8"))

    print(f"BAW VAULT:      {len(baw)}")
    print(f"HKCardPrice:    {len(hkp)}")
    print(f"play venues:    {len(venues)}")

    # ---- index the HKCardPrice shops by their building keys --------------
    by_key = {}
    by_name = {}
    for s in hkp:
        keys = key_aliases(s.get("addr"), "", s.get("name"), "")
        s["_keys"] = keys
        s["_namekey"] = name_key(s.get("name", ""))
        for k in keys:
            by_key.setdefault(k, []).append(s)
        by_name.setdefault(s["_namekey"], []).append(s)

    merged = []
    matched_hkp = set()

    # ---- 1. the BAW VAULT shops -----------------------------------------
    for s in baw:
        # BAW VAULT's address field is the Chinese one, and its
        # building_token is the building the shop sits in.
        addr = s.get("address", "") or ""
        keys = key_aliases(addr, "", s.get("name", ""), s.get("building_token"))
        nk = name_key(s.get("name", ""))
        # A shop is the same shop if it has the same NAME, or if it is
        # the same NAME in the same BUILDING. Matching on the name alone
        # would merge two different branches of the same chain, so the
        # building has to agree too when both sides know it.
        hit = None
        for cand in by_name.get(nk, []):
            if id(cand) in matched_hkp:
                continue
            # The building has to agree when BOTH sides name one. If
            # only one side names it, the matching name is the evidence.
            shared = set(cand["_keys"]) & set(keys)
            cand_has_bldg = any(k.startswith(("zh:", "en:")) for k in cand["_keys"])
            mine_has_bldg = any(k.startswith(("zh:", "en:")) for k in keys)
            if shared or not (cand_has_bldg and mine_has_bldg):
                hit = cand
                break
        if hit is None:
            # fall back to the building, but only when the unit number
            # agrees - a mall can hold several branches
            for k in keys:
                for cand in by_key.get(k, []):
                    if id(cand) in matched_hkp:
                        continue
                    if shop_key(addr, s.get("name", "")) == \
                            shop_key(cand.get("addr", ""), cand.get("name", "")):
                        hit = cand
                        break
                if hit:
                    break
        rec = {
            "name": s.get("name"),
            "name_zh": s.get("name_zh"),
            "address": addr,
            "address_zh": addr,
            "lat": s.get("lat"),
            "lon": s.get("lon"),
            "ai_sources": ["bawvault"],
            "games": (s.get("games") or "").split() if isinstance(s.get("games"), str) else (s.get("games") or []),
            "services": (s.get("services") or "").split() if isinstance(s.get("services"), str) else (s.get("services") or []),
            "ai_play_space": "play_space" in ((s.get("services") or "").split()
                                              if isinstance(s.get("services"), str)
                                              else (s.get("services") or [])),
            "ai_play_tag": False,
            "gym_id": None,
            "mtr": None,
            "district": s.get("area"),
            "baw_region": s.get("region"),
            "baw_url": s.get("url"),
            "ai_geocode_rule": s.get("rule"),
        }
        if hit is not None:
            matched_hkp.add(id(hit))
            rec["ai_sources"].append("hkcardprice")
            rec["ai_play_tag"] = bool(hit.get("play"))
            rec["gym_id"] = hit.get("gym_id") or None
            rec["mtr"] = hit.get("mtr") or None
            rec["hkcardprice_addr"] = hit.get("addr")
            rec["name_zh"] = rec["name_zh"] or hit.get("name")
            # keep the HKCardPrice coordinate when the BAW pin is absent
            if rec["lat"] is None and hit.get("geocoded"):
                rec["lat"] = hit.get("lat")
                rec["lon"] = hit.get("lon")
        merged.append(rec)

    # ---- 2. the HKCardPrice shops not already matched -------------------
    for s in hkp:
        if id(s) in matched_hkp:
            continue
        if not s.get("geocoded"):
            continue
        merged.append({
            "name": s.get("name"),
            "name_zh": s.get("name"),
            "address": s.get("addr"),
            "address_zh": s.get("addr"),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
            "ai_sources": ["hkcardprice"],
            "games": [],
            "services": [],
            "ai_play_space": False,
            "ai_play_tag": bool(s.get("play")),
            "gym_id": s.get("gym_id") or None,
            "mtr": s.get("mtr") or None,
            "district": s.get("geocode_district"),
            "hkcardprice_addr": s.get("addr"),
        })

    # ---- 3. the dedicated play venues -----------------------------------
    # A hand-built venue is often the SAME shop that a directory already
    # lists with a play flag - "ACard TCG" and "ACARD TCG" are one shop,
    # not two. Adding both would double-count the venue and inflate the
    # supply side of the measure. So each venue is first tested against
    # the merged directory shops: if one of them is already a play venue
    # with the same name in the same building, the venue is merged into
    # that shop instead of being added separately.
    def norm_name(x):
        """The comparable stem of a shop name.

        A shop appears in the directories under its Latin name in one
        place and its Chinese name in another - "Brave Soul TCG" and
        "Brave Soul 闘卡魂" are one shop. The branch names and the
        Chinese descriptors are stripped so that only the identifying
        stem is compared."""
        x = (x or "").lower()
        # the Latin-script part only
        lat = re.sub(r"[^a-z0-9]+", " ", x)
        lat = re.sub(r"\b(tcg|cards|card|shop|store|hk|ltd|limited|company|co|"
                     r"gaming|hobby|trading|and|the|of|room|unit|shop)\b", " ", lat)
        lat = re.sub(r"\s+", " ", lat).strip()
        # a branch name qualifies the shop, it does not identify it -
        # "Battleground" and "Battleground Kwun Tong" are one chain
        lat = re.sub(r"\b(kwun tong|tsuen wan|mong kok|causeway bay|sha tin|"
                     r"kowloon bay|tseung kwan o|tuen mun|yuen long|tin shui|"
                     r"cheung sha wan|lai chi kok|sai wan|san po kong|tai po|"
                     r"wan chai|north point|sai kung|ma on shan|hang hau|"
                     r"the angle|centre|center|plaza|point)\b", " ", lat)
        lat = re.sub(r"\s+", " ", lat).strip()
        if lat:
            return lat
        # no Latin script: fall back to the Chinese characters
        zh = re.sub(r"[^\u4e00-\u9fff]+", "", x)
        zh = re.sub(r"(集換式卡牌遊戲平台|卡牌遊戲及桌遊專門店|桌上遊戲專賣店|"
                     r"桌遊工作室|桌遊天地|遊桌|店|遊戲|專門|專賣|研究|所)", "", zh)
        return zh

    def hav(a, b):
        R = 6371000.0
        p1, p2 = math.radians(a[0]), math.radians(b[0])
        dp = p2 - p1
        dl = math.radians(b[1] - a[1])
        x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * R * math.asin(math.sqrt(x))

    # index the merged shops that are already play venues
    play_shops = [m for m in merged
                  if m["ai_play_space"] or m["ai_play_tag"]]
    venues_absorbed = 0
    for v in venues:
        if not v.get("geocoded"):
            continue
        vn = norm_name(v.get("name"))
        best = None
        best_d = 1e9
        for m in play_shops:
            if norm_name(m.get("name")) != vn:
                continue
            d = hav((v["lat"], v["lon"]), (m["lat"], m["lon"]))
            if d < best_d:
                best_d, best = d, m
        # 120 m is the threshold: the same shop listed twice by two
        # sources lands within a few metres of itself; two different
        # shops in the same building are further apart than that.
        if best is not None and best_d < 120:
            if "play_venue" not in best["ai_sources"]:
                best["ai_sources"].append("play_venue")
            best["ai_play_space"] = True
            best["ai_play_tag"] = True
            best["place_type"] = best.get("place_type") or v.get("place_type")
            best["play_note"] = best.get("play_note") or v.get("play_note")
            venues_absorbed += 1
            continue
        merged.append({
            "name": v.get("name"),
            "name_zh": v.get("name_zh"),
            "address": v.get("address"),
            "address_zh": v.get("address_zh"),
            "lat": v.get("lat"),
            "lon": v.get("lon"),
            "ai_sources": ["play_venue"],
            "games": [],
            "services": [],
            "ai_play_space": True,
            "ai_play_tag": True,
            "gym_id": None,
            "mtr": None,
            "district": v.get("geocode_district") or v.get("dc_district"),
            "place_type": v.get("place_type"),
            "play_note": v.get("play_note"),
        })
    print(f"\nhand-built venues absorbed into an existing shop: {venues_absorbed}")

    # ---- the overlap, which is the evidence that a shop is real ---------
    both = [m for m in merged if len(m["ai_sources"]) > 1]
    play_total = [m for m in merged
                  if m["ai_play_space"] or m["ai_play_tag"]]

    print(f"\nmerged shops:   {len(merged)}")
    print(f"in 2+ sources: {len(both)}")
    print(f"play venues:   {len(play_total)}")
    from collections import Counter
    c = Counter()
    for m in merged:
        for s in m["ai_sources"]:
            c[s] += 1
    print("by source:", dict(c))
    print("play by source:", dict(Counter(
        s for m in play_total for s in m["ai_sources"])))

    json.dump(merged, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
