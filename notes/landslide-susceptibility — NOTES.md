# HK Landslide Susceptibility — XGBoost extension

Working folder: `~/GIS Data/HK Landslide Susceptibility/`
Built: 4 Nov 2026
Live map: <https://davidtwmak-maker.github.io/NPLGIS/apps/landslide-susceptibility/>
Purpose: extend the AIGIS26_Gp007 storymap ("Investigation on Soil Erosion and
Landslide in Nature") into a validated, model-based landslide susceptibility
study for Hong Kong.

---

## 1. What the storymap did, and what it got wrong

The storymap used ArcGIS Pro tools on a cropped subset of Hong Kong and built a
visual argument: land cover classification, slope from DTM, landslide records
overlaid, watershed delineation, then a public web map plus a seed-dispersal
game. Its central claim — *"most landslides occur on slopes of 30–45°, so the
high-risk area is slope at 30–45°"* — does not survive proper measurement:

| Test | Storymap result | Re-measured (this project) |
|---|---|---|
| Slope class of incident points | "30–45° is the high-risk band" | 48.2% of incident cells have max slope ≥45°; 15.0% are <30° |
| Area normalisation | not done | 45–90° band holds 22.8% of land but **2.11×** the incident rate; 0–30° holds 32.4% of land but only **0.46×** |
| Mean vs max slope | slope function on DTM | A 200 m cell's *mean* slope dilutes a 40° scarp — with mean slope, 100% of incidents appear under 30°, which is the artefact the storymap fell into |
| Vegetation claim | "intense landslides cause loss of vegetation cover" | Confounded: vegetation is a *cause* (root reinforcement) and an *effect* (denudation). ESA WorldCover 2021 shows 73% of cells have zero vegetation fraction, so land cover cannot resolve a within-cell signal at 200 m. ENTLI's own `COVER` field (vegetation state at the landslide) is the correct source for this question |

The storymap is still a good visual study; its *risk ranking* was never
quantitative. The fix is to replace the eyeballed slope band with a fitted,
validated model over the whole territory.

## 2. Data provenance (all keyless, all live-verified 4 Nov 2026)

| Layer | Source | Endpoint | Count |
|---|---|---|---|
| Landslide incidents | CEDD, CSDI `cedd_rcd_1640249280153_17521` | `https://portal.csdi.gov.hk/server/rest/services/common/cedd_rcd_1640249280153_17521/FeatureServer/0` | 10,854 records (7,949 with a date; `FAILDATE` returned as epoch ms) |
| Historical landslide crowns | CEDD, CSDI `cedd_rcd_1636520697377_96152` | `.../common/cedd_rcd_1636520697377_96152/FeatureServer/0` | 113,166 crowns, 1924–2023 |
| Digital Terrain Model 5 m | LandsD | `https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip` (28.7 MB zip → 302 MB ASCII, 12,751 × 9,601, HK1980) | full territory |
| Rainfall (daily) | CEDD, CSDI `cedd_rcd_1636517963140_47030` | `.../common/cedd_rcd_1636517963140_47030/FeatureServer/0` | 91 gauges, 2005-01-01 → 2026-06-30, 678,770 gauge-days |
| Land cover | ESA WorldCover 2021 v200 | `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{N21E111,N21E114}_Map.tif` | 10 m, 11 classes |
| Geological map 1:100,000 | CEDD, CSDI `cedd_rcd_1636520962284_7237` | layer 5 `GEOLOGY` | 891 polygons |
| Country parks / streams | AFCD `afcd_rcd_1635129924112_81508`, `afcd_rcd_1635130519341_89370` | CSDI FeatureServer | 25 parks, 33 streams |

Note: the CSDI catalogue's "Land Use" entries are **Legislative Council
constituencies**, not land cover — `LNDGS054.GIH3_LC_*_POLY` on map.gov.hk is
`LC` = LegCo. ESA WorldCover was used instead.

## 3. Pipeline

```
raw/Whole_HK_DTM_5m.asc ──► prep_terrain.py ──► work/terrain_200m.npz
   Horn slope (deg), block max/p90 slope, Laplacian curvature, relief (600 m),
   elevation std (roughness), D8 flow direction + accumulation → TWI, SPI
   5 m → 200 m blocks in HK1980 (EPSG:2326); 240 × 318 cells, 29,758 land cells

raw/worldcover_*.tif ──► prep_landcover.py ──► work/landcover_200m.npz
   11 class masks warped to the 200 m grid with average resampling → true
   areal fractions per class (tree, shrub, grass, bare, built, water)

raw/geology_100k.geojson, solid_geology_20k.geojson,
superficial_geology_20k.geojson ──► prep_geology.py ──► work/geology_200m.npz
   lithology → weathering-susceptibility class 0–3 per cell

raw/incidents.csv, raw/entli_crown.csv, raw/raingauge.csv ──► build_dataset.py
   ──► work/train_table.csv (43,388 rows), work/grid_cells.csv (29,758 cells)

work/train_table.csv ──► train_model.py ──► out/model.json, out/metrics.json,
   out/feature_importance.csv, out/susceptibility_grid.csv
   ──► make_susceptibility_map.py ──► out/landslide_susceptibility_map.png
   ──► export_layers.py ──► GeoJSON cells + points, GeoTIFF score raster
```

### Predictors (19 static + 6 rainfall)

Static: `slope` (mean), `slope_max`, `slope_p90`, `relief`, `curv`, `rough`,
`twi`, `spi`, `elev`, `lc_tree`, `lc_shrub`, `lc_grass`, `lc_bare`, `lc_built`,
`lc_veg`, `wx_felsic`, `wx_volc`, `wx_mid`, `wx_res`.

Rainfall: `rain3_max`, `rain3_sum`, `rain30_max`, `rain30_sum` (nearest 3
gauges, inverse-distance weighted), `hk_day_max`, `hk_day_mean` (territory-wide
daily extremes).

## 3a. The weathering factor — what it is, and what it actually does

**No HK open dataset maps weathering.** Verified absent across every candidate:

| Dataset | Finding |
|---|---|
| Geological Map 1:100,000 (`cedd_rcd_1636520962284_7237`) | GEOLOGY/FAULTS/DYKES carry one field each (`Geol_Type`/`F_Type`/`D_Type`) — no decomposition grade |
| Geological Map 1:20,000 (`cedd_rcd_1636520885302_41109`) | `Solid_geology` (`Sol_Type`), `Superficial_geology` (`Sup_Type`), `Texture_and_meta` (`TM_Type`); official dictionary Tables A1–A4 list only unit/formation/lithology/texture |
| Ground Investigation, 330,467 boreholes (`cedd_rcd_1636517845149_16420`) | fields are REPNO/STATTYPE/HOLEINCL/E_COORD/N_COORD/GRDLEVEL/GRDUNIT/DEPTH only |
| GEO AGS borehole logs (`GI_AGS.zip`, 637 MB, 23,954 report zips) | sections PROJ/LOC/CLSS/GRAD/CONG/CONS/TRIG/TRIX; zero hits for weather/decompos/saprolite/corestone |

So weathering is **derived from lithology**, which is the standard engineering
proxy and specifically correct for Hong Kong: Geoguide 3 (GEO, CEDD) states
chemical decomposition dominates weathering in HK rocks, that weathering grade
is the most important aspect of rock-mass description, and that granitoid rocks
weather to great depth producing saprolite and corestone profiles that fail in
deep-seated slides.

Four classes, from the official 1:100k data dictionary
(`GeoMap100k_Dict.pdf`, Appendix A) and the 1:20k Table A2 lithology list:

| Class | Rock | Share of land |
|---|---|---|
| 3 — deeply weathered felsic | granite, granodiorite, quartz monzonite, rhyolite/rhyodacite dykes | 23.5% |
| 2 — weathered volcanic / tuffaceous | rhyolite, tuff, tuffite, volcanic breccia, colluvium, talus | 42.4% |
| 1 — moderate | clastic and metamorphic units (sandstone, siltstone, marble) | 22.2% |
| 0 — resistant / reclamation | beach, marine, reclaimed ground | 11.9% |

Two data traps found and handled:
- **The 1:20k `Solid_geology` layer is mostly dykes, not bedrock** — 718 rhyolite-dyke
  polygons, 542 fine-grained-granite dykes, 498 medium-grained-granite dykes,
  median polygon area under 20,000 m². Left to override the base, it replaces
  the real bedrock with the dyke swarm. It is now used only to refine units
  ≥ 0.5 km².
- **CSDI GeoJSON exports declare EPSG:4326 but carry HK1980 metres.**
  GeoPandas believes the label and reprojects the data ~1.4e6 m away, so the
  rasterise silently returns an all-empty grid. Detected by bounds and
  overridden to EPSG:2326.

### Does it work? Yes as a factor, but it adds almost nothing to the model

Area-normalised incident rate per 1,000 cells, **within slope bands** — this
is the honest test, because HK granite terrain *is* the steep terrain:

| Slope band | resistant | moderate | volcanic | **felsic (granite)** |
|---|---|---|---|---|
| 0–15° | 0.56× | 1.15× | 1.76× | **4.61×** |
| 15–30° | 0.22× | 0.70× | 1.36× | **1.42×** |
| 30–45° | 0.42× | 0.79× | 1.06× | **1.12×** |
| 45–90° | 0.45× | 0.70× | 1.11× | **1.11×** |

Granite terrain carries **4.61× the incident rate of resistant rock on gentle
ground** and still ~1.1–1.4× on steeper ground — the risk factor is real and
survives slope control. But its marginal contribution to the fitted model is
negligible, because slope already captures most of it:

| Model | ROC-AUC |
|---|---|
| weathering classes alone | 0.7489 |
| `wx_felsic` alone | 0.5904 |
| terrain only | 0.8587 |
| terrain + land cover | 0.8600 |
| terrain + land cover + weathering | 0.8598 (**−0.0002**) |
| + interaction `wx_felsic × slope_max` | 0.8570 (−0.0020) |

**Honest conclusion:** weathering is a genuine susceptibility factor and worth
mapping and reporting (it ranks second in the model at 5.1% gain and third
at 3.3%), but it is **not additive to the terrain model** — HK's landslide
susceptibility is already dominated by slope. Report it as a *control on the
storymap's argument* and as an independent line of evidence, not as a
model improvement. Adding an interaction term makes things slightly worse.

## 4. Two leakage traps that had to be closed

**Trap 1 — constant rainfall on negatives.** Negatives were first given
90th-percentile rainfall while positives got their real event rainfall. The
model then separated the classes by rainfall magnitude: AUC 1.0000. Fixed by
giving each pseudo-absent cell a real date and computing its rainfall through
the identical nearest-gauge procedure.

**Trap 2 — missingness as the label.** CEDD rainfall starts in 2005, so the
19,550 pre-2005 positives carried `NaN` rainfall while every negative carried a
value. XGBoost splits on NaN natively, so it learned "NaN → landslide". AUC was
still 0.9937 after trap 1 was fixed. Fixed by **date-matching**: each negative
inherits the date of a randomly chosen positive, which equalises both the
rainfall distribution and the missingness pattern across classes.

The pipeline now runs an explicit guard (`out/metrics.json` →
`leakage_check_rain_only_auc`): a logistic regression on the rainfall columns
alone must score below 0.75 AUC, or the run is flagged as leaking. Current
value: **0.5047**.

## 4a. A cell-indexing bug that was worth catching

The point → 200 m cell lookup used `int((e - X0) / CELL) + 0.5`. Because the
grid cell centre sits at `easting = X0 + col*CELL`, the correct lookup is
`int((e - X0) / CELL + 0.5)` — round to the nearest centre, not truncate
toward the origin. The old form assigned every record whose offset exceeded
half a cell to the neighbouring cell.

Verified against the exported polygon geometry (unambiguous, since each
exported polygon's bounds *are* a cell): the old mapping was **0% correct**
on 4,997 tested records; the new one **100%**. Fixing it raised positive cells
from 21,317 to 21,684, ROC-AUC from 0.858 to 0.882, PR-AUC from 0.824 to
0.853, and moved the map's "very low" class from 172 landslide cells to 129 —
i.e. the model had been smearing landslide records onto land that the
corrected mapping shows is mostly clean.

## 5. Validation

5-fold **spatial blocked** cross-validation (5 km blocks, 98 blocks) — a random
split leaks neighbouring cells across train/test and inflates accuracy.

| Model | ROC-AUC | PR-AUC | Success rate @20% |
|---|---|---|---|
| Slope ≥30° rule (storymap approach) | — | — | recall 0.835 but flags 62.3% of all land |
| Slope ≥45° rule | — | — | recall 0.298, flags 22.6% of land |
| Weathering classes only | 0.749 | — | — |
| Land cover only | 0.514 | — | — |
| Logistic regression (static) | 0.872 | 0.832 | 0.348 |
| **XGBoost (static)** | **0.882** | **0.853** | 0.352 |
| XGBoost + rainfall (3,563 rainfall-complete rows only) | 0.859 | 0.810 | 0.357 |

Honest out-of-fold success rate of the static model: top 5% of cells captures
9.2% of landslides, top 20% captures 35.2%, top 50% captures 80.1%.

Over the whole grid (29,614 scored cells, 19,332 of which hold a record), the
top 10% of cells by score captures 17.9% of all landslide cells — **179× the
rate of a random selection**.

### How the map's five classes are defined (and why "% of land" is always 20%)

The classes are **equal-area quintiles of the model score** — the territory is
ranked by susceptibility and cut into five groups of equal land area. So
"% of land = 20.0%" for every class **by construction**, and it carries no
information. It was a bad column to put in the key, so the key now shows the
columns that do carry information:

| Class | landslide cells | % of all landslides | landslide rate /1,000 cells | risk vs average |
|---|---|---|---|---|
| Very low | 129 | 0.7% | 22 | **0.03×** |
| Low | 2,448 | 12.7% | 413 | 0.63× |
| Moderate | 5,117 | 26.5% | 864 | 1.32× |
| High | 5,743 | 29.7% | 970 | 1.49× |
| Very high | 5,895 | 30.5% | 995 | **1.52×** |

Territory average: 653 landslide cells per 1,000 land cells (19,332 landslide
cells in 29,614 scored land cells).

Two readings worth keeping in mind:
- The **very low class is near-empty of landslides** — 0.03× the average, i.e.
  30× *safer* than average ground. That is where the model's value is: it
  rules ground out.
- But the **very high class is only 1.52× the average**, because "high
  susceptibility" cells are everywhere in the New Territories hills. The
  model separates the low end far better than the high end — which is exactly
  what a 5 km-block CV on a 200 m grid with 65% of cells already holding a
  record would produce, and it is the honest limit of what this map claims.

### The weighting, in one table

Gain share from the fitted ensemble — the fraction of the model's total
discrimination passing through each factor:

| Factor | Gain % | | Factor | Gain % |
|---|---|---|---|---|
| roughness | 33.0% | | slope (max) | 3.7% |
| slope (90th pct) | 9.3% | | elevation | 3.1% |
| slope (mean) | 7.4% | | grass cover | 2.8% |
| vegetation | 5.7% | | stream power index | 2.8% |
| **weathering — felsic** | 4.9% | | **weathering — volcanic** | 2.7% |
| **weathering — resistant** | 4.4% | | wetness index | 2.7% |
| relief | 4.0% | | curvature | 2.6% |
| tree cover | 3.7% | | **weathering — moderate** | 2.5% |
| | | | built-up | 2.4% |
| | | | bare ground | 2.4% |

Grouped: **terrain 68.6%**, land cover 17.0%, weathering 14.5%.

In plain terms: **roughness alone carries a third of the model's
discrimination** — more than all four weathering classes together — because it
captures drainage texture and gully density, which is where landslides
actually initiate. Slope contributes about 20% across its three measures.

Rainfall did **not** improve discrimination on this subset (AUC 0.859 vs
0.882) because only 1,760 positives have rainfall data. Rainfall's value is as
a **trigger** for real-time forecasting, not as a static susceptibility
predictor — the correct framing for a competition submission.

## 6. Honest limitations

1. **Pseudo-absent cells are a proxy, not proof of absence.** 65.3% of land
   cells already hold a landslide record, so the model is trained on a
   50/50 balanced set that does not match the real prevalence (65% recorded).
   The published probabilities are therefore *relative susceptibility*, not
   absolute probability of failure.
2. **ENTLI dominates the training set** (17,256 of 21,684 positives) and is
   heavily weighted to the 1960s aerial survey (90,678 of 113,166 crowns from
   1960–69). Older slides are larger and better mapped than modern ones.
3. **Rainfall attachment covers only 2005–2026** and uses daily totals from
   point gauges, not radar-derived sub-hourly intensity at the slope.
4. **Vegetation is weak at 200 m** — 73% of cells have zero vegetation
   fraction, so the land-cover predictors add less than expected. A 10–20 m
   resolution land-cover layer, or ENTLI's `COVER` field, would be better.
5. **Weathering is derived, not measured** — see §3a. No HK open dataset
   carries a decomposition grade, so the factor is inferred from lithology.
   It is a sound proxy but it is a proxy, and it adds nothing measurable to
   the model beyond slope.
6. **DTM carries vegetation height**, so tree canopy inflates elevation and
   understates slope in forested terrain (stated in the LandsD metadata).

## 7. Suggested next steps (in priority order)

1. **Add structural controls**: distance to faults (`FAULTS`, layer 2) and dykes
   (`DYKES`, layer 1) from the 1:100k geological map — already downloaded
   (`raw/faults_100k.geojson`, `raw/dykes_100k.geojson`) but not yet joined.
   Fault proximity is the one geological variable with an independent
   mechanism (discontinuity orientation and weakened rock along the fault).
2. Build the **rainfall-triggered** model properly: use hourly HKO data, derive
   antecedent 3-day/30-day totals per cell, and frame the output as
   "susceptibility × trigger" for a real-time early-warning product.
3. Use ENTLI's `COVER` and `CLASS` fields directly instead of WorldCover —
   they record vegetation state *at the landslide* (`COVER` = A/B/C/D, not a
   weathering grade).
4. Add a true held-out temporal test: train on pre-2020, test on 2020–2025.
5. Re-run with a 10–20 m analysis grid for the country-park case study.
6. If the team wants a *measured* weathering factor rather than a derived one,
   it has to come from the scanned GI/LT reports (`hkss@cedd.gov.hk`), which
   carry the borehole logs and decomposition grades as images — not from any
   machine-readable source.

## 8. The interactive web map

`apps/landslide-susceptibility/` in the NPLGIS repository, published by
GitHub Actions to GitHub Pages.

**How the interaction works.** The five-class surface is a transparent PNG
overlay, so panning and zooming stay instant — 29,614 polygons as Leaflet
paths would create one DOM element each and stall the browser. But a PNG cannot
be interrogated, and "what is the score of this cell?" is the question a reader
actually asks, so the underlying scores ship as a flat JSON array and the page
converts a mouse position to a row/column and reads the number back. The
124,020 recorded landslide points are baked into a second PNG overlay on the
same pixel grid for the same reason.

**Projection.** The grid is HK1980 (EPSG:2326) metres. The build script fits a
local affine transform to WGS84 over the grid corners by least squares and
writes both directions into the JSON; the measured residual is **0.48 mm** over
64 km, so a cell is never misread. The overlay's alignment was verified in the
browser by checking that the image pixel for a given cell lands on the same
screen pixel as that cell's projected centre — agreement within **1 px** at all
four corners.

| File | What |
|---|---|
| `apps/landslide-susceptibility/index.html` | the page |
| `apps/landslide-susceptibility/app.js` | map, probe and panels |
| `apps/landslide-susceptibility/data/susceptibility_grid.json` | 76,320 scores + class stats + projection fit (430 KB) |
| `apps/landslide-susceptibility/data/susceptibility_surface.png` | the 5-class surface (41 KB) |
| `apps/landslide-susceptibility/data/landslide_points.png` | the 124,020 recorded points (24 KB) |
| `assets/data/landslide/susceptibility_cells.geojson.gz` | 29,614 polygons, EPSG:4326 (GeoJSON is always lon/lat) |
| `assets/data/landslide/landslide_records.geojson.gz` | 124,020 points, EPSG:4326 (GeoJSON is always lon/lat) |
| `assets/data/landslide/landslide_susceptibility.tif` | the score raster, EPSG:2326 |
| `assets/maps/landslide-susceptibility/landslide_susceptibility_map.png` | the published static figure |

## 9. File index

```
prep_terrain.py      DTM → terrain predictors
prep_landcover.py    WorldCover → class fractions
prep_geology.py      geological maps → weathering-susceptibility classes
fetch_vectors.py     CSDI REST → raw CSVs
build_dataset.py     labels + predictors → training table
train_model.py       CV, baselines, final model, grid prediction
export_layers.py     GeoJSON cells + points, GeoTIFF score raster
ablation_weathering.py      weathering-only vs incremental-value test
ablation_slope_control.py   area-normalised rates within slope bands
make_susceptibility_map.py  figure generator
raw/                 DTM ASCII, WorldCover COGs, geology GeoJSON, CSDI CSVs,
                     GI_AGS.zip (637 MB borehole logs - confirmed to carry
                     no weathering grade)
work/                npz predictors, training table, grid cells
out/                 model.json, metrics.json, feature_importance.csv,
                     susceptibility_grid.csv, ablation_weathering.json,
                     landslide_susceptibility_map.png,
                     susceptibility_cells.geojson, landslide_records.geojson,
                     landslide_susceptibility.tif
```

### Reproduce

```bash
~/GIS\ Data/HK\ Landslide\ Susceptibility/prep_terrain.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/prep_landcover.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/fetch_vectors.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/prep_geology.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/build_dataset.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/train_model.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/export_layers.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/make_susceptibility_map.py
# optional diagnostics
~/GIS\ Data/HK\ Landslide\ Susceptibility/ablation_weathering.py
~/GIS\ Data/HK\ Landslide\ Susceptibility/ablation_slope_control.py
```

Interpreter: the local venv at
`/Users/davidhermes/.hermes/cache/scratch/ls-venv/bin/python` (Python 3.13;
rasterio 1.4.3, scipy 1.18.1, scikit-learn 1.9.1, xgboost 3.4.1,
geopandas 1.2.0, pyproj 3.8.0).
XGBoost on this machine needs `libomp.dylib` — a copy of scikit-learn's is
placed in `site-packages/xgboost/lib/` with its install name rewritten to
`@rpath/libomp.dylib` and re-signed, because Homebrew is not installed.