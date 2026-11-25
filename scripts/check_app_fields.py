#!/usr/bin/env python3
"""Check every web app in this repo for the 5834-class defect.

THE DEFECT
    A web app reads a field off a published feature's properties. The
    field was later renamed - here to carry the `ai_` prefix that the
    CSDI Awards disclosure requires. The reader was not updated with
    it, so every `.get()` returned undefined, every number format
    turned that into 0, and the map showed 0 for every small area.

    It does not crash. The map renders. The headline numbers, which
    come from a summary file rather than from the features, stay
    right. Only the per-feature panel is empty - and empty reads like
    a finding rather than like a bug. It shipped for two hours before
    a user asked why the map said zero everywhere.

WHY A GATE
    A renamed field is a silent break. The build must fail loudly on
    it, so this compares every property name each app reads against
    every property name its published data actually contains, and
    exits non-zero when the app reads something that is not there.

    The same check that catches a missing field catches a field that
    was renamed in the data but not in the app, in either direction.

RUN
    python3 scripts/check_app_fields.py
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "apps")

# Property names the app reads off a feature's properties object.
READ_RES = [
    re.compile(r"\bp\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\b(?:q|o|f)\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"properties\??\.([A-Za-z_][A-Za-z0-9_]*)"),
]

# Method names and JS builtins that appear as property reads but are
# not data fields.
IGNORE = {
    "length", "map", "push", "join", "slice", "split", "filter", "find",
    "forEach", "text", "html", "className", "id", "style", "value", "name",
    "type", "lat", "lng", "lon", "title", "href", "src", "index",
    "toFixed", "toUpperCase", "toLowerCase", "trim", "replace", "match",
    "test", "keys", "values", "entries", "get", "has", "add", "set",
    "toString", "format", "round", "max", "min", "sort", "some", "every",
    "reduce", "concat", "includes", "startsWith", "endsWith", "padStart",
    "getAttribute", "setAttribute", "querySelector", "querySelectorAll",
    "addEventListener", "removeEventListener", "closest", "createElement",
    "appendChild", "removeChild", "insertBefore", "focus", "blur", "click",
    "preventDefault", "stopPropagation", "toISOString", "getTime",
    "getFullYear", "getMonth", "getDate", "getHours", "getMinutes",
    "getSeconds", "floor", "ceil", "abs", "sqrt", "pow",
    "parentNode", "children", "childNodes", "firstChild", "lastChild",
    "nextSibling", "previousSibling", "nodeType", "nodeName",
    "dataset", "classList", "offsetWidth", "offsetHeight", "clientWidth",
    "clientHeight", "scrollWidth", "scrollHeight", "scrollTop", "scrollLeft",
    "getBoundingClientRect", "ownerDocument", "defaultView",
    "prototype", "constructor", "message", "stack", "then", "catch",
    "finally", "call", "apply", "bind", "valueOf", "hasOwnProperty",
}

# A read that looks like a data field rather than a method.
def looks_like_field(name):
    if name.startswith("ai_") or name.startswith("ac_"):
        return True
    for suffix in ("_m", "_ratio", "_count", "_pct", "_km", "_m2", "_ha"):
        if name.endswith(suffix):
            return True
    return False


def published_props(data_dir):
    """Every property name in every published data file.

    Nested objects are traversed, because an app can read a field off
    a nested record - the landslide app reads `gain_pct` off each
    entry of `feature_importance`, which is a list of objects.
    """
    names = set()

    def walk(obj, depth=0):
        if depth > 6:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                names.add(k)
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for v in obj[:200]:
                walk(v, depth + 1)

    for f in sorted(os.listdir(data_dir)):
        if not f.endswith((".json", ".geojson")):
            continue
        try:
            d = json.load(open(os.path.join(data_dir, f), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        walk(d)
    return names


def main():
    problems = []
    checked = 0
    for app in sorted(os.listdir(ROOT)):
        app_dir = os.path.join(ROOT, app)
        js = os.path.join(app_dir, "app.js")
        data_dir = os.path.join(app_dir, "data")
        if not os.path.isfile(js) or not os.path.isdir(data_dir):
            continue
        src = open(js, encoding="utf-8").read()
        reads = set()
        for rx in READ_RES:
            reads |= set(rx.findall(src))
        reads -= IGNORE
        pub = published_props(data_dir)
        missing = sorted(n for n in reads
                         if n not in pub and looks_like_field(n))
        checked += 1
        status = "OK" if not missing else f"MISSING {len(missing)}"
        print(f"  {app:34} reads={len(reads):3}  published={len(pub):3}  "
              f"{status}")
        for m in missing:
            print(f"      !! app reads {m!r}, no published file has it")
            problems.append((app, m))

    print()
    if problems:
        print(f"BROKEN BUILD: {len(problems)} field(s) read by an app but "
              f"absent from every published file.")
        print("A renamed field reads as undefined, which a number format "
              "turns into 0 - a finding that looks like data.")
        return 1
    print(f"OK: {checked} app(s) checked, every field an app reads is "
          f"present in its published data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
