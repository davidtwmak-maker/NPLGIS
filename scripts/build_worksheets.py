#!/usr/bin/env python3
"""Build a printable HTML site from the student worksheets.

The vault notes are Markdown; GitHub Pages will not render a .md file, so the
worksheets are converted to standalone HTML with one page per worksheet plus
an index. Pure standard library - no markdown package needed.

Run:  python3 scripts/build_worksheets.py
"""
import html
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "worksheets")
OUT = os.path.join(ROOT, "worksheet-site")

# ---------------------------------------------------------------- inline
INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
# angle-bracket autolink first: <https://...>
AUTOLINK = re.compile(r"&lt;(https?://[^\s&]+)&gt;")
BARE_URL = re.compile(r"(?<![\"'(=\]])\b(https?://[^\s<>\")]+)")
WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
# a run of 3+ underscores is a fill-in rule, not emphasis
RULE_RUN = re.compile(r"_{3,}")


def inline(text):
    """Escape, then apply inline markdown. Code spans are protected first."""
    stash = []

    def keep(m):
        stash.append(m.group(1))
        return f"\x00{len(stash)-1}\x00"

    text = INLINE_CODE.sub(keep, text)
    text = html.escape(text, quote=False)

    # bold that wraps an italic span: **... *x* ...** must be handled before
    # the plain bold rule, otherwise the inner * pair wins and the ** stays literal
    text = BOLD_ITALIC = re.compile(
        r"\*\*([^*]+?)\s*\*([^*\n]+?)\*([^*]*?)\*\*").sub(
        lambda m: f"<strong>{m.group(1)} <em>{m.group(2)}</em>{m.group(3)}</strong>", text)
    text = WIKILINK.sub(
        lambda m: f'<span class="wikilink">{m.group(2) or m.group(1)}</span>', text)
    text = AUTOLINK.sub(
        lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', text)
    text = LINK.sub(
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    text = BARE_URL.sub(r'<a href="\1">\1</a>', text)
    # restore code spans
    text = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{html.escape(stash[int(m.group(1))])}</code>", text)
    # fill-in rules -> a visible line
    text = RULE_RUN.sub('<span class="fill"></span>', text)
    return text


# ---------------------------------------------------------------- blocks
def split_row(line):
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


ALIGN = re.compile(r"^\|?[\s:\-|]+\|[\s:\-|]*$")


def is_table_sep(line):
    s = line.strip()
    return bool(s.startswith("|") and ALIGN.match(s) and "-" in s)


def convert(md):
    lines = md.split("\n")
    out = []
    i = 0
    n = len(lines)

    # frontmatter
    if lines and lines[0].strip() == "---":
        i = 1
        while i < n and lines[i].strip() != "---":
            i += 1
        i += 1

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # horizontal rule
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped) and not is_table_sep(stripped):
            out.append("<hr>")
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            lvl = len(m.group(1))
            txt = inline(m.group(2))
            anchor = re.sub(r"[^a-z0-9]+", "-", m.group(2).lower()).strip("-")
            out.append(f'<h{lvl} id="{anchor}">{txt}</h{lvl}>')
            i += 1
            continue

        # table
        if stripped.startswith("|") and i + 1 < n and is_table_sep(lines[i + 1]):
            header = split_row(stripped)
            aligns = []
            for c in split_row(lines[i + 1]):
                left, right = c.startswith(":"), c.endswith(":")
                aligns.append("center" if left and right else
                              "right" if right else
                              "left" if left else "")
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i].strip()))
                i += 1
            th = "".join(f'<th style="text-align:{a}">{inline(c)}</th>'
                         for c, a in zip(header, aligns))
            body = []
            for r in rows:
                tds = "".join(f'<td style="text-align:{a}">{inline(c)}</td>'
                              for c, a in zip(r, aligns + [""] * (len(aligns) - len(r))))
                body.append(f"<tr>{tds}</tr>")
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>")
            continue

        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            kind = "warn" if any("⚠" in b for b in buf) else "note"
            # join soft-wrapped lines first, so a single italic/bold span that
            # crosses a line break still renders as one run
            merged = []
            for b in buf:
                if merged and not re.match(r"^([-*]|\d+\.)\s", b) \
                        and not re.match(r"^([-*]|\d+\.)\s", merged[-1]) \
                        and merged[-1]:
                    merged[-1] = merged[-1] + " " + b
                else:
                    merged.append(b)
            paras = []
            for b in merged:
                if not b:
                    continue
                if re.match(r"^([-*]|\d+\.)\s", b):
                    paras.append(f"<p class='li'>{inline(b)}</p>")
                else:
                    paras.append(f"<p>{inline(b)}</p>")
            out.append(f'<blockquote class="{kind}">' + "".join(paras) + "</blockquote>")
            continue

        # code fence
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(f'<pre><code class="lang-{html.escape(lang)}">'
                       + html.escape("\n".join(buf)) + "</code></pre>")
            continue

        # list
        if re.match(r"^([-*]|\d+\.)\s+", stripped):
            ordered = bool(re.match(r"^\d+\.", stripped))
            items = []
            while i < n:
                s = lines[i].strip()
                mm = re.match(r"^([-*]|\d+\.)\s+(.*)$", s)
                if not mm:
                    if s and not items:
                        break
                    if s and re.match(r"^([-*]|\d+\.)\s+", s) is None:
                        break
                    break
                content = mm.group(2)
                i += 1
                # continuation lines (indented)
                cont = []
                while i < n and lines[i].startswith("  ") and lines[i].strip():
                    cont.append(lines[i].strip())
                    i += 1
                if cont:
                    content += " " + " ".join(cont)
                items.append(inline(content))
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{x}</li>" for x in items) + f"</{tag}>")
            continue

        # paragraph
        buf = []
        while i < n and lines[i].strip() and not re.match(
                r"^(#{1,6}\s|[-*]\s|\d+\.\s|>|```|\|)", lines[i].strip()):
            if is_table_sep(lines[i].strip()):
                break
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append("<p>" + inline(" ".join(buf)) + "</p>")
        else:
            i += 1

    return "\n".join(out)


# ---------------------------------------------------------------- page
CSS = """
:root{
  --ink:#1b1b1f; --muted:#5b5b66; --line:#d9d9e0; --bg:#ffffff;
  --accent:#1f4e79; --accent-soft:#eef4fa; --warn:#8a4b00; --warn-bg:#fdf3e3;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",
       "PingFang HK","Microsoft JhengHei",Helvetica,Arial,sans-serif;
}
.wrap{max-width:860px;margin:0 auto;padding:40px 26px 90px}
header.doc{border-bottom:3px solid var(--accent);padding-bottom:20px;margin-bottom:30px}
header.doc h1{margin:.2em 0 .3em;font-size:2rem;line-height:1.2;color:var(--accent)}
header.doc .meta{color:var(--muted);font-size:.9rem}
h1,h2,h3,h4{line-height:1.25;margin:1.6em 0 .5em}
h2{font-size:1.42rem;border-bottom:1px solid var(--line);padding-bottom:.28em;color:var(--accent)}
h3{font-size:1.14rem}h4{font-size:1.02rem}
p{margin:.7em 0}
ul,ol{margin:.6em 0;padding-left:1.5em}
li{margin:.32em 0}
hr{border:0;border-top:1px solid var(--line);margin:2em 0}
a{color:var(--accent)}
code{background:#f3f3f7;padding:.1em .35em;border-radius:4px;font-size:.88em;
  font-family:"SF Mono",Menlo,Consolas,monospace;word-break:break-word}
pre{background:#f6f6f9;border:1px solid var(--line);border-radius:8px;
  padding:14px 16px;overflow-x:auto}
pre code{background:none;padding:0;font-size:.85em;line-height:1.5}
table{border-collapse:collapse;width:100%;margin:1.1em 0;font-size:.93em}
th,td{border:1px solid var(--line);padding:8px 10px;vertical-align:top}
th{background:var(--accent-soft);font-weight:600;text-align:left}
tbody tr:nth-child(even){background:#fafafc}
blockquote{margin:1.1em 0;padding:.85em 1.1em;border-left:4px solid var(--accent);
  background:var(--accent-soft);border-radius:0 6px 6px 0}
blockquote.warn{border-left-color:var(--warn);background:var(--warn-bg)}
blockquote p{margin:.35em 0}
blockquote p:first-child{margin-top:0}
blockquote p:last-child{margin-bottom:0}
.fill{display:inline-block;min-width:11em;border-bottom:1px solid #9a9aa6;
  height:1.05em;vertical-align:baseline}
.wikilink{color:var(--accent);border-bottom:1px dotted var(--accent)}
.nav{display:flex;gap:12px;flex-wrap:wrap;margin:26px 0 0;padding-top:18px;
  border-top:1px solid var(--line);font-size:.9rem}
.nav a{padding:6px 12px;border:1px solid var(--line);border-radius:20px;
  text-decoration:none;background:#fafafc}
.nav a:hover{background:var(--accent-soft);border-color:var(--accent)}
.cover h1{font-size:2.1rem}
.cards{display:grid;gap:16px;margin:26px 0}
.card{border:1px solid var(--line);border-radius:10px;padding:18px 20px;background:#fcfcfe}
.card h3{margin-top:0}
.card a{font-weight:600;text-decoration:none}
.card .q{color:var(--muted);font-style:italic;margin:.3em 0 0}
.badge{display:inline-block;background:var(--accent-soft);color:var(--accent);
  border-radius:20px;padding:2px 11px;font-size:.78rem;font-weight:600;margin-right:6px}
.print-only{display:none}
@media print{
  .wrap{max-width:none;padding:0}
  .nav,.print-only{display:none}
  body{font-size:11.5pt;line-height:1.45}
  h2{page-break-after:avoid;font-size:14pt}
  h3{page-break-after:avoid}
  table,blockquote,pre{page-break-inside:avoid}
  a{color:#000;text-decoration:none}
  thead{display:table-header-group}
}
"""

NAV = """
<nav class="nav">
  <a href="index.html">&#8592; All worksheets</a>
  <a href="https://davidtwmak-maker.github.io/NPLGIS/">NPL GIS site</a>
  <a href="https://github.com/davidtwmak-maker/NPLGIS">Repository</a>
</nav>
"""


def page(title, body, extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="Student worksheet - NPL GIS Team">
<style>{CSS}</style>
{extra_head}
</head>
<body>
<div class="wrap">
{body}
{NAV}
</div>
</body>
</html>
"""


def slug(fn):
    s = os.path.splitext(fn)[0]
    s = re.sub(r"^Student Worksheet [—-] ", "", s)
    s = re.sub(r"^Student Worksheets [—-] ", "", s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    files = sorted(f for f in os.listdir(SRC) if f.endswith(".md"))
    index_md = [f for f in files if f.startswith("Student Worksheets")]
    sheets = [f for f in files if f.startswith("Student Worksheet ") and "Student Worksheets" not in f]

    # --- index
    body = f"""<header class="doc cover">
<h1>Student Worksheets &mdash; GIS Projects</h1>
<p class="meta">NPL GIS Team &middot; six task sheets built from the team's real GIS
projects &middot; every live figure re-verified against the source service on
26&nbsp;October&nbsp;2026.</p>
</header>

<div class="cards">
"""
    for f in sheets:
        md = open(os.path.join(SRC, f), encoding="utf-8").read()
        q = re.search(r"^> \*\*Your question:\*\* \*(.+?)\*$", md, re.M)
        lvl = re.search(r"^level:\s*(.+)$", md, re.M)
        qtxt = html.escape(q.group(1)) if q else ""
        badge = f'<span class="badge">{html.escape(lvl.group(1).strip())}</span>' if lvl else ""
        body += f"""<div class="card">
<h3>{badge}<a href="{slug(f)}.html">{html.escape(os.path.splitext(f)[0].replace('Student Worksheet — ',''))}</a></h3>
<p class="q">&ldquo;{qtxt}&rdquo;</p>
</div>
"""
    body += """</div>

<h2>How to use these</h2>
<ol>
<li>Print the worksheet, or fill it in on screen.</li>
<li>Every sheet gives you the <strong>real data</strong>, the <strong>real
method</strong>, and the <strong>check numbers</strong> to verify your run
against — so a wrong run is caught instead of quietly producing a wrong
conclusion.</li>
<li>Each sheet names the <strong>trap</strong> in its dataset. Read that part
before you start.</li>
<li>Every sheet ends with a <strong>data validation statement</strong> and a
<strong>limitations table</strong> to complete. Those two carry marks.</li>
</ol>

<h2>Prerequisites</h2>
<ul>
<li><a href="https://davidtwmak-maker.github.io/NPLGIS/">NPL GIS Team site</a>
&mdash; the live 3D mall model, the maps, and the full data set.</li>
<li><a href="https://github.com/davidtwmak-maker/NPLGIS">GitHub repository</a>
&mdash; every script and data layer the worksheets refer to.</li>
</ul>

<p class="print-only">Print note: these pages are styled for A4 printing.
Use your browser's print dialog; backgrounds are kept off by default, so add
&ldquo;print background colours&rdquo; if you want the table shading.</p>
"""
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(
        page("Student Worksheets — GIS Projects", body))

    # --- one page per worksheet
    for f in sheets:
        md = open(os.path.join(SRC, f), encoding="utf-8").read()
        t = os.path.splitext(f)[0].replace("Student Worksheet — ", "")
        content = convert(md)
        extra = ""
        m = re.search(r"^title:\s*'?(.+?)'?$", md, re.M)
        if m:
            extra = f'<meta property="og:title" content="{html.escape(m.group(1))}">'
        open(os.path.join(OUT, f"{slug(f)}.html"), "w", encoding="utf-8").write(
            page(t, content, extra))
        print(f"  built {slug(f)}.html  <- {f}")

    print(f"\n{len(sheets) + 1} pages written to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
