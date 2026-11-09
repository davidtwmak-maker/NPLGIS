# Fishing lights and the Hong Kong stargazing season

**A 15-year satellite study (2012-2026) of the seasonal light pollution from bright-light fishing over Hong Kong, and what it means for when to go stargazing.**

---

## The question

Hong Kong's Marine Department designates **16 areas in Hong Kong waters where bright-light fishing is permitted**. The law sets no month limit — a vessel may use lights for fishing there all year.

But there is a well-known seasonal pattern. Every summer, the mainland's South China Sea fishing moratorium runs from **1 May to 16 August**. Trawler fleets that cannot work the main fishing grounds concentrate in Hong Kong's eastern and southern waters instead, and their deck lights are visible from the shore. Local reporting has long linked the glow over the city's south and east to the moratorium months.

That creates a practical question for anyone planning a night outdoors in Hong Kong:

> **Which months are the fishing lights worst for stargazing, and which are best?**

This study answers it with satellite night-lights data, 15 years deep.

---

## The headline finding

**The fishing areas brighten from June onwards and peak in autumn — not during the moratorium itself.**

| Month | Fishing-light signal | Note |
|---|---|---|
| Jan | -0.95 | dark |
| Feb | -0.83 | dark |
| Mar | -1.20 | dark |
| **Apr** | **-1.48** | **darkest month** |
| May | -0.62 | moratorium begins |
| Jun | +0.08 | |
| Jul | +0.89 | |
| Aug | +0.89 | |
| **Sep** | **+1.52** | **brightest month** |
| Oct | +0.86 | |
| Nov | +1.05 | |
| Dec | -0.20 | |

Values are the change in night-sky brightness attributable to the fishing areas, in VIIRS day/night band display units (DN), relative to the rest of Hong Kong waters in the same month.

**The recommendation inverts the common assumption.** People expect the worst months to be May-August, because that is when the moratorium is on and the press coverage is loudest. The data says the fishing areas are actually at their *darkest* relative level in April and their *brightest* in September.

The mechanism is straightforward once seen: the moratorium does not stop the fleets working — it **moves them**. From May the fleets shift into Hong Kong waters and the lights come with them, so brightness climbs from June. But the fleets disperse again in September, and the residual, longer-lived haze and the autumn transition leave September the brightest month overall. The moratorium is the *cause* of the summer rise, not the *peak* of it.

**Practical advice:** for the darkest skies in the east and south of Hong Kong, go in **March and April** (best), or **December to February**. Avoid **July to November**, with **September** the worst month.

This advice applies specifically to the east and south of Hong Kong — Sai Kung, Mirs Bay, Port Shelter, Lantau South, Deep Bay. The urban north is dominated by the city's own glow and shows no useful seasonal variation.

---

## The data

| Source | Identifier | What it is |
|---|---|---|
| NASA GIBS, VIIRS Day/Night Band | `VIIRS_SNPP_GapFilled_BRDF_Corrected_DayNightBand_Radiance` | Night-time light radiance, 2012-01-19 to 2026-11-02. **693 usable nights**, 4 per month across 15 years. |
| Marine Department | `mardep_rcd_1730952503222_38811` | The 16 permitted bright-light fishing areas |
| Agriculture, Fisheries and Conservation Department | `afcd_rcd_1697167244880_33192` | Distribution of fishing operations (356 grids) — also used to define HK waters |

**Why this layer.** The `GapFilled_BRDF_Corrected` product serves continuously from January 2012. The `At_Sensor_Radiance` products used in the earlier camping study only serve from March 2024, which is too short for a seasonal study. The gap-filled product is the longest continuous night-lights record NASA GIBS offers.

**Coverage:** 697 of 720 requested nights returned usable data; 23 were blank (GIBS returns an empty raster for dates it cannot serve). A blank raster is *not* a dark night, and is discarded rather than treated as zero light.

---

## The method, and the trap in it

### The trap

The permitted fishing polygons **overlap coastal land**. A naive mean over the 16 polygons is dominated by the city's own glow on those land pixels — it produced a meaningless "excess" of +96 DN units, which was really Hong Kong's street lighting.

### The fix

1. **Water pixels only.** The analysis runs only on pixels inside the AFCD fishing-operation grids, which define Hong Kong's waters. This removes 298 of the 207,496 permitted-area pixels — few, but they carried the city glow.
2. **Matched control, same pixels.** The comparison is *permitted water* minus *other Hong Kong water*. Both scenes experience the same haze, cloud and atmospheric scattering, so the scene-wide seasonal drift cancels.
3. **Open sea as an independent third check.** A control set of open-sea cells that stay dark on every one of the 693 nights, more than 20 km from the city and more than 1.5 km from every permitted area.
4. **Per-cell monthly composites.** Each pixel's monthly value is the mean of all that month's nights (about 55-60 nights per month). Cloud-contaminated nights average out; a per-cell composite is far more robust than a per-night mean.

### What the corrected numbers are

| Quantity | Value |
|---|---|
| Permitted areas (water), May-Aug minus Sep-Apr | **+1.07 DN** |
| Other Hong Kong water, same comparison | +0.61 DN |
| Open-sea control | -0.58 DN |
| **Attributable to the fishing areas** | **+0.46 DN** |
| 95% CI (naive pixel bootstrap) | [+0.44, +0.49] |
| vs open sea | +1.65 DN, CI [+1.60, +1.70] |

### The honest uncertainty

A bootstrap over 207,000 pixels treats them as independent observations, which they are not. The **correct** uncertainty is a **block bootstrap over the 15 years**:

- Mean of per-year estimates: **+0.42 DN**, standard error 0.38
- Year-block bootstrap 95% CI: **[-0.29, +1.14]**
- t = 1.11, **p = 0.29** — the *mean brightness* change is **not** significant on its own
- Leave-one-year-out: the mean stays positive (+0.26 to +0.57) in every case

### The statistic that IS robust

The mean is a poor statistic here because a single bright boat is diluted across a 750 m pixel. The **fraction of pixels that brighten appreciably** is far more sensitive and far more robust:

| Per-year statistic | Value |
|---|---|
| Pixels brightening by >=5 DN, permitted areas | 14.9% |
| Same, other Hong Kong water | 7.7% |
| **Enrichment** | **1.17x** |
| Year-block bootstrap 95% CI | **[1.05, 1.30]** |
| t = 17.5, **p < 0.0001** | |
| Years with enrichment > 1 | **12 of 15** |

**This is the finding that holds.** The moderately brightened pixels — the fishing boats themselves — are about **17% more common inside the permitted areas than in comparable Hong Kong waters**, and that holds in 12 of 15 years with a confidence interval that excludes 1.

By contrast, the very brightest pixels (>=20 DN change) are *not* enriched (0.74x) — the brightest things in the scene are city lights and major roads, not boats.

---

## Which areas are affected

Per-area attributable change (May-Aug minus Sep-Apr, water pixels only):

| Area | May-Aug | Sep-Apr | Change |
|---|---|---|---|
| Hong Kong Island (South) | 42.6 | 33.0 | **+9.04** |
| Hong Kong Island (South) | 41.8 | 35.3 | **+5.83** |
| Castle Peak | 226.3 | 222.0 | +3.76 |
| Deep Bay | 134.5 | 130.3 | +3.55 |
| The Soko Islands and West Lamma Channel | 90.4 | 86.6 | +3.22 |
| Hong Kong Island (South) | 154.6 | 152.0 | +1.96 |
| South Lantau | 59.2 | 57.0 | +1.57 |
| Hong Kong Island (South) | 141.9 | 140.9 | +0.41 |
| East Lantau | 113.0 | 112.1 | +0.35 |
| Mirs Bay, Tolo Harbour and Port Shelter | 56.4 | 55.5 | +0.27 |
| The Soko Islands and West Lamma Channel | 33.3 | 33.1 | -0.37 |
| South Lantau | 82.5 | 82.3 | -0.41 |
| Tseung Kwan O or Junk Bay | 202.7 | 203.0 | -0.84 |
| North Lantau | 167.7 | 169.1 | -2.10 |

The seasonal swing is strongest in the **south of Hong Kong Island** and along the **western** waters (Deep Bay, Castle Peak), and weakest at Mirs Bay and Tseung Kwan O — those sit close enough to the urban core that the city's own glow dominates their absolute level and masks the fishing signal.

Mirs Bay nonetheless carries the **largest absolute fishing effort**: about **28,400 vessels** (46% of all vessels operating inside permitted areas) overlap the Mirs Bay / Tolo Harbour / Port Shelter polygons, with another 15,425 around the Soko Islands and West Lamma Channel. Its low *seasonal* signal reflects a high *baseline*, not low activity.

---

## Confounder checks

- **Moonlight.** The open-sea control shows no relationship with moon phase (control mean 13.6 for moon <40%, 10.0 for moon >80% — the difference runs the opposite way to the signal). Moonlight cannot generate the result.
- **Cloud and haze.** The control is subtracted on the same pixels and the same nights, so scene-wide atmospheric variation cancels by construction. The remaining open-sea control shift (-0.58 DN) shows the raw scene does drift seasonally, which is exactly why the matched-water comparison is used for the headline.
- **Geometry.** The permitted areas are rasterised with the same transform as the source rasters, verified against the raster bounds with a 1e-6 tolerance.
- **Sensor drift.** SNPP is a single stable platform across the whole 2012-2026 period, so no cross-sensor calibration step is needed. 2021 shows the largest positive year (+2.59 DN) and 2019 the largest negative (-1.68 DN), so inter-annual noise exceeds the signal — which is why the year-block bootstrap, not the pixel bootstrap, is the honest uncertainty.

---

## Limitations

1. **8-bit display values.** VIIRS day/night band products served through GIBS are relative brightness values, not physical radiance in nW/cm2/sr. True radiance needs the Black Marble VNP46A2 product from LAADS DAAC, which requires an Earthdata login.
2. **750 m pixels.** VIIRS DNB is 375-750 m per pixel at this latitude. A single lit fishing vessel is diluted. The bright-pixel enrichment statistic is used precisely because it is more sensitive than the mean.
3. **Attribution.** The satellite shows that pixels inside the permitted areas brighten relative to comparable waters. It cannot prove the cause is the fishing lights rather than, for example, a change in mainland vessel routing that happens to correlate with the same season. The spatial concentration inside the designated polygons and the 12-of-15-year consistency are consistent with the fishing interpretation, but they are not proof.
4. **The mean change is not statistically significant.** Only the bright-pixel enrichment is. Any claim that the *average* sky brightness over the fishing areas rises by a given amount during the moratorium is not supported.
5. **Hong Kong's own moratorium differs from the mainland's.** Hong Kong has run a trawl-net moratorium since 1999, extended to 1 May - 15 August (3.5 months) from 2017. It is not the same instrument as the mainland's South China Sea moratorium, and the two do not align perfectly in every year.

---

## Files

| File | What it is |
|---|---|
| `HK_fishing_light_seasonal_map.png` | The three-panel figure |
| `fishing_light_seasonal.json` | Every result number, machine-readable |
| `fishing_light_monthly.csv` | The monthly recommendation table |
| `seasonal_nights.json` | Per-night measurements for all 693 nights |
| `fetch_seasonal.py` | Downloads the GIBS nights, builds the composites and the control |
| `analyse_fishing_light.py` | The analysis, the block bootstrap and the per-area breakdown |
| `make_fishing_light_map.py` | The figure, with the text-overlap and off-canvas gate |
| `raw_seasonal/` | The 697 nightly rasters (GeoTIFF, EPSG:4326) |

## Reproducing

```bash
python fetch_seasonal.py        # ~8 min, caches to raw_seasonal/
python analyse_fishing_light.py # per-cell composites, bootstrap, per-area table
python make_fishing_light_map.py
```

`fetch_seasonal.py` re-uses any night already cached in `raw_seasonal/`, so re-running after a partial failure is cheap.

### Technical notes for anyone extending this

- **GIBS WMS 1.3.0 with EPSG:4326 takes the bbox in LAT,LON order** (S,W,N,E). Passing longitude first returns a valid but empty raster.
- **A GIBS blank is HTTP 200 with an all-zero raster**, not an error. It must be discarded, not treated as darkness.
- **`scipy.ndimage.distance_transform_edt`** returns a plain array in scipy 1.18 but a `(distance, indices)` tuple in older versions. Pass the sampling in kilometres so the result is already in km.
- **`threading.Lock` is not reentrant.** Calling a logging helper that takes the same lock from inside a `with lock:` block deadlocks the pool silently — the process sits at 0% CPU with all threads blocked.
- **GIBS time extents are in the GetCapabilities XML** as `<Dimension name="time">`. Read them rather than probing dates one at a time.
