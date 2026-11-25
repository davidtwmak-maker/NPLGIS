import json, math


def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


hkp = json.load(open('shops_hkcardprice_geocoded.json', encoding='utf-8'))
merged = json.load(open('shops_merged.json', encoding='utf-8'))
mg = [m for m in merged if m.get('lat') is not None]

missing = []
matched = 0
for s in hkp:
    if not s.get('geocoded'):
        continue
    best_d, best_m = 1e9, None
    for m in mg:
        d = hav((s['lat'], s['lon']), (m['lat'], m['lon']))
        if d < best_d:
            best_d, best_m = d, m
    if best_d > 60:
        missing.append((s, best_d, best_m))
    else:
        matched += 1

print(f"merged shops: {len(merged)}")
print(f"geocoded HKCardPrice shops: {sum(1 for s in hkp if s.get('geocoded'))}")
print(f"  matched to a merged shop within 60 m: {matched}")
print(f"  NOT in the merged layer: {len(missing)}")
print()
for s, d, m in missing:
    print(f"  {s.get('name')[:38]:40} nearest: {str(m.get('name'))[:26]:28} {d:.0f} m")
    print(f"      addr: {s.get('addr')}")

# and the reverse: merged shops with no geocode
nogeo = [m for m in merged if m.get('lat') is None]
print(f"\nmerged shops with NO coordinate: {len(nogeo)}")
for m in nogeo:
    print("  ", m.get('name'), "|", m.get('ai_sources'))

# and the venue list
pv = json.load(open('play_venues_geocoded.json', encoding='utf-8'))
vpv = [v for v in pv if v.get('geocoded')]
print(f"\nhand-built venues geocoded: {len(vpv)} / {len(pv)}")
missing_v = []
for v in vpv:
    best_d, best_m = 1e9, None
    for m in mg:
        d = hav((v['lat'], v['lon']), (m['lat'], m['lon']))
        if d < best_d:
            best_d, best_m = d, m
    if best_d > 120:
        missing_v.append((v, best_d, best_m))
print(f"  venues more than 120 m from any merged shop: {len(missing_v)}")
for v, d, m in missing_v:
    print(f"    {v.get('name')[:38]:40} nearest {str(m.get('name'))[:24]:26} {d:.0f} m")
