# HK Self-Study Rooms — seat supply, student demand and walking access

**Question:** Can Hong Kong's self-study rooms serve the students taking the
DSE, and do elderly users take them?
**Answer:** **The seats are not full — they are in the wrong places.**
6,521 public-library study seats against 160,833 senior-secondary students,
weighted 2025 utilisation **29.3%**, but a **5.2× spread** in students per
100 seats (Tuen Mun 6,350 → Islands 1,231). And the crowding measure the brief
asked for is decisive: **105 of 211** census small areas fall below the
territory median floor area of **46 m²**, and **128 of 211 small areas contain
no study room at all**.
**Analysed:** 2026-11-24 · Tool: Python (numpy/scipy/matplotlib) + CSDI FeatureServer + LandsD 3D pedestrian network

---

## Inputs & provenance

Every layer was **live-probed before it was promised**, and every census field
code was **proved by recomputing published figures**, not guessed.

| Layer | Source | Records | What it carries |
|---|---|---:|---|
| Study rooms | EDB "List of Study Room" `edb_rcd_1633320468580_185` | 194 | One point per room, with name and address |
| Senior-secondary enrolment | EDB "Student Enrolment in Secondary Day Schools by District and Grade" `edb_rcd_1633336508088_48919` | 22 | S1–S7 by district, 2025/26 |
| Census small areas | C&SD `censtatd_rcd_1635933193720_58660` | 211 | Age, employment and floor-area statistics |
| District boundaries | C&SD `censtatd_rcd_1635932856094_19982` | 18 | DC districts, for the district table |
| Secondary schools | EDB (5 layers: aided, DSS, caput, govt, private) | 514 | School points, for the walk analysis |
| 3D pedestrian network | LandsD `landsd_rcd_1637222018065_52265` | 465,892 | The real walking graph |
| **Seat counts + utilisation** | **LegCo reply CSTB217** (Q. 3479, 24 Jun 2026) | 18 districts | Seats and 2023–25 utilisation |

> ⚠ **Seat counts exist in no dataset.** They come from the Government's
> written reply to LegCo Question 3479. All 18 seat counts and all 54
> utilisation figures were read out of the source PDF and verified **18/18
> exact**. Without that reply there is no supply side at all — the EDB layer
> lists where the rooms are and nothing else.

---

## Files

| File | Features | Geometry | What it is |
|---|---:|---|---|
| `study_rooms.geojson` | 194 | Point | Every study room with its name and address |
| `census_small_areas_slim.geojson.gz` | 211 | MultiPolygon | Census small areas, slimmed to the 18 attributes the analysis uses |
| `district_boundaries.geojson.gz` | 18 | Polygon | DC district boundaries |
| `sec_enrol_district_grade.csv` | 22 | — | Enrolment by district and grade (EDB publishes no geometry for this, so it ships as a table) |
| `district_table.csv` | 18 | — | The master table: enrolment, seats, utilisation, census counts, floor area |
| `crowding_small_area.csv` | 211 | — | Per small area: floor area, students, retired, study rooms |
| `network_walk.csv` | 514 | — | Every secondary school → its nearest study room, on the real network |
| `elderly_competition_test.json` | — | — | The regression and partial correlations behind the elderly finding |
| `field_decode_audit.json` | — | — | The 7 field-code proofs |
| `network_summary.json` | — | — | Distance-band counts and the route summary |
| `crowding_summary.json` | — | — | The crowding thresholds |

Maps: `assets/maps/self-study-rooms/fig_study_rooms_gap.png` (supply gap +
scatter) and `fig_crowding_small_area.png` (small-area crowding choropleth).

---

## The three findings

### 1. The elderly-competition hypothesis does not survive testing

The tempting analysis is to correlate students-per-100-seats against
retired-per-seat across the 18 districts. It returns **r = +0.866**, which
looks like a decisive finding.

**It is an artefact.** Both ratios share *seats* in the denominator, so any
district with few seats wins both — Tsuen Wan (162 seats) is the champion of
both rankings. The correlation is between two denominators, not between two
populations.

The corrected test runs on counts, not on shared-denominator ratios:

| Test | Result | Reading |
|---|---|---|
| Students per 1,000 retired | partial r = **−0.13** | Wrong sign, CI crosses zero |
| Retired persons per 1,000 students | β = **−0.064** pp | CI [−0.335, +0.469] — not significant |
| Model R² (18 districts) | 0.096, **adjusted −0.024** | Worse than the mean |
| 65+ per 1,000 students | partial r = −0.212 | Not significant |

**What to say:** there is no evidence of elderly competition. The constraint on
study rooms is **supply and distribution**, not competition from other users.
This is a failure to detect an effect, not proof of absence — n = 18.

### 2. The seats are not full, but they are unevenly placed

Weighted 2025 utilisation is **29.3%**. Exam-period admission-card
applications were **2,506 / 2,618 / 2,508** across 2023–25 — flat, and about
**38.5%** of the seat count. There is no exam-period surge in the applications.

What there *is* is a **5.2× spread** in students per 100 seats:

| District | S4–S6 students | Seats | Utilisation 2025 | Students per 100 seats |
|---|---:|---:|---:|---:|
| Tuen Mun | 11,049 | 174 | 45.8% | **6,350** |
| Kowloon City | 14,409 | 322 | 27.1% | 4,475 |
| Tai Po | 7,009 | 200 | 41.1% | 3,505 |
| … | | | | |
| Sham Shui Po | 9,435 | 578 | 30.5% | 1,632 |
| Islands | 2,906 | 236 | 17.8% | **1,231** |

Tuen Mun carries **5,119 more** senior-secondary students per 100 seats than the
Islands. The question is not "are there enough seats" — it is "are the seats
where the students are".

### 3. The "smallest living area shared by the family" measure

The brief asked for the smallest living area shared by family members, as the
demand signal. The census carries it directly: `fa_m`, the **median floor area
per household in m²**, at each of the 211 small areas.

- Territory median floor area: **46 m²**
- **105 of 211** small areas fall below it, holding **743,605 students (71.2%)**
  and only **169 study rooms** — about **4,400 students per room**
- **128 of 211** small areas contain **no study room at all**
- Tightest case: small area **266**, Sham Shui Po — **23 m²**, **7,260**
  students, **0 rooms**

The result is **not an artefact of the threshold**: it holds across cut-offs
from 35 m² to 60 m².

---

## Walking distance — why straight lines lie

The access measure is the **network**, not the straight line. Every secondary
school was routed to its nearest study room by Dijkstra on the full
465,892-feature LandsD 3D pedestrian network (1.42 M nodes).

| Band | Real walk | Straight line | Overstatement |
|---|---:|---:|---:|
| 400 m | **159** | 295 | 86% |
| 600 m | 292 | 394 | 35% |
| 800 m | 382 | 453 | 19% |
| 1,000 m | 436 | 483 | 11% |
| 1,500 m | 484 | 494 | 2% |

Median detour factor **1.44**, p90 **1.99**, max **5.41** — some schools are
five times further away on foot than the crow flies. **Four schools are not
routable at all** and are reported as unreachable, never as zero distance.

---

## The field codes — proved, not guessed

CSDI census field codes are opaque (`age_1`…`age_5`, `nwp_st`, `fa_m`).
Every one was proved by recomputing published C&SD figures, then checked
against a published total. **7/7 checks pass** (`field_decode_audit.json`).

The decisive check: the five age bands sum to the population total in **18/18**
districts, and the residual of **−1,125** is exactly the **institutional
(hospital) population**, which the land-based census definition excludes.
`age_2` is therefore **15–24** — the DSE age group. `nwp_st` is non-working
students, `nwp_re` retired, `fa_m` median floor area in m².

---

## Reproducibility

The working folder holds 12 scripts. The order that rebuilds everything:

```
python3 fetch_network.py       # pedestrian network (~7 min)
python3 analyse.py             # layer inventory + audit
python3 verify_field_codes.py  # 7/7 field-code proofs
python3 district_table.py      # 18-district master table
python3 crowding.py            # small-area crowding
python3 network_walk.py        # Dijkstra walks (~65 s)
python3 network_summary.py     # rebuild the walk summary from the CSV
python3 elderly_test.py        # regression + partial correlations
python3 make_figure.py         # figure 1
python3 make_figure2.py        # figure 2
python3 verify_published.py    # 148 checks: the note vs the regenerated outputs
```

`verify_published.py` parses the district table, the walk-band table and every
headline scalar **out of the published note** and compares them against the
CSV/JSON the scripts just wrote. It passes 148/148.

`network_walk.py` takes an optional output directory, so a verification run
cannot overwrite the published CSV:

```
python3 network_walk.py work/verify_run
```

A fresh run against the re-downloaded network produced a **byte-identical**
`network_walk.csv` and the same summary.

> ⚠ **One bug worth naming, because it is easy to repeat.** The first summary
> counted "routable" schools with `if r["detour"]`, but `detour` is `0.0` for a
> school sitting *inside* a study room (walk distance 0 m) — and `0.0` is
> falsy in Python. Two of 510 schools were silently dropped and every
> distance band was understated by two. The per-school CSV was always right;
> only the summary filter was wrong. **Define membership on the field that
> carries the meaning, never on a ratio that can round to zero.**

---

## Caveats

- **Seat counts cover public libraries only.** The EDB layer lists 194 rooms;
  26 are temporary sports-centre rooms and roughly 150 are community-centre
  and NGO rooms with **no published seat count and no utilisation data**.
- **The 26 temporary sports-centre rooms have no utilisation data at all**,
  so any utilisation-weighted figure is a library figure.
- **n = 18 districts.** Adjusted R² of −0.024. The elderly finding is a
  failure to detect an effect, not proof of absence.
- **Utilisation is a library-wide annual figure**, not an exam-period
  measurement. The admission-card applications are the only exam-period
  demand signal, and they are flat.
- **Snap distances**: study rooms median 11.3 m (max 42.0 m), schools median
  25.7 m (max 127.6 m) — a school snapped 127.6 m from the network may
  overstate its true walk distance slightly.
- The six unroutable schools are rural or on islands without a mapped
  pedestrian network; they are not necessarily unreachable in reality.
- 2021 census data is the most recent small-area release available.

---

## Related

- Student worksheet: `Student Worksheet — Self-Study Rooms Seat Supply and Access.md`
- Full recipe with the ArcGIS Pro / ArcGIS Online steps:
  `Hong Kong Self-Study Rooms — CSDI & LegCo Data and ArcGIS Recipe.md`
- Tool help: *CSDI Dataset Guide for Students*, *ArcGIS Online Analysis Guide
  for Students*

*Data © HKSAR Government (Education Bureau, Census and Statistics Department,
Lands Department, LCSD, Legislative Council). Terms: non-commercial with
attribution.*
