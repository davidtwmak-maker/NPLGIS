---
type: worksheet
title: 'Student Worksheet — MTR Fare Saver Map'
project: GIS Competition — transport, shopping mall network
source: NPL GIS Team working dataset (MTR open data + Fare Saver leaflet)
date: 2026-10-26T00:00:00.000Z
level: secondary (F4–F6) / competition entry
status: reproducible
---

# Student Worksheet — MTR Fare Saver Map

> **Your question:** *Which shopping malls are cheaper to reach by MTR, and where are
> the gaps in the network?*

Every MTR station has a "Fare Saver" list — the shopping malls that give you a
discount when you enter or exit there. The network covers **41 malls** across Hong
Kong. This project maps it, then asks a sharper question: **which large
neighbourhoods have no fare-saver mall within a short walk?**

---

## Part 1 — Get the data (45 minutes)

There is no single dataset. You need four sources, and two of them are not on the
CSDI Portal at all.

| Layer | Source | Records | Notes |
|---|---|---:|---|
| MTR lines | [opendata.mtr.com.hk](https://opendata.mtr.com.hk/data/mtr_lines_and_stations.csv) | 10 lines, 95 stops | official open data; take the first `DT` direction per line, drop the duplicate `UT` |
| MTR station coordinates | [johnleungck/MTR-Stations-Coordinates-JSON](https://github.com/johnleungck/MTR-Stations-Coordinates-JSON) | 80 stations | community-maintained — **you must add the newer stations yourself** |
| MTR line colours | [infinityMark/HK_MTR_map](https://github.com/infinityMark/HK_MTR_map) `MTRMap.js` | 10 colours | matches MTR's published line colours |
| Fare Saver list | [mtr.com.hk Fare Saver page](https://www.mtr.com.hk/ch/customer/tickets/fare_saver.html) | 41 entries | mall, designated station(s), region — **transcribe it by hand** |
| Fare Saver coordinates | OpenStreetMap **Nominatim** | 39 / 41 first pass | 2 misses need hand-pinning |

**Your counts:**

| | Your count | Working set |
|---|---:|---:|
| MTR lines | | 10 |
| Stations | | 98 |
| Fare Saver malls | | 41 |
| Geocoded on the first pass | | 39 / 41 |

> ⚠ **The geocoding trap.** Nominatim placed 2 of the 41 malls in the wrong place
> on the first pass (啟德花園購物商場, 大窩口第二商場). You must **hand-pin** those to
> the known address. Also, community-driven OSM data can put a mall 50–150 m off
> its actual reader. That is fine for station association — but say so, because it
> is not fine if your map claims to show the exact entrance.

**Which two did you have to fix, and how did you find the right place?**

| Mall | What Nominatim returned | How you corrected it |
|---|---|---|
| | | |
| | | |

---

## Part 2 — Build the map (45 minutes)

**Step 1 — Lines.** For each line, take the first direction's station sequence from
the MTR open-data CSV, look up each station's lat/lon, and write a `LineString`
GeoJSON. The polyline is **straight between stations** — no rail geometry is
published. That is the standard simplification for city-scale use.

**Step 2 — Stations.** One point per named station, WGS84.

**Step 3 — Fare Savers.** Geocode each mall by name, in **both Chinese and English**,
preferring Hong Kong results. Group by region: **Hong Kong Island** (blue),
**Kowloon** (red), **New Territories** (green).

**Step 4 — Labels.** Use a **greedy bounding-box collision solver** so labels never
overlap. (A label-placement script is in the repo — `scripts/` in the working
folder. Read how it works before you use it.)

**Check your line count against the official map.** MTR's own network map is the
reference. A line drawn on the wrong side of the harbour is a data error, not a
styling choice.

---

## Part 3 — The sharper question: where are the gaps? (60 minutes)

This is where your project becomes a project rather than a drawing.

**The question:** Hong Kong's newest large housing is in **Kowloon East** — Kai Tak,
Kowloon Bay, Diamond Hill, Choi Hung. The MTR extended there, but the **Fare Saver
network is much older**. Are there whole neighbourhoods with **no fare-saver mall
within a short walk**?

**The data you need** — small-area population and planning units, all on the CSDI
Portal (see [[CSDI Dataset Guide for Students]] §C):

| Dataset | What it gives you |
|---|---|
| 2021 Population Census — Small Tertiary Planning Units (TPU) | population by small planning unit |
| Tertiary Planning Unit (TPU) boundaries | the zone polygons |
| Projections of Population Distribution 2023–2031 | where population is heading |

**The method the team used**

1. Take the **TPU** boundaries in the study area.
2. For each TPU, find the **centroid**.
3. Estimate the **walk** to the nearest fare-saver mall and to the nearest MTR
   station.
4. Score the TPU: **large population × far from any fare-saver mall**.

The working set produced **712 candidate suggestions**, ranked, with the top
candidates sitting in the **Diamond Hill / Choi Hung / Kowloon Bay** area — TPU
281 and its neighbours, with populations around 190,000 and estimated walks of
200–550 m (2.5–6.7 minutes).

**Your run:**

| TPU | Population | Walk to nearest fare-saver (m) | Walk (min) | Nearest MTR | Distance to existing fare saver (m) |
|---|---:|---:|---:|---|---:|
| | | | | | |
| | | | | | |
| | | | | | |

**Your top 5 candidate gaps:**

| Rank | TPU | Population | Walk (min) | Nearest MTR | Why it should be prioritised |
|---:|---|---:|---:|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

**The argument.** If you were advising MTR or a mall operator, which single
location would you argue for first, and what is the population served?

______________________________________________________________

---

## Part 4 — Test your method (30 minutes)

Your ranking rests on two decisions. Test both.

**4a. The walk distance.** The working set used a straight-line estimate converted
to walking time. Try it three ways:

| Method | Top-1 TPU | Population served |
|---|---|---|
| Straight-line × 1.3 detour factor | | |
| Walking network (OSM) service area | | |
| Straight-line only | | |

**Does the ranking change?** ______________________________________________

**4b. The population measure.** Total population, or population **density**, or
population **without a car**? A TPU of 190,000 people in high-rise towers and a
TPU of 190,000 in a village are different problems.

| Measure | Top-1 TPU | Why it might be better |
|---|---|---|
| Total population | | |
| Density | | |
| Household size | | |

---

## Part 5 — Add the shopping layer (30 minutes)

A fare saver is only interesting if you know **what the mall offers** and
**whether it is any good**. The working set has an OpenRice layer for the
Kowloon East candidates — restaurant cards with name, address, district, **smile**
count, **cry** count, and a URL.

| Field | What it is |
|---|---|
| `smiles` | OpenRice "smile" votes |
| `cries` | OpenRice "cry" votes |
| `district` | district name (Chinese) |

**Your table for one candidate area:**

| Mall | Smiles | Cries | Ratio | Read on it |
|---|---|---:|---:|---|
| | | | | |
| | | | | |
| | | | | |

**What is the ratio telling you, and what is it *not* telling you?** (Think about
who reviews restaurants and why.)

______________________________________________________________

---

## Part 6 — Write it up (45 minutes)

**Data validation statement:**

> *Datasets: MTR lines and stations (Transport Department open data,
> opendata.mtr.com.hk, 10 lines / 95 stops) · MTR station coordinates
> (johnleungck/MTR-Stations-Coordinates-JSON, community-maintained, 80 stations,
> supplemented with [n] hand-added) · MTR line colours (infinityMark/HK_MTR_map) ·
> Fare Saver list (mtr.com.hk, 41 entries, transcribed [date]) · Fare Saver
> coordinates (OpenStreetMap Nominatim, 39/41 first-pass, [n] hand-pinned) ·
> Population and TPU boundaries (CSDI ids [list]). Retrieved [date]. CRS: WGS84
> (EPSG:4326). Fields used: [list]. Derived fields: [list — `ai_` prefix where
> AI-assisted].*

**Headline finding, in one sentence:**

______________________________________________________________

**Your limitations — pick at least four:**

| # | Limitation | Effect on your answer |
|---|---|---|
| 1 | Line polylines are **straight between stations** — no rail geometry is published | |
| 2 | Geocoding is **best-effort**; community OSM data can place a mall 50–150 m off its actual reader | |
| 3 | The **Fare Saver leaflet is dated** — malls enter and leave the scheme | |
| 4 | The 5-minute walk is an **estimate**, not a routed walk | |
| 5 | "Fare saver" is a **discount scheme** — being outside one does not mean a mall is unreachable | |
| 6 | The team list is **not the full Fare Saver scheme** — check the official page for the current list | |
| 7 | OpenRice review counts are **self-selected** and unrepresentative | |

---

## Part 7 — Make it yours

| Option | What you would do |
|---|---|
| **A. The full scheme** | Map all 41+ official fare savers, then find the gaps in the *whole* territory, not just Kowloon East. |
| **B. The tourist angle** | Which fare savers serve the main visitor areas, and do they cluster where tourists already go? |
| **C. The school angle** | Is there a fare-saver mall within 10 minutes of every school? |
| **D. Your own** | ______________________________ |

**The AI angle.** Use AI to write the label-collision solver, or to draft the
recommendation memo. Then **declare it** and prefix any AI-inferred field with
`ai_`.

---

## Checklist

- [ ] Four source datasets assembled; MTR open data checked against the official map
- [ ] 41 fare savers transcribed; geocoding misses hand-pinned
- [ ] Line, station, and fare-saver GeoJSON built; region grouping applied
- [ ] Label collision solver working — no overlapping labels
- [ ] Gap analysis done on TPU population; top 5 candidates ranked
- [ ] Walk-distance method tested three ways
- [ ] Shopping layer added (OpenRice); review-count bias discussed
- [ ] Data validation statement written
- [ ] At least four limitations declared
- [ ] AI statement written, `ai_` fields prefixed

---

## Where the working files are

| What | Where |
|---|---|
| Data sources and method | `NPL GIS Team/nplgis/notes/festival-walk — NOTES.md` (MTR Fare Saver section) |
| Cached data | `NPL GIS Team/nplgis/assets/data/mtr/` |
| Kowloon East candidate suggestions | `NPL GIS Team/nplgis/assets/data/mtr/kc_smtpu_suggestions.csv` |
| Full repository | <https://github.com/davidtwmak-maker/NPLGIS> |
| Tool help | [[ArcGIS Online Analysis Guide for Students]] · [[CSDI Dataset Guide for Students]] |

---

*Data © Transport Department / MTR Corporation open data; © HKSAR Government
(CSDI Portal); OpenStreetMap contributors (ODbL). Terms: non-commercial with
attribution.*
