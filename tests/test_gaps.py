"""Tests for scripts/gsc_gaps.py. Standard library only.

Run: python tests/test_gaps.py [path/to/gsc_gaps.py]
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "gsc_gaps.py")
spec = importlib.util.spec_from_file_location("gsc_gaps", TARGET)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

total, bad = 0, []


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


def close(a, b, eps=1e-6):
    return abs(a - b) < eps


# parse_number
check("num thousands comma", g.parse_number("1,234") == 1234.0)
check("num percent dot", g.parse_number("3.45%") == 3.45)
check("num percent comma", g.parse_number("3,45%") == 3.45)
check("num empty", g.parse_number("") == 0.0 and g.parse_number(None) == 0.0 and g.parse_number("-") == 0.0)
check("num int", g.parse_number("12") == 12.0 and g.parse_number(7) == 7.0)
check("num space thousands", g.parse_number("1 234") == 1234.0)
check("num nbsp thousands", g.parse_number("1 234,5") == 1234.5)
check("num comma decimal", g.parse_number("0,5") == 0.5)
check("num both separators", g.parse_number("1,234.5") == 1234.5)
check("num garbage", raises(ValueError, g.parse_number, "abc"))

# read_queries: Search Console export, English header, BOM, percent CTR
gsc = ("﻿Top queries,Clicks,Impressions,CTR,Position\n"
       "как выбрать мотогарнитуру,5,200,2.5%,9.3\n"
       "мотогарнитура для двоих,0,150,0%,25\n"
       "sena 50s,1,120,0.83%,4.2\n"
       "шлем,0,5,0%,40\n"
       ",1,1,1%,1\n")
q = g.read_queries(gsc)
check("gsc rows", len(q) == 4)
check("gsc first", q[0]["query"] == "как выбрать мотогарнитуру" and q[0]["impressions"] == 200.0
      and close(q[0]["ctr"], 0.025) and close(q[0]["position"], 9.3) and q[0]["clicks"] == 5.0)

# read_queries: Russian header, semicolon, no CTR column, comma decimals
ya = "Запрос;Показы;Клики;Средняя позиция\nсена 50s;120;3;4,2\n"
y = g.read_queries(ya)
check("ya parsed", len(y) == 1 and y[0]["impressions"] == 120.0 and y[0]["clicks"] == 3.0)
check("ya ctr computed", close(y[0]["ctr"], 0.025))
check("ya position comma", close(y[0]["position"], 4.2))
check("missing column raises", raises(ValueError, g.read_queries, "Query,Clicks\nx,1\n"))
check("ctr fraction kept", close(g.read_queries("Query,Impressions,CTR\nx,100,0.05\n")[0]["ctr"], 0.05))
check("ctr number over 1 is percent", close(g.read_queries("Query,Impressions,CTR\nx,100,5\n")[0]["ctr"], 0.05))
check("tab delimiter", g.read_queries("Query\tImpressions\nx\t10\n")[0]["impressions"] == 10.0)

with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "Queries.csv")
    with open(p, "w", encoding="utf-8") as fh:  # gsc already starts with a BOM, as real exports do
        fh.write(gsc)
    check("read from path", len(g.read_queries(p)) == 4)

# tokens
check("tokens ru", g.tokens("Как выбрать мотогарнитуру?") == ["выбра", "мотог"])
check("tokens yo", g.tokens("ёлка") == ["елка"])
check("tokens en", g.tokens("How to choose a headset") == ["choos", "heads"])
check("tokens short dropped", g.tokens("a b cd") == ["cd"])
check("tokens digits", g.tokens("Sena 50S") == ["sena", "50s"])
check("page tokens url", "vybra" in g.page_tokens("https://x.ru/kak-vybrat/", "") or
      "vybra" in g.page_tokens("https://x.ru/kak-vybrat/", "Гид"))

# best_page
pages = [("https://x.ru/kak-vybrat/", "Как выбрать мотогарнитуру: гид"),
         ("https://x.ru/sena-50s/", "Sena 50S мотогарнитура")]
pd = [{"url": u, "title": t, "tokens": g.page_tokens(u, t)} for u, t in pages]
u, s = g.best_page("как выбрать мотогарнитуру", pd)
check("best page full match", u == "https://x.ru/kak-vybrat/" and close(s, 1.0))
u, s = g.best_page("мотогарнитура для двоих", pd)
check("best page tie shorter url", u == "https://x.ru/sena-50s/" and close(s, 0.5))
check("best page none", g.best_page("шлем", pd) == (None, 0.0))
check("best page empty query", g.best_page("и в", pd) == (None, 0.0))
lat = [{"url": "https://x.ru/motogarnitury/", "title": "", "tokens": g.page_tokens("https://x.ru/motogarnitury/", "")}]
check("translit url match", g.best_page("мотогарнитуры", lat) == ("https://x.ru/motogarnitury/", 1.0))
check("page tokens skip domain", g.page_tokens("https://shop.example", "") == set())
ru = g.read_queries("Самые частые запросы,Клики,Показы,CTR,Позиция\nсена,1,100,1%,3\n")
check("ru search console header", len(ru) == 1 and ru[0]["impressions"] == 100.0 and close(ru[0]["ctr"], 0.01))
check("header fallback by part", g.read_queries("Search query;Impressions total\nx;10\n")[0]["impressions"] == 10.0)
check("title skips svg icons", g.title_of("<html><head><title>Main &amp; more</title></head><body>"
                                          "<svg><title>icon</title></svg></body></html>") == "Main & more")
check("title inside svg only", g.title_of("<body><svg><title>icon</title></svg></body>") == "")

# analyze
res = g.analyze(q, pages, min_impressions=10, gap_threshold=0.6)
gap_q = [r["query"] for r in res["gaps"]]
st_q = [r["query"] for r in res["striking"]]
lc_q = [r["query"] for r in res["low_ctr"]]
check("analyze counts", res["pages"] == 2 and res["queries"] == 3)
check("analyze gaps", gap_q == ["мотогарнитура для двоих"])
check("analyze gap score", close(res["gaps"][0]["score"], 0.5))
check("analyze striking", st_q == ["как выбрать мотогарнитуру"])
check("analyze low ctr", lc_q == ["sena 50s"])
check("analyze min impressions", "шлем" not in gap_q + st_q + lc_q)
q2 = q + [{"query": "мото интерком", "clicks": 0.0, "impressions": 500.0, "ctr": 0.0, "position": 12.0}]
res2 = g.analyze(q2, pages)
check("analyze sort by impressions", [r["query"] for r in res2["gaps"]][:2] == ["мото интерком", "мотогарнитура для двоих"])
check("analyze striking sort", [r["query"] for r in res2["striking"]] == ["мото интерком", "как выбрать мотогарнитуру"])

# to_markdown
md = g.to_markdown(res)
check("md title", md.startswith("# Query gaps"))
check("md sections", "## Gap queries: visible, but no page targets them" in md and "## Striking distance: positions 8-20" in md
      and "## Weak CTR in the top 5" in md)
check("md row", "| мотогарнитура для двоих | 150 | 0 | 0.0% | 25.0 | https://x.ru/sena-50s/ | 0.50 |" in md)
check("md ctr percent", "| как выбрать мотогарнитуру | 200 | 5 | 2.5% | 9.3 |" in md)
empty = g.analyze([], pages)
check("md none", "None." in g.to_markdown(empty))
check("md newline", md.endswith("\n"))

# CLI
with tempfile.TemporaryDirectory() as tmp:
    qp = os.path.join(tmp, "Queries.csv")
    pp = os.path.join(tmp, "pages.csv")
    op = os.path.join(tmp, "out.json")
    with open(qp, "w", encoding="utf-8") as fh:
        fh.write(gsc)
    with open(pp, "w", encoding="utf-8", newline="") as fh:
        fh.write("url,title\n")
        for u, t in pages:
            fh.write('%s,"%s"\n' % (u, t))
    check("read pages csv", g.read_pages_csv(pp) == pages)
    with contextlib.redirect_stdout(io.StringIO()):
        code = g.main([qp, "--pages", pp, "--format", "json", "--out", op])
    with open(op, encoding="utf-8") as fh:
        j = json.load(fh)
    check("cli json", code == 0 and set(["gaps", "striking", "low_ctr"]) <= set(j))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = g.main([qp, "--pages", pp, "--format", "csv"])
    lines = buf.getvalue().strip().splitlines()
    check("cli csv", code == 0 and lines[0].replace("\r", "") == "list,query,impressions,clicks,ctr,position,page,score"
          and len(lines) == 4)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        code = g.main([os.path.join(tmp, "missing.csv"), "--pages", pp])
    check("cli missing file", code == 2)

print(json.dumps({"ok": not bad, "total": total, "bad": bad}))
sys.exit(0 if not bad else 1)
