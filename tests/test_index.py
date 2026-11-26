"""Tests for scripts/seo_index.py against a local mock of the site, Yandex Webmaster v4 and Search Console.
Standard library only; nothing leaves 127.0.0.1. Response shapes follow the API reference pages
(Webmaster: user, hosts, in-search samples, events samples, indexing samples, errors; Search Console:
urlInspection.index.inspect, sites.list; Google OAuth token exchange).

Run: python tests/test_index.py [path/to/seo_index.py]
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import contextlib
import http.server
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "seo_index.py")
spec = importlib.util.spec_from_file_location("seo_index", TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.API_INTERVAL = 0.0
m.sc.MIN_INTERVAL = 0.0

total, bad = 0, []
YTOK = "y0_AgAAAAB-test-webmaster-token-123"
CID, CSECRET, RTOKEN = "cid-test-77.apps.googleusercontent.com", "GOCSPX-test-secret-xyz", "1//test-refresh-abc"
ATOK = "ya29.test-access-456"
DIRECT = "ya29.test-direct-789"
WRONG = "y0_wrong-token-999"
ALL_SECRETS = (YTOK, CSECRET, RTOKEN, ATOK, DIRECT, WRONG)


def check(name, cond):
    global total
    total += 1
    if not cond:
        bad.append(name)
        print("FAIL", name)


class Mock:
    """One server: the site at /, each API under /<api host>/..."""

    def __init__(self):
        self.log = []
        self.cfg = {}
        self.reset()
        mock = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                mock.handle(self, "GET")

            def do_POST(self):
                mock.handle(self, "POST")

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        self.o = "http://127.0.0.1:%d" % self.port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def reset(self):
        self.log.clear()
        self.cfg = {"hosts": "ours", "verified": True, "inspect_429_after": None, "user_redirect": False,
                    "insearch_429": False, "sites": "prefix"}

    def u(self, p):
        return self.o + p

    def handle(self, h, method):
        p = urllib.parse.urlsplit(h.path)
        n = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(n).decode("utf-8") if n else ""
        auth = h.headers.get("Authorization", "")
        self.log.append((method, p.path, p.query, auth, body))
        seg = p.path.split("/")
        status, payload, ctype, extra = 404, {"error": "not found"}, "application/json", {}
        if len(seg) > 1 and seg[1] in m.API_HOSTS:
            status, payload, extra = self.api(seg[1], "/" + "/".join(seg[2:]), method, urllib.parse.parse_qs(p.query),
                                              auth, body)
        elif p.path == "/robots.txt":
            status, payload, ctype = 200, "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % self.o, "text/plain"
        elif p.path == "/sitemap.xml":
            locs = "".join("<url><loc>%s</loc></url>" % self.u(x) for x in ("/", "/a", "/b", "/c", "/d", "/e"))
            status, payload, ctype = 200, "<urlset>%s</urlset>" % locs, "application/xml"
        data = (payload if isinstance(payload, str) else json.dumps(payload)).encode("utf-8")
        h.send_response(status)
        h.send_header("Content-Type", ctype)
        for k, v in extra.items():
            h.send_header(k, v)
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    def sliced(self, items, q):
        off, lim = int(q.get("offset", ["0"])[0]), int(q.get("limit", ["50"])[0])
        return {"count": len(items), "samples": items[off:off + lim]}

    def api(self, host, path, method, q, auth, body):
        if host == "api.webmaster.yandex.net":
            if auth != "OAuth " + YTOK:
                return 403, {"error_code": "INVALID_OAUTH_TOKEN", "error_message": "bad token %s" % auth}, {}
            if path == "/v4/user":
                if self.cfg["user_redirect"]:
                    return 302, {}, {"Location": self.u("/steal")}
                return 200, {"user_id": 4242}, {}
            if path == "/v4/user/4242/hosts":
                ours = {"host_id": "http:127.0.0.1:%d" % self.port, "ascii_host_url": self.u("/"),
                        "unicode_host_url": self.u("/"), "verified": self.cfg["verified"]}
                other = {"host_id": "https:other.test:443", "ascii_host_url": "https://other.test/",
                         "unicode_host_url": "https://other.test/", "verified": True}
                return 200, {"hosts": [ours, other] if self.cfg["hosts"] == "ours" else [other]}, {}
            hb = "/v4/user/4242/hosts/http:127.0.0.1:%d" % self.port
            if path == hb + "/search-urls/in-search/samples":
                if self.cfg["insearch_429"]:
                    return 429, {"error_code": "QUOTA_EXCEEDED", "error_message": "daily quota"}, {}
                items = [{"url": self.u(x), "last_access": "2026-11-20T10:00:00+03:00", "title": x}
                         for x in ("/", "/a", "/b", "/old")]
                return 200, self.sliced(items, q), {}
            if path == hb + "/search-urls/events/samples":
                items = [{"url": self.u("/c"), "title": "c", "event_date": "2026-11-02T10:00:00+03:00",
                          "last_access": "2026-11-01T10:00:00+03:00", "event": "REMOVED_FROM_SEARCH",
                          "excluded_url_status": "NOT_CANONICAL", "target_url": self.u("/a")},
                         {"url": self.u("/a"), "title": "a", "event_date": "2026-10-01T10:00:00+03:00",
                          "last_access": "2026-10-01T10:00:00+03:00", "event": "APPEARED_IN_SEARCH"}]
                return 200, self.sliced(items, q), {}
            if path == hb + "/indexing/samples":
                items = [{"status": "HTTP_4XX", "http_code": 404, "url": self.u("/d"),
                          "access_date": "2026-11-20T08:00:00+03:00"},
                         {"status": "HTTP_2XX", "http_code": 200, "url": self.u("/b"),
                          "access_date": "2026-11-19T08:00:00+03:00"}]
                return 200, self.sliced(items, q), {}
            return 404, {"error_code": "HOST_NOT_VERIFIED", "error_message": path}, {}
        if host == "oauth2.googleapis.com" and path == "/token" and method == "POST":
            f = urllib.parse.parse_qs(body)
            if (f.get("client_id") == [CID] and f.get("client_secret") == [CSECRET] and f.get("refresh_token") == [RTOKEN]
                    and f.get("grant_type") == ["refresh_token"]):
                return 200, {"access_token": ATOK, "expires_in": 3599, "token_type": "Bearer",
                             "scope": "https://www.googleapis.com/auth/webmasters.readonly"}, {}
            return 400, {"error": "invalid_grant", "error_description": "Bad Request"}, {}
        if auth not in ("Bearer " + ATOK, "Bearer " + DIRECT):
            return 401, {"error": {"code": 401, "message": "Request had invalid authentication credentials.",
                                   "status": "UNAUTHENTICATED"}}, {}
        if host == "www.googleapis.com" and path == "/webmasters/v3/sites":
            sites = {"prefix": [{"siteUrl": self.u("/"), "permissionLevel": "siteOwner"}],
                     "domain": [{"siteUrl": "sc-domain:127.0.0.1", "permissionLevel": "siteFullUser"}],
                     "unverified": [{"siteUrl": self.u("/"), "permissionLevel": "siteUnverifiedUser"}]}
            return 200, {"siteEntry": sites[self.cfg["sites"]]}, {}
        if host == "searchconsole.googleapis.com" and path == "/v1/urlInspection/index:inspect" and method == "POST":
            n = sum(1 for x in self.log if x[1].endswith("index:inspect"))
            if self.cfg["inspect_429_after"] is not None and n > self.cfg["inspect_429_after"]:
                return 429, {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}, {}
            b = json.loads(body)
            pth = urllib.parse.urlsplit(b["inspectionUrl"]).path
            if self.cfg.get("echo_google") and pth == "/e":
                return 500, {"error": {"code": 500, "message": "backend saw header %s" % auth,
                                       "status": "INTERNAL"}}, {}
            base = {"verdict": "PASS", "coverageState": "Submitted and indexed", "robotsTxtState": "ALLOWED",
                    "indexingState": "INDEXING_ALLOWED", "pageFetchState": "SUCCESSFUL",
                    "googleCanonical": b["inspectionUrl"], "userCanonical": b["inspectionUrl"]}
            if pth == "/b":
                base.update(verdict="NEUTRAL", coverageState="Discovered - currently not indexed")
                base.pop("googleCanonical")
            elif pth == "/c":
                base.update(verdict="FAIL", coverageState="Duplicate, Google chose different canonical than user",
                            googleCanonical=self.u("/a"))
            elif pth == "/d":
                base.update(verdict="FAIL", coverageState="Not found (404)", pageFetchState="NOT_FOUND")
            return 200, {"inspectionResult": {"inspectionResultLink": "https://search.google.com/x",
                                              "indexStatusResult": base}}, {}
        return 404, {"error": {"code": 404, "message": "no such method", "status": "NOT_FOUND"}}, {}

    def api_calls(self):
        return [x for x in self.log if x[1].split("/")[1] in m.API_HOSTS]


@contextlib.contextmanager
def env(**kw):
    keys = set(m.SECRET_ENV) | {"SEO_OPS_API_BASE", "GSC_PROPERTY"}
    old = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in kw.items() if v is not None})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run(args, **kw):
    out = io.StringIO()
    with env(**kw), contextlib.redirect_stdout(out):
        code = m.main(args)
    return code, out.getvalue()


def rows(text):
    got = {}
    for line in text.splitlines():
        parts = [x.strip() for x in line.split("|", 2)]
        if len(parts) == 3 and parts[1] in m.STATUSES:
            got[parts[0]] = (parts[1], parts[2])
    return got


mock = Mock()
tmp = tempfile.mkdtemp(prefix="seo_index_test_")
JS, MD = os.path.join(tmp, "index.json"), os.path.join(tmp, "index.md")
BOTH = dict(YANDEX_WEBMASTER_TOKEN=YTOK, GSC_CLIENT_ID=CID, GSC_CLIENT_SECRET=CSECRET, GSC_REFRESH_TOKEN=RTOKEN,
            SEO_OPS_API_BASE=mock.o)

# 1. no keys: both SKIP, exit 0, no API request at all
mock.reset()
code, out = run([mock.o], SEO_OPS_API_BASE=mock.o)
r = rows(out)
check("no keys: exit 0", code == 0)
check("no keys: yandex SKIP", r.get("yandex-index", ("",))[0] == "SKIP")
check("no keys: google SKIP", r.get("google-index", ("",))[0] == "SKIP")
check("no keys: no API request", mock.api_calls() == [])
check("no keys: published from the sitemap", r.get("published", ("", ""))[1].startswith("6 URLs from the sitemap"))

# 2. both engines with keys
mock.reset()
code, out = run([mock.o, "--json", JS, "--md", MD], **BOTH)
r = rows(out)
with open(JS, encoding="utf-8") as fh:
    js_text = fh.read()
doc = json.loads(js_text)
with open(MD, encoding="utf-8") as fh:
    md_text = fh.read()
res = {x["id"]: x for x in doc["results"]}
check("keys: exit 0 (WARN only)", code == 0)
check("keys: yandex WARN", r.get("yandex-index", ("",))[0] == "WARN")
check("keys: yandex detail", r.get("yandex-index", ("", ""))[1].startswith("3 of 6 published pages are in Yandex search"))
check("keys: yandex missing with reasons", res["yandex-index"].get("items") == [
    "/c: removed from search 2026-11-02: NOT_CANONICAL -> %s" % mock.u("/a"),
    "/d: robot crawled it 2026-11-20: HTTP_4XX 404",
    "/e: no Yandex data for this URL: not crawled yet, or older than the samples"])
check("keys: yandex extra", res["yandex-extra"]["status"] == "INFO" and res["yandex-extra"].get("items") == ["/old"])
check("keys: google WARN", res["google-index"]["status"] == "WARN"
      and res["google-index"]["detail"].startswith("3 of 6 inspected pages are not in the Google index"))
check("keys: google missing with reasons", res["google-index"].get("items") == [
    "/b: Discovered - currently not indexed",
    "/c: Duplicate, Google chose different canonical than user; Google canonical %s" % mock.u("/a"),
    "/d: Not found (404); fetch NOT_FOUND"])
check("keys: property from the site list", ("property %s/" % mock.o) in res["google-index"]["detail"])
pages = {p["url"]: p for p in doc["pages"]}
check("keys: per-page verdicts", pages[mock.u("/")].get("yandex") is True and pages[mock.u("/")].get("google") is True
      and pages[mock.u("/d")].get("yandex") is False and pages[mock.u("/d")].get("google") is False)
check("keys: markdown sections", "## yandex-index (WARN)" in md_text and "## google-index (WARN)" in md_text)
calls = mock.api_calls()
check("keys: Yandex header is OAuth", all(a == "OAuth " + YTOK for _, p, _, a, _ in calls
                                          if p.startswith("/api.webmaster.yandex.net/")))
check("keys: Google header is Bearer from the exchange",
      all(a == "Bearer " + ATOK for _, p, _, a, _ in calls if "searchconsole" in p or "/webmasters/v3/" in p))
check("keys: one token exchange", sum(1 for x in calls if x[1].endswith("/token")) == 1)
check("keys: inspect body", all(json.loads(b)["siteUrl"] == mock.u("/") and json.loads(b)["languageCode"] == "en-US"
                                for _, p, _, _, b in calls if p.endswith("index:inspect")))
check("keys: six inspections", sum(1 for x in calls if x[1].endswith("index:inspect")) == 6)
blob = out + js_text + md_text
check("keys: no secret in stdout, JSON or Markdown", not any(s in blob for s in ALL_SECRETS))
code, _out = run([mock.o, "--fail-on", "warn"], **BOTH)
check("keys: --fail-on warn gives exit 1", code == 1)

# 3. a refused token is FAIL, and the token the API echoes back is hidden
mock.reset()
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=WRONG, SEO_OPS_API_BASE=mock.o)
r = rows(out)
check("wrong token: exit 1", code == 1)
check("wrong token: yandex FAIL", r.get("yandex-index", ("",))[0] == "FAIL" and "INVALID_OAUTH_TOKEN" in out)
check("wrong token: echoed token hidden", WRONG not in out and "***" in out)

# 4. SEO_OPS_API_BASE only on loopback
mock.reset()
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=YTOK, SEO_OPS_API_BASE="http://example.org")
check("foreign API base: exit 2", code == 2 and "may point only at" in out)
check("foreign API base: nothing requested", mock.log == [])

# 5. --pages from a crawl report
crawl = os.path.join(tmp, "crawl.json")
with open(crawl, "w", encoding="utf-8") as fh:
    json.dump({"origin": mock.o, "date": "2026-11-26", "pages": [
        {"url": mock.u("/"), "status": 200, "kind": "html", "indexable": True},
        {"url": mock.u("/a"), "status": 200, "kind": "html", "indexable": True},
        {"url": mock.u("/x"), "status": 404, "kind": "error", "indexable": False},
        {"url": mock.u("/y"), "status": 200, "kind": "html", "indexable": False},
        {"url": mock.u("/f.pdf"), "status": 200, "kind": "file", "indexable": False}]}, fh)
mock.reset()
code, out = run([mock.o, "--pages", crawl], **BOTH)
r = rows(out)
check("--pages: two indexable pages", r.get("published", ("", ""))[1].startswith("2 indexable 200 pages"))
check("--pages: sitemap not read", not any(p == "/sitemap.xml" for _, p, _, _, _ in mock.log))
check("--pages: both in index", r.get("yandex-index", ("",))[0] == "OK" and r.get("google-index", ("",))[0] == "OK")
check("--pages: extra lists the rest", "/b" in r.get("yandex-extra", ("", ""))[1])
code, out = run(["other.test", "--pages", crawl], **BOTH)
check("--pages: crawl of another host is exit 2", code == 2 and "is a crawl of" in out)

# 6. host problems in Webmaster
mock.reset()
mock.cfg["hosts"] = "other"
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=YTOK, SEO_OPS_API_BASE=mock.o)
check("host not in account: FAIL", code == 1 and "is not in this Webmaster account (1 hosts there)" in out)
check("host not in account: other hosts not named", "other.test" not in out)
mock.reset()
mock.cfg["verified"] = False
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=YTOK, SEO_OPS_API_BASE=mock.o)
check("host not verified: FAIL", code == 1 and "not verified" in out)
mock.reset()
mock.cfg["insearch_429"] = True
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=YTOK, SEO_OPS_API_BASE=mock.o)
check("Webmaster quota: FAIL with the code", code == 1 and "QUOTA_EXCEEDED" in out)

# 7. paging of the search list
mock.reset()
saved_page = m.PAGE
m.PAGE = 2
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=YTOK, SEO_OPS_API_BASE=mock.o)
m.PAGE = saved_page
offsets = [urllib.parse.parse_qs(q)["offset"][0] for _, p, q, _, _ in mock.log if p.endswith("in-search/samples")]
check("paging: offsets 0 and 2", offsets == ["0", "2"])
check("paging: same verdict", rows(out).get("yandex-index", ("", ""))[1].startswith("3 of 6 published"))

# 8. Google limits and keys
mock.reset()
code, out = run([mock.o, "--google-max", "2"], **BOTH)
check("--google-max 2: two inspections", sum(1 for x in mock.log if x[1].endswith("index:inspect")) == 2)
check("--google-max 2: said so", "inspected the first 2 of 6 published pages" in out)
mock.reset()
mock.cfg["inspect_429_after"] = 3
code, out = run([mock.o], **BOTH)
check("inspection quota: WARN with the count", rows(out).get("google-index", ("",))[0] == "WARN"
      and "Google answered 429 after 3 inspections" in out)
check("inspection quota: no request after the 429", sum(1 for x in mock.log if x[1].endswith("index:inspect")) == 4)
mock.reset()
mock.cfg["echo_google"] = True
code, out = run([mock.o], **BOTH)
check("an error that echoes the exchanged token: hidden", ATOK not in out and "***" in out
      and "inspections failed" in out)
mock.reset()
code, out = run([mock.o], GSC_ACCESS_TOKEN=DIRECT, SEO_OPS_API_BASE=mock.o)
check("direct access token: no exchange", not any(p.endswith("/token") for _, p, _, _, _ in mock.log)
      and rows(out).get("google-index", ("",))[0] == "WARN" and DIRECT not in out)
mock.reset()
code, out = run([mock.o], GSC_CLIENT_ID=CID, SEO_OPS_API_BASE=mock.o)
check("partial Google keys: FAIL", code == 1 and "set all three" in out and mock.api_calls() == [])
mock.reset()
code, out = run([mock.o], GSC_CLIENT_ID=CID, GSC_CLIENT_SECRET=CSECRET, GSC_REFRESH_TOKEN="1//revoked",
                SEO_OPS_API_BASE=mock.o)
check("refused refresh token: FAIL", code == 1 and "Google refused the refresh token (400 invalid_grant" in out)
mock.reset()
code, out = run([mock.o], GSC_ACCESS_TOKEN=DIRECT, GSC_PROPERTY="sc-domain:example.test", SEO_OPS_API_BASE=mock.o)
check("GSC_PROPERTY: site list not read", not any(p.endswith("/webmasters/v3/sites") for _, p, _, _, _ in mock.log)
      and all(json.loads(b)["siteUrl"] == "sc-domain:example.test" for _, p, _, _, b in mock.log
              if p.endswith("index:inspect")))
mock.reset()
mock.cfg["sites"] = "domain"
code, out = run([mock.o], GSC_ACCESS_TOKEN=DIRECT, SEO_OPS_API_BASE=mock.o)
check("domain property picked", "property sc-domain:127.0.0.1" in out)
mock.reset()
mock.cfg["sites"] = "unverified"
code, out = run([mock.o], GSC_ACCESS_TOKEN=DIRECT, SEO_OPS_API_BASE=mock.o)
check("unverified property is not used", code == 1 and "no verified Search Console property" in out)

# 9. an API redirect is not followed (the token must not travel)
mock.reset()
mock.cfg["user_redirect"] = True
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=YTOK, SEO_OPS_API_BASE=mock.o)
check("API redirect: not followed", not any(p == "/steal" for _, p, _, _, _ in mock.log) and code == 1)

# 10. an API that does not answer is exit 2
s = socket.socket()
s.bind(("127.0.0.1", 0))
dead = s.getsockname()[1]
s.close()
mock.reset()
code, out = run([mock.o], YANDEX_WEBMASTER_TOKEN=YTOK, SEO_OPS_API_BASE="http://127.0.0.1:%d" % dead)
check("API unreachable: exit 2", code == 2 and "API UNREACHABLE" in out and YTOK not in out)

# 11. the scrubber
sec = m.Secrets()
sec.add("a+b/c=d")
check("scrub plain, quoted and form-encoded", sec.scrub("x a+b/c=d a%2Bb%2Fc%3Dd a%2Bb%2Fc%3Dd") == "x *** *** ***")
check("short values are not scrubbed", (lambda s: (s.add("ab"), s.scrub("ab"))[1])(m.Secrets()) == "ab")

mock.srv.shutdown()
mock.srv.server_close()
print(json.dumps({"ok": not bad, "total": total, "bad": bad}))
sys.exit(0 if not bad else 1)
