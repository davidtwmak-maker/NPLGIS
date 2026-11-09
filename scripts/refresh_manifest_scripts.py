#!/usr/bin/env python3
"""
Refresh the `scripts` section of assets/data/MANIFEST.json after a code change.

The three project-specific updaters only track their own project's scripts.
After a cross-cutting change (such as making the data paths configurable),
several scripts outside those projects change size and hash and the manifest
goes stale. This refreshes every script entry in place, preserving each
entry's description and only updating `bytes` and `sha256`.

It also enforces the repo convention: the `scripts` section holds only .py
files, and the `files` section holds only data, maps and notes.
"""
import hashlib
import json
import os

REPO = os.environ.get("NPLGIS_REPO", os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
MANIFEST = f"{REPO}/assets/data/MANIFEST.json"


def sha16(b):
    return hashlib.sha256(b).hexdigest()[:16]


def main():
    m = json.load(open(MANIFEST))
    changed = []
    problems = []

    for e in m["scripts"]:
        p = os.path.join(REPO, e["file"])
        if not os.path.exists(p):
            problems.append((e["file"], "MISSING"))
            continue
        b = open(p, "rb").read()
        if not e["file"].endswith((".py", ".sh")):
            problems.append((e["file"], "not a script in the scripts section"))
            continue
        if len(b) != e["bytes"] or not sha16(b).startswith(e["sha256"]):
            e["bytes"] = len(b)
            e["sha256"] = sha16(b)
            changed.append(e["file"])

    # The files section holds data, maps and notes. The code itself belongs
    # in the scripts section, so a .py here is a mistake.
    for e in m["files"]:
        low = e["file"].lower()
        if low.endswith(".py"):
            problems.append((e["file"], ".py in the files section"))

    json.dump(m, open(MANIFEST, "w"), indent=2, ensure_ascii=False)

    print(f"refreshed {len(changed)} script entries")
    for c in changed:
        print("   ", c)
    print(f"problems: {len(problems)}")
    for p in problems:
        print("   ", p)


if __name__ == "__main__":
    main()
