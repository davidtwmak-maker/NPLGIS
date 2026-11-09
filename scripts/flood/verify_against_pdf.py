#!/usr/bin/env python3
"""Cross-check the scraped DSD blockage GeoJSON against DSD's own published PDF list."""
import json
import os
import re

import pypdf

W = os.path.dirname(os.path.abspath(__file__))

pdf_path = os.path.join(W, "raw", "blockage.pdf")
reader = pypdf.PdfReader(pdf_path)
text = "\n".join((p.extract_text() or "") for p in reader.pages)

# The PDF is a flowed list of locations, one per entry, so normalise aggressively:
# strip page furniture, collapse whitespace, split on the known separator.
flat = re.sub(r"\s+", " ", text)
flat = re.sub(r"Page \d+ / \d+", " ", flat)

with open(os.path.join(W, "dsd_blockage.geojson"), encoding="utf-8") as fh:
    feats = json.load(fh)["features"]
titles = [f["properties"]["title"] for f in feats]

def norm(s):
    s = s.replace("&amp;", "&").replace("<br>", " ")
    s = re.sub(r"\(.*?\)", " ", s)          # drop parentheticals
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    # DSD's own PDF has a typo ("Morrision Hill Road") and the text layer splits
    # words across a line break ("sitti ng out area"). Repair both, otherwise the
    # comparison reports false misses on correct scraped data.
    s = s.replace("morrision", "morrison")
    s = re.sub(r"\b([a-z]{4,}) ([a-z]{1,3})\b(?= )", r"\1\2", s) if False else s
    s = s.replace("sitti ng", "sitting").replace("sittin g", "sitting")
    return s

flat_n = norm(flat)
# the PDF text layer can break a word anywhere; also build a de-spaced copy
flat_tight = re.sub(r"\s+", "", flat.lower().replace("morrision", "morrison"))

hits = [t for t in titles if norm(t) and (norm(t) in flat_n or norm(t).replace(" ", "") in flat_tight)]
miss = [t for t in titles if t not in hits]

print(f"PDF pages: {len(reader.pages)}")
print(f"scraped titles: {len(titles)}")
print(f"matched in PDF text: {len(hits)}")
print(f"not found in PDF text: {len(miss)}")
for m in miss[:15]:
    print("   MISS:", m[:90])

# Reverse check: how many PDF entries appear in the scrape?
pdf_units = [u.strip() for u in re.split(r"(?<=\))\s+(?=[A-Z])", flat) if len(u.strip()) > 18]
uniq_pdf = sorted(set(u for u in pdf_units if len(u) > 18))
in_scrape = [u for u in uniq_pdf if norm(u) and norm(u) in norm(" || ".join(titles))]
print(f"PDF location strings (approx): {len(uniq_pdf)}")
print(f"  of which found in the scrape: {len(in_scrape)}")

assert len(hits) >= len(titles) * 0.95, f"only {len(hits)}/{len(titles)} scraped titles found in the PDF"
print("OK: scraped list agrees with DSD's published PDF")
