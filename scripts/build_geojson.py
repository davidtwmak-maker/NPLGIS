#!/usr/bin/env python3
"""
Build GeoJSON layers for an HK volleyball-court booking / usage / live-vacancy map.

Inputs (all fetched live 2026-10-22 unless noted):
  1. SmartPLAY live vacancy  https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/volleyball/file
  2. LCSD facility usage (annual)  CSDI lcsd_rcd_1670389615666_788
  3. LCSD free outdoor volleyball courts  CSDI lcsd_rcd_1670383751618_95284
  4. LCSD beach volleyball courts          CSDI lcsd_rcd_1670383539632_8620
  5. 18 DC district boundaries  GeoInfo Map cache LND_DC_POLY_SDO
  6. Official hire charges   lcsd.gov.hk ls_booking_charges_urban / _nt
  7. General holidays        1823 iCal https://www.1823.gov.hk/common/ical/en.json

Output: venues.geojson, sessions.geojson, usage_by_venue.geojson,
        free_outdoor_courts.geojson, districts.geojson, sessions.csv, venues.csv
"""
import csv
import pathlib
HERE = pathlib.Path(__file__).resolve().parent
import datetime as dt
import gzip
import json
import math
import os
import re
from collections import defaultdict

OUT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(OUT, "raw")
SNAPSHOT_DATE = "2026-10-22"

# ---------------------------------------------------------------- hire charges
# Source: LCSD "Hire Charges of Leisure Facilities", Urban and New Territories
# tables, row "Basketball / Volleyball / Netball Court". Identical in both tables.
# Normal rate, per hour. Peak = (a) at/after 18:00 Mon-Fri, (b) at/after 13:00 Sat,
# (c) at any time on Sunday & public holiday.
RATE_AC = {"peak": 148.0, "offpeak": 120.0}
RATE_NOAC = {"peak": 82.0, "offpeak": 57.0}
RATE_AC_CONC = {"peak": 74.0, "offpeak": 60.0}
RATE_NOAC_CONC = {"peak": 41.0, "offpeak": 29.0}


def load_holidays():
    path = os.path.join(RAW, "hol_en.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig") as f:
        cal = json.load(f)
    out = {}
    for vc in cal["vcalendar"]:
        for ev in vc["vevent"]:
            ds = ev["dtstart"][0]
            out[ds[0:4] + "-" + ds[4:6] + "-" + ds[6:8]] = ev["summary"]
    return out


def classify_ac(venue_name, facility_type):
    """Return (ac_status, basis). Explicit source text wins over inference."""
    if re.search(r"non[- ]air[- ]conditioned", venue_name, re.I):
        return "not_air_conditioned", "venue_name_explicit"
    if "(A/C)" in facility_type:
        return "air_conditioned", "facility_type_explicit"
    if facility_type.endswith("(Urban)"):
        return "not_air_conditioned", "facility_type_implied_no_ac"
    if facility_type.endswith("(NT)"):
        return "air_conditioned", "assumed_default_ac"
    return "unknown", "unclassified"


def peak_period(date_str, start_hh, holidays):
    d = dt.date.fromisoformat(date_str)
    if date_str in holidays:
        return "peak", "public_holiday"
    wd = d.weekday()  # Mon=0 .. Sun=6
    if wd == 6:
        return "peak", "sunday"
    if wd == 5:  # Saturday
        return ("peak", "saturday_pm") if start_hh >= 13 else ("offpeak", "saturday_am")
    return ("peak", "weekday_pm") if start_hh >= 18 else ("offpeak", "weekday_am")


def rates(ac_status):
    if ac_status == "air_conditioned":
        return RATE_AC, RATE_AC_CONC
    return RATE_NOAC, RATE_NOAC_CONC


def feature(props, lon, lat):
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [round(float(lon), 7), round(float(lat), 7)]},
    }


def write_geojson(name, features):
    path = os.path.join(OUT, name)
    fc = {"type": "FeatureCollection", "name": os.path.splitext(name)[0], "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=1)
    print(f"  wrote {name}  ({len(features)} features)")
    return path


def write_csv(name, rows):
    path = os.path.join(OUT, name)
    if not rows:
        return path
    # Rows may carry different optional keys (per-row flags), so collect the
    # union rather than taking the first row's keys as the header.
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {name}  ({len(rows)} rows, {len(cols)} cols)")
    return path


def fld(rec, key, default=None):
    """Tolerant field read — the live feed omits some keys entirely on some venues."""
    v = rec.get(key, default)
    return default if v is None else v


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ---------------------------------------------------------------------- build
def main():
    holidays = load_holidays()
    print(f"general holidays loaded: {len(holidays)}")

    with open(os.path.join(RAW, "sp_volleyball.json"), encoding="utf-8") as f:
        live = json.load(f)
    print(f"live vacancy records: {len(live)}")

    # ---- venue table ---------------------------------------------------------
    venues = {}
    for r in live:
        vn = r["Venue_Name_EN"].strip()
        ac, basis = classify_ac(vn, r["Facility_Type_Name_EN"])
        v = venues.setdefault(
            vn,
            {
                "venue_id": "V" + slug(vn)[:28],
                "venue_name_en": vn,
                "venue_name_tc": r["Venue_Name_TC"].strip(),
                "district_en": r["District_Name_EN"].strip(),
                "district_tc": r["District_Name_TC"].strip(),
                "address_en": r["Venue_Address_EN"],
                "address_tc": r["Venue_Address_TC"],
                "phone": fld(r, "Venue_Phone_No.", ""),
                "lon": float(r["Venue_Longitude"]),
                "lat": float(r["Venue_Latitude"]),
                "region": "New_Territories" if r["Facility_Type_Name_EN"].endswith("(NT)") else "Urban",
                "facility_type_en": r["Facility_Type_Name_EN"],
                "ac_status": ac,
                "ac_status_basis": basis,
                "court_locations": set(),
                "dates": set(),
                "slots": set(),
                "sessions": [],
            },
        )
        loc = r["Facility_Location_Name_EN"].strip()
        v["court_locations"].add(re.sub(r"\s+", " ", loc))
        v["dates"].add(r["Available_Date"])
        v["slots"].add(r["Session_Start_Time"])
        v["sessions"].append(r)

    normal, conc = {}, {}
    for name, v in venues.items():
        n, c = rates(v["ac_status"])
        v["hire_normal_offpeak_hkd"] = n["offpeak"]
        v["hire_normal_peak_hkd"] = n["peak"]
        v["hire_concessionary_offpeak_hkd"] = c["offpeak"]
        v["hire_concessionary_peak_hkd"] = c["peak"]
        normal[name] = n
        conc[name] = c

    # ---- per-session price + live vacancy ------------------------------------
    session_features = []
    csv_rows = []
    by_venue = defaultdict(list)
    for r in live:
        vn = r["Venue_Name_EN"].strip()
        v = venues[vn]
        date_s = r["Available_Date"]
        hh = int(r["Session_Start_Time"].split(":")[0])
        band, why = peak_period(date_s, hh, holidays)
        n, c = normal[vn], conc[vn]
        avail = int(r["Available_Courts"])
        loc = re.sub(r"\s+", " ", r["Facility_Location_Name_EN"].strip())
        loc_slug = slug(loc)
        # A venue can book two genuinely different halls at the same start time
        # (e.g. "Arena (Centre 1)" / "Arena (Centre 2)"), so the hall is part of
        # the key — venue+date+time alone collapses them into one ID.
        s = {
            "session_id": "{}_{}_{}_{}".format(
                v["venue_id"], loc_slug, date_s, r["Session_Start_Time"].replace(":", "")
            ),
            "venue_id": v["venue_id"],
            "venue_name_en": vn,
            "venue_name_tc": v["venue_name_tc"],
            "district_en": v["district_en"],
            "region": v["region"],
            "court_location_en": loc,
            "facility_type_en": r["Facility_Type_Name_EN"],
            "ac_status": v["ac_status"],
            "session_date": date_s,
            "day_of_week": dt.date.fromisoformat(date_s).strftime("%a"),
            "session_start": r["Session_Start_Time"],
            "session_end": r["Session_End_Time"],
            "duration_min": 60,
            "price_band": band,
            "price_band_reason": why,
            "public_holiday": date_s in holidays,
            "available_courts": avail,
            "hire_normal_hkd": n[band],
            "hire_concessionary_hkd": c[band],
            "status": "available" if avail > 0 else "full",
            "value_at_stake_hkd": n[band] * avail,
        }
        session_features.append(feature(s, v["lon"], v["lat"]))
        csv_rows.append({k: v2 for k, v2 in s.items() if k != "ac_status"})
        by_venue[vn].append((date_s, r["Session_Start_Time"], avail))

    # ---- annual usage (Arena = main multi-purpose hall) -----------------------
    # The two datasets name venues differently: the usage feed omits the
    # parenthetical the live feed carries ("Tin Ping Sports Centre" vs
    # "Tin Ping Sports Centre (Non-air-conditioned in Arena)"), so match on the
    # name with parentheticals stripped AND require the two coordinates to be
    # within 60 m. That recovers 8 of the 10 exact-name misses; the remaining
    # two (Sai Wan Ho, Praya Street) are genuinely absent from the live feed.
    def norm_name(s):
        return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", s).lower()).strip()

    live_index = defaultdict(list)
    for nm, v in venues.items():
        live_index[norm_name(nm)].append((nm, v["lon"], v["lat"]))

    def metres(a_lon, a_lat, b_lon, b_lat):
        return 111320 * math.hypot(a_lon - b_lon, (a_lat - b_lat) * 0.893)

    usage_join = {}  # usage-feed name -> live venue name

    usage_by_venue = defaultdict(dict)
    usage_zero_flag = {}
    usage_path = os.path.join(RAW, "usage_arena.geojson")
    allfac = defaultdict(lambda: defaultdict(list))
    if os.path.exists(usage_path):
        with open(usage_path, encoding="utf-8") as f:
            ug = json.load(f)
        for ft in ug["features"]:
            p = ft["properties"]
            m = re.search(r"(\d+(?:\.\d+)?)", str(p.get("Usage") or ""))
            val = float(m.group(1)) if m else None
            vname = p["Venue_EN"].strip()
            yr = str(p.get("Year"))
            allfac[vname][yr].append(val)
            if p.get("Facilities_EN") != "Arena":
                continue
            # resolve to the live-feed venue name where the two datasets differ
            if vname not in venues:
                cands = [
                    (nm, d)
                    for nm, lon, lat in live_index.get(norm_name(vname), [])
                    if p.get("Latitude") is not None and p.get("Longitude") is not None
                    for d in [metres(float(p["Longitude"]), float(p["Latitude"]), lon, lat)]
                    if d <= 60
                ]
                if cands:
                    cands.sort(key=lambda x: x[1])
                    usage_join[vname] = cands[0][0]
                    allfac[usage_join[vname]][yr].append(val)
            key = usage_join.get(vname, vname)
            if key in venues:
                usage_by_venue[key][yr] = val

    # LCSD reports 0% usage for some venues in some years. Two cases, both
    # artifacts rather than closures:
    #   (a) an isolated 0% sandwiched between healthy years (94% -> 0% -> 99%);
    #   (b) every facility reported at the venue is 0% for that year - an
    #       un-reported year (Tung Cheong Street is 0% in 2022 yet is bookable
    #       in today's live feed with 128 sessions).
    # Either way the year is set to missing and flagged; nothing is treated as a
    # closure, because the live feed proves the venue is open.
    for name, years in usage_by_venue.items():
        zeros = [y for y, v in years.items() if v == 0]
        if not zeros:
            continue
        healthy = [v for v in years.values() if v not in (0, None)]
        for y in zeros:
            allvals = allfac.get(name, {}).get(y, [])
            unreported = bool(allvals) and all(v == 0 for v in allvals)
            if healthy or unreported:
                years[y] = None
                reason = "unreported_year" if not healthy else "isolated_zero"
                usage_zero_flag.setdefault(name, []).append(f"{y}:{reason}")

    # ---- venue aggregate features -------------------------------------------
    venue_features = []
    csv_v = []
    for name, v in sorted(venues.items()):
        sess = by_venue[name]
        n_bookable = sum(1 for _, _, a in sess if a > 0)
        total = len(sess)
        dates = sorted({d for d, _, _ in sess})
        upcoming = []
        for d, t, a in sorted(sess):
            if a > 0:
                upcoming.append(f"{d} {t}")
        hours = sorted({t for d, t, a in sess})
        u = usage_by_venue.get(name, {})
        usage_2022 = u.get("2022")

        p = {
            "venue_id": v["venue_id"],
            "venue_name_en": v["venue_name_en"],
            "venue_name_tc": v["venue_name_tc"],
            "district_en": v["district_en"],
            "district_tc": v["district_tc"],
            "region": v["region"],
            "address_en": v["address_en"],
            "address_tc": v["address_tc"],
            "phone": v["phone"],
            "facility_type_en": v["facility_type_en"],
            "ac_status": v["ac_status"],
            "ac_status_basis": v["ac_status_basis"],
            "court_locations_en": "; ".join(sorted(v["court_locations"])),
            "daily_session_slots": len(hours),
            "first_slot": hours[0] if hours else None,
            "last_slot": hours[-1] if hours else None,
            "booking_window_first": dates[0] if dates else None,
            "booking_window_last": dates[-1] if dates else None,
            "court_count": None,
            "court_count_source": "not_published_by_LCSD",
            # price
            "hire_normal_offpeak_hkd": v["hire_normal_offpeak_hkd"],
            "hire_normal_peak_hkd": v["hire_normal_peak_hkd"],
            "hire_concessionary_offpeak_hkd": v["hire_concessionary_offpeak_hkd"],
            "hire_concessionary_peak_hkd": v["hire_concessionary_peak_hkd"],
            # live vacancy
            "snapshot_date": SNAPSHOT_DATE,
            "sessions_in_window": total,
            "sessions_with_vacancy": n_bookable,
            "vacancy_pct": round(100.0 * n_bookable / total, 1) if total else None,
            "courts_available_now": sum(
                a for d, t, a in sess if d == SNAPSHOT_DATE and t > dt.datetime.now().strftime("%H:%M")
            ),
            "next_available_session": upcoming[0] if upcoming else None,
            "snapshot_note": "live vacancy feed refreshes every 5 minutes; snapshot_date is fetch date",
        }
        if usage_2022 is not None:
            p["usage_pct_2022"] = usage_2022
            p["usage_source"] = "LCSD annual facility usage (Arena = main multi-purpose hall)"
        p["usage_pct_2021"] = u.get("2021")
        p["usage_pct_2020"] = u.get("2020")
        zf = usage_zero_flag.get(name)
        if zf:
            p["usage_zero_pct_years_excluded"] = ";".join(zf)
            p["usage_zero_note"] = (
                "LCSD reported 0% for this venue-year only, either isolated between "
                "healthy years or with every facility 0% (un-reported year); treated as "
                "missing, not a closure - the live feed confirms the venue is open"
            )

        venue_features.append(feature(p, v["lon"], v["lat"]))
        csv_v.append(p)

    # ---- free outdoor + beach courts ----------------------------------------
    free_feats = []
    for src_file, did, title in [
        ("outdoor_volleyball.geojson", "lcsd_rcd_1670383751618_95284", "Volleyball Courts (Free Outdoor Pitches/Courts)"),
        ("beach_volleyball.geojson", "lcsd_rcd_1670383539632_8620", "Beach Volleyball Courts"),
    ]:
        path = os.path.join(RAW, src_file)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            g = json.load(f)
        for ft in g["features"]:
            s = ft["properties"]
            lon, lat = ft["geometry"]["coordinates"]
            p = {
                "court_id": f"{did}_{s.get('OBJECTID')}",
                "court_type": title,
                "venue_name_en": (s.get("Name_en") or "").strip(),
                "venue_name_tc": (s.get("Name_cn") or "").strip(),
                "district_en": (s.get("District_en") or "").strip(),
                "district_tc": (s.get("District_cn") or "").strip(),
                "address_en": s.get("Address_en"),
                "address_tc": s.get("Address_cn"),
                "no_of_courts": s.get("Court_no_en"),
                "opening_hours_en": s.get("Opening_hours_en"),
                "phone": s.get("Phone"),
                "remarks_en": s.get("Remarks_en"),
                "booking_fee_hkd": 0,
                "fee_note": "free outdoor hard-surface court; first-come first-served; no hire charge",
                "live_vacancy_available": "n/a",
                "usage_pct": None,
                "dataset_id": did,
                "dataset_title": title,
            }
            free_feats.append(feature(p, lon, lat))

    # ---- district boundaries -------------------------------------------------
    dc_feats = []
    dc_path = str(HERE / "raw" / "012_LND_DC_POLY_SDO.geojson.gz")
    if os.path.exists(dc_path):
        with gzip.open(dc_path, "rt", encoding="utf-8") as f:
            dg = json.load(f)
        alias = {
            "Central and Western District": "Central & Western",
            "Wan Chai District": "Wan Chai",
            "Wong Tai Sin District": "Wong Tai Sin",
        }
        for ft in dg["features"]:
            nm = ft["properties"]["NAME"]
            dc_feats.append(
                {
                    "type": "Feature",
                    "properties": {
                        "district_en": nm,
                        "lcsd_district_en": alias.get(nm, nm.replace(" District", "")),
                    },
                    "geometry": ft["geometry"],
                }
            )
        print(f"  district polygons: {len(dc_feats)}")

    # ------------------------------------------------------------------ write
    print("\nwriting layers:")
    write_geojson("venues.geojson", venue_features)
    write_geojson("sessions.geojson", session_features)
    write_geojson("free_outdoor_courts.geojson", free_feats)
    write_csv("venues.csv", csv_v)
    write_csv("sessions.csv", csv_rows)

    # usage by venue (only venues that have an Arena row)
    uf = []
    for name, v in sorted(venues.items()):
        u = usage_by_venue.get(name)
        if not u:
            continue
        uf.append(
            feature(
                {
                    "venue_id": v["venue_id"],
                    "venue_name_en": name,
                    "district_en": v["district_en"],
                    "usage_facility_type": "Arena",
                    "usage_pct_2020": u.get("2020"),
                    "usage_pct_2021": u.get("2021"),
                    "usage_pct_2022": u.get("2022"),
                    "usage_unit": "per cent of available hours booked",
                    "source": "LCSD Usage of Recreational and Sports Facilities by Venue (annual)",
                },
                v["lon"],
                v["lat"],
            )
        )
    write_geojson("usage_by_venue.geojson", uf)

    if dc_feats:
        with open(os.path.join(OUT, "districts.geojson"), "w", encoding="utf-8") as f:
            json.dump(
                {"type": "FeatureCollection", "name": "districts", "features": dc_feats},
                f,
                ensure_ascii=False,
            )
        print(f"  wrote districts.geojson  ({len(dc_feats)} features)")

    print("\nsummary:")
    print(f"  bookable indoor venues      : {len(venue_features)}")
    print(f"  live session records        : {len(session_features)}")
    print(f"  venues with annual usage    : {len(uf)}")
    print(f"  free outdoor / beach courts : {len(free_feats)}")
    ac = sum(1 for v in venues.values() if v["ac_status"] == "air_conditioned")
    noac = sum(1 for v in venues.values() if v["ac_status"] == "not_air_conditioned")
    assumed = sum(1 for v in venues.values() if v["ac_status_basis"] == "assumed_default_ac")
    print(f"  A/C classified              : {ac} air-conditioned, {noac} not ({assumed} NT venues assumed A/C)")


if __name__ == "__main__":
    main()