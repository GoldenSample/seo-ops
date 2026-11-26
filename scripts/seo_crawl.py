#!/usr/bin/env python3
"""
seo_crawl.py: crawl a live site from its home page and its sitemap. Python 3.9+, standard library only.
No tokens, no login.

Usage
  python seo_crawl.py example.com [--max-pages 200] [--max-seconds 600] [--delay 0.5] [--include-query]
                      [--json crawl.json] [--md crawl.md] [--csv pages.csv] [--compare old-crawl.json]
                      [--resolve host=IP] [--fail-on fail|warn]
  python seo_crawl.py --selftest

The host you pass is the canonical host (with or without www, as your site uses it); https is assumed.
A full origin such as http://127.0.0.1:8000 works too, for a local build.

How it crawls
  1. robots.txt first. The crawler obeys the group for seo-ops-crawl, else the * group. A robots.txt that
     answers 5xx or gives no answer stops the crawl: RFC 9309 tells crawlers to treat the whole site as
     disallowed then. A 429 stops it too, the way Google treats a 429 on robots.txt.
  2. Breadth-first from the home page along <a href> links on the same host and scheme.
  3. Then the sitemap URLs that no link reached (robots.txt Sitemap lines, else /sitemap.xml; sitemap
     index files are followed).
  Redirects are not followed blindly: the target goes into the queue, so chains and loops show. Links with
  a query string are counted but not crawled without --include-query. Files (pdf, images, archives) get a
  HEAD request. Cyrillic paths and hosts are percent-encoded and punycoded the way a browser does it. A page
  without a declared charset that is not valid UTF-8 is read as windows-1251, the default the HTML standard
  suggests for the Russian locale. Politeness as seo_check.py: at most 2 requests per second, an honest
  User-Agent, at most --max-pages URLs per run. A 429 or 503 answer makes the crawler wait (Retry-After, else
  10 s doubling) and slow down to one request per second or slower; a URL that still answers 429 after three
  retries stops the crawl, and the URLs left count as not checked, not as errors of the site.

One line per check: id | OK, WARN, FAIL, INFO or SKIP | detail (the JSON and Markdown reports carry every item)
  crawl-coverage    what was crawled and whether the crawl is complete
  broken-links      internal links to pages that answer 4xx, with the pages that link to them
  server-errors     URLs that answered 5xx or 429, or did not answer
  redirect-links    internal links that point to a redirect: link to the final URL instead
  redirect-chains   two or more redirects in a row, loops, redirects without Location or to an error
  sitemap-errors    sitemap URLs that are not 200, have noindex, a canonical to another URL, are closed by
                    robots.txt or sit on another host
  not-in-sitemap    indexable pages that links reach but the sitemap does not list
  orphans           sitemap URLs that no chain of links from the home page reaches (needs a complete crawl)
  canonical         several canonical tags, canonical to another host, to a redirect, an error or noindex
  noindex           pages with noindex in a robots meta tag or in the X-Robots-Tag header
  titles            empty and duplicate titles among indexable pages
  h1                missing, empty and duplicate H1 among indexable pages
  mixed-host-links  links to the other scheme (http/https) or the other www form of the host
  robots-blocked    internal URLs that robots.txt closes to the crawler
  query-urls        links with a query string
  depth             clicks from the home page
  crawl-diff        with --compare: new errors, lost pages and changed titles since an earlier crawl JSON

Exit codes
  0  no FAIL (with --fail-on warn: no FAIL and no WARN); --selftest: every planted defect was caught
  1  at least one FAIL (or WARN with --fail-on warn); --selftest: some check stayed silent on a defect
  2  site unreachable (robots.txt and home page give no answer, or the home page answers 5xx) or bad arguments

Source: https://github.com/GoldenSample/seo-ops (MIT).
"""
import argparse
import collections
import csv
import datetime
import json
import os
import re
import socket
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo_check as sc  # noqa: E402  (same scripts folder)

VERSION = "1.1.1"
UA = "seo-ops-crawl/%s (+https://github.com/GoldenSample/seo-ops)" % VERSION
AGENT = "seo-ops-crawl"
HTML_ACCEPT = "text/html,application/xhtml+xml"
FILE_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|avif|svg|ico|bmp|tiff?|zip|rar|7z|gz|tgz|tar|docx?|xlsx?|pptx?|"
                      r"odt|ods|csv|txt|xml|json|mp3|mp4|m4a|webm|mov|avi|wav|ogg|woff2?|ttf|otf|eot|exe|dmg|apk)$", re.I)
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "ftp:", "skype:", "viber:", "whatsapp:", "tg:",
                "geo:", "callto:", "intent:", "file:")
META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I)
PATH_SAFE = "/%:@!$&'()*+,;=-._~"
QUERY_SAFE = PATH_SAFE + "?"
MAX_SITEMAPS = 50
MAX_SITEMAP_URLS = 50000
MAX_ITEMS = 50
DEEP = 3
RETRY_STATUSES = (429, 503)
RETRIES = 3          # more tries of one URL after 429 or 503
BACKOFF = 10.0       # seconds before the first retry when there is no Retry-After; doubles with each try
MAX_PAUSE = 120.0    # the longest Retry-After the crawler waits for
SLOW_FLOOR = 1.0     # after a 429 or 503: at least this many seconds between requests
MAX_DELAY = 8.0
R = sc.R
STATUSES = sc.STATUSES


def RI(i, status, detail, items=None):
    """A result line with the full list of items behind it (kept in the JSON and Markdown reports)."""
    r = R(i, status, detail)
    if items:
        r["items"] = list(items)
    return r


# ---------------------------------------------------------------- URLs and text

def ascii_url(url):
    """The URL a browser sends: non-ASCII path and query percent-encoded, a non-ASCII host in punycode,
    %xx escapes in upper case."""
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    netloc = p.netloc
    if any(ord(ch) > 127 for ch in netloc):
        m = re.match(r"^(.*?)(:\d+)?$", netloc)
        host, port = (m.group(1), m.group(2) or "") if m else (netloc, "")
        try:
            netloc = host.encode("idna").decode("ascii") + port
        except UnicodeError:
            pass
    out = urllib.parse.urlunsplit((p.scheme, netloc, urllib.parse.quote(p.path, safe=PATH_SAFE),
                                   urllib.parse.quote(p.query, safe=QUERY_SAFE), p.fragment))
    return re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group(0).upper(), out)


def header_url(s):
    """http.client reads header bytes as latin-1; a Location sent as raw UTF-8 is turned back into text."""
    if s and any(ord(ch) > 127 for ch in s):
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


def retry_after(resp):
    """Seconds from a Retry-After header (a number or an HTTP date), None when there is none."""
    v = resp.h("retry-after").strip()
    if not v:
        return None
    if v.isdigit():
        return float(v)
    try:
        import email.utils
        when = email.utils.parsedate_to_datetime(v)
        return max(0.0, (when - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def page_text(resp):
    """The body as text: the charset of the header, else <meta charset>, else UTF-8, else windows-1251
    (the default the HTML standard suggests for the Russian locale:
    https://html.spec.whatwg.org/multipage/parsing.html#determining-the-character-encoding)."""
    if not resp.raw or re.search(r"charset=", resp.h("content-type"), re.I):
        return resp.body
    m = META_CHARSET.search(resp.raw[:4096])
    if m:
        try:
            return resp.raw.decode(m.group(1).decode("ascii"), "replace")
        except LookupError:
            pass
    try:
        return resp.raw.decode("utf-8")
    except UnicodeDecodeError:
        return resp.raw.decode("cp1251", "replace")


def parse_site(site):
    """'example.com' or 'https://example.com' or 'http://127.0.0.1:8000' -> (scheme, host)."""
    s = (site or "").strip()
    if not re.match(r"(?i)^https?://", s):
        s = "https://" + s
    p = urllib.parse.urlsplit(ascii_url(s))
    if not p.netloc or " " in p.netloc:
        raise ValueError("no host in %r" % site)
    return p.scheme.lower(), p.netloc.lower()


def classify(href, page_url, base_href, origin):
    """(kind, url) of one <a href>. kind: skip, internal, file, query, mixed, alt-host, external."""
    h = re.sub(r"[\t\n\r]", "", (href or "").strip())
    if not h or h.startswith("#") or h.lower().startswith(SKIP_SCHEMES):
        return "skip", None
    try:
        base = urllib.parse.urljoin(page_url, base_href) if base_href else page_url
        p = urllib.parse.urlsplit(ascii_url(urllib.parse.urljoin(base, h)))
    except ValueError:
        return "skip", None
    scheme, netloc = p.scheme.lower(), p.netloc.lower()
    if scheme not in ("http", "https") or not netloc:
        return "skip", None
    url = urllib.parse.urlunsplit((scheme, netloc, p.path or "/", p.query, ""))
    o_scheme, o_host = origin
    if netloc == o_host:
        if scheme != o_scheme:
            return "mixed", url
        if p.query:
            return "query", url
        if FILE_EXT.search(p.path or ""):
            return "file", url
        return "internal", url
    if netloc == sc.alt_host(o_host):
        return "alt-host", url
    return "external", url


def short(items, n=5):
    return sc.short(list(items), n)


# ---------------------------------------------------------------- crawl

class Crawl:
    def __init__(self, origin, max_pages=200, max_seconds=600, include_query=False, fetcher=None, delay=0.0):
        self.delay = delay              # seconds between requests on top of seo_check's two per second
        self.last_req = 0.0
        self.throttled = 0              # how many times the server answered 429 or 503 and we waited
        self.scheme, self.host = origin
        self.origin = origin
        self.base = "%s://%s" % origin
        self.home_key = sc.norm(self.base + "/")
        self.f = fetcher or sc.Fetcher(2 * max_pages + MAX_SITEMAPS + 10, ua=UA)
        self.max_pages = max_pages
        self.max_seconds = max_seconds
        self.include_query = include_query
        self.pages = collections.OrderedDict()
        self.queue = collections.deque()
        self.sources = collections.defaultdict(set)      # target key -> keys of pages that link to it
        self.mixed = collections.defaultdict(set)        # url -> source keys
        self.althost = collections.defaultdict(set)
        self.query = collections.defaultdict(set)
        self.external = 0
        self.robots_resp = None
        self.robots_text = ""
        self.sitemap = collections.OrderedDict()         # key -> loc, same host and scheme
        self.sitemap_foreign = []
        self.sitemap_notes = []
        self.sitemap_files = 0
        self.sitemap_found = False
        self.sitemap_capped = False
        self.fetched = 0
        self.stop_reason = ""
        self.links_complete = False
        self.robots_stop = ""
        self.home_problem = ""
        self.depth = {}
        self.order = {}
        self.t0 = time.monotonic()

    # -- records
    def rec(self, url, via, enqueue=True):
        k = sc.norm(url)
        r = self.pages.get(k)
        if r is None:
            r = {"url": url, "key": k, "status": None, "kind": None, "via": via, "location": "", "error": "",
                 "content_type": "", "title": None, "h1": [], "h1_count": 0, "canonical": None,
                 "canonical_raw": None, "canonicals": 0, "robots": "", "links": 0, "file": via == "file"}
            self.pages[k] = r
            if enqueue:
                self.queue.append(k)
        elif via in ("link", "redirect") and r["via"] in ("canonical", "sitemap"):
            r["via"] = via
        return r

    def path_of(self, url):
        """Short readable form for reports: the path on our host, the full URL elsewhere, %xx decoded."""
        if not url:
            return ""
        try:
            p = urllib.parse.urlsplit(url)
        except ValueError:
            return url
        if p.netloc.lower() == self.host and p.scheme.lower() == self.scheme:
            s = (p.path or "/") + ("?" + p.query if p.query else "")
        else:
            s = url
        try:
            return urllib.parse.unquote(s, errors="strict")
        except UnicodeDecodeError:
            return s

    def allowed(self, url):
        p = urllib.parse.urlsplit(url)
        path = (p.path or "/") + ("?" + p.query if p.query else "")
        return sc.robots_allows(self.robots_text, AGENT, path)

    def off_origin(self, url):
        try:
            p = urllib.parse.urlsplit(url)
        except ValueError:
            return True
        return p.scheme.lower() != self.scheme or p.netloc.lower() != self.host

    # -- network
    def get(self, url, **kw):
        """One request with the crawl delay. On 429 or 503: slow down, wait (Retry-After or a doubling pause)
        and try the URL again, up to RETRIES times."""
        attempt = 0
        while True:
            if self.delay:
                wait = self.delay - (time.monotonic() - self.last_req)
                if wait > 0:
                    time.sleep(wait)
            resp = self.f.get(url, **kw)
            self.last_req = time.monotonic()
            if resp.status not in RETRY_STATUSES or attempt >= RETRIES:
                return resp
            attempt += 1
            pause = retry_after(resp)
            pause = min(BACKOFF * 2 ** (attempt - 1) if pause is None else pause, MAX_PAUSE)
            if self.max_seconds and time.monotonic() + pause - self.t0 > self.max_seconds:
                return resp
            self.throttled += 1
            self.delay = min(max(2 * self.delay, SLOW_FLOOR), MAX_DELAY)
            time.sleep(pause)

    def fetch_robots(self):
        url = self.base + "/robots.txt"
        r = None
        for _ in range(6):  # RFC 9309: follow at least five redirects
            r = self.get(url, accept="text/plain,*/*")
            if r.status in (301, 302, 303, 307, 308) and r.h("location"):
                url = ascii_url(urllib.parse.urljoin(r.url, header_url(r.h("location"))))
                continue
            break
        self.robots_resp = r
        if r.status == 200:
            self.robots_text = page_text(r)
        return r

    def read_sitemaps(self):
        cands = []
        if self.robots_text:
            cands = [ascii_url(s) for s in sc.robots_sitemaps(self.robots_text) if re.match(r"(?i)^https?://", s)]
        if not cands:
            cands = [self.base + "/sitemap.xml"]
        queue, seen = collections.deque(cands), set()
        while queue and self.sitemap_files < MAX_SITEMAPS:
            u = queue.popleft()
            if u in seen:
                continue
            seen.add(u)
            self.sitemap_files += 1
            r = self.get(u, accept="application/xml,text/xml,*/*")
            if r.status != 200:
                self.sitemap_notes.append("%s answers %s" % (self.path_of(u), r.status if r.status > 0 else r.error))
                continue
            try:
                locs, _lms, kids = sc.sitemap_parse(r.body)
            except sc.ET.ParseError as e:
                self.sitemap_notes.append("%s is not valid XML (%s)" % (self.path_of(u), e))
                continue
            self.sitemap_found = True
            queue.extend(ascii_url(k) for k in kids)
            for loc in locs:
                if len(self.sitemap) >= MAX_SITEMAP_URLS:
                    self.sitemap_capped = True
                    break
                loc = ascii_url(loc)
                try:
                    p = urllib.parse.urlsplit(loc)
                except ValueError:
                    self.sitemap_foreign.append(loc)
                    continue
                if p.netloc.lower() == self.host and p.scheme.lower() == self.scheme:
                    self.sitemap.setdefault(sc.norm(loc), loc)
                else:
                    self.sitemap_foreign.append(loc)
        if queue:
            self.sitemap_notes.append("more than %d sitemap files: read the first %d" % (MAX_SITEMAPS, MAX_SITEMAPS))

    def fetch(self, r):
        if r["file"]:
            resp = self.get(r["url"], method="HEAD")
            if resp.status in (403, 405, 501):
                resp = self.get(r["url"], maxbytes=1024)
            return resp, False
        return self.get(r["url"], accept=HTML_ACCEPT), True

    def drain(self):
        """Fetch queued URLs until the queue is empty or a limit stops the crawl. True when the queue is empty."""
        while self.queue:
            if self.fetched >= self.max_pages:
                self.stop_reason = "max-pages"
                return False
            if self.max_seconds and time.monotonic() - self.t0 > self.max_seconds:
                self.stop_reason = "max-seconds"
                return False
            k = self.queue.popleft()
            r = self.pages[k]
            if r["status"] is not None or r["kind"] is not None:
                continue
            if not self.allowed(r["url"]):
                r["kind"] = "blocked"
                continue
            resp, as_page = self.fetch(r)
            if resp.status == -1:
                self.queue.appendleft(k)
                self.stop_reason = "request budget"
                return False
            self.fetched += 1
            self.handle(r, resp, as_page)
            if resp.status == 429:
                self.stop_reason = "rate limited"
                return False
        return True

    def handle(self, r, resp, as_page):
        r["status"] = resp.status
        r["error"] = resp.error
        r["content_type"] = resp.h("content-type").split(";")[0].strip().lower()
        if resp.status == 0:
            r["kind"] = "error"
            return
        if 300 <= resp.status < 400:
            r["kind"] = "redirect"
            raw = header_url(resp.h("location"))
            if raw:
                loc = ascii_url(urllib.parse.urljoin(r["url"], raw))
                r["location"] = loc
                kind, url = classify(loc, r["url"], None, self.origin)
                if kind in ("internal", "file", "query"):
                    self.rec(url, "file" if kind == "file" else "redirect")
            return
        if resp.status == 429:
            r["kind"] = "throttled"
            return
        if resp.status != 200:
            r["kind"] = "error"
            return
        ct = r["content_type"]
        body = page_text(resp) if as_page else ""
        is_html = as_page and ("html" in ct or (not ct and body.lstrip()[:1] == "<"))
        if not is_html:
            r["kind"] = "file"
            return
        r["kind"] = "html"
        info = sc.parse_html(body)
        base = urllib.parse.urljoin(r["url"], info.base) if info.base else r["url"]
        r["title"] = info.title
        r["h1"] = info.h1_texts
        r["h1_count"] = info.h1
        r["robots"] = " ".join((" ".join(info.meta("robots")) + " " + resp.h("x-robots-tag")).lower().split())
        canon = [l.get("href", "").strip() for l in info.links if "canonical" in (l.get("rel") or "").lower().split()]
        canon = [x for x in canon if x]
        r["canonicals"] = len(canon)
        if canon:
            r["canonical_raw"] = canon[0]
            try:
                r["canonical"] = ascii_url(urllib.parse.urljoin(base, canon[0]))
            except ValueError:
                r["canonical"] = canon[0]
        n = 0
        for href, _rel in info.hrefs:
            kind, url = classify(href, r["url"], info.base, self.origin)
            if kind == "query" and self.include_query:
                kind = "internal"
            if kind in ("internal", "file"):
                n += 1
                t = self.rec(url, "file" if kind == "file" else "link")
                if t["key"] != r["key"]:
                    self.sources[t["key"]].add(r["key"])
            elif kind == "query":
                self.query[url].add(r["key"])
            elif kind == "mixed":
                self.mixed[url].add(r["key"])
            elif kind == "alt-host":
                self.althost[url].add(r["key"])
            elif kind == "external":
                self.external += 1
        r["links"] = n
        if r["canonical"]:
            kind, url = classify(r["canonical"], r["url"], None, self.origin)
            if kind in ("internal", "query") and sc.norm(url) != r["key"]:
                self.rec(url, "canonical")

    def run(self):
        """None when the site does not answer at all; else self."""
        robots = self.fetch_robots()
        if robots.status == 0:
            home = self.get(self.base + "/", accept=HTML_ACCEPT)
            if home.status <= 0 or home.status >= 500:
                return None
            self.robots_stop = "robots.txt gives no answer (%s)" % robots.error
            return self
        if robots.status >= 500 or robots.status == 429:
            self.robots_stop = "robots.txt answers %d" % robots.status
            return self
        self.read_sitemaps()
        home = self.rec(self.base + "/", "home")
        self.drain()
        if home["status"] is not None and (home["status"] <= 0 or home["status"] >= 500):
            return None
        if home["kind"] == "blocked":
            self.home_problem = ("robots.txt closes the home page to %s: add a group 'User-agent: %s' with "
                                 "'Allow: /' if you want this crawl" % (AGENT, AGENT))
        elif home["kind"] == "redirect" and (not home["location"] or self.off_origin(home["location"])):
            self.home_problem = ("the home page redirects to %s: pass the canonical host"
                                 % (home["location"] or "nowhere (no Location)"))
        elif home["status"] is not None and 400 <= home["status"] < 500:
            self.home_problem = "the home page answers %d to %s" % (home["status"], UA)
        if self.home_problem:
            self.finish()
            return self
        if not self.stop_reason:
            self.links_complete = True
            for k, loc in self.sitemap.items():
                if k not in self.pages:
                    self.rec(loc, "sitemap")
            self.drain()
        self.finish()
        return self

    def finish(self):
        """Clicks from home over links (cost 1) and redirects (cost 0): 0-1 breadth-first search."""
        out = collections.defaultdict(set)
        for t, srcs in self.sources.items():
            for s in srcs:
                out[s].add((t, 1))
        for k, r in self.pages.items():
            if r["kind"] == "redirect" and r["location"]:
                out[k].add((sc.norm(r["location"]), 0))
        depth = {self.home_key: 0}
        dq = collections.deque([self.home_key])
        while dq:
            k = dq.popleft()
            for t, w in out.get(k, ()):
                d = depth[k] + w
                if t not in depth or d < depth[t]:
                    depth[t] = d
                    if w == 0:
                        dq.appendleft(t)
                    else:
                        dq.append(t)
        self.depth = depth
        self.order = {k: i for i, k in enumerate(self.pages)}


# ---------------------------------------------------------------- checks

def indexable(c, r):
    return (r["kind"] == "html" and r["status"] == 200 and "noindex" not in r["robots"]
            and (not r["canonical"] or sc.norm(r["canonical"]) == r["key"]))


def bad_status(r):
    """An error of the site. 429 is the server slowing our crawl down: the URL is not checked, not broken."""
    s = r["status"]
    return s is not None and (s == 0 or (s >= 400 and s != 429))


def from_list(c, k, n=3):
    srcs = sorted(c.sources.get(k, ()), key=lambda s: c.order.get(s, 0))
    return short([c.path_of(c.pages[s]["url"]) if s in c.pages else s for s in srcs], n)


def check_coverage(c):
    if c.robots_stop:
        return R("crawl-coverage", "FAIL", "%s: a crawler must then treat the whole site as disallowed (RFC 9309 "
                 "for 5xx and no answer; Google treats 429 the same), so nothing was crawled; fix robots.txt first"
                 % c.robots_stop)
    if c.home_problem:
        return R("crawl-coverage", "FAIL", c.home_problem + "; nothing else was crawled")
    kinds = collections.Counter(r["kind"] for r in c.pages.values())
    unfetched = sum(1 for r in c.pages.values() if r["status"] is None and r["kind"] is None)
    det = ("%d URLs fetched: %d pages, %d files, %d redirects, %d errors; %d closed by robots.txt; sitemap: %d URLs "
           "in %d files" % (c.fetched, kinds["html"], kinds["file"], kinds["redirect"], kinds["error"],
                            kinds["blocked"], len(c.sitemap), c.sitemap_files))
    status = "INFO"
    if c.stop_reason == "max-pages":
        det += "; stopped at --max-pages %d with %d URLs not fetched: raise --max-pages for a full crawl" % (
            c.max_pages, unfetched)
    elif c.stop_reason == "max-seconds":
        det += "; stopped at --max-seconds %d with %d URLs not fetched" % (c.max_seconds, unfetched)
    elif c.stop_reason == "rate limited":
        status = "WARN"
        det += ("; stopped: the server still answered 429 after %d retries, %d URLs not fetched: run the crawl "
                "later or with --delay 2" % (RETRIES, unfetched))
    elif c.stop_reason:
        det += "; stopped: %s" % c.stop_reason
    else:
        det += "; complete"
    if c.throttled:
        det += "; the server asked to slow down %d times (429 or 503), requests slowed to one per %.1f s" % (
            c.throttled, c.delay)
    if c.sitemap_capped:
        det += "; sitemap read up to %d URLs" % MAX_SITEMAP_URLS
    return R("crawl-coverage", status, det)


def check_broken(c):
    fail, warn = [], []
    links = 0
    for k, r in c.pages.items():
        srcs = c.sources.get(k)
        if not srcs or r["status"] is None or not (400 <= r["status"] < 500) or r["status"] == 429:
            continue
        links += len(srcs)
        item = "%s (%d) from %s" % (c.path_of(r["url"]), r["status"], from_list(c, k))
        (warn if r["status"] in (401, 403) else fail).append(item)
    if fail:
        return RI("broken-links", "FAIL", "%d broken URLs, %d linking pages: %s" % (
            len(fail) + len(warn), links, short(fail + warn)), fail + warn)
    if warn:
        return RI("broken-links", "WARN", "links to pages that need a login or are forbidden: " + short(warn), warn)
    return R("broken-links", "OK", "no internal link leads to a 4xx page")


def check_server(c):
    fail, warn = [], []
    for k, r in c.pages.items():
        s = r["status"]
        if s is None:
            continue
        if s >= 500:
            fail.append("%s (%d)" % (c.path_of(r["url"]), s))
        elif s == 429:
            warn.append("%s (429: rate limited)" % c.path_of(r["url"]))
        elif s == 0:
            warn.append("%s (no answer: %s)" % (c.path_of(r["url"]), r["error"]))
    if fail:
        return RI("server-errors", "FAIL", "%d URLs answered 5xx: %s" % (len(fail), short(fail + warn)), fail + warn)
    if warn:
        return RI("server-errors", "WARN", short(warn), warn)
    return R("server-errors", "OK", "no 5xx, 429 or unanswered request")


def check_redirect_links(c):
    items, links = [], 0
    for k, r in c.pages.items():
        srcs = c.sources.get(k)
        if r["kind"] != "redirect" or not srcs:
            continue
        links += len(srcs)
        items.append("%s -> %s (%d) from %s" % (c.path_of(r["url"]), c.path_of(r["location"]) or "-",
                                                r["status"], from_list(c, k)))
    if items:
        return RI("redirect-links", "WARN", "%d linked URLs redirect, %d links: link to the final URL: %s"
                  % (len(items), links, short(items)), items)
    return R("redirect-links", "OK", "no internal link points to a redirect")


def chain_of(c, r):
    """(hops, end_record_or_None, problem): problem in '', 'loop', 'no-location', 'error'."""
    hops, seen, cur = 0, {r["key"]}, r
    while cur["kind"] == "redirect":
        if not cur["location"]:
            return hops, cur, "no-location"
        hops += 1
        nk = sc.norm(cur["location"])
        if nk in seen:
            return hops, None, "loop"
        seen.add(nk)
        nxt = c.pages.get(nk)
        if nxt is None or nxt["status"] is None:
            return hops, None, ""
        cur = nxt
    return hops, cur, "error" if bad_status(cur) else ""


def check_chains(c):
    fail, warn = [], []
    for k, r in c.pages.items():
        if r["kind"] != "redirect":
            continue
        if not (c.sources.get(k) or k in c.sitemap or k == c.home_key):
            continue
        hops, end, problem = chain_of(c, r)
        p = c.path_of(r["url"])
        if problem == "loop":
            fail.append("%s: redirect loop" % p)
        elif problem == "no-location":
            fail.append("%s: %d without Location" % (c.path_of(end["url"]), end["status"]))
        elif problem == "error":
            fail.append("%s: ends in %s at %s" % (p, end["status"] or end["error"], c.path_of(end["url"])))
        elif hops >= 2:
            warn.append("%s: %d redirects to %s" % (p, hops, c.path_of(end["url"]) if end else "a URL not fetched"))
    if fail:
        return RI("redirect-chains", "FAIL", short(fail + warn), fail + warn)
    if warn:
        return RI("redirect-chains", "WARN", "redirect straight to the final URL: " + short(warn), warn)
    return R("redirect-chains", "OK", "no chain, loop or broken redirect")


def check_sitemap_errors(c):
    if not c.sitemap_found:
        note = "; ".join(c.sitemap_notes) or "no sitemap"
        return R("sitemap-errors", "WARN", "no readable sitemap (%s): seo_check.py shows the details" % note)
    fail, warn, ok, unchecked = [], [], 0, 0
    for k, loc in c.sitemap.items():
        r = c.pages.get(k)
        p = c.path_of(loc)
        if r is not None and r["kind"] == "blocked":
            warn.append("%s is closed by robots.txt" % p)
            continue
        if r is None or r["status"] is None or r["kind"] == "throttled":
            unchecked += 1
            continue
        if r["status"] != 200:
            if r["kind"] == "redirect":
                fail.append("%s answers %d -> %s" % (p, r["status"], c.path_of(r["location"]) or "-"))
            else:
                fail.append("%s answers %s" % (p, r["status"] or r["error"]))
        elif r["kind"] == "html" and "noindex" in r["robots"]:
            fail.append("%s has noindex" % p)
        elif r["kind"] == "html" and r["canonical"] and sc.norm(r["canonical"]) != k:
            fail.append("%s: canonical points to %s" % (p, c.path_of(r["canonical"])))
        else:
            ok += 1
    if c.sitemap_foreign:
        warn.append("%d URLs on another host or scheme, e.g. %s" % (len(c.sitemap_foreign), c.sitemap_foreign[0]))
    warn += c.sitemap_notes
    tail = "; %d sitemap URLs not checked (crawl limit or 429)" % unchecked if unchecked else ""
    if fail:
        det = "a sitemap lists only canonical indexable 200 URLs: %d errors: %s" % (len(fail), short(fail))
        if warn:
            det += "; %d warnings: %s" % (len(warn), short(warn))
        return RI("sitemap-errors", "FAIL", det + tail, fail + warn)
    if warn:
        return RI("sitemap-errors", "WARN", short(warn) + tail, warn)
    if not ok:
        return R("sitemap-errors", "SKIP", "no sitemap URL was checked" + tail)
    return R("sitemap-errors", "OK", "%d sitemap URLs: 200, indexable, self-canonical%s" % (ok, tail))


def check_not_in_sitemap(c):
    if not c.sitemap_found:
        return R("not-in-sitemap", "SKIP", "no readable sitemap to compare with")
    miss = [c.path_of(r["url"]) for k, r in c.pages.items()
            if r["via"] in ("home", "link", "redirect") and indexable(c, r) and k not in c.sitemap]
    if miss:
        return RI("not-in-sitemap", "WARN", "%d indexable pages that links reach are not in the sitemap: %s"
                  % (len(miss), short(miss)), miss)
    return R("not-in-sitemap", "OK", "every indexable page the links reach is in the sitemap")


def check_orphans(c):
    if not c.sitemap_found:
        return R("orphans", "SKIP", "no readable sitemap")
    if not c.links_complete:
        return R("orphans", "SKIP", "the link crawl stopped (%s) before every link was followed: raise --max-pages"
                 % (c.stop_reason or "limit"))
    orph = []
    for k, loc in c.sitemap.items():
        if k in c.depth:
            continue
        r = c.pages.get(k)
        if r is not None and (r["kind"] == "blocked" or (r["status"] is not None and r["status"] != 200
                                                         and r["kind"] != "throttled")):
            continue  # a sitemap error, reported there
        orph.append(c.path_of(loc))
    if orph:
        return RI("orphans", "WARN", "%d sitemap URLs that no link from the home page reaches: %s"
                  % (len(orph), short(orph)), orph)
    return R("orphans", "OK", "links from the home page reach every sitemap URL")


def check_canonical(c):
    warn, info = [], []
    missing = other = 0
    for k, r in c.pages.items():
        if r["kind"] != "html" or r["status"] != 200:
            continue
        p = c.path_of(r["url"])
        if r["canonicals"] > 1:
            warn.append("%s: %d canonical tags" % (p, r["canonicals"]))
        if not r["canonical"]:
            missing += 1
            continue
        if not re.match(r"(?i)^https?://", r["canonical_raw"] or ""):
            info.append("%s: relative canonical %s" % (p, r["canonical_raw"]))
        tk = sc.norm(r["canonical"])
        if tk == k:
            continue
        try:
            tnet = urllib.parse.urlsplit(r["canonical"]).netloc.lower()
        except ValueError:
            tnet = ""
        if tnet != c.host:
            warn.append("%s: canonical to another host %s" % (p, r["canonical"]))
            continue
        other += 1
        t = c.pages.get(tk)
        if t is None or t["status"] is None or t["kind"] == "throttled":
            continue
        if t["kind"] == "redirect":
            warn.append("%s: canonical %s redirects (%d)" % (p, c.path_of(t["url"]), t["status"]))
        elif t["status"] != 200:
            warn.append("%s: canonical %s answers %s" % (p, c.path_of(t["url"]), t["status"] or t["error"]))
        elif "noindex" in t["robots"]:
            warn.append("%s: canonical %s has noindex" % (p, c.path_of(t["url"])))
    notes = []
    if other:
        notes.append("%d pages name another URL as canonical" % other)
    if missing:
        notes.append("%d pages have no canonical" % missing)
    if warn:
        return RI("canonical", "WARN", short(warn + info) + ("; " + "; ".join(notes) if notes else ""), warn + info)
    if info or notes:
        return RI("canonical", "INFO", "; ".join(([short(info)] if info else []) + notes), info)
    return R("canonical", "OK", "every page has one absolute self-canonical")


def check_noindex(c):
    noi = [c.path_of(r["url"]) for r in c.pages.values() if r["kind"] == "html" and "noindex" in r["robots"]]
    nof = sum(1 for r in c.pages.values() if r["kind"] == "html" and "nofollow" in r["robots"])
    tail = "; nofollow on %d pages" % nof if nof else ""
    if noi:
        return RI("noindex", "INFO", "%d pages have noindex: %s%s" % (len(noi), short(noi), tail), noi)
    return R("noindex", "INFO" if nof else "OK", "no page has noindex" + tail)


def _dups(seen):
    return ["%s on %s" % (v[0], ", ".join(v[1])) for v in seen.values() if len(v[1]) > 1], \
           ["%s on %s" % (v[0], short(v[1], 3)) for v in seen.values() if len(v[1]) > 1]


def check_titles(c):
    bad, seen = [], collections.OrderedDict()
    for r in c.pages.values():
        if not indexable(c, r):
            continue
        t = " ".join((r["title"] or "").split())
        if not t:
            bad.append(c.path_of(r["url"]))
            continue
        seen.setdefault(t.lower(), (t, []))[1].append(c.path_of(r["url"]))
    dup_full, dup = _dups(seen)
    items = ["%s: no title" % p for p in bad] + ["same title: " + d for d in dup_full]
    if bad:
        return RI("titles", "FAIL", "%d pages without a title: %s%s" % (
            len(bad), short(bad), "; same title: " + short(dup, 3) if dup else ""), items)
    if dup:
        return RI("titles", "WARN", "%d titles are used on several pages: %s" % (len(dup), short(dup, 3)), items)
    return R("titles", "OK", "unique titles on %d indexable pages" % sum(len(v[1]) for v in seen.values()))


def check_h1(c):
    none, empty, many, seen = [], [], [], collections.OrderedDict()
    for r in c.pages.values():
        if not indexable(c, r):
            continue
        p = c.path_of(r["url"])
        if r["h1_count"] == 0:
            none.append(p)
            continue
        texts = [t for t in r["h1"] if t]
        if not texts:
            empty.append(p)
            continue
        if r["h1_count"] > 1:
            many.append("%s (%d)" % (p, r["h1_count"]))
        seen.setdefault(texts[0].lower(), (texts[0], []))[1].append(p)
    dup_full, dup = _dups(seen)
    items = (["%s: no h1" % p for p in none] + ["%s: empty h1" % p for p in empty]
             + ["same h1: " + d for d in dup_full] + ["%s h1 tags" % m for m in many])
    warn = (["no h1: " + short(none)] if none else []) + (["empty h1: " + short(empty)] if empty else []) + \
           (["same h1: " + short(dup, 3)] if dup else [])
    if warn:
        return RI("h1", "WARN", "; ".join(warn) + ("; several h1: " + short(many) if many else ""), items)
    if many:
        return RI("h1", "INFO", "several h1: " + short(many), items)
    return R("h1", "OK", "one distinct h1 on each of %d indexable pages" % sum(len(v[1]) for v in seen.values()))


def check_mixed(c):
    items = ["%s from %s" % (u, short(sorted(c.path_of(c.pages[s]["url"]) for s in srcs if s in c.pages), 2))
             for u, srcs in list(c.mixed.items()) + list(c.althost.items())]
    if items:
        return RI("mixed-host-links", "WARN", "%d links go to the other scheme or www form of the host (each costs "
                  "a redirect): %s" % (len(items), short(items, 3)), items)
    return R("mixed-host-links", "OK", "internal links use %s://%s only" % (c.scheme, c.host))


def check_blocked(c):
    blocked = [c.path_of(r["url"]) for r in c.pages.values() if r["kind"] == "blocked"]
    if blocked:
        return RI("robots-blocked", "INFO", "%d internal URLs are closed by robots.txt (not crawled): %s"
                  % (len(blocked), short(blocked)), blocked)
    return R("robots-blocked", "OK", "robots.txt closes none of the URLs the crawl met")


def check_query(c):
    if c.include_query:
        n = sum(1 for r in c.pages.values() if "?" in r["url"] and r["status"] is not None)
        return R("query-urls", "INFO", "--include-query: %d URLs with a query string crawled" % n)
    if c.query:
        q = sorted(c.path_of(u) for u in c.query)
        return RI("query-urls", "INFO", "%d linked URLs with a query string were not crawled (--include-query "
                  "crawls them): %s" % (len(q), short(q)), q)
    return R("query-urls", "OK", "no internal link carries a query string")


def check_depth(c):
    d = {k: v for k, v in c.depth.items() if k in c.pages and c.pages[k]["status"] is not None}
    if not d:
        return R("depth", "SKIP", "no page reached from the home page")
    per = collections.Counter(d.values())
    deep = [c.path_of(c.pages[k]["url"]) for k, v in sorted(d.items(), key=lambda kv: -kv[1])
            if v > DEEP and indexable(c, c.pages[k])]
    det = "deepest page: %d clicks from the home page; pages per depth: %s" % (
        max(per), ", ".join("%d: %d" % (k, per[k]) for k in sorted(per)))
    if deep:
        det += "; %d indexable pages deeper than %d clicks: %s" % (len(deep), DEEP, short(deep))
    if not c.links_complete:
        det += " (partial crawl)"
    return RI("depth", "INFO", det, deep)


def check_diff(c, old, old_name):
    try:
        old_pages = {p["key"]: p for p in old.get("pages", []) if isinstance(p, dict) and p.get("key")}
    except Exception as e:
        return R("crawl-diff", "SKIP", "cannot read %s: %s" % (old_name, e))
    if not old_pages:
        return R("crawl-diff", "SKIP", "%s has no pages" % old_name)
    now = {k: r for k, r in c.pages.items() if r["status"] is not None}

    def bad(p):
        s = p.get("status")
        return s is not None and (s == 0 or (s >= 400 and s != 429))
    new_err = [c.path_of(r["url"]) for k, r in now.items() if bad(r) and not (k in old_pages and bad(old_pages[k]))]
    lost = [c.path_of(r["url"]) for k, r in now.items()
            if k in old_pages and old_pages[k].get("status") == 200 and r["status"] not in (200, 429)]
    gone = [c.path_of(p.get("url", k)) for k, p in old_pages.items() if p.get("status") == 200 and k not in c.pages]
    new = [k for k, r in now.items() if k not in old_pages and r["status"] == 200]
    titles = [c.path_of(r["url"]) for k, r in now.items() if k in old_pages and r["kind"] == "html"
              and old_pages[k].get("kind") == "html" and (old_pages[k].get("title") or "") != (r["title"] or "")]
    det = "since %s (%s): new errors %d, lost (were 200) %d, not met this time %d, new pages %d, changed titles %d" % (
        old_name, old.get("date", "?"), len(new_err), len(lost), len(gone), len(new), len(titles))
    extra, items = [], []
    for label, lst in (("new errors", new_err), ("lost", lost), ("titles", titles), ("not met", gone)):
        if lst:
            extra.append("%s: %s" % (label, short(lst)))
            items += ["%s: %s" % (label, x) for x in lst]
    st = "WARN" if new_err or lost else "INFO"
    return RI("crawl-diff", st, det + ("; " + "; ".join(extra) if extra else ""), items)


def checks(c, old=None, old_name=""):
    res = [check_coverage(c)]
    if c.robots_stop or c.home_problem:
        return res
    res += [check_broken(c), check_server(c), check_redirect_links(c), check_chains(c), check_sitemap_errors(c),
            check_not_in_sitemap(c), check_orphans(c), check_canonical(c), check_noindex(c), check_titles(c),
            check_h1(c), check_mixed(c), check_blocked(c), check_query(c), check_depth(c)]
    if old is not None:
        res.append(check_diff(c, old, old_name))
    return res


# ---------------------------------------------------------------- output

def page_rows(c):
    rows = []
    for k, r in c.pages.items():
        rows.append({"url": r["url"], "key": k, "status": r["status"], "kind": r["kind"], "via": r["via"],
                     "depth": c.depth.get(k), "inlinks": len(c.sources.get(k, ())), "in_sitemap": k in c.sitemap,
                     "indexable": indexable(c, r), "canonical": r["canonical"], "location": r["location"],
                     "title": r["title"], "h1": r["h1"], "robots": r["robots"], "error": r["error"]})
    return rows


def link_rows(c, limit=MAX_ITEMS):
    rows = []
    for k, r in c.pages.items():
        srcs = c.sources.get(k)
        if not srcs or r["status"] is None:
            continue
        if bad_status(r) or r["kind"] == "redirect":
            for s in sorted(srcs, key=lambda s: c.order.get(s, 0)):
                rows.append((c.path_of(c.pages[s]["url"]) if s in c.pages else s, c.path_of(r["url"]),
                             str(r["status"] or r["error"]), c.path_of(r["location"])))
    return rows[:limit], len(rows)


def _md(s):
    return str(s).replace("|", "\\|")


def to_markdown(c, res):
    cnt = {k: sum(1 for r in res if r["status"] == k) for k in STATUSES}
    lines = ["# seo_crawl: %s" % c.host, "",
             "OK %(OK)d, WARN %(WARN)d, FAIL %(FAIL)d, INFO %(INFO)d, SKIP %(SKIP)d. " % cnt
             + "Requests: %d. URLs fetched: %d." % (c.f.n, c.fetched), "",
             "| Check | Status | Detail |", "|---|---|---|"]
    order = {"FAIL": 0, "WARN": 1, "INFO": 2, "OK": 3, "SKIP": 4}
    ranked = sorted(res, key=lambda r: (order.get(r["status"], 9), r["id"]))
    for r in ranked:
        lines.append("| %s | %s | %s |" % (r["id"], r["status"], _md(r["detail"])))
    rows, total = link_rows(c)
    if rows:
        lines += ["", "## Links to fix (%d)" % total, "", "| On page | Link | Status | Goes to |", "|---|---|---|---|"]
        for row in rows:
            lines.append("| %s |" % " | ".join(_md(x) for x in row))
        if total > len(rows):
            lines += ["", "First %d of %d; the full list is in the JSON report." % (len(rows), total)]
    detailed = [r for r in ranked if r.get("items") and r["status"] in ("FAIL", "WARN")]
    if detailed:
        lines += ["", "## Details"]
        for r in detailed:
            lines += ["", "### %s (%s)" % (r["id"], r["status"]), ""]
            lines += ["- " + _md(x) for x in r["items"][:MAX_ITEMS]]
            if len(r["items"]) > MAX_ITEMS:
                lines.append("- and %d more in the JSON report" % (len(r["items"]) - MAX_ITEMS))
    return "\n".join(lines) + "\n"


def write_csv(path, rows):
    cols = ["url", "status", "kind", "via", "depth", "inlinks", "in_sitemap", "indexable", "canonical", "location",
            "title", "h1", "robots", "error"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow(["; ".join(r[c]) if isinstance(r[c], list) else ("" if r[c] is None else r[c]) for c in cols])


# ---------------------------------------------------------------- selftest

def _serve(routes):
    """Serve routes {path: (status, headers, body)} on 127.0.0.1. In headers and bodies {o} becomes the origin,
    {x} the origin with the other scheme, {w} the origin with www., {p} the port. A body (text, codec) is sent
    in that codec. srv.log keeps (method, path, user agent) of every request."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.answer(True)

        def do_HEAD(self):
            self.answer(False)

        def answer(self, with_body):
            port = self.server.server_address[1]
            subs = {"{o}": "http://127.0.0.1:%d" % port, "{x}": "https://127.0.0.1:%d" % port,
                    "{w}": "http://www.127.0.0.1:%d" % port, "{p}": str(port)}

            def sub(s):
                for k, v in subs.items():
                    s = s.replace(k, v)
                return s
            self.server.log.append((self.command, self.path, self.headers.get("User-Agent", "")))
            route = routes.get(self.path, (404, {"Content-Type": "text/html"}, "<title>404</title>"))
            status, headers, body = route() if callable(route) else route
            text, codec = body if isinstance(body, tuple) else (body, "utf-8")
            data = sub(text).encode(codec)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, sub(v))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if with_body:
                self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    srv.log = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _pg(title, h1="", links=(), canon="", extra_head="", body=""):
    a = "".join('<a href="%s">l</a>' % x for x in links)
    c = '<link rel="canonical" href="%s">' % canon if canon else ""
    h = "<h1>%s</h1>" % h1 if h1 else ""
    return ("<!doctype html><html lang=\"en\"><head>%s<title>%s</title>%s</head><body>%s%s%s</body></html>"
            % (extra_head, title, c, h, a, body))


HTML = {"Content-Type": "text/html; charset=utf-8"}
TEXT = {"Content-Type": "text/plain"}


def _page(title, h1, links=(), canon=None, path="", extra_head="", headers=None, body=""):
    hd = dict(HTML)
    hd.update(headers or {})
    return 200, hd, _pg(title, h1, links, "{o}" + (canon if canon is not None else path), extra_head, body)


def planted_site():
    sm = "".join("<url><loc>%s</loc></url>" % u for u in (
        "{o}/", "{o}/a", "{o}/b", "{o}/c", "{o}/gone", "{o}/moved", "{o}/noidx", "{o}/canon-other", "{o}/private/x",
        "https://other.test/z", "{o}/new", "{o}/notitle", "{o}/noh1", "{o}/twocanon", "{o}/canon404",
        "{o}/hdr-noindex", "{o}/deep1", "{o}/deep2", "{o}/deep3", "{o}/deep4", "{o}/deep5", "{o}/doc.pdf",
        "{o}/loop1", "{o}/chain1", "{o}/old", "{o}/err"))  # /chain2 and /loop2 only a redirect reaches
    home_links = ["/a", "/b", "/missing", "/old", "/chain1", "/loop1", "/private/y", "/search?q=x", "{x}/x", "{w}/w",
                  "/doc.pdf", "/broken.pdf", "/err", "/notinsm", "mailto:x@example.org", "#top", "javascript:void(0)",
                  "https://example.org/", "/deep1"]
    return {
        "/robots.txt": (200, TEXT, "User-agent: *\nDisallow: /private/\nSitemap: {o}/sitemap.xml\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, "<urlset>%s</urlset>" % sm),
        "/": _page("Home", "Home", home_links, path="/"),
        "/a": _page("Page A", "A", ["/", "/b", "/canon-other", "/noidx"], path="/a"),
        "/b": _page("Page A", "A", ["/notitle", "/noh1", "/twocanon", "/canon404", "/hdr-noindex", "/new"], path="/b"),
        "/c": _page("Orphan C", "C", ["/"], path="/c"),
        "/gone": (404, HTML, "<title>gone</title>"),
        "/moved": (301, {"Location": "{o}/a"}, ""),
        "/noidx": _page("No index", "Noidx", [], path="/noidx", extra_head='<meta name="robots" content="noindex">'),
        "/canon-other": _page("Canon other", "Canon other", [], canon="/a"),
        "/old": (301, {"Location": "{o}/new"}, ""),
        "/new": _page("New", "New", [], path="/new"),
        "/chain1": (301, {"Location": "{o}/chain2"}, ""),
        "/chain2": (301, {"Location": "{o}/a"}, ""),
        "/loop1": (301, {"Location": "{o}/loop2"}, ""),
        "/loop2": (302, {"Location": "{o}/loop1"}, ""),
        "/doc.pdf": (200, {"Content-Type": "application/pdf"}, "%PDF-1.4"),
        "/err": (500, HTML, "<title>error</title>"),
        "/notinsm": _page("Not in sitemap", "Not in sitemap", [], path="/notinsm"),
        "/notitle": _page("", "No title page", [], path="/notitle"),
        "/noh1": _page("No h1 page", "", [], path="/noh1"),
        "/twocanon": _page("Two canonicals", "Two canonicals", [], path="/twocanon",
                           extra_head='<link rel="canonical" href="{o}/twocanon">'),
        "/canon404": _page("Canonical to 404", "Canonical to 404", [], canon="/missing"),
        "/hdr-noindex": _page("Header noindex", "Header noindex", [], path="/hdr-noindex",
                              headers={"X-Robots-Tag": "noindex"}),
        "/deep1": _page("Deep 1", "Deep 1", ["/deep2"], path="/deep1"),
        "/deep2": _page("Deep 2", "Deep 2", ["/deep3"], path="/deep2"),
        "/deep3": _page("Deep 3", "Deep 3", ["/deep4"], path="/deep3"),
        "/deep4": _page("Deep 4", "Deep 4", ["/deep5"], path="/deep4"),
        "/deep5": _page("Deep 5", "Deep 5", [], path="/deep5"),
    }


CYR = "/\u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f"   # a Cyrillic path, as a link writes it
HELMET = "\u0428\u043b\u0435\u043c"                                       # two different 4-letter words that
WHEEL = "\u0420\u0443\u043b\u044c"                                        # read alike if decoded as UTF-8


def clean_site():
    enc = urllib.parse.quote(CYR)
    sm = "".join("<url><loc>{o}%s</loc></url>" % p for p in ("/", "/p1", "/p2", "/p3", enc.lower(), "/cp-meta",
                                                               "/cp-bare"))
    plain = {"Content-Type": "text/html"}
    return {
        "/robots.txt": (200, TEXT, "User-agent: *\nAllow: /\nSitemap: {o}/sitemap.xml\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, "<urlset>%s</urlset>" % sm),
        "/": _page("Clean home", "Clean home", ["/p1", "/p2", "/p3", CYR, "/cp-meta", "/cp-bare",
                                                "https://example.org/"], path="/"),
        "/p1": _page("Clean one", "Clean one", ["/", "/p2"], path="/p1"),
        "/p2": _page("Clean two", "Clean two", ["/", "/p3"], path="/p2"),
        "/p3": _page("Clean three", "Clean three", ["/"], path="/p3"),
        enc: _page("\u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f", "Manual", ["/"], path=CYR),
        "/cp-meta": (200, plain, (_pg(HELMET, HELMET, ["/"], "{o}/cp-meta", '<meta charset="windows-1251">'), "cp1251")),
        "/cp-bare": (200, plain, (_pg(WHEEL, WHEEL, ["/"], "{o}/cp-bare"), "cp1251")),
    }


def _origin(srv):
    return ("http", "127.0.0.1:%d" % srv.server_address[1])


def _crawl(srv, **kw):
    c = Crawl(_origin(srv), **kw).run()
    return c, ({r["id"]: r for r in checks(c)} if c else {})


def selftest():
    global BACKOFF, SLOW_FLOOR
    saved = (sc.MIN_INTERVAL, BACKOFF, SLOW_FLOOR)
    sc.MIN_INTERVAL, BACKOFF, SLOW_FLOOR = 0.0, 0.01, 0.0
    fails = []

    def want(name, res, cid, statuses, needle=None):
        r = res.get(cid)
        hay = (r["detail"] + "\n" + "\n".join(r.get("items", []))) if r else ""
        ok = r is not None and r["status"] in statuses and (needle is None or needle in hay)
        print("  %-4s %-16s %-46s -> %s" % ("ok" if ok else "MISS", cid, name, r["status"] if r else "none"))
        if not ok:
            fails.append("%s: %s gave %s, expected %s%s" % (name, cid, r and r["status"], "/".join(statuses),
                                                           " with %r" % needle if needle else ""))

    def same(name, got, exp):
        ok = got == exp
        print("  %-4s %-16s %s" % ("ok" if ok else "MISS", "exact", name))
        if not ok:
            fails.append("%s: got %r, expected %r" % (name, got, exp))

    srvs = []
    try:
        print("Planted defects (each must be reported under its check):")
        s = _serve(planted_site())
        srvs.append(s)
        port = s.server_address[1]
        c, res = _crawl(s, max_pages=200)
        want("link to a 404 page", res, "broken-links", ("FAIL",), "/missing (404) from /")
        want("link to a 404 file", res, "broken-links", ("FAIL",), "/broken.pdf (404)")
        want("page answers 500", res, "server-errors", ("FAIL",), "/err (500)")
        want("link to a 301", res, "redirect-links", ("WARN",), "/old -> /new (301)")
        want("two redirects in a row", res, "redirect-chains", ("FAIL",), "/chain1: 2 redirects")
        want("redirect loop", res, "redirect-chains", ("FAIL",), "/loop1: redirect loop")
        want("sitemap URL 404", res, "sitemap-errors", ("FAIL",), "/gone answers 404")
        want("sitemap URL redirects", res, "sitemap-errors", ("FAIL",), "/moved answers 301")
        want("sitemap URL with noindex", res, "sitemap-errors", ("FAIL",), "/noidx has noindex")
        want("sitemap URL with noindex header", res, "sitemap-errors", ("FAIL",), "/hdr-noindex has noindex")
        want("sitemap URL canonical elsewhere", res, "sitemap-errors", ("FAIL",), "/canon-other: canonical points to /a")
        want("sitemap URL closed by robots", res, "sitemap-errors", ("FAIL",), "/private/x is closed by robots.txt")
        want("sitemap URL on another host", res, "sitemap-errors", ("FAIL",), "1 URLs on another host")
        want("page missing from the sitemap", res, "not-in-sitemap", ("WARN",), "/notinsm")
        want("orphan sitemap page", res, "orphans", ("WARN",), "/c")
        want("two canonical tags", res, "canonical", ("WARN",), "/twocanon: 2 canonical tags")
        want("canonical to a 404", res, "canonical", ("WARN",), "/canon404: canonical /missing answers 404")
        want("noindex in a meta tag", res, "noindex", ("INFO",), "/noidx")
        want("noindex in the header", res, "noindex", ("INFO",), "/hdr-noindex")
        want("empty title", res, "titles", ("FAIL",), "/notitle")
        want("same title on two pages", res, "titles", ("FAIL",), "Page A on /a, /b")
        want("page without h1", res, "h1", ("WARN",), "no h1: /noh1")
        want("same h1 on two pages", res, "h1", ("WARN",), "A on /a, /b")
        want("link to the other scheme", res, "mixed-host-links", ("WARN",), "https://127.0.0.1:%d/x" % port)
        want("link to the www form", res, "mixed-host-links", ("WARN",), "http://www.127.0.0.1:%d/w" % port)
        want("link closed by robots", res, "robots-blocked", ("INFO",), "/private/y")
        want("link with a query string", res, "query-urls", ("INFO",), "/search?q=x")
        want("page five clicks deep", res, "depth", ("INFO",), "/deep5")
        want("complete crawl", res, "crawl-coverage", ("INFO",), "complete")
        same("orphans are exactly /c", res["orphans"].get("items"), ["/c"])
        same("not in the sitemap is exactly /notinsm", res["not-in-sitemap"].get("items"), ["/notinsm"])
        same("other-scheme links", sorted(c.mixed), ["https://127.0.0.1:%d/x" % port])
        same("www links", sorted(c.althost), ["http://www.127.0.0.1:%d/w" % port])
        queued = sorted(r["url"] for r in c.pages.values() if "example.org" in r["url"] or "mailto" in r["url"]
                        or "/search" in r["url"])
        same("external, mailto and query links are not queued", queued, [])
        same("a URL only a redirect reaches is crawled",
             [(c.pages.get(sc.norm(c.base + p), {}).get("via"), c.pages.get(sc.norm(c.base + p), {}).get("status"))
              for p in ("/chain2", "/loop2")], [("redirect", 301), ("redirect", 302)])
        same("the pdf is checked as a file", c.pages[sc.norm(c.base + "/doc.pdf")]["kind"], "file")
        same("the pdf is checked with HEAD", sorted({m for m, p, _ in s.log if p == "/doc.pdf"}), ["HEAD"])
        same("robots.txt is obeyed: /private/ never requested", [p for _, p, _ in s.log if p.startswith("/private")], [])
        same("every request carries the crawler User-Agent", sorted({u.split("/")[0] for _, _, u in s.log}),
             [AGENT])
        md = to_markdown(c, checks(c))
        same("Markdown: links table and details", ("## Links to fix" in md, "| / | /missing | 404 |" in md,
                                                    "### sitemap-errors (FAIL)" in md), (True, True, True))

        print("Limits and stops:")
        c2, res2 = _crawl(s, max_pages=3)
        want("stops at --max-pages", res2, "crawl-coverage", ("INFO",), "stopped at --max-pages 3")
        want("no orphan verdict on a partial crawl", res2, "orphans", ("SKIP",))
        same("--max-pages 3 fetches 3 URLs", c2.fetched, 3)
        old = {"date": "2026-01-01", "pages": [dict(p, status=200) if p["key"].endswith("/err") else p
                                                for p in page_rows(c)]}
        c3 = Crawl(_origin(s)).run()
        res3 = {r["id"]: r for r in checks(c3, old, "old.json")}
        want("crawl-diff: a page that broke since", res3, "crawl-diff", ("WARN",), "lost: /err")

        s503 = _serve({"/robots.txt": (503, TEXT, "busy"), "/": _page("H", "H", [], path="/")})
        srvs.append(s503)
        c4, res4 = _crawl(s503)
        want("robots.txt answers 503: stop", res4, "crawl-coverage", ("FAIL",), "robots.txt answers 503")
        same("robots.txt 503: tried %d times, nothing else requested" % (RETRIES + 1),
             [p for _, p, _ in s503.log], ["/robots.txt"] * (RETRIES + 1))

        sblk = _serve({"/robots.txt": (200, TEXT, "User-agent: *\nDisallow: /\n"), "/": _page("H", "H", [], path="/")})
        srvs.append(sblk)
        _c, res6 = _crawl(sblk)
        want("robots.txt closes the home page", res6, "crawl-coverage", ("FAIL",), "robots.txt closes the home page")
        sown = _serve({"/robots.txt": (200, TEXT, "User-agent: *\nDisallow: /\n\nUser-agent: %s\nAllow: /\n" % AGENT),
                       "/": _page("H", "H", [], path="/")})
        srvs.append(sown)
        c7, res7 = _crawl(sown)
        same("a group for seo-ops-crawl opens the site", c7.pages[c7.home_key]["status"], 200)
        soff = _serve({"/robots.txt": (200, TEXT, "User-agent: *\nAllow: /\n"),
                       "/": (301, {"Location": "http://localhost:{p}/"}, "")})
        srvs.append(soff)
        _c, res8 = _crawl(soff)
        want("home page redirects to another host", res8, "crawl-coverage", ("FAIL",), "redirects to http://localhost:")
        s403 = _serve({"/robots.txt": (200, TEXT, ""), "/": (403, HTML, "<title>no bots</title>")})
        srvs.append(s403)
        _c, res9 = _crawl(s403)
        want("home page answers 403", res9, "crawl-coverage", ("FAIL",), "the home page answers 403")

        print("A server that asks to slow down (429, 503):")
        hits = collections.Counter()

        def flaky(path, n, status, extra):
            def route():
                hits[path] += 1
                if hits[path] <= n:
                    return status, dict(TEXT, **extra), "slow down"
                return _page(path.strip("/"), path.strip("/"), ["/"], path=path)
            return route
        sm_thr = "<urlset><url><loc>{o}/</loc></url><url><loc>{o}/slow</loc></url><url><loc>{o}/busy</loc></url></urlset>"
        sthr = _serve({"/robots.txt": (200, TEXT, "User-agent: *\nAllow: /\nSitemap: {o}/sitemap.xml\n"),
                       "/sitemap.xml": (200, {"Content-Type": "application/xml"}, sm_thr),
                       "/": _page("Home", "Home", ["/slow", "/busy"], path="/"),
                       "/slow": flaky("/slow", 2, 429, {}),
                       "/busy": flaky("/busy", 1, 503, {"Retry-After": "0"})})
        srvs.append(sthr)
        c10, res10 = _crawl(sthr)
        same("429 twice, then 200: the page is checked", c10.pages.get(sc.norm(c10.base + "/slow"), {}).get("status"), 200)
        same("503 with Retry-After, then 200", c10.pages.get(sc.norm(c10.base + "/busy"), {}).get("status"), 200)
        same("tries of /slow", hits["/slow"], 3)
        want("the waits are reported", res10, "crawl-coverage", ("INFO",), "asked to slow down 3 times")
        want("no false error after a wait", res10, "sitemap-errors", ("OK",))
        sm_429 = "<urlset><url><loc>{o}/</loc></url><url><loc>{o}/limit</loc></url></urlset>"
        s429 = _serve({"/robots.txt": (200, TEXT, "User-agent: *\nAllow: /\nSitemap: {o}/sitemap.xml\n"),
                       "/sitemap.xml": (200, {"Content-Type": "application/xml"}, sm_429),
                       "/": _page("Home", "Home", ["/limit", "/after"], path="/"),
                       "/limit": (429, TEXT, "slow down"),
                       "/after": _page("After", "After", [], path="/after")})
        srvs.append(s429)
        c11, res11 = _crawl(s429)
        want("still 429 after the retries: the crawl stops", res11, "crawl-coverage", ("WARN",), "still answered 429")
        want("429 is not a sitemap error", res11, "sitemap-errors", ("OK",))
        want("429 shows under server-errors", res11, "server-errors", ("WARN",), "/limit (429")
        same("no request after the stop", c11.pages.get(sc.norm(c11.base + "/after"), {}).get("status"), None)
        same("a 429 link is not in the links-to-fix table", "| /limit | 429 |" in to_markdown(c11, checks(c11)), False)
        same("tries of /limit", sum(1 for _, p, _ in s429.log if p == "/limit"), RETRIES + 1)

        print("Control site without defects, with a Cyrillic URL and windows-1251 pages (nothing above INFO):")
        cs = _serve(clean_site())
        srvs.append(cs)
        c5, res5 = _crawl(cs)
        loud = ["%s %s: %s" % (r["id"], r["status"], r["detail"]) for r in res5.values() if r["status"] in ("WARN", "FAIL")]
        print("  %-4s %-16s %s" % ("ok" if not loud else "MISS", "control", "clean site gives no WARN or FAIL"))
        if loud:
            fails += ["control: " + x for x in loud]
        for cid in ("broken-links", "server-errors", "redirect-links", "sitemap-errors", "not-in-sitemap", "orphans",
                    "canonical", "titles", "h1", "mixed-host-links"):
            want("clean site", res5, cid, ("OK",))
        cyr = c5.pages.get(sc.norm(ascii_url(c5.base + CYR)), {})
        same("the Cyrillic URL answers 200", cyr.get("status"), 200)
        same("windows-1251 titles read right", (c5.pages[sc.norm(c5.base + "/cp-meta")]["title"],
                                                 c5.pages[sc.norm(c5.base + "/cp-bare")]["title"]), (HELMET, WHEEL))
        same("parse_site punycodes a Cyrillic host", parse_site("\u043f\u0440\u0438\u043c\u0435\u0440.\u0440\u0444"),
             ("https", "xn--e1afmkfd.xn--p1ai"))

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]
        sock.close()
        dead = Crawl(("http", "127.0.0.1:%d" % dead_port)).run()
        same("a closed port gives no result (exit 2)", dead, None)
    finally:
        for x in srvs:
            x.shutdown()
            x.server_close()
        sc.MIN_INTERVAL, BACKOFF, SLOW_FLOOR = saved
    print()
    if fails:
        print("SELFTEST FAILED:")
        for x in fails:
            print("  - " + x)
        return 1
    print("SELFTEST PASSED: every planted defect was caught, the control site stayed clean.")
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Crawl a live site and report link and index defects (standard library only).")
    ap.add_argument("site", nargs="?", help="canonical host, e.g. example.com, or an origin such as http://127.0.0.1:8000")
    ap.add_argument("--max-pages", type=int, default=200, help="URLs to fetch at most (default 200)")
    ap.add_argument("--max-seconds", type=int, default=600, help="stop after this many seconds (default 600, 0 = no limit)")
    ap.add_argument("--delay", type=float, default=sc.MIN_INTERVAL,
                    help="seconds between requests (default and minimum 0.5); after 429 or 503 the crawler slows "
                         "down by itself")
    ap.add_argument("--include-query", action="store_true", help="also crawl links with a query string")
    ap.add_argument("--json", help="write results and the page list as JSON (input for seo_index.py --pages)")
    ap.add_argument("--md", help="write a Markdown report (for a CI job summary)")
    ap.add_argument("--csv", help="write the page list as CSV")
    ap.add_argument("--compare", help="an earlier --json report: adds the crawl-diff line")
    ap.add_argument("--resolve", action="append", default=[], metavar="HOST=IP",
                    help="like curl --resolve: connect to IP for HOST, TLS and Host header stay the same")
    ap.add_argument("--fail-on", choices=("fail", "warn"), default="fail")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.site:
        ap.print_usage()
        print("error: give a site or --selftest")
        return 2
    try:
        origin = parse_site(a.site)
    except ValueError as e:
        print("error: %s" % e)
        return 2
    if a.max_pages < 1 or a.max_seconds < 0:
        print("error: --max-pages must be 1 or more and --max-seconds 0 or more")
        return 2
    old = None
    if a.compare:
        try:
            with open(a.compare, encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, ValueError) as e:
            print("error: --compare %s: %s" % (a.compare, e))
            return 2
    if a.resolve:
        pins = dict(x.lower().split("=", 1) for x in a.resolve if "=" in x)
        _orig = socket.getaddrinfo

        def _pinned(h, *args, **kw):
            return _orig(pins.get(str(h).lower(), h), *args, **kw)
        socket.getaddrinfo = _pinned
    c = Crawl(origin, a.max_pages, a.max_seconds, a.include_query, delay=max(a.delay, sc.MIN_INTERVAL)).run()
    if c is None:
        print("SITE UNREACHABLE: %s://%s/ gives no answer or 5xx" % origin)
        return 2
    res = checks(c, old, os.path.basename(a.compare or ""))
    print("seo_crawl %s (%d URLs fetched, %d requests)" % (c.host, c.fetched, c.f.n))
    print("id | status | detail")
    for r in res:
        print("%-16s | %-4s | %s" % (r["id"], r["status"], r["detail"]))
    cnt = {k: sum(1 for r in res if r["status"] == k) for k in STATUSES}
    print("TOTAL: OK %(OK)d, WARN %(WARN)d, FAIL %(FAIL)d, INFO %(INFO)d, SKIP %(SKIP)d; " % cnt
          + "requests: %d" % c.f.n)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"host": c.host, "origin": c.base, "version": VERSION,
                       "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                       "requests": c.f.n, "fetched": c.fetched, "complete": c.links_complete and not c.stop_reason,
                       "summary": cnt, "results": res, "pages": page_rows(c)}, fh, ensure_ascii=False, indent=1)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(c, res))
    if a.csv:
        write_csv(a.csv, page_rows(c))
    if cnt["FAIL"] or (a.fail_on == "warn" and cnt["WARN"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
