# Fishing lights and the Hong Kong stargazing season

**A 15-year satellite study (2012–2026, 693 nights) of the light from bright-light fishing over Hong Kong, and what it means for when to go stargazing.**

> **This note supersedes the first version of this study.** The original analysis was published with a broken land mask and an uncontrolled comparison, and it reported a smooth monthly curve with "September brightest, April darkest". That curve was an artefact. The corrected analysis below says something different and better evidenced: the fishing-light signal is **episodic**, it appears on **a small number of nights**, and those nights cluster in the **May–August moratorium window**. The correction and what caused it are recorded in [§7](#7-why-the-first-version-was-wrong).

---

## The question

Hong Kong's Marine Department designates **16 areas in Hong Kong waters where bright-light fishing is permitted**. The law sets no month limit — a vessel may use lights for fishing there all year.

But there is a well-known seasonal pattern. Every summer the mainland's South China Sea fishing moratorium runs from **1 May to 16 August**. Trawler fleets that cannot work the main fishing grounds concentrate in Hong Kong's eastern and southern waters instead, and their deck lights are visible from the shore. Local reporting has long linked the glow over the city's south and east to the moratorium months.

That creates a practical question for anyone planning a night outdoors in Hong Kong:

> **Which nights are the fishing lights worst for stargazing, and which are best?**

---

## 1. The headline finding

**There is no reliably bright or dark month. The fishing lights are concentrated on a small number of individual nights, and those nights fall mostly in the May–August moratorium window.**

| | |
|---|---|
| Nights analysed | **693** (2012–2026) |
| Nights that carried the signal | **20** — about 2 per year |
| Of those 20, in May–August | **13** (65%) |
| Months with any active night | January (2), April (2), May (5), June (2), July (6), September (1), October (2) |
| Months with **no** active night in 15 years | **February, March, August, November, December** |

The seasonal effect is real but small and intermittent:

| Statistic | Value |
|---|---|
| Seasonal excess of bright deep-water cells inside the permitted areas (May–Aug minus Sep–Apr) | **+0.31 percentage points** |
| Year-block bootstrap 95% confidence interval | **[+0.09, +0.62]** |
| Bootstrap p-value (resampling years) | 0.001 |
| **Exact Wilcoxon signed-rank on the 15 per-year values** | **p < 0.0001** |
| **Exact sign test (10 years positive, 5 negative)** | **p = 0.30** |
| Years showing the effect | 10 of 15 |
| Leave-one-year-out (smallest case, dropping 2018) | **+0.19 pp**, CI [+0.05, +0.32], bootstrap p = 0.009 |
| Leave-one-night-out (dropping the 10 most extreme nights) | **+0.12 pp**, CI [+0.02, +0.23], p = 0.018 |
| Threshold sensitivity, 120 / 140 / 160 / 180 DN | +0.43 / +0.31 / +0.22 / +0.15 pp, p = 0.003 / 0.001 / 0.020 / 0.048 |

**Read the two p-values together.** The Wilcoxon signed-rank test (p < 0.0001) asks whether the positive years tend to be *larger* than the negative years — and they are, because 2018 alone is +2.08 pp. The sign test (p = 0.30) asks only whether *more* years are positive than negative — and 10 of 15 is not enough to be significant on its own. So the effect is **real and driven by a handful of large years, not by a consistent majority of years**. Dropping 2018 leaves +0.19 pp, still positive in 9 of 14 years, still significant by the Wilcoxon test but not by the sign test. That is the honest picture, and it is why the practical advice in §6 is about *nights*, not months.

**Where the estimate is weaker, and why.** At a *lower* brightness threshold (80 or 100 DN) the effect is no longer significant (p = 0.11 and 0.18). The reason is visible in the per-year numbers: 2018 alone contributes **+2.08 pp** against roughly +0.2 to +0.5 in every other year. At low thresholds, faint diffuse glow — haze, bioluminescence, low cloud lit from below — is counted along with vessels, and it swamps the contrast. The 140 DN threshold used throughout was chosen *before* the robustness sweep, on the independent ground that at that level 97% of bright deep-water cells persist across many nights and are therefore structures rather than boats (§4). The honest reading is: **the fishing-vessel signal is real and survives every check at 120 DN and above, and its magnitude is uncertain by roughly a factor of two.**

The effect survives every robustness check at the chosen threshold. It is small because it is rare.

## 2. What the "active nights" were

An **active night** is one on which the permitted areas contained at least 20 more *single-night* bright cells than the control water. The 20 active nights, largest first:

| Night | Month | Extra bright cells | Moon illumination |
|---|---|---|---|
| 2018-05-21 | May | +809 | 33% |
| 2018-07-21 | July | +484 | 54% |
| 2024-07-05 | July | +460 | 3% |
| 2021-04-21 | April | +251 | 64% |
| 2020-07-28 | July | +231 | 51% |
| 2025-05-21 | May | +231 | 39% |
| 2017-01-05 | January | +182 | 44% |
| 2012-04-21 | April | +156 | 0% |
| 2017-01-21 | January | +120 | 43% |
| 2019-06-05 | June | +117 | 4% |

…plus 2018-05-28, 2023-07-05, 2019-07-28, 2016-10-05, 2019-10-21, 2020-07-13, 2025-09-13, 2021-05-21, 2024-06-21, 2020-05-05.

The largest single night, 21 May 2018, put **2,077 bright cells** in the permitted deep water across a **46 km spread** in the Soko Islands and West Lamma Channel — a fleet, not one boat.

## 3. Three independent checks that this really is fishing vessels

**Transient.** A fishing boat is lit on one night. Of the 11,397 distinct bright cells ever seen in the permitted deep water, **5,122 (45%) are lit on exactly one night**. The cells that persist for many nights are fixed structures and were identified and excluded (§4).

**Dark moon.** A vessel is only visible when the sky is dark. The single-night cells inside the permitted areas have a **median moon illumination of 33%**, against 51% for all nights and 55% for the control water's single-night cells. They appear preferentially on dark-moon nights — the opposite of what moonlit cloud tops would do.

**Season.** 76% of the single-night cells inside the permitted areas fall in May–August, against 60% in the control water. Holding moon phase constant, the permitted share stays above the control share in the two darkest moon bands (81% vs 47% at 0–25% illumination; 75% vs 59% at 25–50%).

## 4. What was excluded, and why

Three things could masquerade as fishing lights and were removed before any statistic was computed:

| Excluded | Why | Effect |
|---|---|---|
| **Coastal water within 3 km of land** | City glow reaches it; a fishing boat cannot be distinguished from Kowloon's street lights | The whole analysis is on water ≥ 3 km from land |
| **HK Offshore LNG terminal** (Shek Kwu Chau) | A lit pier and mooring dolphins, 690 m from the Soko Islands cluster | 52.7% of all bright deep-water cells in the permitted areas sat within 3 km of it |
| **Ma Liu Shui–Tung Ping Chau power cable** | A lit cable route | The second bright deep-water cluster, at 114.38°E 22.56°N |

Excluding them **strengthened** the result: +0.24 pp with the LNG terminal included, **+0.28 pp** without it (p < 0.0001).

A separate check confirmed these are structures, not vessels: at a 140 DN threshold, **97% of the bright deep-water cells inside the permitted areas are lit on 5 or more nights** (median 161 of 693 nights). A boat cannot do that.

## 5. Where the vessels were

Only two of the 16 permitted areas produced a detectable signal in deep water:

| Permitted area | Seasonal excess | 95% CI | p | Years positive | Deep-water pixels |
|---|---|---|---|---|---|
| **Mirs Bay, Tolo Harbour and Port Shelter** | **+0.31 pp** | [+0.14, +0.53] | 0.000 | 13/15 | 9,597 |
| **The Soko Islands and West Lamma Channel** | +0.32 pp | [−0.03, +0.77] | 0.082 | 11/15 | 6,945 |

Mirs Bay carries roughly 46% of all fishing effort inside the permitted areas (≈28,400 vessels in the AFCD fishing-operation grids) and is the strongest. **North Lantau, East Lantau, South Lantau, Tseung Kwan O, Deep Bay and Castle Peak showed no significant deep-water signal** — most of those areas hug a coastline bright enough to drown any vessel signal.

## 6. How to find an average when the light changes every night

This section answers the obvious objection: *the light varies night to night, so how can there be an average pattern?*

**A single night carries almost no information.** Over the 693 nights the bright-cell rate in the permitted deep water ranges from **0.000% to 12.556%**, with a median of **0.000%** and a standard deviation of 1.024 pp. More than half of all nights show *literally nothing*. The night-to-night variance is **1.077 pp²**, and the seasonal signal accounts for only **28%** of it. The other 72% is night-specific: weather, tide, and which boats were out.

So you cannot read the pattern off one image. You have to average in a way that cancels the nuisance.

**Step 1 — never average raw brightness across dates.** The naive monthly mean of the raw permitted brightness reads as a smooth curve with a May peak (0.42 pp) and a July peak (0.88 pp). But the within-month standard deviation is *larger* than the month-to-month spread (e.g. May: 0.42 ± 1.70; July: 0.88 ± 2.46). That curve is noise dressed as a trend. This is precisely the mistake that produced the wrong first version of this study.

**Step 2 — difference within each night.** Subtract the control water from the permitted area *on the same image*. This removes the scene-wide component (haze, cloud, the city glow) because it moves both places together. The naive and the differenced curves disagree in shape, which is itself the diagnostic that nuisance was driving the first one.

**Step 3 — compare seasons, not dates.** May–Aug minus Sep–Apr, computed within each night, then averaged across the 15 years. This is a seasonal double difference: it cancels any smooth drift that affects both windows.

**Step 4 — resample years for the uncertainty.** Nights within a year share weather and fleets; pixels share the same atmosphere. A pixel bootstrap over 207,000 pixels gave [+0.44, +0.49] for a statistic whose honest year-block interval is [−0.29, +1.14].

**Step 5 — report the active nights, not a smooth curve.** The monthly **median** of the within-night contrast is ≈0 in every single month, while the monthly **mean** ranges from −0.30 to +0.64. The mean and the median disagreeing is the tell: the mean is being moved by a handful of extreme nights. Plotting the mean makes the fishing signal look like a smooth seasonal wave; it is not.

| Month | mean contrast (pp) | median (pp) | active nights |
|---|---|---|---|
| Jan | −0.13 | −0.18 | 2 |
| Feb | −0.12 | −0.09 | 0 |
| Mar | −0.30 | −0.11 | 0 |
| Apr | +0.01 | −0.02 | 2 |
| May | +0.12 | −0.02 | 5 |
| Jun | +0.00 | −0.06 | 2 |
| Jul | **+0.64** | −0.01 | 6 |
| Aug | −0.06 | −0.10 | 0 |
| Sep | −0.03 | −0.22 | 1 |
| Oct | −0.14 | −0.23 | 2 |
| Nov | −0.21 | −0.24 | 0 |
| Dec | −0.29 | −0.20 | 0 |

**Step 6 — validate against known places and structures.** A lit LNG terminal and a lit power cable will otherwise be counted as boats; both are lit on 5+ nights and must be excluded before any statistic is computed.

The script that produces this table: `scripts/fishing-light/variance_and_averaging.py`.

## 7. Practical advice

The corrected reading of the data:

- **Do not plan around the month.** On a typical night the fishing areas are as dark as the rest of the water. The month tells you very little.
- **Plan around the night.** Only about 2 nights a year carry a big fleet. If you pick a date at random, the probability of hitting one is low.
- **The risk window is May–August**, when 13 of the 20 active nights fell, and the fleets are concentrated in HK waters by the moratorium.
- **February, March, August, November and December had no active night in 15 years** — the safest months on this evidence. (Note that August sits in the middle of the moratorium window and still shows nothing: the fleets concentrate on a handful of dates in May–July, not throughout the closure.)
- **The worst places are the west and east ends** of the permitted area — Soko Islands / West Lamma Channel, and Mirs Bay / Tolo Harbour / Port Shelter. The central and southern parts of the permitted area showed nothing.
- **Use a dark moon.** Vessels are only visible when the sky is dark, so the same fleet matters far more on a moonless night.

## 8. Why the first version was wrong

The first version of this study was published on 2026-11-09 with the conclusion "the fishing areas are darkest in March–April and peak in September", and a monthly table running April −1.48 to September +1.52. That was wrong, for three separate reasons, all of which were caught when the study was re-examined against the screenshot the user supplied.

**1. The land mask was broken.** The "open sea" control was built from `hk_land_boundary.geojson`, a polygon covering only **342 km²** — Hong Kong's land is about 1,106 km². Kowloon, Sha Tin, Tuen Mun, Yuen Long and Sheung Shui all classified as *sea*. The control was therefore largely the Guangdong mainland, whose lights are far brighter than Hong Kong's. The mask was rebuilt from a full OSM coastline (2,139 ways over the frame), rasterised with `all_touched`, dilated 3 px, and flood-filled from an open-sea seed; it is now verified against 14 known places.

**2. The comparison was confounded by distance from land.** Every permitted area hugs the coast. Permitted water sits a mean 1.4 km from land; other Hong Kong water 2.7 km. A raw comparison therefore partly measures "close to the city". The corrected analysis compares only within matched distance bands, and controls the domain to water ≥ 3 km from land.

**3. A pixel bootstrap produced a falsely tight interval.** Resampling 207,000 pixels gave a 95% CI of [+0.44, +0.49] for a statistic whose honest interval, resampled over the 15 **years**, is [−0.29, +1.14]. Pixels within a night are spatially correlated and nights within a year are not independent. Every interval in this study resamples years.

There was also a fourth problem, found during the re-check: the original "bright-pixel enrichment of 1.17×, p < 0.0001" was computed over pixels without any distance control, and the effect it measured did not survive the corrections.

**Nothing in this note rests on the original analysis.** The scripts are listed in §10.

## 9. Method

**Data**
- NASA GIBS, layer `VIIRS_SNPP_GapFilled_BRDF_Corrected_DayNightBand_Radiance` — 693 nights, 2012–2026, at 22.15–22.60°N, 113.72–114.45°E. This is the only VIIRS layer serving continuously from 2012; the `At_Sensor_Radiance` layers used in the camping study begin in March 2024.
- Marine Department permitted bright-light fishing areas (`mardep_rcd_1730952503222_38811`) — 16 polygons.
- AFCD distribution of fishing operations (`afcd_rcd_1697167244880_33192`) — 356 grids with vessel-class counts.
- OSM coastline via Overpass — the land mask.
- Moon phase computed from a known new-moon epoch.

**Design**
1. Land mask: OSM coastline → rasterise (`all_touched`) → dilate 3 px → flood-fill sea from an open-sea seed → verify against 14 places.
2. Domain: sea cells ≥ 3 km from land, minus 3 km around the LNG terminal and the Ma Liu Shui cable.
3. Per night, per cell: bright = DN ≥ 140.
4. **Vessel cells** = cells bright on *exactly one* night. A vessel is lit on one night; a structure is lit on many.
5. Contrast = vessel cells inside the permitted areas minus vessel cells in the control deep water, computed **within each night** so any scene-wide change cancels.
6. Seasonal = May–Aug mean minus Sep–Apr mean, then averaged over years.
7. Uncertainty: **year-block bootstrap**, 4,000 resamples.
8. Robustness: leave-one-year-out, leave-one-night-out, and a sweep of the brightness threshold.

**Known limitations**
- GIBS serves an 8-bit *display* render, not calibrated radiance (the 8-bit DN scale is a contrast stretch). Absolute values are not nW/(cm²·sr); all statistics are relative.
- The 750 m native product is upsampled to ~63 m, so a single boat is spread over many pixels; a "cell" is a fraction of a pixel area, not a vessel.
- One night in 8 is duplicated by the GIBS service itself (confirmed server-side: 2014-08-05 = 2014-08-13, and 2023-05-05 = 2023-05-13). Two of 693 nights are therefore not independent.
- Satellite overpasses are around 13:30 local, so the "night" image is taken at a consistent time and is not a full-night observation.
- The permitted areas are the legal bright-light zones; fishing with lights outside them is illegal, so vessels are assumed to stay inside. This is an assumption, not a measurement.
- A change in mainland vessel routing coinciding with the same season would produce the same signature. The data cannot separate the two.
- 20 active nights is a small sample. The seasonal estimate is real but its magnitude carries wide uncertainty.

## 10. Files and reproducibility

Local: `/Users/davidhermes/GIS Data/HK Night Lights/`

**Running the scripts from a fresh checkout.** The shipped scripts read their
input data from one directory. That directory is now configurable, so the
scripts work on a machine that is not the one they were written on:

```bash
export GIS_DATA_DIR="/path/to/your/data/dir"
python scripts/fishing-light/definitive_analysis.py
```

Without the variable they fall back to the original path, so nothing breaks
for the author. The scripts expect the 693 GeoTIFFs in `raw_seasonal/` and
the two input JSON files; `fetch_seasonal.py` downloads the rasters and
`definitive_analysis.py` does the analysis.

**A note on `fetch_seasonal.py`.** It prints a monthly table of raw
brightness differences. That table is the *superseded* first version of this
study — it measures the city glow on the shore, not fishing vessels, because
the permitted polygons overlap the coast. The script now prints a banner
saying so. The published result comes from `definitive_analysis.py`.

| Script | What it does |
|---|---|
| `fetch_seasonal.py` | Downloads the 693 nightly rasters from GIBS |
| `definitive_analysis.py` | The main analysis: masks, contrast, seasonal double difference, vessel validation, per-area breakdown |
| `final_summary.py` | The active-night list and the biggest-night spatial description |
| `robustness.py` | Leave-one-year-out, leave-one-night-out, threshold sensitivity |
| `check_2023_break.py` | Tests whether the product changed around 2023 |
| `persistence_test.py` | Fixed structure vs moving boat (nights per cell) |
| `moon_phase_test.py` | Dark-moon test on the transient cells |
| `variance_and_averaging.py` | The variance decomposition and the four averaging methods compared |
| `make_corrected_map.py` | The figure |
| `gate_corrected_map.py` | The figure gate: text overlap, off-canvas, pixel probes |

Outputs: `DEFINITIVE_results.json`, `active_nights.json`, `robust_monthly.json`, `robustness.json`, `map_data.json`, `nightly_measurements_CORRECTED.csv`.

Shipped with this note: `HK_fishing_light_seasonal_map_CORRECTED.png`, `fishing_light_seasonal_CORRECTED.json`, `fishing_light_active_nights.csv`, `fishing_light_monthly.csv`, `nightly_measurements.csv.gz`.

## 11. Sources

- NASA GIBS / NASA Black Marble — VIIRS day/night band, Suomi NPP
- Hong Kong Marine Department — areas where bright-light fishing is permitted
- Hong Kong AFCD — distribution of fishing operations
- OpenStreetMap contributors (ODbL) — coastline
