"""Tests for scripts/wordstat.py against a local mock of the Wordstat methods of Yandex Search API v2.
Standard library only; nothing leaves 127.0.0.1. Request and response fields follow the API reference pages
(GetTop, GetDynamics, GetRegionsDistribution, GetRegionsTree; authentication).

Run: python tests/test_wordstat.py [path/to/wordstat.py]
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import contextlib
import csv
import http.server
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "wordstat.py")
spec = importlib.util.spec_from_file_location("wordstat", TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.MIN_GAP = 0.0

total, bad = 0, []
KEY = "AQVNtest-api-key-123456"
IAM = "t1.test-iam-token-654321"
WRONG = "AQVNwrong-key-999999"
FOLDER = "b1gtestfolder"


def check(name, cond):
    global total
    total += 1
    if not cond:
        bad.append(name)
        print("FAIL", name)


class Mock:
    def __init__(self):
        self.log = []
        self.busy_seen = 0
        mock = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                mock.handle(self)

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.o = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def reset(self):
        self.log.clear()
        self.busy_seen = 0

    def handle(self, h):
        n = int(h.headers.get("Content-Length") or 0)
        body = json.loads(h.rfile.read(n).decode("utf-8")) if n else {}
        auth = h.headers.get("Authorization", "")
        path = urllib.parse.urlsplit(h.path).path
        self.log.append((path, auth, body, time.monotonic()))
        status, payload, extra = self.answer(path, auth, body)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        for k, v in extra.items():
            h.send_header(k, v)
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    def answer(self, path, auth, body):
        pre = "/searchapi.api.cloud.yandex.net/v2/wordstat/"
        if auth not in ("Api-Key " + KEY, "Bearer " + IAM):
            return 401, {"code": 16, "message": "The token is invalid: %s" % auth}, {}
        ph = body.get("phrase")
        if ph == "bad":
            return 400, {"code": 3, "message": "invalid phrase"}, {}
        if ph == "busy" and self.busy_seen == 0:
            self.busy_seen += 1
            return 429, {"code": 8, "message": "quota exceeded"}, {"Retry-After": "0"}
        if path == pre + "topRequests":
            return 200, {"totalCount": "1200", "results": [{"phrase": ph, "count": "1200"},
                                                          {"phrase": ph + " купить", "count": "300"}],
                         "associations": [{"phrase": "похожий " + ph, "count": "50"}]}, {}
        if path == pre + "dynamics":
            return 200, {"results": [{"date": "2025-11-01T00:00:00Z", "count": "100", "share": "0.001"},
                                     {"date": "2025-12-01T00:00:00Z", "count": "250", "share": "0.002"}]}, {}
        if path == pre + "regions":
            return 200, {"results": [{"region": "213", "count": "500", "share": "0.4", "affinityIndex": "150.5"},
                                     {"region": "2", "count": "200", "share": "0.16", "affinityIndex": "120"}]}, {}
        if path == pre + "getRegionsTree":
            return 200, {"regions": [{"id": "225", "label": "Россия", "children": [
                {"id": "213", "label": "Москва"}, {"id": "2", "label": "Санкт-Петербург"}]}]}, {}
        return 404, {"code": 5, "message": "not found"}, {}


@contextlib.contextmanager
def env(**kw):
    keys = set(m.SECRET_ENV) | {"SEO_OPS_API_BASE", "YANDEX_CLOUD_FOLDER_ID"}
    old = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    os.environ.update(kw)
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


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


mock = Mock()
tmp = tempfile.mkdtemp(prefix="wordstat_test_")
CACHE = os.path.join(tmp, "cache")
OUT = os.path.join(tmp, "out.csv")
JS = os.path.join(tmp, "out.json")
E = dict(YANDEX_CLOUD_API_KEY=KEY, YANDEX_CLOUD_FOLDER_ID=FOLDER, SEO_OPS_API_BASE=mock.o)
P3 = ["чай пуэр", "чайник для пуэра", "улун"]


def fresh_cache():
    shutil.rmtree(CACHE, ignore_errors=True)


# 1. dry run: no key needed, nothing sent
mock.reset()
fresh_cache()
code, out = run(["top"] + P3 + ["--cache", CACHE, "--dry-run"], SEO_OPS_API_BASE=mock.o)
check("dry run: exit 0", code == 0)
check("dry run: counts", "dry run: 3 top requests to send, 0 answered from the cache" in out)
check("dry run: price", "about 0.06 RUB" in out)
check("dry run: nothing sent", mock.log == [])

# 2. top with an API key and a folder
mock.reset()
code, out = run(["top"] + P3 + ["--cache", CACHE, "--csv", OUT, "--json", JS], **E)
rows = read_csv(OUT)
check("top: exit 0", code == 0)
check("top: three requests", len(mock.log) == 3)
check("top: Api-Key header", all(a == "Api-Key " + KEY for _, a, _, _ in mock.log))
check("top: body", mock.log[0][2] == {"phrase": "чай пуэр", "numPhrases": "50", "folderId": FOLDER})
check("top: method path", mock.log[0][0] == "/searchapi.api.cloud.yandex.net/v2/wordstat/topRequests")
check("top: csv rows", len(rows) == 12 and rows[0] == {"phrase": "чай пуэр", "type": "total",
                                                       "query": "чай пуэр", "count": "1200"})
check("top: contains row", rows[2] == {"phrase": "чай пуэр", "type": "top", "query": "чай пуэр купить",
                                       "count": "300"})
check("top: similar row", rows[3] == {"phrase": "чай пуэр", "type": "similar", "query": "похожий чай пуэр",
                                      "count": "50"})
check("top: summary line", "чай пуэр: 1200 searches in 30 days" in out)
check("top: cost line", "requests sent: 3, from the cache: 0, about 0.06 RUB; errors: 0" in out)
with open(JS, encoding="utf-8") as fh:
    js_text = fh.read()
check("top: json", json.loads(js_text)["requests_sent"] == 3 and KEY not in js_text)
check("top: key not printed", KEY not in out)

# 3. the cache answers a rerun; --cache-days 0 sends again
mock.reset()
code, out = run(["top"] + P3 + ["--cache", CACHE], **E)
check("cache: nothing sent", mock.log == [] and "from the cache: 3" in out)
code, out = run(["top"] + P3 + ["--cache", CACHE, "--dry-run"], **E)
check("cache: dry run sees it", "0 top requests to send, 3 answered from the cache" in out)
code, out = run(["top"] + P3 + ["--cache", CACHE, "--cache-days", "0"], **E)
check("cache-days 0: sent again", len(mock.log) == 3)
def text_of(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


check("cache: no secret in cache files", not any(KEY in text_of(os.path.join(CACHE, f)) for f in os.listdir(CACHE)))

# 4. IAM token and devices
mock.reset()
fresh_cache()
code, out = run(["top", "улун", "--cache", CACHE, "--devices", "phone,desktop", "--num", "7", "--regions", "213,2"],
                YANDEX_CLOUD_IAM_TOKEN=IAM, SEO_OPS_API_BASE=mock.o)
check("iam: Bearer header", mock.log and mock.log[0][1] == "Bearer " + IAM)
check("iam: body without folder", mock.log and mock.log[0][2] == {"phrase": "улун", "numPhrases": "7",
                                                                  "regions": ["213", "2"],
                                                                  "devices": ["DEVICE_PHONE", "DEVICE_DESKTOP"]})
code, out = run(["top", "x", "--devices", "watch"], **E)
check("bad device: exit 2", code == 2)
code, out = run(["top", "x", "--num", "2001"], **E)
check("num over 2000: exit 2", code == 2)

# 5. the hourly window
mock.reset()
fresh_cache()
saved = m.HOUR
m.HOUR = 1.0
code, out = run(["top"] + P3 + ["--cache", CACHE, "--per-hour", "2"], **E)
m.HOUR = saved
stamps = [t for _, _, _, t in mock.log]
check("window: third request waits for the window", len(stamps) == 3 and stamps[2] - stamps[0] >= 0.95)
check("window: said so", "quota window: 2 requests in the last hour" in out)

# 6. 429 with Retry-After, a failed phrase, a refused key
mock.reset()
fresh_cache()
code, out = run(["top", "busy", "bad", "улун", "--cache", CACHE], **E)
check("429: retried", sum(1 for _, _, b, _ in mock.log if b.get("phrase") == "busy") == 2)
check("429: said so", "429 from the API: waiting 0 s" in out)
check("bad phrase: exit 1, others answered", code == 1 and "error: bad: 400 invalid phrase" in out
      and "улун: 1200 searches" in out and "busy: 1200 searches" in out)
mock.reset()
fresh_cache()
code, out = run(["top"] + P3 + ["--cache", CACHE], YANDEX_CLOUD_API_KEY=WRONG, SEO_OPS_API_BASE=mock.o)
check("wrong key: exit 1 after one request", code == 1 and len(mock.log) == 1 and "KEY REFUSED" in out)
check("wrong key: echoed key hidden", WRONG not in out and "***" in out)
mock.reset()
fresh_cache()
code, out = run(["top", KEY, "--cache", CACHE], **E)
check("a key pasted as a phrase is hidden on screen", KEY not in out and "***: 1200 searches" in out)

# 7. guards
mock.reset()
code, out = run(["top", "x", "--cache", CACHE], YANDEX_CLOUD_API_KEY=KEY, SEO_OPS_API_BASE="http://example.org")
check("foreign API base: exit 2", code == 2 and mock.log == [])
fresh_cache()
code, out = run(["top", "x", "--cache", CACHE], SEO_OPS_API_BASE=mock.o)
check("no key: exit 2 with a hint", code == 2 and "--dry-run works without a key" in out)

# 8. dynamics: dates moved to the start of the period
mock.reset()
fresh_cache()
code, out = run(["dynamics", "улун", "--from", "2025-11-17", "--to", "2026-11-01", "--cache", CACHE, "--csv", OUT], **E)
check("dynamics: monthly body", mock.log and mock.log[0][2] == {
    "phrase": "улун", "period": "PERIOD_MONTHLY", "fromDate": "2025-11-01T00:00:00Z",
    "toDate": "2026-11-01T00:00:00Z", "folderId": FOLDER})
check("dynamics: csv", read_csv(OUT) == [{"phrase": "улун", "date": "2025-11-01", "count": "100", "share": "0.001"},
                                          {"phrase": "улун", "date": "2025-12-01", "count": "250", "share": "0.002"}])
check("dynamics: summary", "peak 250 on 2025-12-01" in out)
mock.reset()
code, out = run(["dynamics", "улун", "--period", "weekly", "--from", "2026-11-26", "--cache", CACHE], **E)
check("dynamics: weekly from Monday", mock.log and mock.log[0][2]["fromDate"] == "2026-11-23T00:00:00Z"
      and mock.log[0][2]["period"] == "PERIOD_WEEKLY")
code, out = run(["dynamics", "x", "--from", "26.11.2026"], **E)
check("dynamics: bad date exit 2", code == 2)

# 9. regions with names, and the tree
mock.reset()
fresh_cache()
code, out = run(["regions", "улун", "--names", "--region-type", "cities", "--cache", CACHE, "--csv", OUT], **E)
paths = [p.rsplit("/", 1)[-1] for p, _, _, _ in mock.log]
check("regions: tree once, then regions", paths == ["getRegionsTree", "regions"])
check("regions: body", mock.log and mock.log[1][2] == {"phrase": "улун", "region": "REGION_CITIES",
                                                       "folderId": FOLDER})
check("regions: names in csv", read_csv(OUT)[0] == {"phrase": "улун", "region": "213", "region_name": "Москва",
                                                    "count": "500", "share": "0.4", "affinity_index": "150.5"})
check("regions: the free tree is not priced", "requests sent: 2, from the cache: 0, about 0.05 RUB" in out)
mock.reset()
code, out = run(["regions", "чайник", "--names", "--cache", CACHE], **E)
check("regions: tree from the cache next time", [p.rsplit("/", 1)[-1] for p, _, _, _ in mock.log] == ["regions"])
mock.reset()
fresh_cache()
code, out = run(["tree", "--cache", CACHE, "--csv", OUT], **E)
tree = read_csv(OUT)
check("tree: rows", tree == [{"id": "225", "label": "Россия", "parent_id": "", "depth": "0"},
                             {"id": "213", "label": "Москва", "parent_id": "225", "depth": "1"},
                             {"id": "2", "label": "Санкт-Петербург", "parent_id": "225", "depth": "1"}])
check("tree: free", "about 0.00 RUB" in out and mock.log[0][2] == {"folderId": FOLDER})

# 10. phrase files
txt = os.path.join(tmp, "phrases.txt")
with open(txt, "w", encoding="utf-8") as fh:
    fh.write("# markers\nчай пуэр\n\n  Чай Пуэр  \nчайник   для улуна\n" + "x" * 401 + "\n")
mock.reset()
fresh_cache()
code, out = run(["top", "--phrases", txt, "--cache", CACHE, "--dry-run"], **E)
check("txt: comments, blanks, duplicates", "2 top requests to send" in out and "longer than 400 characters" in out)
csvf = os.path.join(tmp, "phrases.csv")
with open(csvf, "w", encoding="cp1251", newline="") as fh:
    fh.write("Фраза;Частота\nкупить чай пуэр;100\nчай пуэр шу;50\n")
code, out = run(["top", "--phrases", csvf, "--cache", CACHE], **E)
check("csv cp1251 with a header", [b["phrase"] for _, _, b, _ in mock.log] == ["купить чай пуэр",
                                                                               "чай пуэр шу"])

mock.srv.shutdown()
mock.srv.server_close()
shutil.rmtree(tmp, ignore_errors=True)
print(json.dumps({"ok": not bad, "total": total, "bad": bad}, ensure_ascii=False))
sys.exit(0 if not bad else 1)
