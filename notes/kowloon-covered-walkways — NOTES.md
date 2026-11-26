# Covered Walkways to School — Method Note

**Working folder:** `~/GIS Data/Sun-Rain Exposure/`
**Computed:** 22 November 2026 — routes solved on the LandsD 3D Pedestrian
Network, every count recomputed from the delivered files.
**Study area:** six districts — Sham Shui Po, Kowloon City, Yau Tsim Mong,
Wong Tai Sin, Kwun Tong and Kwai Chung. The first three are the Kowloon
Peninsula; the study was extended on 22 November 2026 to cover Kowloon East
and the western New Territories in Kowloon.

## The question

Where are the covered pedestrian pathways, and how covered is the walk from a
public transport stop to each registered secondary school?

## The method

Routes are **shortest paths on the pedestrian network**, not straight lines.
The 3D Pedestrian Network is split into three classes straight from its own
authoritative fields:

| Class | Test | Segments in study area |
|---|---|---:|
| Sheltered | `WeatherProof = 1` (Covered) **or** `Location = 2` (Indoor) | 34,533 |
| Exposed | `Location = 1` and `WeatherProof = 2` (NonCovered) | 111,662 |
| Unclassified | `WeatherProof = 3` | 2,469 |

`WeatherProof = 3` is counted as **not covered** — the conservative reading
for a rain-exposure question.

For each school, every stop within 800 m straight-line is snapped to the
network, a route is solved back to the school, and the route is measured
segment by segment:

- `ai_covered_ratio` — sheltered length ÷ total length
- `ai_longest_exposed_m` — **the longest unbroken stretch with no cover**
- `ai_n_exposed_runs` — how many separate open stretches

Two routes are reported per school: the **shortest** (nearest stop) and the
**best-covered** (what a student who knows the network would actually walk).

## The result

### Which schools are in the study

**Registered secondary schools only**: government, aided and direct-subsidy-
scheme schools operating a **whole-day** secondary section.

The EDB school registry does **not** hold one row per school. It holds one row
per **(school, registered premises, teaching session)**, and the School
Registration Number encodes all three:

```
SCRN = 6-digit school number | 4-digit location ID | 2-digit session code
session code:  31 = A.M.   32 = P.M.   33 = whole day   34 = evening
```

So filtering on the dataset name alone is not enough. The merged file carried:

| Filtered out | Count | Why |
|---|---:|---|
| Private and private-independent schools | 22 | outside the study scope |
| Caput schools | 2 | outside the study scope |
| Evening colleges, and A.M./P.M. sections | (inside the private set) | not a whole-day secondary section |
| A second registered premises of the same school | 1 | Lai Chack Middle School's Scout Path extension block, 100 m from its Canton Road main site |

**164 sites, 163 registered schools.** Kowloon Sam Yuk Secondary School keeps
both of its sites — Boundary Street (the junior secondary campus) and
Sycamore Street (the senior campus, 573 m away) are genuinely separate
campuses with different walks, and the registry lists them as two location IDs
of the same school.

| Check | Value |
|---|---:|
| Schools in the study area | **164** (163 registered schools, one with two campuses) |
| By district | Kwai Chung 31 · Kwun Tong 33 · Kowloon City 36 · Sham Shui Po 24 · Wong Tai Sin 22 · Yau Tsim Mong 18 |
| Stops (MTR exits / bus / green minibus) | **3,692** = 441 / 1,390 / 1,861 |
| Schools routed | **164 of 164** |
| Median most-sheltered route length | **799 m** |
| Median longest uncovered stretch | **223 m** |
| Schools with a > 200 m uncovered stretch | **95** |
| Schools with a > 500 m uncovered stretch | **16** |
| Schools with a fully covered walk | **1** |
| Detour factor (shortest route ÷ straight line) | median **1.15**, max **8.36** |

**Only one school has a completely covered walk** — Ying Wa College (331 m
from an MTR exit). Choi Hung Estate Catholic Secondary School comes within
0.4 % of it (0.996 on a 30 m route). The median school still has a single
unbroken 223 m stretch in the open; at the worst schools that stretch
approaches 900 m.

The stop itself is a second, separate exposure — the share of stops with a
covered path within 30 m:

| Stop type | Sheltered | Share |
|---|---:|---:|
| MTR station exits | 313 of 441 | **71 %** |
| Bus stops | 727 of 1,390 | **52 %** |
| Green minibus stops | 901 of 1,861 | **48 %** |

An MTR exit is the best shelter in the system; a green minibus stop — the one
that serves what the bus does not — is the worst.


## Five bugs found and fixed

All five produced plausible-looking output and no error. Bugs 3 and 4 were
found by checking the outputs against the data rather than trusting them; bug 3
was prompted by a reader questioning the route distances.

1. **Duplicate edges were summed, not minimised.** `coo_matrix` *adds*
   duplicate `(u,v)` entries, so parallel segments between the same two nodes
   were added together and the shortest-path cost inflated. The first build
   returned median routes of 107 m — far too short for a Kowloon school
   commute. Fixed by building an explicit pair → min-cost map before the
   matrix is assembled. (scipy's sparse `.minimum()` is a trap here: it
   treats implicit zeros as the minimum and erases the graph entirely.)
2. **A 30 m buffer was 30 degrees.** Shapely measures in coordinate units,
   so `point.buffer(30.0)` on lon/lat geometry is a 3,300 km radius — and
   every one of the 1,778 stops came back 100 % sheltered. Fixed by
   projecting to EPSG:2326 and buffering in metres.
3. **Every distance used the wrong scale for east–west movement.** The graph
   cost was `geom.length * M_PER_DEG_LAT` — a length in *degrees* multiplied
   by the metres-per-degree-latitude constant. One degree of longitude here is
   102,980 m but one degree of latitude is 110,540 m, so every east–west
   segment was inflated by 7.3 %. The symptom was subtle: route lengths
   looked plausible, but the drawn geometry was consistently ~3.5 % shorter
   than the number reported beside it. An explicit round-trip check —
   recomputing every exported route's length in EPSG:2326 and comparing it
   with the stored `ai_route_m` — found 152 of 206 routes disagreeing. After
   the fix all 206 agree to within 2 m.
4. **Six schools share a name, and the schools come from five datasets that
   each restart their own OBJECTID counter.** Neither name nor OBJECTID is
   therefore a usable key: keying on the name merged three Rudolf Steiner
   campuses into one, and keying on OBJECTID collided across datasets. The
   analysis is keyed on `dataset_id + OBJECTID`, unique across all 103. This
   mattered in the web map, where joining routes back by name drew the
   *wrong campus's* route.
5. **Five figures in this note were mistyped.** The MTR worst-case table was
   written by hand from the pipeline's console output, and four of its
   numbers were wrong — median walk 704 m against 693, median longest
   uncovered stretch 403 m against 398, schools needing over 15 min 58
   against 57, exit snap 4.2 m against 3.7 — and one district row carried
   17 against 16. The p90 in the same table was right, which is what makes
   this the hard kind of error: **a figure that is nearly right is harder to
   catch by eye than one that is grossly wrong**, and 704 against 693 looks
   like a perfectly good median. The data has said 693/1,242/398/57 since
   the note was written; the note simply disagreed with it. Found by
   recomputing every figure in the table from `mtr_walk_schools.json` using
   the pipeline's own conventions — `statistics.median`,
   `statistics.quantiles(v, n=10)[8]`, `walk_minutes > 15` — and checking
   them against what the note claimed.

   Guard added: `scripts/kowloon-covered-walkways/verify_note.py` **parses
   the note's own tables** and compares them against the shipped data, so a
   mistyped figure cannot survive a rebuild. The expected values are read
   out of the note rather than typed into the script, because a typed list
   would be a second place to be wrong and the gate would then be checking
   the data against itself. The note has two tables with an overlapping row
   label — "Median longest uncovered stretch" appears once for the
   most-sheltered school route (223 m) and once for the MTR walk (398 m) —
   so the search is scoped to the MTR section by its heading. The school-route
   table is checked separately against `Schools_RouteMetrics.csv`, and all
   seven of its figures agree.
6. **The web map and the note were quoting two different MTR walks.** The
   app ships two MTR route sets: `mtr_walks.geojson` — the worst-case walk
   from the nearest station exit, built by `mtr_walk_schools.py`, median
   693 m — and, inside each school's `ai_ro.nearest_mtr` option, the
   stop-to-school pipeline's MTR route, built by
   `kowloon_peninsula_routes.py`, median 706 m. **They disagree for 19 of
   164 schools**, sometimes by 300 m. The note and the map's own key text
   quote 693 m; the school's panel shows the other number's route.

   The cause is the candidate set, not the network: both scripts build the
   same graph from the same three LandsD files, but the stop-to-school
   script caps candidate stops at 800 m straight-line from the school
   (`PTI_SEARCH_M`), while the MTR script searches every exit in a 1 km
   buffer around the study area. For 18 of the 19 the two builds pick the
   same *station* but a different *exit* of it; for one —
   CARMEL ALISON LAM FOUNDATION SECONDARY SCHOOL — the MTR script's exit
   (Kwai Fong, Exit D) is 903 m straight-line from the school, outside the
   800 m cap, so the stop-to-school build could not have considered it and
   reports a 1,858 m walk where the true nearest-exit walk is 1,547 m.

   The fix is not to pick one number and edit the other: **the app should
   quote the walk it draws.** The purple dashed line and its popup come
   from `mtr_walks.geojson`; the school's panel must therefore show that
   same walk, and the weighted metric must be built on it, or the panel
   and the line describe two different journeys to the same school.

## Scenario — worst case: walking from the nearest MTR station

The stop-to-school analysis above assumes the buses run. This is the
opposite bound: **bus and minibus service is out, or the roads are too
congested to travel on, so the student walks the whole way from the
station.**

The origin is the **MTR station exit**, not the station centroid — students
enter and leave through exits. All 481 exits inside a 1 km buffer around
the study area (31 stations used) are snapped to the pedestrian network,
a shortest path is solved from each to the school, and the shortest wins.

| Check | Value |
|---|---:|
| Schools with a walkable route to an MTR exit | **164 of 164** |
| Median walk | **693 m** |
| p90 walk | **1,242 m** |
| Longest walk | **2,311 m** (Shun Lee Catholic, from Choi Hung) |
| Median longest uncovered stretch | **398 m** |
| Median walking time in rain | **12 min** (10 min on the flat) |
| Schools needing over 15 min | **57** |
| Schools needing over 20 min | **25** |
| Schools with no covered stretch at all | **22** |
| Median exit-to-network snap | 3.7 m (max 48.5 m) |

By district — the new districts are markedly harder:

| District | Schools | Median walk | p90 | Longest | Median time | Over 15 min |
|---|---:|---:|---:|---:|---:|---:|
| Yau Tsim Mong | 18 | 396 m | 616 m | 669 m | 6 min | 0 |
| Sham Shui Po | 24 | 384 m | 751 m | 800 m | 7 min | 2 |
| Wong Tai Sin | 22 | 708 m | 1,230 m | 1,264 m | 12 min | 6 |
| Kowloon City | 36 | 758 m | 1,119 m | 1,192 m | 14 min | 15 |
| Kwun Tong | 33 | 825 m | 2,046 m | 2,311 m | 16 min | 18 |
| Kwai Chung | 31 | 903 m | 1,674 m | 1,813 m | 16 min | 16 |

Walking time uses **Tobler's hiking function**, applied per edge —
`v = 6 · exp(−3.5 · |slope + 0.05|)` km/h — plus a **20 % rain penalty**.
Tobler slows the walk on descents as well as climbs, which a single
route-wide speed factor cannot do.

**A note on the covered share.** The MTR walk's median covered share is
0.08, against 0.41 for the "most-sheltered route" above. That is not a
contradiction: the most-sheltered route was *selected* to maximise covered
share, so its cover share is biased upward by the selection. The MTR walk is
a fixed nearest-exit choice, so it is an unbiased sample of what students
actually walk. Pooled, the MTR walk is 14.2 % sheltered.

Ten stations serve 93 of the 164 schools, so station-level resilience is the
lever: Kwai Hing 15, Kwun Tong 13, To Kwa Wan 12, Choi Hung 11, Shek Kip Mei
9, Tsing Yi 7, Mong Kok East 7, Kowloon Tong 7, Kwai Fong 6, Diamond Hill 6.

**The new districts carry the long walks.** Six of the ten worst schools are
in Kwun Tong and Kwai Chung, walking 1.6–2.3 km from Choi Hung, Kwun Tong,
Kwai Hing and Tsing Yi. Four of them share the same 624 m uncovered stretch
on **Clear Water Bay Road**, which is the single worst piece of exposed
walking in the study.

### Nine more bugs, of the same family

All nine produced plausible output and no error. Each was caught by checking
the exported geometry against the stored number, by a reader questioning a
distance, or by reading the source data rather than trusting it.

5. **Parallel edges were summed again.** The same `coo_matrix` trap as bug 1,
   reintroduced when this scenario was built as a separate script. The
   cheapest segment per node pair is now chosen *before* the matrix is
   assembled.
6. **Edge orientation was decided by comparing coordinates.** Nodes are snapped
   by rounding to 1e-6 degrees, so two entries for the same node can differ in
   the seventh decimal, and an exact coordinate test wrongly reversed an
   edge. A wrongly reversed edge makes the drawn line jump back where it came
   from. Fixed by deciding orientation from **node IDs**.
7. **The path was traced in the wrong order.** `pred` points toward the
   source, so walking it from the exit gives exit→school order. The code
   built the geometry in the reverse of that and then reversed it again, and
   the drawn line came out roughly twice the walked length.
8. **The export zipped two lists of different length.** The metrics list
   skips schools with no reachable exit, so zipping it against the school
   list misaligned every record after the first skip.
9. **Snapping to a disconnected elevated concourse node.** Some exits snapped
   ~17 km away, to a node on the wrong side of a flyover. Fixed by rejecting
   snaps beyond 120 m and by selecting the exit on **network** distance.
10. **The school filter did not exist.** The study included private schools,
    caput schools, evening colleges and A.M./P.M. sections — 24 of 103
    records were not registered whole-day secondary schools. Fixed with an
    explicit filter on finance type and session, documented under *Which
    schools are in the study*.
11. **A school with two registered premises was counted twice.** The EDB
    registry stores one row per (school, premises, session), so Lai Chack
    Middle School appeared twice — its Canton Road main site and its Scout
    Path extension block, 100 m apart. Sites of the same school within 150 m
    are now merged onto the main site. Kowloon Sam Yuk's two campuses are
    573 m apart and are **kept** as separate sites.
12. **The MTR exit was keyed by name alone.** "Exit A" exists twice at Lam Tin
    Station — once on the concourse and once at ground level — and 176
    (station, exit) pairs in the layer are ambiguous. The exit's own
    coordinates are now stored on every record, so the map and the check
    never depend on a lossy name key.
13. **A hard-coded bounding box clipped the study area.** The MTR script
    filtered the network by a fixed lon/lat box, which silently cut off
    Kwun Tong and Kwai Chung when the area grew. It now clips by the same
    District Council polygons as the main pipeline.
14. **All 895 MTR exits in Hong Kong were snap-tested.** The entry-point
    layer covers the whole territory; exits outside the study area are now
    excluded before snapping. Including them made the median exit-to-network
    snap look like 591 m instead of 4.2 m.

**Standing test:** every exported route's length, recomputed in EPSG:2326,
must equal its stored walk distance. It now holds for all 164 walks to
within **0.15 m**, and the same check caught bugs 3 and 7. A second standing
test: every exported route must start at the exit it names and end at its
school — that caught bug 12.

## Access typology — the 15-minute rule

**The rule.** If the worst-case walk from the nearest MTR exit exceeds **15
minutes** (Tobler per edge + 20 % rain penalty), the student uses **bus or
minibus** for access instead of walking. It is applied on *time*, not
distance: 15 minutes is ~1,050 m on the flat but lands anywhere between
**623 m and 1,027 m** on the real routes, because Tobler slows the climb.

| | Schools |
|---|---:|
| Walk-access to MTR (≤ 15 min) | **107** |
| Bus/minibus-dependent (> 15 min) | **57** |

Sensitivity at 10 / 15 / 20 min: 66/98 · **107/57** · 139/25 — the hillside
schools are dependent at every threshold.

For the 57 dependent schools **both access routes are reported side by side**
(`work/access_reference_bus_vs_mtr.csv`): the bus/minibus route (stop name,
walk metres, covered share, longest gap, number of routes serving the stop)
and the MTR walk (station, exit, metres, minutes, gap). Service fragility:
**38 of the 57** have **≤ 2 routes** at their nearest stop — one delayed
driver from no service at all.

**Priority score** for covered-walkway investment, 1 point each:
transit-dependent · ≤ 2 routes at the stop · MTR gap ≥ 500 m · bus gap ≥
200 m · climb ≥ 30 m. Tiers (0–1 low, 2 medium, ≥ 3 high): 58/30/76 across
all 164, and **47/8/2** among the 57 dependent schools.

Delivered: the map rings dependent schools in teal and their click panel
labels both routes ("Bus/minibus route" / "MTR walk (reference)"); the GDB's
`Schools_RouteMetrics` carries `ac_access`, `ac_walk_min`, `ac_bus_*`,
`ac_mtr_*`, `ac_priority`, `ac_tier`, `ac_reasons`; and the typology CSVs are
in `arcgis/`. Limits (also in the vault note): the rule is assumed behaviour,
not observed; home-end access is not modelled; walk times are modelled
(Tobler + rain), not surveyed; fragility counts routes, not headways.

## Files

| File | Records | What it is |
|---|---:|---|
| `assets/data/kowloon-covered-walkways/peninsula_routes_schools.json` | 164 | School records with every exposure metric (`ai_` prefixed). The nested per-stop detail is stripped for the public copy |
| `assets/data/kowloon-covered-walkways/peninsula_route_geometry.geojson.gz` | 328 | The routes — shortest and best-covered per school. Stored as one feature per network edge (12,058 parts), so dissolve on `school_id` + `ai_route_kind` to get a route back. EPSG:4326 |
| `assets/data/kowloon-covered-walkways/peninsula_covered_paths.geojson.gz` | 34,533 | The sheltered network with street names. EPSG:4326 |
| `assets/data/kowloon-covered-walkways/peninsula_pti.geojson.gz` | 3,692 | Stops, with the 30 m shelter flag. EPSG:4326 |
| `assets/data/kowloon-covered-walkways/Schools_RouteMetrics.csv` | 164 | The same school metrics as a flat table |
| `assets/data/kowloon-covered-walkways/Kowloon_Covered_Walkways.gdb.zip` | 7 feature classes | Esri File Geodatabase, **EPSG:2326 (HK 1980 Grid)** — opens natively in ArcGIS Pro |
| `assets/maps/kowloon-covered-walkways/kowloon_peninsula_covered_routes.png` | — | The two-panel figure |
| `assets/data/kowloon-covered-walkways/mtr_walk_schools.json` | 164 | The worst-case walk from the nearest MTR exit, per school |
| `assets/data/kowloon-covered-walkways/mtr_walk_routes.geojson` | 164 | Those 164 walks as lines |
| `assets/data/kowloon-covered-walkways/MTR_WorstCase_Schools.csv` | 164 | The same worst-case metrics as a flat table |
| `scripts/mtr_walk_schools.py` | — | Computes the worst-case MTR walk |

The File Geodatabase carries seven feature classes:
`Schools_RouteMetrics` (164), `Route_Candidates` (24,978),
`Routes_To_School` (12,058 edges), `Covered_Paths` (34,533),
`Stops_PTI` (3,692), `MTR_WorstCase_Walks` (164, whole routes),
`MTR_WorstCase_Schools` (164).

**Derived fields** (all `ai_`-prefixed, per the CSDI Awards disclosure rule;
every other field is authoritative and unmodified): `ai_covered_ratio`,
`ai_covered_m`, `ai_longest_exposed_m`, `ai_n_exposed_runs`,
`ai_unclassified_m`, `ai_route_m`, `ai_direct_m`, `ai_snap_m`, `ai_by_type`,
`ai_best_cov_ratio`, `ai_best_cov_route_m`, `ai_best_cov_kind`,
`ai_best_cov_longest_exposed_m`, `ai_sheltered_within_30m`.

## Assumptions

- **A10** "Covered" = `WeatherProof = 1` or `Location = 2`. `WeatherProof = 3`
  counts as not covered.
- **A11** "Best route" = the candidate with the **highest covered ratio**,
  not the shortest — a student will take the sheltered option even if it is
  longer. The shortest route is reported too.
- **A12** Candidate stops = within **800 m straight-line** of the school.
- **A13** School → network snap: nearest graph node, accepted within 150 m.
- **A17** **School scope**: registered whole-day secondary schools only —
  government, aided and direct-subsidy-scheme. Private, private-independent
  and caput schools are excluded, as are evening colleges and A.M./P.M.
  sections. Two registered premises of the same school within 150 m are one
  campus and are merged; campuses further apart are kept as separate sites.
- **A18** **Study area**: six Census 2021 District Council districts — Sham
  Shui Po, Kowloon City, Yau Tsim Mong, Wong Tai Sin, Kwun Tong, Kwai
  Chung. The network is clipped by these polygons, never by a bounding box.
- **A14** Distance metric: **Hong Kong 1980 Grid (EPSG:2326)**. Every reported
  distance — route length, snap distance, detour factor, the 30 m shelter test
  — is measured in the projected CRS, not in degrees.
- **A15** Worst-case scenario: the walk starts at the **MTR station exit**,
  chosen by **network** distance, not by proximity to a station centroid.
  Exits more than 120 m from the pedestrian network are unusable.
- **A16** Walking time uses **Tobler's hiking function** per edge plus a
  **20 % rain penalty**. The rain penalty is a judgement, not a measurement:
  test 10 % and 30 % — the ordering of schools is robust, the exact minutes
  are not.

## Limits

- `WeatherProof` is only as good as its source; LandsD records provenance in
  `LevelSource`. Spot-check ~20 random segments per district before
  publication.
- Coverage is binary per segment — partial cover within a segment is not
  resolved.
- The "best route" is a **modelled choice**: it assumes the student knows
  which stop gives the sheltered path and will walk past two closer stops to
  take it. This is the first thing a field survey should test.
- The 30 m shelter radius is a chosen threshold, not an official standard.
  Test 15 m and 50 m — the ordering of the three stop types is robust, the
  exact percentages are not.
- Rain exposure only. The sun question (sky view factor, hours in shadow) is
  Stage 2 and lives in the open SVF tool.

## Sources

| Layer | Dataset | Provider |
|---|---|---|
| 3D Pedestrian Network | `landsd_rcd_1637222018065_52265` | Lands Department via CSDI Portal |
| Bus stops | `td_rcd_1638874475129_49745` | Transport Department via CSDI Portal |
| Green minibus stops | `td_rcd_1638874728005_80512` | Transport Department via CSDI Portal |
| MTR station exits | 3D Indoor Map WFS (`mapapi.hkmapservice.gov.hk`) | MTR Corporation / HK Maps |
| Secondary schools | 5 EDB datasets, merged | Education Bureau via CSDI Portal |
| District boundaries | Census 2021 District Council polygons | Census and Statistics Department |
