---
type: index
title: 'Student Worksheets — GIS Projects'
date: 2026-10-26T00:00:00.000Z
topic: student worksheets
audience: students / published
status: active
---

# Student Worksheets — GIS Projects

> **Six task sheets built from the team's real GIS projects.** Each one gives
> students the **actual government data**, the **actual method**, the **check
> numbers** to verify their run against, and the **limitations** they must declare.
> Written 26 Oct 2026.

Every figure in these worksheets was **re-verified live against the source
services on 26 Oct 2026** — the CSDI Portal, the SmartPLAY feed, the GeoInfo Map
REST service, and the Esri terrain. Where a figure has drifted since the project
note was written, the worksheet says so.

---

## The six worksheets

| # | Worksheet | Project | The question students answer | Level |
|---|---|---|---|---|
| 1 | [[Student Worksheet — 3D Pedestrian Network and Covered Walkways]] | Covered Walkways | *Can you walk across Hong Kong without getting wet?* | Intermediate |
| 2 | [[Student Worksheet — Volleyball Courts Booking Data]] | Volleyball Courts | *When is it easiest to get a volleyball court?* | Intermediate |
| 3 | [[Student Worksheet — 15-Minute Walk Catchment]] | 15-min walk | *What can you reach from a school in 15 minutes on foot?* | Beginner-friendly |
| 4 | [[Student Worksheet — Festival Walk 3D Mall Model]] | Festival Walk 3D | *How do you get between floors in a mall built into a hillside?* | Advanced |
| 5 | [[Student Worksheet — Building Heights in 3D]] | 3D Buildings | *What does a city look like when you can see its height?* | Intermediate |
| 6 | [[Student Worksheet — MTR Fare Saver Map]] | MTR Fare Saver | *Which neighbourhoods have no fare-saver mall within a short walk?* | Intermediate |

**Start here:** #3 and #5 — they need the least setup. #1 and #4 are the strongest
competition entries. #2 is the best teaching project because it contains a
**deliberate trap** (the answer looks like price band; it is actually lead time).

---

## What every worksheet has

1. **The question first** — one sentence, in the student's language.
2. **Where the data comes from** — dataset, provider, CSDI id, service URL, record
   count, and the field that carries the meaning.
3. **The method, step by step**, with the *specific* tool and settings.
4. **The check numbers** — what a correct run produces, so a wrong run is caught
   instead of quietly producing a wrong conclusion.
5. **The trap** — where this dataset misleads, and how to see through it.
6. **The assumptions to test** — the numbers the student chose, re-run three ways.
7. **A data validation statement** to fill in, in the competition's own format.
8. **Limitations to declare** — a table to complete, with the real ones listed.
9. **An extension task** — four options, including "your own".
10. **The AI angle** — where AI is genuinely useful here, and the disclosure to write.
11. **A checklist** — what "done" means.
12. **Where the working files are** — so a student can see a finished example.

---

## The one rule for all of them

**A percentage that crosses two different populations is an artefact, not a
finding.** Always ask: *what window does this average span?*

This is the lesson the volleyball project taught the hardest, and it applies to
every worksheet:

- A **8-day booking feed** whose last day is nearly empty makes "off-peak is
  more available" look true when it is not about price at all.
- A **day-of-week table** from a window containing two Thursdays double-counts
  Thursday and invents a pattern.
- A **single constant elevation** for a building on a slope makes the building
  float in the air.
- **"Everything with no floor id"** is not the same as "vertical circulation" —
  it sweeps in 48 flat surfaces along with 29 real connectors.

---

## Prerequisites

| Guide | What it is for |
|---|---|
| [[CSDI Dataset Guide for Students]] | **Finding** the data — the catalogue of CSDI datasets, with tested service links |
| [[ArcGIS Online Analysis Guide for Students]] | **Analysing** it — every tool, with a 10-minute exercise on real Hong Kong data |
| [[3D Mapping Learning Resources]] | The 3D path — browser-based, no software to install |
| [[CSDI Awards 2026 — Team Project Timeline]] | The competition deadlines and the five-phase plan |

> ⚠ **Correction applied 26 Oct 2026.** Two LCSD dataset ids were swapped in the
> CSDI Dataset Guide and in the Volleyball Courts recipe note. Both are fixed, and
> both files carry a dated correction note.

---

## How these were built

- Every check number was **queried live** from the source service on 26 Oct 2026,
  not copied from the project notes.
- The Sham Shui Po building-height figures were **independently recomputed**
  from the GeoInfo Map `B1K_Bldg` layer — 5,690 buildings inside the boundary,
  median 19 m, tallest 159 m, all matching the published note.
- Where a **live feed has moved on** (the SmartPLAY booking window), the worksheet
  gives the new reference figures *and* explains why the student's own decimals
  will differ.
- Where the **source data has a trap**, the worksheet names it rather than
  letting the student fall into it.

---

## Related

- [[GIS Projects]] — the index of the groups' submitted projects
- [[CSDI Awards 2026 — Team Project Timeline]] · [[CSDI Awards 2024 — Category 2 and Category 3]]
- Working data and scripts: <https://github.com/davidtwmak-maker/NPLGIS>
