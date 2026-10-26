---
type: worksheet
title: 'Student Worksheet — Volleyball Courts Booking Data'
project: GIS Competition — sports facilities, booking data, live vacancy
source: NPL GIS Team working dataset (LCSD CSDI + SmartPLAY open-data feed)
date: 2026-10-26T00:00:00.000Z
level: secondary (F4–F6) / competition entry
status: reproducible
---

# Student Worksheet — Volleyball Courts Booking Data

> **Your question:** *When is it easiest to get a volleyball court in Hong Kong?*

The obvious answer is "off-peak" — and the obvious answer is **wrong**. This
worksheet makes you find that out yourself, using a live government data feed.

You are given three separate sources, because **no single dataset has all three
things you need**.

---

## Part 1 — Get the data (45 minutes)

| Variable | Source | Why not the other one |
|---|---|---|
| **Live vacancy** | SmartPLAY open-data feed | CSDI has the *locations* but never publishes *current* availability |
| **Annual usage %** | CSDI `lcsd_rcd_1670389615666_788` | SmartPLAY carries no usage figures |
| **Price** | LCSD published rate card | **No dataset has it** — price is *derived* |
| **Free courts** | CSDI (see table) | Not in the SmartPLAY feed at all |

**The three CSDI layers** — paste any of them into ArcGIS Pro with *Add Data → From URL*:

| Dataset | id | Records | Notes |
|---|---|---:|---|
| Usage of Recreational and Sports Facilities by Venue | `lcsd_rcd_1670389615666_788` | 1,206 | `Facilities_EN = "Arena"` for the main hall |
| Sports Centres | `lcsd_rcd_1629267205215_31341` | 106 | independent coordinate check |
| Volleyball Courts (Free Outdoor Pitches/Courts) | `lcsd_rcd_1670383751618_95284` | 58 | free, no charge |
| Beach Volleyball Courts | `lcsd_rcd_1670383539632_8620` | 7 | free, no charge |

Pattern for all of them:
`https://portal.csdi.gov.hk/server/rest/services/common/<id>/FeatureServer/0`

> ⚠ **A field trap that breaks the download.** An explicit `outFields` list **plus**
> `outSR` returns **HTTP 400**. Use `outFields=*` instead. Paging past 3,000 rows
> needs `resultOffset`.

**The live feed** — refreshes every 5 minutes, so your numbers will be *newer* than
the working set:

```
https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/volleyball/file
```

It is a plain JSON array. Each row is one bookable session:
`Venue_Name_EN`, `District_Name_EN`, `Facility_Type_Name_EN`,
`Facility_Location_Name_EN`, `Available_Date`, `Session_Start_Time`,
`Session_End_Time`, `Available_Courts`.

> ⚠ **The feed window moves every day.** The working set in the recipe note was
> pulled on 22 Oct and covered **22–29 Oct 2026**. The same feed read on
> **26 Oct 2026** covers **26 Oct – 2 Nov 2026** — still 13,152 sessions, but a
> different set of dates. **Your percentages will not match the recipe note's
> exactly, and that is expected.** What must stay the same is the *shape* of the
> result: the last day of the window is far emptier than the days before it, and
> holding lead time constant shrinks the peak/off-peak gap. Compare your
> **structure**, not your decimals.

**The rate card** (LCSD hire charges, per hour):

| Court type | Peak | Off-peak | Concessionary peak / off-peak |
|---|---:|---:|---:|
| Indoor **with** air-conditioning | $148 | $120 | $74 / $60 |
| Indoor **without** air-conditioning | $82 | $57 | $41 / $29 |

Peak = from 18:00 Mon–Fri, from 13:00 Sat, all day Sun and public holidays.
Get the gazetted holidays from `https://www.1823.gov.hk/common/ical/en.json` so a
session on a public holiday is banded correctly.

**Count what you have:**

| | Your count | Working set |
|---|---:|---:|
| Bookable indoor venues | | 101 |
| Sessions in the 8-day feed | | 13,152 |
| Free outdoor + beach courts | | 65 |
| Sports centres (for cross-checking) | | 106 |

---

## Part 2 — Derive the price (30 minutes)

**The live feed publishes no price.** It only says how many courts are free. So you
join price on from the published rate card, by **air-conditioning status** and
**time band**.

The A/C status comes from `Facility_Type_Name_EN`:
`Volleyball Court (A/C)(Urban)` → A/C · `Volleyball Court (NT)` → **no flag** ·
`Volleyball Court (Urban)` → not A/C.

> ⚠ **The assumption you must declare.**
> **47 of the 52 New Territories venues have no A/C flag in the feed.** They are
> *assumed* A/C. If LCSD lists one as non-air-conditioned, its price is wrong by up
> to $66/hour. Flag every one of them (e.g. `ac_status_basis = assumed_default_ac`)
> and **state it in your write-up**.

**Your working:**

| A/C status | Venues |
|---|---:|
| air-conditioned | |
| not air-conditioned | |
| of which **assumed** (no flag in feed) | |

Region split: **49 urban, 52 New Territories.** Does your data agree?

---

## Part 3 — The trap (45 minutes)

**Do this the naive way first.** Split the 13,152 sessions by price band and work
out the percentage with any vacancy:

| Band | Sessions | With vacancy |
|---|---:|---:|
| Peak | | |
| Off-peak | | |

Now write the conclusion the naive numbers suggest:

______________________________________________________________

**Now test it.** Split the *same* sessions by **how far ahead** they are booked.
The feed window is 8 days, so lead time runs 0 to 7 days.

| Lead time | Sessions | Already fully booked | With vacancy |
|---:|---:|---:|---:|
| Today | | | |
| +1 day | | | |
| +2 days | | | |
| +3 days | | | |
| +4 days | | | |
| +5 days | | | |
| +6 days | | | |
| +7 days | | | |

**What do you see?** The answer is in this shape — fill it in from your own run.

*Reference: the same feed read on **26 Oct 2026** (window 26 Oct – 2 Nov). Your
numbers will differ in the decimals but should match in the shape.*

| Lead time | Sessions | Already fully booked | With vacancy |
|---:|---:|---:|---:|
| Today (+0) | 1,644 | 97.6% | 2.4% |
| +1 day | 1,644 | 94.8% | 5.2% |
| +2 days | 1,644 | 94.4% | 5.6% |
| +3 days | 1,644 | 92.9% | 7.1% |
| +4 days | 1,644 | 93.8% | 6.2% |
| +5 days | 1,644 | 99.3% | 0.7% |
| +6 days | 1,644 | 98.7% | 1.3% |
| **+7 days** | 1,644 | **33.2%** | **66.8%** |

| | Your numbers | Reference (26 Oct 2026) |
|---|---:|---:|
| Next 6 days, already fully booked | | 95.9% |
| A week out, already fully booked | | 33.2% |

**Now re-test the price gap with lead time held constant:**

| Lead | Peak vacancy | Off-peak vacancy | Gap (pp) |
|---:|---:|---:|---:|
| +0 | | | |
| +5 | | | |
| +6 | | | |
| +7 | | | |

**What happens to the gap?** ______________________________________________

**Why?** Write one sentence:

______________________________________________________________

---

## Part 4 — A second trap: day of week (20 minutes)

Make a day-of-week table the naive way.

| Day | Sessions | Vacancy |
|---|---:|---:|
| Mon | | |
| Tue | | |
| Wed | | |
| Thu | | |
| Fri | | |
| Sat | | |
| Sun | | |

**One of these days looks far better than all the others. Check the dates before
you believe it.** The feed window runs 8 days — how many of each weekday does that
contain? If a window starts and ends on the same weekday, that weekday is
**double-counted** and the table fabricates a pattern.

> **Rule to write in your notes:** before publishing a day-of-week table, check the
> *dates*. A percentage that crosses two different populations is an artefact, not a
> finding. Always ask: *what window does this average span?*

**Your corrected table:**

| Day | Sessions | Vacancy (after splitting the doubled day) |
|---|---:|---:|
| | | |

---

## Part 5 — Where does the vacancy sit? (30 minutes)

Join `sessions.geojson` to the **18 District Council districts** on `district_en`,
then *Summarize* to get vacancy per district. Count venues and free courts per
district too.

| District | Venues | Free courts | Sessions | Vacancy |
|---|---:|---:|---:|---:|
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |

**The geographic question to answer:** where is public sports provision **free and
uncrowded**, and where is it **scarce and contested**? That is a clean HK
settlement question and it makes a good competition entry.

> ⚠ **The confound to check.** The emptiest districts may also have the **lowest
> usage figure**. A district with only 4 venues has a small `n`, and LCSD's usage
> covers the **whole arena** — a multi-purpose hall that switches between
> volleyball, basketball and netball — not volleyball alone. Check the sample size
> before you make a claim about it.

---

## Part 6 — The map that tells the story (30 minutes)

The single most persuasive frame is a **timeline**, not a choropleth.

1. Symbolise `sessions.geojson` by `session_date`.
2. Play the timeline. **Watch the wave of bookings move in.**

**Design notes**
- Circle fill = % of bookable sessions with vacancy.
- Circle **outline** = price band (thick ring = air-conditioned, thin = not).
- Brown triangles = the 65 free outdoor / beach courts.
- Use `districts.geojson` as your basemap polygon layer, with `district_en` labels.
  **Do not draw a coastline by hand.**
- Label only the extremes — **not** all 101 venues.

**Your map question, in one line** (this goes in the title):

______________________________________________________________

---

## Part 7 — Write it up (45 minutes)

**Data validation statement:**

> *Datasets: SmartPLAY live vacancy feed (JSON, refreshes every 5 minutes, window
> [start]–[end], 13,152 sessions) · Usage of Recreational and Sports Facilities by
> Venue (CSDI id `lcsd_rcd_1670389615666_788`, LCSD, 1,206 rows) · Sports Centres
> (`lcsd_rcd_1629267205215_31341`, 106) · Volleyball Courts Free Outdoor
> (`lcsd_rcd_1670383751618_95284`, 58) · Beach Volleyball Courts
> (`lcsd_rcd_1670383539632_8620`, 7). Retrieved [date]. Count parity served vs
> downloaded: [fill in]. Fields used: [list]. Derived fields: [list — `ai_` prefix
> where AI-assisted].*

**Headline finding, in one sentence.** Use the shape from Part 3, not the naive
answer:

______________________________________________________________

**Your limitations — at least four, from this list:**

| # | Limitation | Why it matters |
|---|---|---|
| 1 | Price is **derived** from the rate card, not observed; 47 NT venues assume A/C | |
| 2 | Usage is **whole-arena**, not volleyball | |
| 3 | Usage data **stops at 2022** | |
| 4 | **32 venues have an excluded 0% year** (reported as `null`, not 0%) — isolated zeros between healthy years (94% → 0% → 99%) or whole-year non-reports | |
| 5 | **No court counts** — `NoOfVolleyballCourts` is empty in all 106 records; `available_courts` is a *vacancy* count, not a court count | |
| 6 | **One snapshot, 8 days** — all figures for that window | |
| 7 | Free courts have **no live feed** (first-come first-served) | |

---

## Part 8 — Make it yours

| Option | What you would do |
|---|---|
| **A. Fair-share finder** | Which district has the worst ratio of *free* courts to population? |
| **B. Peak-hour targeting** | Which venues still have off-peak slots free at 19:00 on a weekday? Who loses out? |
| **C. Your own** | ______________________________ |

**The AI angle.** Use AI where it is genuinely useful — writing the session classifier,
interpreting the lead-time table, drafting captions — then **declare it**: which tool,
what it did, how you verified the output. Prefix any AI-inferred field with `ai_`.

---

## Checklist

- [ ] Live feed pulled and counted; CSDI layers loaded from the service URLs
- [ ] CSDI id recorded; count parity checked (served vs downloaded)
- [ ] Price derived from the rate card; `price_band_reason` written for every session
- [ ] The 47 assumed A/C venues flagged and declared
- [ ] Naive peak/off-peak gap calculated **first**
- [ ] Lead-time split done; gap re-tested at fixed lead time
- [ ] Day-of-week table checked against the actual dates
- [ ] District table built; the small-`n` confound checked
- [ ] Timeline map built
- [ ] Data validation statement written
- [ ] At least four limitations declared
- [ ] AI statement written, `ai_` fields prefixed

---

## Where the working files are

| What | Where |
|---|---|
| Full recipe | [[Volleyball Courts — CSDI & SmartPLAY Data and ArcGIS Recipe]] |
| Layer and method notes | `NPL GIS Team/GIS Projects/NOTES.md` |
| Re-fetch script | `NPL GIS Team/GIS Projects/fetch_raw.sh` |
| Build script | `NPL GIS Team/GIS Projects/build_geojson.py` |
| Check script (9/9 checks must pass) | `NPL GIS Team/GIS Projects/analyse_volleyball.py` |
| Cached GeoJSON layers | `NPL GIS Team/nplgis/assets/data/volleyball/` |
| Full repository | <https://github.com/davidtwmak-maker/NPLGIS> |

---

*Data © HKSAR Government (LCSD, CSDI Portal). Terms: non-commercial with attribution.*
