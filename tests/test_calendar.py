"""Tests for scripts/seo_calendar.py. Standard library only.

Run: python tests/test_calendar.py [path/to/seo_calendar.py]
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "seo_calendar.py")

spec = importlib.util.spec_from_file_location("seo_calendar", TARGET)
cal_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal_mod)

D = dt.date
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


def run_cli(*argv):
    out = io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = cal_mod.main(list(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 2
    return code, out.getvalue()


TEMPLATE = {
    "schema": "seo-ops-calendar/1",
    "about": "test",
    "site": "",
    "launch": "",
    "tasks": [
        {"id": "a-once", "kind": "once", "offset_days": 0, "what": "Launch step", "who": "human", "skill": "s"},
        {"id": "b-once-14", "kind": "once", "offset_days": 14, "what": "Index check", "who": "human", "skill": "s"},
        {"id": "w-7", "kind": "every", "every_days": 7, "what": "Weekly", "who": "cron", "skill": "s"},
        {"id": "m-30", "kind": "every", "every_days": 30, "offset_days": 3, "what": "Monthly", "who": "human", "skill": "s"},
        {"id": "e-deploy", "kind": "event", "trigger": "deploy", "what": "On deploy", "who": "cron", "skill": "s"},
    ],
}


def copy(o):
    return json.loads(json.dumps(o))


# to_date
check("to_date valid", cal_mod.to_date("2026-12-01") == D(2026, 12, 1))
check("to_date bad format", raises(ValueError, cal_mod.to_date, "2026-1-1"))
check("to_date bad day", raises(ValueError, cal_mod.to_date, "2026-02-30"))
check("to_date not str", raises(ValueError, cal_mod.to_date, 20261201))

# validate template
check("validate good template", cal_mod.validate(copy(TEMPLATE), template=True) == [])
t = copy(TEMPLATE); t["tasks"][1]["id"] = "a-once"
check("validate duplicate id", len(cal_mod.validate(t, template=True)) >= 1)
t = copy(TEMPLATE); t["tasks"][0]["kind"] = "sometimes"
check("validate bad kind", len(cal_mod.validate(t, template=True)) >= 1)
t = copy(TEMPLATE); t["tasks"][2]["every_days"] = 0
check("validate every_days 0", len(cal_mod.validate(t, template=True)) >= 1)
t = copy(TEMPLATE); t["tasks"][2]["every_days"] = True
check("validate every_days bool", len(cal_mod.validate(t, template=True)) >= 1)
t = copy(TEMPLATE); del t["tasks"][4]["trigger"]
check("validate event without trigger", len(cal_mod.validate(t, template=True)) >= 1)
t = copy(TEMPLATE); del t["tasks"][0]["offset_days"]
check("validate once without offset", len(cal_mod.validate(t, template=True)) >= 1)
t = copy(TEMPLATE); t["tasks"][0]["who"] = "robot"
check("validate bad who", len(cal_mod.validate(t, template=True)) >= 1)
t = copy(TEMPLATE); t["tasks"][0]["id"] = "Bad_ID"
check("validate bad id", len(cal_mod.validate(t, template=True)) >= 1)
check("validate template as site calendar fails", len(cal_mod.validate(copy(TEMPLATE), template=False)) >= 1)

# init
tpl = copy(TEMPLATE)
site = cal_mod.init(tpl, "x.ru", D(2026, 12, 1))
by = {x["id"]: x for x in site["tasks"]}
check("init does not mutate template", tpl == TEMPLATE)
check("init site", site["site"] == "x.ru" and site["launch"] == "2026-12-01")
check("init keeps about", site.get("about") == "test")
check("init once offset 0", by["a-once"]["due"] == "2026-12-01")
check("init once offset 14", by["b-once-14"]["due"] == "2026-12-15")
check("init every default first", by["w-7"]["next"] == "2026-12-08" and by["w-7"]["last"] is None)
check("init every with offset", by["m-30"]["next"] == "2026-12-04")
check("init event untouched", "due" not in by["e-deploy"] and "next" not in by["e-deploy"])
check("init result validates", cal_mod.validate(site) == [])
bad_tpl = copy(TEMPLATE); bad_tpl["tasks"][0]["kind"] = "x"
check("init bad template raises", raises(ValueError, cal_mod.init, bad_tpl, "x.ru", D(2026, 12, 1)))

# due_date
check("due_date once", cal_mod.due_date(by["a-once"]) == D(2026, 12, 1))
check("due_date every", cal_mod.due_date(by["w-7"]) == D(2026, 12, 8))
check("due_date event", cal_mod.due_date(by["e-deploy"]) is None)

# buckets
c = copy(site)
for x in c["tasks"]:
    if x["id"] == "m-30":
        x["next"] = "2026-12-16"
c["tasks"].append({"id": "c-done", "kind": "once", "offset_days": 0, "due": "2026-12-01", "done": "2026-12-02",
                   "what": "Done one", "who": "human", "skill": "s"})
c["tasks"].append({"id": "s-soon", "kind": "every", "every_days": 7, "next": "2026-12-15", "last": None,
                   "what": "Soon one", "who": "human", "skill": "s"})
before = copy(c)
b = cal_mod.buckets(c, D(2026, 12, 8), within=7)
ids = {k: [x["id"] for x in v] for k, v in b.items()}
check("buckets keys", set(b) == {"overdue", "today", "soon", "later", "event", "done"})
check("buckets overdue", ids["overdue"] == ["a-once"])
check("buckets overdue days", b["overdue"][0]["days"] == -7 and b["overdue"][0]["due_on"] == "2026-12-01")
check("buckets today", ids["today"] == ["w-7"])
check("buckets soon", ids["soon"] == ["s-soon", "b-once-14"] or ids["soon"] == ["b-once-14", "s-soon"])
check("buckets soon sorted by date then id", ids["soon"] == ["b-once-14", "s-soon"])
check("buckets later", ids["later"] == ["m-30"])
check("buckets event", ids["event"] == ["e-deploy"])
check("buckets done", ids["done"] == ["c-done"])
check("buckets does not mutate", c == before)
bh = cal_mod.buckets(c, D(2026, 12, 8), within=7, who="human")
check("buckets who filter", all(x["who"] == "human" for v in bh.values() for x in v) and bh["today"] == [])

# mark_done
c2 = copy(site)
cal_mod.mark_done(c2, "w-7", D(2026, 12, 10))
w = [x for x in c2["tasks"] if x["id"] == "w-7"][0]
check("mark_done every", w["last"] == "2026-12-10" and w["next"] == "2026-12-17")
cal_mod.mark_done(c2, "a-once", D(2026, 12, 2))
check("mark_done once", [x for x in c2["tasks"] if x["id"] == "a-once"][0]["done"] == "2026-12-02")
check("mark_done once goes to done", "a-once" in [x["id"] for x in cal_mod.buckets(c2, D(2026, 12, 8))["done"]])
cal_mod.mark_done(c2, "e-deploy", D(2026, 12, 3))
check("mark_done event", [x for x in c2["tasks"] if x["id"] == "e-deploy"][0]["last"] == "2026-12-03")
check("mark_done unknown", raises(KeyError, cal_mod.mark_done, c2, "nope", D(2026, 12, 3)))

# slug and track_page
check("slug path", cal_mod.slug("https://x.ru/Kak-Vybrat/") == "kak-vybrat")
check("slug home", cal_mod.slug("https://x.ru/") == "home")
check("slug long", len(cal_mod.slug("https://x.ru/" + "a" * 80)) == 40)
check("slug collapse", cal_mod.slug("https://x.ru/a__b//c") == "a-b-c")
c3 = copy(site)
added = cal_mod.track_page(c3, "https://x.ru/kak-vybrat/", D(2026, 12, 1))
check("track ids", added == ["page-kak-vybrat-d7", "page-kak-vybrat-d21", "page-kak-vybrat-d90"])
dues = {x["id"]: x.get("due") for x in c3["tasks"]}
check("track dues", dues["page-kak-vybrat-d7"] == "2026-12-08" and dues["page-kak-vybrat-d21"] == "2026-12-22"
      and dues["page-kak-vybrat-d90"] == "2027-03-01")
check("track no duplicates", cal_mod.track_page(c3, "https://x.ru/kak-vybrat/", D(2026, 12, 1)) == [])
check("track result validates", cal_mod.validate(c3) == [])
check("track home", cal_mod.track_page(copy(site), "https://x.ru/", D(2026, 12, 1))[0] == "page-home-d7")

# to_markdown
md = cal_mod.to_markdown(b, "x.ru", D(2026, 12, 8))
check("md title", md.splitlines()[0] == "# SEO calendar: x.ru, 2026-12-08")
check("md overdue line", "- [ ] `a-once` Launch step (due 2026-12-01, human)" in md)
check("md sections", "## Overdue" in md and "## Today" in md and "## Next days" in md)
empty = {k: [] for k in ("overdue", "today", "soon", "later", "event", "done")}
check("md nothing due", "Nothing due." in cal_mod.to_markdown(empty, "x.ru", D(2026, 12, 8)))
check("md ends with newline", md.endswith("\n"))

# save and load
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "c.json")
    c4 = copy(site)
    c4["tasks"][0]["what"] = "Проверка: ёлка"
    cal_mod.save(p, c4)
    with open(p, encoding="utf-8") as fh:
        raw = fh.read()
    check("save keeps cyrillic", "Проверка: ёлка" in raw)
    check("load round trip", cal_mod.load(p) == c4)
    with open(os.path.join(tmp, "bad.json"), "w", encoding="utf-8") as fh:
        fh.write("{broken")
    check("load bad json", raises(ValueError, cal_mod.load, os.path.join(tmp, "bad.json")))
    with open(os.path.join(tmp, "bom.json"), "w", encoding="utf-8-sig") as fh:
        json.dump(c4, fh, ensure_ascii=False)
    check("load bom", cal_mod.load(os.path.join(tmp, "bom.json")) == c4)

# CLI
with tempfile.TemporaryDirectory() as tmp:
    tp = os.path.join(tmp, "tpl.json")
    with open(tp, "w", encoding="utf-8") as fh:
        json.dump(TEMPLATE, fh)
    out = os.path.join(tmp, "seo-calendar.json")
    code, text = run_cli("init", "--site", "x.ru", "--launch", "2026-12-01", "--template", tp, "--out", out)
    check("cli init", code == 0 and os.path.exists(out))
    code, text = run_cli("init", "--site", "x.ru", "--launch", "2026-12-01", "--template", tp, "--out", out)
    check("cli init refuses overwrite", code == 2)
    code, text = run_cli("init", "--site", "x.ru", "--launch", "2026-12-01", "--template", tp, "--out", out, "--force")
    check("cli init force", code == 0)
    code, text = run_cli("init", "--site", "x.ru", "--launch", "2026-13-01", "--template", tp, "--out", out, "--force")
    check("cli init bad date", code == 2)
    code, text = run_cli("due", "--calendar", out, "--date", "2026-12-08", "--format", "json")
    try:
        j = json.loads(text)
        ok = code == 0 and [x["id"] for x in j["buckets"]["overdue"]] == ["a-once", "m-30"] and j["within"] == 7
    except Exception:
        ok = False
    check("cli due json", ok)
    code, text = run_cli("due", "--calendar", out, "--date", "2026-12-08", "--strict")
    check("cli due strict overdue", code == 1)
    code, text = run_cli("due", "--calendar", out, "--date", "2026-11-01", "--strict")
    check("cli due strict clean", code == 0)
    code, text = run_cli("due", "--calendar", out, "--date", "2026-12-08", "--format", "md")
    check("cli due md", code == 0 and "# SEO calendar: x.ru, 2026-12-08" in text)
    code, text = run_cli("due", "--calendar", out, "--date", "2026-12-08", "--format", "text", "--who", "cron")
    check("cli due text", code == 0)
    code, text = run_cli("done", "nope", "--calendar", out, "--on", "2026-12-10")
    check("cli done unknown", code == 2)
    code, text = run_cli("done", "w-7", "--calendar", out, "--on", "2026-12-10")
    saved = cal_mod.load(out)
    w = [x for x in saved["tasks"] if x["id"] == "w-7"][0]
    check("cli done saves", code == 0 and w["next"] == "2026-12-17")
    code, text = run_cli("track", "https://x.ru/p", "--calendar", out, "--on", "2026-12-01")
    saved = cal_mod.load(out)
    check("cli track", code == 0 and any(x["id"] == "page-p-d7" for x in saved["tasks"]))
    code, text = run_cli("validate", "--calendar", out)
    check("cli validate ok", code == 0)
    code, text = run_cli("validate", "--calendar", tp, "--template")
    check("cli validate template", code == 0)
    code, text = run_cli("validate", "--calendar", tp)
    check("cli validate template as site fails", code == 2)
    code, text = run_cli("due", "--calendar", os.path.join(tmp, "missing.json"))
    check("cli due missing file", code == 2)

# the shipped template
real_tpl = os.path.join(HERE, "..", "templates", "calendar.json")
if os.path.exists(real_tpl):
    rt = cal_mod.load(real_tpl)
    check("shipped template validates", cal_mod.validate(rt, template=True) == [])
    rs = cal_mod.init(rt, "example.com", D(2026, 12, 1))
    check("shipped template inits", cal_mod.validate(rs) == [])

print(json.dumps({"ok": not bad, "total": total, "bad": bad}))
sys.exit(0 if not bad else 1)
