---
type: worksheet
title: 'Student Worksheet — 15-Minute Walk Catchment'
project: GIS Competition — accessibility, walking catchment
source: NPL GIS Team working dataset (CSDI FEHD licences + OpenStreetMap network)
date: 2026-10-26T00:00:00.000Z
level: secondary (F4–F6) / competition entry
status: reproducible
---

# Student Worksheet — 15-Minute Walk Catchment

> **Your question:** *What can you reach from a school in 15 minutes on foot?*

This is the workhorse of urban geography: turn a walking time into a **catchment**,
then ask what a place inside it actually gives you. The method is short; the traps
are in the assumptions, so this worksheet is mostly about the assumptions.

---

## Part 1 — The worked example

The NPL GIS Team ran this for **Po Leung Kuk Ngan Po Ling College** (PLK Ngan Po Ling
College), To Kwa Wan.

| | |
|---|---|
| School | 26 Sung On Street, To Kwa Wan |
| Point | 22.3127775, 114.1901041 (WGS84) |
| **Answer** | **497 licensed restaurants** of 2,654 in the study area |
| Tool | QGIS 4.2.3 headless (`qgis_process`) |
| Analysed | 10 Oct 2026 |

**Your version:** pick a place near you — your school, your home, a MTR station, a
market — and run the whole thing yourself.

| | Your place |
|---|---|
| Name | |
| Address | |
| Point (lon, lat) | |
| Why this place is interesting | |

> Use the **Nominatim** geocoder to find the point, and **check the result against
> the address on the school's or venue's own website**. A geocoder that returns the
> right street but the wrong building will silently shift your whole catchment.

---

## Part 2 — The three inputs

| Layer | Source | Notes |
|---|---|---|
| Your point | Nominatim geocode, checked against the official address | 1 point |
| Restaurants | CSDI **FEHD Restaurant Licences** `fehd_rcd_1630036390312_58893` | 17,283 territory-wide; attributes include `restaurant_name` (in `NSEARCH03_EN`), licence type, address EN/TC, district, licence expiry |
| Walking network | OpenStreetMap via **Overpass API** | foot-accessible road types, `foot!=no`; split per segment for exact junction connectivity |

**All processing in EPSG:2326 (HK1980 Grid), metres.**

> ⚠ **The FEHD field trap.** `LATITUDE` and `LONGITUDE` are **string** fields.
> Spatial envelope queries work fine, but a **numeric `where` on them fails
> silently**. Also, `restaurant_name` lives in the `NSEARCH03_EN` field —
> `NAME_EN` is only the licence *category* ("General Restaurant"), not the shop's
> name.

**Your counts:**

| | Your count |
|---|---:|
| Restaurants in the study area (bbox) | |
| Walk network segments | |

---

## Part 3 — Build the catchment (45 minutes)

**Three steps, in this order.** Skipping the middle one is why people get answers
that are too big.

**Step 1 — Service area (network distance)**
- QGIS: `native:serviceareafrompoint`
- Network = the OSM segments, Start = your point, Strategy = **Shortest**,
  Travel cost = **1,200 m**
- Result: `reachable_15min` — the set of network edges you can actually walk to

**Step 2 — Buffer (to the shopfront)**
- QGIS: `native:buffer`, **50 m**, dissolved
- Result: `catchment_15min`
- **Why:** 50 m is roughly the walking distance from the middle of a street to a
  shopfront on the other side. Without this, a restaurant directly opposite the
  school falls *outside* the network catchment, which is obviously wrong.

**Step 3 — Extract**
- QGIS: `native:extractbylocation`, restaurants `are within` the catchment
- Result: `restaurants_15min`

**GUI equivalent:** Vector → Network Analysis → Service Area (from point) → then
Vector → Geoprocessing Tools → Buffer → Extract → Location.

**Your result:**

| | Your number | Working set (Ngan Po Ling College) |
|---|---:|---:|
| Restaurants in the study area | | 2,654 |
| Within 15 minutes | | **497** |
| As % of the study area | | 18.7% |

---

## Part 4 — Test the assumptions (30 minutes)

Your answer rests on **two numbers you chose**. A competition judge will ask about
both.

### 4a. The walking speed

15 minutes × 80 m/min (≈4.8 km/h, normal walking pace) = 1,200 m.

**Re-run at three speeds:**

| Assumed speed | Distance | Restaurants | % of study area |
|---|---:|---:|---:|
| 60 m/min (slow, elderly, wheelchair) | 900 m | | |
| 80 m/min (baseline) | 1,200 m | | 18.7% |
| 100 m/min (brisk) | 1,500 m | | |

**Why does this matter?** The first row is roughly the population that most needs
convenient access and is least able to extend their walking time. Make that point
explicitly if you use the 900 m figure.

### 4b. The 50 m buffer

| Buffer | Restaurants | % |
|---:|---:|---:|
| 0 m | | |
| 25 m | | |
| 50 m (baseline) | | |
| 100 m | | |

**Which assumption changes the answer more?** ________________________________

### 4c. Compare with 5 minutes

The working set also has a 5-minute catchment: **82 restaurants** (400 m).

| Catchment | Restaurants |
|---|---:|
| 5 minutes (400 m) | 82 |
| 15 minutes (1,200 m) | 497 |

**How fast do the choices thin out?** Calculate the ratio:

______________________________________________________________

**Look at the working set's licence types** — `restaurants_15min.csv` has a
`licence_type` column. Split your own result by type. What does the split tell you
about the neighbourhood? (General Restaurant vs Light Refreshment is the usual
contrast — a light refreshment licence covers only a smaller menu, so a place with
one is usually a cafe or a cha chaan teng, not a full restaurant.)

| Licence type | Count | % of catchment |
|---|---:|---:|
| | | |
| | | |
| | | |

---

## Part 5 — Make it a geographic argument (45 minutes)

A count is not yet a finding. Turn it into geography.

**1. Map it.** Points for the restaurants, a dissolved catchment polygon, your
origin point. Add a basemap.

**2. Compare two places.** Run the same analysis for a second origin. Good pairs:

| Origin type | Example | Why it is interesting |
|---|---|---|
| A **MTR station** | | Transit gives you the whole city, not one neighbourhood |
| A **public housing estate** | | Tests whether provision follows population |
| A **remote rural village** | | Tests the same question at the other end |
| A **school** | | Tests daily-life access for students |

| | Origin A | Origin B |
|---|---|---|
| Name | | |
| 15-min restaurants | | |
| As % of the study area | | |

**3. Explain the difference.** What makes one place better served than the other?
Think: density, land use mix, pedestrian route quality, topography, income, history.

______________________________________________________________

**4. Find the gaps.** Where in your study area is there a *cluster* of people with no
restaurant within 15 minutes? Use *Summarize Within* over population or school
catchments. That is the map a policy argument is built on.

---

## Part 6 — Write it up (45 minutes)

**Data validation statement:**

> *Datasets: FEHD Restaurant Licences (CSDI id `fehd_rcd_1630036390312_58893`, Food
> and Environmental Hygiene Department, via portal.csdi.gov.hk; 17,283 territory-wide,
> [n] in the study area bbox) · OpenStreetMap walking network (Overpass API, [date],
> [n] ways → [n] segments) · Origin point (Nominatim geocode of "[address]",
> cross-checked against [source]). Retrieved [date]. Processing CRS: HK1980
> (EPSG:2326), metres; network travel cost 1,200 m at an assumed 80 m/min;
> 50 m dissolved buffer. Fields used: [list]. Derived fields: [list — `ai_` prefix
> where AI-assisted].*

**Your headline finding, in one sentence:**

______________________________________________________________

**Your limitations — from this list, pick at least four:**

| # | Limitation | Effect on your answer |
|---|---|---|
| 1 | Walking speed and the 50 m buffer are **teaching assumptions**, not surveyed values | |
| 2 | OSM network completeness — minor footpaths may be **missing** | |
| 3 | **Plan-view crossings** (flyovers, footbridges without shared nodes) can be under- or over-connected | |
| 4 | FEHD licence points are **premises locations**, not shopfront entrances | |
| 5 | Licence data updated 2026-06/07; some venues may have opened or closed since | |
| 6 | No **opening hours** — a licensed restaurant closed that day still counts | |
| 7 | No **cuisine or price** data in the licence record | |

---

## Part 7 — Make it yours

| Option | What you would do |
|---|---|
| **A. The school version** | Every school in a district, ranked by how many students have no lunch option within 10 minutes. This is the shape of the 2024 award-winning project. |
| **B. The elderly version** | Same analysis at 900 m, cross-referenced with elderly centres. |
| **C. The 15-minute city** | A different place entirely — a new town, a border crossing, an island. |
| **D. Your own** | ______________________________ |

**The AI angle.** A good use: writing the walk-network splitter, or drafting the
narrative. Then **declare it** and prefix any AI-inferred field with `ai_`.

---

## Checklist

- [ ] Origin point geocoded **and cross-checked** against an official address
- [ ] Three layers loaded, FEHD string-field trap understood
- [ ] Service area at 1,200 m, then 50 m buffer, then extract — in that order
- [ ] Result compared with the 497 working figure for the Ngan Po Ling case
- [ ] Walking speed tested at 900 / 1,200 / 1,500 m
- [ ] Buffer tested at 0 / 25 / 50 / 100 m
- [ ] 5-minute and 15-minute catchments compared
- [ ] Licence types split
- [ ] Second origin analysed and the difference explained
- [ ] Data validation statement written
- [ ] At least four limitations declared
- [ ] AI statement written, `ai_` fields prefixed

---

## Where the working files are

| What | Where |
|---|---|
| Layer and method notes | `NPL GIS Team/nplgis/notes/walk-restaurants — NOTES.md` |
| Cached data | `NPL GIS Team/nplgis/assets/data/walk/` |
| QGIS project stub | `results.gpkg`, `npol_walk.qgs` (working folder) |
| Full repository | <https://github.com/davidtwmak-maker/NPLGIS> |
| Tool help | [[ArcGIS Online Analysis Guide for Students]] · [[CSDI Dataset Guide for Students]] |

---

*Data © HKSAR Government (FEHD, CSDI Portal). OpenStreetMap contributors (ODbL).
Terms: non-commercial with attribution.*
