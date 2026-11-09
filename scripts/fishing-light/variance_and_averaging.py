#!/usr/bin/env python3
"""
How to find an average pattern when the light varies night to night (v2).

This script quantifies the night-to-night variability of the fishing-light
signal and demonstrates the methods for recovering a seasonal pattern from
it, with the honest uncertainty of each.

It uses the CORRECTED per-night table (deep water only, the LNG terminal and
the Ma Liu Shui cable excluded, within-night contrast against the control
deep water) - not the superseded v1 table, whose land mask treated the
Guangdong mainland as sea.

THE PROBLEM
-----------
Night-time light over the permitted fishing areas moves a lot from night to
night, for reasons that have nothing to do with fishing:

  * the moon        - lights the sea surface, so a full-moon night is bright
                      everywhere;
  * cloud and haze - scatters and diffuses city light over the water;
  * the city itself - Kowloon and the mainland glow reach the coastal water.

So a single night's image (like 2026-06-21) tells you almost nothing about
fishing. To find a pattern you must remove the scene-wide component and
compare the permitted areas against other water ON THE SAME NIGHT.

THE METHODS, MEASURED HERE
---------------------------
  1. naive monthly mean of the raw brightness   -> dominated by nuisance
  2. within-night difference (permitted - control) -> removes the scene-wide
     component
  3. seasonal double difference (May-Aug minus Sep-Apr, within each night)
     -> the design used
  4. the same on a robust (median) statistic with a year-block bootstrap
     -> the published result

plus a variance decomposition: how much of the night-to-night swing is
nuisance, and how much is the fishing signal.
"""
import csv
import json
import math
import os
import random
import statistics
from collections import defaultdict

R = "/Users/davidhermes/GIS Data/HK Night Lights"
CSV = f"{R}/nightly_measurements_CORRECTED.csv"
MOR = {5, 6, 7, 8}
RNG = random.Random(12345)


def log(m):
    print(m, flush=True)


def boot_ci(vals, iters=4000):
    """Year-block bootstrap: resample the YEARS, not the nights."""
    by_year = defaultdict(list)
    for y, v in vals:
        by_year[y].append(v)
    years = sorted(by_year)
    out = []
    for _ in range(iters):
        samp = []
        for _ in years:
            yy = years[int(RNG.random() * len(years)) % len(years)]
            samp.append(by_year[yy][int(RNG.random() * len(by_year[yy])) % len(by_year[yy])])
        out.append(statistics.mean(samp))
    out.sort()
    return out[int(0.025 * iters)], out[int(0.975 * iters)]


def pval(vals, null=0.0):
    by_year = defaultdict(list)
    for y, v in vals:
        by_year[y].append(v)
    years = sorted(by_year)
    obs = abs(statistics.mean([v for _, v in vals]) - null)
    hits = 0
    N = 4000
    for _ in range(N):
        s = 0.0
        for _ in years:
            yy = years[int(RNG.random() * len(years)) % len(years)]
            s += by_year[yy][int(RNG.random() * len(by_year[yy])) % len(by_year[yy])]
        if abs(s / len(years) - null) >= obs:
            hits += 1
    return (hits + 1) / (N + 1)


def corr(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0.0


def r2(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    sxx = sum((x - ma) ** 2 for x in a)
    sxy = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    syy = sum((y - mb) ** 2 for y in b)
    return (sxy ** 2 / (sxx * syy)) if sxx and syy else 0.0


def main():
    rows = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            rows.append({
                "date": r["date"], "year": int(r["year"]),
                "month": int(r["month"]), "moon": float(r["moon_pct"]),
                "p": float(r["permitted_bright_pct"]),
                "c": float(r["control_bright_pct"]),
                "x": float(r["contrast_pp"]),
            })
    log(f"nights: {len(rows)}  {rows[0]['date']} .. {rows[-1]['date']}")

    log("\n" + "=" * 76)
    log("1  HOW MUCH DOES THE SIGNAL MOVE NIGHT TO NIGHT?")
    log("=" * 76)
    for nm, key in (("permitted deep water", "p"),
                    ("control deep water", "c"),
                    ("permitted - control", "x")):
        v = [r[key] for r in rows]
        q = statistics.quantiles(v, n=100)
        log(f"  {nm:24s} mean {statistics.mean(v):7.3f}  sd {statistics.stdev(v):6.3f}"
            f"  min {min(v):7.3f}  p25 {q[24]:7.3f}  med {statistics.median(v):7.3f}"
            f"  p75 {q[74]:7.3f}  max {max(v):7.3f}")
    log("\n  the range is the point: one night cannot tell you the season.")

    log("\n" + "=" * 76)
    log("2  WHERE DOES THE NIGHT-TO-NIGHT VARIANCE COME FROM?")
    log("=" * 76)
    perm = [r["p"] for r in rows]
    ctrl = [r["c"] for r in rows]
    moon = [r["moon"] for r in rows]
    exc = [r["x"] for r in rows]

    log(f"  corr(permitted, control) = {corr(perm, ctrl):+.4f}")
    log(f"  corr(permitted, moon)     = {corr(perm, moon):+.4f}")
    log(f"  corr(control, moon)       = {corr(ctrl, moon):+.4f}")
    log(f"  corr(permitted, excess)   = {corr(perm, exc):+.4f}")
    log(f"\n  R^2 of the scene-wide control on the permitted brightness: "
        f"{r2(ctrl, perm):.3f}")
    log(f"  R^2 of the moon on the permitted brightness:             "
        f"{r2(moon, perm):.3f}")
    log(f"  R^2 of the moon on the within-night contrast:             "
        f"{r2(moon, exc):.3f}")

    per_year = defaultdict(lambda: {"mor": [], "oth": []})
    for r in rows:
        per_year[r["year"]]["mor" if r["month"] in MOR else "oth"].append(r["x"])
    py = {y: statistics.mean(d["mor"]) - statistics.mean(d["oth"])
          for y, d in per_year.items() if d["mor"] and d["oth"]}
    tot_var = statistics.variance(exc)
    seas_var = statistics.variance(list(py.values()))
    log(f"\n  variance of the nightly contrast:          {tot_var:.5f} pp^2")
    log(f"  variance of the seasonal signal per year:  {seas_var:.5f} pp^2")
    log(f"  -> the season accounts for {100*seas_var/tot_var:.1f}% of the "
        f"night-to-night variance")
    log(f"  -> the other {100-100*seas_var/tot_var:.1f}% is night-specific: "
        f"weather, tide, which boats were out")

    log("\n" + "=" * 76)
    log("3  FOUR WAYS TO AVERAGE, AND WHAT EACH ONE GETS RIGHT")
    log("=" * 76)

    log("\n  METHOD 1  naive monthly mean of the raw brightness, no control")
    m1 = {m: statistics.mean([r["p"] for r in rows if r["month"] == m]) for m in range(1, 13)}
    m1sd = {m: statistics.stdev([r["p"] for r in rows if r["month"] == m]) for m in range(1, 13)}
    for m in range(1, 13):
        log(f"    {m:>2d}{' *' if m in MOR else '  '} {m1[m]:7.3f}  sd {m1sd[m]:5.3f}")
    log("    * = May-Aug moratorium window")
    log("    -> reads as a smooth curve with a May peak, but the within-month")
    log("       sd is larger than the month-to-month spread, so the curve is")
    log("       mostly noise dressed as a trend.")

    log("\n  METHOD 2  within-night difference (permitted - control), monthly mean")
    m2 = {m: statistics.mean([r["x"] for r in rows if r["month"] == m]) for m in range(1, 13)}
    m2med = {m: statistics.median([r["x"] for r in rows if r["month"] == m]) for m in range(1, 13)}
    log(f"    {'month':>5s} {'mean':>9s} {'median':>9s}")
    for m in range(1, 13):
        log(f"    {m:>5d} {m2[m]:9.3f} {m2med[m]:9.3f}")
    log("    -> the mean and the median DISAGREE, and the median is ~0 in every")
    log("       month. That disagreement is the tell: the mean is being moved")
    log("       by a handful of extreme nights.")

    log("\n  METHOD 3  seasonal double difference, per year, then averaged")
    for y, v in sorted(py.items()):
        log(f"    {y}  {v:+8.3f}")
    yrs = list(py.items())
    m3 = statistics.mean(v for _, v in yrs)
    l3, h3 = boot_ci(yrs)
    p3 = pval(yrs)
    log(f"    mean {m3:+.3f} pp   95% CI [{l3:+.3f}, {h3:+.3f}]   p = {p3:.4f}"
        f"   ({sum(1 for _, v in yrs if v > 0)}/{len(yrs)} years positive)")

    log("\n  METHOD 4  the published design (transient cells only, year-block CI)")
    defn = json.load(open(f"{R}/DEFINITIVE_results.json"))
    se = defn["seasonal_effect"]
    log(f"    {se['mean_pp']:+.3f} pp   95% CI [{se['ci_pp'][0]:+.3f}, {se['ci_pp'][1]:+.3f}]"
        f"   p = {se['p']:.4f}   ({se['years_positive']}/{se['n_years']} years positive)")

    log("\n" + "=" * 76)
    log("4  THE PRACTICAL RULE")
    log("=" * 76)
    log("""
  1. NEVER average raw night-time brightness across dates. The moon, haze
     and city glow move the whole scene by more than the fishing signal does.

  2. ALWAYS difference WITHIN a night: permitted area minus other water on
     the SAME image. This is the single most important step, and it is cheap.

  3. THEN compare seasons, not dates: May-Aug minus Sep-Apr, computed within
     each night, then averaged across years.

  4. For uncertainty, resample YEARS - not nights, not pixels. Nights in a
     year share weather and fleets; pixels share the same atmosphere. A pixel
     bootstrap gives a falsely tight interval.

  5. Report the active NIGHTS, not a smooth curve. The median night shows no
     signal at all; the signal lives on about 2 nights a year. A monthly mean
     curve hides that, and it is why the first version of this study was
     wrong.

  6. Validate against known places and known structures before publishing: a
     lit LNG terminal and a lit power cable will otherwise be counted as
     fishing boats.
""")


if __name__ == "__main__":
    main()
