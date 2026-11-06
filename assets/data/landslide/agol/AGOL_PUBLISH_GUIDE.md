# Publishing the steep-slope layers to ArcGIS Online

Prepared 6 Nov 2026. Source: HK Landslide Susceptibility project
(`~/GIS Data/HK Landslide Susceptibility/`).

This is the student-facing version of the recipe. The general publishing
method — hosted layers, scenes, live feeds, storage quotas — is in the
Obsidian note **[[Publishing Processed Data in ArcGIS Online]]** in the NPL
GIS Team vault (`CSDI Portal/`). This file is the specific, copy-and-paste
path for *these* layers.

---

## 1. Download the files

All in `assets/data/landslide/agol/` on
<https://github.com/davidtwmak-maker/NPLGIS>:

| File | Features | Size | What it is |
|---|---:|---:|---|
| **`steep_slopes_over30.zip`** | 33,231 | 4.5 MB | **Start here.** Zipped shapefile, has `.prj` |
| `slope_classes.zip` | 106,874 | 24 MB | Zipped shapefile, five slope classes |
| `steep_slopes_over30_wgs84.geojson` | 33,231 | 21 MB | Same data, original field names, no renaming needed |
| `hk_slopes_agol_both_layers.zip` | both | 32 MB | One GeoPackage, **both** layers — one upload |
| `field_mapping.json` | — | 1 KB | Which field name became which |

Direct links (right-click → Download):

```
https://raw.githubusercontent.com/davidtwmak-maker/NPLGIS/main/assets/data/landslide/agol/steep_slopes_over30.zip
https://raw.githubusercontent.com/davidtwmak-maker/NPLGIS/main/assets/data/landslide/agol/slope_classes.zip
https://raw.githubusercontent.com/davidtwmak-maker/NPLGIS/main/assets/data/landslide/agol/steep_slopes_over30_wgs84.geojson
https://raw.githubusercontent.com/davidtwmak-maker/NPLGIS/main/assets/data/landslide/agol/hk_slopes_agol_both_layers.zip
https://raw.githubusercontent.com/davidtwmak-maker/NPLGIS/main/assets/data/landslide/agol/field_mapping.json
```

**Which one should I pick?**

- **One layer, simplest:** `steep_slopes_over30.zip`
- **Both layers in a single hosted item:** `hk_slopes_agol_both_layers.zip`
  (a GeoPackage with two layers inside — AGOL publishes both at once)
- **Don't want to rename fields:** `steep_slopes_over30_wgs84.geojson`
  (GeoJSON has no 10-character field-name limit)

---

## 2. The CRS trap — read this before you upload

**Every file above is already in EPSG:4326 (WGS84 longitude/latitude).**
Upload it as-is.

The source data was computed in EPSG:2326 (HK1980 Grid, metres). AGOL
publishes from a file assuming coordinates are longitude/latitude —
*"The features are published in the WGS 1984 Web Mercator (Auxiliary Sphere)
coordinate system"*. Upload the HK1980 version and the layer lands in the
wrong part of the world, or fails the extent check with
`x = 801,037 is not a longitude`.

If you re-project the data yourself and you get a file whose coordinates are
six-figure numbers, it is **not** ready for AGOL. Check the first coordinate:
it must look like `[114.16, 22.55]`, not `[801037, 848002]`.

---

## 3. Publish it

1. Sign in at <https://arcgis.com>.
2. **Content → My Content → Create New → Feature layer → Upload data.**
3. Choose the format that matches your file:
   - zipped shapefile → **Shapefile**
   - `.geojson` → **GeoJSON**
   - `.gpkg` inside the zip → **GeoPackage**
4. Upload the file. Choose **"Add data and create a hosted layer"**.
5. Set the **title, summary and tags** — tags are how people find your item.
6. **Add Item.** Large layers take a few minutes to analyse.

> A GeoJSON file must be **under 100 MB**. Every file here is well under that.

### If you used the shapefile: restore the field names

Shapefile `.dbf` field names are capped at **10 characters**, so they were
shortened on export. In the AGOL item page → **Data** → rename each field
back:

| In the shapefile | Rename to |
|---|---|
| `slp_mean` | `slope_mean_deg` |
| `slp_sd` | `slope_sd_deg` |
| `slp_max` | `slope_max_deg` |
| `slope_cls` | `slope_class` |
| `slope_id` | `slope_class_id` |
| `area_m2` | `area_m2` |
| `area_km2` | `area_km2` |
| `n_cells` | `n_cells` |
| `over_30` | `over_30` |
| `region_id` | `region_id` |
| `slope_def` | `slope_def` |

`field_mapping.json` has the same table in machine-readable form. Do the
renaming **before** you share the layer.

### If you used the GeoPackage or the GeoJSON

Field names are already full length — skip the renaming.

---

## 4. Make it draw properly

### The 2,000-record limit — the one thing that will bite you

AGOL returns **2,000 records at a time** by default when drawing or querying
a feature layer. The class layer has **106,874 features**, so out of the box
it will draw only the first 2,000 and the rest of Hong Kong will be missing.

Two fixes:

- **Item page → Data → the layer's source view → edit → enable "Allow >2000
  features per request"**, then Save. This is the right fix.
- Or publish the GeoJSON/shapefile **as a web map layer** rather than a
  hosted feature layer — the file is drawn in full, but it is not queryable
  and not editable.

### Style

- **Steep-slopes layer:** graduated colours on `slope_max_deg`, sequential
  ramp. Or unique values on `slope_class` with five classes:
  `0–15°` light green → `15–30°` sand → `30–45°` orange → `45–60°` red →
  `60°+` dark red.
- **Class layer:** unique values on `slope_class`, same five colours.
- **Basemap:** Light Gray Canvas, or the HK basemap.
- Pop-ups: show `slope_max_deg`, `area_km2`, `n_cells`. Not all ten fields.

### Share

Item page → **Sharing** → *Everyone* (public competition entry) or *My org*.
Then **open the URL in a private window** to confirm it works — a share link
that asks for a login is not a public link.

---

## 5. What the data is

- **What it maps:** every part of Hong Kong whose ground is steeper than
  **30°** — 33,231 separate hillsides.
- **Extent:** 113.29 km², which is **10.09% of the land area**
  (Hong Kong's land is 1,122.26 km²).
- **Slope definition:** the **maximum** gradient within each 20 m cell
  (Horn's method on the LandsD 5 m DTM) — *not* the mean slope of the cell.
- **Connectivity:** 8-connectivity, so steep cells touching at a corner merge
  into one hillside.
- **Five classes:** 0–15° (48.42% of land), 15–30° (41.48%), 30–45° (8.73%),
  45–60° (1.21%), 60°+ (0.15%).
- **Area reconciliation error:** 0.0 m². **Invalid geometries:** 0.

---

## 6. Caveats to state in any write-up

- This is a **slope layer, not a landslide probability map.** 30° is a
  planning convention, not the angle at which landslides begin.
- The polygons are a **20 m generalisation of a 5 m DTM**. One cell is one
  400 m² square.
- **The DTM carries tree canopy**, so it understates slope in forest. Measured
  against the Copernicus GLO-30 bare-earth DEM over 2,805,642 cells: median
  offset +0.12 m, 5th–95th percentile −9.24 m to +8.99 m.
- **Why max slope and not mean slope:** 22,700 of the 124,020 recorded
  landslide incidents sit in cells whose *mean* slope is under 30° but whose
  *max* is over it. A mean-slope threshold would erase roughly a fifth of
  the evidence — including the steepest ground in the territory.
- To model susceptibility, combine this layer with rainfall, geology and the
  recorded incident points. See
  `notes/landslide-susceptibility — NOTES.md` in the repo for the full model.

---

## 7. Provenance

| Layer | Source |
|---|---|
| Digital Terrain Model 5 m | LandsD, via CSDI |
| Landslide incidents (124,020) | CEDD — Location of Landslide Incidents + ENTLI historical crowns |
| Geological map 1:100,000 | CEDD, via CSDI `cedd_rcd_1636520962284_7237` |
| Rainfall (daily) | CEDD, via CSDI `cedd_rcd_1636517963140_47030` |
| Land cover | ESA WorldCover 2021 v200 |

All keyless. The terrain was computed in EPSG:2326 (HK1980 Grid) and
reprojected to EPSG:4326 for publishing.

Full method, the factor analysis and six build gates:
`notes/steep-slopes-over30 — NOTES.md`.
