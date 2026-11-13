# Hong Kong — land below 5 metres (low-lying land) and the "depressions" map

**Prepared for:** ArcGIS Pro
**Projection:** Hong Kong 1980 Grid System, **EPSG:2326**
**Source raster:** LandsD 5 m Digital Terrain Model
(`landsd_rcd_1638158088368_93806`), 5 m cells, 12,751 × 9,601

---

## The headline numbers

| Measure | Value |
|---|---|
| Hong Kong's land area (this mask) | **1,116.0 km²** (true area ≈ 1,106 km², so +0.9 %) |
| **Land below 5 m** | **60.6 km²** |
| Share of Hong Kong's land | **5.4 %** |
| Mean elevation of that land | 2.4 m |
| Largest single patch | 23.1 km² (Yuen Long / Tin Shui Wai) |

---

## What this is

The map and data show every part of Hong Kong's land whose ground level is
**below 5 metres** above sea level. On the map this is the **blue**.

## The one thing you must know before you use this

**The source DTM codes the sea as 0 metres.** So if you run
`elevation < 5` on the DTM on its own, you get **the entire ocean** — about
2,700 km² of Hong Kong's waters and the harbours, not the low-lying land.

Two things make that worse, and both are handled here:

1. **Flat land is also coded 0 m.** Cheung Chau's town, Lamma's valley floor,
   the airport apron, the Tsuen Wan and Kwai Chung flats and the Tin Shui Wai
   reclaimed area all read 0 m in the DTM — they are real land at real sea
   level, but they are indistinguishable from the sea by elevation alone.
2. **Some harbour water reads above 0 m.** Victoria Harbour and Tolo Harbour
   contain cells at 1–9 m (dredged channels, harbour structures), so a
   "land = elevation above 0" test calls parts of the harbour land.

That is why the package ships a **land mask** and why the GeoJSON is the
recommended layer to load in ArcGIS Pro.

---

## The files

| File | What it is | Use it for |
|---|---|---|
| **`hk_lowland_under5m.geojson`** | The low-lying land as polygons, cleaned: slivers under 0.05 km² dropped, leaving **106 patches**. Each carries its area, mean/min/max elevation and centre point. | The best layer to **symbolise and label**. Load it straight into ArcGIS Pro. |
| **`hk_lowland_under5m.tif`** | Binary raster, `1` = land below 5 m, `0` = everything else. EPSG:2326, 533 KB, deflate-compressed. | "Extract by Mask", "Raster to Polygon", area statistics, or as a mask for your own analysis |
| **`hk_lowland_under5m_map.png`** | The map (200 dpi). | Your figure, a slide, or a quick check |
| **`hk_lowland_under5m_patches.csv`** | One row per kept patch: id, area, centre lon/lat, mean/min/max elevation. | A quick read in a spreadsheet |
| **`hk_lowland_under5m_all_patches.geojson`** | Every contiguous patch (9,146 of them), including the slivers. | Completeness; the cleaned file drops the slivers for readability |
| **`hk_land_mask.tif`** | Binary raster, `1` = land, `0` = sea. | If you want to build your own elevation query |

---

## How to load it in ArcGIS Pro

### Option A — the map layer (recommended)

1. **Map** → **Add Data** → **Add Data** → browse to `hk_lowland_under5m.geojson`.
2. ArcGIS Pro reads GeoJSON in the WGS84 geographic system by default.
   **Project it to EPSG:2326** so it lines up with the DTM and with the
   DSD / WSD layers: **Project** → **Data Management** → **Project** → set
   *Output Coordinate System* to `Hong Kong 1980 Grid System (EPSG:2326)`.
   (Or simply set the **Map** coordinate system to EPSG:2326 and ArcGIS Pro
   will draw it on the fly.)
3. Symbolise: a single solid fill, blue, 40 % transparent.
4. **Label** the patches. The `area_km2` and `mean_elev_m` fields are the
   ones worth showing.

### Option B — the raster

1. **Map** → **Add Data** → **Add Raster Data** → `hk_lowland_under5m.tif`.
2. Symbology → **Classified** or **Unique Values** on the single band
   (values 0 and 1).
3. For the area in square kilometres: **Analysis** → **Raster Calculator**
   with `Con("hk_lowland_under5m.tif" = 1, 1, 0)`, then
   **Conversion** → **Raster to Polygon** and read the `area` field, or
   **Analysis** → **Overlay** → **Tabulate Area**.

### Checking you loaded it correctly

| Check | Expected |
|---|---|
| Projection | Hong Kong 1980 Grid System (EPSG:2326) |
| Tai Mo Shan | about 929 m on the DTM (the summit is 957 m) |
| Tuen Mun seafront | about 3 m |
| Victoria Harbour | about 5 m — **and it must be white (sea), not blue** |
| Tolo Harbour | 0 m — **and it must be white (sea), not blue** |
| Total land below 5 m | **60.6 km²**, 5.4 % of the land |

---

## How the land mask was built, and what to trust

Every land boundary for Hong Kong reachable without a login was tested, and
each one fails a different way. These were verified by probing named places,
not by reading documentation:

| Source | Why it was rejected |
|---|---|
| CEDD "Coastline" polygons | A coastal **geology band**, not a land boundary. 922.6 km² of open sea lies inside it; Tolo Harbour and Victoria Harbour read as land. |
| CSDI "Digital Land Boundary Map iC1000" | A **map-sheet index**. All 4,709 polygons are exactly 0.45 km² — one 1 km square sheet each. |
| 2023 District Council constituency boundaries | Administrative lines that run out into the sea. Their union is 2,754 km², 2.5× the land. |
| Esri China (HK) iB1000 SWA shoreline | The coastline does not close: only 1,114 of 4,323 endpoints are shared between ways, so a flood fill from the open sea leaks straight through the land. The gap is topological, not a resolution limit. |
| Natural Earth 10 m ADM0 | The best outline available (1,036 km²) but generalised — it omits the small islands and the airport. |
| The OSM coastline on its own | It closes the **islands** perfectly — Cheung Chau is a single closed ring of 1,004 nodes whose filled area (2.473 km²) matches the DTM's own positive land on that island (2.472 km²) to within 0.001 km² — but a coastline has no land border, so a flood fill from the open sea leaks through the northern New Territories (813 km² leaked). |

**The mask that was used** is built from the OpenStreetMap **Hong Kong
boundary** — OSM relation 20044132 (`admin_level=4`, name 香港 Hong Kong) and
913110 (`admin_level=3`) — chained with the Guangdong–Hong Kong border ways
named `Border Guangdong - Hong Kong` and the `natural=coastline` ways, and
then intersected with the DTM's positive elevation:

```
LAND = (the OSM Hong Kong boundary) AND (the DTM's positive elevation)
```

- the **boundary** says where Hong Kong ends — the coast *and* the land
  border with Shenzhen;
- the **DTM's positive elevation** says where the ground rises above sea
  level — 1,119.4 km² on its own.

A cell is land only if it passes both. That is what removes the reclaimed
harbour structures inside Victoria Harbour and Tolo Harbour, which the DTM
alone would call land.

### The acceptance test

| Test | Result |
|---|---|
| Land area | 1,116.0 km² against a true 1,106 km² → **+0.9 %** |
| Named land probes | 37 of 40 correct |
| Named water probes | all 11 correct — Victoria Harbour, Tolo Harbour, Deep Bay, Clearwater Bay, Shenzhen Bay, Aberdeen Channel and the open sea are all water |
| The 3 failures | Tsuen Wan flats, Peng Chau and Lamma Island — all three are places the DTM codes as **0 m**, so the DTM cannot see them. Their area is **under 1 km²** and it is **not** in the 60.6 km² figure. |

### What this means for the number

- **60.6 km²** is the figure this package ships.
- A **conservative** reading — land = DTM above 0 m, then below 5 m — gives
  **61.7 km²**, essentially the same. The 60.6 km² figure is not inflated by
  the mask choices: the two independent routes agree to within 2 %.
- The flat land the DTM codes as 0 m (the reclaimed towns, the airport apron,
  the Cheung Chau and Lamma flats) is genuinely land and genuinely low, but
  the DTM cannot separate it from the sea, so it is **excluded** here. If you
  want it included, say so and it can be added as a separate layer.

---

## Known limits

- The DTM is a **terrain** model. It does not include building footprints,
  so a raised podium or a flyover can read as low ground.
- **Reclaimed land below 0 m** — the airport platform and the Kwai Tsing
  container terminals sit at or below sea level by design. They are land, but
  they are protected by sea walls, so they are not the same hazard as a
  natural floodplain.
- **Vertical datum.** The DTM is in metres above the Hong Kong Principal
  Datum, which is close to but not identical to mean sea level. "Below 5 m"
  here means "below 5 m above the Hong Kong Principal Datum".
- **A "depression" in the technical sense** — a closed basin from which
  water cannot escape — is a different question from "land below 5 m", and
  this map is not that. Use **Spatial Analyst → Hydrology → Fill** (or
  **Sink** in ArcGIS Pro) on the DTM for that, and clip to the land mask
  first: a full Fill on the 122-million-cell Hong Kong grid is slow and
  large.

---

## Files and how they were made

| Script | What it does |
|---|---|
| `fetch_osm_coastline_api.py` | Fetches the OSM data for the territory from the OSM API, in tiles, caching each tile on disk |
| `fetch_boundary_ways.py` | Fetches the OSM boundary ways the tiles miss |
| `assemble_osm_coastline.py` | Turns the cached tiles into one coastline file and reports the chain count |
| `build_land_mask_osm_hk.py` | Builds `hk_land_mask.npy` from the OSM boundary + the DTM, and verifies it against named places |
| `build_lowland_deliverables.py` | Writes the GeoTIFF, the GeoJSON files and the CSV |
| `make_lowland_map.py` | Draws the map and runs the label-overlap check |

Order: `fetch_osm_coastline_api.py` → `assemble_osm_coastline.py` →
`build_land_mask_osm_hk.py` → `build_lowland_deliverables.py` →
`make_lowland_map.py`.

To rebuild from scratch, you need the 5 m DTM and a Python with the
geospatial stack:

```
pip install numpy scipy rasterio shapely pyproj matplotlib Pillow
```

Then point the scripts at the DTM and run them in order:

```
export HK_DTM_TIF=/path/to/Whole_HK_DTM_5m.tif
python3 fetch_osm_coastline_api.py    # caches the OSM tiles
python3 fetch_boundary_ways.py        # the boundary ways the tiles miss
python3 assemble_osm_coastline.py     # one coastline file
python3 build_land_mask_osm_hk.py     # the land mask + its verification
python3 build_lowland_deliverables.py # the GeoTIFF, GeoJSON and CSV
python3 make_lowland_map.py           # the map + the label checks
```

`fetch_boundary_ways.py` is not optional. The tiled fetch covers the sea,
but the ways that run along the Shenzhen land border are not in the tiles,
and without them the boundary does not close and the mask comes out at
559 km² instead of 1,116 km². Fetch them with
`/way/<id>/full` - the bulk endpoint `/ways?ways=...` returns the ways with
only `<nd ref>` and no node coordinates, so the geometry cannot be resolved
from it.

`HK_DTM_TIF` wins; if it is unset the scripts look in
`$GIS_DATA_DIR/HK Landslide Susceptibility/raw/`, then
`$GIS_DATA_DIR/HK Flood Causes/raw/`, then the SSD copy at
`/Volumes/Extreme Pro/Download/HK DTM 5m/Whole_HK_DTM_5m.tif`.

The OSM fetch takes a while: the API rate-limits hard (HTTP 429) and the
grid is 48 tiles. The tiles are cached on disk, so a rerun resumes rather
than starting over.
