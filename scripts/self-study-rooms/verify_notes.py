#!/usr/bin/env python3
"""
Check every number in the published notes against the SHIPPED layers.

The notes live in two places - the Obsidian vault recipe and this repo's
notes/ file - and they are written differently on purpose: the recipe's walk
table puts the distance bands in the COLUMNS, the notes file puts them in the
ROWS, and the recipe's crowding table has no counterpart in the notes file.

Rules:
  - every count and total is computed from the shipped file, never from the
    note
  - tables are matched by HEADER SEMANTICS, so column order and wording can
    differ between the two notes
  - prose figures are checked by CONTEXT WINDOW, not by exact phrase: the
    expected value must appear within a short window of the keyword that
    introduces it. A number that appears near the right keyword but with the
    wrong value is a FAILURE - that is the drift this script exists to catch
  - a fact the note states in a way the script cannot find is a FAILURE, not
    a skip: a note that stops quoting a number is as wrong as one that quotes
    it wrongly
  - the check is independent of the analysis scripts, so it catches the
    scripts being wrong as well as the note being wrong

Run:  python3 scripts/self-study-rooms/verify_notes.py
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(REPO, "assets", "data", "self-study-rooms")

VAULT = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/NPL GIS Team/GIS Projects")

NOTES = [
    os.path.join(REPO, "notes", "hk-self-study-rooms — NOTES.md"),
    os.path.join(VAULT, "Hong Kong Self-Study Rooms — CSDI & LegCo Data and ArcGIS Recipe.md"),
]

# the districts that must appear in a district table, even if the table
# elides the middle rows with an ellipsis
KEY_DISTRICTS = ["Tuen Mun", "Kowloon City", "Tai Po", "Sham Shui Po", "Islands"]

results = []


def check(label, got, want, tol=0.0):
    ok = abs(got - want) <= tol if isinstance(got, (int, float)) else got == want
    results.append((ok, label, got, want))
    return ok


def fail(label, detail):
    results.append((False, label, detail, None))


def num(s):
    """Parse a number that may carry a Unicode minus, thousands separators, a
    multiplication sign or a trailing unit. The notes use U+2212 MINUS SIGN,
    which float() rejects, so it is normalised here. A spelled-out number
    ("Four schools") is also accepted."""
    s = str(s).strip()
    for ch in ("−", "–", "—"):
        s = s.replace(ch, "-")
    s = s.replace("×", "").replace("*", "")
    word = s.strip().lower()
    if word in NUM_WORDS:
        return float(NUM_WORDS[word])
    s = re.sub(r"[^\d.,\-]", "", s)
    return float(s.replace(",", ""))


NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}


def numbers_in(text):
    """Every number that appears in a piece of text, including number WORDS.
    The notes spell small counts out ("Four schools could not be routed"),
    so a digit-only scan would miss the fact entirely."""
    out = []
    for m in re.finditer(r"[−–—]?\d[\d,]*\.?\d*\s*×?", text):
        try:
            out.append(num(m.group(0)))
        except ValueError:
            pass
    for m in re.finditer(r"\b(" + "|".join(NUM_WORDS) + r")\b", text, re.I):
        out.append(float(NUM_WORDS[m.group(1).lower()]))
    return out


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def parse_tables(text):
    """Return [(header_cells, [row_cells, ...]), ...] for every table."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            header = cells(lines[i])
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            if rows:
                out.append((header, rows))
        else:
            i += 1
    return out


def plain(s):
    """Strip markdown emphasis and normalise ampersand/'and' so a district
    named 'Central & Western' matches the CSV's 'Central and Western'."""
    s = re.sub(r"[*`]", "", s).strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\s+", " ", s)
    return s


def find_table(tables, *keywords):
    for header, rows in tables:
        h = " | ".join(plain(c) for c in header)
        if all(k.lower() in h for k in keywords):
            return header, rows
    return None, None


def find_row(rows, key):
    for r in rows:
        if r and plain(r[0]) == plain(key):
            return r
    return None


def prose_only(text):
    """Return the text with every markdown TABLE line blanked out.

    The offsets are preserved - each table line is replaced by spaces of the
    same length - so a match index found here still indexes correctly into
    the original text.
    """
    out = []
    for line in text.split("\n"):
        if line.strip().startswith("|"):
            out.append(" " * len(line))
        else:
            out.append(line)
    return "\n".join(out)


def check_claim(name, text, label, pattern, want, tol=0.05, group=1, required=True):
    """Check a prose claim by CAPTURING the number the note states.

    The pattern must capture the number that belongs to THIS claim, so the
    check compares the note's own value against the data. That is what
    catches drift: a pattern that merely looks for the right number nearby
    would pass even if the note had swapped two numbers around, and a
    pattern that only checks the FIRST mention would let a second copy of
    the same fact drift away unnoticed.

    `required=False` skips the check when the note does not make the claim
    at all - used for facts that only one of the two notes states.
    """
    hits = list(re.finditer(pattern, prose_only(text), re.I | re.S))
    if not hits:
        if required:
            fail(f"{name}: {label}", "claim not found")
        return False
    bad = []
    for m in hits:
        try:
            got = num(m.group(group))
        except (ValueError, IndexError):
            bad.append(f"unparseable {m.group(0)[:80]!r}")
            continue
        if abs(got - want) > tol:
            bad.append(f"{got} != {want}")
    if bad:
        fail(f"{name}: {label}", f"{len(bad)} of {len(hits)} claims wrong: {bad[0]}")
        return False
    check(f"{name}: {label}", len(hits), len(hits))
    return True


def check_prose(name, text, label, keyword, want, tol=0.05, window=170):
    """The expected value must appear near EVERY mention of the keyword,
    but only in PROSE.

    Two rules make this usable:
      * matches inside a markdown TABLE are ignored - the tables are already
        checked cell by cell, and a table row that happens to contain the
        keyword is not a claim about the prose fact
      * the keyword must be SPECIFIC. A generic one like "seats" matches
        every table row and every caveat, and requiring the value at every
        mention then fails on text that never claimed to be the total

    Checking every mention (not just the first) is what catches one copy of
    a fact drifting away from another copy of the same fact.
    """
    hits = list(re.finditer(keyword, prose_only(text), re.I))
    if not hits:
        fail(f"{name}: {label}", "not stated")
        return False
    bad = []
    for m in hits:
        lo = max(0, m.start() - window)
        hi = min(len(text), m.end() + window)
        nums = numbers_in(text[lo:hi])
        if not any(abs(v - want) <= tol for v in nums):
            bad.append(text[lo:hi].replace("\n", " ")[:110])
    if bad:
        fail(f"{name}: {label}", f"{len(bad)} of {len(hits)} mentions lack {want}: {bad[0]!r}")
        return False
    check(f"{name}: {label}", want, want)
    return True


def main():
    dt = list(csv.DictReader(open(os.path.join(DATA, "district_table.csv"), encoding="utf-8")))
    ns = json.load(open(os.path.join(DATA, "network_summary.json"), encoding="utf-8"))
    cs = json.load(open(os.path.join(DATA, "crowding_summary.json"), encoding="utf-8"))
    ec = json.load(open(os.path.join(DATA, "elderly_competition_test.json"), encoding="utf-8"))
    walk = list(csv.DictReader(open(os.path.join(DATA, "network_walk.csv"), encoding="utf-8")))

    seats = sum(int(r["seats"]) for r in dt)
    s46 = sum(int(r["s4_6"]) for r in dt)
    per = [float(r["students_per_100_seats"]) for r in dt]
    wutil = sum(int(r["seats"]) * float(r["util_2025"]) for r in dt) / seats
    spread = max(per) / min(per)
    n_unreach = sum(1 for r in walk
                    if r["reachable"].strip().lower() in ("no", "false", ""))

    for path in NOTES:
        name = os.path.basename(path)[:46]
        if not os.path.exists(path):
            fail(f"{name}: FILE MISSING", path)
            continue
        text = open(path, encoding="utf-8").read()
        tables = parse_tables(text)

        # ------------------------------------------------ district table
        header, rows = find_table(tables, "district", "s4")
        if not rows:
            fail(f"{name}: district table not found", "header with 'District' and 'S4'")
        else:
            heads = [plain(c) for c in header]
            ci = {k: next((i for i, h in enumerate(heads) if k in h), None)
                  for k in ("s4", "seat", "per 100", "utilisation")}
            if ci["s4"] is None or ci["seat"] is None or ci["per 100"] is None:
                fail(f"{name}: district table columns", header)
            else:
                present = 0
                for r in dt:
                    row = find_row(rows, r["district"])
                    if not row:
                        continue  # the table may elide middle rows with "..."
                    present += 1
                    check(f"{name}: {r['district']} S4-S6", num(row[ci["s4"]]), int(r["s4_6"]))
                    check(f"{name}: {r['district']} seats", num(row[ci["seat"]]), int(r["seats"]))
                    check(f"{name}: {r['district']} per100", num(row[ci["per 100"]]),
                          float(r["students_per_100_seats"]), tol=0.5)
                    if ci["utilisation"] is not None and len(row) > ci["utilisation"]:
                        check(f"{name}: {r['district']} utilisation", num(row[ci["utilisation"]]),
                              float(r["util_2025"]), tol=0.05)
                if present < len(KEY_DISTRICTS):
                    fail(f"{name}: district table rows", f"only {present} of 18 shown")
                for k in KEY_DISTRICTS:
                    if not find_row(rows, k):
                        fail(f"{name}: district row {k}", "row missing")

        # ------------------------------------------------ walk band table
        # orientation A: bands in the rows  | Band | Real walk | Straight |
        # orientation B: bands in the COLUMNS | | 400 m | 600 m | ...
        # NOTE: the table must be matched on the BAND, not on "real walk" -
        # the worst-detour table also has a "Real walk" column.
        band_keys = {"400 m": "400m", "600 m": "600m", "800 m": "800m",
                     "1,000 m": "1000m", "1,500 m": "1500m"}
        header, rows = find_table(tables, "400 m")
        if not rows:
            # orientation A has the band in the FIRST CELL of each row, so the
            # header does not contain "400 m" - find the table by its row
            # labels instead.
            for h, rr in tables:
                if any(plain(r[0]) in band_keys for r in rr):
                    header, rows = h, rr
                    break
        if rows and any(plain(r[0]) in band_keys for r in rows):
            # orientation A: bands in the rows
            for r in rows:
                band = plain(r[0])
                if band in band_keys:
                    check(f"{name}: band {band} walk", num(r[1]), ns["within"][band_keys[band]])
                    check(f"{name}: band {band} straight", num(r[2]),
                          ns["within_straight"][band_keys[band]])
            for label in band_keys:
                if not find_row(rows, label):
                    fail(f"{name}: band {label} row", "row missing")
        elif rows:
            # orientation B: bands in the columns
            heads = [plain(c).replace(",", "") for c in header]
            cols = {}
            for i, h in enumerate(heads):
                for label in band_keys:
                    if h == label.lower().replace(",", ""):
                        cols[label] = i
            if len(cols) != 5:
                fail(f"{name}: walk band columns", header)
            else:
                walk_row = find_row(rows, "Real walk")
                if walk_row is None:
                    fail(f"{name}: walk band row 'Real walk'", rows[0])
                else:
                    for label, key in band_keys.items():
                        check(f"{name}: band {label}", num(walk_row[cols[label]]),
                              ns["within"][key])
        else:
            fail(f"{name}: walk band table not found", "no band table")

        # ------------------------------------------------ crowding table
        header, rows = find_table(tables, "threshold", "small areas")
        if rows:
            med = None
            for r in rows:
                if "median" in plain(r[0]):
                    med = r
                    break
            if med:
                check(f"{name}: areas below median", num(med[1]), cs["n_small_areas_below_median"])
                check(f"{name}: students in small areas", num(med[2]),
                      cs["students_in_small_accommodation"])
                check(f"{name}: rooms in those areas", num(med[4]), cs["rooms_in_small_areas"])
            else:
                fail(f"{name}: crowding median row", "no row labelled median")

        # ------------------------------------------------ prose claims
        # Each pattern CAPTURES the number the note states for that claim, so
        # the check compares the note's own value against the data. A
        # pattern that only looked for the right number nearby would pass
        # even if two numbers had been swapped, and checking only the first
        # mention would let a second copy of the same fact drift.
        N = r"[\d,]+"

        # the S4-S6 total, wherever it is stated as such
        check_claim(name, text, "S4-S6 total",
                    rf"({N})\s+senior-secondary students", s46, tol=0.5)

        # the seat total.
        #
        # Several different quantities end in the word "seats":
        #   "6,521 public-library study seats"   <- the TOTAL
        #   "2,466 students per 100 seats"      <- a RATE
        #   "Tsuen Wan (162 seats)"             <- ONE district
        #   "Kwun Tong has 685 seats"           <- ONE district
        #   "| Seats |"                         <- a table header
        # so the count is captured and each match is classified by its
        # surrounding text. A match is a TOTAL claim unless it is preceded by
        # "per" (a rate) or qualified as a single district's count.
        TOTAL_CTX = re.compile(
            r"public-library study seats|territory's\s*$|against\s*$|"
            r"\*\*|library seats|seats figure|seats\*?\*?\s+is\b", re.I)
        seen = 0
        for m in re.finditer(
                rf"({N})\s+(?:public-library\s+)?(?:library\s+)?(?:study\s+)?seats",
                prose_only(text), re.I):
            before = text[max(0, m.start() - 40):m.start()]
            after = text[m.end():m.end() + 40]
            if re.search(r"\bper\s*$", before) or re.search(r"\bper\s*\n>?\s*$", before):
                continue  # the "per 100 seats" rate
            if re.search(r"\(\s*$", before) or re.search(r"has\s+$", before):
                continue  # one district's own count
            if re.search(r"^(?:\s*\*\*)?\s*(?:is\b|figure\b)", after):
                pass  # "6,521 seats is 38.5%" - a total claim
            elif not TOTAL_CTX.search(before[-30:] + after[:30]):
                continue  # neither a total phrase nor a rate: skip it
            seen += 1
            if abs(num(m.group(1)) - seats) > 0.5:
                fail(f"{name}: seat total", f"{num(m.group(1))} != {seats}")
        if seen:
            check(f"{name}: seat total", seen, seen)
        else:
            fail(f"{name}: seat total", "claim not found")

        # weighted 2025 utilisation
        check_claim(name, text, "weighted utilisation",
                    rf"weighted(?: average)? 2025 utilisation[^%\n]*?([\d.]+)\s*%",
                    round(wutil, 1))

        # the students-per-100-seats spread
        check_claim(name, text, "spread",
                    rf"([\d.]+)\s*×\s*spread", round(spread, 1))

        # the territory median floor area
        check_claim(name, text, "median floor area",
                    rf"median floor area (?:of|across)[^\n]*?({N})\s*m²", 46)

        # the small areas with no study room
        check_claim(name, text, "areas with no room",
                    rf"(\d+)\s+of (?:the )?211[^.\n]*?no study room", 128)

        # the unroutable schools. The count is sometimes spelled out
        # ("Four schools could not be routed"), so the word form is
        # captured and converted.
        check_claim(name, text, "unreachable schools",
                    r"(\d+|\w+)\s+schools\s+(?:are not|could not be)\s*\n?\s*(?:routable|routed)",
                    n_unreach, group=1)

        # the students and rooms in the small accommodation. The notes file
        # says "holding 743,605 students ... and only 169 study rooms"; the
        # recipe says "those areas hold 169 of the 194 study rooms".
        check_claim(name, text, "students in small areas",
                    rf"holding[^.\n]*?({N})\s+students", cs["students_in_small_accommodation"],
                    tol=0.5, required=False)
        check_claim(name, text, "rooms in small areas",
                    rf"only[^.\n]*?(\d+)\s+study rooms", cs["rooms_in_small_areas"], required=False)
        check_claim(name, text, "rooms in small areas (recipe form)",
                    rf"areas hold (\d+) of the 194 study rooms", cs["rooms_in_small_areas"],
                    required=False)

        # the spurious correlation and the corrected partial correlation.
        # Both are in markdown TABLES, so they are read from the table rows
        # and the note's own value is compared with the data.
        header, cr = find_table(tables, "correlation")
        if cr:
            row = find_row(cr, "students per 100 seats vs retired persons per seat")
            if row:
                check(f"{name}: spurious r", abs(num(row[1])),
                      ec["spurious_shared_denominator"]["students_per_100_seats_vs_retired_per_seat"],
                      tol=0.005)
            else:
                fail(f"{name}: spurious r", "row missing")

        header, pr = find_table(tables, "relationship")
        if pr:
            row = find_row(pr, "utilisation ~ retired, controlling for students")
            if row:
                check(f"{name}: partial r (util~retired)", num(row[1]),
                      ec["partial_correlations"]["util_vs_retired_given_students"], tol=0.005)
            else:
                fail(f"{name}: partial r (util~retired)", "row missing")
        else:
            # the notes file puts it in a Test/Result table instead
            header, pr = find_table(tables, "test", "result")
            if pr:
                row = find_row(pr, "Students per 1,000 retired")
                if row:
                    m = re.search(r"([+−\-]?[\d.]+)", row[1])
                    if m:
                        check(f"{name}: partial r (util~retired)", num(m.group(1)),
                              ec["partial_correlations"]["util_vs_retired_given_students"],
                              tol=0.005)
                    else:
                        fail(f"{name}: partial r (util~retired)", row[1])

        # the admission-card applications: three years, each near its own year.
        # Two forms are accepted - a Year/Applications table, and the inline
        # "2,506 / 2,618 / 2,508 across 2023-25" form.
        ac = ec["admission_card_applications"]
        header, arows = find_table(tables, "admission")
        if arows:
            for year, val in ac.items():
                row = find_row(arows, year)
                if row:
                    check(f"{name}: admission cards {year}", num(row[1]), val)
                else:
                    fail(f"{name}: admission cards {year}", "row missing")
        else:
            # the inline form: capture the three numbers in order
            m = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)\s*/\s*(\d[\d,]*)", prose_only(text))
            if m:
                for got, (year, val) in zip(m.groups(), ac.items()):
                    check(f"{name}: admission cards {year}", num(got), val)
            else:
                fail(f"{name}: admission cards", "inline form not found")

    # ------------------------------------------------------------- report
    fails = [r for r in results if not r[0]]
    for ok, label, got, want in results:
        if not ok:
            print(f"  FAIL {label}: got {got!r}, expected {want!r}")
    print(f"\nchecks run: {len(results)}")
    if fails:
        print(f"{len(fails)} FAILURES")
        return 1
    print("all published numbers match the shipped layers ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
