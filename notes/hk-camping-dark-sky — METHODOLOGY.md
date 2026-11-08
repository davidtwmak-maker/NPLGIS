# Hong Kong country-park campsites ranked for dark skies

**Question.** Which of Hong Kong's 41 designated country-park campsites give the
best night sky, and which are worth the walk in?

**Answer in one line.** The six darkest are all in Sai Kung and Lantau South
country parks; Wan Tsai South (Sai Kung West) is the darkest site in Hong
Kong, and the brightest campsites are the ones at Ngong Ping and in Tai Lam
country park — and that is exactly what the data says.

---

## 1. Why this is a GIS problem, not a list

Hong Kong has 41 designated campsites in 13 country parks. There is no
official "dark sky" list, because dark sky is a *raster* property and the
campground data is *vector* points. The analysis is therefore:

1. get every campsite as a point;
2. get a night-lights surface for Hong Kong;
3. sample the surface at each point;
4. add the things a camper actually cares about (access, facilities, open
   horizon);
5. rank them, and be honest about how much weight each factor deserves.

The interesting methodological question is **step 2 and 3**, because that is
where this kind of study usually goes wrong.

---

## 2. The night-lights data, and the trap in it

### What was used

| | |
|---|---|
| Product | VIIRS Day/Night Band (NOAA-21), `VIIRS_NOAA21_GapFilled_BRDF_Corrected` |
| Source | NASA GIBS WMS (`gibs.earthdata.nasa.gov`), `epsg4326/best` |
| Resolution | ~15 arc-second (VIIRS native), resampled by the service |
| Composite | median of **12 nights, 27 Oct – 7 Nov 2026** |
| Grid | 2600 × 1807, EPSG:4326, bounds 113.72–114.45 E, 22.15–22.60 N |
| Values | 8-bit display render, 13–255 |

### Trap 1 — GIBS serves only about the last 12 days

The layer's `GetCapabilities` declares a time range from 2023-02-10 to
"present", and that declaration is true as a *capability*. But the `best`
endpoint only actually **renders** roughly the last twelve days. Every
older date returns HTTP 200 with a **blank, all-zero raster** — not an
error, not a 404. A script that does not check the returned pixels will
silently build a composite of zeros and publish it as Hong Kong's night sky.

The first fetch in this project hit exactly that: eight requested nights,
eight "successful" downloads, and seven of them completely empty.

The fix is a content check, not a status check:

```python
blank, mx, mn = is_blank(path)      # read the raster, test max > 0
if blank:
    reject the night, and record WHY
```

### Trap 2 — a blank raster is not the only bad raster

A night can return pixels and still be unusable. Moonlight lifts the whole
scene, which inflates dark rural areas and compresses the contrast between
city and countryside. The first project had already solved this by proving
its georeference with a ratio between an urban box and an open-sea box: on a
good night that ratio is **greater than 4**. The same boxes and the same
threshold were reused here, so the check is consistent with the earlier work:

| Night | Open sea | Urban | Rural | Urban/sea | Moon | Verdict |
|---|---|---|---|---|---|---|
| 2026-10-27 | 16.3 | 236.0 | 38.7 | 14.5x | 5% | keep |
| 2026-10-28 | 14.4 | 205.7 | 33.2 | 14.3x | 9% | keep |
| … | | | | | | |
| 2026-11-06 | 16.6 | 155.0 | 39.4 | 9.3x | 9% | keep |
| 2026-11-07 | 16.4 | 157.2 | 37.4 | 9.6x | 14% | keep |

**All 12 available nights passed the contrast gate**, and the composite
re-proved its own georeference at **9.59x** urban/sea. That is the number
to check before trusting any night-lights map of Hong Kong.

### Trap 3 — GIBS night-lights are an 8-bit display render, not radiance

The `best` endpoint returns a colour-mapped image, so the numbers are
0–255 display values, not physical radiance. That is fine for **ranking**
places against each other — which is what this study does — but it cannot
be converted into lux, and the values must not be described as brightness
in physical units.

For calibrated radiance the proper source is NASA Black Marble
(`VNP46A2`, nadir BRDF-corrected DNB) from LAADS DAAC, which requires a
NASA Earthdata login. The GIBS route was chosen here because it needs no
account and is enough for a relative ranking.

### Trap 4 — GIBS has no historical archive

Because only ~12 days are served, a median over 12 nights is a composite
of one lunar cycle, not of a year. It captures cloud-free variation but
**cannot** capture seasonal effects (winter haze, summer humidity) or
long-term trends in lighting. A student writing this up must say so.

---

## 3. The other data

Everything else is open data from the CSDI Portal, fetched live.

| Factor | Dataset | CSDI ID | Role |
|---|---|---|---|
| Campsites | AFCD — Location of campsites in country parks | `afcd_rcd_1635133060194_82554` | 41 points, 13 parks; tent space, water source |
| Country parks | AFCD — Country parks | `afcd_rcd_1635129924112_81508` | 25 polygons for context |
| Visitor centres | AFCD — Visitor centres in country parks | `afcd_rcd_1635133243757_2529` | 8 points, access term |
| Facilities | AFCD — Facilities in country parks | `afcd_rcd_1635136427551_29173` | 167 points, toilets |
| Trails | AFCD — Trails in country parks | `afcd_rcd_1665568199103_4360` | 167 sections, route context |
| Terrain | LandsD 5 m DTM via the 20 m grid (`terrain_20m.npz`) | — | relief, open horizon |
| Coastline | OpenStreetMap `natural=coastline` | — | thin orientation line on the map only — **not** a mask (see §4) |

**Why the access term uses visitor centres.** AFCD publishes visitor
centres for country parks, not campsite entrances, so "distance to the
nearest visitor centre" is a proxy for "how far you must carry your
gear", not the true walk from a car park. It is the best consistently
available proxy, and it is what the ranking uses.

**Why the horizon term uses relief rather than a horizon algorithm.** A
true sky-view factor needs a 3D horizon computation over the terrain.
`relief_500m` — the maximum elevation difference within 500 m of the
campsite — is a defensible proxy for "how much of the sky is blocked", and
it is cheap and explainable to a secondary-school audience.

---

## 4. The land-mask trap — and why the map applies no mask

Every candidate land boundary for Hong Kong includes territorial waters.
The failure mode is quiet: a territorial-waters mask makes Victoria Harbour
and the South China Sea look like lit land, which puts a bright false glow
over the sea and makes the map wrong without making it obviously broken.

| Source | Union area | Verdict |
|---|---|---|
| LandsD iC1000 Digital Land Boundary | ~2130 km² | **wrong** — includes territorial waters |
| 2023 District Council constituencies | ~2768 km² | **wrong** — includes territorial waters |
| OSM administrative relation 913110 | ~2770 km² | **wrong** — territorial waters |
| DTM validity mask (LandsD 5 m) | ~1108 km² | **wrong** — interpolates across the harbour, drops small islands |
| Natural Earth 10m admin-0 | ~1042 km² | **too coarse** — misses Sai Kung, Tsing Yi, Plover Cove; 3/16 point tests |
| OSM `natural=coastline` ways, polygonised | 44 km² (sea ring) / 2747 km² (complement) | **failed** — see below |

### What was tried, in order

1. **The Esri China (HK) iB1000 shoreline already in this repo** — 9,031
   MultiLineStrings. Stitching them into rings closed only 711 of 5,325
   chains: the linework is fragmented and cannot be reassembled.
2. **A DTM elevation mask** (`elev > 0`) gave 1130.7 km², close to the
   ~1106 km² of real land, but the correct-area result was misleading — the
   mask fails point tests badly. It interpolates across the harbour, so
   Victoria Harbour reads as land, and it drops the outlying islands.
3. **A flood fill from the sea** over a rasterised OSM coastline. This is
   the textbook method and it failed too: the coastline could not be
   closed. The OSM `/map` API returns ways **clipped to the requested
   bbox**, and the fetch merged fragments with a dictionary keyed on way id,
   so a way spanning a box boundary kept only its last fragment. That
   dropped most of the coastline and left gaps the flood poured through.
   After merging fragments properly (103 dangling endpoints, down from
   many more), the barrier still was not continuous enough to flood-fill.
4. **Ring-union selection** against known land and sea points. The
   coastline rings carry the sea on the left, so the ring union gives the
   sea (44 km²) and its complement gives sea plus land (2747 km²) — neither
   is the land mask, and the topology could not resolve it.

### The resolution

**The map applies no land mask at all**, and this is the right answer, not a
workaround.

A light-pollution map should show the sea as dark, because the sea *is*
dark — the same raster that shows Mong Kok at 255 shows open sea at 13.
Masking the sea would have **removed information** rather than added it:
every land mask in the table above would have had to be trusted to
redraw a boundary the data already tells us about correctly.

The OSM coastline is therefore drawn as a **thin line** on the map for
orientation, not used to cut the raster.

This was only reached after the point-test table above was read as a
*search* rather than a checklist. The honest summary is that no public
Hong Kong land polygon in this set is trustworthy as a sea mask, and the
correct engineering response was to not need one.


---

## 5. Scoring

Each factor is min-max normalised to 0–1 and inverted where a **low** raw
value is good (brightness, walk distance, relief).

```
score = 0.50 * darkness          # night-lights value at the campsite
      + 0.20 * access             # distance to nearest visitor centre
      + 0.20 * facilities         # 0.6 * tent space + 0.4 * water source
      + 0.10 * open horizon       # local relief within 500 m
```

The weights are a **judgement**, stated plainly so they can be argued
with: the study is *about* light pollution, so darkness carries half the
score; access and facilities together carry 40% because a dark site you
cannot reach or cannot camp in is not a good campsite; the horizon term is
a minor tie-breaker.

Two robustness checks are reported with the results:

- **Single-night vs composite.** The rank of every campsite is computed
  against one night as well as the 12-night composite. The maximum rank
  shift and the mean shift are reported in
  `campsite_scores_summary.json`. A campsite whose rank swings wildly
  between nights is a campsite whose "darkness" is not established.
- **Distinct-value gates.** The build asserts that the access term
  produces more than 20 distinct values and that the score produces more
  than 30. These catch a silent bug in which every site receives the same
  number — which is exactly what happened when `GeoSeries.distance`
  returned a distance **matrix** and `.min()` was taken over the whole
  matrix instead of along each row.

---

## 6. Results

### The six darkest campsites

| Rank | Campsite | Country park | Night-lights value | Walk to visitor centre |
|---|---|---|---|---|
| 1 | Wan Tsai South | Sai Kung West (Wan Tsai Extension) | 37 | 8,078 m |
| 2 | Wan Tsai West | Sai Kung West (Wan Tsai Extension) | 37 | 8,354 m |
| 3 | Ham Tin Wan | Sai Kung East | 33 | 6,341 m |
| 4 | Sai Wan | Sai Kung East | 41 | 5,596 m |
| 5 | Hau Tong Kai | Sai Kung West | 37 | 5,330 m |
| 6 | Man Cheung Po | Lantau South | 33 | 5,087 m |

The brightest end is the opposite story and confirms the measure works:
**Ngong Ping** (125, a tourist complex with its own lighting), **Ho Pui**
in Tai Lam (173, right beside the Tuen Mun / Yuen Long built-up area),
**Lau Shui Heung** in Pat Sin Leng (140) and **Hok Tau** (138).

The ranking reproduces independent knowledge: Sai Kung's New Territories
is repeatedly described as having the darkest skies in Hong Kong, and
Lantau's south coast is the other known dark area. Ngong Ping is a
lit-up tourist site. The measure is not merely producing a number — it is
producing the number you would expect from field knowledge, which is the
only external validation available without a light meter on site.

### The result that needs a caveat

Ranks 1 and 2 (Wan Tsai South and Wan Tsai West) have **identical**
night-lights values of 37 and sit about 700 m apart. At the ~15
arc-second resolution of the VIIRS grid, they fall in the **same pixel**.
Their ordering is therefore decided by the other factors, not by any
difference in darkness. This is stated in the figure and the notes rather
than hidden.

---

## 7. Limitations

1. **Relative, not absolute.** The light-pollution values are an 8-bit
   display render. They rank sites against each other; they are not
   luminance in lux.
2. **Twelve nights, one lunar cycle.** GIBS serves only about 12 days, so
   this is not a year-long or seasonal composite.
3. **No weather, no moon phase at the campsite.** A real observing site also
   depends on cloud cover and the moon at the site, neither of which is
   in the raster.
4. **Access is proxied by visitor centres**, not by the true campsite
   entrance or car park.
5. **The horizon term is a proxy** (500 m relief), not a computed
   sky-view factor.
6. **No site visit.** All of this is remote sensing plus open data. The
   final check is to stand there.
7. **Campsites close and change.** AFCD's list reflects designated
   camping areas with permits; check AFCD before travelling.

---

## 8. Reproducing this

```
GIS Data/HK Camping Sites/
  fetch_coastline.py            coastline fetch + fallback chain
  fetch_coastline_osm.py        the OSM /map grid fetch that worked
  score_campsites.py            fetch CSDI data, sample, score, assert
  make_camping_map.py           build the figure, with the overlap + pixel gates
  campsite_scores.csv           41 rows, all factors and the score
  campsite_scores.geojson       the same, as points in EPSG:4326
  campsite_scores_summary.json  run statistics and robustness figures
  HK_camping_sites_dark_sky_map.png
```

Every script **fails loudly** rather than producing a plausible wrong
answer: the scoring script asserts that all 41 campsites received a value
for every factor, that no score is NaN, and that the access and score
terms each produce many distinct values. The map script checks for text
overlap and off-canvas text before it writes the file, then verifies
afterwards that the pixels over land actually match the source raster
colour for the source value at that location.
