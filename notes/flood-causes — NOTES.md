# HK Flood Causes — Flash Flood and Storm Surge — Method Note

**Working folder:** `~/GIS Data/HK Flood Causes/`
**Fetched:** 9 November 2026 — every endpoint probed live, every count
verified against the served values.
**Study area:** the 267 Drainage Services Department flood-prone areas
(226 blockage + 15 drainage works in progress + 26 coastal low-lying or
windy).

This note covers the **two non-blockage flooding mechanisms** in Hong
Kong: **flash flood** (rainfall-driven) and **storm surge**
(sea-level-driven). The DSD's own Strategic Planning Study on Flood
Management (**CE 77/2021**, December 2025) names these as the territory's
dual threat.

---

## 1. The factors

### Flash flood

| # | Factor | Measurement | Weight |
|---|---|---|---:|
| F1 | Rainfall intensity | Daily maximum at the nearest GEO gauge, normalised on the HK record 24-hour rainfall (**956.0 mm**, Tai Mo Shan, 21–22 July 1994) | 0.30 |
| F2 | Low-lying ground | DTM elevation; score falls linearly from 20 m to 0 m | 0.25 |
| F3 | Steep catchment | DTM slope (40 m block-mean of the 5 m DTM) | 0.15 |
| F4 | Drainage capacity | Count of DSD stormwater inlets within 200 m; score **falls** as the count rises | 0.15 |
| F5 | Channel surcharge | Distance to the nearest major engineered channel; score falls from 0 to 1 km | 0.10 |
| F6 | Outlet restriction | Distance to the nearest outfall; score falls from 0 to 3 km | 0.05 |

### Storm surge

| # | Factor | Measurement | Weight |
|---|---|---|---:|
| S1 | Low-lying ground | DTM elevation; score falls linearly from 10 m to 0 m | 0.40 |
| S2 | Distance to the sea | Distance to the CEDD coastline; score **falls** as the distance grows to 2 km | 0.25 |
| S3 | Wave exposure | CEDD wave climate HMAX at the nearest station (KYC / WLC), normalised on HK's 10 m design wave | 0.20 |
| S4 | Tidal range | Local tidal range at the nearest HKO tide station | 0.15 |
| S5 | Designated coastal area | Distance to the nearest of the **26 CEDD Coastal Hazards Study areas**; score falls from 0 to 1.5 km | — |
| S6 | Defence assets | DSD pumping stations and inflatable dams within 500 m — a **mitigation** multiplier of up to 30% | — |

Missing factors are handled by **renormalising** the remaining weights,
so a point with no nearby outfall is not penalised for it.

**Dominant hazard** = whichever score is higher.

---

## 2. The result

| DSD list | Areas | Mean flash-flood | Mean storm-surge | Flash flood | Storm surge |
|---|---:|---:|---:|---:|---:|
| Locations Prone to Blockage | 226 | 0.47 | 0.34 | 197 | 29 |
| Drainage Improvement Works In Progress | 15 | 0.46 | 0.37 | 11 | 4 |
| Coastal Low-lying or Windy Residential Areas | 26 | 0.54 | **0.60** | 7 | **19** |
| **All** | **267** | — | — | **215** | **52** |

Flash flood 0.27–0.65 (median 0.49); storm surge 0.10–0.80 (median 0.35).
These are **relative indices, not probabilities**.

**The three lists are three different flooding problems.** The blockage
list is flash-flood dominated and sits a median 671 m from the sea; the
coastal list is storm-surge dominated, sits a median 16 m from the sea at
a median elevation of 5 m, and still carries a *higher* mean
flash-flood score than the blockage list — low flat ground ponds rain as
well as taking seawater.

---

## 3. The datasets

| Dataset | CSDI ID | Records | Role |
|---|---|---:|---|
| GEO raingauge daily | `cedd_rcd_1636517963140_47030` L0 | 1,126,191 rows / 95 gauges / 1984–2026 | F1 |
| DSD stormwater channel | `dsd_rcd_1629267205231_66675` L1 | 9,247 lines | F5 |
| DSD stormwater inlet | `dsd_rcd_1629267205231_69065` L0 | 1,221 points | F4 |
| DSD stormwater manhole | `dsd_rcd_1629267205232_64331` L0 | 78,525 points | network density |
| DSD stormwater pipes | `dsd_rcd_1629267205232_85526` L0 | 107,204 lines | trunk capacity |
| DSD outfalls | `dsd_rcd_1629267205232_35872` L0 | 15 points | F6 |
| Catchwater / surface channels | `hyd_rcd_1632359687762_99131` L0 | 23,489 lines | channel context |
| WSD catchment & subcatchment | `wsd_rcd_1629267205232_5923` L0 | 1,223 polygons | drainage catchment |
| CEDD wave data | `cedd_rcd_1636518176374_67772` L0 | 376,191 hourly rows / 2 stations | S3 |
| CEDD geological coastline | `cedd_rcd_1636520962284_7237` L0 | 193 polygons | S2 |
| Marine Dept tide stations | `mardep_rcd_1638860616268_1438` L0 | 5 points | S4 |
| HKO predicted tide (hourly / high-low) | `hko_rcd_1634808062104_80740`, `hko_rcd_1634809240679_79523` | 15 + 15 | tide context |
| HKO sea-level & pressure | `hko_rcd_1634954951621_38375` L0 | 12 points | surge driver |
| HKO wind | `hko_rcd_1634953844424_88011` L0 | 30 points | surge driver |
| DSD facilities | `dsd_rcd_1629267205232_11360` L0 | 407 points | S6 |
| Typhoon shelters | `mardep_rcd_1730971403590_9667` L0 | 14 points | refuge context |
| Harbour limit | `mardep_rcd_1730972646896_40009` L0 | 4 features | marine context |
| LandsD DTM 5 m | direct zip (below) | 9,601 × 12,751 grid | F2, F3, S1 |

**DTM:** `https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip`
→ 28.7 MB zip → `Whole_HK_DTM_5m.asc` (HK1980 origin 799997.5 / 799997.5,
NODATA −9999, **six-line header** — `np.loadtxt` needs `skiprows=6`).

**The 26 coastal areas** come from DSD's own coastal list, not from CSDI
`cedd_rcd_1640249339500_66807` (which holds only Tung Chung).

---

## 4. The traps

1. **The raingauge `Rainfall` field is TEXT.** Values carry quality
   markers (`'12.5'` clean, `'12.5#'` provisional, `'***'` missing), so a
   server-side `max` is a **string comparison** and returns **99.5 for
   every gauge**. Compute the extremes locally.
2. **Use the whole rainfall record.** The 2020+ subset (213,570 rows)
   makes 622.5 mm look like the record; the full record is 1,126,191 rows
   back to 1984 and contains **875.5 mm at Tsuen Wan, 22 July 1994**. The
   published territory record is **956.0 mm in 24 hours at Tai Mo Shan,
   21–22 July 1994** (GEO Report No. 314, Table 10.1) — use that as the
   normaliser.
3. **The full record has no geometry**, and its attributes sit under
   `attributes`, not `properties`. `merge_rain_locations.py` joins it with
   the coordinates from the 2020 file.
4. **`landsd_rcd_1637223499176_68379` is NOT a land boundary** — it is the
   iC1000 map-sheet catalogue, 2,130 km² against Hong Kong's real
   ~1,106 km². Use the CEDD coastline (193 polygons, 1,092 km²).
5. **WSD `Shape__Area` is in square metres** even though the layer is
   served in lon/lat (verified against an EPSG:2326 shoelace measurement,
   max relative difference 2.0e-09).
6. **The 1,223 WSD catchments are SECTION polygons** (median 0.026 km²),
   not whole catchments.
7. **The DTM ASCII grid stores the northern edge first.**
   `row = (YLL + nrows*cell - Y) / cell`.
8. **The wave dataset's `YEAR` field is a misnamed timestamp**
   (`'26/1/1994 15:00'`). The station is in `LOCATION`.
9. **CSDI attributes arrive under `properties`** once converted to
   GeoJSON.
10. **Group by the exact field value.** The `dsd_list` value is
    `"Drainage Improvement Works In Progress"` — matching a remembered
    phrase returns zero rows and silently drops a table row.
11. **The CSDI designated-area layer holds ONE polygon, not 26.**
12. **Check the sign of every factor against a place you know.** Three
    were wrong at first (distance to the sea rose with distance; the inlet
    count rose with count; wave exposure applied territory-wide) and the
    results still looked plausible. The tell is the top-scoring place
    names.

---

## 5. Files

```
HK Flood Causes/
├── fetch_flood_causes.py      21 layers, paginated
├── fetch_rain_full.py         the complete 1,126,191-row rain record
├── merge_rain_locations.py    full record + gauge coordinates -> one file
├── derive_terrain_factors.py  Horn slope + D8 flow accumulation
├── derive_flood_factors.py    the 267 scores
├── make_flood_causes_map.py   the figure
├── gate_flood_causes_map.py   the gate - must pass
└── out/
    ├── flood_hazard_factors.geojson   267 points, every factor
    ├── flood_hazard_factors.csv
    ├── factor_summary.json
    └── HK_flood_causes_map.png
```

**The build gate** checks: file size and pixel variance; every text box
inside the canvas; no text-over-text overlap above 30% of the smaller box;
no marker under a text box; pixel probes on the saved PNG confirming each
panel contains sea, land and its own point colours; and the panel C table
checked against the source layer so no row can vanish silently.

---

## Related

- `notes/hk-flood-prone-areas — NOTES.md` — the three DSD lists and the
  derived-mechanism work this extends
- `notes/landslide-susceptibility — NOTES.md` — the same factor-analysis
  discipline applied to landslides
