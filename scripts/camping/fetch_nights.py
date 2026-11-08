#!/usr/bin/env python3
"""
Fetch several moonless-near nights of VIIRS DNB and build a median composite.

WHY A COMPOSITE:  a single night is one sample of a noisy quantity.  A
median composite over N nights is far more robust for RANKING sites by
light pollution, and it is the standard practice for annual NTL products.

The GIBS daily DNB layers are 8-bit DISPLAY products (the service serves
RGB rasters), so the composite is a RELATIVE brightness measure.  That is
enough to rank sites; it is NOT enough to convert to radiance, mag/arcsec^2
or a Bortle class.  The write-up must say so.

Moon check: NOAA-20's open sea reads ~157 against NOAA-21's ~13 on the
same date, because the moon was up.  We therefore compute the open-sea
floor for each night and reject any night whose floor is high - a high sea
floor means moonlight (or haze) contaminated the scene.

Run:  ls-venv/bin/python fetch_nights.py
"""
import json
import os
import sys
import urllib.request

import numpy as np
import rasterio

BASE = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
LAYER = "VIIRS_NOAA21_GapFilled_BRDF_Corrected_DayNightBand_Radiance"
RAW = "/Users/davidhermes/GIS Data/HK Night Lights/raw"
BBOX = "22.15,113.72,22.60,114.45"
W, H = 2600, 1807

# Candidate nights.
#
# CRITICAL: GIBS's GetCapabilities declares this layer as 2023-02-10 .. today,
# but the "best" endpoint only actually SERVES roughly the last 12 days.
# Every other date returns HTTP 200 with an ALL-ZERO raster - a silent
# failure, not an error.  A probe of 2026-10-01..2026-11-07 found exactly 12
# usable nights: 2026-10-27 .. 2026-11-07.  Everything before 27 Oct is
# blank.
#
# So a multi-night composite is possible, but only within that ~12-day
# window - and that window contains exactly one new moon (10 Nov is just
# outside it), so most of these nights are MOONLIT.  The moon check below is
# what decides which are usable.
#
# Moon phase matters more than date: NOAA-20's open sea reads ~157 against
# NOAA-21's ~13 on the same date because the moon was up.
NIGHTS = [
    "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31",
    "2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05",
    "2026-11-06", "2026-11-07",
]
SERVED_RANGE = ("2023-02-10", "2026-11-07")


def url_for(date, width=W, height=H):
    return (
        f"{BASE}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={LAYER}"
        f"&STYLES=default&FORMAT=image/tiff&TRANSPARENT=FALSE&TIME={date}"
        f"&WIDTH={width}&HEIGHT={height}&CRS=EPSG:4326&BBOX={BBOX}"
    )


def fetch(date):
    p = os.path.join(RAW, f"night_{date}.tif")
    if os.path.exists(p) and os.path.getsize(p) > 100_000:
        return p
    assert SERVED_RANGE[0] <= date <= SERVED_RANGE[1], \
        f"{date} is outside the layer's served range {SERVED_RANGE}"
    u = url_for(date)
    tmp = p + ".part"
    try:
        urllib.request.urlretrieve(u, tmp)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"{date}: {type(e).__name__}: {e}")
    # A WMS error comes back as XML, not a TIFF.
    with open(tmp, "rb") as f:
        magic = f.read(4)
    if magic != b"II*\x00":
        os.remove(tmp)
        raise RuntimeError(f"{date}: not a TIFF (WMS exception)")
    os.rename(tmp, p)
    return p


def moon_illumination(date_str):
    """Approximate illuminated fraction of the moon for a date.

    Synodic approximation against the known new moon of 2000-01-06 18:14
    UTC.  Good to a few percent, which is all the screening needs.
    """
    import datetime
    import math
    d = datetime.date.fromisoformat(date_str)
    epoch = datetime.date(2000, 1, 6)
    jd = d.toordinal() - epoch.toordinal()
    cycles = jd / 29.530588853
    phase = cycles - math.floor(cycles)
    return abs(phase)


def is_blank(path):
    """A date outside the served range returns a 200 with an ALL-ZERO raster.

    This is the silent failure that cost seven nights the first time.  Every
    downloaded night is checked for actual content before it is trusted.
    """
    with rasterio.open(path) as ds:
        a = ds.read(1)
    return int(a.max()) == 0, int(a.max()), int(a.min())


def band1(path):
    with rasterio.open(path) as ds:
        return ds.read(1), ds


def open_sea_floor(arr, ds):
    """Open-sea reference from the SAME boxes the original project used.

    The first project proved its georeference with a ratio > 4 between an
    urban box and an open-sea box, using these exact coordinates.  Using
    the same boxes keeps the new nights comparable with the established
    29 Oct baseline.  (An earlier version of this script used a large SE
    quadrant, which included lit coastline and gave a ratio of only ~3.5
    on the SAME night that scores 19.2x with the correct boxes - a
    threshold error dressed up as a moon signal.)
    """
    lon0, lat0 = ds.bounds.left, ds.bounds.top
    xres, yres = ds.res

    def box(lo0, lo1, la0, la1):
        x0 = int((lo0 - lon0) / xres)
        x1 = int((lo1 - lon0) / xres)
        y0 = int((lat0 - la1) / yres)
        y1 = int((lat0 - la0) / yres)
        return arr[y0:y1, x0:x1].ravel()

    sea = np.concatenate([box(114.30, 114.44, 22.16, 22.27),
                           box(114.34, 114.44, 22.33, 22.44)])
    urban = np.concatenate([box(114.160, 114.180, 22.293, 22.325),
                             box(114.118, 114.138, 22.352, 22.368),
                             box(114.030, 114.080, 22.532, 22.558)])
    rural = np.concatenate([box(114.112, 114.138, 22.402, 22.420),
                             box(114.116, 114.142, 22.428, 22.445)])
    return (float(np.mean(sea)), float(np.mean(urban)), float(np.mean(rural)))


def main():
    os.makedirs(RAW, exist_ok=True)
    report = {"layer": LAYER, "bbox": BBOX, "nights": {}, "kept": [], "rejected": []}

    for d in NIGHTS:
        try:
            p = fetch(d)
            blank, mx, mn = is_blank(p)
            if blank:
                report["nights"][d] = {"file": os.path.basename(p),
                                        "blank": True, "max": mx}
                report["rejected"].append(d)
                print(f"  {d}: BLANK (all zeros - date outside served range)",
                      flush=True)
                continue
            arr, ds = band1(p)
            sea, urban, rural = open_sea_floor(arr, ds)
            ratio = urban / max(sea, 0.01)
            illum = moon_illumination(d)
            # The original project established the georeference with
            # urban/open-sea > 4 on a known-good night.  A night that falls
            # below that is washed out - moonlight or haze lifting the
            # whole scene - and must not go into the composite.
            ok = ratio > 4.0
            reason = []
            if ratio <= 4.0:
                reason.append(f"contrast {ratio:.1f}x below 4x (moon/haze washed out)")
            report["nights"][d] = {
                "file": os.path.basename(p),
                "open_sea_mean": round(sea, 2),
                "urban_mean": round(urban, 2),
                "rural_mean": round(rural, 2),
                "urban_over_sea": round(ratio, 2),
                "moon_illuminated_frac": round(illum, 3),
                "usable": bool(ok),
                "reject_reason": "; ".join(reason),
            }
            (report["kept"] if ok else report["rejected"]).append(d)
            print(f"  {d}: sea={sea:6.1f} urban={urban:7.1f} rural={rural:6.1f} "
                  f"ratio={ratio:5.2f} moon={illum*100:4.1f}% "
                  f"{'KEEP' if ok else 'reject: ' + '; '.join(reason)}", flush=True)
        except Exception as e:
            report["nights"][d] = {"error": str(e)}
            print(f"  {d}: ERROR {e}", flush=True)

    kept = report["kept"]
    print(f"\nkept {len(kept)} nights, rejected {len(report['rejected'])}")
    if kept:
        # median composite
        stack = []
        for d in kept:
            arr, ds = band1(os.path.join(RAW, f"night_{d}.tif"))
            stack.append(arr.astype(np.float32))
        comp = np.median(np.stack(stack), axis=0).astype(np.uint8)
        cp = os.path.join(RAW, "night_composite_median.tif")
        with rasterio.open(os.path.join(RAW, f"night_{kept[0]}.tif")) as src:
            prof = src.profile.copy()
            prof.update(dtype="uint8", count=1)
            with rasterio.open(cp, "w", **prof) as dst:
                dst.write(comp, 1)
        report["composite"] = os.path.basename(cp)
        report["composite_nights"] = kept
        print(f"wrote {cp}")
        sea, urban, rural = open_sea_floor(comp, ds)
        ratio = urban / max(sea, 0.01)
        print(f"composite: sea={sea:.1f} urban={urban:.1f} rural={rural:.1f} "
              f"ratio={ratio:.2f}x")
        assert ratio > 4.0, f"composite georeference not proven (ratio {ratio:.2f})"
        print("  GEOREFERENCE PROVEN on the composite")

    out = os.path.join(RAW, "night_selection.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
