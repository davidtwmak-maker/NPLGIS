# Student Worksheets — GIS Projects

Six task sheets built from the NPL GIS Team's real GIS projects, for secondary
students and CSDI Awards entrants.

**Start with** `Student Worksheets — GIS Projects.md` — that is the index, with the
level and the "what question does it answer" for each.

| File | Project | The question |
|---|---|---|
| `Student Worksheet — 3D Pedestrian Network and Covered Walkways.md` | Covered Walkways | Can you walk across Hong Kong without getting wet? |
| `Student Worksheet — Volleyball Courts Booking Data.md` | Volleyball Courts | When is it easiest to get a volleyball court? |
| `Student Worksheet — 15-Minute Walk Catchment.md` | 15-min walk | What can you reach from a school in 15 minutes on foot? |
| `Student Worksheet — Festival Walk 3D Mall Model.md` | Festival Walk 3D | How do you get between floors in a mall built into a hillside? |
| `Student Worksheet — Building Heights in 3D.md` | 3D Buildings | What does a city look like when you can see its height? |
| `Student Worksheet — MTR Fare Saver Map.md` | MTR Fare Saver | Which neighbourhoods have no fare-saver mall within a short walk? |

## What each worksheet gives the student

1. The question, stated in one sentence.
2. Where the data comes from — dataset, provider, CSDI id, service URL, record count.
3. The method, step by step, with the specific tool and settings.
4. **The check numbers** — what a correct run produces, so a wrong run is caught
   instead of quietly producing a wrong conclusion.
5. The trap in that dataset, named.
6. The assumptions to re-run three ways.
7. A data validation statement in the competition's own format.
8. Limitations to declare.
9. An extension task, and the AI disclosure to write.
10. A checklist, and the working files to compare against.

## Provenance

Every live figure was **re-verified against the source service on 26 Oct 2026** —
the CSDI Portal, the SmartPLAY open-data feed, the GeoInfo Map REST service, and
Esri WorldElevation3D Terrain3D. The Sham Shui Po building-height statistics were
independently recomputed from `B1K_Bldg` rather than copied.

Where a figure has **drifted** since the underlying project note was written, the
worksheet says so — the SmartPLAY booking window moves daily, so students'
decimals will differ from the project notes while the structure of the result
holds.

## Corrections applied

Two LCSD dataset ids were swapped in the source project notes and have been fixed
in the vault, with dated correction notes in both files:

- *Sports Centres* — `lcsd_rcd_1629267205215_31341` (106 records)
- *Beach volleyball courts* — `lcsd_rcd_1670383539632_8620` (7 records)

## Data and scripts

Everything the worksheets point at lives in this repository:

- `assets/data/` — the GeoJSON and CSV layers (also gzipped for the large ones)
- `scripts/` — the data-build and analysis scripts, including
  `build_vertical_3d.py` and `build_buildings_3d.py` for the 3D model
- `apps/festival-walk-3d/` — the live 3D mall model
- `notes/` — the full provenance notes for each dataset
- `maps/` — the finished maps

---

*Data © HKSAR Government (LCSD, CSDI Portal, Lands Department). Terms:
non-commercial use with attribution.*
