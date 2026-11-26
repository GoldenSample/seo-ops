"""Tests for scripts/serp_cluster.py. Standard library only, no network.

Run: python tests/test_cluster.py [path/to/serp_cluster.py]
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import contextlib
import csv
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "serp_cluster.py")
spec = importlib.util.spec_from_file_location("serp_cluster", TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

total, bad = 0, []


def check(name, cond):
    global total
    total += 1
    if not cond:
        bad.append(name)
        print("FAIL", name)


def run(args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = m.main(args)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


def text_of(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def jload(path):
    try:
        return json.loads(text_of(path))
    except ValueError:
        return {"clusters": [], "stats": {}, "params": {}, "page_in_several_clusters": {}}


def write(path, text, enc="utf-8"):
    with open(path, "w", encoding=enc, newline="") as fh:
        fh.write(text)
    return path


def groups(clusters):
    return [c["phrases"] for c in clusters]


def rs(path):
    """read_serp that reports a failure as an empty result instead of stopping the run."""
    try:
        return m.read_serp(path)
    except Exception as e:  # a mutant may raise; the checks below then fail one by one
        print("read_serp raised %s: %s" % (type(e).__name__, e))
        return {"positions": {}, "freq": {}, "shape": None, "header": None}


def rf(path):
    try:
        return m.read_freq(path)
    except Exception as e:
        print("read_freq raised %s: %s" % (type(e).__name__, e))
        return {}


# ------------------------------------------------ the plain pairwise walk the index must reproduce

def reference(serps, freq, threshold, mode, top):
    norm = m.normalize_url
    sets = {p: {norm(u) for u in serps[p][:top] if norm(u)} for p in serps}

    def f(p):
        return freq.get(p, 0) if freq else 0
    order = sorted(serps, key=lambda p: (-f(p), p))
    left, out = list(order), []
    while left:
        centre = left.pop(0)
        members = [centre]
        if sets[centre]:
            for p in list(left):
                if not sets[p]:
                    continue
                if mode == "soft":
                    ok = len(sets[p] & sets[centre]) >= threshold
                else:
                    ok = all(len(sets[p] & sets[q]) >= threshold for q in members)
                if ok:
                    members.append(p)
                    left.remove(p)
        counts = {}
        for q in members:
            for k in sets[q]:
                counts[k] = counts.get(k, 0) + 1
        shared = sorted([k for k, n in counts.items() if n >= 2], key=lambda k: (-counts[k], k)) \
            if len(members) > 1 else []
        out.append({"centre": centre, "phrases": members, "freq": sum(f(q) for q in members),
                    "shared_urls": shared, "no_serp": not sets[centre]})
    return out


def lcg(seed):
    x = seed
    while True:
        x = x * 48271 % (2**31 - 1)  # MINSTD, seed >= 1
        yield x


def synthetic(seed, n=90):
    g = lcg(seed)
    serps, freq = {}, {}
    for i in range(n):
        topic = next(g) % 7
        urls = []
        while len(urls) < 12:
            if next(g) % 10 < 7:
                u = "https://t%d.test/p%d" % (topic, next(g) % 11)
            else:
                u = "https://g.test/x%d" % (next(g) % 25)
            if u not in urls:
                urls.append(u)
        name = "q%02d" % i
        serps[name] = [] if i % 23 == 5 else urls
        freq[name] = (next(g) % 40) * 10
    return serps, freq


# ------------------------------------------------ units
check("normalize: protocol-relative", m.normalize_url("//www.Example.com/a/") == "example.com/a")
check("normalize: percent-encoding equals the decoded path",
      m.normalize_url("https://a.test/%D1%87%D0%B0%D0%B9/") == m.normalize_url("a.test/чай"))
check("normalize: punycode host read as unicode", m.normalize_url("https://xn--e1afmkfd.xn--p1ai/") == "пример.рф")
check("normalize: ipv6 default port", m.normalize_url("http://[::1]:80/x") == "[::1]/x")
check("normalize: ipv6 without port kept", m.normalize_url("http://[::1]/x") == "[::1]/x")
check("normalize: broken ipv6 does not raise", isinstance(m.normalize_url("http://[abc/x"), str))
check("looks like url: yes", all(m.looks_like_url(s) for s in (
    "https://a.test/x", "a.test", "пример.рф/путь", "xn--e1afmkfd.xn--p1ai", "a.test:8080/x", "a.test?x=1")))
check("looks like url: no", not any(m.looks_like_url(s) for s in (
    "купить чай", "12.50", "1.5", "т.е.", "", "v1.2", "e.g")))
check("numbers", m.parse_number("1 234") == 1234 and m.parse_number("12,5") == 12.5
      and m.parse_number("1,234") == 1234 and m.parse_number("-") is None and m.parse_number("") is None)
check("phrase key", m.fkey("  Чёрный   Чай ") == "черный чай")

# the inverted index gives the same clusters as the plain pairwise walk
same = True
for seed in (1, 2, 3):
    serps, freq = synthetic(seed)
    for mode in ("soft", "hard"):
        for th in (1, 2, 3, 4, 5, 6):
            for top in (10, 6):
                if th > top:
                    continue
                for fr in (freq, None):
                    if m.cluster(serps, fr, th, mode, top) != reference(serps, fr, th, mode, top):
                        same = False
                        print("differs: seed %d mode %s threshold %d top %d freq %s" % (seed, mode, th, top, bool(fr)))
check("index equals the pairwise walk (3 seeds, both modes, thresholds 1-6, top 10 and 6)", same)
serps, freq = synthetic(4)
r = m.cluster(serps, freq, 3, "soft", 10)
check("synthetic data forms real clusters", sum(1 for c in r if len(c["phrases"]) > 1) >= 3)

# ------------------------------------------------ fixtures
# A, B, C share u1-u3 (A-B) and u4-u6 (A-C); B and C share only u1 -> soft {A,B,C}, hard {A,B},{C}.
# D shares u1-u3 with A only at positions 9-11: with top 10 it shares two URLs, with top 11 three.
U = ["https://www.r%d.test/page/" % i for i in range(1, 40)]


def serp_long():
    rows = {"чай пуэр": [U[0], U[1], U[2], U[3], U[4], U[5], U[20], U[21], U[22], U[23]],
            "купить пуэр": [U[0], U[1], U[2], U[24], U[25], U[26], U[27], U[28], U[29], U[30]],
            "чай пуэр шу": [U[3], U[4], U[5], U[0], U[31], U[32], U[33], U[34], U[35], U[36]],
            "заварник для пуэра": [U[10], U[11], U[12], U[13], U[14], U[15], U[16], U[17], U[0], U[1]],
            "польза пуэра": []}
    return rows


FREQ = {"чай пуэр": 900, "купить пуэр": 500, "чай пуэр шу": 300,
        "заварник для пуэра": 200, "польза пуэра": 50}


def long_csv(path, sep=",", enc="utf-8", head=("keyword", "position", "url", "volume")):
    lines = [sep.join(head)]
    for p, urls in serp_long().items():
        if not urls:
            lines.append(sep.join([p, "", "", str(FREQ[p])]))
        for i, u in enumerate(urls, 1):
            lines.append(sep.join([p, str(i), u, str(FREQ[p])]))
    # D's 11th result: the third shared URL, beyond top 10
    lines.append(sep.join(["заварник для пуэра", "11", U[2].replace("www.", ""), str(FREQ["заварник для пуэра"])]))
    return write(path, "\n".join(lines) + "\n", enc)


def wide_csv(path, sep=";", enc="cp1251", head=True):
    lines = []
    if head:
        lines.append(sep.join(["Запрос"] + ["URL %d" % i for i in range(1, 12)]))
    for p, urls in serp_long().items():
        extra = [U[2]] if p == "заварник для пуэра" else []
        lines.append(sep.join([p] + urls + extra))
    return write(path, "\r\n".join(lines) + "\r\n", enc)


tmp = tempfile.mkdtemp(prefix="serp_cluster_")
P = lambda name: os.path.join(tmp, name)  # noqa: E731

# ------------------------------------------------ long form, English headers, frequency column
long_path = long_csv(P("long.csv"))
d = rs(long_path)
check("long: shape and phrases", d["shape"] == "long" and len(d["positions"]) == 5 and d["header"])
check("long: frequency column read", d["freq"].get("чай пуэр") == 900)
check("long: phrase without results kept", d["positions"].get("польза пуэра", []) == [])
code, out = run([long_path, "--json", P("long.json"), "--csv", P("long_out.csv"), "--md", P("long.md")])
j = jload(P("long.json"))
check("long: exit 0", code == 0)
check("long soft: clusters", groups(j["clusters"]) == [
    ["чай пуэр", "купить пуэр", "чай пуэр шу"], ["заварник для пуэра"],
    ["польза пуэра"]])
check("long soft: cluster frequency", bool(j["clusters"]) and j["clusters"][0]["freq"] == 1700)
check("long soft: shared urls normalized", bool(j["clusters"]) and j["clusters"][0]["shared_urls"][:1] == ["r1.test/page"])
check("long: no_serp marked", len(j["clusters"]) > 2 and j["clusters"][2]["no_serp"] is True
      and j["stats"].get("no_serp") == 1)
check("long: params", j["params"] == {"mode": "soft", "threshold": 3, "top": 10})
code, out = run([long_path, "--top", "11", "--json", P("long11.json")])
j11 = jload(P("long11.json"))
check("top 11 counts the 11th result", ["чай пуэр", "купить пуэр", "чай пуэр шу",
                                        "заварник для пуэра"] == (groups(j11["clusters"]) or [[]])[0])
code, out = run([long_path, "--mode", "hard", "--json", P("hard.json")])
jh = jload(P("hard.json"))
check("hard: C leaves the cluster of A and B", groups(jh["clusters"])[:2] == [
    ["чай пуэр", "купить пуэр"], ["чай пуэр шу"]])
code, out = run([long_path, "--threshold", "4", "--json", P("t4.json")])
check("threshold 4: only A and C stay together", groups(jload(P("t4.json"))["clusters"]) == [
    ["чай пуэр", "чай пуэр шу"], ["купить пуэр"], ["заварник для пуэра"],
    ["польза пуэра"]])
rows = list(csv.reader(io.StringIO(text_of(P("long_out.csv")))))
check("csv: header", (rows or [[]])[0] == ["cluster", "centre", "phrase", "frequency", "cluster_frequency", "cluster_size",
                                 "site_url", "site_position", "cluster_site_page", "no_serp"])
check("csv: one row per phrase", len(rows) == 6 and rows[1][:3] == ["1", "чай пуэр", "чай пуэр"])
check("csv: no_serp column", len(rows) > 5 and rows[5][2] == "польза пуэра" and rows[5][9] == "yes")
md = text_of(P("long.md"))
check("md: table with clusters", "| 1 | чай пуэр | 3 | 1700 |" in md and "5 phrases, 3 clusters" in md)
check("stdout: summary", "5 phrases -> 3 clusters" in out or "5 phrases -> 3 clusters" in run([long_path])[1])

# ------------------------------------------------ wide form, Russian header, windows-1251, semicolon
wide_path = wide_csv(P("wide.csv"))
d = rs(wide_path)
check("wide cp1251: shape and phrase names", d["shape"] == "wide" and "чай пуэр" in d["positions"])
check("wide: positions in column order", [x[0] for x in d["positions"].get("заварник для пуэра", [])] == list(range(1, 12)))
code, out = run([wide_path, "--freq", write(P("freq.csv"), "Фраза,Частотность\n" + "\n".join(
    "%s,%d" % (p.upper().replace("Е", "Ё", 1), n) for p, n in FREQ.items()) + "\n"), "--json", P("wide.json")])
jw = jload(P("wide.json"))
check("wide: same clusters as long", groups(jw["clusters"]) == groups(j["clusters"]))
check("freq file matched without case and ё", "--freq matched 5 of 5 phrases" in out
      and bool(jw["clusters"]) and jw["clusters"][0]["freq"] == 1700)

# headerless wide form, tab separated
d = rs(wide_csv(P("nohead.tsv"), sep="\t", enc="utf-8", head=False))
check("no header row: all phrases kept", d["header"] is False and len(d["positions"]) == 5
      and len(d["positions"].get("чай пуэр", [])) == 10)

# repeated url headers and numbered columns are the wide form
d = rs(write(P("rep.csv"), "phrase,url,url,url\nа,https://a.test/1,https://a.test/2,https://a.test/3\n"))
check("repeated url headers: wide", d["shape"] == "wide" and len(d["positions"].get("а", [])) == 3)
d = rs(write(P("num.csv"), "Запрос;1;2;3\nа;a.test/1;a.test/2;a.test/3\n"))
check("numbered columns: wide", d["shape"] == "wide" and [u for _, u in d["positions"].get("а", [])] == [
    "a.test/1", "a.test/2", "a.test/3"])

# delimiter: commas inside a quoted phrase do not decide
d = rs(write(P("quoted.csv"), '"чай, купить, недорого, москва";https://a.test/1;https://a.test/2;'
                      'https://a.test/3\n"чай, недорого";https://a.test/1;https://a.test/2;https://a.test/3\n'))
check("quoted commas: semicolon chosen", list(d["positions"]) == ["чай, купить, недорого, москва", "чай, недорого"])

# a phrase repeated in the file keeps the first result per position
dup = "phrase;" + ";".join("u%d" % i for i in range(1, 11)) + "\n"
x = ["https://x.test/%d" % i for i in range(1, 11)]
dup += "икс;" + ";".join(x) + "\n" + "Икс;" + ";".join(x) + "\n"
dup += "игрек;" + ";".join([x[5], x[6], x[7]] + ["https://y.test/%d" % i for i in range(7)]) + "\n"
code, out = run([write(P("dup.csv"), dup), "--json", P("dup.json")])
check("repeated phrase: results not doubled", groups(jload(P("dup.json"))["clusters"]) == [
    ["игрек", "икс"]] and "10 repeated results" in out)

# positions decide the depth, not the row count: results at 12-14 do not count with top 10
gap = ["phrase,position,url"] + ["икс,%d,https://x.test/%d" % (i, i) for i in range(1, 11)]
gap += ["игрек,%d,https://y.test/%d" % (i, i) for i in (1, 2, 3)]
gap += ["игрек,%d,https://x.test/%d" % (i + 11, i) for i in (1, 2, 3)]
gap_path = write(P("gap.csv"), "\n".join(gap) + "\n")
run([gap_path, "--json", P("gap10.json")])
run([gap_path, "--top", "14", "--json", P("gap14.json")])
check("depth by position: top 10 keeps them apart, top 14 joins them",
      groups(jload(P("gap10.json"))["clusters"]) == [["игрек"], ["икс"]]
      and groups(jload(P("gap14.json"))["clusters"]) == [["игрек", "икс"]])

# ------------------------------------------------ frequencies from wordstat.py top
ws = "phrase,type,query,count\nчай,total,чай,5000\nчай,top,чай пуэр,900\n" \
     "чай,top,купить пуэр,500\nчай,similar,чай пуэр шу,300\n" \
     "заварник,total,заварник для пуэра,200\n"
fw = rf(write(P("ws.csv"), ws))
check("wordstat csv: total, top and similar rows", fw.get("чай пуэр") == 900
      and fw.get("чай пуэр шу") == 300 and fw.get("заварник для пуэра") == 200)
code, out = run([long_path, "--freq", write(P("f1.csv"), "phrase,frequency\nчай пуэр,1\nпольза пуэра,7\n"),
                 "--freq", write(P("f2.csv"), "phrase,frequency\nчай пуэр,2\n"), "--json", P("two.json")])
two = {c["centre"]: c["freq"] for c in jload(P("two.json"))["clusters"]}
check("two --freq files: both read, the later wins", "--freq matched 2 of 5 phrases" in out
      and two.get("польза пуэра") == 7 and two.get("заварник для пуэра") == 200)
check("freq without header", rf(write(P("nh.csv"), "чай;12\nзаварник;1 500\n")) == {
    "чай": 12, "заварник": 1500})

# ------------------------------------------------ --site: page per cluster, new pages, split, shared page
S = "https://shop.test"
site_serp = {
    "a1": ["%s/blog/teapot" % S, U[0], U[1], U[2], U[3]],
    "a2": [U[0], U[1], U[2], "%s/teapots" % S, U[4]],
    "a3": [U[0], U[1], U[2], U[4], "%s/teapots/" % S],
    "b1": [U[10], U[11], U[12], U[13], "%s/teapots" % S],
    "b2": [U[10], U[11], U[12], U[14], U[15]],
    "c1": [U[20], U[21], U[22], U[23], U[24]],
    "c2": [U[20], U[21], U[22], U[25], U[26]],
}
lines = ["phrase,position,url,frequency"]
fq = {"a1": 90, "a2": 80, "a3": 70, "b1": 60, "b2": 50, "c1": 40, "c2": 30}
for p, urls in site_serp.items():
    for i, u in enumerate(urls, 1):
        lines.append("%s,%d,%s,%d" % (p, i, u, fq[p]))
code, out = run([write(P("site.csv"), "\n".join(lines) + "\n"), "--site", "www.shop.test", "--top", "5",
                 "--json", P("site.json"), "--md", P("site.md"), "--csv", P("site_out.csv")])
js = jload(P("site.json"))
by = {c["centre"]: c for c in js["clusters"]}
for k in ("a1", "b1", "c1"):
    by.setdefault(k, {"site_page": "", "site_covers": 0, "site_position": 0, "site_note": ""})
check("site: clusters", groups(js["clusters"]) == [["a1", "a2", "a3"], ["b1", "b2"], ["c1", "c2"]])
check("site: page that covers most phrases wins over a better position",
      by["a1"]["site_page"] == "%s/teapots" % S and by["a1"]["site_covers"] == 2 and by["a1"]["site_position"] == 4)
check("site: split cluster noted", by["a1"]["site_note"].startswith("several pages of the site")
      and "/blog/teapot" in by["a1"]["site_note"])
check("site: cluster without a page", by["c1"]["site_page"] is None and "new page" in by["c1"]["site_note"])
check("site: page main for two clusters", list(js["page_in_several_clusters"].values()) == [[1, 2]])
smd = text_of(P("site.md"))
check("site md: sections", "## Candidates for new pages (1)" in smd and "- c1: 2 phrases, frequency 70" in smd
      and "## One cluster, several pages of the site (1)" in smd and "## One page, main page of several clusters (1)"
      in smd)
srows = list(csv.reader(io.StringIO(text_of(P("site_out.csv")))))
check("site csv: site url and position per phrase", len(srows) > 3 and srows[1][6] == "%s/blog/teapot" % S and srows[1][7] == "1"
      and srows[3][6] == "%s/teapots/" % S and srows[3][7] == "5" and srows[1][8] == "%s/teapots" % S)

# ------------------------------------------------ bad input
check("missing file: exit 2", run([P("none.csv")])[0] == 2)
check("empty file: exit 2", run([write(P("empty.csv"), "\n\n")])[0] == 2)
check("threshold above top: exit 2", run([long_path, "--threshold", "11"])[0] == 2)
check("threshold 0: exit 2", run([long_path, "--threshold", "0"])[0] == 2)
check("no url column: exit 2", run([write(P("nourl.csv"), "phrase,frequency\nчай,10\n")])[0] == 2)
check("freq without columns: exit 2", run([long_path, "--freq", write(P("badfreq.csv"), "a,b\nx,y\n")])[0] == 2)
check("bad mode: exit 2", run([long_path, "--mode", "medium"])[0] == 2)

# ------------------------------------------------ the README example (examples/serp.csv, examples/freq.csv)
EX = os.path.join(HERE, "..", "examples")
check("example: files present",
      os.path.exists(os.path.join(EX, "serp.csv")) and os.path.exists(os.path.join(EX, "freq.csv")))
code, _out = run([os.path.join(EX, "serp.csv"), "--freq", os.path.join(EX, "freq.csv"), "--site", "example.com",
                  "--json", P("ex.json"), "--md", P("ex.md")])
ex = jload(P("ex.json"))
eid = {c.get("id"): c.get("centre") for c in ex["clusters"]}
eby = {c.get("centre"): c for c in ex["clusters"]}
check("example: 14 phrases in 6 clusters", code == 0 and ex["stats"].get("phrases") == 14
      and ex["stats"].get("clusters") == 6 and ex["stats"].get("singletons") == 1)
check("example: two clusters without a page of the shop",
      sorted((c.get("centre"), c.get("freq")) for c in ex["clusters"] if not c.get("site_page"))
      == [("how to brew oolong", 390), ("how to make matcha", 1920)])
check("example: /green-tea/ is the main page of two clusters",
      [sorted(eid.get(i) or "" for i in ids) for ids in ex["page_in_several_clusters"].values()]
      == [["green tea", "matcha powder"]])
oolong = eby.get("oolong tea") or {}
check("example: the oolong cluster is split between /oolong/ and the home page",
      oolong.get("site_page") == "https://example.com/oolong/" and oolong.get("freq") == 3090
      and "https://example.com/ (1)" in (oolong.get("site_note") or ""))
check("example md: one phrase in the singular", "- how to brew oolong: 1 phrase, frequency 390" in text_of(P("ex.md")))

print(json.dumps({"ok": not bad, "total": total, "bad": bad}))
sys.exit(0 if not bad else 1)
