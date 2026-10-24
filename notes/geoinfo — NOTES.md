# GeoInfo Map data cache — `www.map.gov.hk/gm`

Bulk-cached for David's map-figure generation. Fetched **2026-10-08** by Hermes Agent.

## What this is

**GeoInfo Map (地理資訊地圖)** — HKSAR Government's public geospatial viewer. Base maps,
buildings, photo maps by **LandsD Survey & Mapping Office**; facility data from **29
government departments**; hosting by Digital Policy Office.

- Viewer: <https://www.map.gov.hk/gm/>
- Terms: non-commercial/personal use allowed with attribution — **cite `www.map.gov.hk`,
  keep copyright notices, government owns copyright** (IP Rights Notice on the site).
- Native CRS: **HK1980 grid, EPSG:2326** (ArcGIS `wkid 102140`). All exports here are
  re-projected to **WGS84 (EPSG:4326 / CRS84)** for web use.

## What's in here

| File/dir | What | Status |
|---|---|---|
| `inventory.json` | Every service/layer found: geometry, fields, counts, pagination support | 407 entries; **467 downloadable leaf layers, 8,697,273 features** |
| `manifest.json` | Per-layer fetch result: served count vs fetched count, bytes, status | written live by the download job |
| `raw/<service>/<id>_<name>.geojson` | WGS84 GeoJSON FeatureCollections | download job (`geoinfomap_bulk.py download`) |
| `historical_maps/` | One export PNG per historical-map raster layer | **PARTIAL — see Known issues** |
| `ib20000.py` | iB20000 photo-map tile fetcher (bbox → mosaic PNG) | working, tested |
| `tiles_ib20000/` | tile cache | grows with use |
| `ib20000_territory_z14.png` | whole-territory iB20000 mosaic @ z14 (~9.5 m/px) | prefetch job |
| `geoinfomap_bulk.py` | the downloader (phases: inventory / download / histmap) | re-runnable; download resumes (skips existing files) |
| `inventory.log` (`inv.log`) | scan log | |

## Endpoints (all verified live 2026-10-08)

### ArcGIS REST — vectors (no key needed)
```
https://www.map.gov.hk/arcgis/rest/services/[folder/]<Service>/MapServer/<layer>/query
https://www.map.gov.hk/arcgis2/rest/services/...   (mirror node; histmap/highlight live here)
```
- Folders: `Lgat`, `rGeoInfoMap`, `rIA_SMRIS`, `Utilities`; root services: `hkgeocode`,
  `mbafacility__d00`, `mbameshtile__d00/d01`, `mbaoldm1898__c00`, `mbatsm_link__d00`
  (`mbafacility__d00_android` = duplicate, skipped).
- Query recipe: `?f=geojson&where=1=1&outSR=4326&resultOffset=N&resultRecordCount=1000`,
  verify fetched == `returnCountOnly`; fallback pages by `objectIds`.
- Notable content: land lots (`C1K_LOT_SDO` 375,513), buildings (`B1K_Bldg` 342,424),
  land use 2016/2021/2025 (`GIH3_LC_*_POLY`), District Council areas 2015/2019/2023,
  **Census 2011/2016/2021** (DC / CA / TPU small & large planning units), streets,
  trails, cycling, bus stops (55,852), lamp posts (192,628), facility name points
  (124,886), DSD drainage pipes, schools/clinics/hospitals/election/etc. (484 facility
  codes in `map.menu_structure.js`), historical photo points.

### iB20000 photo basemap tiles (1:20,000) — **keyless**
```
https://services2.map.gov.hk/xyz/ib20000/tile/{z}/{row}/{col}     → PNG 256×256
```
- Esri fused tile cache; HK1980 grid; origin `(-4786700, 8353100)`; LOD 0–21 standard
  XYZ resolutions (L0 = 156543.03392800014 m/px, halve per level); **viewer caps at z17**.
- `col = floor((x - ox)/(256·res))`, `row = floor((oy - y)/(256·res))` (y down).
- Service metadata: `…/xyz/ib20000?f=json` (extent, lods).
- Use `ib20000.py --bbox w,s,e,n --z 16 --out x.png` (WGS84 lon/lat; `--hk80` for metres;
  `--prefetch 14` for the whole territory).

### Other basemap/label rasters — **key required**
```
https://api.hkmapservice.gov.hk/osm/xyz/basemap/HK80/tile/{z}/{x}/{y}.png   (topo)
https://api.hkmapservice.gov.hk/osm/xyz/imagery/HK80/tile/{z}/{x}/{y}.png   (ortho)
https://api.hkmapservice.gov.hk/osm/xyz/basemap/GS/HK80/tile/{z}/{x}/{y}.png (grayscale)
https://api.hkmapservice.gov.hk/ags/map/basemap/VT/IndexedGeneral/HK80      (vector tiles)
```
`?key=` required — the viewer's own public key sits in `map.gov.hk/gm/` page source
(`map_api_key`). **Key policy: do not persist keys in files** — for heavy reuse register
a free key via the HK Map Service API portal, or pass via `HKMAP_KEY` env var. Same HK80
tile grid as iB20000. Max zoom for ortho/topo: z17 (viewer), DOP1982 up to z19.

### Config values (from `map.gov.hk/gm` index.html)
`map_server_host=https://www.map.gov.hk` · `tile_service_host=https://services2.map.gov.hk` ·
`histmap_layer_path=/arcgis2/…/rgeo_histmap_d00/MapServer` · `dynamic_layer_path=/arcgis2/…/rgeo_highlight_d00/MapServer` ·
`geodata_host=https://geodata.gov.hk` · `geodata_geoserver_context=/geoserver/geodatastore/ows`

## Known issues / caveats

1. **Historical map rasters (`rgeo_histmap_d00`) export blank** via ArcGIS `/export` —
   both `arcgis` and `arcgis2` nodes, PNG and JPEG, with explicit `layers` visibility
   params: returns a flat 253-grey canvas (verified by pixel stats). `mbaoldm1898__c00`
   (1889/1898 map) exports fine (2.3 MB PNG, in `historical_maps/`). The in-app viewer
   may still render them interactively — unverified (its requests were not captured).
   The geoserver WMS (`geodata.gov.hk/geoserver/…`) did not respond from this machine.
   → Re-test before promising historical-sheet exports; CSDI also publishes historical
   maps (`landsd_rcd_1637714816051_3690` + 2 more, per csdi-portal skill).
2. **Scale-variant duplicate layers**: many datasets appear 2–6 times (`_LVL_6`,
   `_LVL_7_9`, cross-service mirrors in `Lgat`/`rgeo_highlight`/`rsm_dynamic`). Raw/
   keeps them all (source fidelity); dedupe by layer name pattern when composing a map.
3. `hkgeocode` MapServer = road-centreline geometry (2000 m/100 m/5 m generalisation),
   not a geocoding service — for address→coords use CSDI/Census geocoder or Nominatim.
4. Census/land-use attribute names are cryptic codes (`LCCODE`, `__CENSUS_2021_CA`…) —
   keep `inventory.json` `fields` list as the field dictionary.
5. Count parity is checked per layer (served `returnCountOnly` vs fetched features) and
   recorded in `manifest.json` — re-run `python3 geoinfomap_bulk.py download` to top up
   after the source refreshes (facility data updates continuously).

## Reproduce / refresh

```bash
cd "/Users/davidhermes/GIS Data/GeoInfo Map"
python3 geoinfomap_bulk.py inventory     # rescan (~4 min)
python3 geoinfomap_bulk.py download      # resume/refresh vectors
python3 ib20000.py --prefetch 14         # refresh territory mosaic
```
(Hermes toolchain python has PIL + pyproj; system python3 does not.)

## Attribution (put on any figure using this data)

> Base map: © The Government of the HKSAR (LandsD), www.map.gov.hk · Data: GeoInfo Map,
> participating HKSAR departments · iB20000 orthophoto: LandsD
