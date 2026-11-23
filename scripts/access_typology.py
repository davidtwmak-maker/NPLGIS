#!/usr/bin/env python3
"""Access typology for the six-district covered-walkway study.

The rule (stated assumption about behaviour, not observed mode choice):

    If the worst-case walk from the nearest MTR exit exceeds 15 minutes
    (Tobler's hiking function per edge + 20% rain penalty), students use
    bus or minibus for access instead of walking.

That splits every school into
    walk-access           <= 15 min walk to the nearest MTR exit
    transit-dependent     >  15 min  -> bus/minibus is the practical access

For every transit-dependent school BOTH access routes are reported, side
by side, as reference:
    the bus/minibus route   normal conditions: walk from the nearest
                           bus/minibus stop, plus how many routes serve it
    the MTR walk           the outage contingency: the forced walk

Service fragility is the number of distinct bus/minibus routes serving the
school's nearest stop, from the TD GTFS feed (stops -> stop_times -> trips ->
routes).  A school with one or two routes and no MTR within walking time is
fragile in normal conditions AND badly exposed in an outage.

Priority score for covered-walkway investment (1 point each):
    + transit-dependent (> 15 min to MTR)
    + service fragility (<= 2 routes at the nearest bus/minibus stop)
    + MTR-walk longest uncovered stretch >= 500 m
    + bus-route longest uncovered stretch >= 200 m
    + climb to the school >= 30 m (hillside)
    tiers: 0-1 low, 2 medium, >=3 high

Outputs (work/):
    access_typology.json        every school, all fields
    access_typology.csv         the same, flat
    access_reference_bus_vs_mtr.csv   the paired reference table (the
                                transit-dependent schools, both routes)
"""

import csv
import json
import math
import os
from collections import Counter, defaultdict

BASE = os.path.expanduser("~/GIS Data/Sun-Rain Exposure")
WORK = os.path.join(BASE, "work")
GTFS = os.path.join(BASE, "raw", "gtfs")

THRESHOLDS = (10, 15, 20)      # minutes; 15 is the rule, others are sensitivity


def log(msg):
    print(msg, flush=True)


def load_gtfs_routes_per_stop():
    """stop_id -> set of route labels ('KMB 1', 'GMB 20020267-ish'...)."""
    route_label = {}
    with open(os.path.join(GTFS, "routes.txt"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            short = (row.get("route_short_name") or "").strip()
            agency = (row.get("agency_id") or "").strip()
            long = (row.get("route_long_name") or "").strip()
            label = "%s %s" % (agency, short) if short else "%s %s" % (agency, long[:20])
            route_label[row["route_id"]] = label
    trip_route = {}
    with open(os.path.join(GTFS, "trips.txt"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            trip_route[row["trip_id"]] = row["route_id"]
    per_stop = defaultdict(set)
    with open(os.path.join(GTFS, "stop_times.txt"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rid = trip_route.get(row["trip_id"])
            if rid:
                per_stop[row["stop_id"]].add(route_label.get(rid, rid))
    return per_stop


def load_stop_names():
    names = {}
    with open(os.path.join(GTFS, "stops.txt"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            names[row["stop_id"]] = row["stop_name"]
    return names


def main():
    schools = json.load(open(os.path.join(WORK, "peninsula_routes_schools.json"), encoding="utf-8"))
    mtr = {r["school_id"]: r for r in
           json.load(open(os.path.join(WORK, "mtr_walk_schools.json"), encoding="utf-8"))}
    log("schools %d | mtr walks %d" % (len(schools), len(mtr)))
    per_stop = load_gtfs_routes_per_stop()
    stop_names = load_stop_names()
    log("gtfs: %d stops with routes" % len(per_stop))

    out = []
    for s in schools:
        m = mtr.get(s["school_id"])
        if not m:
            continue
        # ---- the rule, at 15 min, with 10/20 min sensitivity flags
        typology = "walk-access" if m["walk_minutes"] <= 15 else "transit-dependent"
        # ---- the bus/minibus reference (normal conditions)
        by = s.get("ai_by_type") or {}
        bus_kind = s.get("ai_pti_kind") if s.get("ai_pti_kind") in ("bus", "minibus") else None
        if bus_kind is None:
            for k in ("minibus", "bus"):
                if k in by:
                    bus_kind = k
                    break
        bus = by.get(bus_kind) or {}
        stop_id = bus.get("ai_pti_name")
        routes_at_stop = sorted(per_stop.get(stop_id, ()))
        n_routes = len(routes_at_stop)

        bus_ref = {
            "kind": bus_kind,
            "stop_id": stop_id,
            # TD stop names carry two variants separated by a pipe - keep the first
            "stop_name": (stop_names.get(stop_id) or "").split("|")[0].strip() or None,
            "route_m": bus.get("ai_route_m"),
            "covered_ratio": bus.get("ai_covered_ratio"),
            "longest_exposed_m": bus.get("ai_longest_exposed_m"),
            "n_routes_at_stop": n_routes,
            "routes_at_stop": ", ".join(routes_at_stop[:8]),
        }
        mtr_ref = {
            "station": m["station"], "exit": m["exit"],
            "walk_m": m["walk_m"], "walk_minutes": m["walk_minutes"],
            "covered_ratio": m["covered_ratio"], "longest_exposed_m": m["longest_exposed_m"],
            "climb_m": m["climb_m"],
        }
        # ---- priority score
        score = 0
        reasons = []
        if typology == "transit-dependent":
            score += 1; reasons.append("transit-dependent")
        if bus_kind and n_routes <= 2:
            score += 1; reasons.append("fragile service (%d route%s)" % (n_routes, "s" if n_routes != 1 else ""))
        if m["longest_exposed_m"] >= 500:
            score += 1; reasons.append("MTR gap >= 500 m")
        if (bus.get("ai_longest_exposed_m") or 0) >= 200:
            score += 1; reasons.append("bus gap >= 200 m")
        if m["climb_m"] >= 30:
            score += 1; reasons.append("climb >= 30 m")
        tier = "high" if score >= 3 else ("medium" if score == 2 else "low")

        rec = {
            "school_id": s["school_id"], "name": s["name"], "name_tc": s.get("name_tc"),
            "district": s["district"], "lat": s["lat"], "lon": s["lon"],
            "access": typology,
            "walk_minutes": m["walk_minutes"],
            "access_at_10": "walk-access" if m["walk_minutes"] <= 10 else "transit-dependent",
            "access_at_15": typology,
            "access_at_20": "walk-access" if m["walk_minutes"] <= 20 else "transit-dependent",
            "bus_ref": bus_ref, "mtr_ref": mtr_ref,
            "priority_score": score, "priority_tier": tier, "priority_reasons": "; ".join(reasons),
        }
        out.append(rec)

    json.dump(out, open(os.path.join(WORK, "access_typology.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)

    # flat CSV
    flat_keys = ["school_id", "name", "name_tc", "district", "access",
                 "access_at_10", "access_at_20",
                 "walk_minutes", "priority_score", "priority_tier", "priority_reasons"]
    with open(os.path.join(WORK, "access_typology.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=flat_keys)
        w.writeheader()
        for r in out:
            w.writerow({k: r[k] for k in flat_keys})

    # paired reference table — the transit-dependent schools, BOTH routes
    ref_keys = ["school_id", "name", "name_tc", "district",
                "bus_kind", "bus_stop_name", "bus_stop_id", "bus_route_m",
                "bus_covered_ratio", "bus_longest_exposed_m", "bus_n_routes_at_stop", "bus_routes_at_stop",
                "mtr_station", "mtr_exit", "mtr_walk_m", "mtr_walk_minutes",
                "mtr_covered_ratio", "mtr_longest_exposed_m", "mtr_climb_m",
                "priority_tier"]
    with open(os.path.join(WORK, "access_reference_bus_vs_mtr.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ref_keys)
        w.writeheader()
        for r in out:
            if r["access"] != "transit-dependent":
                continue
            row = {"school_id": r["school_id"], "name": r["name"], "name_tc": r["name_tc"],
                   "district": r["district"], "priority_tier": r["priority_tier"]}
            row.update({"bus_" + k: v for k, v in r["bus_ref"].items()})
            row.update({"mtr_" + k: v for k, v in r["mtr_ref"].items()})
            w.writerow(row)

    # ---- report
    n = len(out)
    for t in THRESHOLDS:
        c = sum(1 for r in out if r["access_at_%d" % t] == "walk-access")
        log("threshold %2d min: walk-access %3d | transit-dependent %3d" % (t, c, n - c))
    dep = [r for r in out if r["access"] == "transit-dependent"]
    log("\npriority tiers (all %d): %s" % (n, dict(Counter(r["priority_tier"] for r in out))))
    log("priority tiers (the %d dependent): %s" % (len(dep), dict(Counter(r["priority_tier"] for r in dep))))
    frag = [r for r in dep if r["bus_ref"]["n_routes_at_stop"] <= 2]
    log("dependent schools with <= 2 routes at the nearest stop: %d" % len(frag))
    log("dependent schools whose nearest stop is not in GTFS: %d"
        % sum(1 for r in dep if r["bus_ref"]["n_routes_at_stop"] == 0))
    log("\nhigh-priority dependent schools:")
    for r in sorted(dep, key=lambda x: (-x["priority_score"], -x["mtr_ref"]["walk_m"])):
        if r["priority_tier"] != "high":
            continue
        log("   %-46s %-22s bus %4.0f m (%d routes) | MTR %4.0f m %2.0f min | %s"
            % (r["name"][:46], (r["mtr_ref"]["station"] or "")[:22],
               r["bus_ref"]["route_m"] or 0, r["bus_ref"]["n_routes_at_stop"],
               r["mtr_ref"]["walk_m"], r["mtr_ref"]["walk_minutes"], r["priority_reasons"]))
    log("\nwrote work/access_typology.json, access_typology.csv, access_reference_bus_vs_mtr.csv")


if __name__ == "__main__":
    main()
