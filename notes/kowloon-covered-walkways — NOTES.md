# Kowloon Covered Walkways to School — Method Note

**Working folder:** `~/GIS Data/Sun-Rain Exposure/`
**Computed:** 22 November 2026 — routes solved on the LandsD 3D Pedestrian
Network, every count recomputed from the delivered files.
**Study area:** the Kowloon Peninsula — Sham Shui Po, Kowloon City and Yau
Tsim Mong districts (28.5 km²). Kowloon East is excluded; it is not the
peninsula.

## The question

Where are the covered pedestrian pathways on the Kowloon Peninsula, and how
covered is the walk from a public transport stop to each secondary school?

## The method

Routes are **shortest paths on the pedestrian network**, not straight lines.
The 3D Pedestrian Network is split into three classes straight from its own
authoritative fields:

| Class | Test | Segments in study area |
|---|---|---:|
| Sheltered | `WeatherProof = 1` (Covered) **or** `Location = 2` (Indoor) | 14,761 (173.9 km) |
| Exposed | `Location = 1` and `WeatherProof = 2` (NonCovered) | 56,906 |
| Unclassified | `WeatherProof = 3` | 1,943 |

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

| Check | Value |
|---|---:|
| Secondary schools in the study area | **103** |
| Stops (MTR exits / bus / green minibus) | **1,778** = 326 / 716 / 736 |
| Schools routed | **103 of 103** |
| Median route length | **768 m** |
| Median longest uncovered stretch | **238 m** |
| Schools with a > 200 m uncovered stretch | **57** |
| Schools with a > 500 m uncovered stretch | **15** |
| Schools with a fully covered walk | **2** |
| Detour factor (route ÷ straight line) | median **1.16**, max **3.88** |

**Only two schools have a completely covered walk** — Ying Wa College and
California School. The median school still has a single unbroken 238 m
stretch in the open; at the worst schools that stretch approaches 900 m.

The stop itself is a second, separate exposure — the share of stops with a
covered path within 30 m:

| Stop type | Sheltered | Share |
|---|---:|---:|
| MTR station exits | 222 of 326 | **68 %** |
| Bus stops | 393 of 716 | **55 %** |
| Green minibus stops | 368 of 736 | **50 %** |

An MTR exit is the best shelter in the system; a green minibus stop — the one
that serves what the bus does not — is the worst.

## Four bugs found and fixed

All four produced plausible-looking output and no error. Bugs 3 and 4 were
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

## Scenario — worst case: walking from the nearest MTR station

The stop-to-school analysis above assumes the buses run. This is the
opposite bound: **bus and minibus service is out, or the roads are too
congested to travel on, so the student walks the whole way from the
station.**

The origin is the **MTR station exit**, not the station centroid — students
enter and leave through exits. All 375 exits in the study area (29 stations)
are snapped to the pedestrian network, a shortest path is solved from each to
the school, and the shortest wins.

| Check | Value |
|---|---:|
| Schools with a walkable route to an MTR exit | **103 of 103** |
| Median walk | **492 m** |
| p90 walk | **1,013 m** |
| Longest walk | **1,667 m** (Po Leung Kuk Choi Kai Yau, from Lai Chi Kok) |
| Median longest uncovered stretch | **335 m** |
| Median walking time in rain | **8 min** (6 min on the flat) |
| Schools needing over 15 min | **20** |
| Schools with no covered stretch at all | **34** |
| Median exit-to-network snap | 4.3 m (max 48.5 m) |

Walking time uses **Tobler's hiking function**, applied per edge —
`v = 6 · exp(−3.5 · |slope + 0.05|)` km/h — plus a **20 % rain penalty**.
Tobler slows the walk on descents as well as climbs, which a single
route-wide speed factor cannot do.

**A note on the covered share.** The MTR walk's median covered share is
0.03, against 0.41 for the "most-sheltered route" above. That is not a
contradiction: the most-sheltered route was *selected* to maximise covered
share, so its cover share is biased upward by the selection. The MTR walk is
a fixed nearest-exit choice, so it is an unbiased sample of what students
actually walk. Against the fair baseline in this project — the nearest-stop
route, also not selected for coverage — the MTR walk is *better* sheltered
(11.5 % pooled vs 4.8 %). The network-wide baseline for the study area is
23 % sheltered.

Ten stations serve 81 of the 103 schools, so station-level resilience is the
lever: To Kwa Wan 15, Shek Kip Mei 12, Kowloon Tong 9, Mong Kok East 8,
Prince Edward 8, Yau Ma Tei 8.

### Five more bugs, of the same family

All five produced plausible output and no error. Each was caught by checking
the exported geometry against the stored number, or by a reader questioning
a distance.

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

**Standing test:** every exported route's length, recomputed in EPSG:2326,
must equal its stored walk distance. It now holds for all 103 walks to
within **0.15 m**, and the same check caught bugs 3 and 7.

## Files

| File | Records | What it is |
|---|---:|---|
| `assets/data/kowloon-covered-walkways/peninsula_routes_schools.json` | 103 | School records with every exposure metric (`ai_` prefixed). The nested per-stop detail is stripped for the public copy |
| `assets/data/kowloon-covered-walkways/peninsula_route_geometry.geojson.gz` | 206 | The routes — shortest and best-covered per school. EPSG:4326 |
| `assets/data/kowloon-covered-walkways/peninsula_covered_paths.geojson.gz` | 14,761 | The sheltered network with street names. EPSG:4326 |
| `assets/data/kowloon-covered-walkways/peninsula_pti.geojson.gz` | 1,778 | Stops, with the 30 m shelter flag. EPSG:4326 |
| `assets/data/kowloon-covered-walkways/Schools_RouteMetrics.csv` | 103 | The same school metrics as a flat table |
| `assets/data/kowloon-covered-walkways/Kowloon_Covered_Walkways.gdb.zip` | 5 feature classes | Esri File Geodatabase, **EPSG:2326 (HK 1980 Grid)** — opens natively in ArcGIS Pro |
| `assets/maps/kowloon-covered-walkways/kowloon_peninsula_covered_routes.png` | — | The two-panel figure |
| `assets/data/kowloon-covered-walkways/mtr_walk_schools.json` | 103 | The worst-case walk from the nearest MTR exit, per school |
| `assets/data/kowloon-covered-walkways/mtr_walk_routes.geojson` | 103 | Those 103 walks as lines |
| `scripts/mtr_walk_schools.py` | — | Computes the worst-case MTR walk |

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
