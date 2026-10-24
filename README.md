# NPL GIS Team

Hong Kong geospatial projects — maps, 3D scenes, and the open data behind them.

**Live site:** <https://smonss1.github.io/nplgis/>

---

## The 3D map — Festival Walk floor exits

`apps/festival-walk-3d/` is the flagship. It is a self-contained ArcGIS JS scene:

- Each floor of Festival Walk (又一城) is a separate GeoJSON layer.
- Every layer is lifted to its **own absolute height** — MTR level (0 m), LG2, LG1, G, UG —
  so the exits fan out up the hillside in the colour of the floor they belong to.
- The ground is real terrain (Esri WorldElevation3D); Festival Walk's floor sits at
  about 58 m, with Lion Rock at 495 m directly behind it.
- Click any line to see the official attributes from the source dataset.

Open `apps/festival-walk-3d/index.html` directly, or serve the repo root and visit
`/apps/festival-walk-3d/`. It needs WebGL3.

**Rebuild the scene data** from the CSDI API:

```bash
python3 scripts/build_festival_walk_3d.py
```

That queries the official FeatureServer for `BuildingID 1108222840` and writes
`apps/festival-walk-3d/data/*.geojson`.

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
  data/                         Source data, geocoded layers, flat CSVs
    pedestrian/                 3D pedestrian network, split by WeatherProof/Location
    festival-walk/              Festival Walk + Kowloon Tong layers
    volleyball/                 Venues, sessions, usage, districts, shoreline
    mtr/                        Fare savers, MTR lines and stations
    walk/                       Restaurant catchments
apps/
  festival-walk-3d/             The 3D scene (index.html + per-floor GeoJSON)
scripts/                        Every build and render script, made portable
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
