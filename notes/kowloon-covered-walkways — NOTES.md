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
| Median route length | **795 m** |
| Median longest uncovered stretch | **249 m** |
| Schools with a > 200 m uncovered stretch | **62** |
| Schools with a > 500 m uncovered stretch | **15** |
| Schools with a fully covered walk | **2** |
| Detour factor (route ÷ straight line) | median **1.21**, max **3.92** |

**Only two schools have a completely covered walk** — Ying Wa College and
California School. The median school still has a single unbroken 249 m
stretch in the open; at the worst schools that stretch exceeds a kilometre.

The stop itself is a second, separate exposure — the share of stops with a
covered path within 30 m:

| Stop type | Sheltered | Share |
|---|---:|---:|
| MTR station exits | 222 of 326 | **68 %** |
| Bus stops | 383 of 716 | **53 %** |
| Green minibus stops | 355 of 736 | **48 %** |

An MTR exit is the best shelter in the system; a green minibus stop — the one
that serves what the bus does not — is the worst.

## Two bugs found and fixed

Both produced plausible-looking output and no error.

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
   converting the radius to degrees first.

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
- **A14** Distance metric: equirectangular at 22.32° N (111.32 km/° lon,
  110.54 km/° lat).

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
