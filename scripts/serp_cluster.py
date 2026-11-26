#!/usr/bin/env python3
"""
serp_cluster.py: group search phrases into clusters by the URLs they share in the search results.
Python 3.9+, standard library only. No network and no key: it reads a CSV of results you collected.

Usage
  python serp_cluster.py serp.csv [--freq freq.csv ...] [--mode soft|hard] [--threshold 3] [--top 10]
                         [--site example.com] [--csv clusters.csv] [--md clusters.md] [--json clusters.json]

Input: the top results for each phrase, from any tool or service that exports them (the skill
seo-semantic-core lists sources). Two shapes are read:
  long  one row per result: phrase, position, url (a frequency column is used when present)
  wide  one row per phrase: the phrase, then the result URLs in position order (url1, url2, ... or any
        columns that hold URLs); a file whose first row already holds URLs is read as wide with no header
Headers in English or Russian; UTF-8 with or without BOM, or windows-1251; comma, semicolon or tab.
A phrase that appears twice keeps the first result at each position.
Frequencies come from a frequency column of the same file or from --freq: a CSV of phrase and frequency
(with or without a header), or the CSV of `wordstat.py top` (its total, top and similar rows); --freq may be
given more than once, a later file wins. Phrases are matched without case, ё as е.

How clusters are made (Arsenkin's clustering help, checked 2026-11-26; the skill seo-semantic-core gives
the sources). URLs are compared without the scheme, www, a default port, the trailing slash and the
#fragment; percent-encoding and punycode are decoded. Only results at positions 1 to --top count.
  soft  phrases in order of frequency; the first phrase not yet placed is the centre, and every other
        phrase that shares at least --threshold URLs with the centre joins it (articles, large cores)
  hard  a phrase joins only if it shares at least --threshold URLs with every phrase already in the
        cluster (niche projects, strong competition)
Defaults: soft, threshold 3, top 10 (Arsenkin: grouping strength 2 to 10, "optimal 3"; depth TOP-10).
Without frequencies the centres are taken in A to Z order.

With --site each cluster gets the page of your site that ranks for most of its phrases (at any depth the
file holds). A cluster where your site has no page is a candidate for a new page. One cluster spread over
several of your pages, and one page that is the main page of several clusters, are reported: both are
signs of pages that compete for one intent, or of clusters to merge.

Output: CSV with a row per phrase, a Markdown summary, JSON. Exit codes: 0 done, 2 bad input.
Source: https://github.com/GoldenSample/seo-ops (MIT).
"""
import argparse
import collections
import csv
import io
import json
import re
import sys
from urllib.parse import unquote, urlsplit

VERSION = "1.1.1"

ALIASES = {
    "phrase": ["phrase", "keyword", "keywords", "query", "queries", "key", "search query", "фраза", "фразы",
               "запрос", "запросы", "ключ", "ключи", "ключевое слово", "ключевая фраза", "поисковый запрос"],
    "url": ["url", "urls", "link", "address", "landing page", "result", "адрес", "ссылка", "url адрес",
            "страница", "документ"],
    "position": ["position", "pos", "rank", "place", "позиция", "место", "поз", "позиция в выдаче"],
    "frequency": ["frequency", "freq", "volume", "search volume", "count", "wordstat", "частота", "частотность",
                  "частотка", "показы", "показов в месяц", "запросов в месяц", "базовая частотность"],
}
PARTS = {"phrase": ["phrase", "keyword", "query", "фраз", "запрос", "ключ"],
         "url": ["url", "link", "адрес", "ссылк"],
         "position": ["position", "позиц"],
         "frequency": ["freq", "volume", "частот"]}
NUMBERED = re.compile(r"\d\W*$")          # "url 1", "позиция 3", "URL (2)": a column of the wide form
URL_RE = re.compile(r"^(https?://)?[\w.-]+\.[^\W\d_][\w-]+(:\d+)?([/?#]|$)", re.I)
QUOTED = re.compile(r'"(?:[^"]|"")*"')


# ---------------------------------------------------------------- clustering core
# Written for seo-ops by a local model from a spec and tests (43 known answers), reviewed by Claude.
# Claude's changes: the port is cut with rpartition and only when it is a number; percent-encoding and
# punycode are decoded and //host is read as a URL; candidates come from an inverted URL index walked in
# processing order, so large cores do not compare every pair (same result: tests/test_cluster.py checks it
# against the plain pairwise walk). A phrase with no shared URL can never join, since threshold >= 1.

def normalize_url(u):
    """Comparison key of a result URL: host without www and default port, path without the trailing slash,
    the query kept, the fragment dropped."""
    u = (u or "").strip()
    if u.startswith("//"):
        u = "http:" + u
    if "://" not in u:
        u = "http://" + u
    try:
        parts = urlsplit(u)
    except ValueError:
        return u.lower()
    netloc = parts.netloc.lower()
    host, sep, port = netloc.rpartition(":")
    if not sep or not port.isdigit():
        host, port = netloc, ""
    if port in ("80", "443"):
        port = ""
    if host.startswith("www."):
        host = host[4:]
    if "xn--" in host:
        try:
            host = host.encode("ascii").decode("idna")
        except (UnicodeError, ValueError):
            pass
    res = host + (":" + port if port else "") + unquote(parts.path).rstrip("/")
    if parts.query:
        res += "?" + unquote(parts.query)
    return res


def cluster(serps, freq=None, threshold=3, mode="soft", top=10):
    """serps: {phrase: [result URLs in position order]}; freq: {phrase: number} or None.
    Returns clusters in the order they were made: {centre, phrases, freq, shared_urls, no_serp}."""
    if mode not in ("soft", "hard"):
        raise ValueError("mode must be either 'soft' or 'hard'")
    if not isinstance(top, int) or top < 1:
        raise ValueError("top must be at least 1")
    if not (1 <= threshold <= top):
        raise ValueError("threshold must be between 1 and top (inclusive)")
    sets = {}
    for phrase in serps:
        keys = set()
        for u in list(serps[phrase])[:top]:
            k = normalize_url(u)
            if k:
                keys.add(k)
        sets[phrase] = keys

    def f(p):
        return freq.get(p, 0) if freq else 0
    order = sorted(serps, key=lambda p: (-f(p), p))
    rank = {p: i for i, p in enumerate(order)}
    index = collections.defaultdict(list)
    for p in order:
        for k in sets[p]:
            index[k].append(p)
    placed, out = set(), []
    for centre in order:
        if centre in placed:
            continue
        placed.add(centre)
        members = [centre]
        if sets[centre]:
            cands = set()
            for k in sets[centre]:
                cands.update(index[k])
            for p in sorted(cands - placed, key=rank.get):
                if mode == "soft":
                    ok = len(sets[p] & sets[centre]) >= threshold
                else:
                    ok = all(len(sets[p] & sets[m]) >= threshold for m in members)
                if ok:
                    members.append(p)
                    placed.add(p)
        shared = []
        if len(members) > 1:
            counts = collections.Counter(k for m in members for k in sets[m])
            shared = sorted((k for k, n in counts.items() if n >= 2), key=lambda k: (-counts[k], k))
        out.append({"centre": centre, "phrases": members, "freq": sum(f(m) for m in members),
                    "shared_urls": shared, "no_serp": not sets[centre]})
    return out


# ---------------------------------------------------------------- input

def fkey(p):
    """Matching key of a phrase: lower case, ё as е, single spaces."""
    return " ".join((p or "").lower().replace("ё", "е").split())


def clean_phrase(s):
    return " ".join((s or "").split())


def parse_number(s):
    s = str(s if s is not None else "").replace(" ", "").replace("\xa0", "").replace(" ", "")
    if s in ("", "-", "—"):
        return None
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.match(r"^\d{1,3}(,\d{3})+$", s) else s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def looks_like_url(s):
    s = (s or "").strip()
    return bool(s) and " " not in s and URL_RE.match(s) is not None


def read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251")


def read_rows(text):
    """CSV rows without blank ones; the delimiter is the one the first line uses most outside quotes."""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return []
    bare = QUOTED.sub("", lines[0])
    delim = max((",", ";", "\t"), key=bare.count)
    return [r for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim) if any(c.strip() for c in r)]


def columns(headers):
    """Column index of phrase, position and frequency by header name (exact names first, then parts)."""
    cols, used = {}, set()
    for key in ("phrase", "position", "frequency"):
        for i, h in enumerate(headers):
            if i not in used and h in ALIASES[key]:
                cols[key] = i
                used.add(i)
                break
    for key in ("phrase", "position", "frequency"):
        if key in cols:
            continue
        for i, h in enumerate(headers):
            if h and i not in used and any(p in h for p in PARTS[key]) and not NUMBERED.search(h):
                cols[key] = i
                used.add(i)
                break
    return cols


def is_url_header(h):
    return bool(h) and (h in ALIASES["url"] or any(p in h for p in PARTS["url"]))


def read_serp(path):
    """{'positions': {phrase: [(position, url)]}, 'freq': {phrase: n}, 'shape': 'long'|'wide', 'header': bool}."""
    rows = read_rows(read_text(path))
    if not rows:
        raise ValueError("%s is empty" % path)
    header = sum(1 for c in rows[0] if looks_like_url(c)) < 2
    if header:
        headers, data = [h.strip().lower() for h in rows[0]], rows[1:]
    else:
        headers, data = [""] * max(len(r) for r in rows), rows
    cols = columns(headers)
    url_heads = [i for i, h in enumerate(headers) if is_url_header(h)]
    display, positions, freq = {}, collections.OrderedDict(), {}

    def slot(cell):
        phrase = clean_phrase(cell)
        if not phrase:
            return None
        p = display.setdefault(fkey(phrase), phrase)
        positions.setdefault(p, [])
        return p

    def cell(r, i):
        return r[i] if i is not None and i < len(r) else ""

    if 1 <= len(url_heads) <= 2:
        shape = "long"
        exact = [i for i in url_heads if headers[i] in ALIASES["url"]]
        ui = exact[0] if exact else url_heads[0]
        pi = cols.get("phrase")
        if pi is None or pi == ui:
            pi = 0 if ui != 0 else 1
        po = cols.get("position") if cols.get("position") not in (ui, pi) else None
        fi = cols.get("frequency") if cols.get("frequency") not in (ui, pi, po) else None
        for r in data:
            p = slot(cell(r, pi))
            if p is None:
                continue
            lst = positions[p]
            pos = parse_number(cell(r, po)) if po is not None else None
            url = cell(r, ui).strip()
            if url:
                lst.append((pos if pos is not None else len(lst) + 1, url))
            v = parse_number(cell(r, fi)) if fi is not None else None
            if v is not None:
                freq[p] = v
    else:
        shape = "wide"
        pi = cols.get("phrase", 0)
        fi = cols.get("frequency")
        url_cols = []
        for i in range(len(headers)):
            if i in (pi, fi):
                continue
            vals = [r[i].strip() for r in data if i < len(r) and r[i].strip()]
            if vals and 2 * sum(1 for v in vals if looks_like_url(v)) >= len(vals):
                url_cols.append(i)
        if not url_cols:
            raise ValueError("no URL column in %s: give a url column (one row per result) or URL columns "
                             "(one row per phrase); header: %s" % (path, ", ".join(headers)))
        for r in data:
            p = slot(cell(r, pi))
            if p is None:
                continue
            for n, i in enumerate(url_cols, 1):
                if looks_like_url(cell(r, i)):
                    positions[p].append((n, cell(r, i).strip()))
            v = parse_number(cell(r, fi)) if fi is not None else None
            if v is not None:
                freq[p] = v
    if not positions:
        raise ValueError("no phrase rows in %s (header: %s)" % (path, ", ".join(headers)))
    for p in positions:
        positions[p].sort(key=lambda x: x[0])
    return {"positions": positions, "freq": freq, "shape": shape, "header": header}


def read_freq(path):
    """{fkey(phrase): frequency} from a phrase and frequency CSV or from the CSV of wordstat.py top."""
    rows = read_rows(read_text(path))
    if not rows:
        raise ValueError("--freq %s is empty" % path)
    headers, data = [h.strip().lower() for h in rows[0]], rows[1:]
    out = {}
    if {"phrase", "type", "query", "count"} <= set(headers):
        t, q, c = headers.index("type"), headers.index("query"), headers.index("count")
        for r in data:
            if len(r) > max(t, q, c) and r[t].strip() in ("total", "top", "similar") and r[q].strip():
                v = parse_number(r[c])
                if v is not None:
                    k = fkey(r[q])
                    out[k] = max(out.get(k, v), v)
        return out
    cols = columns(headers)
    if "phrase" in cols and "frequency" in cols:
        pi, fi = cols["phrase"], cols["frequency"]
    elif len(rows[0]) >= 2 and parse_number(rows[0][1]) is not None:
        pi, fi, data = 0, 1, rows
    else:
        raise ValueError("--freq %s needs a phrase and a frequency column (header: %s)" % (path, ", ".join(headers)))
    for r in data:
        if len(r) > max(pi, fi) and r[pi].strip():
            v = parse_number(r[fi])
            if v is not None:
                out[fkey(r[pi])] = v
    return out


def first_per_position(lst):
    seen, out, dropped = set(), [], 0
    for pos, url in lst:
        if pos in seen:
            dropped += 1
            continue
        seen.add(pos)
        out.append((pos, url))
    return out, dropped


# ---------------------------------------------------------------- site pages

def host_of(key):
    return re.split(r"[/?]", key, maxsplit=1)[0]


def site_hits(positions, site):
    """{phrase: (position, url)}: the best result of the site for each phrase, at any depth the file holds."""
    want = host_of(normalize_url(site))
    hits = {}
    for phrase, lst in positions.items():
        for pos, url in lst:
            if host_of(normalize_url(url)) == want:
                hits[phrase] = (pos, url)
                break
    return hits


def attach_site(clusters, hits):
    """Sets site_page, site_position, site_covers and site_note on each cluster; returns the pages that are
    the main page of more than one cluster: {page key: [cluster ids]}."""
    page_clusters = collections.defaultdict(list)
    for c in clusters:
        pages, best = collections.Counter(), {}
        for p in c["phrases"]:
            if p in hits:
                pos, url = hits[p]
                k = normalize_url(url)
                pages[k] += 1
                if k not in best or pos < best[k][0]:
                    best[k] = (pos, url)
        if not pages:
            c.update(site_page=None, site_position=None, site_covers=0,
                     site_note="no page of the site in the results: candidate for a new page")
            continue
        k = sorted(pages, key=lambda x: (-pages[x], best[x][0], x))[0]
        c.update(site_page=best[k][1], site_position=best[k][0], site_covers=pages[k], site_note="")
        if len(pages) > 1:
            c["site_note"] = "several pages of the site: " + ", ".join(
                "%s (%d)" % (best[x][1], pages[x]) for x in sorted(pages, key=lambda x: (-pages[x], x)))
        page_clusters[k].append(c["id"])
    return {k: v for k, v in page_clusters.items() if len(v) > 1}


# ---------------------------------------------------------------- output

def md_cell(s):
    return str(s).replace("|", "\\|")


def count(n, one, many):
    """'1 phrase', '2 phrases'."""
    return "%d %s" % (n, one if n == 1 else many)


def to_markdown(clusters, params, stats, conflicts, site):
    lines = ["# serp_cluster %s" % VERSION, "",
             "%s, %s (%d of one phrase, %s without results in the top). " % (
                 count(stats["phrases"], "phrase", "phrases"), count(stats["clusters"], "cluster", "clusters"),
                 stats["singletons"], count(stats["no_serp"], "phrase", "phrases")) +
             "Mode %(mode)s, threshold %(threshold)d shared URLs, top %(top)d." % params, ""]
    head, sep = "| # | Centre | Phrases | Frequency | Shared URLs |", "|---|---|---|---|---|"
    if site:
        head, sep = head + " Site page |", sep + "---|"
    lines += [head, sep]
    for c in sorted(clusters, key=lambda c: (-c["freq"], c["id"])):
        row = "| %d | %s | %d | %s | %s |" % (c["id"], md_cell(c["centre"]), len(c["phrases"]), c["freq"],
                                            md_cell(", ".join(c["shared_urls"][:3])) or "-")
        if site:
            row += " %s |" % ("-" if c["no_serp"] else md_cell(c.get("site_page") or "new page"))
        lines.append(row)
    if site:
        new = [c for c in clusters if not c.get("site_page") and not c["no_serp"]]
        split = [c for c in clusters if c.get("site_note", "").startswith("several")]
        if new:
            lines += ["", "## Candidates for new pages (%d)" % len(new), ""]
            lines += ["- %s: %s, frequency %s" % (c["centre"], count(len(c["phrases"]), "phrase", "phrases"),
                                                  c["freq"])
                      for c in sorted(new, key=lambda c: (-c["freq"], c["id"]))]
        if split:
            lines += ["", "## One cluster, several pages of the site (%d)" % len(split), ""]
            lines += ["- %s: %s" % (c["centre"], c["site_note"].split(": ", 1)[1]) for c in split]
        if conflicts:
            by_id = {c["id"]: c for c in clusters}
            lines += ["", "## One page, main page of several clusters (%d)" % len(conflicts), ""]
            for ids in conflicts.values():
                lines.append("- %s: %s" % (by_id[ids[0]]["site_page"], "; ".join(by_id[i]["centre"] for i in ids)))
    return "\n".join(lines) + "\n"


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Cluster search phrases by shared result URLs (CSV in, no network).")
    ap.add_argument("serp", help="CSV of results: long (phrase, position, url) or wide (phrase, url1, url2, ...)")
    ap.add_argument("--freq", action="append", default=[],
                    help="CSV of phrase and frequency, or the CSV of wordstat.py top; may be given more than once")
    ap.add_argument("--mode", choices=("soft", "hard"), default="soft")
    ap.add_argument("--threshold", type=int, default=3, help="shared URLs needed to join (default 3)")
    ap.add_argument("--top", type=int, default=10, help="result positions that count, 1 to N (default 10)")
    ap.add_argument("--site", help="your host: each cluster gets the page of the site that ranks for it")
    ap.add_argument("--csv", help="write one row per phrase")
    ap.add_argument("--md", help="write a Markdown summary")
    ap.add_argument("--json", help="write clusters and parameters as JSON")
    a = ap.parse_args(argv)
    if not (1 <= a.threshold <= a.top):
        print("error: --threshold must be between 1 and --top")
        return 2
    try:
        data = read_serp(a.serp)
        extra = {}
        for path in a.freq:
            extra.update(read_freq(path))
    except (OSError, ValueError) as e:
        print("error: %s" % e)
        return 2
    positions = data["positions"]
    freq = dict(data["freq"])
    matched = 0
    for p in positions:
        if fkey(p) in extra:
            freq[p] = extra[fkey(p)]
            matched += 1
    serps, dropped = {}, 0
    for p, lst in positions.items():
        kept, n = first_per_position(lst)
        dropped += n
        positions[p] = kept
        serps[p] = [u for pos, u in kept if pos <= a.top]
    clusters = cluster(serps, freq or None, a.threshold, a.mode, a.top)
    for n, c in enumerate(clusters, 1):
        c["id"] = n
    hits = site_hits(positions, a.site) if a.site else {}
    conflicts = attach_site(clusters, hits) if a.site else {}
    params = {"mode": a.mode, "threshold": a.threshold, "top": a.top}
    stats = {"phrases": len(serps), "clusters": len(clusters),
             "singletons": sum(1 for c in clusters if len(c["phrases"]) == 1),
             "no_serp": sum(1 for c in clusters if c["no_serp"]),
             "with_frequency": sum(1 for p in serps if p in freq)}
    notes = ["%s form%s" % (data["shape"], "" if data["header"] else ", no header row")]
    if a.freq:
        notes.append("--freq matched %d of %d phrases" % (matched, len(serps)))
    if not freq:
        notes.append("no frequencies: centres in A to Z order")
    if dropped:
        notes.append("%d repeated results of the same phrase and position ignored" % dropped)
    print("serp_cluster: %s -> %s (%d of one phrase, %d without results in the top)" % (
        count(stats["phrases"], "phrase", "phrases"), count(stats["clusters"], "cluster", "clusters"),
        stats["singletons"], stats["no_serp"]))
    print("  mode %s, threshold %d, top %d; %s" % (a.mode, a.threshold, a.top, "; ".join(notes)))
    shown = [c for c in sorted(clusters, key=lambda c: (-c["freq"], c["id"])) if len(c["phrases"]) > 1][:20]
    for c in shown:
        tail = (" -> %s" % (c.get("site_page") or "new page")) if a.site else ""
        print("  #%d %s: %d phrases, frequency %s%s" % (c["id"], c["centre"], len(c["phrases"]), c["freq"], tail))
    if a.site:
        print("  site %s: %s without a page of the site, %d spread over several pages, %s the main page of "
              "several clusters" % (
                  a.site, count(sum(1 for c in clusters if not c.get("site_page") and not c["no_serp"]),
                                "cluster", "clusters"),
                  sum(1 for c in clusters if c.get("site_note", "").startswith("several")),
                  count(len(conflicts), "page is", "pages are")))
    try:
        if a.csv:
            with open(a.csv, "w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["cluster", "centre", "phrase", "frequency", "cluster_frequency", "cluster_size",
                            "site_url", "site_position", "cluster_site_page", "no_serp"])
                for c in clusters:
                    for p in c["phrases"]:
                        pos, url = hits.get(p, ("", ""))
                        w.writerow([c["id"], c["centre"], p, freq.get(p, ""), c["freq"], len(c["phrases"]), url, pos,
                                    c.get("site_page") or "", "yes" if not serps[p] else ""])
        if a.md:
            with open(a.md, "w", encoding="utf-8") as fh:
                fh.write(to_markdown(clusters, params, stats, conflicts, bool(a.site)))
        if a.json:
            with open(a.json, "w", encoding="utf-8") as fh:
                json.dump({"version": VERSION, "params": params, "stats": stats, "shape": data["shape"],
                           "site": a.site, "clusters": clusters, "page_in_several_clusters": conflicts},
                          fh, ensure_ascii=False, indent=1)
    except OSError as e:
        print("error: %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
