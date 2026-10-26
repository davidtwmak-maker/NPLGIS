# HK Volleyball Courts — GeoJSON layers

Booking price, usage percentage and **live** vacancy status for volleyball courts in
Hong Kong, prepared from LCSD (康樂及文化事務署) open data.

**Snapshot: 22 October 2026.** All layers are WGS84 (`EPSG:4326`), RFC 7946 compliant.

---

## Files

| File | Features | Geometry | What it is |
|---|---:|---|---|
| `venues.geojson` | 101 | Point | One row per bookable indoor venue — price bands, usage %, vacancy summary |
| `sessions.geojson` | 13,152 | Point | Every bookable session in the 8-day window, with its own price and vacancy |
| `free_outdoor_courts.geojson` | 65 | Point | Free outdoor + beach volleyball courts (no hire charge, no feed) |
| `usage_by_venue.geojson` | 100 | Point | LCSD annual usage % for the main arena, 2020–2022 |
| `districts.geojson` | 18 | Polygon | The 18 District Council district boundaries (for join/aggregation) |
| `venues.csv` / `sessions.csv` | — | — | Flat versions for Excel / XY Table to Points |

Rebuild: `bash fetch_raw.sh` then `python3 build_geojson.py`.
Quick-look check: `python3 quicklook_map.py` → `quicklook_map.png`.

---

## The three things you wanted to study

### 1. Booking price

The live feed publishes **no price** — it only says how many courts are free. Price
comes from LCSD's published hire-charge schedule, which is a **single published rate
card**, so it is joined onto each session by air-conditioning status and time band.

Basketball / Volleyball / Netball Court, per hour (identical in the Urban and
New Territories schedules):

| Venue type | Peak | Off-peak | Concessionary peak / off-peak |
|---|---:|---:|---:|
| Indoor **with** A/C | $148 | $120 | $74 / $60 |
| Indoor **without** A/C | $82 | $57 | $41 / $29 |

Peak = at or after 18:00 Mon–Fri, at or after 13:00 Sat, any time Sun or public holiday.
Off-peak = before 18:00 Mon–Fri (except public holiday), before 13:00 Sat.

So `sessions.geojson` carries `hire_normal_hkd` and `hire_concessionary_hkd` per
session, plus `price_band` and `price_band_reason` so the band can be audited.

### 2. Usage percentage

`usage_by_venue.geojson` / `venues.geojson` — LCSD's annual *Usage of Recreational
and Sports Facilities by Venue*, matched on **"Arena"** (the main multi-purpose hall).
**100 of the 101** live venues have a match; the series runs **2020–2022 only** and
stops there. For 2022: 89 venues have a value, median 95%, range 57–99%.

8 venues needed a fuzzy join — the usage feed drops the parenthetical the live feed
carries (*Tin Ping Sports Centre* vs *Tin Ping Sports Centre (Non-air-conditioned in
Arena)*). These are matched on the name with parentheticals stripped **and** coordinates
within 60 m; every recovery was 1:1 and the largest was 37 m. The only 2 LCSD venues
with no bookable volleyball court today are Sai Wan Ho and Praya Street.

### 3. Live vacancy

`available_courts` per session, from the SmartPLAY feed, refreshed **every 5 minutes**
by LCSD. In this snapshot 1,911 of 13,152 sessions (14.5%) had a vacancy.

---

## Sources

| Data | Source | Format | Notes |
|---|---|---|---|
| Live vacancy | `data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/volleyball/file` | JSON | 13,152 rows; every 5 min; 8-day window 22–29 Oct 2026 |
| Usage | CSDI `lcsd_rcd_1670389615666_788` | FeatureServer | 1,206 rows, 301 of them Arena; 2020–2022 |
| Free outdoor courts | CSDI `lcsd_rcd_1670383751618_95284` | FeatureServer | 58 courts |
| Beach volleyball | CSDI `lcsd_rcd_1670383539632_8620` | FeatureServer | 7 courts |
| Districts | GeoInfo Map `LND_DC_POLY_SDO` | cached gz GeoJSON | 18 polygons |
| Hire charges | lcsd.gov.hk `ls_booking_charges_urban.html` / `_nt.html` | HTML table | transcribed, see rate card above |
| General holidays | `1823.gov.hk/common/ical/en.json` | iCal | 2025–2027 gazetted |

---

## Validation

- **Count parity** — CSDI served vs downloaded: 58/58 outdoor, 7/7 beach, 1,206/1,206
  usage, 106/106 sports centres. Live feed 13,152 → 13,152 session features.
- **session_id unique** — 13,152 of 13,152. The hall is part of the key, because some
  venues book two genuinely different halls at the same start time
  (`Arena (Centre 1)` / `Arena (Centre 2)`); venue+date+time alone collides 256 times.
- **Coordinate check** — all 101 venue points fall inside the HK bounding box, all
  distinct, and 99 of them land within 200 m of the matching record in LCSD's separate
  sports-centre dataset. The two others are naming variants, not errors:
  *Boundary Street Sports Centre* (LCSD calls it "No. 2", 2.8 m away) and
  *JC Tuen Mun Butterfly Beach Sports Centre* ("The Jockey Club …", 0.0 m).
- **Structure** — no null geometry, no null properties, all polygon rings closed.

---

## Outline map (`hk_outline_map.png`)

`hk_outline_map.png` replaces `quicklook_map.png` as the orientation figure. The
quicklook version had no basemap, so the dots floated without landmarks.

**Land outline — how it was obtained.** The OSM `natural=coastline` route failed:
every Overpass instance (`overpass-api.de`, `kumi`, `private.coffee`, `osm.ru`)
was unreachable from this machine for the whole session (HTTP 000), and the one
instance that answered (`osm.ch`) serves a Switzerland-only extract. geoBoundaries
has no HKG row (HK is inside CHN). The bundled Natural Earth 10m territory was
tested and **rejected**: its HK polygon is generalised about 7% small in area and
strands 23 venue dots in the sea, which would misplace courts on the map.

What worked is **Esri China (HK) Shoreline** (`Shoreline_view` layer 19), the
iB1000 shoreline derived from LandsD — 9,033 polyline features, 533,761 vertices,
verified WGS84 (urban centres fall 0.1–1.5 km inland from the nearest shore
vertex; Aberdeen 37 m, Sha Tin 188 m, Sai Kung 120 m).

**Why the outline is drawn as line work, not a filled polygon.** The iB1000
shoreline is published as 9,078 separate parts. Endpoint stitching closes 1,911
rings but leaves 1,828 open chains, and the largest chain spans only 0.004°
(~400 m) — the harbour mouths and open coastlines never join. A flood-fill land
mask therefore leaks through the digitising gaps: at best 22% land against an
expected ~32%, with Mong Kok, Kowloon Park and Tuen Mun reading as sea. Raising
the stitching tolerance makes it **worse** (3 m tolerance closes 843 rings, fewer
than 40 cm's 1,911), because it merges unrelated short fragments.

So the map draws the shoreline exactly as published, as line work. Nothing is
inferred, and no land polygon is claimed. The land tint under the dots comes from
the 18 LandsD district polygons, which tile the whole territory — note those
include **territorial waters**, which is why they alone would have mis-drawn the
coast. `build_land_mask.py` and `stitch_shoreline.py` are kept as the record of
what was tried and rejected.

**Labels are data-derived.** Every area label anchor is tested against
`districts.geojson` before rendering. This caught a real error: the first draft
labelled the western island "Hong Kong Island" when the point was in **Islands
District (Lantau)**, and put a second "New Territories" label in open sea.

**Encoding on the map.** Circle fill = % of bookable sessions with vacancy (8-day
window); circle outline = price band, thick blue ring for air-conditioned
($148 peak / $120 off), thin tan ring for not air-conditioned ($82 / $57); brown
triangles = the 65 free outdoor/beach courts.

`districts.geojson` doubles as a labelled basemap layer — pick `district_en` for
tooltips.

---

## Judgement calls — read before mapping

**1. The 47 NT venues assumed to be air-conditioned.** The feed names the facility
type `Volleyball Court (NT)` for all 52 NT venues and `(A/C)(Urban)` for the 49 urban
ones, but it gives no A/C flag for NT. Five NT venues say "Non-air-conditioned in Arena"
in their name and are correctly detected; the other 47 are **assumed A/C**, flagged
`ac_status_basis = assumed_default_ac`. Their price could be wrong if LCSD lists them as
non-air-conditioned. Check a venue page before quoting its charge.

**2. `court_count` is null everywhere.** LCSD's sports-centre dataset has a
`NoOfVolleyballCourts` field, but it is **empty in every one of the 106 records**, so
there is no authoritative court count for bookable indoor courts. The free outdoor
courts *do* publish counts (`no_of_courts`). Do not infer indoor counts from
`available_courts`, which is a vacancy count, not a court count.

**3. Zero-usage years set to null, not zero.** LCSD reports 0% for some venue-years.
These are artifacts, not closures: 33 are an isolated 0% between healthy years
(94% → 0% → 99%), and 1 (Tung Cheong Street, 2022) has every facility at 0% — an
un-reported year. That venue is bookable in today's live feed with 128 sessions, which
proves it was open. Affected years are listed in `usage_zero_pct_years_excluded`
across **32 venues** (23 × `2021:isolated_zero`, 10 × `2022:isolated_zero`,
1 × `2022:unreported_year`).

**4. Usage is the whole hall, not volleyball.** "Arena" is the main multi-purpose
arena that converts between volleyball, basketball and netball. It is the best proxy
available — LCSD publishes no per-sport usage — but it is **not** a volleyball-only figure.

**5. Free outdoor courts have no live data.** They are first-come first-served with no
booking feed and no hire charge, so `live_vacancy_available` is `"n/a"` and
`booking_fee_hkd` is 0. They are a separate layer rather than merged into `venues.geojson`.

---

## Suggested next step

`quicklook_map.png` already shows the headline pattern: **peak sessions are almost
unbookable (7.7% vacancy) against 19.8% off-peak**, and the free outdoor courts carry
no price and no wait. If you want a competition map, the sharpest angle is that price
gap — $148 vs $57 an hour buys availability.

---

Data © HKSAR Government (LCSD, CSDI Portal, LandsD). Terms: non-commercial with
attribution.

---

## Student worksheet

[[Student Worksheet — Volleyball Courts Booking Data]]
