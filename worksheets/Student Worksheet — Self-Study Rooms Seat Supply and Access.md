---
type: worksheet
title: 'Student Worksheet — Self-Study Rooms: Seat Supply, Student Demand and Walking Access'
project: GIS Competition — DSE study-seat demand, supply and access
source: NPL GIS Team working dataset (EDB + C&SD CSDI layers + LegCo reply CSTB217)
date: 2026-11-24T00:00:00.000Z
level: secondary (F4–F6) / competition entry
status: reproducible
---

# Student Worksheet — Self-Study Rooms: Seat Supply, Student Demand and Walking Access

> **Your question:** *Can Hong Kong's study rooms serve the students taking the DSE, and do elderly users take them?*

The obvious answer is "yes, there are enough seats" — and the obvious
*analysis* of that question is **wrong in a way that looks impressive**. This
worksheet makes you find that out yourself.

You are given four separate sources, because **no single dataset has both the
demand side and the supply side**.

---

## Part 1 — Get the data (45 minutes)

| Variable | Source | Why not the other one |
|---|---|---|
| **Where the rooms are** | EDB `edb_rcd_1633320468580_185` "Study Room" | The only layer listing all 194 rooms |
| **How many seats, how busy** | LegCo reply **CSTB217** (Q. 3479, 2026) | No dataset carries seat counts or utilisation |
| **How many students** | EDB `edb_rcd_1633336508088_48919` enrolment by district and grade | Census age bands are not school cohorts |
| **Smallest living area** | C&SD 2021 Census `censtatd_rcd_1635933193720_58660` (STPUG) | Nothing else carries floor area |

**The CSDI layers** — paste any into ArcGIS Pro with *Add Data → From URL*:

| Dataset | id | Records | Notes |
|---|---|---:|---|
| List of Study Room | `edb_rcd_1633320468580_185` | 194 | points; `SEARCH02_EN` = district; `LASTUPDATE` = 2024–2026 |
| Student Enrolment in Secondary Day Schools by District and Grade | `edb_rcd_1633336508088_48919` | 22 | `S1`–`S7`; 18 districts + 3 regions + total |
| 2021 Census, Small Tertiary Planning Units | `censtatd_rcd_1635933193720_58660` | 211 | `fa_m` = median floor area; `nwp_st` = students; `age_2` = 15–24 |
| 2021 Census, District Council Districts | `censtatd_rcd_1635932856094_19982` | 18 | join layer |
| Aided / DSS / Private / Government / Caput Secondary Schools | `edb_rcd_1629267205213_53323` and 4 more | 514 | the demand origin points |
| 3D Pedestrian Network | `landsd_rcd_1637222018065_52265` | 465,892 | for real walking distance |

Pattern for all of them:
`https://portal.csdi.gov.hk/server/rest/services/common/<id>/FeatureServer/0`

> ⚠ **A field trap that breaks the download.** An explicit `outFields` list **plus**
> `outSR` returns **HTTP 400**. Use `outFields=*` instead. Paging past 3,000 rows
> needs `resultOffset`.

**The LegCo reply** — the only place with seat counts:
`https://www.legco.gov.hk/yr2025/english/counmtg/agenda/cm20260626.pdf`
Controller's Reply to Question Serial No. 3479, 24 Jun 2026. The **Annex**
gives seats and average hourly utilisation for 2023, 2024 and 2025 for all 18
districts. Read it out of the PDF and type it into a spreadsheet — you will
need it in every later part.

---

## Part 2 — Decode the census fields before you use them (30 minutes)

CSDI census fields are codes. Guessing them is the easiest way to produce a
confident, wrong map. Check each of these yourself against the C&SD published
figures before you go further:

| Code | Claim | Check you should make | Result |
|---|---|---|---|
| `t_pop` | land-based non-institutional population | does it sum to **7,411,945**? | ✅ |
| `age_1`…`age_5` | 0–14 / 15–24 / 25–44 / 45–64 / 65+ | do the bands sum to `t_pop`, and is the gap the institutional population? | ✅ residual = 1,125 |
| `t_wp` + `t_nwp` | working + non-working | does it equal `t_pop` in every district? | ✅ 18/18 |
| `nwp_st` | non-working students | does `nwp_st + nwp_re + nwp_care + nwp_hm + nwp_oth` equal `t_nwp`? | ✅ 18/18 |
| `dh` | domestic households | people ÷ households ≈ **2.8**? | ✅ 2.77 |
| `fa_m` | median floor area (m²) | median of district medians ≈ **40 m²**? | ✅ 41 m² |

> ⚠ **`fa_m` is a MEDIAN of household floor areas**, not per-capita area and not
> a student-level measurement. Say so in your write-up.

---

## Part 3 — The trap (45 minutes)

> **Your question:** *are busy districts also the districts with lots of elderly people?*

Build the two ratios you would naturally build, then correlate them:

| Correlation | Your r |
|---|---|
| students per 100 seats vs retired persons per seat | **+0.866** ← a spectacular result! |

That +0.866 is **completely spurious**, and this is the single most important
thing in the project. Both ratios have **seats in the denominator**, so a
district with few seats scores high on both sides regardless of what is
happening inside it. Tsuen Wan has 162 seats — it wins both ratios.

**Now do it properly.** Use counts, not ratios:

1. Regress utilisation on students and retired together.
2. Compute partial correlations: utilisation ~ students *given* retired, and
   utilisation ~ retired *given* students.

| Test | Your result | Expected |
|---|---|---|
| r(students per 100 seats, retired per seat) | | +0.866 (spurious) |
| partial r: utilisation ~ retired, given students | | **−0.13** |
| partial r: utilisation ~ students, given retired | | **+0.27** |
| Regression coefficient on retired (per 1,000) | | −0.064, CI includes 0 |
| Regression coefficient on students (per 1,000) | | +1.29, CI includes 0 |
| Adjusted R² | | **−0.02** |

**What to say**

> There is no evidence that elderly users crowd students out. Once the shared
> denominator is removed, retired persons have a partial correlation of −0.13
> with utilisation — wrong sign, and not significant. The apparent +0.87 was an
> artefact of dividing both by the same seat count.

> ⚠ With n = 18 and adjusted R² of −0.02, this is a **negative result** — "we
> looked and did not find it" — not proof that no effect exists. Write it that way.

---

## Part 4 — Where are the students, and where are the seats? (30 minutes)

Build the district table: S4–S6 enrolment, seats, students per 100 seats,
2025 utilisation, retired, median floor area.

| District | S4–S6 | Seats | per 100 seats | Util 2025 |
|---|---:|---:|---:|---:|
| Tuen Mun | 11,049 | 174 | 6,350 | 45.8% |
| Kowloon City | 14,409 | 322 | 4,475 | 27.1% |
| Tai Po | 7,009 | 200 | 3,505 | 41.1% |
| Yuen Long | 13,997 | 428 | 3,270 | 44.2% |
| Sha Tin | 16,283 | 564 | 2,887 | 38.8% |
| … | | | | |
| Sham Shui Po | 9,435 | 578 | 1,632 | 30.5% |
| Islands | 2,906 | 236 | 1,231 | 17.8% |

Territory: 160,833 students · 6,521 seats · 2,466 per 100 seats · weighted
utilisation **29.3%**.

**Two findings, and they pull in opposite directions:**

1. **The seats are not full.** Even the busiest district averages under 46%
   hourly utilisation. Demand is met on average.
2. **But they are in the wrong places.** A 5.2× spread between Tuen Mun and
   Islands. And check the **exam-period** measure in the LegCo reply:
   admission-card applications were 2,506 / 2,618 / 2,508 for 2023/2024/2025 —
   about **38.5%** of the 6,521 seats, and **flat** across three years.

> ⚠ The seats and utilisation are **public-library only**. The 150
> community-centre and NGO rooms have **no published seat count**, and the 26
> temporary sports-centre rooms have **no utilisation data at all**. Any claim
> about total Hong Kong capacity that ignores these is understating supply.

---

## Part 5 — The smallest living area (40 minutes)

Now the part your brief asks for: **how small is the home the student shares,
and is there a study room near it?**

Use the 211 census small areas (STPUG):

1. Territory median of `fa_m` across the 211 small areas → **46 m²**.
2. Count the small areas below it, and the students and study rooms inside them.
3. **Test the threshold** — does the answer depend on where you cut?

| Threshold | Small areas | Students | % of students | Rooms |
|---|---:|---:|---:|---:|
| < 35 m² | 37 | 219,645 | 21.0% | 45 |
| < 40 m² | 66 | 425,739 | 40.8% | 112 |
| < 45 m² | 102 | 716,908 | 68.6% | 165 |
| **< 46 m²** | **105** | **743,605** | **71.2%** | **169** |
| < 60 m² | 148 | 925,871 | 88.6% | 188 |

The pattern is robust to the threshold. Then find the sharpest cases — the
smallest accommodation carrying the most students:

| Small area | District | m² | Students | Rooms |
|---|---|---:|---:|---:|
| 266 | Sham Shui Po | 23 | 7,260 | **0** |
| 267 | Sham Shui Po | 23 | 5,392 | **0** |
| 755 | Sha Tin | 30 | 13,192 | 1 |
| 286 | Kowloon City | 30 | 7,720 | **0** |

**128 of the 211 small areas contain no study room at all.**

---

## Part 6 — Straight lines lie (45 minutes)

This is where the project earns its marks.

**First**, measure school → nearest study room **in a straight line**, at
400 m, 600 m, 800 m, 1,000 m and 1,500 m. (ArcGIS Online *Summarize Nearby*,
or ArcGIS Pro *Distance Matrix* with the "Straight Line" travel model.)

**Then** measure the **real walk** on the LandsD 3D Pedestrian Network:
465,892 features → ~1.42 million nodes, then Dijkstra from all 514 schools.

| | 400 m | 600 m | 800 m | 1,000 m | 1,500 m |
|---|---:|---:|---:|---:|---:|
| **Real walk** | **159** | 292 | 382 | 436 | 484 |
| Straight-line | 295 | 394 | 453 | 483 | 494 |

**Straight-line overstates access by 86% at 400 m.** Median detour factor 1.44,
max 5.41.

| School | Straight | Real walk | Detour |
|---|---:|---:|---:|
| Po Kok Secondary School | 113 m | 610 m | ×5.41 |
| Po Chiu Catholic Secondary School | 102 m | 495 m | ×4.84 |
| Hong Kong Bluebell College | 313 m | 1,446 m | ×4.62 |

> ⚠ Four schools could not be routed (their snap point sits on an isolated
> piece of the network). Report them as unreachable — **not** as "no room
> nearby".

> ⚠ If you use straight-line distance because the network is heavy, write
> "within 400 m in a straight line" and treat it as an **upper bound on
> access**. Never let it stand as a walking claim.

---

## Part 7 — The map that tells the story (40 minutes)

Two maps, and each must pass a QC check before you submit it.

**Map A — the supply gap.** District boundaries, graduated fill on students
per 100 seats; study rooms and secondary schools over the top.

**Map B — the crowding.** The 211 small areas, graduated on residents aged
15–24 per study room, with the 128 room-less areas hatched.

**QC checks before you call either map finished** — each of these caught a
real defect in our own working set:

- [ ] The map's north–south and east–west scale are the same on the page
      (plot in a projected CRS, or set the aspect correctly). A squashed Hong
      Kong misleads every reader.
- [ ] No text crosses a legend box border. **Measure the gap** — do not
      eyeball it.
- [ ] Legend symbols sit beside their labels; every row has a marker.
- [ ] Scale bar and north arrow are fully inside the frame.
- [ ] Only label what will not collide — 18 district labels do collide.
- [ ] The source line is complete and not cut off at the page edge.

---

## Part 8 — Write it up (45 minutes)

The recipe note's §D and §J are the model. Structure:

1. **One question**, stated crisply.
2. **The sources**, with a line on why you needed more than one.
3. **The validation statement** — dataset ids, served count vs downloaded
   count, fetch date, the field-code proofs.
4. **The finding**, with the trap you avoided.
5. **The limitations** — at least four.
6. **The AI statement** — which tool, what it did, how you verified it.
   Prefix any AI-inferred field with `ai_`.

### Limitations you must declare

| # | Limitation | |
|---|---|---|
| 1 | Seats and utilisation are **public-library only**; the other 150 rooms have no seat count | |
| 2 | The **26 temporary sports-centre rooms** have no utilisation data at all | |
| 3 | Utilisation is an **average hourly rate**, not a peak or exam-period rate | |
| 4 | "Aged 15–24" is **not** "DSE candidates" | |
| 5 | `fa_m` is a **median of household** floor areas | |
| 6 | The **2021 Census** is three years old | |
| 7 | **n = 18 districts** — weakly powered | |
| 8 | Points are **snapped to the network** (median 11 m for rooms, 26 m for schools) | |
| 9 | **Four schools could not be routed** | |

---

## Part 9 — Make it yours

| Option | What you would do |
|---|---|
| **A. Where to build the next study room** | Use the crowding map: which small areas have many students aged 15–24, the smallest floor area, and no room within 800 m? |
| **B. An exam-period timetable** | Admission-card applications run March–May. Model 2,500 applications across 6,521 seats and 18 districts — which sessions overflow? |
| **C. A fair-share index** | Build a composite score (students per 100 seats × median floor area × retired share) and rank districts. Defend every weight. |
| **D. Your own** | ______________________________ |

**The AI angle.** Use AI where it is genuinely useful — writing the regression
code, interpreting the distance bands, drafting captions — then **declare it**:
which tool, what it did, how you verified the output. Prefix any AI-inferred
field with `ai_`.

---

## Checklist

- [ ] All four sources pulled; CSDI ids recorded; served-vs-downloaded counts checked
- [ ] LegCo Annex read out of the PDF and typed into a spreadsheet
- [ ] Census field codes decoded and checked against published figures (Part 2)
- [ ] The spurious correlation calculated **first**, and then disproved
- [ ] Partial correlations and the regression computed
- [ ] District table built with all 18 districts
- [ ] Exam-period admission-card applications read out and compared to seat count
- [ ] Crowding threshold sensitivity tested, not just one cut-off
- [ ] Straight-line AND network distances computed, and the gap stated
- [ ] Unroutable schools reported as unreachable, not as zero
- [ ] Both maps built and QC-checked
- [ ] Data validation statement written
- [ ] At least four limitations declared
- [ ] AI statement written, `ai_` fields prefixed

---

## Where the working files are

| What | Where |
|---|---|
| Full recipe and method notes | `notes/hk-self-study-rooms — NOTES.md` (this repository) |
| Working folder | `~/GIS Data/HK Self Study Rooms/` |
| Raw layers | `.../raw/` — study rooms, enrolment, census small areas + districts, schools, pedestrian network |
| Published layers | `assets/data/self-study-rooms/` — study rooms, census small areas, district boundaries, and every analysis table |
| Master district table | `assets/data/self-study-rooms/district_table.csv` |
| Crowding table | `assets/data/self-study-rooms/crowding_small_area.csv` |
| Walk distances | `assets/data/self-study-rooms/network_walk.csv` |
| Competition test | `assets/data/self-study-rooms/elderly_competition_test.json` |
| Field-code audit | `assets/data/self-study-rooms/field_decode_audit.json` (7/7 checks) |
| Rebuild and verify | `scripts/self-study-rooms/build_layers.py` then `scripts/self-study-rooms/verify_notes.py` |

---

*Data © HKSAR Government (Education Bureau, Census and Statistics Department, LandsD, LCSD). Terms: non-commercial with attribution.*
