# Hong Kong country-park campsites ranked for dark skies

**Question.** Which of Hong Kong's 41 designated country-park campsites give
the best night sky, and which are worth the walk in?

**Answer.** The six darkest are all in Sai Kung and Lantau South country
parks. Wan Tsai South (Sai Kung West) is the darkest site in Hong Kong; the
brightest campsites are Ngong Ping and Ho Pui in Tai Lam, which sit beside
lit-up tourist and built-up areas.

## What was used

| Layer | Source | ID |
|---|---|---|
| 41 campsites | AFCD — Location of campsites in country parks | `afcd_rcd_1635133060194_82554` |
| 25 country parks | AFCD — Country parks | `afcd_rcd_1635129924112_81508` |
| 8 visitor centres | AFCD — Visitor centres in country parks | `afcd_rcd_1635133243757_2529` |
| 167 facilities | AFCD — Facilities in country parks | `afcd_rcd_1635136427551_29173` |
| 167 trail sections | AFCD — Trails in country parks | `afcd_rcd_1665568199103_4360` |
| Night lights | VIIRS Day/Night Band NOAA-21, NASA GIBS | 12-night median, 27 Oct – 7 Nov 2026 |
| Terrain | LandsD LiDAR DTM 2020 via CSDI, 20 m grid | `terrain_20m.npz` |

## The four traps in this study

**1. GIBS serves only about the last 12 days.** The layer declares a time
range from 2023, but the `best` endpoint only *renders* roughly the last
twelve days. Every older date returns HTTP 200 with a **blank, all-zero
raster** — not an error. The first fetch here requested eight nights and
seven came back empty. The fix is a content check, not a status check:
read the raster and test `max > 0` before trusting it.

**2. A blank raster is not the only bad raster.** Moonlight lifts the whole
scene and flattens the contrast between city and countryside. The gate used
here is the one established by the earlier HK Night Lights project: the
ratio between an urban box and an open-sea box must exceed 4. On the final
composite that ratio is **9.59x**, and all 12 nights ranged 7.9x–13.8x, so
the georeference is proven rather than assumed.

**3. GIBS night lights are an 8-bit display render, not radiance.** They
rank places against each other; they are not lux and must not be described
as physical brightness. For calibrated radiance you need NASA Black Marble
`VNP46A2` from LAADS DAAC, which requires an Earthdata login.

**4. Every official Hong Kong land-boundary dataset includes territorial
waters.** The LandsD iC1000 "Digital Land Boundary" unions to ~2130 km²
against ~1106 km² of real land. The 2023 District Council constituencies
union to ~2768 km². The OSM administrative relation 913110 gives ~2770 km².
The DTM validity mask interpolates the harbour; Natural Earth 10m is too
coarse and misses Sai Kung, Tsing Yi and Plover Cove entirely.

**The map therefore applies no land mask at all**, and the sea is shown
dark — which is correct, because the sea *is* dark (open sea 13, Mong Kok
255 in the same raster). Masking would have removed information rather
than added it. The OSM coastline is drawn as a thin line for orientation.

## Scoring

```
score = 0.50 * darkness          # VIIRS DNB value at the campsite
      + 0.20 * access             # distance to nearest visitor centre
      + 0.20 * facilities         # 0.6 * tent space + 0.4 * water source
      + 0.10 * open horizon       # local relief within 500 m
```

Darkness carries half the weight because the study is *about* light
pollution. Access and facilities together carry 40% because a dark site
you cannot reach, or cannot camp in, is not a good campsite. The weights
are a stated judgement so they can be argued with.

## Results

### The six darkest

| Rank | Campsite | Country park | DNB value | Walk to visitor centre |
|---|---|---|---|---|
| 1 | Wan Tsai South | Sai Kung West (Wan Tsai Extension) | 37 | 8,078 m |
| 2 | Wan Tsai West | Sai Kung West (Wan Tsai Extension) | 37 | 8,354 m |
| 3 | Ham Tin Wan | Sai Kung East | 33 | 6,341 m |
| 4 | Sai Wan | Sai Kung East | 41 | 5,596 m |
| 5 | Hau Tong Kai | Sai Kung West | 37 | 5,330 m |
| 6 | Man Cheung Po | Lantau South | 33 | 5,087 m |

The bright end confirms the measure works: **Ngong Ping** (125 — a lit
tourist complex), **Ho Pui** in Tai Lam (173 — beside the Yuen Long built-up
area), **Lau Shui Heung** in Pat Sin Leng (140), **Hok Tau** (138).

This reproduces independent knowledge. Sai Kung's New Territories is
repeatedly described as having the darkest skies in Hong Kong, Lantau's
south coast is the other known dark area, and Ngong Ping is a lit tourist
site. Getting the expected answer from data you did not steer is the only
external validation available without a light meter on site.

### Two results that need a caveat

Ranks 1 and 2 have **identical** DNB values of 37 and sit about 700 m
apart, so at ~15 arc-second resolution they fall in the **same pixel**.
Their order is decided by the other factors, not by any difference in
darkness. Stated in the figure rather than hidden.

## Robustness and limitations

- **Single-night vs composite:** the maximum rank shift is **14 places**
  and the mean is **3.63** across all 41 campsites. A site whose rank swings
  wildly between nights is a site whose darkness is not established.
- The composite covers one lunar cycle, so it captures cloud-free
  variation but **not** seasonal haze or long-term lighting trends.
- Access is proxied by **visitor centres**, not the true campsite entrance.
- The horizon term is a **proxy** (500 m relief), not a computed sky-view
  factor.
- No site visit. This is remote sensing plus open data; the final check is
  to stand there.

## The build fails loudly

Both scripts assert rather than produce a plausible wrong answer:

`score_campsites.py` asserts all 41 campsites received a value for every
factor, that no score is NaN, that the access term produces more than 20
distinct values, and that the score produces more than 30. That last pair
exists because `GeoSeries.distance` returns a **matrix** between two
GeoSeries — taking `.min()` over the whole matrix gives one global minimum
and every campsite the same value, silently.

`make_camping_map.py` checks for text overlap and off-canvas text **before**
writing the file, then verifies afterwards that the rendered pixels over the
bright city, the dark country and the dark sea each match the colour the
source raster should produce at that location. That check exists because an
earlier version **transposed** the raster — mirroring the map across the
diagonal so Mong Kok's bright core was drawn over Sai Kung. The map looked
entirely plausible and was completely wrong.

## Files

```
assets/data/camping/campsite_scores.geojson.gz     41 scored campsites
assets/data/camping/night_lights_composite.tif     VIIRS 12-night median
assets/data/camping/campsite_scores.csv             all factors and scores
assets/data/camping/campsite_scores_summary.json    run statistics
assets/maps/camping-sites/HK_camping_sites_dark_sky_map.png
```

Build scripts are in `scripts/camping/`; the full method write-up is in
`notes/hk-camping-dark-sky — METHODOLOGY.md` (the longer version, including
the four land-mask attempts that failed), and the shorter summary is
`notes/hk-camping-dark-sky — NOTES.md` (this file).
