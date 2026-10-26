# 15-minute walk restaurants — PLK Ngan Po Ling College

**Question:** Find all restaurants within 15 minutes walking distance from Po Leung Kuk Ngan Po Ling College.
**Answer:** **497 licensed restaurants** (of 2,654 in the study area) fall inside the 15-min walking catchment.
**Analysed:** 2026-10-10 · Tool: QGIS 4.2.3 headless (`qgis_process`)

## Inputs & provenance

| Layer | Source | Notes |
|---|---|---|
| School point | Nominatim geocode of "26 Sung On Street, To Kwa Wan" (matches school website & EDB) | 22.3127775, 114.1901041 (WGS84) |
| Restaurants | CSDI **FEHD Restaurant Licences** `fehd_rcd_1630036390312_58893` (ArcGIS FeatureServer) | 17,283 territory-wide; 2,654 in bbox; attributes: `restaurant_name` (from `NSEARCH03_EN`), licence type, address EN/TC, district, licence expiry |
| Walking network | OpenStreetMap via Overpass API (bbox 22.290–22.335 N, 114.165–114.210 E; foot-accessible road types, `foot!=no`) | 16,576 ways → 67,337 segments (split per segment for exact junction connectivity) |

All processing in **EPSG:2326 (HK1980 Grid)**, metres.

## Method (QGIS Processing, reproducible in the GUI)

1. Reproject inputs to EPSG:2326 (`ogr2ogr -t_srs EPSG:2326`).
2. **Service area** — `native:serviceareafrompoint`: network = OSM segments, start = school, strategy = Shortest, travel cost = **1,200 m** → `reachable_15min`.
   - Assumption: 15 min × 80 m/min (≈4.8 km/h normal walking pace) = 1,200 m along the network.
3. **Buffer** — `native:buffer`, 50 m, dissolved → `catchment_15min` (50 m ≈ walking distance to a shopfront across the street).
4. **Extract by location** — `native:extractbylocation`, restaurants `are within` catchment → `restaurants_15min` = **497 features**.

GUI equivalent: Vector → Network Analysis → Service Area (from point) → then Vector → Geoprocessing Tools → Buffer → Extract → Location.

## Files

- `results.gpkg` — layers: `school`, `network_osm`, `reachable_15min`, `catchment_15min`, `restaurants_bbox` (2,654), `restaurants_15min` (**497**)
- `restaurants_15min.csv` — the 497 with lon/lat, name, licence type, address (Excel-friendly)
- `restaurants_bbox.geojson`, `network_segments.geojson`, `school.geojson` — raw inputs (WGS84)
- `map_15min_restaurants.png` — quick-look map
- `npol_walk.qgs` — QGIS project stub used for headless runs (open in QGIS, add `results.gpkg`)

## Caveats

- Walking speed and the 50 m buffer are teaching assumptions, not surveyed values.
- OSM network completeness: minor footpaths may be missing; plan-view crossings (flyovers/footbridges without shared nodes) can be under/over-connected. HK streets generally allow pedestrian access.
- FEHD licence points are premises locations (licence holders), updated 2026-06/07; `restaurant_name` lives in the `NSEARCH03_EN` field, `NAME_EN` is only the licence category.
- FEHD `LATITUDE`/`LONGITUDE` are **string** fields — spatial envelope queries work; numeric `where` on them fails.

## Fun numbers

- 497 restaurants reachable — check top licence categories: General Restaurant vs Light Refreshment split in the CSV.
- Compare with a 5-minute catchment (400 m) to see how fast food choices thin out.

---

## Student worksheet

[[Student Worksheet — 15-Minute Walk Catchment]]
