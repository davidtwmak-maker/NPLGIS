---
type: worksheet
title: 'Student Worksheet — Festival Walk 3D Mall Model'
project: GIS Competition — 3D indoor network, vertical circulation
source: NPL GIS Team working dataset (CSDI 3D Pedestrian Network + GeoInfo footprints)
date: 2026-10-26T00:00:00.000Z
level: secondary (F4–F6) / competition entry
status: reproducible
---

# Student Worksheet — Festival Walk 3D Mall Model

> **Your question:** *How do you get between floors in a shopping mall built into a
> hillside?*

Festival Walk (又一城) sits on the Kowloon Tong hillside. It has **seven levels**
— an MTR station concourse, two underground shopping levels, a ground floor on
Tat Chee Avenue, an upper ground floor, and two shopping floors above. This
worksheet rebuilds it in 3D from government data, and it is the most technical
project in the set.

**There is a live version you can look at first:**
<https://davidtwmak-maker.github.io/NPLGIS/apps/festival-walk-3d/>

---

## Part 1 — What the data actually gives you (30 minutes)

Two datasets, from two different government sources.

| Layer | Source | What it gives you |
|---|---|---|
| The **route network**, per floor | CSDI **3D Pedestrian Network** `landsd_rcd_1637222018065_52265` | polylines, split by `FloorID` |
| The **building footprint** | GeoInfo Map (map.gov.hk) `B1K_Bldg` | the mall's own polygon |

**A.** Download the pedestrian network (see
[[Covered Walkways Project — CSDI Data and ArcGIS Recipe]] for the script) and
split it by `FloorID`. The floors published for Festival Walk are:

| Floor | Meaning |
|---|---|
| `MTR_Level` | MTR station concourse |
| `LG2` | underground shopping level 2 |
| `LG1` | underground shopping level 1 |
| `G` | ground floor, on Tat Chee Avenue |
| `UG` | upper ground floor |

**Your count of route features per floor:**

| Floor | Features | Length (km) |
|---|---:|---:|
| MTR_Level | | |
| LG2 | | |
| LG1 | | |
| G | | |
| UG | | |

> ⚠ **Only five floors are published.** `1/F` and `2/F` have **no route network at
> all**. Do not invent routes for them. In the working model they are drawn as
> **schematic envelopes** and labelled as such. Say the same in your write-up.

**B.** Find the mall's own footprint in the GeoInfo `B1K_Bldg` layer
(`BUILDINGID = 1108222840` in the working set — 163 points, about **18,217 m²**).

**C.** Now find the **vertical circulation** — the lifts, escalators, stairs and
ramps that join the floors. This is the hard part, and it is the heart of the
project.

---

## Part 2 — The trap: "everything with no floor" is NOT vertical circulation (45 minutes)

The obvious way to find the vertical connectors is to take every route with **no
`FloorID`**. **Do not do that.** In the working set, that query returns **77**
features — and only **29** of them are vertical connectors.

The other **48** are **flat surfaces** that happen to have no floor: podium decks,
traffic islands, road crossings, footbridges, footways. They are at one level.
Drawing them as if they were vertical circulation turns the model into a flat
mesh — and that is exactly the mistake the working set made first.

**How to separate them properly.** The CSDI layer carries the meaning in its own
fields:

| Field | Values | Use it for |
|---|---|---|
| `FeatureType` | Escalator **8**, Lift **10**, Staircase **12**, Ramp **11** (all **Indoor**) · Footway **1**, Traffic Island **6**, Crossing **32**, Footbridge **2** (all **Outdoor**) | the primary filter |
| `Location` | 1 = Outdoor, 2 = Indoor | secondary check |
| `Gradient` | the true rise over run | confirms a slope |

**Your classification:**

| Class | Count (working set) | Your count |
|---|---:|---:|
| Escalator | 18 | |
| Lift | 8 | |
| Staircase | 2 | |
| Ramp | 1 | |
| **Genuine vertical connectors** | **29** | |
| Flat site surfaces (not vertical) | 48 | |
| **Total with no `FloorID`** | **77** | |

**Now the second half of the method — which two floors does each connector join?**
You cannot read it off the data. You **measure** it: a connector's end vertices
land at **exactly 0.00 m** from the vertices of the floor network it serves,
because the routes and the connectors share vertices.

So: for each connector, take each endpoint, find the **nearest vertex in each
floor's network**, and record the distance. The floors where that distance is
**~0 m** are the floors it joins.

| Connector | Floor A (distance) | Floor B (distance) | Rise (m) | Type |
|---|---|---|---:|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

**How many connectors span more than one floor?** ______________________

> **A lift is different from an escalator.** A lift's plan length is tiny (its
> shaft is roughly 0.1 m across in the data) but it can span three floors. An
> escalator has a real slope. Draw a lift as a **vertical shaft**, not as a line
> along its 0.1 m plan length — otherwise it looks like a dot on one floor.

---

## Part 3 — Put it in 3D (60 minutes)

Now build the scene. The working model is a web app using the **ArcGIS Maps SDK
for JavaScript 5.0** — read the live version first, then rebuild it in
**ArcGIS Pro** (3D Analyst) or your own scene.

**3a. The floor plates.** Each floor gets its own footprint, derived by buffering
that floor's own route network by **14 m**. The mall is not a rectangle — the
upper floors have **projecting wings**, and if every floor uses the same outline
the lower ones are hidden.

| Floor | Your footprint area (m²) | Notes |
|---|---:|---|
| MTR | | |
| LG2 | | |
| LG1 | | |
| G | | |
| UG | | |
| 1/F | | schematic inset envelope — no route network |
| 2/F | | schematic inset envelope — no route network |

**3b. The podium.** The building is founded into a hillside. The podium is the
**union of all seven floor footprints**, extruded from **below the terrain** up to
the G floor.

**The measurement trap.** If you pin the whole building to one constant elevation,
it **floats**. In the working set the terrain under Festival Walk's own footprint
runs from **18.9 m to 35.2 m** — a **16.3 m slope**. Pinning every floor to a
single height left the building 23–39 m in the air at the downhill end.

> **Measure, don't eyeball.** Sample the terrain **under the footprint** and take
> the **minimum**, not the mean. The minimum means it can never be buried, and the
> floor order stays monotonic.
>
> **The API trap:** the elevation layer lives in `map.ground.layers`, not
> `map.layers`. The height comes back on `res.geometry.z`, not `res.z`. And the
> REST `getSamples` endpoint uses a different field (`value`) and silently samples
> the **coarsest** DEM level — it reported a flat 57.5 m everywhere, which is
> useless for a building. Use `queryElevation` in the app.

**3c. The datum.** Where is "ground level"? Pick a **real place** and measure it.
The working set used the **Tat Chee Avenue junction at the mall** —
**33.03 m** (Esri WorldElevation3D Terrain3D). The G floor is set to **33.0 m**.

| Datum candidate | Measured height | Which did you use and why? |
|---|---:|---|
| Tat Chee Avenue junction | 33.03 m | |
| Another street vertex | | |
| Minimum terrain under footprint | 18.9 m | |
| Maximum terrain under footprint | 35.2 m | |

**3d. Vertical exaggeration.** The storey height is **schematic** — the CSDI data
gives no official floor-to-floor heights, so the model uses a **5.5 m storey
interval** and stretches it **2×** for legibility.

> ⚠ **Declare both.** "垂直高度放大 2 倍" (vertical exaggeration 2×) and the
> schematic storey height must both appear on the figure. A stretched model with
> no label is a lie.

**Your heights on the model:**

| Floor | Display height (G = 0) | Absolute elevation (m) |
|---|---:|---:|
| MTR | −16.5 m | |
| LG2 | −11.0 m | |
| LG1 | −5.5 m | |
| G | 0.0 m | 33.0 |
| UG | +5.5 m | |
| 1/F | +11.0 m | |
| 2/F | +16.5 m | |

**3e. Labels.** Seven floor labels plus one for the vertical circulation, and they
**must not overlap**. The working solution: one layer per label, explicit z on
every point, a screen-space offset, and a **fan-out** that spreads labels whose
*rendered* positions are too close. Measure separation in **rendered pixels**, not
in geometry.

| Label pair | Minimum rendered separation (px) | Overlapping? |
|---|---:|---|
| MTR / LG2 | | |
| LG2 / LG1 | | |
| LG1 / G | | |
| G / UG | | |
| UG / 1/F | | |
| 1/F / 2/F | | |

---

## Part 4 — The scene (30 minutes)

**4a. Underground floors are invisible by default.** The MTR, LG2 and LG1 levels
sit **below** the uphill terrain. Set the ground opacity to **0.5** so they show
through. Then check: can a viewer actually see all three underground levels?

**4b. The camera.** An oblique view centred on the mall. In the working set the
camera was placed **directly** (a `Camera` object with a target, distance and
tilt) rather than through `goTo()` with distance options, which proved unreliable.

| Setting | Working value | Your value |
|---|---:|---:|
| Distance | 400 m | |
| Tilt | 41° | |
| Heading | | |
| Screen position of the mall | (640, 315) | |

**4c. The rendering trap that costs hours.** In *absolute-height* elevation mode,
**every ring, every polyline vertex and every label point must carry an explicit
z.** A 2D ring `[x, y]` renders **zero pixels** — with no error, no warning, and
no exception. A 3D ring `[x, y, z]` renders correctly. The symptom is a scene
with layers listed in the panel but **nothing visible**.

> Also: `GeoJSONLayer` **ignores** `elevationInfo`. You must use a
> `GraphicsLayer`. And a `Graphic` cannot carry layer-level `elevationInfo`, so
> each label needs **its own layer**.

**4d. The layer order.** The floor plates are drawn **below** the route lines. If
the plates are on top, an orange slab covers the network underneath it.

**Your check:** with the routes hidden, how many floor plates can you count? With
the plates hidden, how many route layers? Then with both on, is every route
readable?

---

## Part 5 — Write it up (45 minutes)

**Data validation statement:**

> *Datasets: 3D Pedestrian Network (CSDI id `landsd_rcd_1637222018065_52265`,
> Lands Department, via portal.csdi.gov.hk) — per-floor route layers and 29
> vertical connectors, features counted per floor; building footprint from GeoInfo
> Map (www.map.gov.hk), `B1K_Bldg` layer 4, BUILDINGID 1108222840, 163 points,
> 18,217 m². Retrieved [date]. CRS: WGS84 (EPSG:4326) for storage; HK1980
> (EPSG:2326) for measurement. Terrain: Esri WorldElevation3D Terrain3D, sampled
> under the footprint (18.9–35.2 m); G floor datum set to 33.0 m from the Tat Chee
> Avenue junction (measured 33.03 m). Fields used: FloorID, FeatureType, Location,
> Gradient, TerminalID. Derived fields: [list — `ai_` prefix where AI-assisted].*

**Your headline finding, in one sentence.** The question the model answers:

______________________________________________________________

**Your limitations — you need at least five, and they are all real:**

| # | Limitation | Effect on your answer |
|---|---|---|
| 1 | Floor heights are **schematic** (5.5 m storey, 2× exaggerated) — the official heights were never published | |
| 2 | The **podium is a schematic mass**, not the real architectural envelope | |
| 3 | `1/F` and `2/F` are **schematic envelopes** — no route network exists for them | |
| 4 | The **vertical connectors' floor assignment is inferred** from endpoint matching, not published | |
| 5 | **48 flat surfaces** were separated out from the 77 no-`FloorID` features | |
| 6 | OpenStreetMap has **no `levels` tag** for 又一城, so no independent height check exists | |
| 7 | The terrain is a **general DEM**, not a site survey | |

---

## Part 6 — Make it yours

| Option | What you would do |
|---|---|
| **A. Another mall** | Do the same for a mall you know — Cityplaza, Times Square, Sha Tin New Town Plaza. The method is identical. |
| **B. The accessibility question** | Which floors can a wheelchair user reach? Work out which connectors are lifts and whether the routes between them connect. |
| **C. The exit question** | Where do the exits from each floor reach street level, and how far is each from the nearest bus stop? |
| **D. Your own** | ______________________________ |

**The AI angle.** Good uses: writing the connector-classification script, writing
the label-collision solver, interpreting the result. Then **declare it** and prefix
any AI-inferred field with `ai_`.

---

## Checklist

- [ ] Per-floor route networks split by `FloorID`, counts and lengths recorded
- [ ] Footprint found and its area measured
- [ ] The 77 no-`FloorID` features split into **29 connectors** and **48 flat surfaces**
- [ ] Each connector's two floors **measured** by endpoint matching, not assumed
- [ ] Floor footprints derived per floor, including the projecting wings
- [ ] Podium built from the **union** of all floor footprints
- [ ] Terrain **measured** under the footprint, minimum used
- [ ] Datum set to a real measured place (Tat Chee Avenue junction, 33.0 m)
- [ ] VE and schematic storey height **both declared on the figure**
- [ ] Every ring, vertex and label point carries an **explicit z**
- [ ] Labels do not overlap; separation measured in **rendered pixels**
- [ ] Underground floors visible; ground opacity set
- [ ] Data validation statement written
- [ ] At least five limitations declared
- [ ] AI statement written, `ai_` fields prefixed

---

## Where the working files are

| What | Where |
|---|---|
| **Live 3D model** | <https://davidtwmak-maker.github.io/NPLGIS/apps/festival-walk-3d/> |
| App source | `NPL GIS Team/nplgis/apps/festival-walk-3d/index.html` |
| Floor plates + podium builder | `NPL GIS Team/nplgis/scripts/build_buildings_3d.py` |
| Vertical connector classifier | `NPL GIS Team/nplgis/scripts/build_vertical_3d.py` |
| Relief map (2D version) | `NPL GIS Team/GIS Projects/festival_walk_3d_relief.png` |
| Full repository | <https://github.com/davidtwmak-maker/NPLGIS> |
| 3D learning resources | [[3D Mapping Learning Resources]] |

---

*Data © HKSAR Government (Lands Department, CSDI Portal; Lands Department GeoInfo
Map). Terms: non-commercial with attribution.*
