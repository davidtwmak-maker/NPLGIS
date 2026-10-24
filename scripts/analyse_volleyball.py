#!/usr/bin/env python3
"""
Volleyball court booking — reproduce every number in
"Volleyball Courts — CSDI & SmartPLAY Data and ArcGIS Recipe".

Run:  python3 analyse_volleyball.py
Needs: only the Python standard library. No GIS software.

Each check prints the expected value from the session note; the script asserts
against it, so if your download differs you find out immediately instead of
quietly writing a wrong conclusion.
"""
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = date(2026, 10, 22)  # the day the feed was pulled


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)["features"]


def pct(fs):
    """% of sessions with at least one court free."""
    if not fs:
        return None
    return sum(1 for s in fs if s["properties"]["available_courts"] > 0) / len(fs) * 100


def lead_days(session):
    """How many days after the snapshot this session is booked for."""
    y, m, d = map(int, session["properties"]["session_date"].split("-"))
    return (date(y, m, d) - SNAPSHOT).days


def check(label, got, expected, tol=0.05):
    ok = got is not None and abs(got - expected) <= tol
    print(f"  {'OK ' if ok else 'FAIL'}  {label:<46} {got:6.1f}%  (expected {expected:.1f}%)")
    return ok


def main():
    venues = load("venues.geojson")
    sessions = load("sessions.geojson")
    free = load("free_outdoor_courts.geojson")

    results = []

    print("\n=== 1. Dataset size ===")
    print(f"  bookable indoor venues : {len(venues):>6,}")
    print(f"  sessions in 8-day feed: {len(sessions):>6,}")
    print(f"  free outdoor / beach   : {len(free):>6,}")
    results.append(len(venues) == 101)
    results.append(len(sessions) == 13152)
    results.append(len(free) == 65)

    print("\n=== 2. Is the price gap real? (the number people quote) ===")
    peak = [s for s in sessions if s["properties"]["price_band"] == "peak"]
    off = [s for s in sessions if s["properties"]["price_band"] == "offpeak"]
    print(f"  full 8-day window   peak {pct(peak):5.1f}% (n={len(peak):,})   "
          f"off-peak {pct(off):5.1f}% (n={len(off):,})")
    results.append(check("peak sessions with vacancy", pct(peak), 7.7))
    results.append(check("off-peak sessions with vacancy", pct(off), 19.8))

    print("\n=== 3. THE TRAP: that gap is an artefact of the booking window ===")
    print("  Split the same sessions by how far ahead they are booked.")
    print("  lead |   sessions | already FULLY booked | vacancy")
    for L in range(8):
        fs = [s for s in sessions if lead_days(s) == L]
        full = sum(1 for s in fs if s["properties"]["available_courts"] == 0)
        print(f"  {L:4d} | {len(fs):10,} | {full / len(fs) * 100:18.1f}% | {pct(fs):6.1f}%")

    near = [s for s in sessions if lead_days(s) <= 6]
    far = [s for s in sessions if lead_days(s) == 7]
    results.append(check("next 6 days, sessions already fully booked",
                         sum(1 for s in near if s["properties"]["available_courts"] == 0) / len(near) * 100, 94.8, 0.1))
    results.append(check("a week out, sessions already fully booked",
                         sum(1 for s in far if s["properties"]["available_courts"] == 0) / len(far) * 100, 19.9, 0.1))

    print("\n=== 4. Re-test the price gap once lead time is held constant ===")
    print("  lead |   peak      |  off-peak    |  gap")
    for L in (0, 1, 4, 5, 6, 7):
        p = [s for s in sessions if lead_days(s) == L and s["properties"]["price_band"] == "peak"]
        o = [s for s in sessions if lead_days(s) == L and s["properties"]["price_band"] == "offpeak"]
        if pct(p) is None or pct(o) is None:
            continue
        print(f"  {L:4d} | {pct(p):5.1f}%    |  {pct(o):5.1f}%     |  {pct(o) - pct(p):5.1f} pp")
    p7 = [s for s in far if s["properties"]["price_band"] == "peak"]
    o7 = [s for s in far if s["properties"]["price_band"] == "offpeak"]
    results.append(check("a week out: peak", pct(p7), 77.6))
    results.append(check("a week out: off-peak", pct(o7), 81.2))
    print("  => at a fixed one-week lead time the peak/off-peak gap nearly vanishes.")
    print("     Lead time, not price band, is what decides bookability.")

    print("\n=== 5. Day of week (naive version) ===")
    dow = defaultdict(lambda: [0, 0])
    for s in sessions:
        dow[s["properties"]["day_of_week"]][1] += 1
        if s["properties"]["available_courts"] > 0:
            dow[s["properties"]["day_of_week"]][0] += 1
    for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        a, b = dow[d]
        print(f"  {d}  sessions {b:6,}   vacancy {a / b * 100:5.1f}%")
    print("  WARNING: 'Thu' looks far better than every other day. It does not.")
    print("  The feed covers 22 and 29 Oct, i.e. TWO Thursdays; the second is still")
    print("  almost empty. Never read a day-of-week table without checking the dates.")

    print("\n=== 6. Where does the vacancy sit? (by district) ===")
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for f in venues:
        agg[f["properties"]["district_en"]][0] += 1
    for f in free:
        d = f["properties"].get("district_en")
        if d:
            agg[d][1] += 1
    for s in sessions:
        d = s["properties"]["district_en"]
        agg[d][2] += 1
        if s["properties"]["available_courts"] > 0:
            agg[d][3] += 1
    print("  district           venues  free  sessions  vacancy")
    for d, (nv, nf, ns, nva) in sorted(agg.items(), key=lambda kv: -kv[1][2]):
        print(f"  {d:<18}{nv:6d}{nf:6d}{ns:10,}{nva / ns * 100:9.1f}%")

    print("\n=== 7. Price and air-conditioning ===")
    print("  ", Counter(f["properties"]["ac_status"] for f in venues))
    print("   published rate card (per hour)")
    print("     air-conditioned      $148 peak / $120 off-peak")
    print("     not air-conditioned   $82 peak /  $57 off-peak")
    print("   47 New Territories venues have NO A/C flag in the feed and are")
    print("   ASSUMED air-conditioned — their price may be wrong.")

    print("\n=== 8. Annual usage (whole arena, not volleyball) ===")
    for yr in (2020, 2021, 2022):
        vals = [f["properties"].get(f"usage_pct_{yr}") for f in venues]
        vals = [x for x in vals if x is not None]
        print(f"  {yr}: n={len(vals):3d}  median {statistics.median(vals):5.1f}%  "
              f"range {min(vals):.0f}–{max(vals):.0f}%")
    excluded = sum(1 for f in venues if f["properties"].get("usage_zero_pct_years_excluded"))
    print(f"  {excluded} venues have an excluded 0% year — reported as null, not 0%.")

    print(f"\n=== {'ALL CHECKS PASSED' if all(results) else 'SOME CHECKS FAILED'} "
          f"({sum(results)}/{len(results)}) ===\n")


if __name__ == "__main__":
    main()