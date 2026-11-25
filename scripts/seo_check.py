#!/usr/bin/env python3
"""
seo_check.py: external SEO check of a live site. Python 3.9+, standard library only.

Usage
  python seo_check.py example.com [--pages 8] [--json out.json] [--md out.md]
                      [--engines google,yandex,bing] [--indexnow-key KEY]
                      [--max-requests 60] [--resolve host=IP] [--fail-on fail|warn]
  python seo_check.py --selftest

The host you pass is the canonical host (with or without www, as your site uses it).
The script reads robots.txt, the sitemap, a sample of sitemap URLs and a few special paths and prints
one line per check: id | OK, WARN, FAIL, INFO or SKIP | detail.

Politeness: GET and HEAD only, at most 2 requests per second, at most --max-requests per run,
an honest User-Agent, redirects are not followed (the check inspects them).

Exit codes
  0  no FAIL (with --fail-on warn: no FAIL and no WARN); --selftest: every planted defect was caught
  1  at least one FAIL (or WARN with --fail-on warn); --selftest: some check stayed silent on a defect
  2  site unreachable (home page gives no answer or 5xx) or bad arguments

Source: https://github.com/GoldenSample/seo-ops (MIT). The thresholds and the reasons behind each
check are in skills/seo-launch/SKILL.md.
"""
import argparse
import datetime
import gzip
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

VERSION = "1.0.1"
UA = "seo-ops-check/%s (+https://github.com/GoldenSample/seo-ops)" % VERSION
MIN_INTERVAL = 0.5          # 2 requests per second
TIMEOUT = 15
MAX_BODY = 3_000_000

# AI crawlers. Search and user-triggered bots decide whether an AI product can cite or open your pages.
# Training bots only decide whether your text may be used to train models. Sources (checked 2026-11-25):
# https://developers.openai.com/api/docs/bots , https://support.claude.com/en/articles/8896518 ,
# https://developers.google.com/search/docs/fundamentals/gen-ai-controls ,
# https://yandex.ru/support/webmaster/ru/adding-site/indexing-prohibition
AI_SEARCH_BOTS = ["OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User"]
AI_TRAINING_BOTS = ["GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended", "CCBot", "Bytespider",
                    "meta-externalagent", "Amazonbot"]
ORG_TYPES = {"organization", "localbusiness", "store", "onlinestore", "onlinebusiness", "corporation",
             "professionalservice", "electronicsstore", "computerstore"}
STATUSES = ("OK", "WARN", "FAIL", "INFO", "SKIP")


# ---------------------------------------------------------------- network

class Resp:
    def __init__(self, status=0, headers=None, body="", url="", error="", raw=b"", elapsed=0.0):
        self.status = status          # 0 network error, -1 request budget spent
        self.headers = headers or {}  # lower-case keys
        self.body = body
        self.raw = raw
        self.url = url
        self.error = error
        self.elapsed = elapsed        # seconds until the body was read

    def h(self, name):
        return self.headers.get(name.lower(), "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Fetcher:
    def __init__(self, max_requests=60):
        self.n = 0
        self.max = max_requests
        self.last = 0.0
        self.opener = urllib.request.build_opener(_NoRedirect())

    def tick(self):
        wait = MIN_INTERVAL - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.n += 1

    def get(self, url, method="GET", accept="*/*", enc="gzip", maxbytes=MAX_BODY):
        if self.n >= self.max:
            return Resp(-1, error="request budget of %d spent" % self.max, url=url)
        self.tick()
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": UA, "Accept": accept, "Accept-Encoding": enc})
        t0 = time.monotonic()
        try:
            r = self.opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            r = e
        except Exception as e:  # DNS, TLS, timeout
            return Resp(0, error="%s: %s" % (type(e).__name__, e), url=url)
        try:
            raw = b"" if method == "HEAD" else r.read(maxbytes)
        except Exception as e:
            return Resp(0, error="read: %s" % e, url=url)
        elapsed = time.monotonic() - t0
        headers = {k.lower(): v for k, v in r.headers.items()}
        if headers.get("content-encoding", "").lower() == "gzip" and raw:
            try:
                raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, maxbytes)
            except Exception:
                pass
        if raw[:2] == b"\x1f\x8b":  # a .gz file served as is (sitemap.xml.gz)
            try:
                raw = gzip.decompress(raw)[:maxbytes]
            except Exception:
                pass
        cs = "utf-8"
        m = re.search(r"charset=([\w-]+)", headers.get("content-type", ""), re.I)
        if m:
            cs = m.group(1)
        try:
            body = raw.decode(cs, "replace")
        except LookupError:
            body = raw.decode("utf-8", "replace")
        return Resp(getattr(r, "status", None) or r.code, headers, body, url, raw=raw, elapsed=elapsed)


def tls_probe(host, fetcher):
    """Return (alpn, tls_version, days_left, error) from one TLS handshake."""
    if fetcher.n >= fetcher.max:
        return None, None, None, "request budget spent"
    fetcher.tick()
    try:
        ctx = ssl.create_default_context()
        ctx.set_alpn_protocols(["h2", "http/1.1"])
        with socket.create_connection((host, 443), TIMEOUT) as s:
            with ctx.wrap_socket(s, server_hostname=host) as t:
                cert = t.getpeercert() or {}
                days = None
                if cert.get("notAfter"):
                    end = datetime.datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), datetime.timezone.utc)
                    days = (end - datetime.datetime.now(datetime.timezone.utc)).days
                return t.selected_alpn_protocol(), t.version(), days, ""
    except Exception as e:
        return None, None, None, "%s: %s" % (type(e).__name__, e)


# ---------------------------------------------------------------- HTML parsing

class Info:
    def __init__(self):
        self.title = None
        self.lang = None
        self.metas = []
        self.links = []
        self.imgs = []
        self.scripts = []
        self.styles = []
        self.ld_raw = []
        self.h1 = 0
        self.a_count = 0

    def meta(self, key):
        key = key.lower()
        return [m.get("content", "") for m in self.metas
                if (m.get("name") or m.get("property") or "").lower() == key]

    def meta1(self, key):
        v = self.meta(key)
        return v[0].strip() if v else None

    def link(self, rel):
        for l in self.links:
            if rel in (l.get("rel") or "").lower().split():
                return l.get("href")
        return None


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.i = Info()
        self._in_title = False
        self._title = []
        self._ld = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        i = self.i
        if tag == "html" and i.lang is None:
            i.lang = a.get("lang", "").strip()
        elif tag == "title" and i.title is None:
            self._in_title = True
        elif tag == "meta":
            i.metas.append(a)
        elif tag == "link":
            i.links.append(a)
            if "stylesheet" in a.get("rel", "").lower().split() and a.get("href"):
                i.styles.append(a["href"])
        elif tag == "img":
            i.imgs.append(a)
        elif tag == "h1":
            i.h1 += 1
        elif tag == "a":
            i.a_count += 1
        elif tag == "script":
            if a.get("src"):
                i.scripts.append(a["src"])
            if "ld+json" in a.get("type", "").lower():
                self._ld = []

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self.i.title = "".join(self._title).strip()
        elif tag == "script" and self._ld is not None:
            self.i.ld_raw.append("".join(self._ld))
            self._ld = None

    def handle_data(self, data):
        if self._in_title:
            self._title.append(data)
        if self._ld is not None:
            self._ld.append(data)


def parse_html(text):
    p = _P()
    try:
        p.feed(text)
        p.close()
    except Exception:
        pass
    return p.i


def iter_dicts(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from iter_dicts(v)
    elif isinstance(o, list):
        for v in o:
            yield from iter_dicts(v)


def types_of(d):
    t = d.get("@type")
    if isinstance(t, str):
        return [t.lower()]
    if isinstance(t, list):
        return [x.lower() for x in t if isinstance(x, str)]
    return []


def is_org(d):
    for t in types_of(d):
        if t in ORG_TYPES or t.endswith("store") or t.endswith("business") or t.endswith("organization"):
            return True
    return False


class Page:
    def __init__(self, url, resp):
        self.url = url
        self.resp = resp
        self.info = parse_html(resp.body) if resp.status == 200 else Info()
        self.nodes = []
        self.ld_errors = 0
        for raw in self.info.ld_raw:
            try:
                self.nodes.extend(iter_dicts(json.loads(raw.strip(), strict=False)))
            except Exception:
                self.ld_errors += 1

    def path(self):
        s = urllib.parse.urlsplit(self.url)
        return (s.path or "/") + (("?" + s.query) if s.query else "")

    def robots(self):
        return (" ".join(self.info.meta("robots")) + " " + self.resp.h("x-robots-tag")).lower()


def norm(u):
    s = urllib.parse.urlsplit(u)
    return "%s://%s%s%s" % (s.scheme.lower(), s.netloc.lower(), s.path or "/", ("?" + s.query) if s.query else "")


def R(i, status, detail):
    return {"id": i, "status": status, "detail": detail}


def worst(statuses):
    for s in ("FAIL", "WARN", "INFO"):
        if s in statuses:
            return s
    return "OK"


def short(items, n=3):
    items = list(items)
    s = ", ".join(items[:n])
    return s + (" and %d more" % (len(items) - n) if len(items) > n else "")


def loc_of(resp):
    h = resp.h("location")
    return urllib.parse.urljoin(resp.url, h) if h else ""


def no_answer(resp, cid, what):
    """FAIL when the network failed, SKIP when the request budget is spent, None when there is an answer."""
    if resp is None or resp.status == -1:
        return R(cid, "SKIP", "%s: skipped, request budget spent" % what)
    if resp.status == 0:
        return R(cid, "FAIL", "%s: no answer (%s)" % (what, resp.error))
    return None


# ---------------------------------------------------------------- robots.txt (RFC 9309)
# Written for seo-ops by a local model from a spec and tests (tests/test_robots.py), reviewed by Claude.
def _agent_token(value):
    """Product token of a user-agent value: '*' or the leading run of letters, '_' and '-'."""
    m = re.match(r"\*|[A-Za-z_-]+", value)
    return (m.group(0) if m else value).lower()


def _robots_groups(robots_text):
    groups, current, prev_ua = [], None, False
    for line in robots_text.splitlines():
        content = line.split("#", 1)[0].strip()
        if ":" not in content:
            continue
        key, value = content.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if current is None or not prev_ua:
                current = {"agents": [], "rules": []}
                groups.append(current)
            current["agents"].append(_agent_token(value))
            prev_ua = True
        elif key in ("allow", "disallow"):
            if current is not None:
                current["rules"].append((key, value))
            prev_ua = False
        # other keys (sitemap, crawl-delay, clean-param, host) are transparent
    return groups


def _rule_matches(pattern, path):
    rx = re.escape(pattern).replace(r"\*", ".*")
    if pattern.endswith("$"):
        rx = rx[:-2] + "$"
    return re.match(rx, path) is not None


def robots_allows(robots_text, user_agent, path="/", ignore_star=False):
    """RFC 9309: may the crawler with product token user_agent fetch path?

    The groups that name the agent are combined; otherwise the '*' groups (unless ignore_star, used for
    YandexAdditional, which does not read the '*' group). The longest matching rule wins; on a tie Allow wins.
    """
    if path == "/robots.txt":
        return True
    groups = _robots_groups(robots_text)
    ua = user_agent.lower()
    chosen = [g for g in groups if ua in g["agents"]]
    if not chosen:
        if ignore_star:
            return True
        chosen = [g for g in groups if "*" in g["agents"]]
    best = None
    for g in chosen:
        for kind, pattern in g["rules"]:
            if pattern and _rule_matches(pattern, path):
                n = len(pattern)
                if best is None or n > best[1] or (n == best[1] and kind == "allow"):
                    best = (kind, n)
    return best is None or best[0] == "allow"


def robots_sitemaps(robots_text):
    """Values of all Sitemap lines, in file order."""
    out = []
    for line in robots_text.splitlines():
        content = line.split("#", 1)[0].strip()
        if ":" in content:
            key, value = content.split(":", 1)
            if key.strip().lower() == "sitemap" and value.strip():
                out.append(value.strip())
    return out


def engine_allowed(text, engine):
    """Is the home page open for the main robot of a search engine."""
    if engine == "google":
        return robots_allows(text, "Googlebot", "/")
    if engine == "bing":
        return robots_allows(text, "bingbot", "/")
    if engine == "yandex":
        agents = {a.strip().lower() for a in re.findall(r"(?im)^\s*user-agent\s*:\s*([^#\r\n]+)", text)}
        return robots_allows(text, "YandexBot" if "yandexbot" in agents else "Yandex", "/")
    return True


# ---------------------------------------------------------------- checks: crawl and index

def check_redirects(items):
    """items: [(label, Resp, expected_url, kind)], kind: main-http | alt-host."""
    bad, warn, good, notes = [], [], [], []
    for label, resp, expected, kind in items:
        if resp.status == -1:
            notes.append("%s: skipped (budget)" % label)
            continue
        if resp.status == 0:
            if kind == "alt-host":
                notes.append("%s: no answer, fine if the host is not used anywhere" % label)
            else:
                warn.append("%s: no answer (%s), http links will fail" % (label, resp.error))
            continue
        loc = loc_of(resp)
        if resp.status in (301, 308) and loc == expected:
            good.append(label)
        elif resp.status in (302, 303, 307) and loc == expected:
            warn.append("%s: %d is temporary, use 301 or 308" % (label, resp.status))
        else:
            bad.append("%s: status %d, Location %s, expected a permanent redirect to %s"
                       % (label, resp.status, loc or "-", expected))
    detail = "; ".join(bad + warn + (["permanent redirect: " + ", ".join(good)] if good else []) + notes)
    return R("redirects", "FAIL" if bad else "WARN" if warn else "OK", detail or "nothing to check")


def check_trailing_slash(resp, expected, variant_canonical):
    if resp is None:
        return R("trailing-slash", "SKIP", "no sitemap URL with a path to test")
    u = no_answer(resp, "trailing-slash", "slash variant")
    if u:
        return u
    loc = loc_of(resp)
    if resp.status in (301, 308) and loc == expected:
        return R("trailing-slash", "OK", "the other slash form redirects permanently to the sitemap form")
    if resp.status in (302, 303, 307) and loc == expected:
        return R("trailing-slash", "WARN", "the other slash form redirects with %d, use 301 or 308" % resp.status)
    if resp.status in (404, 410):
        return R("trailing-slash", "OK", "the other slash form answers %d (no duplicate)" % resp.status)
    if resp.status == 200:
        if variant_canonical and norm(variant_canonical) == norm(expected):
            return R("trailing-slash", "OK", "the other slash form answers 200 with canonical to the sitemap form")
        return R("trailing-slash", "WARN", "%s answers 200 without canonical to %s: duplicate URL"
                 % (resp.url, expected))
    return R("trailing-slash", "WARN", "the other slash form answers %d, Location %s" % (resp.status, loc or "-"))


def check_open_redirect(resp, host):
    u = no_answer(resp, "open-redirect", "//example.com/ probe")
    if u:
        return u
    target = urllib.parse.urlsplit(loc_of(resp)).netloc.lower() if resp.h("location") else ""
    if 300 <= resp.status < 400 and target and target != host and target != alt_host(host):
        return R("open-redirect", "FAIL", "https://%s//example.com/ redirects to %s: open redirect" % (host, target))
    return R("open-redirect", "OK", "//example.com/ stays on the site (status %d)" % resp.status)


def check_robots(resp, engines, asset_path):
    u = no_answer(resp, "robots-txt", "robots.txt")
    if u:
        return u
    if resp.status in (404, 410):
        return R("robots-txt", "WARN", "no robots.txt (%d): everything is allowed, but there is no Sitemap line" % resp.status)
    if resp.status >= 500 or resp.status == 429:
        return R("robots-txt", "FAIL", "robots.txt answers %d: Google stops crawling the site while robots.txt fails "
                 "(first 12 hours), then uses the last good copy" % resp.status)
    if resp.status != 200:
        return R("robots-txt", "WARN", "robots.txt answers %d (Location %s)" % (resp.status, loc_of(resp) or "-"))
    text = resp.body
    bad, warn, info = [], [], []
    for e in engines:
        if not engine_allowed(text, e):
            bad.append("the home page is blocked for %s" % e)
    if asset_path and not robots_allows(text, "Googlebot", asset_path):
        bad.append("%s is blocked: robots must load CSS and JS to render pages" % asset_path)
    sm = robots_sitemaps(text)
    abs_sm = [s for s in sm if re.match(r"https?://", s, re.I)]
    if not abs_sm:
        warn.append("no Sitemap: line with an absolute URL")
    if "yandex" in engines and not re.search(r"(?im)^\s*clean-param\s*:", text):
        info.append("no Clean-param: Yandex may treat URLs with tracking parameters as duplicates")
    det = "Sitemap lines: %d" % len(sm)
    st = "FAIL" if bad else "WARN" if warn else "INFO" if info else "OK"
    return R("robots-txt", st, "; ".join(bad + warn + info + [det]))


def check_ai_bots(resp):
    if resp is None or resp.status != 200:
        return R("ai-bots", "INFO", "no robots.txt rules: all AI bots may crawl")
    text = resp.body
    blocked_search = [b for b in AI_SEARCH_BOTS if not robots_allows(text, b, "/")]
    blocked_train = [b for b in AI_TRAINING_BOTS if not robots_allows(text, b, "/")]
    ya_add = robots_allows(text, "YandexAdditional", "/", ignore_star=True)
    det = ("training bots blocked: %s; YandexAdditional (Alice answers) %s"
           % (", ".join(blocked_train) or "none", "allowed" if ya_add else "blocked in its own group"))
    if blocked_search:
        return R("ai-bots", "WARN", "search and answer bots blocked: %s: these AI products will not cite the site; %s"
                 % (", ".join(blocked_search), det))
    return R("ai-bots", "OK", "search and answer bots allowed; " + det)


def sitemap_parse(text):
    """(locs, lastmods, child_sitemaps); raises ET.ParseError."""
    root = ET.fromstring(text.lstrip("\ufeff").strip())
    locs, lms, kids = [], [], []
    is_index = root.tag.split("}")[-1].lower() == "sitemapindex"
    for el in root:
        loc = lm = None
        for c in el:
            t = c.tag.split("}")[-1].lower()
            if t == "loc":
                loc = (c.text or "").strip()
            elif t == "lastmod":
                lm = (c.text or "").strip()
        if loc:
            if is_index:
                kids.append(loc)
            else:
                locs.append(loc)
                lms.append(lm or "")
    return locs, lms, kids


def check_sitemap(found, today=None):
    """found: dict(url, resp, locs, lastmods, children, error, host)."""
    today = today or datetime.date.today()
    resp = found.get("resp")
    u = no_answer(resp, "sitemap", "sitemap")
    if u:
        return u
    if resp.status != 200:
        return R("sitemap", "FAIL", "%s answers %d" % (found["url"], resp.status))
    if found.get("error"):
        return R("sitemap", "FAIL", "%s is not valid XML (%s)" % (found["url"], found["error"]))
    locs, lms = found["locs"], found["lastmods"]
    if not locs:
        return R("sitemap", "FAIL", "%s has no <loc> URLs" % found["url"])
    warn = []
    ct = resp.h("content-type").lower()
    if "xml" not in ct and "gzip" not in ct and "text/plain" not in ct:
        warn.append("Content-Type is %s, expected xml" % (ct or "missing"))
    have = [x for x in lms if x]
    if not have:
        warn.append("no lastmod: engines cannot see which pages changed")
    elif len(have) < len(lms):
        warn.append("lastmod on %d of %d URLs" % (len(have), len(lms)))
    days = {x[:10] for x in have}
    if len(have) > 3 and len(days) == 1:
        warn.append("every lastmod is %s: looks like the build date, not the change date" % next(iter(days)))
    future = [x for x in have if x[:10] > (today + datetime.timedelta(days=1)).isoformat()]
    if future:
        warn.append("%d lastmod values are in the future" % len(future))
    host = found.get("host")
    foreign = [l for l in locs if host and urllib.parse.urlsplit(l).netloc.lower() != host]
    if foreign:
        warn.append("%d URLs are on another host, e.g. %s" % (len(foreign), foreign[0]))
    det = "%d URLs from %s%s, lastmod on %d, distinct dates %d" % (
        len(locs), found["url"], (" and %d child sitemaps" % len(found["children"])) if found["children"] else "",
        len(have), len(days))
    return R("sitemap", "WARN" if warn else "OK", "; ".join(warn + [det]))


def canon_problem(p):
    c = p.info.link("canonical")
    if not c:
        return "WARN", "no canonical"
    if not re.match(r"https?://", c, re.I):
        return "WARN", "relative canonical (%s)" % c
    if norm(c) != norm(p.url):
        return "FAIL", "canonical points to %s" % c
    return None, None


def check_sitemap_urls(pages):
    """pages[0] is the home page; the rest come from the sitemap."""
    if len(pages) < 1:
        return R("sitemap-urls", "SKIP", "no pages")
    bad, warn = [], []
    for p in pages:
        st = p.resp.status
        if st == -1:
            continue
        if st != 200:
            bad.append("%s answers %s" % (p.path(), st if st else p.resp.error))
            continue
        if "noindex" in p.robots():
            bad.append("%s has noindex" % p.path())
        level, why = canon_problem(p)
        if level == "FAIL":
            bad.append("%s: %s" % (p.path(), why))
        elif level == "WARN":
            warn.append("%s: %s" % (p.path(), why))
    live = sum(1 for p in pages if p.resp.status == 200)
    if bad:
        return R("sitemap-urls", "FAIL", "sitemap must list only canonical indexable 200 URLs: " + short(bad + warn, 5))
    if warn:
        return R("sitemap-urls", "WARN", short(warn, 5))
    return R("sitemap-urls", "OK", "%d of %d sampled URLs: 200, indexable, self-canonical" % (live, len(pages)))


def check_not_found(resp):
    u = no_answer(resp, "not-found", "unknown URL")
    if u:
        return u
    if resp.status in (404, 410):
        return R("not-found", "OK", "an unknown URL answers %d" % resp.status)
    if resp.status == 200:
        return R("not-found", "FAIL", "an unknown URL answers 200: soft 404")
    if 300 <= resp.status < 400:
        return R("not-found", "WARN", "an unknown URL redirects to %s: engines may treat it as soft 404" % (loc_of(resp) or "-"))
    return R("not-found", "FAIL", "an unknown URL answers %d" % resp.status)


# ---------------------------------------------------------------- checks: transport and hygiene

def check_transport(enc_home, enc_sitemap, alpn):
    proto, tls, _days, err = alpn
    warn = []
    for label, enc in (("HTML", enc_home), ("sitemap", enc_sitemap)):
        if enc is not None and enc.lower() not in ("gzip", "br", "zstd"):
            warn.append("%s without compression (Content-Encoding: %s)" % (label, enc or "none"))
    if err:
        warn.append("TLS probe: %s" % err)
    elif proto != "h2":
        warn.append("no HTTP/2 (ALPN: %s)" % proto)
    det = "HTML %s, sitemap %s, ALPN %s, %s" % (enc_home or "-", enc_sitemap or "-", proto, tls)
    return R("transport", "WARN" if warn else "OK", "; ".join(warn) if warn else det)


def check_tls_expiry(alpn):
    _proto, _tls, days, err = alpn
    if err:
        return R("tls-expiry", "FAIL", "TLS handshake failed: %s" % err)
    if days is None:
        return R("tls-expiry", "SKIP", "no certificate date")
    if days < 7:
        return R("tls-expiry", "FAIL", "certificate expires in %d days" % days)
    if days < 21:
        return R("tls-expiry", "WARN", "certificate expires in %d days" % days)
    return R("tls-expiry", "OK", "certificate valid for %d more days" % days)


def check_response_time(home):
    ms = int(home.elapsed * 1000)
    if ms > 2000:
        return R("response-time", "WARN", "home page took %d ms from this runner: slow server response" % ms)
    if ms > 1000:
        return R("response-time", "INFO", "home page took %d ms from this runner" % ms)
    return R("response-time", "OK", "home page took %d ms from this runner" % ms)


def check_static_cache(asset_url, resp):
    if asset_url is None:
        return R("static-cache", "SKIP", "no same-origin JS or CSS file on the home page")
    u = no_answer(resp, "static-cache", "static file")
    if u:
        return u
    cc = resp.h("cache-control")
    m = re.search(r"max-age=(\d+)", cc)
    name = urllib.parse.urlsplit(asset_url).path
    if resp.status == 200 and ("immutable" in cc.lower() or (m and int(m.group(1)) >= 2592000)):
        return R("static-cache", "OK", "%s: %s" % (name, cc))
    return R("static-cache", "WARN", "%s: status %d, Cache-Control: %s (hashed files can be cached for a year)"
             % (name, resp.status, cc or "none"))


def check_source_maps(asset_url, map_resp):
    if asset_url is None or not asset_url.endswith(".js"):
        return R("source-maps", "SKIP", "no same-origin JS file on the home page")
    u = no_answer(map_resp, "source-maps", ".map")
    if u:
        return R("source-maps", "SKIP", u["detail"])
    p = urllib.parse.urlsplit(asset_url).path + ".map"
    if map_resp.status == 200:
        return R("source-maps", "WARN", "%s is public: the source code is exposed" % p)
    return R("source-maps", "OK", "%s answers %d" % (p, map_resp.status))


def check_security_headers(home):
    h = home.headers
    warn = []
    if not h.get("strict-transport-security"):
        warn.append("no Strict-Transport-Security")
    if "nosniff" not in h.get("x-content-type-options", "").lower():
        warn.append("no X-Content-Type-Options: nosniff")
    if warn:
        return R("security-headers", "WARN", "; ".join(warn))
    if not h.get("content-security-policy"):
        return R("security-headers", "INFO", "HSTS and nosniff present, no Content-Security-Policy")
    return R("security-headers", "OK", "HSTS, nosniff and CSP present")


def check_security_txt(resp, now=None):
    u = no_answer(resp, "security-txt", "security.txt")
    if u:
        return R("security-txt", "SKIP", u["detail"]) if u["status"] == "SKIP" else u
    if resp.status != 200:
        return R("security-txt", "WARN", "no /.well-known/security.txt (status %d), RFC 9116" % resp.status)
    if not re.search(r"^\s*Contact:", resp.body, re.I | re.M):
        return R("security-txt", "WARN", "security.txt has no Contact line")
    m = re.search(r"^\s*Expires:\s*(\S+)", resp.body, re.I | re.M)
    if not m:
        return R("security-txt", "WARN", "security.txt has no Expires line")
    try:
        exp = datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=datetime.timezone.utc)
        if exp < (now or datetime.datetime.now(datetime.timezone.utc)):
            return R("security-txt", "WARN", "security.txt expired on %s" % m.group(1))
    except ValueError:
        return R("security-txt", "WARN", "security.txt Expires is not a date: %s" % m.group(1))
    return R("security-txt", "OK", "security.txt present, Expires %s" % m.group(1))


# ---------------------------------------------------------------- checks: pages

def live_pages(pages):
    return [p for p in pages if p.resp.status == 200]


def check_titles(pages):
    bad, warn, seen = [], [], {}
    for p in live_pages(pages):
        t = p.info.title
        if not t:
            bad.append("%s: no title" % p.path())
            continue
        if len(t) > 70:
            warn.append("%s: title has %d characters" % (p.path(), len(t)))
        seen.setdefault(t.strip().lower(), []).append(p.path())
    for paths in seen.values():
        if len(paths) > 1:
            warn.append("same title on " + ", ".join(paths))
    if bad:
        return R("titles", "FAIL", short(bad + warn, 6))
    if warn:
        return R("titles", "WARN", short(warn, 6))
    return R("titles", "OK", "unique titles up to 70 characters on %d pages" % len(live_pages(pages)))


def check_descriptions(pages):
    warn, info = [], []
    for p in live_pages(pages):
        d = p.info.meta1("description")
        if not d:
            warn.append("%s: no description" % p.path())
        elif len(d) < 50:
            warn.append("%s: description has %d characters" % (p.path(), len(d)))
        elif len(d) > 160:
            info.append("%s: description has %d characters, the snippet will be cut" % (p.path(), len(d)))
    if warn:
        return R("descriptions", "WARN", short(warn + info, 6))
    if info:
        return R("descriptions", "INFO", short(info, 6))
    return R("descriptions", "OK", "descriptions of 50 to 160 characters on %d pages" % len(live_pages(pages)))


def check_h1(pages):
    warn, info = [], []
    for p in live_pages(pages):
        if p.info.h1 == 0:
            warn.append("%s: no h1" % p.path())
        elif p.info.h1 > 1:
            info.append("%s: %d h1" % (p.path(), p.info.h1))
    if warn:
        return R("h1", "WARN", short(warn + info, 6))
    if info:
        return R("h1", "INFO", short(info, 6))
    return R("h1", "OK", "one h1 on %d pages" % len(live_pages(pages)))


def check_lang_viewport(pages):
    warn = []
    for p in live_pages(pages):
        if not p.info.lang:
            warn.append("%s: no <html lang>" % p.path())
        if not p.info.meta1("viewport"):
            warn.append("%s: no viewport meta" % p.path())
    if warn:
        return R("lang-viewport", "WARN", short(warn, 6))
    return R("lang-viewport", "OK", "html lang and viewport on %d pages" % len(live_pages(pages)))


def check_open_graph(pages):
    warn = []
    for p in live_pages(pages):
        miss = []
        if not p.info.meta1("og:title"):
            miss.append("og:title")
        img = p.info.meta1("og:image")
        if not img:
            miss.append("og:image")
        elif not re.match(r"https?://", img, re.I):
            miss.append("absolute og:image")
        if not p.info.meta1("twitter:card"):
            miss.append("twitter:card")
        if miss:
            warn.append("%s: no %s" % (p.path(), ", ".join(miss)))
    if warn:
        return R("open-graph", "WARN", short(warn, 4))
    return R("open-graph", "OK", "og:title, absolute og:image and twitter:card on %d pages" % len(live_pages(pages)))


def check_image_preview(pages):
    miss = [p.path() for p in live_pages(pages)
            if "max-image-preview:large" not in p.robots().replace(" ", "")]
    if miss:
        return R("image-preview", "INFO", "no max-image-preview:large (large previews in Discover and search): " + short(miss))
    return R("image-preview", "OK", "max-image-preview:large on %d pages" % len(live_pages(pages)))


def check_images(pages):
    imgs = no_alt = no_wh = n = 0
    for p in live_pages(pages):
        n += 1
        for im in p.info.imgs:
            imgs += 1
            if "alt" not in im:
                no_alt += 1
            if not (im.get("width") and im.get("height")):
                no_wh += 1
    if not imgs:
        return R("images", "SKIP", "no <img> on %d sampled pages" % n)
    det = "%d <img> on %d pages: without alt %d, without width and height %d" % (imgs, n, no_alt, no_wh)
    return R("images", "WARN" if (no_alt or no_wh) else "OK", det)


# ---------------------------------------------------------------- checks: structured data

def check_json_ld(pages):
    lp = live_pages(pages)
    broken = ["%s (%d blocks)" % (p.path(), p.ld_errors) for p in lp if p.ld_errors]
    if broken:
        return R("json-ld", "FAIL", "JSON-LD does not parse: " + short(broken))
    with_ld = [p for p in lp if p.nodes]
    if not with_ld:
        return R("json-ld", "WARN", "no JSON-LD on %d sampled pages" % len(lp))
    return R("json-ld", "OK", "JSON-LD parses on %d of %d pages" % (len(with_ld), len(lp)))


def check_organization(home):
    if home.resp.status != 200:
        return R("organization", "SKIP", "home page is not 200")
    orgs = [d for d in home.nodes if is_org(d)]
    if not orgs:
        return R("organization", "WARN", "no Organization or store node on the home page")
    if not any(d.get("@id") for d in orgs):
        return R("organization", "INFO", "organization node without @id: other nodes cannot reference it")
    return R("organization", "OK", "organization node with @id on the home page")


def check_website(home):
    if home.resp.status != 200:
        return R("website", "SKIP", "home page is not 200")
    if any("website" in types_of(d) for d in home.nodes):
        return R("website", "OK", "WebSite node on the home page")
    return R("website", "WARN", "no WebSite node on the home page (site name in results)")


def offer_problems(prod):
    """None = no offers; otherwise a list of (level, problem)."""
    offers = prod.get("offers")
    if not offers:
        return None
    lst = offers if isinstance(offers, list) else [offers]
    probs = []
    for o in lst:
        if not isinstance(o, dict):
            continue
        spec = o.get("priceSpecification") if isinstance(o.get("priceSpecification"), dict) else {}
        price = o.get("price", o.get("lowPrice", spec.get("price")))
        cur = o.get("priceCurrency", spec.get("priceCurrency"))
        if price in (None, ""):
            probs.append(("FAIL", "no price"))
        if not cur:
            probs.append(("FAIL", "no priceCurrency"))
        if not o.get("availability"):
            probs.append(("WARN", "no availability"))
    return probs


def check_product_offer(pages):
    seen, fail, warn, no_offer = 0, [], [], []
    for p in live_pages(pages):
        for d in p.nodes:
            if "product" in types_of(d):
                seen += 1
                pr = offer_problems(d)
                if pr is None:
                    no_offer.append(p.path())
                    continue
                f = sorted({x for lvl, x in pr if lvl == "FAIL"})
                w = sorted({x for lvl, x in pr if lvl == "WARN"})
                if f:
                    fail.append("%s: %s" % (p.path(), ", ".join(f)))
                if w:
                    warn.append("%s: %s" % (p.path(), ", ".join(w)))
    if not seen:
        return R("product-offer", "SKIP", "no Product nodes in the sample (raise --pages)")
    if fail:
        return R("product-offer", "FAIL", short(fail + warn, 4))
    if warn or no_offer:
        return R("product-offer", "WARN", short(warn + ["%s: Product without offers" % x for x in dict.fromkeys(no_offer)], 4))
    return R("product-offer", "OK", "%d Product nodes with price, priceCurrency and availability" % seen)


def check_self_ratings(pages):
    org_rated, prod_rated = [], []
    for p in live_pages(pages):
        for d in p.nodes:
            if not (d.get("aggregateRating") or d.get("review")):
                continue
            if is_org(d):
                org_rated.append(p.path())
            elif "product" in types_of(d):
                prod_rated.append(p.path())
    if org_rated:
        return R("self-ratings", "WARN", "rating or review markup on the organization itself: self-serving reviews are "
                 "not eligible for review snippets in Google; never copy ratings from other platforms: "
                 + short(dict.fromkeys(org_rated)))
    if prod_rated:
        return R("self-ratings", "INFO", "product ratings on %s: they must match reviews visible on the page"
                 % short(dict.fromkeys(prod_rated)))
    return R("self-ratings", "OK", "no rating markup on the organization")


# ---------------------------------------------------------------- checks: IndexNow and llms.txt

def check_indexnow_key(key, resp):
    if not key:
        return R("indexnow-key", "SKIP", "no key given (--indexnow-key or INDEXNOW_KEY)")
    u = no_answer(resp, "indexnow-key", "key file")
    if u:
        return u
    if resp.status != 200:
        return R("indexnow-key", "FAIL", "key file /<key>.txt answers %d" % resp.status)
    if resp.body.strip() != key:
        return R("indexnow-key", "FAIL", "key file answers 200 but its content is not the key")
    return R("indexnow-key", "OK", "key file answers 200 with the key")


def check_llms_txt(resp):
    if resp is None or resp.status <= 0:
        return R("llms-txt", "SKIP", "not requested")
    if resp.status == 200:
        return R("llms-txt", "INFO", "llms.txt present (%s, %d characters); optional: Google says it neither helps "
                 "nor harms, no major AI search has said it reads it" % (resp.h("content-type") or "no type", len(resp.body)))
    return R("llms-txt", "INFO", "no llms.txt (status %d); optional, low priority" % resp.status)


# ---------------------------------------------------------------- sampling

def alt_host(host):
    return host[4:] if host.startswith("www.") else "www." + host


def pick_sample(locs, host, n):
    paths = []
    for loc in locs:
        s = urllib.parse.urlsplit(loc)
        if s.netloc.lower() != host:
            continue
        path = (s.path or "/") + (("?" + s.query) if s.query else "")
        if path == "/" or re.search(r"\.(xml|txt|md|yml|json|pdf|jpg|jpeg|png|webp|avif|gif|svg)$", s.path or "", re.I):
            continue
        paths.append(path)
    groups = {}
    for p in paths:
        groups.setdefault(p.strip("/").split("/")[0], []).append(p)
    order = [list(g) for g in groups.values()]
    out = []
    while len(out) < n and any(order):
        for g in order:
            if g and len(out) < n:
                out.append(g.pop(0))
    return ["https://%s%s" % (host, p) for p in out], paths


def pick_asset(info, base):
    """First same-origin JS file, else first same-origin CSS file."""
    host = urllib.parse.urlsplit(base).netloc.lower()
    for group, ext in ((info.scripts, ".js"), (info.styles, ".css")):
        for s in group:
            full = urllib.parse.urljoin(base, s.split("?")[0].split("#")[0])
            sp = urllib.parse.urlsplit(full)
            if sp.netloc.lower() == host and sp.path.endswith(ext):
                return full
    return None


def find_sitemap(f, base, robots_resp, host):
    cands = []
    if robots_resp is not None and robots_resp.status == 200:
        cands = [s for s in robots_sitemaps(robots_resp.body) if re.match(r"https?://", s, re.I)]
    if not cands:
        cands = [base + "/sitemap.xml"]
    url = cands[0]
    found = {"url": url, "resp": None, "locs": [], "lastmods": [], "children": [], "error": "", "host": host}
    resp = f.get(url, accept="application/xml,text/xml,*/*")
    found["resp"] = resp
    if resp.status != 200:
        return found
    try:
        locs, lms, kids = sitemap_parse(resp.body)
    except ET.ParseError as e:
        found["error"] = str(e)
        return found
    found["locs"], found["lastmods"], found["children"] = locs, lms, kids
    for k in kids[:3]:
        r = f.get(k, accept="application/xml,text/xml,*/*")
        if r.status == 200:
            try:
                l2, m2, _ = sitemap_parse(r.body)
                found["locs"] += l2
                found["lastmods"] += m2
            except ET.ParseError:
                pass
    return found


def toggle_slash(url):
    s = urllib.parse.urlsplit(url)
    path = s.path[:-1] if s.path.endswith("/") else s.path + "/"
    return urllib.parse.urlunsplit((s.scheme, s.netloc, path, s.query, ""))


# ---------------------------------------------------------------- run

def run(host, npages, key, engines, max_requests):
    f = Fetcher(max_requests)
    base = "https://" + host
    html_acc = "text/html,application/xhtml+xml"
    home = f.get(base + "/", accept=html_acc)
    if home.status <= 0 or home.status >= 500:
        return None, f.n, "home page %s: %s" % (base + "/", home.error or "status %d" % home.status)
    res = []
    if home.status != 200:
        res.append(R("home", "FAIL", "home page answers %d (Location %s)" % (home.status, loc_of(home) or "-")))
    robots = f.get(base + "/robots.txt")
    found = find_sitemap(f, base, robots, host)
    sample_urls, paths = pick_sample(found["locs"], host, max(npages - 1, 0))

    alt = alt_host(host)
    items = [("http://%s/" % host, f.get("http://%s/" % host), base + "/", "main-http"),
             ("https://%s/" % alt, f.get("https://%s/" % alt), base + "/", "alt-host")]
    if paths:
        items.append(("https://%s%s" % (alt, paths[0]), f.get("https://%s%s" % (alt, paths[0])), base + paths[0], "alt-host"))
    res.append(check_redirects(items))

    slash_resp, slash_expected, slash_canon = None, None, None
    if sample_urls:
        slash_expected = sample_urls[0]
        variant = toggle_slash(slash_expected)
        slash_resp = f.get(variant, accept=html_acc)
        if slash_resp.status == 200:
            slash_canon = parse_html(slash_resp.body).link("canonical")
    res.append(check_trailing_slash(slash_resp, slash_expected, slash_canon))
    res.append(check_open_redirect(f.get(base + "//example.com/"), host))

    def enc_of(resp, url):
        if resp is None or resp.status != 200:
            return None
        e = resp.h("content-encoding")
        if not e:
            e = f.get(url, method="HEAD", enc="gzip, br").h("content-encoding")
        return e
    probe = tls_probe(host, f)
    res.append(check_transport(enc_of(home, base + "/"), enc_of(found["resp"], found["url"]), probe))
    res.append(check_tls_expiry(probe))
    res.append(check_response_time(home))

    info = parse_html(home.body)
    asset = pick_asset(info, base + "/")
    asset_resp = map_resp = None
    if asset:
        asset_resp = f.get(asset, method="HEAD")
        if asset_resp.status in (403, 405, 501):
            asset_resp = f.get(asset, maxbytes=65536)
        if asset.endswith(".js"):
            map_resp = f.get(asset + ".map", method="HEAD")
            if map_resp.status in (403, 405, 501):
                map_resp = f.get(asset + ".map", maxbytes=4096)
    res.append(check_static_cache(asset, asset_resp))
    res.append(check_source_maps(asset, map_resp))
    res.append(check_security_headers(home))
    res.append(check_robots(robots, engines, urllib.parse.urlsplit(asset).path if asset else None))
    res.append(check_ai_bots(robots))
    res.append(check_sitemap(found))

    pages = [Page(base + "/", home)]
    for u in sample_urls:
        pages.append(Page(u, f.get(u, accept=html_acc)))
    res.append(check_sitemap_urls(pages))
    res.append(check_not_found(f.get(base + "/seo-ops-check-no-such-page-7f3a9", accept=html_acc)))
    res.append(check_titles(pages))
    res.append(check_descriptions(pages))
    res.append(check_h1(pages))
    res.append(check_lang_viewport(pages))
    res.append(check_open_graph(pages))
    res.append(check_image_preview(pages))
    res.append(check_images(pages))
    res.append(check_json_ld(pages))
    res.append(check_organization(pages[0]))
    res.append(check_website(pages[0]))
    res.append(check_product_offer(pages))
    res.append(check_self_ratings(pages))
    res.append(check_security_txt(f.get(base + "/.well-known/security.txt")))
    res.append(check_indexnow_key(key, f.get(base + "/" + key + ".txt") if key else None))
    res.append(check_llms_txt(f.get(base + "/llms.txt")))
    note = "pages sampled: %d, sitemap URLs: %d" % (len(pages), len(found["locs"]))
    return res, f.n, note


def to_markdown(host, res, n, note):
    cnt = {k: sum(1 for r in res if r["status"] == k) for k in STATUSES}
    lines = ["# seo_check: %s" % host, "",
             "OK %(OK)d, WARN %(WARN)d, FAIL %(FAIL)d, INFO %(INFO)d, SKIP %(SKIP)d. " % cnt
             + "Requests: %d. %s." % (n, note[0].upper() + note[1:]), "",
             "| Check | Status | Detail |", "|---|---|---|"]
    order = {"FAIL": 0, "WARN": 1, "INFO": 2, "OK": 3, "SKIP": 4}
    for r in sorted(res, key=lambda r: (order.get(r["status"], 9), r["id"])):
        lines.append("| %s | %s | %s |" % (r["id"], r["status"], r["detail"].replace("|", "\\|")))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- selftest

def _page(url, html, status=200, headers=None):
    h = {"content-type": "text/html"}
    h.update(headers or {})
    return Page(url, Resp(status, h, html, url))


GOOD_LD = ('<script type="application/ld+json">{"@graph":[{"@type":"Store","@id":"https://x.test/#org"},'
           '{"@type":"WebSite","@id":"https://x.test/#site"}]}</script>')


def _html(title="A good page title", desc="A page description of a normal length, longer than fifty characters.",
          canon="https://x.test/", og_image=True, extra="", ld=GOOD_LD, lang="en", h1="<h1>Head</h1>",
          robots="index, max-image-preview:large", viewport=True):
    img = '<meta property="og:image" content="https://x.test/i.jpg">' if og_image else ""
    vp = '<meta name="viewport" content="width=device-width">' if viewport else ""
    canon_tag = '<link rel="canonical" href="%s">' % canon if canon else ""
    lang_attr = ' lang="%s"' % lang if lang else ""
    return ('<html%s><head><title>%s</title><meta name="description" content="%s">%s%s'
            '<meta property="og:title" content="t">%s<meta name="twitter:card" content="summary">'
            '<meta name="robots" content="%s">%s</head><body>%s%s</body></html>'
            ) % (lang_attr, title, desc, canon_tag, vp, img, robots, ld, h1, extra)


def _ld(obj):
    return '<script type="application/ld+json">%s</script>' % json.dumps(obj)


def selftest():
    fails = []

    def want(name, result, allowed):
        st = result["status"]
        ok = st in allowed
        print("  %-4s %-16s %-44s -> %s" % ("ok" if ok else "MISS", result["id"], name, st))
        if not ok:
            fails.append("%s: %s gave %s, expected %s" % (name, result["id"], st, "/".join(allowed)))

    print("Positive controls (good input gives OK):")
    good = [_page("https://x.test/", _html()),
            _page("https://x.test/a", _html(title="Another title", canon="https://x.test/a"))]
    for fn in (check_sitemap_urls, check_titles, check_descriptions, check_h1, check_lang_viewport,
               check_open_graph, check_image_preview, check_json_ld, check_self_ratings):
        want("good pages", fn(good), ("OK",))
    want("good home", check_organization(good[0]), ("OK",))
    want("good home", check_website(good[0]), ("OK",))
    robots_ok = "User-agent: *\nAllow: /\nClean-param: utm_source\nSitemap: https://x.test/sitemap.xml\n"
    want("good robots", check_robots(Resp(200, {}, robots_ok), ["google", "yandex", "bing"], "/a.js"), ("OK",))
    want("good robots", check_ai_bots(Resp(200, {}, robots_ok)), ("OK",))
    sm_ok = "<urlset>" + "".join("<url><loc>https://x.test/%d</loc><lastmod>2026-11-%02d</lastmod></url>" % (i, i + 1)
                                 for i in range(5)) + "</urlset>"
    locs, lms, kids = sitemap_parse(sm_ok)
    want("good sitemap", check_sitemap({"url": "https://x.test/sitemap.xml", "resp": Resp(200, {"content-type": "application/xml"}, sm_ok),
                                        "locs": locs, "lastmods": lms, "children": kids, "error": "", "host": "x.test"},
                                       today=datetime.date(2026, 11, 25)), ("OK",))
    want("permanent redirects", check_redirects([("http", Resp(301, {"location": "https://x.test/"}, "", "http://x.test/"),
                                                  "https://x.test/", "main-http")]), ("OK",))
    want("unknown URL 404", check_not_found(Resp(404, {}, "")), ("OK",))
    want("TLS 90 days", check_tls_expiry(("h2", "TLSv1.3", 90, "")), ("OK",))
    product = _ld([{"@type": "Store", "@id": "a"}, {"@type": "Product", "offers": {
        "@type": "Offer", "price": "10", "priceCurrency": "EUR", "availability": "https://schema.org/InStock"}}])
    want("full Product", check_product_offer([_page("https://x.test/p", _html(ld=product))]), ("OK",))

    print("Defects (each check must give FAIL or WARN):")
    bad = ("FAIL", "WARN")
    want("unknown URL answers 200", check_not_found(Resp(200, {}, _html())), ("FAIL",))
    want("unknown URL redirects", check_not_found(Resp(302, {"location": "/"}, "", "https://x.test/zz")), ("WARN",))
    want("title of 90 characters", check_titles([_page("https://x.test/", _html(title="T" * 90))]), ("WARN",))
    want("no title", check_titles([_page("https://x.test/", _html(title=""))]), ("FAIL",))
    want("same titles", check_titles([_page("https://x.test/", _html()), _page("https://x.test/a", _html(canon="https://x.test/a"))]), ("WARN",))
    want("short description", check_descriptions([_page("https://x.test/", _html(desc="short"))]), ("WARN",))
    want("no h1", check_h1([_page("https://x.test/", _html(h1=""))]), ("WARN",))
    want("no lang", check_lang_viewport([_page("https://x.test/", _html(lang=""))]), ("WARN",))
    want("no viewport", check_lang_viewport([_page("https://x.test/", _html(viewport=False))]), ("WARN",))
    want("no og:image", check_open_graph([_page("https://x.test/", _html(og_image=False))]), ("WARN",))
    want("canonical to another URL", check_sitemap_urls([_page("https://x.test/", _html(canon="https://x.test/other"))]), ("FAIL",))
    want("noindex in sitemap URL", check_sitemap_urls([_page("https://x.test/", _html(robots="noindex"))]), ("FAIL",))
    want("noindex in header", check_sitemap_urls([_page("https://x.test/", _html(), headers={"x-robots-tag": "noindex"})]), ("FAIL",))
    want("sitemap URL redirects", check_sitemap_urls([_page("https://x.test/", "", status=301)]), ("FAIL",))
    want("no canonical", check_sitemap_urls([_page("https://x.test/", _html(canon=""))]), ("WARN",))
    want("broken JSON-LD", check_json_ld([_page("https://x.test/", _html(ld='<script type="application/ld+json">{bad</script>'))]), ("FAIL",))
    want("no organization", check_organization(_page("https://x.test/", _html(ld=""))), ("WARN",))
    want("no WebSite", check_website(_page("https://x.test/", _html(ld=_ld({"@type": "Store", "@id": "a"})))), ("WARN",))
    want("Product without price", check_product_offer([_page("https://x.test/", _html(
        ld=_ld([{"@type": "Product", "offers": {"@type": "Offer", "priceCurrency": "EUR"}}])))]), ("FAIL",))
    want("Product without availability", check_product_offer([_page("https://x.test/", _html(
        ld=_ld([{"@type": "Product", "offers": {"@type": "Offer", "price": "1", "priceCurrency": "EUR"}}])))]), ("WARN",))
    want("Product without offers", check_product_offer([_page("https://x.test/", _html(ld=_ld({"@type": "Product"})))]), ("WARN",))
    want("rating on the organization", check_self_ratings([_page("https://x.test/", _html(
        ld=_ld({"@type": "Store", "@id": "a", "aggregateRating": {"ratingValue": 5}})))]), ("WARN",))
    want("images without alt", check_images([_page("https://x.test/", _html(extra='<img src="a.webp">'))]), ("WARN",))
    want("robots blocks everything", check_robots(Resp(200, {}, "User-agent: *\nDisallow: /\n"), ["google"], None), ("FAIL",))
    want("robots blocks Yandex", check_robots(Resp(200, {}, "User-agent: Yandex\nDisallow: /\nUser-agent: *\nAllow: /\n"
                                                    "Sitemap: https://x.test/s.xml\n"), ["yandex"], None), ("FAIL",))
    want("robots blocks CSS and JS", check_robots(Resp(200, {}, "User-agent: *\nDisallow: /assets/\nSitemap: https://x.test/s.xml\n"),
                                                  ["google"], "/assets/app.js"), ("FAIL",))
    want("robots without Sitemap", check_robots(Resp(200, {}, "User-agent: *\nAllow: /\n"), ["google"], None), ("WARN",))
    want("robots answers 503", check_robots(Resp(503, {}, ""), ["google"], None), ("FAIL",))
    want("robots answers 429", check_robots(Resp(429, {}, ""), ["google"], None), ("FAIL",))
    want("search bot blocked", check_ai_bots(Resp(200, {}, "User-agent: OAI-SearchBot\nDisallow: /\n")), ("WARN",))
    sm_same = "<urlset>" + "".join("<url><loc>https://x.test/%d</loc><lastmod>2026-11-19</lastmod></url>" % i
                                   for i in range(5)) + "</urlset>"
    l2, m2, k2 = sitemap_parse(sm_same)
    want("same lastmod everywhere", check_sitemap({"url": "u", "resp": Resp(200, {"content-type": "application/xml"}, sm_same),
                                                   "locs": l2, "lastmods": m2, "children": k2, "error": "", "host": "x.test"},
                                                  today=datetime.date(2026, 11, 25)), ("WARN",))
    want("sitemap 404", check_sitemap({"url": "u", "resp": Resp(404, {}, ""), "locs": [], "lastmods": [], "children": [],
                                       "error": "", "host": "x.test"}), ("FAIL",))
    want("sitemap not XML", check_sitemap({"url": "u", "resp": Resp(200, {}, "<html>"), "locs": [], "lastmods": [], "children": [],
                                           "error": "syntax error", "host": "x.test"}), ("FAIL",))
    want("temporary redirect", check_redirects([("http", Resp(302, {"location": "https://x.test/"}, "", "http://x.test/"),
                                                 "https://x.test/", "main-http")]), ("WARN",))
    want("no redirect to the main host", check_redirects([("www", Resp(200, {}, "", "https://www.x.test/"),
                                                           "https://x.test/", "alt-host")]), ("FAIL",))
    want("slash duplicate", check_trailing_slash(Resp(200, {}, "", "https://x.test/a/"), "https://x.test/a", None), ("WARN",))
    want("open redirect", check_open_redirect(Resp(301, {"location": "https://example.com/"}, "", "https://x.test//example.com/"),
                                              "x.test"), ("FAIL",))
    want("static file without cache", check_static_cache("https://x.test/a.js", Resp(200, {"cache-control": "no-cache"})), ("WARN",))
    want("public source map", check_source_maps("https://x.test/a.js", Resp(200, {}, "")), ("WARN",))
    want("no HSTS", check_security_headers(Resp(200, {})), ("WARN",))
    want("no compression or HTTP/2", check_transport("", "", ("http/1.1", "TLSv1.3", 90, "")), ("WARN",))
    want("certificate ends in 3 days", check_tls_expiry(("h2", "TLSv1.3", 3, "")), ("FAIL",))
    want("certificate ends in 15 days", check_tls_expiry(("h2", "TLSv1.3", 15, "")), ("WARN",))
    want("slow response", check_response_time(Resp(200, {}, "", elapsed=3.5)), ("WARN",))
    want("no security.txt", check_security_txt(Resp(404, {})), ("WARN",))
    want("expired security.txt", check_security_txt(Resp(200, {}, "Contact: mailto:a@x.test\nExpires: 2020-01-01T00:00:00Z\n")), ("WARN",))
    want("IndexNow key mismatch", check_indexnow_key("abcdef0123456789", Resp(200, {}, "other")), ("FAIL",))
    want("IndexNow key missing", check_indexnow_key("abcdef0123456789", Resp(404, {}, "")), ("FAIL",))
    print()
    if fails:
        print("SELFTEST FAILED, checks stayed silent:")
        for x in fails:
            print("  - " + x)
        return 1
    print("SELFTEST PASSED: every planted defect was caught.")
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="External SEO check of a live site (standard library only).")
    ap.add_argument("host", nargs="?", help="canonical host, e.g. example.com or www.example.com")
    ap.add_argument("--pages", type=int, default=8, help="pages to sample: home plus sitemap URLs (default 8)")
    ap.add_argument("--json", help="write results as JSON to this file")
    ap.add_argument("--md", help="write a Markdown report to this file (for a CI job summary)")
    ap.add_argument("--engines", default="google,yandex,bing", help="search engines to check robots.txt for")
    ap.add_argument("--indexnow-key", default=os.environ.get("INDEXNOW_KEY"), help="IndexNow key (default: INDEXNOW_KEY)")
    ap.add_argument("--max-requests", type=int, default=60, help="request budget for one run (default 60)")
    ap.add_argument("--resolve", action="append", default=[], metavar="HOST=IP",
                    help="like curl --resolve: connect to IP for HOST, TLS and Host header stay the same")
    ap.add_argument("--fail-on", choices=("fail", "warn"), default="fail")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.host:
        ap.print_usage()
        print("error: give a host or --selftest")
        return 2
    if a.resolve:
        pins = dict(x.lower().split("=", 1) for x in a.resolve if "=" in x)
        _orig = socket.getaddrinfo

        def _pinned(h, *args, **kw):
            return _orig(pins.get(str(h).lower(), h), *args, **kw)
        socket.getaddrinfo = _pinned
    host = re.sub(r"^https?://", "", a.host.strip()).strip("/").split("/")[0].lower()
    engines = [e.strip().lower() for e in a.engines.split(",") if e.strip()]
    res, n, note = run(host, max(a.pages, 1), (a.indexnow_key or "").strip() or None, engines, max(a.max_requests, 10))
    if res is None:
        print("SITE UNREACHABLE: " + note)
        return 2
    print("seo_check %s (%s)" % (host, note))
    print("id | status | detail")
    for r in res:
        print("%-16s | %-4s | %s" % (r["id"], r["status"], r["detail"]))
    cnt = {k: sum(1 for r in res if r["status"] == k) for k in STATUSES}
    print("TOTAL: OK %(OK)d, WARN %(WARN)d, FAIL %(FAIL)d, INFO %(INFO)d, SKIP %(SKIP)d; " % cnt + "requests: %d" % n)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"host": host, "version": VERSION,
                       "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                       "requests": n, "note": note, "summary": cnt, "results": res}, fh, ensure_ascii=False, indent=1)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(host, res, n, note))
    if cnt["FAIL"] or (a.fail_on == "warn" and cnt["WARN"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
