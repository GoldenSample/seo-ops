"""Tests for scripts/indexnow.py. Standard library only. No network: fetch and post are fakes.

Run: python tests/test_indexnow.py [path/to/indexnow.py]
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import contextlib
import datetime
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "indexnow.py")
spec = importlib.util.spec_from_file_location("indexnow", TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

total, bad = 0, []
UTC = datetime.timezone.utc


def check(name, cond):
    global total
    total += 1
    if not cond:
        bad.append(name)
        print("FAIL", name)


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    except Exception:
        return False
    return False


def dt(*a):
    return datetime.datetime(*a, tzinfo=UTC)


# valid_key
check("key ok", m.valid_key("a1b2c3d4") is True)
check("key dash ok", m.valid_key("abcd-1234-EFGH") is True)
check("key max length", m.valid_key("a" * 128) is True)
check("key short", m.valid_key("abc1234") is False)
check("key long", m.valid_key("a" * 129) is False)
check("key bad char", m.valid_key("abcd_1234") is False)
check("key none", m.valid_key(None) is False and m.valid_key("") is False and m.valid_key(12345678) is False)

# parse_lastmod
check("lm date", m.parse_lastmod("2026-11-20") == dt(2026, 11, 20))
check("lm minutes z", m.parse_lastmod("2026-11-20T10:30Z") == dt(2026, 11, 20, 10, 30))
check("lm seconds offset", m.parse_lastmod("2026-11-20T13:30:00+03:00") == dt(2026, 11, 20, 10, 30))
check("lm utc offset zero", m.parse_lastmod("2026-11-20T13:30:00+03:00").utcoffset() == datetime.timedelta(0))
check("lm negative offset", m.parse_lastmod("2026-11-20T05:30:00-05:00") == dt(2026, 11, 20, 10, 30))
check("lm fraction", m.parse_lastmod("2026-11-20T10:30:00.123Z") == dt(2026, 11, 20, 10, 30, 0, 123000))
check("lm long fraction", m.parse_lastmod("2026-11-20T10:30:00.123456789Z") == dt(2026, 11, 20, 10, 30, 0, 123456))
check("lm no zone is utc", m.parse_lastmod("2026-11-20T10:30:00") == dt(2026, 11, 20, 10, 30))
check("lm whitespace", m.parse_lastmod(" 2026-11-20 ") == dt(2026, 11, 20))
check("lm aware", m.parse_lastmod("2026-11-20").tzinfo is not None)
check("lm bad", m.parse_lastmod("20.11.2026") is None and m.parse_lastmod("") is None and m.parse_lastmod(None) is None)
check("lm impossible date", m.parse_lastmod("2026-02-30") is None)

# parse_sitemap
SM = ('﻿<?xml version="1.0" encoding="UTF-8"?>\n'
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
      '<url><loc> https://x.test/a </loc><lastmod>2026-11-24</lastmod></url>'
      '<url><loc>https://x.test/b</loc></url>'
      '<url><lastmod>2026-11-24</lastmod></url>'
      '<url><loc>https://x.test/c</loc><lastmod>2026-11-25T08:00:00+03:00</lastmod></url>'
      '<url><loc>https://other.test/d</loc><lastmod>2026-11-25</lastmod></url>'
      '</urlset>\n')
e, k = m.parse_sitemap(SM)
check("sm entries", e == [("https://x.test/a", "2026-11-24"), ("https://x.test/b", ""),
                          ("https://x.test/c", "2026-11-25T08:00:00+03:00"), ("https://other.test/d", "2026-11-25")])
check("sm no children", k == [])
IDX = ('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
       '<sitemap><loc>https://x.test/s1.xml</loc></sitemap><sitemap><loc>https://x.test/s2.xml</loc></sitemap>'
       '<sitemap><loc>https://x.test/s3.xml</loc></sitemap></sitemapindex>')
e, k = m.parse_sitemap(IDX)
check("idx children", e == [] and k == ["https://x.test/s1.xml", "https://x.test/s2.xml", "https://x.test/s3.xml"])
check("sm invalid raises ValueError", raises(ValueError, m.parse_sitemap, "<urlset><url>"))

# collect
S1 = ('<urlset><url><loc>https://x.test/1</loc><lastmod>2026-11-25</lastmod></url>'
      '<url><loc>https://x.test/2</loc></url></urlset>')
S2 = ('<urlset><url><loc>https://x.test/2</loc><lastmod>2026-11-01</lastmod></url>'
      '<url><loc>https://x.test/3</loc></url></urlset>')
PAGES = {"https://x.test/sitemap.xml": (200, IDX), "https://x.test/s1.xml": (200, S1),
         "https://x.test/s2.xml": (200, S2), "https://x.test/s3.xml": (404, "")}
calls = []


def fake_fetch(url):
    calls.append(url)
    return PAGES.get(url, (404, ""))


got, failed = m.collect("https://x.test/sitemap.xml", fake_fetch)
check("collect follows index", [u for u, _ in got] == ["https://x.test/1", "https://x.test/2", "https://x.test/3"])
check("collect keeps first duplicate", dict(got)["https://x.test/2"] == "")
check("collect reports failed child", failed == ["https://x.test/s3.xml"])
calls.clear()
got, failed = m.collect("https://x.test/sitemap.xml", fake_fetch, max_children=1)
check("collect max children", [u for u, _ in got] == ["https://x.test/1", "https://x.test/2"] and failed == []
      and "https://x.test/s2.xml" not in calls)
check("collect top error raises", raises(ValueError, m.collect, "https://x.test/none.xml", fake_fetch))
check("collect top invalid raises", raises(ValueError, m.collect, "https://x.test/bad.xml", lambda u: (200, "<urlset>")))
got, failed = m.collect("https://x.test/one.xml", lambda u: (200, S1))
check("collect plain urlset", [u for u, _ in got] == ["https://x.test/1", "https://x.test/2"] and failed == [])

# same_host
kept, dropped = m.same_host(["https://x.test/a", "https://X.TEST/b", "https://other.test/c", "http://x.test/d",
                             "https://www.x.test/e"], "X.test")
check("same host kept", kept == ["https://x.test/a", "https://X.TEST/b", "http://x.test/d"])
check("same host dropped", dropped == ["https://other.test/c", "https://www.x.test/e"])

# changed_since
entries = [("https://x.test/a", "2026-11-24"), ("https://x.test/b", ""),
           ("https://x.test/c", "2026-11-25T08:00:00+03:00"), ("https://x.test/e", "2026-11-25T04:59:59Z")]
check("changed since", m.changed_since(entries, dt(2026, 11, 25, 5, 0)) == ["https://x.test/c"])
check("changed since early", m.changed_since(entries, dt(2026, 11, 1)) == ["https://x.test/a", "https://x.test/c", "https://x.test/e"])

# diff_state
ch, rm, ns = m.diff_state(entries, {})
check("diff first run baseline", ch == [] and rm == [] and ns == {
    "https://x.test/a": "2026-11-24", "https://x.test/b": "",
    "https://x.test/c": "2026-11-25T08:00:00+03:00", "https://x.test/e": "2026-11-25T04:59:59Z"})
old = {"https://x.test/gone": "2026-01-01", "https://x.test/a": "2026-11-24", "https://x.test/b": "",
       "https://x.test/c": "2026-11-20"}
ch, rm, ns = m.diff_state(entries, old)
check("diff changed and new", ch == ["https://x.test/c", "https://x.test/e"])
check("diff removed", rm == ["https://x.test/gone"])
check("diff new state", "https://x.test/gone" not in ns and len(ns) == 4 and ns["https://x.test/c"] == "2026-11-25T08:00:00+03:00")

# filter_recent
send, skipped = m.filter_recent(["u1", "u2", "u3"], {"u1": 1000.0, "u2": 400.0}, 1500.0)
check("filter recent", send == ["u2", "u3"] and skipped == ["u1"])
send, skipped = m.filter_recent(["u"], {"u": 900.0}, 1500.0)
check("filter recent boundary", send == ["u"] and skipped == [])

# batches
b = m.batches(list(range(25001)))
check("batches", [len(x) for x in b] == [10000, 10000, 5001] and b[1][0] == 10000)
check("batches small", m.batches(["a", "b"], size=1) == [["a"], ["b"]])
check("batches empty", m.batches([]) == [])

# build_payload
p = m.build_payload("x.test", "a1b2c3d4", ["https://x.test/a"])
check("payload", p == {"host": "x.test", "key": "a1b2c3d4", "urlList": ["https://x.test/a"]}
      and list(p) == ["host", "key", "urlList"])
p = m.build_payload("x.test", "a1b2c3d4", ["u"], key_location="https://x.test/k/a1b2c3d4.txt")
check("payload key location", list(p) == ["host", "key", "keyLocation", "urlList"]
      and p["keyLocation"] == "https://x.test/k/a1b2c3d4.txt")

# retry_after_seconds
now_ts = dt(2026, 11, 25, 12, 0).timestamp()
check("retry digits", m.retry_after_seconds("120", now_ts) == 120 and m.retry_after_seconds(" 30 ", now_ts) == 30)
check("retry none", m.retry_after_seconds(None, now_ts) == 3600 and m.retry_after_seconds("soon", now_ts) == 3600
      and m.retry_after_seconds("", now_ts) == 3600)
check("retry date", m.retry_after_seconds("Wed, 25 Nov 2026 12:10:00 GMT", now_ts) == 600)
check("retry date past", m.retry_after_seconds("Wed, 25 Nov 2026 11:00:00 GMT", now_ts) == 0)


# check_key
def kf(url):
    return {"https://x.test/a1b2c3d4.txt": (200, "a1b2c3d4\n"),
            "https://x.test/k/a1b2c3d4.txt": (200, "wrong")}.get(url, (404, ""))


ok, d = m.check_key("x.test", "a1b2c3d4", kf)
check("key file ok", ok is True and "https://x.test/a1b2c3d4.txt" in d and "200" in d)
ok, d = m.check_key("x.test", "a1b2c3d4", kf, key_location="https://x.test/k/a1b2c3d4.txt")
check("key file mismatch", ok is False and "https://x.test/k/a1b2c3d4.txt" in d)
ok, d = m.check_key("x.test", "zzzzzzzz", kf)
check("key file missing", ok is False and "404" in d)

# submit
posted = []


def fake_post(url, body, headers):
    posted.append((url, json.loads(body.decode("utf-8")), headers))
    return 202, {}


st, h = m.submit("https://api.indexnow.org/indexnow", {"host": "x.test", "key": "k", "urlList": ["u"]}, fake_post)
check("submit status", st == 202 and h == {})
check("submit url and body", posted[0][0] == "https://api.indexnow.org/indexnow"
      and posted[0][1] == {"host": "x.test", "key": "k", "urlList": ["u"]})
check("submit content type", posted[0][2].get("Content-Type", "").startswith("application/json"))
check("submit user agent", "seo-ops-indexnow" in posted[0][2].get("User-Agent", ""))

# load_json / save_json
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "s.json")
    dflt = {"sent": {}}
    got = m.load_json(path, dflt)
    got["sent"]["x"] = 1
    check("load_json default copy", got == {"sent": {"x": 1}} and dflt == {"sent": {}})
    m.save_json(path, {"a": "б"})
    check("save_json round trip", m.load_json(path, {}) == {"a": "б"} and not os.path.exists(path + ".tmp"))

# CLI
KEY = "a1b2c3d4e5f6"
SITE_SM = ('<urlset><url><loc>https://x.test/</loc><lastmod>2026-11-25T10:00:00Z</lastmod></url>'
           '<url><loc>https://x.test/old</loc><lastmod>2026-10-01</lastmod></url>'
           '<url><loc>https://x.test/new</loc><lastmod>2026-11-25T09:00:00Z</lastmod></url>'
           '<url><loc>https://cdn.test/img</loc><lastmod>2026-11-25</lastmod></url></urlset>')
NOW = dt(2026, 11, 25, 12, 0).timestamp()


def make_fetch(sm=SITE_SM, keybody=KEY):
    def f(url):
        if url == "https://x.test/sitemap.xml":
            return 200, sm
        if url == "https://x.test/%s.txt" % KEY:
            return 200, keybody
        return 404, ""
    return f


class Post:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    def __call__(self, url, body, headers):
        self.calls.append(json.loads(body.decode("utf-8")))
        st = self.statuses.pop(0) if self.statuses else 200
        return st, ({"retry-after": "300"} if st == 429 else {})


def run(args, fetch=None, post=None, now=NOW):
    out = io.StringIO()
    code = m.main(args, fetch=fetch or make_fetch(), post=post if post is not None else Post([]), now=now, out=out)
    return code, out.getvalue()


os.environ.pop("INDEXNOW_KEY", None)
code, text = run(["--site", "x.test"])
check("cli no key", code == 2 and "error:" in text)
code, text = run(["--site", "x.test", "--key", "bad_key!"])
check("cli bad key", code == 2)
os.environ["INDEXNOW_KEY"] = KEY
code, text = run(["--site", "x.test"])
check("cli key from env", code == 0 and "dry run" in text)
os.environ.pop("INDEXNOW_KEY", None)

p = Post([200])
code, text = run(["--site", "x.test", "--key", KEY], post=p)
check("cli dry run default 26 hours", code == 0 and "dry run: 2 URLs" in text and p.calls == [])
check("cli dry run lists urls", "  https://x.test/new" in text)
check("cli dropped other host", "dropped 1 URLs on other hosts" in text)

p = Post([200])
code, text = run(["--site", "https://X.test/path", "--key", KEY, "--submit"], post=p)
check("cli submit", code == 0 and len(p.calls) == 1 and p.calls[0]["urlList"] == ["https://x.test/", "https://x.test/new"]
      and p.calls[0]["host"] == "x.test" and p.calls[0]["key"] == KEY)
check("cli submit prints batch", "batch 1/1: 2 URLs -> 200" in text)

p = Post([200])
code, text = run(["--site", "x.test", "--key", KEY, "--submit"], fetch=make_fetch(keybody="nope"), post=p)
check("cli key mismatch blocks submit", code == 1 and p.calls == [] and "key file FAIL" in text)

code, text = run(["--site", "x.test", "--key", KEY, "--check-key"])
check("cli check key ok", code == 0 and "key file OK" in text)
code, text = run(["--site", "x.test", "--key", KEY, "--check-key"], fetch=make_fetch(keybody="nope"))
check("cli check key fail", code == 1 and "key file FAIL" in text)

p = Post([202])
code, text = run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/p1", "--url", "https://x.test/p2",
                  "--submit"], post=p)
check("cli url mode", code == 0 and p.calls[0]["urlList"] == ["https://x.test/p1", "https://x.test/p2"])

code, text = run(["--site", "x.test", "--key", KEY, "--since-hours", "1"])
check("cli since hours nothing", code == 0 and "nothing to send" in text)

nolm = "<urlset><url><loc>https://x.test/a</loc></url></urlset>"
code, text = run(["--site", "x.test", "--key", KEY], fetch=make_fetch(sm=nolm))
check("cli no lastmod hint", code == 0 and "no lastmod" in text and "--state" in text)

code, text = run(["--site", "x.test", "--key", KEY], fetch=lambda u: (500, ""))
check("cli sitemap error", code == 2 and "error:" in text)

big = "<urlset>" + "".join("<url><loc>https://x.test/p%d</loc></url>" % i for i in range(10001)) + "</urlset>"
p = Post([200, 200])
code, text = run(["--site", "x.test", "--key", KEY, "--all", "--submit"], fetch=make_fetch(sm=big), post=p)
check("cli two batches", code == 0 and [len(c["urlList"]) for c in p.calls] == [10000, 1] and "batch 2/2" in text)

p = Post([200])
code, text = run(["--site", "x.test", "--key", KEY, "--all"], fetch=make_fetch(sm=big), post=p)
check("cli dry run truncates list", code == 0 and "and 9981 more" in text and p.calls == [])

with tempfile.TemporaryDirectory() as tmp:
    st = os.path.join(tmp, "state.json")
    p = Post([])
    code, text = run(["--site", "x.test", "--key", KEY, "--state", st], post=p)
    check("state dry run first no file", code == 0 and not os.path.exists(st))
    code, text = run(["--site", "x.test", "--key", KEY, "--state", st, "--submit"], post=p)
    check("state first run baseline", code == 0 and p.calls == [] and "nothing to send" in text and os.path.exists(st))
    sm2 = SITE_SM.replace("2026-10-01", "2026-11-25T11:00:00Z")
    p = Post([200])
    code, text = run(["--site", "x.test", "--key", KEY, "--state", st, "--submit"], fetch=make_fetch(sm=sm2), post=p)
    check("state sends changed", code == 0 and len(p.calls) == 1 and p.calls[0]["urlList"] == ["https://x.test/old"])
    with open(st, encoding="utf-8") as fh:
        saved = json.load(fh)
    check("state saved new lastmod", saved.get("https://x.test/old") == "2026-11-25T11:00:00Z")
    sm3 = sm2.replace("2026-11-25T09:00:00Z", "2026-11-25T11:30:00Z")
    code, text = run(["--site", "x.test", "--key", KEY, "--state", st], fetch=make_fetch(sm=sm3))
    with open(st, encoding="utf-8") as fh:
        saved2 = json.load(fh)
    check("state dry run writes nothing", code == 0 and "dry run: 1 URLs" in text and saved2 == saved)
    sm4 = sm2.replace('<url><loc>https://x.test/new</loc><lastmod>2026-11-25T09:00:00Z</lastmod></url>', '')
    p = Post([200])
    code, text = run(["--site", "x.test", "--key", KEY, "--state", st, "--submit"], fetch=make_fetch(sm=sm4), post=p)
    check("state sends removed url", code == 0 and len(p.calls) == 1 and p.calls[0]["urlList"] == ["https://x.test/new"])

with tempfile.TemporaryDirectory() as tmp:
    st = os.path.join(tmp, "state.json")
    with open(st, "w", encoding="utf-8") as fh:
        json.dump({"https://x.test/": "2026-01-01"}, fh)
    p = Post([403])
    code, text = run(["--site", "x.test", "--key", KEY, "--state", st, "--submit"], post=p)
    with open(st, encoding="utf-8") as fh:
        s2 = json.load(fh)
    check("403 keeps old state", code == 1 and s2 == {"https://x.test/": "2026-01-01"} and "403" in text
          and p.calls[0]["urlList"] == ["https://x.test/", "https://x.test/old", "https://x.test/new"])

with tempfile.TemporaryDirectory() as tmp:
    log = os.path.join(tmp, "sent.json")
    p = Post([200])
    code, _ = run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/a", "--sent-log", log, "--submit"], post=p)
    check("sent log written", code == 0 and os.path.exists(log))
    p2 = Post([200])
    code2, text2 = run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/a", "--url", "https://x.test/b",
                        "--sent-log", log, "--submit"], post=p2, now=NOW + 300)
    check("resend window skips", code2 == 0 and p2.calls[0]["urlList"] == ["https://x.test/b"] and "skipped 1" in text2)
    p3 = Post([200])
    code3, _ = run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/a", "--sent-log", log, "--submit"],
                   post=p3, now=NOW + 700)
    check("resend after window", code3 == 0 and p3.calls[0]["urlList"] == ["https://x.test/a"])
    p4 = Post([200])
    run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/c", "--sent-log", log, "--submit"],
        post=p4, now=NOW + 90000)
    with open(log, encoding="utf-8") as fh:
        j = json.load(fh)
    check("sent log drops old entries", "https://x.test/a" not in j["sent"] and "https://x.test/c" in j["sent"])

with tempfile.TemporaryDirectory() as tmp:
    log = os.path.join(tmp, "sent.json")
    p = Post([429])
    code, text = run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/a", "--sent-log", log, "--submit"], post=p)
    check("429 returns 1", code == 1 and "429" in text)
    with open(log, encoding="utf-8") as fh:
        j = json.load(fh)
    check("429 blocked until", abs(j.get("blocked_until", 0) - (NOW + 300)) < 1 and "https://x.test/a" not in j["sent"])
    p2 = Post([200])
    code2, text2 = run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/b", "--sent-log", log, "--submit"],
                       post=p2, now=NOW + 100)
    check("blocked run sends nothing", code2 == 1 and p2.calls == [] and "blocked until" in text2)
    p3 = Post([200])
    code3, _ = run(["--site", "x.test", "--key", KEY, "--url", "https://x.test/b", "--sent-log", log, "--submit"],
                   post=p3, now=NOW + 400)
    check("after block sends", code3 == 0 and len(p3.calls) == 1)

p = Post([429, 200])
code, text = run(["--site", "x.test", "--key", KEY, "--all", "--submit"], fetch=make_fetch(sm=big), post=p)
check("429 stops further batches", code == 1 and len(p.calls) == 1)

with contextlib.redirect_stderr(io.StringIO()):
    check("modes are exclusive", raises(SystemExit, m.main, ["--site", "x.test", "--key", KEY, "--all", "--since-hours", "2"],
                                        fetch=make_fetch(), post=Post([]), now=NOW, out=io.StringIO()))

print(json.dumps({"ok": not bad, "total": total, "bad": bad}))
sys.exit(0 if not bad else 1)
