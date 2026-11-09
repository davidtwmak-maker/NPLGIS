# NPL GIS Team

Hong Kong geospatial projects — maps, 3D scenes, and the open data behind them.

**Live site:** <https://davidtwmak-maker.github.io/NPLGIS/>

**Repository:** <https://github.com/davidtwmak-maker/NPLGIS>

---

## The 3D map — Festival Walk floor exits

`apps/festival-walk-3d/` is the flagship. It is a self-contained ArcGIS JS scene:

- Each floor of Festival Walk (又一城) is a separate GeoJSON layer.
- Every layer is lifted to its **own absolute height** — MTR level (0 m), LG2, LG1, G, UG —
  so the exits fan out up the hillside in the colour of the floor they belong to.
- **The mall itself is drawn as 3D geometry.** Each floor is a separate translucent
  slab (`PolygonSymbol3D` + `ExtrudeSymbol3DLayer`), and every floor gets its **own
  footprint**, derived from that floor's own pedestrian routes buffered 14 m. The seven
  floors therefore read as seven distinct sheets in a stack rather than one flat slab.
- **1/F and 2/F are shown as massing only.** CSDI publishes route data for five floors
  (MTR, LG2, LG1, G, UG); the two upper floors have no published network, so they are
  drawn from the G-floor retail envelope, inset. They are labelled `體量` in the legend.
- Each floor's Chinese label sits at that floor's **own route centroid**, so the labels
  fan out instead of stacking on one point.
- The ground is real terrain (Esri WorldElevation3D); Festival Walk's floor sits at
  about 58 m, with Lion Rock at 495 m directly behind it.
- Click any line to see the official attributes from the source dataset.

**The building is founded on the hillside.** The site slopes: Esri Terrain3D under
Festival Walk's own footprints runs **18.9 m to 35.2 m**. A stack of plates pinned to
one elevation therefore floated over the downhill end. The stack is now based on the
**lowest terrain under the footprint**, and a translucent **podium** — the union of
every floor's footprint, extruded from below the terrain up to the G floor — carries the
building into the hill. The underground floors (MTR, LG2, LG1) sit inside that mass, so
`map.ground.opacity` is reduced to 0.5 to let them show through the surface.

**The G floor is set to Tat Chee Avenue (達之路).** The G floor's pedestrian
routes touch the street at four junctions; the closest is an exact vertex match. The
street there is at **33.0 m**, measured from Esri WorldElevation3D Terrain3D with
`ElevationLayer.queryElevation` (33.03 m at the main junction). The mall's G floor is
a podium deck that meets the street at that junction, so the whole stack is measured
from there. A translucent podium — the union of all seven floor footprints — runs
from −6 m up to the G floor, carrying the building into the hillside. The ground is
drawn at 50% opacity so the three underground floors remain visible through it.

**Heights are schematic.** Each storey is drawn at 5.5 m (the CSDI published floor
levels), at **2× vertical scale** so the levels separate on screen. **The height datum is
the ground floor G**, so each floor reads:

| Floor | Height rel. G | | Floor | Height rel. G |
|---|---|---|---|---|
| MTR Level | −16.5 m | | UG | +5.5 m |
| LG2 | −11.0 m | | 1/F | +11.0 m |
| LG1 | −5.5 m | | 2/F | +16.5 m |
| **G** | **0.0 m** | | | |

Plan positions and the underlying data are unchanged. Festival Walk's official
architectural heights were not published, so the model must not be read as a measured
building. The podium is a schematic foundation mass, not the real building envelope.

| Floor | Absolute elevation | | Floor | Absolute elevation |
|---|---|---|---|---|
| MTR Level | 0.0 m | | UG | 44.0 m |
| LG2 | 11.0 m | | 1/F | 55.0 m |
| LG1 | 22.0 m | | 2/F | 66.0 m |
| **G** | **33.0 m** (= Tat Chee Ave) | | | |

**Vertical circulation is drawn in 3D.** The CSDI route table links floors
through routes that carry no floor id — lifts, escalators, staircases and
ramps. The first version of this layer took *every* route with no floor id and
drew all 77 at one constant elevation, which collapsed them into a flat yellow
mesh draped over the building.

`scripts/build_vertical_3d.py` now separates them properly. It uses the CSDI
`FeatureType` domain (Escalator 8, Lift 10, Staircase 12, Ramp 11 — versus
Traffic Island 6, Crossing 32/33, Footway 1) and the `Location` field
(Indoor 2 / Outdoor 1) to tell real connectors from flat outdoor surfaces, and
resolves which two published floors each connector joins by matching its ends
against the floor networks — a connector's ends land at **0.00 m** from the
floor network it serves, because the two share vertices.

| Connector | Count | Drawn as |
|---|---|---|
| Escalator | 18 | sloping line between its two floors |
| Lift | 8 | vertical shaft between its two floors |
| Staircase | 2 | sloping line |
| Ramp | 1 | sloping line |

That leaves **29 genuine connectors** (drawn at 18 distinct z values from 0 to
44 m) and **48 flat surfaces** — podium decks, traffic islands, crossings and
footways — which are not vertical circulation and belong on the terrain, not
inside the building.

**Every polygon and polyline carries an explicit z.** GeoJSON rings are 2D, and in
`absolute-height` mode SceneView does not fall back to the layer's elevation for
polygon geometry — the extrusion base resolves to 0/NaN and the symbol renders as
**zero pixels with no error**. Adding z to every vertex is what makes the plates and
the floor networks appear.

Open `apps/festival-walk-3d/index.html` directly, or serve the repo root and visit
`/apps/festival-walk-3d/`. It needs WebGL3.

**Rebuild the scene data** from the CSDI API:

```bash
python3 scripts/build_festival_walk_3d.py   # per-floor route GeoJSON from CSDI
python3 scripts/build_buildings_3d.py       # mall floor plates + label anchors
python3 scripts/build_vertical_3d.py        # 3D vertical circulation + site surfaces
```

`build_festival_walk_3d.py` queries the official FeatureServer for
`BuildingID 1108222840` and writes `apps/festival-walk-3d/data/*.geojson`.
`build_buildings_3d.py` turns those per-floor routes into the 3D floor plates
(`buildings_3d.geojson`), the label anchors (`floor_labels.json`), and the camera
centre in `index.html`.

---

## The landslide susceptibility map

`apps/landslide-susceptibility/` is an interactive Leaflet map of where Hong
Kong's ground fails, on a 200 m grid.

- **Hover any cell** to read its susceptibility score, class and HK1980
  coordinates. The scores ship as a flat JSON array, so the page converts a
  mouse position to a row/column and reads the number back with no server
  round-trip.
- **XGBoost** on 19 static predictors: terrain from the LandsD 5 m DTM, land
  cover from ESA WorldCover 2021, and a **weathering-susceptibility** factor
  derived from the CEDD geological map.
- **5-fold spatial blocked cross-validation** on 5 km blocks — ROC-AUC **0.882**,
  PR-AUC 0.853. A random split leaks neighbouring cells and inflates the score.
- Trained against **19,332 cells holding a recorded landslide** (CEDD Location
  of Landslide Incidents + the ENTLI historical crown inventory, 124,020 points
  in all).

**Why a PNG overlay and not 29,614 polygons.** Leaflet creates one DOM element
per vector feature, so the cell polygons would stall the browser on every pan.
The five-class surface is therefore a transparent PNG, and the scores live
beside it in JSON. The 124,020 landslide points are baked into a second PNG on
the same pixel grid for the same reason. The **vector layers still ship** in
`assets/data/landslide/` (gzipped GeoJSON in EPSG:2326, plus a GeoTIFF score
raster) for anyone opening them in QGIS or ArcGIS Pro.

**The projection is a fitted affine transform**, not a library: the build
script fits HK1980 → WGS84 over the grid corners by least squares and writes
both directions into the JSON. The measured residual is **0.48 mm** over 64 km.
The overlay's alignment was then verified in the browser by checking that the
image pixel for a given cell lands on the same screen pixel as that cell's
projected centre — agreement within **1 px** at all four corners.

**Weathering is derived, not measured.** No Hong Kong open dataset carries a
decomposition grade: the geological maps expose only lithology, the 330,467
Ground Investigation boreholes expose only strata grade, and the 23,954 GEO AGS
borehole-log archives contain no weathering text at all. So the factor is
inferred from lithology, which is the standard engineering proxy and the right
one for Hong Kong (Geoguide 3, CEDD).

**What the model says that the original storymap did not.** The storymap
asserted most landslides fall on 30–45° slopes. Re-measured and area-
normalised, the 45–90° band holds a quarter of the land at **2.11×** the
incident rate, while 0–30° runs at **0.46×**. Granite terrain carries
**4.61×** the incident rate of resistant rock on gentle slopes — but adding
weathering to the model moves ROC-AUC by −0.0002, because slope already
captures it. Report the weathering factor as evidence about the landscape, not
as a model improvement.

Full method, validation and limitations: `notes/landslide-susceptibility — NOTES.md`.

---

## The steep slopes map — ground steeper than 30°

`assets/data/landslide/steep_slopes_over30.geojson.gz` is a stand-alone
vector layer of Hong Kong's steep ground: **33,231 polygons covering
113.29 km², which is 10.09% of the land area** (1,122.26 km²). It is a
polygon layer rather than a raster so it can be restyled, dissolved and
overlaid in QGIS or ArcGIS Pro without re-running anything.

**The threshold is on the MAXIMUM gradient in each 20 m cell, not the mean.**
This is not a detail. Re-measured against all 124,020 recorded incidents,
**22,700 of them sit in cells whose mean slope is under 30° but whose maximum
is over it.** A mean-slope threshold would erase roughly a fifth of the
evidence — including the steepest ground in the territory. With mean slope,
100% of incidents appear below 30° and the "high-risk band" claim inverts.

**Steep cells are merged with 8-connectivity**, so corner-touching cells
become one hillside instead of confetti: 33,231 coherent regions rather than
47,140 fragments for the same mask.

The class raster behind it is five classes from the LandsD 5 m DTM —
0–15° (48.4% of land), 15–30° (41.5%), 30–45° (8.7%), 45–60° (1.2%), 60°+
(0.2%) — and ships as `slope_classes_20m.tif` with `slope_max_20m.tif`
alongside it.

**What drives landslides here.** Gain share from the fitted ensemble: terrain
**68.6%**, land cover 17.0%, weathering 14.5%. The single biggest predictor is
**roughness** (elevation standard deviation within the cell) at **33%** —
more than all four weathering classes combined. It measures drainage texture
and gully density, and gullies are where slides initiate. The original
storymap did not consider it at all.

Weathering is a genuine but *redundant* factor: granite carries **4.61×** the
incident rate of resistant rock on gentle ground, yet adding it to
terrain + land cover moves ROC-AUC by **−0.0002**. Slope already captures the
signal. Report it as evidence about the landscape, not as a model improvement.

Rainfall is a **trigger, not a static predictor**: adding it to the static
model lowers AUC, but in the daily trigger model rainfall carries most of the
discrimination and susceptibility × rainfall reaches ROC-AUC **0.770**. The
terrain says where the ground is fragile; the rain says when it fails.

Full method, the factor table, six build gates and honest limitations:
`notes/steep-slopes-over30 — NOTES.md`.

---

## Publishing these layers to ArcGIS Online

`assets/data/landslide/agol/` holds the **ArcGIS Online-ready** versions of
the same layers, plus `AGOL_PUBLISH_GUIDE.md` — a step-by-step recipe for
downloading from GitHub and publishing a live hosted layer.

| File | Features | Size | What it is |
|---|---:|---:|---|
| **`steep_slopes_over30.zip`** | 33,231 | 4.5 MB | **Start here.** Zipped shapefile, has `.prj` |
| `slope_classes.zip` | 106,874 | 24 MB | Zipped shapefile, five slope classes |
| `steep_slopes_over30_wgs84.geojson` | 33,231 | 21 MB | Same data, original field names |
| `hk_slopes_agol_both_layers.zip` | both | 32 MB | One GeoPackage, **both** layers |
| `field_mapping.json` | — | 1 KB | Which field name became which |

Two things students get wrong, both handled in the guide:

- **The CRS trap.** These layers were computed in EPSG:2326 (HK1980 Grid,
  metres). AGOL publishes from a file *assuming* longitude/latitude, so the
  HK1980 version lands in the wrong part of the world. Every file in `agol/`
  is already reprojected to **EPSG:4326** — upload as-is.
- **The 2,000-record limit.** AGOL returns 2,000 records per request by
  default, so the 106,874-feature class layer draws only its first 2,000
  until *Allow >2000 features per request* is enabled on the source view.

Shapefile `.dbf` field names are capped at 10 characters, so they were
shortened on export; `field_mapping.json` maps them back.

---

## Uploading to GitHub (team member)

The repository is already published at <https://github.com/davidtwmak-maker/NPLGIS> and
the site is live. To push an update you need a **clone with its Git history**, not just
the files — the `nplgis/` folder in the shared iCloud drive contains the working tree
only (no `.git`), so `git push` from it will not work.

**Option A — clone the published repo (simplest).**

```bash
git clone https://github.com/davidtwmak-maker/NPLGIS.git
cd NPLGIS
# make your changes, then:
git add -A
git commit -m "Describe your change"
git push origin main
```

You will be prompted for a GitHub username and a **personal access token** (not your
account password). The token needs the `repo` scope; tick the **`workflow` box** as well,
otherwise GitHub refuses any commit that touches `.github/workflows/deploy.yml` with:

> refusing to allow an OAuth App to create or update workflow `.github/workflows/deploy.yml`
> without `workflow` scope

If you use the GitHub CLI instead:

```bash
gh auth login          # browser sign-in
gh auth setup-git      # route git through the CLI credential helper
gh auth refresh -h github.com -s workflow   # only if you will edit the deploy workflow
```

**Option B — work from the shared drive copy.**

Copy the `nplgis/` folder out of the iCloud drive to your own machine, then turn it into
a working clone:

```bash
cd nplgis
git init
git remote add origin https://github.com/davidtwmak-maker/NPLGIS.git
git fetch --depth=1 origin main
git reset --hard origin/main     # matches the folder to the published commit
git branch --set-upstream-to=origin/main main
git status                      # should be clean
```

`git reset --hard` is the important line: it lines the folder up with the published
commit instead of treating every file as new. Do this **before** editing, otherwise your
first commit will re-add all 128 files as new rather than as a change on top of what is
already published.

**After every push**, GitHub Actions rebuilds and redeploys the site automatically
(`.github/workflows/deploy.yml`). The live URL does not change; the run shows up under
the repository's **Actions** tab, and the run must be green before the change appears
on the site.

**What not to commit:** `raw/`, `lidar_dtm/` and `tiles_ib20000/` are deliberately
excluded by `.gitignore` — they are large source downloads, not deliverables. If a
script needs them, run the matching `scripts/fetch_*.sh` first.

---

## What's in the repository

```
index.html                      Site landing page
assets/
  style.css                     Site styles
  maps/                         All rendered maps, full resolution
    festival-walk/              5   · 3D relief, floor exits, fare savers, TPU suggestions
    pedestrian-network/         6   · covered paths, exposed paths, sheltered chains
    volleyball-courts/          2   · outline basemap, quick-look
    walk-restaurants/           2   · 5-minute and 15-minute catchments
    geoinfo/                   22   · iB20000 territory sheet + 21 historical sheets
    landslide-susceptibility/   2   · the susceptibility map, steep-slopes map
  data/                         Source data, geocoded layers, flat CSVs
    pedestrian/                 3D pedestrian network, split by WeatherProof/Location
    festival-walk/              Festival Walk + Kowloon Tong layers
    volleyball/                 Venues, sessions, usage, districts, shoreline
    mtr/                        Fare savers, MTR lines and stations
    walk/                       Restaurant catchments
    landslide/                  Susceptibility cells (29,614), landslide records
                                (124,020), score raster, steep-slope polygons
                                (33,231) + slope rasters — all EPSG:2326
      agol/                     ArcGIS Online-ready versions (EPSG:4326) +
                                AGOL_PUBLISH_GUIDE.md
apps/
  festival-walk-3d/             The 3D scene (index.html + per-floor GeoJSON + floor plates
                                + the podium that grounds the stack on the hillside)
  landslide-susceptibility/    The interactive landslide map (Leaflet + score grid
                                + two PNG overlays)
scripts/                        Every build and render script, made portable
  build_festival_walk_3d.py     Per-floor route GeoJSON from the CSDI FeatureServer
  build_buildings_3d.py         Mall 3D floor plates + label anchors from those routes
  prep_terrain.py               LandsD DTM 5 m → 200 m terrain predictors
  prep_landcover.py             ESA WorldCover → areal class fractions per cell
  prep_geology.py               CEDD geological maps → weathering-susceptibility classes
  fetch_vectors.py              CSDI REST → landslide, rainfall, ENTLI raw CSVs
  build_dataset.py              Labels + predictors → training table
  train_model.py                Spatial blocked CV, baselines, final XGBoost model
  export_layers.py              GeoJSON cells + points, GeoTIFF score raster
  make_susceptibility_map.py    The published static figure
  ablation_weathering.py        Weathering-only vs incremental-value test
  ablation_slope_control.py     Area-normalised incident rates within slope bands
  build_steep_slope_polygons.py Ground steeper than 30 deg -> 33,231 polygons
  make_steep_slope_map.py       The two-panel steep-slopes figure
  export_slope_layers.py        Packages + verifies the shipped slope layers
  update_manifest.py            Extends MANIFEST.json with the slope layers
  test_slope30_definition.py    Max-vs-mean slope measurement against incidents
  test_slope_coherence.py       4- vs 8-connectivity region count
worksheets/                     Student task sheets, one per project, with check numbers
notes/                          Per-project provenance and validation notes
```

---

## Data

Everything is sourced from official open data. Nothing here is scraped from a
commercial map service.

| Dataset | ID / source | Notes |
|---|---|---|
| 3D Pedestrian Network | `landsd_rcd_1637222018065_52265` | LandsD via CSDI · 465,892 segments |
| LiDAR DTM 2020 | `cedd_rcd_1629267205233_87895` | Bulk tiles + HK1980 grid mosaic |
| Volleyball venues / sessions | LCSD SmartPLAY open data | Refreshed every 5 minutes |
| Volleyball usage | CSDI `lcsd_rcd_1670389615666_788` | 2020–2022 only |
| MTR lines and stations | `opendata.mtr.com.hk` | Official |
| Historical maps | GeoInfo Map iB1000 / iB20000 | LandsD |
| Shoreline | Esri China (HK) Shoreline | iB1000, from LandsD |

### Large files are gzipped

GitHub rejects any file over 100 MB, so the biggest layers ship compressed
(GeoJSON compresses to roughly 17% of its size):

```bash
gunzip assets/data/pedestrian/pedestrian_network_hk.geojson.gz
```

The 3D scene's own GeoJSON is **not** compressed — the browser fetches it directly.

---

## Reproducing the maps

Every script in `scripts/` runs standalone and writes its output next to itself.
Paths are relative to the script directory, so the repo works wherever you clone it.

```bash
# 3D pedestrian network export from CSDI
python3 scripts/export_pednet.py

# sheltered-chain connectivity analysis
python3 scripts/arcgis_sheltered_chains.py

# volleyball court GeoJSON build (fetch raw inputs first)
bash scripts/fetch_raw_volleyball.sh
python3 scripts/build_geojson.py

# Festival Walk 3D scene data
python3 scripts/build_festival_walk_3d.py

# Festival Walk relief render (needs the LiDAR DTM mosaic)
python3 scripts/build_mosaic_lidar_dtm.py    # downloads tiles, builds the mosaic
python3 scripts/render_festival_walk_relief2.py
```

**Python dependencies:** `rasterio`, `numpy`, `matplotlib`, `shapely`, `requests`,
`pillow`. The 3D scene itself needs no build step — it is plain HTML + JS loading
ArcGIS from the CDN.

### The analysis scripts need an input data directory

The night-lights and flood analyses work on downloaded source data that is far
too large to keep in the repo (697 nightly GeoTIFFs, a 302 MB elevation grid).
Those scripts read it from one directory, set by the `GIS_DATA_DIR`
environment variable:

```bash
export GIS_DATA_DIR="/path/to/your/data/dir"
python3 scripts/fishing-light/definitive_analysis.py
python3 scripts/flood/derive_mechanism_v2.py
```

If the variable is not set they fall back to the original location on the
author's machine, so the scripts still run for the author without any change.
Each project's note in `notes/` lists the inputs its scripts expect.

---

## Student worksheets

Six task sheets built from the projects in this repository, for secondary students
and CSDI Awards entrants — real data, the real method, the check numbers, the
traps, and the limitations to declare.

Start with **`worksheets/Student Worksheets — GIS Projects.md`** (the index).

| Worksheet | The question |
|---|---|
| 3D Pedestrian Network and Covered Walkways | Can you walk across Hong Kong without getting wet? |
| Volleyball Courts Booking Data | When is it easiest to get a volleyball court? |
| 15-Minute Walk Catchment | What can you reach from a school in 15 minutes on foot? |
| Festival Walk 3D Mall Model | How do you get between floors in a mall built into a hillside? |
| Building Heights in 3D | What does a city look like when you can see its height? |
| MTR Fare Saver Map | Which neighbourhoods have no fare-saver mall within a short walk? |

Every live figure in them was re-verified against the source service on
26 Oct 2026, and the Sham Shui Po building-height statistics were recomputed from
`B1K_Bldg` rather than copied.

---

## Notes on honesty of the data

Each project's `notes/` file records provenance, validation counts, and the
limitations that must be stated in any write-up. The ones worth reading before you
quote a number:

- **`WeatherProof` accuracy** depends on the source recorded in `LevelSource`
  (CEDD / 3D / LiDAR / estimation). Spot-check ~20 segments per district against
  Street View before publication.
- **The 100 m connectivity threshold** for public transport is a chosen value, not
  an official standard. Test 50 m and 200 m.
- **The 3D scene floor heights** (5.5 m storey height) are indicative for teaching
  and demonstration, not the official surveyed heights of Festival Walk.
- **Geocoding** of fare-saver malls is community-driven OSM data and may be 50–150 m
  off a mall's actual reader.

---

## Licences

Code and documentation in this repository are released under the
[MIT Licence](LICENSE.txt).

**Map data © HKSAR Government** (Lands Department, LCSD, CSDI Portal) and
**© Esri / Lands Department** for the shoreline. Terms: non-commercial use with
attribution. Third-party inputs (OpenStreetMap, MTR opendata, OpenRice) carry
their own licences.
