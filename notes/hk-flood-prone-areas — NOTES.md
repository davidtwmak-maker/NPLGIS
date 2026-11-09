# HK Flood-Prone Areas — Data Package & Methodology Notes

Working folder: `~/GIS Data/HK Flood Prone Areas/`
Fetched: **4 November 2026** (all endpoints probed live; counts verified against served values)

---

## 1. The reference storymap, and what to copy from it

`https://storymaps.arcgis.com/stories/a3e6eaefc6854a85b83857341b9e99e1` — **"FLOOD RISK"**, Cambridge MA Community Development Department (created Jun 2021, modified Dec 2025). Its companion is a public-facing Web Experience: **"Flood Viewer 2025 Tool"** (`55143e5f4676454d954376a9981f26f5`).

**Its storymap spine** (extracted from the StoryMap JSON `nodes`):

| Section | Question it answers |
|---|---|
| The Stormwater Journey | Where does rain water go? (watershed framing) |
| What is the Risk? → *Precipitation Flooding* | Where does it flood, and how deep? |
| An Encroaching Ocean | Sea level rise and storm surge as a second driver |
| What is the Risk? → *Storm Surge Flooding* | Which properties are exposed to sea water? |
| What is the Impact of Flooding? | Consequences — depth × value × people |
| Protecting You and Your Property | Actionable fix for the worst case |
| What is Your Risk? → *Resident* / *Businesses* | **Address-level lookup** — click your own building |
| Learn More | References |

**Its data model** (from the Flood Viewer Web Experience config) — this is the pattern to imitate:

- `Cambridge_FV2025_Flood_Extents_Layers` — **flood extent polygons by scenario**
- `Final_Refined_DEM_Contours` — DEM + contour basemap
- `Buildings`, `Address_Points`, `FV2025_Parcels` — **property-level exposure**
- `Water_Bodies`

**Two structural weaknesses to beat:**
1. **It is a northern-hemisphere city with a single river geometry.** HK has no comparable published flood-extent layer — this is the gap your team can fill, and the reason this project is publishable.
2. **It has no statistical validation.** Cambridge asserts its flood extents; it never tests them against observed records. A HK project that *quantifies* the gap between modelled and observed flooding is a stronger competition entry.

---

## 2. What Hong Kong actually publishes (the official baseline)

DSD replaced the old "flooding blackspots" list with **flood-prone areas**, grouped by **cause of flooding** (not by severity):

| List | Count | Nature |
|---|---|---|
| Locations Prone to Blockage | **226 points** | Blockage at catchpits/gullies during heavy rain |
| Locations with Drainage Improvement Works in Progress | **15 points** | Projects completing progressively by mid-2031 |
| Coastal Low-lying or Windy Residential Areas | **26 areas** | From the CEDD Coastal Hazards Study (storm surge + overtopping wave + sea level rise) |

The three lists are **the study area**. DSD's own note on every page: *"The locations and extents shown in map are indicative only."* — i.e. **points, not polygons**. That limitation is the project's opening, not its excuse.

### Data fetched (this package)

| File | Records | Source | Geometry |
|---|---|---|---|
| `dsd_blockage.geojson` | 226 | DSD web map `mapData` (leaflet) | Point (WGS84) |
| `dsd_works.geojson` | 15 | DSD web map `mapData` | Point |
| `dsd_coastal.geojson` | 26 | DSD web map `mapData` | Point |
| `support/dsd_channel.json` | 9,247 | CSDI `dsd_rcd_1629267205231_66675` L1 | LineString |
| `support/dsd_engineered_channel.json` | 2,719 | CSDI `dsd_rcd_1742963120722_16615` L0 | LineString (with WIDTH/HEIGHT) |
| `support/dsd_inlet.json` | 1,221 | CSDI `dsd_rcd_1629267205231_69065` L0 | Point |
| `support/wsd_catchment.json` | 1,223 | CSDI `wsd_rcd_1629267205232_5923` L0 | Polygon (NAME, SUBCATCH_ID) |
| `support/landsd_land_boundary.json` | 4,709 | CSDI `landsd_rcd_1637223499176_68379` (iC1000) | Polygon |
| `raw/blockage.pdf` | 4 pp. | DSD official list PDF (26.8.26 r1) | Text |

**Provenance:** the three flood-prone lists were scraped from the DSD Leaflet pages' inline `mapData` JSON, because DSD publishes **no open spatial file** for them. The PDF (`raw/blockage.pdf`) is DSD's own published list and was used to **cross-check** the scrape: `verify_against_pdf.py` matches **226 / 226** scraped titles against the PDF text layer.

*Two PDF artefacts had to be repaired in the checker, and both are DSD's, not the scrape's:* DSD's PDF spells "**Morrision** Hill Road" (the map says "Morrison"), and the text layer splits a word across a line break ("sitti ng out area"). Without repairing those, the check reports false misses on correct data.

**Reproduce:** `./fetch_support.sh` (paginates to 3,000/page and asserts final counts). Scraped lists: see `raw/*.html`.

---

## 3. Verified supporting datasets (all live-probed, counts confirmed)

| Dataset | CSDI id | Count | Use |
|---|---|---|---|
| GEO Raingauge Data (daily) | `cedd_rcd_1636517963140_47030` | 1,126,191 rows / 91 gauges | Rainfall record 1984→2026 |
| Gridded rainfall nowcast | `hko_rcd_1634958531320_87755` | 840 | HKO 4-km grid, live |
| Predicted tidal info (hourly) | `hko_rcd_1634808062104_80740` | 15 | Astronomical tide |
| Predicted tidal info (high/low) | `hko_rcd_1634809240679_79523` | 15 | High/low tide table |
| Stormwater pipes | `dsd_rcd_1629267205232_85526` | 107,204 | Drainage capacity proxy |
| Manhole (Stormwater) | `dsd_rcd_1629267205232_64331` | 78,525 | Network density |
| Manhole (Stormwater) special | same, L1 | 1,342 | Special structures |
| Multiple Pipes (Stormwater) | `dsd_rcd_1629267205231_39480` | — | Parallel pipe runs |
| Rising Main (Stormwater) | `dsd_rcd_1629267205232_15861` | — | Outfall links |
| Tapping Point (Stormwater) | `dsd_rcd_1629267205232_22725` | 1,948 | Roof/yard connections |
| Terminal Manhole (Sewage) | `dsd_rcd_1629267205232_35333` | — | Sewage/stormwater interaction |
| Catchwater (Engineered Drainage Systems) | `wsd_rcd_1629267205232_33206` | 721 | Major channel network |
| Catchment & subcatchment areas | `wsd_rcd_1629267205232_5923` | 1,223 | **The analysis unit** |
| Digital Terrain Model 5 m | `landsd_rcd_1638158088368_93806` | raster | WMS + GeoTiff only, **no vector service** |
| Building | `landsd_rcd_1637211194312_35158` | 342,233 | Exposure |
| 2021 Census — Small Subunit Groups | `censtatd_rcd_1635933365202_19171` | 2,342 | Population at fine grain |
| 2021 Census — Small Tertiary Planning Unit | `censtatd_rcd_1635933193720_58660` | — | Population |
| Geological Map 1:100,000 | `cedd_rcd_1636520962284_7237` | 10 layers | GEOLOGY, Coastline (193) |
| Geol. 1:100,000 — Coastline | same, L0 | 193 | Coastal distance |
| Flooding Blackspots (**deprecated**) | `dsd_rcd_1728891975004_392` | 4 | **Do not build on it** — removed 30 Nov 2026 |

**DTM direct download** (the CSDI file-api returns 403 for it):
`https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip` → 28.7 MB zip, `Whole_HK_DTM_5m.asc` (12,751 × 9,601, 5 m cells, HK1980 origin 799997.5/799997.5, NODATA −9999). Open with rasterio/GDAL, **not** `np.loadtxt`.

---

## 4. Methodology — the recommended study

### The research question (operationalised)

> **Which locations in Hong Kong are most exposed to urban flooding, and what drives that exposure?**

Do **not** copy Cambridge's "click your house" framing alone — it is a lookup, not a study, and it has no testable pattern. Also avoid a bare "map the flood-prone areas" project: the DSD map already exists and the team's output would be wallpaper.

**Recommended framing:** build a **Flood Exposure Index** over the 1,223 WSD catchments (or the 2,342 census small subunit groups), score each, then deep-dive the top 5–15.

### Step 1 — Terrain & catchment base

- DTM 5 m → derive **slope** and **elevation**; compute **flow accumulation** and **catchment area** per cell.
- Join to WSD catchment polygons → each catchment gets terrain descriptors (mean slope, catchment area, outlet elevation).

### Step 2 — The drivers (each traceable to a named dataset)

| Driver | Dataset | Why it matters |
|---|---|---|
| Catchment area & impervious cover | WSD catchments + ESA WorldCover 2021 (built class 50) | Bigger, more built catchments fill faster |
| Drainage network density | DSD channels + engineered channels | Where the network is thin, backup is likelier |
| Drainage inlets per hectare | `dsd_inlet` (1,221) | Inlet density = local capacity proxy |
| Stormwater pipe density | `dsd_rcd_1629267205232_85526` (107,204) | Trunk capacity proxy |
| Outfall / rising main presence | Rising mains (1,948 tapping points, SW rising mains) | Where backwater is possible |
| Elevation relative to tide | HKO predicted tide + DTM | Sea water inundation risk |
| Rainfall intensity | GEO Raingauge (1.13 M rows) + HKO gridded nowcast | Which catchments get hit hardest |
| Exposure | Building (342k) + 2021 Census small subunit (2,342) | How many people / assets |
| Distance to coast | Geological Map Coastline (193 features) | Storm surge exposure |
| Distance to river | WSD Catchwater Channel (721) | Fluvial flood exposure |

### Step 3 — Compute the index

Per catchment: normalise each driver → weight → composite score → rank. **Weights must be stated with one-line rationales** (per competition convention), or better, **learned** from a model with its own importance measure (gain share) plus a linear comparator.

### Step 4 — Validation (this is what separates a real project)

- **Ground truth:** GEO Raingauge daily rainfall 1984→2026. Define "flood event" at a gauge (e.g. daily total above a return-period threshold), then test whether catchments whose catchments drain to that gauge score higher.
- **Guard against leakage** (a real trap): if positives get a measured rainfall value and negatives get a percentile fill, the model learns the fill, not the geography. Give every negative a real date and compute its predictors through the **identical** procedure.
- **Spatial blocked CV**, not random split — neighbouring cells share predictor values, so a random split inflates AUC. Group into ~5 km blocks.
- **Area-normalise any class comparison** — a band holding 22% of land but 48% of events is 2.1×; that ratio is the headline number.
- **Fit a classifier on one suspect predictor alone and assert AUC < 0.75.** If it fails, the sampling design is wrong, not the model.

### Step 5 — Exposure & impact

Join the index to buildings and census small subunit groups: population and assets in the top-scoring catchments. The impact map answers "who is affected", not "where is it wet".

### Step 6 — Ground truth from the field (student-collected)

Students photograph and time-record flooding at 15–20 sites (photo + timestamp + observed depth), including at least 3 sites the index ranked **low** — that is what proves the index has skill. Privacy rule: no student home locations; observed commutes/sites only.

---

## 4b. Derived flood mechanism for all 267 points (NEW)

`derive_mechanism_v2.py` → `flood_mechanism.geojson` + `flood_mechanism.csv`

DSD publishes the three lists grouped by *cause*, but does not publish the
cause for each individual point. This derives it from the data, so every
location can be classified on a reproducible basis rather than by reading its
street name.

**Metrics measured per point**

| Field | Source | Meaning |
|---|---|---|
| `d_coast_km` | CEDD geological coastline `cedd_rcd_1636520962284_7237` (193 polygons; dissolves to 1,098 km², shoreline 1,062 km) | distance to the sea |
| `elevation_m` | LandsD Whole HK DTM 5 m (HK1980 grid, EPSG:2326) | ground level, 0–192 m across the 267 points |
| `d_bigchannel_km` | DSD channels + engineered channels, `WIDTH ≥ 10 m` | distance to a major watercourse |
| `d_inlet_km` | DSD stormwater inlets (1,221) | distance to the nearest gully |
| `d_catchment_km` | WSD catchments (1,223) | distance to the catchment edge |
| `nearest_catchment` | WSD catchment `NAME` | the drainage catchment |

**Decision tree** (thresholds are percentiles of the 267-point distribution,
so they are fitted to this city rather than imported from another one)

| Mechanism | Condition | Count |
|---|---|---|
| `local_drainage_blockage` | everything else — urban local network, not coastal, not beside a major channel | 185 |
| `channel_backflow` | within major-channel p20 (0.06 km) and not coastal | 48 |
| `coastal_tidal` | on DSD's coastal list, OR (within coast p20 **and** near a major channel **and** ground ≤ 5 m) | 32 |
| `low_lying_ponding` | inland beyond coast p50, low-lying, beside a major channel | 2 |

**Cross-tab against DSD's own grouping** — this is the interesting result:
the blockage list is **not** homogeneous. Of the 226 locations DSD attributes
to blockage, the derivation finds 46 that sit beside a major channel (i.e.
channel backflow, not purely local blockage) and 5 that are effectively
coastal. Only 173 are purely local-network blockage. A project that reports
"226 blockage locations" as one category is mis-describing a fifth of its
own study area.

**Validation against known places** (the check that matters):

- All **11** checked locations on DSD's coastal list derive to
  `coastal_tidal` — Sai Kung Town (0.00 km from the sea, 1 m elevation),
  Tai O (0.00 km, 3 m), Kar Wo Lei Tuen Mun (0.03 km, 5 m), Ma Po Tsuen
  (0.08 km, 5 m), Tung Chung Bay (0.01 km, 3 m), Kennedy Town (0.00 km, 4 m),
  Tseung Kwan O South (0.29 km, 7 m), Yuen Long Central (0.78 km, 10 m).
- Inland locations derive to `local_drainage_blockage` as they should —
  Chuk Yuen Bus Terminus (2.56 km from the sea, 55 m elevation), Lung Cheung
  Road (2.17 km, 15 m), Tai Po Road near N6940 (2.88 km, 140 m).

**Confidence**: 58 high, 92 medium, 117 low. `low` is the honest label where
the default class was assigned with no inlet within 300 m.

### Pitfall found while building this

**`landsd_rcd_1637223499176_68379` is NOT a land boundary.** The layer is the
**iC1000 map-sheet index** — 4,709 features whose fields are `SHEETNO`,
`FGDB`, `DGN`, `GML` (a download catalogue). Dissolving it as if it were land
gives **2,130 km²** against Hong Kong's real ~**1,106 km²**, so every
"distance to the coast" computed from it is wrong. Use the CEDD geological
coastline instead: it dissolves to **1,098 km²**, with the largest polygon at
793 km² (Hong Kong Island + Lantau + the New Territories) and the shoreline at
1,062 km. (The OSM coastline ways are a poor substitute here — they include
rivers and streams, so the merged line is 1,506 km and the distance to the
sea is contaminated by riverbanks.) The same class of mistake — a catalogue
layer used as geometry — also produced the broken land mask in the night-lights
study; see the `gis/hk-night-lights-composite` skill.

Also: CSDI FeatureServer responses saved to GeoJSON carry their attributes
under the key **`properties`**, not `attributes`. Reading `attributes` alone
silently yields an empty field list and every name lookup comes back blank.

Also: the DTM ASCII grid is 12,751 × 9,601 = 122 M cells. Random window reads
through rasterio's ASCII driver take minutes; convert once with
`np.loadtxt(path, skiprows=6, dtype=np.float32)` to a `.npy` (490 MB) and
index it directly. The ASCII grid stores the northern edge first, so
`row = (YLL + nrows*cell - Y) / cell`.

---

## 5. Feasibility cap (competition rule of thumb)

- **Stage 1 (territory-wide, cheap):** score all 1,223 catchments or 2,342 small subunit groups. Raster + overlay only.
- **Stage 2 (deep dive):** top 5–15 catchments only. Network analysis, fieldwork, site profiles.
- **Never:** full-territory fine-grained analysis or territory-wide fieldwork.

---

## 6. StoryMaps question chain

**Where** (the 267 official points) → **What** (the index, as a map) → **Why** (which drivers carry the weight) → **Who is affected** (population/assets) → **What to do** (the actionable fix for the worst case, with a physical model — e.g. a canyon cross-section of the worst catchment).

Every map answers one question. Never illustrate a paragraph.

---

## 7. Assumptions to declare (A1..An)

- A1: DSD points mark the *location* of a designated area, not its extent — a 100 m buffer is a stated approximation of the affected spot.
- A2: Annual extreme rainfall ≈ daily totals from the 91-gauge network; sub-daily intensity not modelled.
- A3: Astronomical tide level is used as the sea-water level; storm surge return periods are not modelled (no open dataset).
- A4: Impervious fraction from ESA WorldCover class 50 (10 m) — a proxy for built-up cover, not impervious surface.
- A5: Inlet count per hectare is a capacity proxy; actual inlet capacity is not published.
- A6: DTM 5 m vertical accuracy is assumed adequate for relative elevation, not absolute.
- A7: Building exposure is by centroid; floor area and basement use are not published.
- A8: Population is 2021 census; the study year must be stated.
- A9: The 4-record CSDI "Flooding Blackspots" dataset is deprecated and excluded — the DSD web lists supersede it.

---

## 8. Data validation block (for the submission)

```
Dataset: Flood-prone areas (3 lists) — Drainage Services Department
Source:  DSD website mapData (no open file); PDF "Locations Prone to
         Blockage_26.8.26(Eng)_r1.pdf" used as the cross-check
Fetch:   4 November 2026
Counts:  served 226 / 15 / 26 = 267 points; exported 267 (parity)
Geometry dropped: 0.  CRS: EPSG:4326 (WGS84)

Dataset: DSD drainage channels / engineered channels / inlets — CSDI
Source:  portal.csdi.gov.hk FeatureServer (ids in section 3)
Fetch:   4 November 2026
Counts:  served 9,247 / 2,719 / 1,221; exported identical (parity)
CRS:     served EPSG:4326 via outSR=4326

Dataset: WSD catchment & subcatchment areas — CSDI
Source:  wsd_rcd_1629267205232_5923 L0
Counts:  served 1,223; exported 1,223
```

**Field provenance:** every attribute in the output files is either (a) an authoritative field carried from the source, or (b) a derived value prefixed `ai_` and listed in the field dictionary.

---

## 9. Files

```
HK Flood Prone Areas/
├── NOTES.md                        this file
├── fetch_support.sh                fetch + assert the supporting layers
├── make_overview_map.py            build the overview map (self-checks text overlap)
├── verify_against_pdf.py           cross-check the 226 scraped titles vs DSD's PDF
├── flood_prone_areas_overview.png  the map
├── dsd_blockage.geojson            226 points
├── dsd_works.geojson                15 points
├── dsd_coastal.geojson              26 points
├── raw/
│   ├── blockage.pdf                DSD official list PDF (cross-check)
│   ├── blockage.html works.html coastal.html   scraped pages
└── support/
    ├── dsd_channel.json             9,247 lines
    ├── dsd_engineered_channel.json  2,719 lines
    ├── dsd_inlet.json               1,221 points
    ├── wsd_catchment.json           1,223 polygons
    └── landsd_land_boundary.json    4,709 polygons
```

**Map build gate:** `make_overview_map.py` asserts zero text overlaps and zero off-canvas text; last run 40 text boxes, 0 overlaps, 0 off-canvas.

---

## 10. Key URLs

- DSD flood-prone areas: `https://www.dsd.gov.hk/EN/Flood_Prevention/Our_Flooding_Situation/Flood_Prone_Areas/index.html`
- CEDD Coastal Hazards Study: `https://cedd.gov.hk/eng/media-corner/project-reports/index-id-24.html`
- CSDI Portal: `https://portal.csdi.gov.hk/` (CSW: `https://portal.csdi.gov.hk/geoportal/csw`)
- LandsD DTM zip: `https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip`
- ESA WorldCover: `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N21E111_Map.tif` (HK also needs `N21E114`)
