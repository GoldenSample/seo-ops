#!/usr/bin/env python3
"""
seo_index.py: which published pages of a site are missing from the Yandex and Google index, and why.
Python 3.9+, standard library only.

Usage
  python seo_index.py example.com --keys keys.env [--pages crawl.json] [--google-max 100] [--gsc-property PROP]
                      [--json index.json] [--md index.md] [--fail-on fail|warn]

Published pages = the URLs of the sitemap (robots.txt Sitemap lines, else /sitemap.xml; index files are
followed) or, with --pages, the indexable 200 pages of a seo_crawl.py --json report.

Keys come only from the keys file named with --keys FILE (seo_keys.py; in Claude Code the plugin option
keys_file, in the cron a file the workflow writes from its secrets). The environment is never read for keys,
and the pack has none. Without a key the engine's line is SKIP and the exit code stays 0. Names in the file:
  Yandex  YANDEX_WEBMASTER_TOKEN  OAuth token of your app with the right webmaster:hostinfo
          (https://yandex.ru/dev/webmaster/doc/ru/tasks/how-to-get-oauth); it lives 6 months.
  Google  GSC_ACCESS_TOKEN, or GSC_CLIENT_ID + GSC_CLIENT_SECRET + GSC_REFRESH_TOKEN, exchanged at
          oauth2.googleapis.com for an access token (scope webmasters.readonly). GSC_PROPERTY or
          --gsc-property names the property (https://example.com/ or sc-domain:example.com); without it the
          site list of the account is searched.
Token values never reach the output: every printed line, the JSON and the Markdown pass a filter that
replaces them with ***. Requests carry a token only to the official API hosts below. SEO_OPS_API_BASE
(for tests) sends them to a mock instead and may point only at 127.0.0.1, localhost or ::1.

What is read
  Yandex Webmaster API v4 (api.webmaster.yandex.net): user, hosts, the pages in search (all, 100 per
  request, up to 50 000), search events (appeared, removed, with the reason) and robot crawl samples.
  Google Search Console (searchconsole.googleapis.com, www.googleapis.com): the site list and URL
  Inspection of each published URL up to --google-max (default 100; Google's quota is 2000 a day and
  600 a minute per site).

One line per check: id | OK, WARN, FAIL, INFO or SKIP | detail (the JSON and Markdown carry every item)
  published      where the list of published pages came from
  yandex-index   published pages in Yandex search; the missing ones with the reason Webmaster gives
  yandex-extra   pages in Yandex search that the site does not publish (old URLs, parameters, duplicates)
  google-index   inspected pages in the Google index; the missing ones with Google's coverage state

Exit codes
  0  no FAIL (with --fail-on warn: no FAIL and no WARN)
  1  FAIL (a token refused, the site not in the account) or WARN with --fail-on warn
  2  bad arguments, no published pages, the site or an API gives no answer

Source: https://github.com/GoldenSample/seo-ops (MIT).
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo_check as sc  # noqa: E402  (same scripts folder)
import seo_crawl as cr  # noqa: E402
import seo_keys  # noqa: E402

VERSION = "1.2.0"
UA = "seo-ops-index/%s (+https://github.com/GoldenSample/seo-ops)" % VERSION
YANDEX = "https://api.webmaster.yandex.net/v4"
GSC_INSPECT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
GSC_SITES = "https://www.googleapis.com/webmasters/v3/sites"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
API_HOSTS = ("api.webmaster.yandex.net", "searchconsole.googleapis.com", "www.googleapis.com", "oauth2.googleapis.com")
LOOPBACK = ("127.0.0.1", "localhost", "::1")
KEY_NAMES = ("YANDEX_WEBMASTER_TOKEN", "GSC_ACCESS_TOKEN", "GSC_CLIENT_ID", "GSC_CLIENT_SECRET", "GSC_REFRESH_TOKEN")
API_INTERVAL = 0.2      # at most 5 API requests per second (Google allows 600 inspections a minute per site)
PAGE = 100              # Webmaster samples per request (the API allows 1-100)
MAX_IN_SEARCH = 50000   # the Webmaster API returns at most 50 000 URLs
MAX_EVENTS = 2000
MAX_SAMPLES = 2000
TIMEOUT = 30
R = sc.R
RI = cr.RI
STATUSES = sc.STATUSES


class Unreachable(Exception):
    pass


class Secrets:
    """Token values to hide: as they are, percent-encoded and form-encoded."""

    def __init__(self):
        self.values = set()

    def add(self, v):
        v = (v or "").strip()
        if len(v) >= 4:
            self.values.add(v)

    def scrub(self, s):
        s = str(s)
        for v in sorted(self.values, key=len, reverse=True):
            for form in {v, urllib.parse.quote(v, safe=""), urllib.parse.quote_plus(v)}:
                s = s.replace(form, "***")
        return s


def api_base_problem():
    base = os.environ.get("SEO_OPS_API_BASE", "").strip()
    if not base:
        return ""
    p = urllib.parse.urlsplit(base)
    if p.scheme not in ("http", "https") or (p.hostname or "").lower() not in LOOPBACK:
        return ("SEO_OPS_API_BASE is for tests and may point only at 127.0.0.1, localhost or ::1; "
                "unset it to use the real APIs")
    return ""


def api_error(status, js):
    parts = [str(status)]
    if isinstance(js, dict):
        e = js.get("error")
        if isinstance(e, dict):
            parts += [str(e.get("status") or ""), str(e.get("message") or "")]
        elif e:
            parts += [str(e), str(js.get("error_description") or "")]
        if js.get("error_code"):
            parts += [str(js["error_code"]), str(js.get("error_message") or "")]
    return " ".join(p for p in parts if p)[:300]


class Api:
    def __init__(self, secrets):
        self.secrets = secrets
        self.base = os.environ.get("SEO_OPS_API_BASE", "").strip().rstrip("/")
        self.opener = urllib.request.build_opener(sc._NoRedirect())  # a redirect must not carry a token away
        self.calls = 0
        self.last = 0.0

    def url(self, u):
        p = urllib.parse.urlsplit(u)
        if p.scheme != "https" or p.netloc not in API_HOSTS:
            raise ValueError("not an official API host: %s" % p.netloc)
        if not self.base:
            return u
        return self.base + "/" + p.netloc + p.path + ("?" + p.query if p.query else "")

    def call(self, method, u, auth=None, body=None, form=None):
        """(status, parsed JSON or None, error text). Status 0 means no answer."""
        wait = API_INTERVAL - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.calls += 1
        headers = {"User-Agent": UA, "Accept": "application/json"}
        data = None
        if auth:
            headers["Authorization"] = auth
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(form).encode("ascii")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.url(u), data=data, method=method, headers=headers)
        try:
            r = self.opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            r = e
        except Exception as e:  # DNS, TLS, timeout, refused
            return 0, None, self.secrets.scrub("%s: %s" % (type(e).__name__, e))
        try:
            raw = r.read(5_000_000)
        except Exception as e:
            return 0, None, self.secrets.scrub("read: %s" % e)
        finally:
            try:
                r.close()
            except Exception:
                pass
        status = getattr(r, "status", None) or r.code
        try:
            js = json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            js = None
        return status, js, self.secrets.scrub(api_error(status, js) if status >= 300 else "")


# ---------------------------------------------------------------- published pages

def key(u):
    return sc.norm(cr.ascii_url((u or "").strip())) if u else ""


def published_pages(origin, pages_json):
    """(urls, note, error)."""
    base = "%s://%s" % origin
    if pages_json:
        try:
            with open(pages_json, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            return [], "", "cannot read --pages %s: %s" % (pages_json, e)
        if (data.get("origin") or "").rstrip("/").lower() != base:
            return [], "", "--pages %s is a crawl of %s, not of %s" % (pages_json, data.get("origin"), base)
        urls = [p["url"] for p in data.get("pages", []) if isinstance(p, dict) and p.get("status") == 200
                and p.get("indexable") and p.get("kind") == "html"]
        if not urls:
            return [], "", "--pages %s has no indexable 200 page" % pages_json
        return urls, "%d indexable 200 pages from %s (crawl of %s)" % (
            len(urls), os.path.basename(pages_json), data.get("date", "?")), ""
    c = cr.Crawl(origin, max_pages=1, fetcher=sc.Fetcher(cr.MAX_SITEMAPS + 10, ua=UA))
    robots = c.fetch_robots()
    if robots.status == 0:
        return [], "", "SITE UNREACHABLE: %s/robots.txt gives no answer (%s)" % (base, robots.error)
    c.read_sitemaps()
    if not c.sitemap_found or not c.sitemap:
        note = "; ".join(c.sitemap_notes) or "no sitemap"
        return [], "", "no published URLs: no readable sitemap on %s (%s); pass --pages crawl.json" % (base, note)
    note = "%d URLs from the sitemap (%d files)" % (len(c.sitemap), c.sitemap_files)
    if c.sitemap_foreign:
        note += "; %d URLs on another host or scheme left out" % len(c.sitemap_foreign)
    return list(c.sitemap.values()), note, ""


def path_of(origin, u):
    p = urllib.parse.urlsplit(u or "")
    if p.scheme.lower() == origin[0] and p.netloc.lower() == origin[1]:
        s = (p.path or "/") + ("?" + p.query if p.query else "")
    else:
        s = u or ""
    try:
        return urllib.parse.unquote(s, errors="strict")
    except UnicodeDecodeError:
        return s


# ---------------------------------------------------------------- Yandex

def paged(api, url, auth, cap):
    """(samples, count, capped, error) of a Webmaster samples list."""
    out, count, offset = [], 0, 0
    while True:
        st, js, err = api.call("GET", "%s?offset=%d&limit=%d" % (url, offset, PAGE), auth)
        if st == 0:
            raise Unreachable("Yandex Webmaster API: " + err)
        if st != 200 or not isinstance(js, dict):
            return out, count, False, err or "%d without JSON" % st
        count = int(js.get("count") or 0)
        batch = js.get("samples") or []
        out += [s for s in batch if isinstance(s, dict)]
        offset += PAGE
        if not batch or offset >= count:
            return out, count, False, ""
        if offset >= cap:
            return out, count, True, ""


def latest(items, date_field):
    best = {}
    for s in items:
        k = key(s.get("url"))
        if k and (k not in best or (s.get(date_field) or "") > (best[k].get(date_field) or "")):
            best[k] = s
    return best


def yandex_reason(e, s):
    if e and e.get("event") == "REMOVED_FROM_SEARCH":
        r = "removed from search %s" % (e.get("event_date") or "")[:10]
        if e.get("excluded_url_status"):
            r += ": " + str(e["excluded_url_status"])
        if e.get("bad_http_status"):
            r += " (HTTP %s)" % e["bad_http_status"]
        if e.get("target_url"):
            r += " -> %s" % e["target_url"]
        return r
    if s:
        r = "robot crawled it %s: %s" % ((s.get("access_date") or "")[:10], s.get("status") or "?")
        if s.get("http_code"):
            r += " %s" % s["http_code"]
        if s.get("status") == "HTTP_2XX":
            r += ", not in search yet"
        return r
    if e and e.get("event") == "APPEARED_IN_SEARCH":
        return "appeared in search %s, not in the search list now" % (e.get("event_date") or "")[:10]
    return "no Yandex data for this URL: not crawled yet, or older than the samples"


def yandex(api, token, origin, published, per):
    auth = "OAuth " + token
    st, js, err = api.call("GET", YANDEX + "/user", auth)
    if st == 0:
        raise Unreachable("Yandex Webmaster API: " + err)
    if st != 200 or not isinstance(js, dict) or not js.get("user_id"):
        return [R("yandex-index", "FAIL", "the Webmaster API refused the token (%s): issue a new one at "
                  "oauth.yandex.ru, it lives 6 months" % err)]
    uid = js["user_id"]
    st, js, err = api.call("GET", "%s/user/%s/hosts" % (YANDEX, uid), auth)
    if st == 0:
        raise Unreachable("Yandex Webmaster API: " + err)
    if st != 200 or not isinstance(js, dict):
        return [R("yandex-index", "FAIL", "the Webmaster API gave no host list (%s)" % err)]
    want = "%s://%s" % origin
    hosts = [h for h in js.get("hosts") or [] if isinstance(h, dict)]
    host = next((h for h in hosts if (h.get("ascii_host_url") or "").rstrip("/").lower() == want), None)
    if host is None:
        bare = sc.alt_host(origin[1]) if origin[1].startswith("www.") else origin[1]
        variants = [h.get("ascii_host_url") for h in hosts
                    if urllib.parse.urlsplit(h.get("ascii_host_url") or "").netloc.lower() in (bare, "www." + bare)]
        det = "%s/ is not in this Webmaster account (%d hosts there)" % (want, len(hosts))
        if variants:
            det += "; it has %s: pass the host the way Webmaster shows it" % ", ".join(variants)
        return [R("yandex-index", "FAIL", det)]
    if not host.get("verified"):
        return [R("yandex-index", "FAIL", "%s/ is in the account but not verified: confirm the rights in Webmaster" % want)]
    hb = "%s/user/%s/hosts/%s" % (YANDEX, uid, urllib.parse.quote(str(host.get("host_id")), safe=":"))
    notes = []
    mirror = host.get("main_mirror")
    if isinstance(mirror, dict) and (mirror.get("ascii_host_url") or "").rstrip("/").lower() not in ("", want):
        notes.append("Yandex treats %s as the main mirror" % mirror.get("ascii_host_url"))
    found, count, capped, err = paged(api, hb + "/search-urls/in-search/samples", auth, MAX_IN_SEARCH)
    if err:
        return [R("yandex-index", "FAIL", "the list of pages in search did not load (%s)" % err)]
    if capped:
        notes.append("read %d of %d pages in search" % (len(found), count))
    events, _n, ecap, eerr = paged(api, hb + "/search-urls/events/samples", auth, MAX_EVENTS)
    samples, _n, scap, serr = paged(api, hb + "/indexing/samples", auth, MAX_SAMPLES)
    if eerr:
        notes.append("search events did not load (%s)" % eerr)
    if serr:
        notes.append("crawl samples did not load (%s)" % serr)
    in_search = {key(s.get("url")): s for s in found if s.get("url")}
    ev, sm = latest(events, "event_date"), latest(samples, "access_date")
    pub = [(key(u), u) for u in published]
    pub_keys = {k for k, _ in pub}
    missing = []
    for k, u in pub:
        row = per.setdefault(k, {"url": u})
        if k in in_search:
            row["yandex"] = True
            continue
        reason = yandex_reason(ev.get(k), sm.get(k))
        row["yandex"], row["yandex_reason"] = False, reason
        missing.append("%s: %s" % (path_of(origin, u), reason))
    extra = [path_of(origin, s.get("url")) for k, s in in_search.items() if k not in pub_keys]
    tail = ("; " + "; ".join(notes)) if notes else ""
    n = len(pub)
    if missing:
        res = [RI("yandex-index", "WARN", "%d of %d published pages are in Yandex search; missing: %s%s"
                  % (n - len(missing), n, cr.short(missing, 3), tail), missing)]
    else:
        res = [R("yandex-index", "OK", "all %d published pages are in Yandex search%s" % (n, tail))]
    if capped:
        res.append(R("yandex-extra", "SKIP", "the search list was read only in part"))
    elif extra:
        res.append(RI("yandex-extra", "INFO", "%d pages in Yandex search are not published (not in the sitemap or "
                      "the crawl): %s" % (len(extra), cr.short(extra)), extra))
    else:
        res.append(R("yandex-extra", "OK", "Yandex search holds no page beyond the published ones"))
    return res


# ---------------------------------------------------------------- Google

def google_token(api, secrets, keys):
    """(token, failure row); (None, None) when no Google key is set."""
    tok = keys.get("GSC_ACCESS_TOKEN", "").strip()
    if tok:
        return tok, None
    trio = [keys.get(k, "").strip() for k in ("GSC_CLIENT_ID", "GSC_CLIENT_SECRET", "GSC_REFRESH_TOKEN")]
    if not any(trio):
        return None, None
    if not all(trio):
        return None, R("google-index", "FAIL", "set all three of GSC_CLIENT_ID, GSC_CLIENT_SECRET and "
                       "GSC_REFRESH_TOKEN, or GSC_ACCESS_TOKEN, in the keys file")
    st, js, err = api.call("POST", GOOGLE_TOKEN, form={"client_id": trio[0], "client_secret": trio[1],
                                                       "grant_type": "refresh_token", "refresh_token": trio[2]})
    if st == 0:
        raise Unreachable("Google OAuth: " + err)
    if st != 200 or not isinstance(js, dict) or not js.get("access_token"):
        return None, R("google-index", "FAIL", "Google refused the refresh token (%s): issue a new one" % err)
    secrets.add(js["access_token"])
    return js["access_token"], None


def google_property(api, auth, origin, prop):
    if prop:
        return prop, None
    st, js, err = api.call("GET", GSC_SITES, auth)
    if st == 0:
        raise Unreachable("Search Console API: " + err)
    if st != 200 or not isinstance(js, dict):
        return None, R("google-index", "FAIL", "Search Console refused the token (%s)" % err)
    urls = [e.get("siteUrl") for e in js.get("siteEntry") or []
            if isinstance(e, dict) and e.get("permissionLevel") != "siteUnverifiedUser"]
    host = origin[1].split(":")[0]
    bare = host[4:] if host.startswith("www.") else host
    for cand in ("%s://%s/" % origin, "sc-domain:" + bare):
        if cand in urls:
            return cand, None
    return None, R("google-index", "FAIL", "no verified Search Console property for %s://%s/ in this account (%d "
                   "there): add it, or name it with --gsc-property" % (origin[0], origin[1], len(urls)))


def google_reason(isr, url):
    parts = [isr.get("coverageState") or isr.get("verdict") or "no index status"]
    if isr.get("pageFetchState") and isr["pageFetchState"] != "SUCCESSFUL":
        parts.append("fetch " + isr["pageFetchState"])
    if isr.get("indexingState") and isr["indexingState"] != "INDEXING_ALLOWED":
        parts.append(isr["indexingState"])
    if isr.get("robotsTxtState") == "DISALLOWED":
        parts.append("robots.txt DISALLOWED")
    if isr.get("googleCanonical") and key(isr["googleCanonical"]) != key(url):
        parts.append("Google canonical " + isr["googleCanonical"])
    return "; ".join(parts)


def google(api, secrets, keys, have_file, prop, origin, published, google_max, per):
    tok, fail = google_token(api, secrets, keys)
    if fail:
        return [fail]
    if not tok:
        return [R("google-index", "SKIP", ("no GSC_ACCESS_TOKEN or GSC_CLIENT_ID + GSC_CLIENT_SECRET + "
                  "GSC_REFRESH_TOKEN in the keys file" if have_file else "no keys file (--keys FILE)")
                  + ": Search Console is not asked")]
    auth = "Bearer " + tok
    prop, fail = google_property(api, auth, origin, prop)
    if fail:
        return [fail]
    todo = published[:google_max]
    missing, errors, done, quota = [], [], 0, False
    for u in todo:
        st, js, err = api.call("POST", GSC_INSPECT, auth, body={"inspectionUrl": u, "siteUrl": prop,
                                                                "languageCode": "en-US"})
        if st == 0:
            raise Unreachable("Search Console API: " + err)
        if st == 429:
            quota = True
            break
        if st in (401, 403):
            return [R("google-index", "FAIL", "Search Console refused the inspection for %s (%s)" % (prop, err))]
        if st != 200 or not isinstance(js, dict):
            errors.append("%s: %s" % (path_of(origin, u), err))
            continue
        done += 1
        isr = (js.get("inspectionResult") or {}).get("indexStatusResult") or {}
        row = per.setdefault(key(u), {"url": u})
        row["google_verdict"] = isr.get("verdict")
        if isr.get("verdict") == "PASS":
            row["google"] = True
            continue
        reason = google_reason(isr, u)
        row["google"], row["google_reason"] = False, reason
        missing.append("%s: %s" % (path_of(origin, u), reason))
    notes = ["property %s" % prop]
    if len(published) > len(todo):
        notes.append("inspected the first %d of %d published pages (--google-max; quota 2000 a day per site)"
                     % (len(todo), len(published)))
    if quota:
        notes.append("Google answered 429 after %d inspections: the quota is spent, the rest was not inspected" % done)
    if errors:
        notes.append("%d inspections failed: %s" % (len(errors), cr.short(errors, 2)))
    tail = "; " + "; ".join(notes)
    if missing:
        return [RI("google-index", "WARN", "%d of %d inspected pages are not in the Google index: %s%s"
                   % (len(missing), done, cr.short(missing, 3), tail), missing + errors)]
    if not done:
        return [RI("google-index", "WARN", "no page was inspected" + tail, errors)]
    return [R("google-index", "OK" if not (quota or errors) else "WARN",
              "all %d inspected pages are in the Google index%s" % (done, tail))]


# ---------------------------------------------------------------- output

def to_markdown(host, res, scrub):
    cnt = {k: sum(1 for r in res if r["status"] == k) for k in STATUSES}
    lines = ["# seo_index: %s" % host, "",
             "OK %(OK)d, WARN %(WARN)d, FAIL %(FAIL)d, INFO %(INFO)d, SKIP %(SKIP)d." % cnt, "",
             "| Check | Status | Detail |", "|---|---|---|"]
    for r in res:
        lines.append("| %s | %s | %s |" % (r["id"], r["status"], r["detail"].replace("|", "\\|")))
    for r in res:
        if r.get("items") and r["status"] in ("WARN", "FAIL", "INFO"):
            lines += ["", "## %s (%s)" % (r["id"], r["status"]), ""]
            lines += ["- " + x.replace("|", "\\|") for x in r["items"][:200]]
            if len(r["items"]) > 200:
                lines.append("- and %d more in the JSON report" % (len(r["items"]) - 200))
    return scrub("\n".join(lines) + "\n")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Published pages missing from the Yandex and Google index (keys only "
                                             "from --keys FILE).")
    ap.add_argument("site", help="canonical host, e.g. example.com, or an origin such as https://www.example.com")
    ap.add_argument("--pages", help="a seo_crawl.py --json report: use its indexable 200 pages instead of the sitemap")
    ap.add_argument("--google-max", type=int, default=100, help="URL Inspection requests at most (default 100)")
    ap.add_argument("--json", help="write the results and the per-page verdicts as JSON")
    ap.add_argument("--md", help="write a Markdown report (for a CI job summary or an issue)")
    ap.add_argument("--fail-on", choices=("fail", "warn"), default="fail")
    ap.add_argument("--keys", metavar="FILE", help="keys file (seo_keys.py) with YANDEX_WEBMASTER_TOKEN and the "
                    "GSC_* keys; the environment is not read for keys")
    ap.add_argument("--gsc-property", help="Search Console property (else GSC_PROPERTY of the keys file, else "
                    "found in the account)")
    a = ap.parse_args(argv)
    have_file = seo_keys.resolve_path(a.keys) is not None
    try:
        keys = seo_keys.keys_from_args(a.keys)
    except seo_keys.KeysFileError as e:
        print("error: %s" % e)
        return 2
    secrets = Secrets()
    for k in KEY_NAMES:
        secrets.add(keys.get(k, ""))

    def say(s=""):
        print(secrets.scrub(s))
    problem = api_base_problem()
    if problem:
        say("error: " + problem)
        return 2
    if a.google_max < 1:
        say("error: --google-max must be 1 or more")
        return 2
    try:
        origin = cr.parse_site(a.site)
    except ValueError as e:
        say("error: %s" % e)
        return 2
    published, note, err = published_pages(origin, a.pages)
    if err:
        say(err)
        return 2
    api = Api(secrets)
    per = {}
    res = [R("published", "INFO", note)]
    try:
        ytok = keys.get("YANDEX_WEBMASTER_TOKEN", "").strip()
        if ytok:
            res += yandex(api, ytok, origin, published, per)
        else:
            res.append(R("yandex-index", "SKIP", ("no YANDEX_WEBMASTER_TOKEN in the keys file" if have_file
                                                  else "no keys file (--keys FILE)") + ": Yandex Webmaster is not asked"))
        prop = (a.gsc_property or keys.get("GSC_PROPERTY") or "").strip()
        res += google(api, secrets, keys, have_file, prop, origin, published, a.google_max, per)
    except Unreachable as e:
        say("API UNREACHABLE: %s" % e)
        return 2
    say("seo_index %s (%d published pages, %d API requests)" % (origin[1], len(published), api.calls))
    say("id | status | detail")
    for r in res:
        say("%-13s | %-4s | %s" % (r["id"], r["status"], r["detail"]))
    cnt = {k: sum(1 for r in res if r["status"] == k) for k in STATUSES}
    say("TOTAL: OK %(OK)d, WARN %(WARN)d, FAIL %(FAIL)d, INFO %(INFO)d, SKIP %(SKIP)d" % cnt)
    if a.json:
        doc = {"host": origin[1], "origin": "%s://%s" % origin, "version": VERSION,
               "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "api_requests": api.calls, "summary": cnt, "results": res,
               "pages": [per.get(key(u), {"url": u}) for u in published]}
        with open(a.json, "w", encoding="utf-8") as fh:
            fh.write(secrets.scrub(json.dumps(doc, ensure_ascii=False, indent=1)))
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(origin[1], res, secrets.scrub))
    if cnt["FAIL"] or (a.fail_on == "warn" and cnt["WARN"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
