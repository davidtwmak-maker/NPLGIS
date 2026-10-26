---
type: worksheet
title: 'Student Worksheet — 3D Pedestrian Network and Covered Walkways'
project: GIS Competition — pedestrian network, covered paths
source: NPL GIS Team working dataset (CSDI 3D Pedestrian Network)
date: 2026-10-26T00:00:00.000Z
level: secondary (F4–F6) / competition entry
status: reproducible
---

# Student Worksheet — 3D Pedestrian Network and Covered Walkways

> **Your question:** *Can you walk across Hong Kong without getting wet?*

Most of Hong Kong's footpath network is open to the sky. This project asks whether
the sheltered parts — covered walkways, footbridges, indoor passages — join up into
one continuous route, or whether they are thousands of disconnected fragments.

You are given the **real network** (465,892 path segments). Your job is to find the
finding, and to prove it with numbers you can check.

---

## Part 1 — Get the data (30 minutes)

The dataset is the **3D Pedestrian Network** from the **CSDI Portal**, published by the
**Lands Department**.

| | |
|---|---|
| Dataset | 3D Pedestrian Network |
| CSDI id | `landsd_rcd_1637222018065_52265` |
| Provider | Lands Department, HKSAR Government |
| Service | `https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637222018065_52265/FeatureServer/0` |
| Layer | `PedestrianRoute` (polyline) |
| Records | **465,892** |
| Native CRS | HK 1980 Grid (EPSG:2326) |
| Portal page | <https://portal.csdi.gov.hk/geoportal?datasetId=landsd_rcd_1637222018065_52265> |

**Get it into ArcGIS Pro**

1. *Add Data → From URL* → paste the service URL above. Pro pages past the 3,000-row
   server cap by itself, so you do not need to download anything.
2. Add layer **1000** the same way — that is the **Terminal** table (669 public
   transport interchanges).
3. Open the attribute table and find these three fields. Write down what each one
   means to you:

| Field | Values | What you think it means |
|---|---|---|
| `Location` | 1, 2, 3 | |
| `WeatherProof` | 1, 2, 3 | |
| `FeatureType` | text | |

> ⚠ **The trap in this dataset.** `Location = 1` is *Outdoor*. `Location = 2` is
> *Indoor*. `WeatherProof = 1` is *Covered*, `2` is *NonCovered*, `3` is
> *Unclassified*. A path is only **sheltered** if it is indoors **or** a covered
> outdoor path. Do not assume every path is one or the other — read the values.

---

## Part 2 — Split the network (45 minutes)

Use *Layer Properties → Definition Query*, then *Export Features* for each class.

| Class | Definition query | Segments |
|---|---|---|
| Exposed to sun and rain | `Location = 1 AND WeatherProof = 2` | **380,957** |
| Covered (outdoor but sheltered) | `Location = 1 AND WeatherProof = 1` | **54,341** |
| Indoor | `Location = 2` | **25,784** |
| **Sheltered (covered + indoor)** | merge the two above | **80,125** |
| Whole network | `1 = 1` | **465,892** |

**Check your numbers before you go on.** If your counts differ from the table, stop
and find out why — a mismatch is a signal, not noise. Two usual causes: you exported
before applying the definition query, or you measured the *length* of the lines
instead of counting the rows.

**Now add a measurement.** *Add Geometry Attributes* → `GEODESIC_LENGTH` in kilometres.
Then *Summary Statistics* on the length field to get the total for each class.

**Your numbers:**

| Class | Total length (km) | % of network length |
|---|---|---|
| Exposed | | |
| Covered | | |
| Indoor | | |
| Sheltered | | |

---

## Part 3 — The hard part: do the sheltered paths join up? (60 minutes)

This is the question that makes the project interesting, and **no geoprocessing tool
does it for you**. A "sheltered chain" is a set of covered/indoor segments you can
walk through without ever stepping outside.

**The method — connected components**

1. Take the **sheltered** feature class (covered + indoor merged).
2. Treat each segment's **endpoints as nodes**. Two segments are connected if they
   share an endpoint (within **0.1 m** — snap to a grid of 0.1 m to compare).
3. Walk every segment, joining its own endpoints together, and merging the groups
   that overlap. This is a **union–find** (disjoint set) problem.
4. Each group is one chain. Count them, and add up the length of every segment in
   each group.

**The script to do it is in the vault** — `[[arcgis_sheltered_chains.py]]`. It runs in
the ArcGIS Pro Python window, adds `CHAIN_ID` and `CHAIN_KM` to your feature class,
and prints the ranking. Read it before you run it: it tells you what it expects.

**Check against the working result:**

| Check | Expected |
|---|---|
| Sheltered components (chains) | **13,373** |
| Longest chain | **10.82 km**, 985 segments |
| Where it runs | **Sheung Wan ↔ Central** |
| Interchanges it serves | Central, Hong Kong, Sheung Wan MTR + Macau Ferry bus + Central Piers 7 & 8 |

**Your results:**

| | Your run | Working run |
|---|---|---|
| Number of chains | | 13,373 |
| Longest chain (km) | | 10.82 |
| Longest chain — segments | | 985 |

**Now write one sentence answering the opening question.** Use these words somewhere:
*connected*, *fragmented*, *chain*.

______________________________________________________________

______________________________________________________________

---

## Part 4 — Why does the chain break? (45 minutes)

**Every uncovered road crossing breaks the chain.** Find where.

1. Buffer the long chains by about **1 m**.
2. *Intersect* that with the **exposed** (uncovered) network.
3. Sort the resulting link lengths **ascending**. The **shortest uncovered gap** is
   your highest-priority candidate for a new covered link.

**Your answer:** the three shortest gaps are

| Rank | Location | Gap length (m) | Why it should be covered |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |

**And one question that turns this into a real project:** what would a new covered
link cost, and who pays for it? Think about who benefits — a school, a hospital, a
MTR station, a market.

---

## Part 5 — Link the network to public transport (45 minutes)

A sheltered route is only useful if it gets you **to** somewhere. Here we test how
well the sheltered network connects to transport interchanges.

1. *Add Join* — layer `PedestrianRoute` → layer 1000 (Terminal) on `TerminalID`.
2. Definition query `TerminalID IS NOT NULL`.
3. *Dissolve* by `TerminalID` → one feature per interchange.
4. *Feature To Point* (inside) → interchange points.
5. *Near* or *Generate Near Table* from the **covered** paths to those points, with a
   **100 m** search radius.
6. *Calculate Field* (Python) to classify each interchange: **Both** / **MTR only** /
   **Bus only** / **Neither**.

**Check against the working result:**

| Interchange type | Sheltered access |
|---|---|
| MTR station | 80 / 88 testable |
| Light rail | 48 / 68 |
| Ferry | 23 / 25 |
| Bus terminus | 122 / 216 |
| **Overall** | **411 / 656 (63%)** |

> ⚠ **Two things you must declare in your write-up.**
> 1. The **100 m** threshold is a choice, not an official figure. Test it at 50 m and
>    200 m and say how the answer changes.
> 2. These are **straight-line** distances, not walking distance along the network.
> 3. **13 interchanges** (including 11 MTR stations) have **no linked segments at all**
>    in the network and were excluded. Say so, or your denominator is wrong.

**Your results at three thresholds:**

| Radius | Interchanges with sheltered access | % |
|---|---|---|
| 50 m | | |
| 100 m | | 63% |
| 200 m | | |

---

## Part 6 — Write it up (45 minutes)

The competition wants a **data validation statement**. Fill this in:

> *Dataset: 3D Pedestrian Network (CSDI id `landsd_rcd_1637222018065_52265`), Lands
> Department, via portal.csdi.gov.hk. Retrieved [date]. Records served: 465,892 /
> used: 465,892. CRS: HK1980 (EPSG:2326), reprojected to WGS84 (EPSG:4326) for
> web use. Fields used: Location, WeatherProof, FeatureType, Gradient, TerminalID,
> StreetNameEN. Derived fields: [your fields — prefix any AI-inferred field with
> `ai_`].*

**Your headline finding, in one sentence.** Not "off-peak is more available" — a
finding that *changes what someone would do*:

______________________________________________________________

**Your three limitations to declare.** (Hints: distance threshold · walking vs
straight-line · `WeatherProof` provenance varies between CEDD, LiDAR and estimation
— so spot-check about 20 segments in each district.)

| # | Limitation | Effect on your answer |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

---

## Part 7 — Extend it (your own project)

Now make it yours. Choose one:

| Option | What you would do |
|---|---|
| **A. Rainy-day route finder** | Build a web map where a user picks two points and gets the most sheltered route. Needs network analysis. |
| **B. School accessibility** | For your school, how sheltered is the walk to the nearest MTR station? Which stretch would you lobby to cover? |
| **C. Elderly care** | Find sheltered routes within 200 m of elderly centres — the people who most need them. |
| **D. Your own** | ______________________________ |

**The AI angle (this year's theme).** AI must be *integral*, not decorative. Good
uses here: writing a script to do the chain analysis, interpreting the output,
drafting captions, checking your figures against the source. Then **declare it** —
which tool, what it did, how you checked it — and prefix any AI-inferred field with
`ai_`.

---

## Checklist

- [ ] Dataset loaded from the service URL, CSDI id recorded
- [ ] Four definition queries exported, counts match
- [ ] Lengths measured in km, not row counts
- [ ] Chain analysis run, results compared with the check table
- [ ] Gap analysis done, three shortest gaps identified
- [ ] Public transport link tested at 50 / 100 / 200 m
- [ ] Data validation statement written
- [ ] Three limitations declared
- [ ] AI statement written, `ai_` fields prefixed
- [ ] Map has one clear question, a legend, readable pop-ups

---

## Where the working files are

| What | Where |
|---|---|
| Full recipe and provenance | [[Covered Walkways Project — CSDI Data and ArcGIS Recipe]] |
| Chain script | `[[arcgis_sheltered_chains.py]]` |
| Network export script | `[[export_pednet.py]]` |
| Cached GeoJSON layers | `NPL GIS Team/nplgis/assets/data/pedestrian/` |
| Full network in the GitHub repo | <https://github.com/davidtwmak-maker/NPLGIS> |
| Tool help | [[ArcGIS Online Analysis Guide for Students]] · [[CSDI Dataset Guide for Students]] |

---

*Data © HKSAR Government (Lands Department), via the CSDI Portal. Terms: non-commercial
use with attribution.*
