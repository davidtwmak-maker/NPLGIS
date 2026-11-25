#!/usr/bin/env python3
"""Scrape the HKCardPrice directory of Hong Kong PTCG card shops.

WHY THIS SOURCE
    The user asked where you can go to PLAY a deck with other people, not
    merely where you can buy cards. Two earlier sources answer the wrong
    question:

      - BAW VAULT lists 205 shops but flags "play space" on only 12 of
        them, because its flag means "has a table you can play at".
      - findpoketcgstore lists stores with addresses but no play flag.

    HKCardPrice is a Hong Kong PTCG directory that carries an explicit
    打牌 ("play") tag per shop, plus the official Pokemon shop-map ID
    (GYM054 etc.), which is a first-party registration - the shop has
    registered itself as a Pokemon Card Gym, which means it runs events
    and people can play there.

    It also cross-checks the addresses, and it caught two wrong ones in
    my own hand-built venue list:
      - Ookido Institute TCG is at 嘉時工業大廈 1/F128, 新蒲崗六合街25號
        (San Po Kong, Wong Tai Sin), NOT at 福華街25號 (Sham Shui Po)
      - Play Card Chill is at 榮盛工業大廈 15/F B06, 新蒲崗五芳街26號
        (San Po Kong), NOT at 永盛工業大廈

    Each shop page also gives the nearby MTR station and the district.

OUTPUT
    raw/hkcardprice_shops.json - one record per shop
"""
import html as htmlmod
import json
import re
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = RAW / "hkcardprice_shops.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Language": "zh-HK,zh;q=0.9"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                print(f"    FETCH FAIL {url}: {e}")
                return None
            time.sleep(2)
    return None


def unesc(s):
    return htmlmod.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_listing(doc):
    """Parse the main shop list page.

    Each entry is:
      <li class="shop-item"><div class="si-main">
        <a class="si-name" href="/shops/SLUG/">NAME</a>
        <div class="si-sub">MTR · DISTRICT</div>
        <div class="si-addr">ADDRESS</div>
      </div><div class="si-tags">...tags...</div></li>

    The tags are the value of the shop: 買卡 (buy), 賣卡／收購 (sell/buy
    back), 打牌 (PLAY), 送評 (grading)."""
    shops = []
    # split on the item boundary so each block can be parsed on its own
    blocks = re.split(r'<li class="shop-item">', doc)[1:]
    for b in blocks:
        b = b.split("</li>")[0]
        m_name = re.search(r'<a class="si-name" href="([^"]+)">(.*?)</a>', b, re.S)
        if not m_name:
            continue
        slug = m_name.group(1)
        name = unesc(m_name.group(2))
        m_sub = re.search(r'<div class="si-sub">(.*?)</div>', b, re.S)
        m_addr = re.search(r'<div class="si-addr">(.*?)</div>', b, re.S)
        sub = unesc(m_sub.group(1)) if m_sub else ""
        addr = unesc(m_addr.group(1)) if m_addr else ""
        # the tags live in the si-tags div
        m_tags = re.search(r'<div class="si-tags">(.*?)</div>', b, re.S)
        tags_raw = m_tags.group(1) if m_tags else ""
        tags = [unesc(t) for t in re.findall(r"<span[^>]*>(.*?)</span>",
                                            tags_raw, re.S)]
        mtr = ""
        district = ""
        for part in sub.split("·"):
            part = part.strip()
            if part.endswith("站"):
                mtr = part
            elif part.endswith("區"):
                district = part
        shops.append({
            "name": name,
            "slug": slug.strip("/").replace("shops/", ""),
            "addr": addr,
            "mtr": mtr,
            "district_zh": district,
            "tags": [t for t in tags if t],
            "play": "打牌" in tags,
            "buy": "買卡" in tags,
            "sell": "賣卡" in tags or "收購" in tags,
            "grading": "送評" in tags,
        })
    return shops


def enrich(s, doc):
    """Pull the details off the shop's own page.

    The page carries the official Pokemon shop-map id (GYM054), the
    verification date, and sometimes an English address."""
    m_gym = re.search(r"shopmap/map/([A-Z0-9]+)", doc)
    m_date = re.search(r"資料核實日期\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", doc)
    m_dist = re.search(r"地區\s*<a[^>]*>([^<]+?)</a>", doc)
    m_mtr = re.search(r"附近港鐵站\s*<a[^>]*>([^<]+?)</a>", doc)
    s["gym_id"] = m_gym.group(1) if m_gym else ""
    s["verified"] = m_date.group(1) if m_date else ""
    if m_dist and not s.get("district_zh"):
        s["district_zh"] = m_dist.group(1).strip()
    if m_mtr and not s.get("mtr"):
        s["mtr"] = m_mtr.group(1).strip()
    return s


def main():
    RAW.mkdir(exist_ok=True)
    doc = fetch("https://hkcardprice.com/shops/")
    if not doc:
        print("FATAL: could not fetch the shop list")
        return
    (RAW / "hkcardprice_shops.html").write_text(doc, encoding="utf-8")
    shops = parse_listing(doc)
    print(f"parsed {len(shops)} shops from the list page")

    # The list page shows a default filter. Ask the site for the shops
    # tagged 打牌 so the play set is complete rather than whatever the
    # default view happens to show.
    play_url = "https://hkcardprice.com/shops/?use=%E6%89%93%E7%89%8C"
    pdoc = fetch(play_url)
    if pdoc:
        pshops = parse_listing(pdoc)
        print(f"play-filtered page lists {len(pshops)} shops")
        have = {s["slug"] for s in shops}
        for s in pshops:
            if s["slug"] not in have:
                shops.append(s)
                have.add(s["slug"])

    # The per-district pages hold the rest.
    m_dists = re.findall(r'href="(/shops/district/[^"]+/)"', doc)
    print(f"{len(set(m_dists))} district pages")
    for d in sorted(set(m_dists)):
        dd = fetch("https://hkcardprice.com" + d)
        if not dd:
            continue
        have = {s["slug"] for s in shops}
        for s in parse_listing(dd):
            if s["slug"] not in have:
                shops.append(s)

    # Enrich each shop from its own page (official gym id, verification
    # date). This is 117 requests, so it is paced.
    print(f"enriching {len(shops)} shop pages...")
    for i, s in enumerate(shops, 1):
        if s.get("gym_id") and s.get("verified"):
            continue
        p = fetch("https://hkcardprice.com/shops/" + s["slug"] + "/")
        if p:
            enrich(s, p)
        if i % 20 == 0:
            print(f"  {i}/{len(shops)}")
            json.dump(shops, open(OUT, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)

    json.dump(shops, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_play = sum(1 for s in shops if s["play"])
    print(f"\nwrote {OUT}: {len(shops)} shops, {n_play} tagged 打牌 (play)")
    from collections import Counter
    print("by district:")
    for k, v in Counter(s["district_zh"] for s in shops).most_common():
        print(f"   {k:14} {v}")


if __name__ == "__main__":
    main()
