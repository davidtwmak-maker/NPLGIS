#!/usr/bin/env python3
"""Check every figure in the covered-walkways note against the shipped data.

WHY
    The note's MTR worst-case table was written by hand from the
    pipeline's console output. Four of its figures were mistyped, and
    one district row carried a count that does not match the data.
    None of them was wrong enough to look wrong: 704 against 693 is a
    plausible median, 403 against 398 is a plausible gap.

    A figure that is nearly right is the hardest kind to catch by
    eye, and the hardest kind to defend in a write-up.

THE CONVENTIONS
    Taken from mtr_walk_schools.py, so that "the median" means one
    thing:
        statistics.median(v)                the median
        statistics.quantiles(v, n=10)[8]    the p90
        walk_minutes > 15                   the over-15-minute count
        walk_minutes_flat                   the flat-ground time

RUN
    python3 scripts/kowloon-covered-walkways/verify_note.py
"""
import csv
import json
import re
import statistics as stx
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent          # scripts/kowloon-covered-walkways -> repo root
DATA = REPO / "assets/data/kowloon-covered-walkways/mtr_walk_schools.json"
NOTE = REPO / "notes/kowloon-covered-walkways — NOTES.md"

# The heading that opens the MTR worst-case section. The note's tables
# are scoped by heading because row labels repeat across sections.
MTR_HEADING = "## Scenario — worst case: walking from the nearest MTR station"

# What the note CLAIMS. These are PARSED OUT OF THE NOTE, not typed
# here - a typed list would be a second place to be wrong, and the
# gate would then check the data against itself. The note is the thing
# under test, so the note is where the claims come from.
NOTE_DISTRICTS = [
    ("Yau Tsim Mong", "YAU TSIM MONG"),
    ("Sham Shui Po", "SHAM SHUI PO"),
    ("Wong Tai Sin", "WONG TAI SIN"),
    ("Kowloon City", "KOWLOON CITY"),
    ("Kwun Tong", "KWUN TONG"),
    ("Kwai Chung", "KWAI TSING"),
]

# The labels the note uses for the overall figures, and how to read
# the number out of the markdown cell.
OVERALL_ROWS = [
    ("Median walk", r"\*\*([\d,]+) m\*\*"),
    ("p90 walk", r"\*\*([\d,]+) m\*\*"),
    ("Longest walk", r"\*\*([\d,]+) m\*\*"),
    ("Median longest uncovered stretch", r"\*\*([\d,]+) m\*\*"),
    ("Schools needing over 15 min", r"\*\*(\d+)\*\*"),
    ("Schools needing over 20 min", r"\*\*(\d+)\*\*"),
    ("Schools with no covered stretch at all", r"\*\*(\d+)\*\*"),
]


def load_rows():
    d = json.load(open(DATA, encoding="utf-8"))
    return d if isinstance(d, list) else d.get("schools", d)


def actuals(rows):
    v = [float(r["walk_m"]) for r in rows if r.get("walk_m") is not None]
    g = [float(r["longest_exposed_m"]) for r in rows
         if r.get("longest_exposed_m") is not None]
    mins = [float(r["walk_minutes"]) for r in rows
            if r.get("walk_minutes") is not None]
    snaps = [float(r["exit_snap_m"]) for r in rows
             if r.get("exit_snap_m") is not None]
    return {
        "median walk": round(stx.median(v)),
        "p90 walk": round(stx.quantiles(v, n=10)[8]),
        "longest walk": round(max(v)),
        "median longest uncovered": round(stx.median(g)),
        "over 15 min": sum(1 for x in mins if x > 15),
        "over 20 min": sum(1 for x in mins if x > 20),
        "no covered stretch": sum(
            1 for r in rows if float(r.get("covered_m") or 0) == 0),
        "exit snap median": round(stx.median(snaps), 1),
        "exit snap max": round(max(snaps), 1),
    }


def note_overall_claims(text):
    """The figures the note's MTR check table claims, parsed out of it.

    The note has TWO tables with overlapping row labels - the
    stop-to-school table and the MTR worst-case table - and both carry
    a "Median longest uncovered stretch" row. They are different
    measures over different routes: 223 m is the gap on the
    most-sheltered school route, 398 m is the gap on the MTR walk.
    So the search is scoped to the MTR section, or the gate would read
    the wrong row.
    """
    section = mtr_section(text)
    claims = {}
    for label, pattern in OVERALL_ROWS:
        m = re.search(r"\|\s*" + re.escape(label) + r"\s*\|([^|]*)\|", section)
        if not m:
            continue
        n = re.search(pattern, m.group(1))
        if n:
            claims[label] = float(n.group(1).replace(",", ""))
    return claims


def mtr_section(text):
    """The part of the note from the MTR scenario heading onwards."""
    i = text.find(MTR_HEADING)
    if i < 0:
        return text
    j = text.find("\n## ", i + 1)
    return text[i:j] if j > 0 else text[i:]


def note_district_claims(text):
    """The by-district rows the note claims, parsed out of it."""
    section = mtr_section(text)
    claims = {}
    for label, _ in NOTE_DISTRICTS:
        m = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|(.+)\|\s*$",
                      section, re.M)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        nums = []
        for c in cells:
            n = re.match(r"\*\*([\d,]+)\*\*|^([\d,]+)", c.replace(",", ""))
            if n:
                nums.append(float((n.group(1) or n.group(2)).replace(",", "")))
                continue
            t = re.search(r"([\d,]+)\s*min", c)
            if t:
                nums.append(float(t.group(1).replace(",", "")))
                continue
            nums.append(None)
        if len(nums) >= 6:
            claims[label] = nums[:6]
    return claims


def main():
    if not DATA.exists():
        print(f"  {DATA} not found")
        return 1
    if not NOTE.exists():
        print(f"  {NOTE} not found")
        return 1
    text = NOTE.read_text(encoding="utf-8")
    rows = load_rows()
    act = actuals(rows)
    problems = []

    # The note's overall figures, keyed by the note's own labels.
    label_to_key = {
        "Median walk": "median walk",
        "p90 walk": "p90 walk",
        "Longest walk": "longest walk",
        "Median longest uncovered stretch": "median longest uncovered",
        "Schools needing over 15 min": "over 15 min",
        "Schools needing over 20 min": "over 20 min",
        "Schools with no covered stretch at all": "no covered stretch",
    }
    claims = note_overall_claims(text)
    print("  === the overall check table ===")
    for label, key in label_to_key.items():
        want = claims.get(label)
        got = act[key]
        if want is None:
            problems.append(f"overall {label}: not found in the note")
            print(f"    {label:36} NOT FOUND IN THE NOTE")
            continue
        ok = abs(want - got) < 0.051
        if not ok:
            problems.append(f"overall {label}: note says {want:g}, "
                            f"data says {got:g}")
        print(f"    {label:36} note {want:>7g}   data {got:>7g}   "
              f"{'' if ok else '<-- DIFFERS'}")
    # The exit snap row is a plain (not bold) cell.
    m = re.search(r"\|\s*Median exit-to-network snap\s*\|([^|]*)\|",
                  mtr_section(text))
    if m:
        n = re.search(r"([\d.]+)\s*m\s*\(max\s*([\d.]+)\s*m\)", m.group(1))
        if n:
            for want, key in ((float(n.group(1)), "exit snap median"),
                              (float(n.group(2)), "exit snap max")):
                got = act[key]
                ok = abs(want - got) < 0.051
                if not ok:
                    problems.append(f"overall {key}: note says {want:g}, "
                                    f"data says {got:g}")
                print(f"    {key:36} note {want:>7g}   data {got:>7g}   "
                      f"{'' if ok else '<-- DIFFERS'}")

    print()
    print("  === the by-district table ===")
    by = defaultdict(list)
    for r in rows:
        by[r.get("district")].append(r)
    dclaims = note_district_claims(text)
    for label, key in NOTE_DISTRICTS:
        rs = by.get(key, [])
        want = dclaims.get(label)
        if not rs:
            problems.append(f"{label}: no rows in the data")
            continue
        if want is None:
            problems.append(f"{label}: row not found in the note")
            print(f"    {label:16} ROW NOT FOUND IN THE NOTE")
            continue
        v = [float(r["walk_m"]) for r in rs if r.get("walk_m") is not None]
        mins = [float(r["walk_minutes"]) for r in rs
                if r.get("walk_minutes") is not None]
        got = (len(rs), round(stx.median(v)),
               round(stx.quantiles(v, n=10)[8]), round(max(v)),
               round(stx.median(mins)), sum(1 for x in mins if x > 15))
        want_t = tuple(want)
        ok = got == want_t
        if not ok:
            diffs = ", ".join(
                f"{lbl} note={w:g} data={g}"
                for lbl, w, g in zip(
                    ("n", "median", "p90", "max", "time", ">15"),
                    want_t, got)
                if w != g)
            problems.append(f"{label}: {diffs}")
            print(f"    {label:16} <-- DIFFERS")
            print(f"        {diffs}")
        else:
            print(f"    {label:16} OK")

    print()
    print("  === the stop-to-school table ===")
    check_school_table(text, problems)

    print()
    if problems:
        print(f"BROKEN NOTE: {len(problems)} figure(s) in the method note do "
              f"not match the shipped data.")
        for p in problems:
            print(f"  {p}")
        return 1
    print("OK: every figure in the note's MTR table matches the shipped data.")
    return 0


def check_school_table(text, problems):
    """The stop-to-school table, checked against Schools_RouteMetrics.csv.

    This is the other table in the note, and it comes from a different
    source: the school routes, not the MTR walks. Its figures describe
    the most-sheltered route to the school, so they are read from the
    `ai_best_cov_*` columns.
    """
    csv_path = REPO / "assets/data/kowloon-covered-walkways/Schools_RouteMetrics.csv"
    if not csv_path.exists():
        problems.append(f"school table: {csv_path} not found")
        return
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def col(name):
        return [float(r[name]) for r in rows if r.get(name) not in (None, "", "None")]

    best_m = col("ai_best_cov_route_m")
    longest = col("ai_best_cov_longest_exposed_m")
    route = col("ai_route_m")
    direct = col("ai_direct_m")
    detour = [r / d for r, d in zip(route, direct) if d]

    # (label, the number the note claims, the number the data gives)
    checks = [
        ("Median most-sheltered route length",
         note_number(text, "Median most-sheltered route length", r"\*\*([\d,]+) m\*\*"),
         round(stx.median(best_m))),
        ("Median longest uncovered stretch",
         note_number(text, "Median longest uncovered stretch", r"\*\*([\d,]+) m\*\*"),
         round(stx.median(longest))),
        ("Schools with a > 200 m uncovered stretch",
         note_number(text, "Schools with a > 200 m uncovered stretch", r"\*\*(\d+)\*\*"),
         sum(1 for x in longest if x > 200)),
        ("Schools with a > 500 m uncovered stretch",
         note_number(text, "Schools with a > 500 m uncovered stretch", r"\*\*(\d+)\*\*"),
         sum(1 for x in longest if x > 500)),
        ("Schools with a fully covered walk",
         note_number(text, "Schools with a fully covered walk", r"\*\*(\d+)\*\*"),
         sum(1 for r in rows
             if abs(float(r["ai_best_cov_ratio"]) - 1.0) < 1e-9)),
    ]
    for label, want, got in checks:
        if want is None:
            problems.append(f"school table {label}: not found in the note")
            print(f"    {label:44} NOT FOUND IN THE NOTE")
            continue
        ok = abs(want - got) < 0.051
        if not ok:
            problems.append(f"school table {label}: note says {want:g}, "
                            f"data says {got:g}")
        print(f"    {label:44} note {want:>7g}   data {got:>7g}   "
              f"{'' if ok else '<-- DIFFERS'}")

    # The detour factor row carries two numbers.
    m = re.search(r"\|\s*Detour factor \(shortest route ÷ straight line\)\s*\|([^|]*)\|",
                  text)
    if m:
        n = re.search(r"median\s*\*\*([\d.]+)\*\*.*?max\s*\*\*([\d.]+)\*\*",
                      m.group(1))
        if n:
            for want, got, what in ((float(n.group(1)),
                                     round(stx.median(detour), 2), "median"),
                                    (float(n.group(2)),
                                     round(max(detour), 2), "max")):
                ok = abs(want - got) < 0.011
                if not ok:
                    problems.append(f"school table detour {what}: note says "
                                    f"{want:g}, data says {got:g}")
                print(f"    {'detour factor ' + what:44} note {want:>7g}   "
                      f"data {got:>7g}   {'' if ok else '<-- DIFFERS'}")


def note_number(text, label, pattern):
    """The number the note claims on the row with this label."""
    m = re.search(r"\|\s*" + re.escape(label) + r"\s*\|([^|]*)\|", text)
    if not m:
        return None
    n = re.search(pattern, m.group(1))
    if not n:
        return None
    return float(n.group(1).replace(",", ""))


if __name__ == "__main__":
    sys.exit(main())
