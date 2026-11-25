# Population data — what every column means

Two files, both derived from the **CSDI 2021 Population Census** as served by
the CSDI portal, plus the study's own layers. Nothing here is estimated.

- `POPULATION — district_census_full.csv` — 18 rows, one per District Council
  district. The population columns are the **full C&SD field set** for the
  district layer, not just the ones this study used.
- `POPULATION — small_area_census.csv` — 211 rows, one per census small area
  (Small Tertiary Planning Unit, STPUG). Each row adds the number of study
  rooms inside that small area, so the crowding map can be recomputed from
  scratch.

## Source layers

| Layer | CSDI id | What |
|---|---|---|
| District Council districts | `censtatd_rcd_1635932856094_19982` | 18 features, 212 census fields |
| Census small areas (STPUG) | `censtatd_rcd_1635933193720_58660` | 211 features |
| Study rooms | `edb_rcd_1633320468580_185` | 194 features |
| Secondary enrolment S1–S7 | `edb_rcd_1633336508088_48919` | 22 rows (18 districts + 3 regions + total) |

## The field codes — decoded and proved, not guessed

CSDI census fields are codes. Guessing them is the single easiest way to
produce a confident, wrong map. Every code below was **proved
empirically** by `verify_field_codes.py`, which recomputes published C&SD
figures from the CSDI geometry and compares. **7 of 7 checks pass** — the full
audit is in `field_decode_audit.json`.

| Code | Meaning | How it was proved |
|---|---|---|
| `t_pop` | land-based non-institutional population | sums to **7,411,945** = C&SD's published land-based total |
| `t_wp` | working population | `t_wp + t_nwp == t_pop` in **18 of 18** districts |
| `t_nwp` | non-working population | same identity |
| `age_1` | 0–14 | band totals match C&SD tables; the residual across all five bands is exactly **−1,125** = the institutional (hospital) population, which C&SD's land-based definition requires |
| `age_2` | **15–24** | as above — this is the band used for the "students" measure |
| `age_3` | 25–44 | as above |
| `age_4` | 45–64 | as above |
| `age_5` | 65+ | as above |
| `nwp_st` | non-working **students** | `nwp_st + nwp_re + nwp_care + nwp_hm + nwp_oth == t_nwp` in **18 of 18** districts; territory total 3,731,538 on both sides |
| `nwp_re` | retired persons | same identity |
| `nwp_care` | in institutional care | same identity |
| `nwp_hm` | students living in the same household as the head (household members) | same identity |
| `nwp_oth` | other non-working | same identity |
| `fa_m` | **median floor area of accommodation, m²** | median of district medians = 41 m² vs C&SD's published territory median of 40 m² (Main Results Table 7.10 / Summary Table 6.7); also checked against 540 major housing-estate units (median 42 m², min 12, max 148) |
| `dh` | domestic households | `sum_dh` = 2,673,714 against `sum_t_pop` = 7,411,945 → **2.77** persons per household vs C&SD's published average of 2.8 |
| `pop_m` / `pop_f` / `pop_s` / `pop_pub` | male / female / single / public-scheme housing population | from the same layer |
| `mearn_xfdh_1` | median monthly earnings, 1st decile | from the same layer |
| `edu_deg` | population with a degree | from the same layer |
| `pls_same` / `plw_same` | usual residents living in the same district | from the same layer |
| `whr_1` | usual residents, 1st quartile | from the same layer |

## The two school-student measures — do not confuse them

There are **two** different populations called "students" in this data, and
they answer different questions.

| Measure | Source | Territory total | What it means |
|---|---|---|---|
| **Senior-secondary enrolment** | EDB `edb_rcd_1633336508088_48919` | S1–S7: **347,820**; S4–S6: **160,833** | actual school students, by grade and district |
| **Census "aged 15–24"** (`age_2`) | C&SD census | **591,073** | everyone aged 15–24, including students, working young people and those not in education |
| **Census "non-working students"** (`nwp_st`) | C&SD census | **1,044,577** | a broad "students" category in the census, not the same as enrolment — it counts anyone the census classifies as a non-working student |

The study uses **EDB enrolment** for the demand measure, because the brief is
about Form 4–6 (DSE) students, and **census `age_2` / `nwp_st`** for the
crowding and elderly-competition measures, because the census is the only
source that carries floor area and retirement.

**Caveat that must be stated:** "aged 15–24" is not "DSE candidates". A census
small area with many 15–24-year-olds is a crowded small area with many
potential students — it does not measure exam-season demand directly.

## The seat and utilisation figures — read the caveat

Seats (6,521) and 2025 utilisation (29.3% weighted) come from a **LegCo
reply, CSTB217 (question 3479, 2026)**. They are **public-library study
seats only**. The other 150 study rooms (sports centres, community halls) have
**no seat count and no utilisation data anywhere** — that is a data gap, not
an oversight. The admission-card applications (2,506 / 2,618 / 2,508 for
2023/24/25) are the only **direct** exam-period demand measure available.

## Re-deriving the study from these files

```
students_per_100_seats = s4_6_enrolment / seats * 100
crowding_index         = t_pop / (fa_m * households)          (per small area)
share_below_46m2       = students in small areas with fa_m < 46 / all students
weighted_utilisation   = sum(seats_d * util_d) / sum(seats_d)
```

All of these are recomputed by `district_table.py` and `crowding.py` in the
`scripts/` folder, and every published figure is checked by
`verify_published.py` (the vault recipe) and `verify_notes.py` (against the
shipped layers).
