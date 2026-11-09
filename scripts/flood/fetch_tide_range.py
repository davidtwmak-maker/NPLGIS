#!/usr/bin/env python3
"""
Fetch the tidal RANGE at each HKO tide station (the S4 storm-surge factor).

The tide factor was declared in the method note but never entered the
score - the station was looked up and reported, and then ignored. This
script fetches the real tidal range so it can be used.

Where the data comes from
-------------------------
The CSDI tide-station layer points at live HKO CSV endpoints:
  predicted high/low times and heights  HLT_<code>_<year>.csv
  predicted hourly heights               HHOT_<code>_<year>.csv
on https://data.weather.gov.hk/weatherAPI/hko_data/csdi/dataset/

The tidal RANGE at a station is the mean diurnal range: the mean of the
high-water heights minus the mean of the low-water heights over the
year. A bigger range means a bigger push of water at the flood tide, so
it is a genuine storm-surge factor.

The 2026 file is used (the current year).

Run:  ls-venv/bin/python fetch_tide_range.py
"""
import csv
import io
import json
import os
import re
import statistics
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out")
YEAR = 2026


def get(url, tries=3, timeout=90):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "hermes-gis-flood"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:                     # noqa: BLE001
            last = e
    raise last


def parse_highlow(text):
    """Return (mean_high, mean_low, n_high, n_low) from an HKO HLT csv.

    The csv has NO high/low marker column - it is
      Year, Month, Day, Hour, Minute, Second, TimeZone, Height(m)
    with the high and low tides listed in time order (two of each per
    day, so a naive "every other row" alternation is WRONG - it starts
    on a low and yields a negative range).

    The high and low tides are separated by the local-extremum test: a
    tide that is at least as high as both of its neighbours is a high
    water, and at least as low as both is a low water. That gives
    627 HW / 626 LW for Cheung Chau, and a diurnal range of 1.08 m -
    which is the right order of magnitude for Hong Kong.
    """
    vals = []
    for row in csv.reader(io.StringIO(text.replace("\ufeff", ""))):
        if len(row) < 8:
            continue
        try:
            vals.append(float(row[7]))
        except (ValueError, IndexError):
            continue
    if len(vals) < 10:
        return None
    highs = [vals[i] for i in range(1, len(vals) - 1)
             if vals[i] >= vals[i - 1] and vals[i] >= vals[i + 1]]
    lows = [vals[i] for i in range(1, len(vals) - 1)
            if vals[i] <= vals[i - 1] and vals[i] <= vals[i + 1]]
    if not highs or not lows:
        return None
    return (statistics.mean(highs), statistics.mean(lows),
            len(highs), len(lows))


def main():
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(RAW, "predicted_tide_highlow.geojson")
    g = json.load(open(src))
    out = {}
    for ft in g["features"]:
        p = ft["properties"]
        name = p.get("TideStation_en")
        url = (p.get(f"PredictedTimesAndHeights_url_{YEAR}")
               or p.get(f"PredictedTimesAndHeights_url_{YEAR - 1}"))
        if not name or not url:
            continue
        try:
            text = get(url)
        except Exception as e:                     # noqa: BLE001
            print(f"  {name:<18} FETCH FAILED: {e}")
            continue
        res = parse_highlow(text)
        if not res:
            print(f"  {name:<18} no usable rows")
            continue
        mean_h, mean_l, nh, nl = res
        rng = mean_h - mean_l
        if rng <= 0:
            print(f"  {name:<18} non-positive range {rng:.2f} - rejected")
            continue
        out[name] = {"mean_high_m": round(mean_h, 3),
                     "mean_low_m": round(mean_l, 3),
                     "tidal_range_m": round(rng, 3),
                     "n_high": nh, "n_low": nl,
                     "source_url": url,
                     "year": YEAR}
        print(f"  {name:<18} range {rng:5.2f} m  (H {mean_h:.2f} / "
              f"L {mean_l:.2f}, {nh} HW {nl} LW)")

    p = os.path.join(OUT, "tide_ranges.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {p}  ({len(out)} stations)")
    if out:
        r = [v["tidal_range_m"] for v in out.values()]
        print(f"  range across stations: {min(r):.2f} - {max(r):.2f} m")


if __name__ == "__main__":
    main()
