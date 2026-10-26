---
type: worksheet
title: 'Student Worksheet — Building Heights in 3D'
project: GIS Competition — built form, 3D city model
source: NPL GIS Team working dataset (GeoInfo Map 1:1000 topographic database)
date: 2026-10-26T00:00:00.000Z
level: secondary (F4–F6) / competition entry
status: reproducible
---

# Student Worksheet — Building Heights in 3D

> **Your question:** *What does a city look like when you can see its height?*

A flat choropleth of building height is hard to read — it is a number painted on a
map. A **3D block model** shows the skyline: where the towers are, where the
low-rise stretches are, and how the two interlock. This worksheet builds one from
government topographic data.

**There is a worked example to look at first:**
[[Sham Shui Po — Building Heights in 3D]] (in the `3D Buildings` folder — a video
and a hero image).

---

## Part 1 — The data (30 minutes)

| | |
|---|---|
| Dataset | **LSGI 1:1000 Topographic Database — buildings** (`B1K_Bldg`, layer 4) |
| Provider | **Lands Department, HKSAR Government** (GeoInfo Map) |
| Service | `https://www.map.gov.hk/arcgis/rest/services/rGeoInfoMap/rgeo_highlight_d00/MapServer/4` |
| Records | **342,424** buildings territory-wide |
| Geometry | Polygon |
| Native CRS | Hong Kong 1980 Grid (EPSG:2326) |

**The three fields that matter:**

| Field | Meaning |
|---|---|
| `BUILDINGID` | the building's unique id |
| `BASELEVEL` | the level of the building's base (metres, HK1980 datum) |
| `ROOFLEVEL` | the level of the building's roof (metres) |

**Height = ROOFLEVEL − BASELEVEL.** That is the whole model.

> ⚠ **Three traps before you start.**
> 1. The service returns **1,000 records per request**. You must **page** through
>    it (`resultOffset`) — a single request gives you 1,000 of 342,424 and no
>    error to tell you so.
> 2. Some buildings have **no height recorded**. They are not zero-height
>    buildings; they are buildings of **unknown** height. Report them separately.
> 3. `CERTAINTY` and `DATASOURCE` fields exist — height certainty flags are
>    **not** filtered in the worked example. Say so.

**Your first pull — how many records did you get?**

| | |
|---|---:|
| Records in one request (no paging) | |
| Records after paging | 342,424 |
| Buildings with both BASELEVEL and ROOFLEVEL | |
| Buildings with no usable height | |

---

## Part 2 — Pick your district and clip (45 minutes)

**Your district:** ____________________ (Sham Shui Po is the worked example)

**A. Get the district boundary.** The District Council district boundaries are in
GeoInfo Map as `LND_DC_POLY_SDO` (layer 119 in `rgeo_highlight_d00`), or from the
**2021 Population Census** (`DC_ENG = "Sham Shui Po"`, code F).

**B. Find the buildings.** The working set queried the **bounding box** first
and then kept only buildings whose footprint fell **inside** the boundary:

> *11,182 buildings queried in the district bounding box → 5,690 inside the
> boundary.*

**Why the two-step matters:** a bounding box always contains buildings from
neighbouring districts — the Kowloon Tong side of the boundary, the harbour, the
neighbouring Kowloon City area. If you count the box contents as "Sham Shui Po",
you are over-counting. Clip properly.

**C. Filter the heights.** Keep heights where **1 m ≤ ROOFLEVEL − BASELEVEL ≤ 600 m**.

| Check | Working set (Sham Shui Po) | Your district |
|---|---:|---:|
| Buildings queried in the bounding box | 11,182 | |
| Buildings inside the boundary | 5,690 | |
| With recorded heights | 5,373 (94.4%) | |
| Without (drawn flat) | 317 | |

**Your counts:**

| | Your numbers |
|---|---:|
| Buildings inside the boundary | |
| With usable height | |
| Percentage with height | |
| Without height | |

---

## Part 3 — The statistics (30 minutes)

Now compute the height distribution. This is where the interesting numbers are.

| Statistic | Working set (Sham Shui Po) | Your district |
|---|---:|---:|
| Median height | 19 m | |
| 75% of buildings are at or below | 29 m | |
| 1 in 10 exceeds | 41 m | |
| Tallest | 159 m | |
| Under 10 m | 1,777 (33.1%) | |
| Over 80 m | 196 | |
| Over 41 m | 529 (9.8%) | |

**What does a median of 19 m tell you about the district?** ____________________

______________________________________________________________

**The 75% line is the more useful number.** If three-quarters of the district is
29 m or shorter, then the tall buildings are the *exception*, and the district's
character is set by the low-rise majority. What does that suggest about the age
and the land use of the area?

______________________________________________________________

---

## Part 4 — Build the 3D model (60 minutes)

**A. Extrude.** In ArcGIS Pro: *Layer Properties → 3D Model → Extrusion* → set
**height from expression** to `ROOFLEVEL - BASELEVEL`.

**B. Symbology.** The worked example colours blocks by height — **darker roof =
taller**. Keep the ramp **sequential** (one hue, increasing value). Do **not** use
a rainbow ramp: it implies categories that do not exist.

**C. The ground.** The worked example draws the ground **flat** — the figure shows
*building* height, not terrain. That is a deliberate choice and you must say so:

> ⚠ **The ground is drawn flat — the figure shows *building* height, not terrain.**

If you add real terrain, you are making a different claim. Both are legitimate,
but the caption must match. In Sham Shui Po, the difference is large: the district
sits on a **hillside**, so a flat ground plane puts hillside buildings visually
higher than they are.

**D. The buildings with no height** are drawn as **flat white footprints**. They
are the most honest possible representation: *we do not know*.

**Your model — describe what you made:**

| | |
|---|---|
| District | |
| Buildings extruded | |
| Drawn flat (no height) | |
| Ground | flat / terrain |
| Vertical exaggeration used | |
| Software | |

---

## Part 5 — Read the model (30 minutes)

This is the analysis step, and it is where the marks are. The worked example gives
you three questions:

**1. Find the 80 m + blocks. Which parts of the district do they cluster in, and
why there?**

| | Your answer |
|---|---|
| Where they cluster | |
| Why there | |

Think about: land value, plot size, proximity to transport, history (redevelopment
timing), planning controls.

**2. The sub-10 m blocks — what pattern do they follow across the district?**

| | Your answer |
|---|---|
| The pattern | |
| What produces it | |

**3. Give one way this 3D view shows the height pattern more clearly than a flat
choropleth — and one way it hides it.**

| | |
|---|---|
| **Shows better** | |
| **Hides** | |

> The hiding answer is usually about **occlusion**: a tall block in front hides the
> low-rise behind it. That is a real limitation of 3D, and saying so is a sign of
> understanding, not weakness.

---

## Part 6 — Write it up (45 minutes)

**Data validation statement:**

> *Dataset: LSGI 1:1000 Topographic Database — buildings (`B1K_Bldg`, layer 4),
> provider Lands Department, HKSAR Government (GeoInfo Map ArcGIS REST service
> `rgeo_highlight_d00`), queried [date]. District boundary: [source, e.g. 2021
> Population Census, District Council district, DC_ENG = "[your district]"]. Counts:
> [n] buildings queried in the district bounding box → [n] inside the boundary;
> heights kept where 1 m ≤ ROOFLEVEL − BASELEVEL ≤ 600 m. Geometry: Hong Kong 1980
> Grid (EPSG:2326); figure drawn on a local equidistant plane at the district
> centre. Known limits: [n] buildings without recorded heights drawn flat; ground
> terrain [not modelled / modelled]; height-certainty flags not filtered.*

**Headline finding, in one sentence:**

______________________________________________________________

**Your limitations — pick at least four:**

| # | Limitation | Effect on your answer |
|---|---|---|
| 1 | **[n]%** of buildings have **no recorded height** and are drawn flat | |
| 2 | The **ground is flat** — the figure shows building height, not terrain | |
| 3 | **Height-certainty flags are not filtered** — some heights are estimates | |
| 4 | `ROOFLEVEL − BASELEVEL` is **roof-to-base**, not floor count or occupied height | |
| 5 | A **bounding box** contains neighbouring districts — the clip must be exact | |
| 6 | The service **pages 1,000 at a time**; an unpaged pull silently truncates | |
| 7 | The model shows **the building stock, not the people** — density is a different variable | |

---

## Part 7 — Make it yours

| Option | What you would do |
|---|---|
| **A. Two districts side by side** | Sham Shui Po (old, dense, low-rise) against a new town (Tseung Kwan O, Tuen Mun) — same technique, different story. |
| **B. Add terrain** | The working set drew the ground flat. Add real terrain and describe what changes. |
| **C. Change over time** | GeoInfo Map has **historical map sheets** from 1889 to 1970. Put an old sheet under the modern 3D model and describe the change. |
| **D. Your own** | ______________________________ |

**The AI angle.** Use AI to write the paging script, to interpret the height
distribution, or to draft the captions. Then **declare it** and prefix any
AI-inferred field with `ai_`.

---

## Checklist

- [ ] Dataset loaded from the service URL, paged to the full count
- [ ] District boundary obtained and the clip done **exactly**, not by bounding box
- [ ] Height filter applied; buildings with no height reported separately
- [ ] Median, 75th percentile, 90th percentile and tallest computed
- [ ] 3D model extruded with a **sequential** colour ramp
- [ ] Ground: flat or terrain — and the caption says which
- [ ] All three reading questions answered
- [ ] Data validation statement written
- [ ] At least four limitations declared
- [ ] AI statement written, `ai_` fields prefixed

---

## Where the working files are

| What | Where |
|---|---|
| Worked example | [[Sham Shui Po — Building Heights in 3D]] (`3D Buildings/` folder) |
| GeoInfo Map cache and endpoints | `NPL GIS Team/nplgis/notes/geoinfo — NOTES.md` |
| Historical map sheets | `NPL GIS Team/Maps/GeoInfo Map/historical_maps/` (21 sheets, 1889–1970) |
| Full repository | <https://github.com/davidtwmak-maker/NPLGIS> |
| Tool help | [[ArcGIS Online Analysis Guide for Students]] · [[CSDI Dataset Guide for Students]] |

---

*Data © HKSAR Government (Lands Department), non-commercial use with citation. Base
map © Esri, HERE, Garmin, © OpenStreetMap contributors.*
