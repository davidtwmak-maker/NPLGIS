# MTR Fare Saver Map — data sources

**Output:** `mtr_fare_saver_map.png` (1650×1430 px)

## Sources

| Layer | Source | Records | Notes |
|---|---|---|---|
| MTR lines (10) | [opendata.mtr.com.hk/data/mtr_lines_and_stations.csv](https://opendata.mtr.com.hk/data/mtr_lines_and_stations.csv) | 10 line codes, 95 station stops | official opendata; we extracted the first `DT` direction for each line and dropped duplicate `UT` |
| MTR station WGS84 | [johnleungck/MTR-Stations-Coordinates-JSON](https://github.com/johnleungck/MTR-Stations-Coordinates-JSON) | 80 stations | community-maintained; supplemented with 18 hand-added coords for newer stations (Hin Keng, Kai Tak, etc., from OpenRice pages and known geography) |
| MTR line colors | [infinityMark/HK_MTR_map](https://github.com/infinityMark/HK_MTR_map) MTRMap.js | 10 colors | matches MTR's published line colors (觀塘/荃灣/港島/...) |
| Fare saver list (41) | [mtr.com.hk Fare Saver page](https://www.mtr.com.hk/ch/customer/tickets/fare_saver.html) | 41 entries | list of shopping malls, the designated MTR station(s), and the region; manually transcribed to `fare_savers.csv` |
| Fare saver coords | [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/) via Hermes `maps` skill | 39 / 41 first-pass | 2 misses (啟德花園購物商場, 大窤口第二商場) hand-pinned to known addresses |

## Method

1. Build routes — for each line, take the first direction's station sequence from the MTR opendata CSV, look up each station's lat/lon, write a `LineString` GeoJSON. The line polyline is straight between stations (no rail geometry is published; this matches city-scale use).
2. Build stations GeoJSON — one point per named station with WGS84 lat/lon.
3. Geocode each fare-saver by name (zh + en) via Nominatim, preferring Hong Kong results.
4. Render with matplotlib — MTR lines in their official colors, stations as small open circles, fare savers as colored stars grouped by region (Hong Kong Island blue, Kowloon red, New Territories green), with leader-line labels placed by a greedy bbox-collision solver.

## Quality notes

- **Train tracking station list** (the Fare Saver leaflet 2026-6 update) matches mtr.com.hk's current page 1:1.
- Geocoding is best-effort — community-driven OSM data may place some malls ~50-150m off their actual reader; for station-association purposes this is fine.
- The polyline uses straight segments; real MTR alignment curves are smoothed at larger scales. For urban-scale analysis (catchment, accessibility) this is the standard simplification.

## Files in this folder

- `mtr_lines_and_stations.csv` — raw MTR opendata
- `mtrStationsCoord.json` — raw github station coordinates
- `MTRMap.js` — raw github color source
- `fare_savers.csv` — transcribed list, no coords
- `fare_savers_geocoded.csv` — list with lat/lon
- `fare_savers.geojson` — point features for the map
- `fare_savers_routes.geojson` — line features for the map
- `fare_savers_stations.geojson` — station point features
- `build_map_data.py` — data prep pipeline
- `render_map.py` — map renderer
- `mtr_fare_saver_map.png` — output

---

## Student worksheet

[[Student Worksheet — Festival Walk 3D Mall Model]]
