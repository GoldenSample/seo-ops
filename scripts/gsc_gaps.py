#!/usr/bin/env python3
"""
gsc_gaps.py: find search queries where a site is already visible but has no page that targets them.
Python 3.9+, standard library only.

Input: a query export (Google Search Console: Performance, Queries tab, Export; or a Yandex Webmaster
query export) and the site's pages (a CSV with url and title columns, or the sitemap: the script then
reads each page title, one request per second).

Output, three lists sorted by impressions:
  gaps      the query matches no page well (match below --gap-threshold): candidates for a new page
  striking  average position 8 to 20: a better page or internal links may move it to the first page
  low_ctr   top-5 position but CTR under half of a rough planning number: rewrite title and snippet

Usage
  python gsc_gaps.py Queries.csv --sitemap https://example.com/sitemap.xml [--format md|json|csv]
  python gsc_gaps.py Queries.csv --pages pages.csv [--min-impressions 10] [--gap-threshold 0.6] [--out FILE]

The match is word overlap after simple stemming (first 5 letters of long words), with Cyrillic words
also tried in Latin transliteration, so /motogarnitury/ matches the query "мотогарнитуры".
It is a sorting aid, not a verdict: read the lists before you plan pages.

Exit codes: 0 ok, 2 bad input or no pages. Source: https://github.com/GoldenSample/seo-ops (MIT).
Written by a local model from a spec and tests (tests/test_gaps.py), reviewed and extended by Claude.
"""
import argparse
import csv
import html.parser
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

VERSION = "1.1.0"
UA = "seo-ops-gaps/1.0 (+https://github.com/GoldenSample/seo-ops)"

ALIASES = {
    "query": ["top queries", "query", "queries", "запрос", "запросы", "поисковый запрос",
              "самые частые запросы", "популярные запросы"],
    "clicks": ["clicks", "клики", "клик"],
    "impressions": ["impressions", "показы", "показов"],
    "ctr": ["ctr"],
    "position": ["position", "average position", "avg. position", "позиция", "средняя позиция",
                 "средняя позиция показа"],
}
# Fallback when no header equals an alias: the first header that contains one of these parts.
PARTS = {
    "query": ["quer", "запрос"],
    "clicks": ["click", "клик"],
    "impressions": ["impression", "показ"],
    "ctr": ["ctr"],
    "position": ["position", "позиц"],
}


def parse_number(s) -> float:
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).replace(" ", "").replace("\xa0", "").replace(" ", "")
    if s in ("", "-", "—"):
        return 0.0
    if s.endswith("%"):
        s = s[:-1]
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.match(r"^\d{1,3}(,\d{3})+$", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise ValueError("not a number: %r" % s)


def _columns(headers):
    cols = {}
    for key, aliases in ALIASES.items():
        for i, h in enumerate(headers):
            if h in aliases:
                cols[key] = i
                break
    for key, parts in PARTS.items():
        if key in cols:
            continue
        for i, h in enumerate(headers):
            if i not in cols.values() and any(p in h for p in parts):
                cols[key] = i
                break
    return cols


def read_queries(source) -> list:
    """source: a file path, or the CSV text itself when it contains a newline."""
    if not isinstance(source, str):
        raise ValueError("source must be a file path or CSV text")
    if "\n" in source:
        content = source.lstrip("﻿")
    else:
        with open(source, "r", encoding="utf-8-sig") as f:
            content = f.read().lstrip("﻿")
    lines = content.splitlines()
    if not lines:
        return []
    first = lines[0]
    delim = max([",", ";", "\t"], key=lambda d: first.count(d))  # ties keep the earlier one
    reader = csv.reader(io.StringIO(content), delimiter=delim)
    headers = [h.strip().lower() for h in next(reader, [])]
    cols = _columns(headers)
    missing = [k for k in ("query", "impressions") if k not in cols]
    if missing:
        raise ValueError("missing columns: %s (header: %s)" % (", ".join(missing), ", ".join(headers)))

    def cell(row, key):
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else None

    out = []
    for row in reader:
        q = (cell(row, "query") or "").strip()
        if not q:
            continue
        clicks = parse_number(cell(row, "clicks"))
        impressions = parse_number(cell(row, "impressions"))
        raw_ctr = cell(row, "ctr")
        if raw_ctr is not None:
            v = parse_number(raw_ctr)
            ctr = v / 100.0 if ("%" in str(raw_ctr) or v > 1) else v
        else:
            ctr = clicks / impressions if impressions > 0 else 0.0
        out.append({"query": q, "clicks": clicks, "impressions": impressions, "ctr": ctr,
                    "position": parse_number(cell(row, "position"))})
    return out


STOP = {"в", "во", "на", "и", "с", "со", "для", "по", "о", "об", "от", "до", "из", "к", "ко", "за", "у", "а", "или",
        "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "with", "how", "what", "is",
        "как", "что", "какой", "какая", "какие", "какую"}

TRANSLIT = dict(zip("абвгдезийклмнопрстуфыэ", "abvgdeziyklmnoprstufye"))
TRANSLIT.update({"ж": "zh", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ь": "",
                 "ю": "yu", "я": "ya"})


def _stem(t):
    return t[:5] if len(t) >= 6 else t


def _words(text):
    text = (text or "").lower().replace("ё", "е")
    return [w for w in re.findall(r"[^\W_]+", text) if len(w) >= 2 and w not in STOP]


def tokens(text) -> list:
    return [_stem(w) for w in _words(text)]


def translit(word) -> str:
    return "".join(TRANSLIT.get(ch, ch) for ch in word)


def page_tokens(url, title) -> set:
    path = urllib.parse.urlsplit(url).path
    for ch in "-_/.":
        path = path.replace(ch, " ")
    return set(tokens(title)) | set(tokens(path))


def _forms(query):
    """One set of acceptable stems per query word: the word itself and its Latin transliteration."""
    return [{_stem(w), _stem(translit(w))} for w in _words(query)]


def best_page(query, pages) -> tuple:
    forms = _forms(query)
    if not forms or not pages:
        return (None, 0.0)
    best_url, best = None, 0.0
    for p in sorted(pages, key=lambda p: (len(p["url"]), p["url"])):  # ties: shorter, then alphabetical
        hit = sum(1 for f in forms if f & p["tokens"])
        score = hit / len(forms)
        if score > best:
            best_url, best = p["url"], score
    return (best_url, best) if best > 0 else (None, 0.0)


EXPECTED_CTR = {1: 0.25, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05}  # rough planning numbers, not a benchmark


def analyze(queries, pages, min_impressions=10, gap_threshold=0.6) -> dict:
    pd = [{"url": u, "title": t, "tokens": page_tokens(u, t)} for u, t in pages]
    rows = []
    for q in queries:
        if q["impressions"] < min_impressions:
            continue
        url, score = best_page(q["query"], pd)
        row = dict(q)
        row["page"], row["score"] = url, round(score, 2)
        rows.append(row)
    gaps, striking, low_ctr = [], [], []
    for r in rows:
        if r["score"] < gap_threshold:
            gaps.append(r)
        if 8 <= r["position"] <= 20:
            striking.append(r)
        if 0 < r["position"] <= 5.5:
            k = min(5, max(1, int(r["position"] + 0.5)))
            if r["ctr"] < 0.5 * EXPECTED_CTR[k]:
                low_ctr.append(r)

    def order(lst):
        return sorted(lst, key=lambda x: (-x["impressions"], x["query"]))
    return {"gaps": order(gaps), "striking": order(striking), "low_ctr": order(low_ctr),
            "pages": len(pages), "queries": len(rows)}


def to_markdown(result, top=30) -> str:
    out = ["# Query gaps",
           "Pages compared: %d. Queries with enough impressions: %d." % (result["pages"], result["queries"]), ""]
    for header, data in (("## Gap queries: visible, but no page targets them", result["gaps"]),
                         ("## Striking distance: positions 8-20", result["striking"]),
                         ("## Weak CTR in the top 5", result["low_ctr"])):
        out.append(header)
        if not data:
            out.append("None.")
        else:
            out.append("| Query | Impressions | Clicks | CTR | Position | Closest page | Match |")
            out.append("|---|---:|---:|---:|---:|---|---:|")
            for r in data[:top]:
                out.append("| %s | %d | %d | %.1f%% | %.1f | %s | %.2f |" % (
                    r["query"].replace("|", "\\|"), int(r["impressions"]), int(r["clicks"]), r["ctr"] * 100,
                    r["position"], r["page"] or "-", r["score"]))
            if len(data) > top:
                out.append("")
                out.append("%d more rows: use --top or --format csv." % (len(data) - top))
        out.append("")
    return "\n".join(out) + "\n"


def read_pages_csv(path) -> list:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = [h.strip().lower() for h in next(reader, [])]
        if "url" not in headers or "title" not in headers:
            raise ValueError("pages CSV needs url and title columns")
        u, t = headers.index("url"), headers.index("title")
        return [(row[u], row[t]) for row in reader if len(row) > max(u, t)]


class _Title(html.parser.HTMLParser):
    """Text of the first <title> outside <svg>; icon titles inside inline SVG are skipped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.on, self.done, self.svg = [], False, False, 0

    def handle_starttag(self, tag, attrs):
        if tag == "svg":
            self.svg += 1
        elif tag == "title" and not self.done and not self.svg:
            self.on = True

    def handle_endtag(self, tag):
        if tag == "svg" and self.svg:
            self.svg -= 1
        elif tag == "title" and self.on:
            self.on, self.done = False, True

    def handle_data(self, data):
        if self.on:
            self.parts.append(data)


def title_of(html_text) -> str:
    p = _Title()
    try:
        p.feed(html_text)
        p.close()
    except Exception:
        pass
    return re.sub(r"\s+", " ", "".join(p.parts)).strip()


def _get(url, limit):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(limit)
            cs = r.headers.get_content_charset() or "utf-8"
        return raw.decode(cs, "replace")
    except (urllib.error.URLError, OSError, ValueError, LookupError):
        return ""


def _locs(xml_text):
    try:
        root = ET.fromstring(xml_text.lstrip("﻿").strip())
    except ET.ParseError:
        return None, []
    kind = root.tag.split("}")[-1].lower()
    locs = [(el.text or "").strip() for el in root.iter() if el.tag.split("}")[-1].lower() == "loc"]
    return kind, [x for x in locs if x]


def fetch_titles(sitemap_url, max_pages=200, delay=1.0) -> list:
    """Read the sitemap (one level of sitemap index, at most 5 children) and the title of each page."""
    kind, locs = _locs(_get(sitemap_url, 50_000_000))
    if kind == "sitemapindex":
        urls = []
        for child in locs[:5]:
            _, sub = _locs(_get(child, 50_000_000))
            urls.extend(sub)
    else:
        urls = locs
    out = []
    for u in urls[:max_pages]:
        time.sleep(delay)
        out.append((u, title_of(_get(u, 200_000))))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Queries where the site is visible but no page targets them.")
    ap.add_argument("queries_csv", help="query export: Search Console Queries.csv or a Yandex Webmaster export")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pages", help="CSV with url and title columns")
    src.add_argument("--sitemap", help="sitemap URL: the script reads every page title, one per second")
    ap.add_argument("--min-impressions", type=int, default=10)
    ap.add_argument("--gap-threshold", type=float, default=0.6, help="match below this is a gap (0 to 1)")
    ap.add_argument("--top", type=int, default=30, help="rows per list in Markdown")
    ap.add_argument("--max-pages", type=int, default=200, help="pages to read from the sitemap")
    ap.add_argument("--format", choices=["md", "json", "csv"], default="md")
    ap.add_argument("--out", help="write here instead of stdout (UTF-8)")
    a = ap.parse_args(argv)
    try:
        queries = read_queries(a.queries_csv)
        pages = read_pages_csv(a.pages) if a.pages else fetch_titles(a.sitemap, max_pages=a.max_pages)
        if not pages:
            raise ValueError("no pages to compare: the pages CSV is empty or the sitemap gave no URLs")
        result = analyze(queries, pages, a.min_impressions, a.gap_threshold)
        if a.format == "md":
            text = to_markdown(result, top=a.top)
        elif a.format == "json":
            text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        else:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["list", "query", "impressions", "clicks", "ctr", "position", "page", "score"])
            for label in ("gaps", "striking", "low_ctr"):
                for r in result[label]:
                    w.writerow([label, r["query"], r["impressions"], r["clicks"], r["ctr"], r["position"],
                                r["page"] or "", r["score"]])
            text = buf.getvalue()
        if a.out:
            with open(a.out, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        else:
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass
            sys.stdout.write(text)
    except (ValueError, OSError) as e:
        sys.stderr.write("error: %s\n" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
