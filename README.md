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
```

`build_festival_walk_3d.py` queries the official FeatureServer for
`BuildingID 1108222840` and writes `apps/festival-walk-3d/data/*.geojson`.
`build_buildings_3d.py` turns those per-floor routes into the 3D floor plates
(`buildings_3d.geojson`), the label anchors (`floor_labels.json`), and the camera
centre in `index.html`.

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
  data/                         Source data, geocoded layers, flat CSVs
    pedestrian/                 3D pedestrian network, split by WeatherProof/Location
    festival-walk/              Festival Walk + Kowloon Tong layers
    volleyball/                 Venues, sessions, usage, districts, shoreline
    mtr/                        Fare savers, MTR lines and stations
    walk/                       Restaurant catchments
apps/
  festival-walk-3d/             The 3D scene (index.html + per-floor GeoJSON + floor plates
                                + the podium that grounds the stack on the hillside)
scripts/                        Every build and render script, made portable
  build_festival_walk_3d.py     Per-floor route GeoJSON from the CSDI FeatureServer
  build_buildings_3d.py         Mall 3D floor plates + label anchors from those routes
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
