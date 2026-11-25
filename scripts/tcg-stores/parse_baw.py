#!/usr/bin/env python3
"""Parse the BAW VAULT Hong Kong card-shop directory into a clean CSV.

Each shop row on the directory page carries:
  data-lat / data-lng   the pin
  data-g                 game tags (onepiece, pokemon, yugioh, mtg, ...)
  data-s                 service tags (buys_cards, grading_dropoff, play_space, ...)
  data-t                 checked / not-checked
  data-dist              the named area (Cheung Sha Wan, Kwun Tong, ...)
  the shop name (English + original Chinese) and the shop's own page URL
  the "Directions" link, which carries the full street address in Chinese

Coordinates come from the source page; nothing is geocoded from memory.
"""
import csv
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

PAGES = {
    "Kowloon": "https://bawvault.com/card-shops/hong-kong/kowloon/",
    "Hong Kong Island": "https://bawvault.com/card-shops/hong-kong/hong-kong-island/",
    "New Territories": "https://bawvault.com/card-shops/hong-kong/new-territories/",
}

ROW_RE = re.compile(r'<li class="shop-row"(?P<attrs>[^>]*)>(?P<body>.*?)</li>', re.S)
ATTR_RE = re.compile(r'data-(?P<k>[a-z]+)="(?P<v>[^"]*)"')


def fetch(url, dest):
    if dest.exists() and dest.stat().st_size > 5000:
        return dest.read_text(encoding="utf-8", errors="replace")
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8", errors="replace")
    dest.write_text(body, encoding="utf-8")
    return body


def parse(region, body):
    rows = []
    for m in ROW_RE.finditer(body):
        attrs = dict((mm.group("k"), html.unescape(mm.group("v")))
                     for mm in ATTR_RE.finditer(m.group("attrs")))
        b = m.group("body")
        name_m = re.search(r'<p class="shop-name">.*?<a href="(?P<href>[^"]+)">(?P<name>[^<]+)</a>', b, re.S)
        if not name_m:
            continue
        orig_m = re.search(r'<span class="orig"[^>]*>([^<]*)</span>', b)
        meta_m = re.search(r'<p class="shop-meta">(.*?)<span', b, re.S)
        games_m = re.search(r'<p class="shop-games">(.*?)</p>', b, re.S)
        hours_m = re.search(r'<p class="shop-hours">(.*?)</p>', b, re.S)
        dir_m = re.search(r'destination=([^"&]+)', b)
        address = ""
        if dir_m:
            address = urllib.parse.unquote(dir_m.group(1))
            # the destination is "NAME ADDRESS"; the address starts after the shop name
            nm = html.unescape(name_m.group("name")).strip()
            if address.startswith(nm):
                address = address[len(nm):].strip(" ,")
            orig = html.unescape(orig_m.group(1)).strip() if orig_m else ""
            if orig and address.startswith(orig):
                address = address[len(orig):].strip(" ,")
        rows.append({
            "region": region,
            "name": html.unescape(name_m.group("name")).strip(),
            "name_zh": html.unescape(orig_m.group(1)).strip() if orig_m else "",
            "url": "https://bawvault.com" + name_m.group("href"),
            "area": attrs.get("dist", ""),
            "lat": attrs.get("lat", ""),
            "lng": attrs.get("lng", ""),
            "games": attrs.get("g", ""),
            "services": attrs.get("s", ""),
            "checked": attrs.get("t", ""),
            "hours": re.sub(r"<[^>]+>", " ", hours_m.group(1)).strip() if hours_m else "",
            "address_zh": address,
            "meta": re.sub(r"<[^>]+>", " ", meta_m.group(1)).strip() if meta_m else "",
        })
    return rows


def main():
    allrows = []
    for region, url in PAGES.items():
        dest = RAW / f"baw_{region.replace(' ', '_')}.html"
        body = fetch(url, dest)
        rows = parse(region, body)
        print(f"{region:20} {len(rows):4} shops")
        allrows.extend(rows)

    fields = ["region", "name", "name_zh", "area", "lat", "lng", "games",
              "services", "checked", "hours", "address_zh", "url"]
    with open(HERE / "baw_shops.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in allrows:
            w.writerow({k: r.get(k, "") for k in fields})

    nolat = [r for r in allrows if not r["lat"]]
    dupes = {}
    for r in allrows:
        if r["lat"]:
            dupes.setdefault((r["lat"], r["lng"]), []).append(r["name"])
    shared = {k: v for k, v in dupes.items() if len(v) > 1}
    print(f"\ntotal {len(allrows)} shops; {len(nolat)} without coordinates; "
          f"{len(shared)} coordinate groups shared by >1 shop")
    for k, v in list(shared.items())[:10]:
        print("   ", k, v)
    json.dump(allrows, open(HERE / "baw_shops.json", "w"), ensure_ascii=False, indent=1)
    print("wrote baw_shops.csv / baw_shops.json")


if __name__ == "__main__":
    sys.exit(main())
