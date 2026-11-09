# HK Steep Slopes >30° — 2D polygon layer

Working folder: `~/GIS Data/HK Landslide Susceptibility/`
Built: 5 Nov 2026
Published: <https://github.com/davidtwmak-maker/NPLGIS> — `assets/data/landslide/`
Purpose: a stand-alone, map-ready polygon layer of Hong Kong's ground steeper
than 30°, with the slope rasters behind it and the factor evidence that says
which terrain variables actually control landslide incidence.

This sits alongside the susceptibility model in
`notes/landslide-susceptibility — NOTES.md`. That note explains the model;
this one explains the **terrain factor itself**, measured at a 20 m grid.

---

## 1. What the layer shows

| | |
|---|---|
| Regions of ground steeper than 30° | **33,231** polygons |
| Total area | **113.29 km²** = **10.09%** of Hong Kong's land |
| Land area used as the denominator | 1,122.26 km² (2,805,642 valid 20 m cells) |
| Area reconciliation error | **0.0 m²** |
| Invalid geometries | **0** |
| CRS | EPSG:2326 (HK1980 Grid) |

Slope classes across the whole territory:

| Class | Area | % of land |
|---|---|---|
| 0–15° | 543.43 km² | 48.42% |
| 15–30° | 465.53 km² | 41.48% |
| 30–45° | 97.95 km² | 8.73% |
| 45–60° | 13.61 km² | 1.21% |
| 60°+ | 1.73 km² | 0.15% |

Almost nine-tenths of Hong Kong is under 30°. The steep ground is not a
continuous band — it is 33,231 separate hillsides, and the largest single one
is a small fraction of the territory.

## 2. Two decisions that change the numbers

### 2.1 Max slope, not mean slope

The mask uses the **steepest 5 m cell within each 20 m cell** (Horn's method,
3×3 kernel on the LandsD 5 m DTM), not the mean slope of the 20 m cell.

This matters because a 20 m cell that averages 18° can still contain a 45°
scarp. Measured against the 124,020 recorded incidents:

> **22,700 incidents sit in cells whose MEAN slope is under 30° but whose MAX
> slope is over it.** A mean-slope threshold would erase roughly a fifth of
> the evidence — including the steepest ground in the territory.

This is the same trap the original AIGIS26_Gp007 storymap fell into (see the
susceptibility note, §1): with mean slope, 100% of incidents appear under 30°
and the "high-risk band" claim inverts.

### 2.2 8-connectivity

Steep cells touching only at a corner are merged into one polygon, so the
layer reads as **hillsides** rather than confetti. 4-connectivity gave 47,140
fragments for the same mask — 42% more polygons for the same ground.

Both decisions are recorded in `test_slope30_definition.py` and
`test_slope_coherence.py`, and both are asserted in the build.

## 3. The factors considered

The susceptibility model (`notes/landslide-susceptibility — NOTES.md`) fits 19
static predictors plus rainfall. Gain share from the fitted ensemble — the
fraction of the model's total discrimination passing through each factor:

| Factor | Gain % | | Factor | Gain % |
|---|---|---|---|---|
| **roughness** | **33.0%** | | slope (max) | 3.7% |
| slope (90th percentile) | 9.3% | | elevation | 3.1% |
| slope (mean) | 7.4% | | grass cover | 2.8% |
| **vegetation fraction** | 5.7% | | stream power index | 2.8% |
| **weathering — felsic (granite)** | 4.9% | | weathering — volcanic | 2.7% |
| **weathering — resistant** | 4.4% | | wetness index | 2.7% |
| relief | 4.0% | | curvature | 2.6% |
| tree cover | 3.7% | | weathering — moderate | 2.5% |
| | | | built-up | 2.4% |
| | | | bare ground | 2.4% |

Grouped: **terrain 68.6%**, land cover 17.0%, weathering 14.5%.

### What that means in plain terms

**1. Roughness is the single biggest factor (33%).** More than all four
weathering classes combined. Roughness here is elevation standard deviation
within the cell — it measures drainage texture and gully density, and gullies
are where landslides actually initiate. This is the most useful finding in the
project, because it is the one factor the original storymap did not consider
at all.

**2. Slope matters, but through its extremes.** Mean slope, 90th-percentile
slope and max slope together carry ~20%. The 90th percentile and max carry
more than the mean, which is the quantitative version of §2.1.

**3. Weathering is a real factor that adds almost nothing to the model.**
Granite terrain carries **4.61×** the incident rate of resistant rock on
gentle ground (area-normalised, within slope bands):

| Slope band | resistant | moderate | volcanic | felsic (granite) |
|---|---|---|---|---|
| 0–15° | 0.56× | 1.15× | 1.76× | **4.61×** |
| 15–30° | 0.22× | 0.70× | 1.36× | 1.42× |
| 30–45° | 0.42× | 0.79× | 1.06× | 1.12× |
| 45–90° | 0.45× | 0.70× | 1.11× | 1.11× |

But adding weathering to terrain+land cover moves ROC-AUC by **−0.0002**
(0.8600 → 0.8598), and a `wx_felsic × slope_max` interaction makes it
**−0.0020** worse. Slope already captures the signal. **Report weathering as
independent evidence about the landscape, not as a model improvement.**

Note the confounding: in Hong Kong, granite terrain *is* the steep terrain, so
the 4.61× figure at 0–15° is itself partly a slope effect. The within-band
control is what makes the claim defensible, and even then the effect
attenuates with slope.

**4. Vegetation is weak at this resolution.** 73% of cells have zero
vegetation fraction, so the land-cover predictors add less than expected
(terrain → +0.0013, terrain+LC → +0.0013). A 10–20 m land-cover layer, or
ENTLI's own `COVER` field (vegetation state *at* the landslide), would be
better.

**5. Rainfall is a trigger, not a static predictor.** Adding rainfall to the
static model *lowers* AUC (0.882 → 0.859) because only 1,760 positives have
rainfall data. But in the trigger model (daily, 2,986 territory-wide rain
events ≥50 mm), rainfall carries most of the discrimination:

| Model | ROC-AUC | PR-AUC |
|---|---|---|
| susceptibility only | 0.566 | 0.175 |
| rainfall on the event day only | 0.689 | 0.233 |
| rainfall with antecedent conditions | 0.758 | 0.333 |
| **susceptibility × rainfall trigger** | **0.770** | **0.352** |

Gain share in the trigger model: `rain1` 35.4%, `rain30` 19.2%,
`rain60` 15.6%, `rain3` 14.5%, `susceptibility` 15.3%.

**The right framing is therefore *susceptibility × trigger*: the terrain
layer says where ground is fragile, the rainfall says when it fails.** That
is the competition-grade argument, and it is why this slope layer is worth
publishing separately from the susceptibility raster.

## 4. Honest limitations

1. **This is a slope layer, not a landslide probability map.** 30° is a
   planning convention, not the angle at which landslides begin.
2. **20 m generalisation of a 5 m DTM.** One cell is one 400 m² square.
3. **The DTM carries tree canopy**, which inflates elevation and understates
   slope in forest. Measured against the Copernicus GLO-30 bare-earth DEM over
   2,805,642 cells: overall median offset **+0.12 m**, 5th–95th percentile
   **−9.24 m to +8.99 m**. The tree-vs-bare offset is only **−0.72 m**, so
   the canopy bias is small at this resolution — but it is not zero, and it
   biases *steep* forest cells toward under-reporting.
4. **Pseudo-absent cells are a proxy for absence.** 65.3% of land cells
   already hold a record, so the model trains on a balanced set that does not
   match real prevalence. Scores are *relative* susceptibility.
5. **ENTLI dominates the training set** (17,256 of 21,684 positives) and is
   weighted to the 1960s aerial survey, where slides were larger and better
   mapped.
6. **Canopy, not rock, sets the DTM surface** in the country parks — the
   within-cell slope spread is 31° on average (p90: 48°), so a single 20 m
   cell can contain both a 10° bench and a 58° face.

## 5. Files

| File | What |
|---|---|
| `assets/data/landslide/steep_slopes_over30.geojson.gz` | 33,231 polygons, EPSG:4326 (GeoJSON is always lon/lat), with slope stats and area per polygon |
| `assets/data/landslide/slope_classes_20m.tif` | five-class slope raster (1=0–15°, 2=15–30°, 3=30–45°, 4=45–60°, 5=60°+), EPSG:2326, 20 m |
| `assets/data/landslide/slope_max_20m.tif` | maximum slope per 20 m cell, degrees, EPSG:2326 |
| `assets/maps/landslide-susceptibility/steep_slopes_over30_map.png` | the two-panel figure |
| `assets/data/landslide/agol/` | **ArcGIS Online-ready versions (EPSG:4326) + `AGOL_PUBLISH_GUIDE.md`** |
| `scripts/build_steep_slope_polygons.py` | mask → polygonise → repair → verify |
| `scripts/make_steep_slope_map.py` | figure generator |
| `scripts/export_slope_layers.py` | packages and verifies the shipped files |
| `scripts/test_slope30_definition.py` | the max-vs-mean measurement |
| `scripts/test_slope_coherence.py` | the 4- vs 8-connectivity comparison |

### Publishing to ArcGIS Online

`assets/data/landslide/agol/` holds the same two vector layers reprojected to
**EPSG:4326** (AGOL publishes from a file *assuming* longitude/latitude, so
the HK1980 source would land in the wrong part of the world), plus
`AGOL_PUBLISH_GUIDE.md` with the full recipe — download links, the publish
steps, the field-name restoration table for the 10-character shapefile DBF
limit, the 2,000-record limit, styling, and the caveats to state.

The guide is also in the team vault as
**[[HK Steep Slopes >30 — GitHub to ArcGIS Online Recipe]]**.


### Layer fields

`region_id`, `slope_mean_deg`, `slope_sd_deg`, `slope_max_deg`, `area_m2`,
`area_km2`, `n_cells`, `slope_def` (`max_horn_20m`).

### Reproduce

```bash
V=~/GIS\ Data/HK\ Landslide\ Susceptibility
$V/build_steep_slope_polygons.py       # → out/steep_slopes_over30.geojson
$V/make_steep_slope_map.py             # → out/steep_slopes_over30_map.png
$V/export_slope_layers.py              # → assets/data/landslide/ + assets/maps/
```

Interpreter: `/Users/davidhermes/.hermes/cache/scratch/ls-venv/bin/python`
(Python 3.13; geopandas 1.2.0, rasterio 1.4.3, shapely 2.2.0, pyproj 3.8.0).

## 6. Six build gates (all of them caught a real defect)

1. **Feature counts asserted** against the source — a truncated write cannot
   pass as a delivery.
2. **Area reconciled in a projected CRS** — polygon area must equal the cell-area
   sum from the raster mask, to 0.0 m².
3. **GEOS `is_valid` only** as the validity rule. Polygons *with holes* are
   valid; a stricter custom check wrongly rejected 181 of them.
4. **`make_valid` repair before measuring**, with area measured from the
   *repaired* geometry — a repair can split a polygon into a MultiPolygon, so
   a cell count is not a substitute for a measurement.
5. **8-connectivity for region labelling**, asserted against the raster mask.
6. **Gate before write in the figure script** — `savefig` runs only after the
   overlap gate passes, so a failing render cannot leave a plausible-looking
   PNG on disk.

## 7. The figure

Two panels sharing one extent:

- **Panel A — slope classes with the incidents.** Five classes from the
  LandsD 5 m DTM, with 40,000 of the 124,020 recorded incidents overprinted.
  The incidents cluster visibly on the orange and red classes.
- **Panel B — the >30° polygons alone**, over the gentler land, with the six
  largest regions labelled by area.

A pixel probe is part of the build: an earlier render *looked* correct but was
88% blank, because the polygons were in HK1980 metres and were drawn on WGS84
axes. The shipped PNG has real pixel counts for all five classes and asserts
zero text overlap and zero clipping.

## 8. Data provenance

| Layer | Source | Count |
|---|---|---|
| Digital Terrain Model 5 m | LandsD | full territory, 12,751 × 9,601, HK1980 |
| Landslide incidents | CEDD, CSDI `cedd_rcd_1640249280153_17521` | 10,854 |
| Historical landslide crowns | CEDD, CSDI `cedd_rcd_1636520697377_96152` | 113,166 (1924–2023) |
| Land cover | ESA WorldCover 2021 v200 | 10 m, 11 classes |
| Geological map 1:100,000 | CEDD, CSDI `cedd_rcd_1636520962284_7237` | 891 polygons |
| Rainfall (daily) | CEDD, CSDI `cedd_rcd_1636517963140_47030` | 91 gauges, 2005–2026 |
| Bare-earth DEM (canopy check) | Copernicus GLO-30 | for the bias measurement |

All keyless. The CSDI "Land Use" catalogue entries are Legislative Council
constituencies, not land cover — ESA WorldCover was used instead.
