# Hong Kong trading card game shops and play venues — NOTES

**What this project answers:** *Where can you go in Hong Kong to play a deck with
other people, and who lives near those places?* The map pairs every card shop
and play venue in Hong Kong with the 2021 Population Census population aged
15–24 within 1 km, so the gaps between demand and supply are visible.

**The headline numbers**

| | |
|---|---|
| Card shops mapped | **289** |
| Places you can actually play | **49** |
| Shops confirmed by two independent directories | **47 (16%)** |
| Official Pokémon Gyms (run events) | **66** |
| Census small areas | **211** |
| Hong Kong's population aged 15–24 | **591,073 (8% of the population)** |
| 15–24-year-olds within 1 km of a play venue | **181,152** |
| 15–24-year-olds with **no** venue within 1 km | **409,921 (69.4%)** |
| Small areas with no venue within 1 km | **152 of 211** |

**The one-line answer:** the places to play are concentrated in the urban core —
Sham Shui Po, Yau Tsim Mong, Kwun Tong, Wan Chai, Wong Tai Sin — and the young
people who would play them are spread across the whole territory. **Seven in ten
15-to-24-year-olds in Hong Kong live more than a kilometre from any venue where
they could play.** That is the finding, and it is a supply problem, not a demand
problem.

**The finding survives its own strongest challenge.** If every one of the 66
registered Pokémon Gyms is counted as a venue too — the most generous possible
reading of the supply side — the unserved share only falls from **69.4% to
65.1%**, and the number of small areas with no venue only falls from 152 to
145. The gap is not an artefact of how strictly "play space" is defined.

---

## 1. Sources

| Source | What it gives | Provenance |
|---|---|---|
| **BAW VAULT** Hong Kong card-shop directory | 205 shops with map pins, addresses, service tags | Directory scrape, checked 16 Oct 2026 |
| **HKCardPrice** Hong Kong PTCG directory | 117 shops, 24 tagged 打牌 "play", 67 with an official Pokémon Gym id | `hkcardprice.com/shops/`, scraped 25 Nov 2026, all 117 detail pages fetched and verified |
| **Hand-built venue list** | 23 card-game and board-game cafés | Built from shop listings and web search, 25 Nov 2026 |
| **HK Government location search** | Building-level geocoding | `map.gov.hk/gih-ws2/search`, Referer header required |
| **C&SD 2021 Population Census** | Population by small area, incl. age 15–24 | `censtatd_rcd_1635933193720_58660`, via the CSDI Portal |
| **District Council boundaries** | District check for every geocode | `assets/data/self-study-rooms/district_boundaries.geojson.gz`, 18 features |

**OpenStreetMap was tried and abandoned.** All three Overpass mirrors failed
(`overpass-api.de`, `overpass.osm.jp`, `overpass.private.coffee`). The
fallback was to download the raw tile data for the whole territory: a
**651-tile grid**, plus **23 tiles split into quarters** where the full-tile
request hit the 50,000-node limit, giving **720 tiles with complete
coverage** and no gaps.

Every tag in those 720 tiles was read. There is **not one shop tagged as a
card game shop** — no `shop=cards`, no `shop=card_game`, no
`shop=board_game`, no `shop=hobby`. The parser found **173 distinct shop
tags** in total (`supermarket` 588, `mall` 656, `convenience` 1,237, and so
on). The nearest neighbours are `shop=toys` (50) and `shop=model` (3); two
of those model shops matched only because their name contains 模型
("models"), and both were rejected as card-game shops. OSM has no usable
coverage of this scene.

The tile data is kept, so the claim is checkable rather than asserted.

**But the sweep did find one real gap.** 玩具模型倉 (Hobbyland) is a trading-card
chain, and OSM carries its Sham Shui Po branch at **福榮街 54** — a shop that
**neither directory lists**. The two directories together carry its Kwun Tong
branch (BAW VAULT), its Ma On Shan branch and its Tseung Kwan O branch
(HKCardPrice), but not this one. It is left out of the layer rather than
hand-added: OSM has no card-game shop tag, so this is a name-matched
`shop=toys` record, and the scope of a single shop should be settled by
reading its page, not by a keyword rule. **One branch of one chain in one
district** is the honest size of what OSM contributed.

### The merge

The three directories are merged into one layer on a **shop-level** key —
building + shop name — not on the building alone, because a single mall can
hold a dozen card shops and each needs its own point on the map.

- **47 shops** appear in two or more directories. Every one was checked
  address-by-address before being merged.
- Matching on the building alone would wrongly merge a mall's shops together;
  matching on the name alone would wrongly merge a chain's branches. Both the
  name **and** the building must agree, and where only one side names a
  building, the name match alone is accepted.
- A shop can only carry the play flag once. The merge refuses to let a second
  shop in the same building claim it.
- **Six of the 23 hand-built venues turned out to be the same shop the
  directories already list** — "ACard TCG" and "ACARD TCG" are one shop, not
  two. Each venue is tested against the merged directory shops on its
  normalised name and its distance, and absorbed into the shop it duplicates
  rather than added as a second venue. Without this the supply side would
  have been inflated by six venues, and the gaps understated.

---

## 2. Geocoding

Every shop is geocoded to the **building**, not to a street centroid, using the
Hong Kong Government's own location search service.

**How the endpoint works:** `https://www.map.gov.hk/gih-ws2/search?keyword={kw}&extent=`
must be called with a `Referer: https://www.map.gov.hk/gm/` header. The
response is a **bare JSON list** (not an object with a `results` key), and the
useful fields are `cname`, `ename`, `caddress`, `eaddress`, and `type`. Type `B`
is a building, `S` and `PL` are shopping centres and complexes, `F` is a
facility inside one. Coordinates are HK1980 Grid and need the HK80→WGS84
offset.

**Ranking the candidate matches.** A hit is accepted on evidence, in this
order:

1. **Building name match** — Chinese or English, case-insensitive, with
   suffix normalisation (中心 vs 商場 are the same building; 大樓 vs 工廈 vs
   工廠大廈 are all stripped to their stem).
2. **Street number match** — the number in the source address must appear in
   the hit's own address. Floor specifications (`11/F`, `G/F`) are excluded
   from the number so they cannot masquerade as street numbers.
3. **Street name match** — credit only, never elimination. The two directories
   routinely give the same street two different names, so a street-name
   disagreement is evidence of nothing.
4. **District** — **confirmatory, never a veto.** Hand-written district
   columns in source listings are guesses, and a district boundary that runs
   down a street splits a single building between two districts. The district
   is recorded and compared, but it never rejects an otherwise good match.

**Three gates that override the ranking**, each added after it caught a real
error rather than before it:

- **A point-in-polygon land test.** A bounding box is not a land test.
  Hong Kong is not a rectangle, and the BAW VAULT pin for HobbyX Plus (K11
  Art Mall) sits at 22.426 N, 114.086 E — in the Pearl River estuary,
  **40 km from the shop**, and inside the bounding box. Every candidate is
  now tested against the District Council boundary polygons: a hit outside
  every district is not in Hong Kong and cannot be the shop's building.
- **The address outranks the pin.** A directory pin whose District Council
  district contradicts the district the address names is a wrong pin. When
  that happens the pin stops anchoring the radius, and the candidate's own
  district is checked against the address's instead. The area-to-district
  mapping used for this is **derived** — the government geocoder is asked
  where each area name is, the district its hits agree on is taken, and the
  shop pins are used only as a cross-check. An area where the geocoder's
  hits disagree, or where the pins disagree with the geocoder, is left
  unmapped: an unmapped area never triggers the check, whereas a wrongly
  mapped area would reject a correct pin.
- **An area is not a building, and a road is not a building.** The
  government index has a record for every district and neighbourhood
  ("旺角", type `PL`) and for every street ("CASTLE PEAK ROAD", type `ST`).
  Both were being accepted as buildings. An area token cannot outscore a
  building token, and street records are rejected outright — "League Castle
  (D-Park)" was being placed on the road 645 m from 愉景新城, the building
  its address actually gives.

**Why this ranking.** The hardest problem in this dataset is **duplicate
building names**. There are three separate buildings called 嘉威大廈 in Hong
Kong. When a source address is only a building name, the search returns all
three and only the street number in the hit's own address can separate them.
Hence street number ranks above street name, and full-address queries are
tried before name-only queries.

**Results**

| Set | Geocoded | District-confirmed |
|---|---|---|
| BAW VAULT shops | 205 | — |
| HKCardPrice shops | **112 / 117** | 100 |
| Hand-built venues | **19 / 23** | 19 |

**Merged: 289 shops**, of which 47 are confirmed by two or more sources.

The **5** HKCardPrice shops still unresolved are the cases the government
index simply does not carry in the shape the directory gives them, or does
not carry at all:

| Shop | Address | Why |
|---|---|---|
| Cardstop | *(none)* | the directory lists no address at all |
| Grass Type TCG Company | Room R3, 11/F Everest Industrial Building, 396 Kwun Tong Road | the gazetteer calls it Everest Industrial **Centre**; the directory says **Building** |
| Have Card 樓上咭店 | 九龍弼街49號唐二樓 | the building is not in the index under that name |
| MY 咭 | 天悅廣埸 1樓133A店 | the mall is indexed as 天悅廣場, and the unit is on its first floor |
| Ptcgcardfans 見卡打牌 | 天悅廣埸1樓165店 | the same mall, the same floor |

The **4** unresolved hand-built venues were traced to **wrong addresses in the
source listings**, not to failed matches: 嘉時工廠大廈 is at 六合街25-27號 in San
Po Kong, not the 福華街25號 the directory gives — a different building.

**The three that moved.** Three shops changed position when the matcher was
corrected, and in every case the new position is the one the address names:
千日匠 旺角新之城店 moved 6.4 km, from a stray HKT WiFi hotspot in Tai Kok to
旺角中心第一座, the mall its address gives; CardKing moved 87 m from 美羅中心
to 美羅中心2期, because its address says 二期; Card Gather moved 84 m from
良膳廚坊 to 屯門恒威工業中心, because its address says so.

**Three geocodes were checked by hand against the authoritative District
Council boundary layer and confirmed correct despite differing from the
directory's own district label.** These are boundary cases — 天后 and 太子 sit
on district lines.

---

## 3. The spatial analysis

**Population.** The 2021 Population Census small areas, with the population
aged 15 to 24 for each, joined to the shop layer by the area's own geometry.

**Two tiers of "a place you can play", kept apart because the evidence
differs.** A *confirmed* venue is one the source directory itself says you can
play at — BAW VAULT's `play_space` service tag, HKCardPrice's 打牌 flag, or a
hand-built venue entry. A *registered Gym* is one on the official Pokémon shop
map, so it runs official events and events need a play space. That is strong
evidence, but it is not the same claim as "you can turn up and play", so the
66 Gyms are counted and reported separately rather than folded into the 49
confirmed venues. The sensitivity scenario below tests the assumption.

**The measure.** For every census small area:

```
y1524_per_play_1000m = (population aged 15-24 within 1 km of a play venue)
                        ÷ (number of play venues within 1 km)
```

1 km is a straight-line radius from the area's centroid. It is a **proxy for
walking, not a routed distance** — on Hong Kong's street network 1 km of
straight line is often 1.3 km of actual walking, and the error is not uniform
across the territory.

**Verification gates.** The build refuses to produce output unless:

- The summed population reconciles **exactly** with the published C&SD figure
  — **7,411,945**. It does.
- Polygon simplification moves no vertex more than **60 m** (worst case
  **13.3 m**).
- No small area loses more than 2% of its area to simplification, and no area
  with a population above 50 changes by more than 5%.

**The fix worth recording:** the shipped
`POPULATION — small_area_census.csv` has a **defective district column** — 15
of 18 districts are wrong, and the defect predates this project (commit
`d6c0eb9`). It was not silently worked around. The district was re-derived
spatially from the small-area polygons themselves (`raster.py` scanline
assignment, then `fix_blank_districts.py` and `diagnose_district.py`), and the
wrong column is flagged in §6.

---

## 4. What the AI did, and what the data did

Same division of labour as the covered-walkways project.

**The AI wrote the code and the method.** Roughly 2,000 lines of Python across
13 scripts: the directory parsers, the geocoder and its evidence ranking, the
merge and its dedup rules, the census join, the catchment measurement, the
verification gates, the browser data builder and the static figure.

**The government data produced the answer.** No number in this project was
written by hand. Every count is re-derived from the shipped files by an
independent script, and the population total is checked against the published
C&SD figure rather than assumed.

**The AI found the bugs, by checking outputs against source data rather than
trusting them.** Thirty-five silent defects were caught this way, including:

- the census column names (`t_pop`, `age_2_15_24`) being read as if they were
  `pop_total` / `pop_15_24` — the build failed its own reconciliation gate at
  **0** people, which is how it was found;
- the **district column being wrong for 15 of 18 districts** in the shipped
  census CSV, caught by spatial assignment disagreeing with the file;
- San Po Kong being assigned to Kowloon City when the census boundary layer
  puts it in **Wong Tai Sin**;
- a script that had silently dropped the `address_zh` and `bldg_zh` columns
  from the venue table;
- the browser data shipping as a plain array when Leaflet needs GeoJSON
  Features — the polygons did not render at all;
- a geocoder comparing a Chinese district label against an English one and
  reporting **0** district-consistent matches;
- the strip-area-prefix list missing 長沙灣, so building names kept the area
  name attached and matched nothing;
- a score-ranking tuple bug where the token was read as if it were the score;
- a 30 m shelter buffer that had become 30 **degrees**, making every stop read
  as 100% sheltered — the same class of error as the covered-walkways project;
- duplicate building names in the search results needing street-number
  disambiguation (three separate 嘉威大廈);
- the merge double-counting a play flag when two shops shared a building;
- **the hand-built venues double-counting six shops the directories already
  listed** — "ACard TCG" and "ACARD TCG" are one shop, so the venue list and
  the directory each claimed it and the supply side was inflated by six;
- the shop names not matching across directories because one used the Latin
  name and the other the Chinese one — "Brave Soul TCG" and "Brave Soul 闘卡魂"
  are one shop, and the branch name has to be stripped off as well
  ("Battleground" and "Battleground Kwun Tong" are one chain);
- a truncation where the area table showed bare codes instead of names;
- **a bounding box being used as a land test** — Hong Kong is not a
  rectangle, and the directory's own pin for HobbyX Plus (K11 Art Mall) sat
  at 22.426 N, 114.086 E, in the Pearl River estuary **40 km from the shop**.
  A point-in-polygon test against the District Council boundary is the only
  test that settles "is this in Hong Kong", and it rejected the pin;
- the address tokeniser cutting a building name at its phase marker, so
  "恒豐工業大廈第1期" produced the token "工業大廈第" — a token that matches
  every industrial building in Hong Kong, and did;
- the shop's own name being used as a building token, so "League Castle
  (D-Park)" matched **CASTLE PEAK ROAD**, a road, 645 m from the building its
  address gives (愉景新城);
- a street record (type `ST`) being accepted as a building at all;
- an **area** record being accepted as a building, so "Have Card" was placed
  at the Mong Kok district centroid, 679 m from 華懋王子大廈, because the
  area name matched exactly and the building name did not;
- a mall's Chinese name carrying a qualifier — "天悅廣場 (別稱)" — which made
  an exact match look like a partial one;
- a mall whose name starts with a lower-case letter ("i SQUARE") being
  invisible to the tokeniser, leaving one shop unlocated;
- `s not in confirmed` comparing **dicts by value**, so two different shops
  with the same fields compared equal and a registered Gym was dropped from
  the registered-only count;
- **fourteen of the 117 HKCardPrice shops failing to geocode, and being
  silently dropped from the layer** — they were never reported as missing.
  Five separate causes, one per building-name shape the tokeniser did not
  handle:
  - the area prefix was stripped from the whole name, so **將軍澳廣場**
    (the mall in Tseung Kwan O) became "廣場" — two characters, rejected as
    too short. The building name is the *whole* run, area included, and the
    strip must not be allowed to eat it;
  - the mall name could not be followed immediately by a floor number
    (**將軍澳廣場1樓**), so no building token was produced at all;
  - a building named *after* the street number (**49號唐二樓**) has a CJK run
    that begins with the 號 marker, and did not look like a building;
  - the English patterns required the building word to be **last**
    ("Everest Industrial Building" has it in the middle) and did not know
    the **abbreviations** directories use ("Hewlett Ctr");
  - the gazetteer's record type **`P`** was not accepted. 喜利商場 is a
    type-P record, and type-P records were being filtered out before
    scoring, so a perfectly good mall was never a candidate.
- the **distinctive-name comparison accepting a prefix** as a match: the
  wanted core "元朗喜利" and the hit core "元朗" (a different building,
  元朗大廈) compared as equal on a loose containment test. A hit matches
  when the wanted core *ends with* the hit's core, since the identifying
  part of a building name is at its end;
- a **script-mixed building name** — 美聯**工業****大厦**, traditional 工業
  with simplified 厦 — matching neither the traditional nor the
  simplified suffix list, and so matching nothing;
- the gazetteer's own qualifier **" (別稱)"** surviving the suffix strip
  and turning the hit's core into "喜利商場 (別稱)", which matched nothing;
- an **area record** (元朗, type PL, the area's centroid) winning over the
  real building, putting 精靈谷 at the 元朗 centroid, 700 m from the
  喜利商場 its address names;
- the English building name of a mall differing from the gazetteer's —
  the directory writes "Everest Industrial **Building**", the gazetteer
  "Everest Industrial **Centre**";
- **a renamed field reading as zero.** The published GeoJSON carries the
  `ai_` prefixed names — `ai_play_near_1000m`, not `play_near` — because
  every derived field carries that prefix for the CSDI Awards disclosure.
  The build script that assembles the browser data still read the old
  names, so `p.get("play_near")` returned `None` for **every one of the
  211 small areas**, and `int(float(None or 0))` turned each into **0**.
  The app then reported "no play venue within 1 km" for the whole
  territory. It did not crash, the map rendered, and the headline numbers
  — which come from the summary — were correct, so the error was
  invisible: only the per-area panel was wrong, and it looked like a
  finding.
  The fix is the reader, and the fix that stops it recurring is a
  **cross-check against an independent copy of the same numbers**: the
  build now compares every area's venue count against the CSV, which
  carries the same values under the working names, and refuses to write
  output if they disagree. A renamed field can now fail the build
  instead of quietly emptying the map;
- **a matched record naming the wrong thing.** The government index
  holds a record type `F` — a business *inside* a building: a clinic,
  a 7-Eleven, a WiFi hotspot. **37 of the 112 resolved HKCardPrice
  shops matched one**, because the index keys on the unit number the
  address gives, and a unit number lives inside a building. The
  position was right in every case, but the published `geocode_match`
  named the clinic — so 玩具模型倉 (將軍澳廣場店) was published as
  "啟心醫務中心" and 天悅廣場's eight shops were published as
  "郭炳輝醫生醫務所有限公司".
  The label is now the **building**, read from the facility's own
  address and from the shop's address, then confirmed against the
  gazetteer's own building record so the spelling is the official one.
  The facility is kept in a new `geocode_evidence` field, so the
  match can still be audited. Every one of the 37 was checked against
  the building its address names; no position moved.

**Every derived field carries an `ai_` prefix** (`ai_y1524_per_play_1000m`,
`ai_play_venue_count`, …). This is the disclosure mechanism used for the
CSDI Awards entry and it is what the school group should quote.

**A prefix rename is a schema change.** Putting the `ai_` prefix on the
published fields changed the names the GeoJSON carries, so every script
that reads that GeoJSON has to read the new names. The prefix was
applied to the published layer in one commit and the reader was not
updated in the same one — and because a missing property is indistinguishable
from a zero, the result was a map that claimed the whole territory had no
venue within 1 km. **When a published field is renamed, every reader of
that file is part of the change**, and the build needs a gate that
compares the value it read against a second copy of the same number.

`scripts/check_app_fields.py` is that gate, applied to every app in this
repository: it compares every property name each app reads against every
property name its published data actually contains, and exits non-zero
when an app reads something that is not there. It is the check that would
have caught the 5834 bug before it shipped, and it covers the three apps
here — the walkways app (日曬雨淋中學's project) passes on all 33 fields
it reads.

---

## 5. Honest limits

- **The play flag is a directory claim, not a verified visit.** 24 shops are
  tagged 打牌 by HKCardPrice and 12 by BAW VAULT's service tags; nobody has
  walked in and checked. A venue's play space can change without notice. The
  sensitivity scenario above shows the conclusion does not rest on how
  strictly this flag is read — 65.1% are still unserved if all 66 registered
  Gyms count.
- **Six venues were absorbed rather than added.** The 49 confirmed venues
  include six that two sources independently list. If those six were counted
  twice, the unserved share would fall by roughly a point — the conclusion
  is unchanged either way, but the deduplication is stated so the number can
  be checked.
- **1 km is straight-line.** Real walking distance is longer and varies with the
  street network. It has not been routed — unlike the covered-walkways project,
  which does route on the LandsD pedestrian network.
- **The measure is per venue, and one mall can hold many shops.** A mall with
  three card shops counts as three venues for the areas around it. That is
  defensible (each is a separate place to play) but it is not the same as
  counting *venues*.
- **The census is 2021.** Five years old at the time of writing. Shops open
  and close in that time.
- **The small-area boundaries are anonymised codes** with no place names, so
  the table identifies each area by district and code.
- **A shop in a mall is placed at the mall's centroid**, not at a unit number
  inside it. Two shops in the same mall may land on exactly the same point.
- **The hand-built venue list is not exhaustive** — it is a list of the venues
  that a web search found, not a survey of every café in Hong Kong.

---

## 6. Known defects in upstream files

- **`assets/data/self-study-rooms/POPULATION — small_area_census.csv`** — the
  `district` column is **wrong for 15 of the 18 districts** (defect predates
  this project; commit `d6c0eb9`). This project re-derives the district
  spatially and does not use that column. Other projects that rely on it should
  be re-checked.
- **BAW VAULT's `address` field is Chinese**, not English, and its
  `building_token` is the building token — the field names are misleading and
  two earlier merge attempts produced 5 and 35 false overlaps because the
  merge read the wrong column as the English address.

---

## 7. Files

**Data** — `assets/data/tcg-stores/`

| File | What |
|---|---|
| `tcg_shops_merged.json` | The merged layer: 289 shops with coordinates, district, play flag, gym id, source count |
| `tcg_shops_hkcardprice.json` | The 117 HKCardPrice shops with geocodes and district checks |
| `tcg_shops_hkcardprice_directory.json` | The raw directory scrape, before geocoding — provenance |
| `tcg_play_venues.json` | The 23 hand-built venues, 19 geocoded |
| `POPULATION — tcg_small_area_metrics.csv` | Per-area population and the measure |
| `tcg_small_area_metrics.geojson` | The 211 areas with their metrics and simplified geometry |
| `tcg_summary.json` | The headline numbers |

**Map** — `assets/maps/tcg-stores/tcg_shops_map.png`

**App** — `apps/tcg-stores/` (`index.html`, `app.js`, `data/`)

**Scripts** — `scripts/tcg-stores/` (13 files, in pipeline order:
parse → scrape → geocode → merge → analyse → build → verify)

---

*Population data © HKSAR Government, released under the C&SD terms for
non-commercial use with attribution. Every AI-derived field is prefixed `ai_`.*
