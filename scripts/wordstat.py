#!/usr/bin/env python3
"""
wordstat.py: Yandex Wordstat through the official API (Yandex Search API v2, Wordstat methods).
Python 3.9+, standard library only. Yandex Cloud bills each request; you need a key of your own.

Usage
  python wordstat.py top      "phrase" ... [--phrases FILE] [--num 50] [--regions 213,2] [--devices all]
  python wordstat.py dynamics "phrase" ... [--phrases FILE] [--period monthly|weekly|daily] [--from 2025-12-01]
                              [--to 2026-11-01] [--regions 213] [--devices all]
  python wordstat.py regions  "phrase" ... [--phrases FILE] [--region-type all|cities|regions] [--names]
  python wordstat.py tree
  every command: [--csv out.csv] [--json out.json] [--cache DIR] [--cache-days 7] [--per-hour 100] [--dry-run]

  top       how often the phrase was searched in the last 30 days, the queries that contain it and similar
            queries (numPhrases up to 2000)
  dynamics  searches per month, week or day (seasonality); --from is moved to the start of its period
  regions   where the phrase is searched: count, share and affinity index per region (last 30 days);
            --names adds region names from the regions tree
  tree      the regions tree with IDs (free)

Key, from your environment only: YANDEX_CLOUD_API_KEY (API key of a service account with the role
search-api.webSearch.user) or YANDEX_CLOUD_IAM_TOKEN (lives up to 12 hours); YANDEX_CLOUD_FOLDER_ID names the
folder (with a service-account key the API finds it by itself). The key never reaches the output.

Price and pace (Yandex pages checked 2026-11-26: https://aistudio.yandex.ru/ru/docs/search-api/pricing ,
https://aistudio.yandex.ru/ru/docs/search-api/concepts/limits): top and dynamics 20 RUB, regions 50 RUB per
1000 requests with VAT, tree free; quota 100 requests an hour and 10 a second. The script stays under
--per-hour (default 100) with a sliding one-hour window, so 300 phrases take a little over two hours; --dry-run
prints the requests, the price and the time and sends nothing. Answers are cached on disk (default
~/.cache/seo-ops/wordstat, outside any repo), so a broken run goes on where it stopped and a rerun within
--cache-days costs nothing.

Phrases go to the API as written. The Wordstat operators (-word, !form, +stopword, "quotes", [order],
(a|b)) are described for the Wordstat site (https://yandex.ru/support2/wordstat/ru/content/operators), not
on the API pages.

Exit codes: 0 every phrase answered; 1 the key was refused or a phrase failed; 2 bad arguments, no key, the
API gives no answer. Source: https://github.com/GoldenSample/seo-ops (MIT).
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo_check as sc  # noqa: E402  (same scripts folder)
import seo_index as si  # noqa: E402

VERSION = "1.1.0"
UA = "seo-ops-wordstat/%s (+https://github.com/GoldenSample/seo-ops)" % VERSION
API = "https://searchapi.api.cloud.yandex.net"
API_HOST = "searchapi.api.cloud.yandex.net"
METHODS = {"top": "/v2/wordstat/topRequests", "dynamics": "/v2/wordstat/dynamics",
           "regions": "/v2/wordstat/regions", "tree": "/v2/wordstat/getRegionsTree"}
PRICE = {"top": 20.0, "dynamics": 20.0, "regions": 50.0, "tree": 0.0}   # RUB per 1000 requests with VAT, 2026-11-26
DEVICES = {"all": "DEVICE_ALL", "desktop": "DEVICE_DESKTOP", "phone": "DEVICE_PHONE", "tablet": "DEVICE_TABLET"}
PERIODS = {"monthly": "PERIOD_MONTHLY", "weekly": "PERIOD_WEEKLY", "daily": "PERIOD_DAILY"}
REGION_TYPES = {"all": "REGION_ALL", "cities": "REGION_CITIES", "regions": "REGION_REGIONS"}
SECRET_ENV = ("YANDEX_CLOUD_API_KEY", "YANDEX_CLOUD_IAM_TOKEN")
HOUR = 3600.0
MIN_GAP = 0.2        # at most 5 requests a second (the quota allows 10)
WAIT_429 = 300.0     # pause after 429 without Retry-After
MAX_WAIT = 3600.0    # the longest the script waits for the quota in one run
MAX_PHRASE = 400     # the API limit for phrase
TIMEOUT = 60
HEADER = ("phrase", "фраза", "keyword", "query", "запрос",
          "ключ")


def default_cache():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "seo-ops", "wordstat")


# ---------------------------------------------------------------- input

def read_phrases(args):
    """(phrases in order without duplicates, problems)."""
    raw, problems = list(args.phrase or []), []
    if getattr(args, "phrases", None):
        try:
            with open(args.phrases, encoding="utf-8-sig") as fh:
                text = fh.read()
        except UnicodeDecodeError:
            with open(args.phrases, encoding="cp1251") as fh:
                text = fh.read()
        except OSError as e:
            return [], ["cannot read --phrases %s: %s" % (args.phrases, e)]
        lines = text.splitlines()
        if args.phrases.lower().endswith(".csv") and lines:
            delim = max((",", ";", "\t"), key=lines[0].count)
            rows = list(csv.reader(lines, delimiter=delim))
            if rows and rows[0] and rows[0][0].strip().lower() in HEADER:
                rows = rows[1:]
            raw += [r[0] for r in rows if r]
        else:
            raw += [x for x in lines if not x.lstrip().startswith("#")]
    out, seen = [], set()
    for p in raw:
        p = " ".join(p.split())
        if not p or p.lower() in seen:
            continue
        if len(p) > MAX_PHRASE:
            problems.append("longer than %d characters, skipped: %s..." % (MAX_PHRASE, p[:60]))
            continue
        seen.add(p.lower())
        out.append(p)
    return out, problems


def id_list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def period_start(day, period):
    if period == "monthly":
        return day.replace(day=1)
    if period == "weekly":
        return day - datetime.timedelta(days=day.weekday())
    return day


def default_from(today, period):
    if period == "monthly":
        y, mth = today.year - 1, today.month
        return datetime.date(y, mth, 1)
    if period == "weekly":
        return period_start(today - datetime.timedelta(weeks=12), "weekly")
    return today - datetime.timedelta(days=30)


def rfc3339(day):
    return day.strftime("%Y-%m-%dT00:00:00Z")


def body_for(cmd, phrase, a, folder):
    b = {}
    if cmd == "top":
        b = {"phrase": phrase, "numPhrases": str(a.num)}
    elif cmd == "dynamics":
        b = {"phrase": phrase, "period": PERIODS[a.period], "fromDate": rfc3339(a.from_day)}
        if a.to_day:
            b["toDate"] = rfc3339(a.to_day)
    elif cmd == "regions":
        b = {"phrase": phrase, "region": REGION_TYPES[a.region_type]}
    if cmd in ("top", "dynamics") and getattr(a, "regions", None):
        b["regions"] = id_list(a.regions)
    if cmd != "tree" and getattr(a, "devices", None):
        b["devices"] = [DEVICES[d] for d in id_list(a.devices)]
    if folder:
        b["folderId"] = folder
    return b


# ---------------------------------------------------------------- cache and pace

class Cache:
    def __init__(self, folder, days):
        self.folder, self.days = folder, days

    def file(self, cmd, body):
        h = hashlib.sha256(json.dumps([cmd, body], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return os.path.join(self.folder, "%s-%s.json" % (cmd, h[:32]))

    def get(self, cmd, body):
        if not self.folder or self.days <= 0:
            return None
        try:
            with open(self.file(cmd, body), encoding="utf-8") as fh:
                doc = json.load(fh)
            saved = datetime.datetime.fromisoformat(doc["saved"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if datetime.datetime.now(datetime.timezone.utc) - saved > datetime.timedelta(days=self.days):
            return None
        return doc.get("response")

    def put(self, cmd, body, response):
        if not self.folder:
            return
        os.makedirs(self.folder, exist_ok=True)
        path = self.file(cmd, body)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"saved": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                       "command": cmd, "phrase": body.get("phrase"), "response": response}, fh, ensure_ascii=False)
        os.replace(tmp, path)


class Pace:
    """At most per_hour requests in any sliding hour, and MIN_GAP between two requests."""

    def __init__(self, per_hour):
        self.per_hour = per_hour
        self.stamps = collections.deque()
        self.last = 0.0
        self.waited = 0.0

    def wait(self, say):
        now = time.monotonic()
        while self.stamps and now - self.stamps[0] >= HOUR:
            self.stamps.popleft()
        if len(self.stamps) >= self.per_hour:
            pause = HOUR - (now - self.stamps[0])
            say("quota window: %d requests in the last hour, waiting %.0f s" % (len(self.stamps), pause))
            time.sleep(max(0.0, pause))
            self.waited += max(0.0, pause)
            now = time.monotonic()
            while self.stamps and now - self.stamps[0] >= HOUR:
                self.stamps.popleft()
        gap = MIN_GAP - (now - self.last)
        if gap > 0:
            time.sleep(gap)
        self.last = time.monotonic()
        self.stamps.append(self.last)


# ---------------------------------------------------------------- API

class KeyRefused(Exception):
    pass


class Client:
    def __init__(self, auth, secrets, pace, say):
        self.auth, self.secrets, self.pace, self.say = auth, secrets, pace, say
        self.base = os.environ.get("SEO_OPS_API_BASE", "").strip().rstrip("/")
        self.opener = urllib.request.build_opener(sc._NoRedirect())
        self.sent = 0
        self.waited = 0.0

    def url(self, cmd):
        return (self.base + "/" + API_HOST if self.base else API) + METHODS[cmd]

    def once(self, cmd, body):
        self.pace.wait(self.say)
        self.sent += 1
        req = urllib.request.Request(self.url(cmd), data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     method="POST", headers={"Authorization": self.auth, "User-Agent": UA,
                                                             "Content-Type": "application/json",
                                                             "Accept": "application/json"})
        try:
            r = self.opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            r = e
        except Exception as e:
            return 0, None, self.secrets.scrub("%s: %s" % (type(e).__name__, e)), None
        try:
            raw = r.read(20_000_000)
        except Exception as e:
            return 0, None, self.secrets.scrub("read: %s" % e), None
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
        err = ""
        if status >= 300:
            msg = js.get("message") if isinstance(js, dict) else ""
            err = self.secrets.scrub(("%s %s" % (status, msg or "")).strip()[:300])
        return status, js, err, r.headers.get("Retry-After") if hasattr(r, "headers") and r.headers else None

    def post(self, cmd, body):
        """(response JSON, error). Raises KeyRefused on 401/403 and si.Unreachable when there is no answer."""
        while True:
            status, js, err, retry = self.once(cmd, body)
            if status == 0:
                raise si.Unreachable("Search API: " + err)
            if status in (401, 403):
                raise KeyRefused(err)
            if status == 429:
                pause = float(retry) if (retry or "").strip().isdigit() else WAIT_429
                if self.waited + pause > MAX_WAIT:
                    return None, "%s; waited %.0f s for the quota, giving up" % (err, self.waited)
                self.say("429 from the API: waiting %.0f s for the quota" % pause)
                time.sleep(pause)
                self.waited += pause
                continue
            if status != 200 or not isinstance(js, dict):
                return None, err or "%d without JSON" % status
            return js, ""


# ---------------------------------------------------------------- results

def num(x):
    try:
        return int(str(x))
    except (TypeError, ValueError):
        try:
            return float(str(x))
        except (TypeError, ValueError):
            return None


def flat_tree(regions, parent=None, depth=0, out=None):
    out = [] if out is None else out
    for r in regions or []:
        if not isinstance(r, dict):
            continue
        out.append({"id": str(r.get("id")), "label": r.get("label") or "", "parent_id": parent, "depth": depth})
        flat_tree(r.get("children"), str(r.get("id")), depth + 1, out)
    return out


def rows_for(cmd, phrase, js, names):
    if cmd == "top":
        rows = [{"phrase": phrase, "type": "total", "query": phrase, "count": num(js.get("totalCount"))}]
        rows += [{"phrase": phrase, "type": "top", "query": r.get("phrase"), "count": num(r.get("count"))}
                 for r in js.get("results") or [] if isinstance(r, dict)]
        rows += [{"phrase": phrase, "type": "similar", "query": r.get("phrase"), "count": num(r.get("count"))}
                 for r in js.get("associations") or [] if isinstance(r, dict)]
        return rows
    if cmd == "dynamics":
        return [{"phrase": phrase, "date": (r.get("date") or "")[:10], "count": num(r.get("count")),
                 "share": num(r.get("share"))} for r in js.get("results") or [] if isinstance(r, dict)]
    if cmd == "regions":
        return [{"phrase": phrase, "region": str(r.get("region")), "region_name": names.get(str(r.get("region")), ""),
                 "count": num(r.get("count")), "share": num(r.get("share")),
                 "affinity_index": num(r.get("affinityIndex"))} for r in js.get("results") or [] if isinstance(r, dict)]
    return flat_tree(js.get("regions"))


COLUMNS = {"top": ("phrase", "type", "query", "count"), "dynamics": ("phrase", "date", "count", "share"),
           "regions": ("phrase", "region", "region_name", "count", "share", "affinity_index"),
           "tree": ("id", "label", "parent_id", "depth")}


def summary(cmd, phrase, rows):
    if cmd == "top":
        total = rows[0]["count"] if rows else None
        top = ["%s (%s)" % (r["query"], r["count"]) for r in rows if r["type"] == "top"][:3]
        return "%s: %s searches in 30 days; contains: %s" % (phrase, total, ", ".join(top) or "-")
    if cmd == "dynamics":
        if not rows:
            return "%s: no points" % phrase
        peak = max(rows, key=lambda r: r["count"] or 0)
        return "%s: %d points, peak %s on %s, last %s on %s" % (phrase, len(rows), peak["count"], peak["date"],
                                                                rows[-1]["count"], rows[-1]["date"])
    if cmd == "regions":
        top = ["%s %s (%s)" % (r["region"], r["region_name"], r["share"]) if r["region_name"]
               else "%s (%s)" % (r["region"], r["share"]) for r in sorted(rows, key=lambda r: -(r["count"] or 0))[:3]]
        return "%s: %d regions; most: %s" % (phrase, len(rows), ", ".join(top) or "-")
    return "%d regions in the tree" % len(rows)


# ---------------------------------------------------------------- main

def build_parser():
    ap = argparse.ArgumentParser(description="Yandex Wordstat through the official Search API (your key, paid per "
                                             "request).")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--csv", help="write the rows as CSV (UTF-8)")
        p.add_argument("--json", help="write the raw answers and the rows as JSON")
        p.add_argument("--cache", default=default_cache(), help="folder for cached answers (default %(default)s)")
        p.add_argument("--cache-days", type=int, default=7, help="reuse cached answers this young (0 = never)")
        p.add_argument("--per-hour", type=int, default=100, help="requests per sliding hour (Yandex quota 100)")
        p.add_argument("--dry-run", action="store_true", help="print requests, price and time; send nothing")

    def phrases(p):
        p.add_argument("phrase", nargs="*")
        p.add_argument("--phrases", help="file with one phrase per line, or a CSV with phrases in the first column")
        p.add_argument("--devices", help="all, desktop, phone, tablet (comma separated, up to 3)")

    p = sub.add_parser("top", help="frequency, queries that contain the phrase, similar queries")
    phrases(p)
    p.add_argument("--num", type=int, default=50, help="queries to return, 1-2000 (default 50)")
    p.add_argument("--regions", help="region IDs, comma separated (wordstat.py tree lists them)")
    common(p)
    p = sub.add_parser("dynamics", help="searches per month, week or day")
    phrases(p)
    p.add_argument("--period", choices=sorted(PERIODS), default="monthly")
    p.add_argument("--from", dest="from_", help="YYYY-MM-DD (default: 12 months, 12 weeks or 30 days back)")
    p.add_argument("--to", help="YYYY-MM-DD")
    p.add_argument("--regions", help="region IDs, comma separated")
    common(p)
    p = sub.add_parser("regions", help="where the phrase is searched")
    phrases(p)
    p.add_argument("--region-type", choices=sorted(REGION_TYPES), default="all")
    p.add_argument("--names", action="store_true", help="add region names from the regions tree (free request)")
    common(p)
    p = sub.add_parser("tree", help="the regions tree with IDs (free)")
    p.set_defaults(phrase=[], phrases=None)
    common(p)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = build_parser()
    a = ap.parse_args(argv)
    secrets = si.Secrets()
    for k in SECRET_ENV:
        secrets.add(os.environ.get(k, ""))

    def say(s=""):
        print(secrets.scrub(s))
    if not a.cmd:
        ap.print_usage()
        return 2
    problem = si.api_base_problem()
    if problem:
        say("error: " + problem)
        return 2
    if a.per_hour < 1:
        say("error: --per-hour must be 1 or more")
        return 2
    if a.cmd == "top" and not 1 <= a.num <= 2000:
        say("error: --num must be 1-2000")
        return 2
    if getattr(a, "devices", None):
        bad_dev = [d for d in id_list(a.devices) if d not in DEVICES]
        if bad_dev or len(id_list(a.devices)) > 3:
            say("error: --devices takes up to 3 of %s" % ", ".join(sorted(DEVICES)))
            return 2
    if a.cmd == "dynamics":
        try:
            today = datetime.date.today()
            a.from_day = period_start(datetime.date.fromisoformat(a.from_), a.period) if a.from_ \
                else default_from(today, a.period)
            a.to_day = datetime.date.fromisoformat(a.to) if a.to else None
        except ValueError:
            say("error: --from and --to take YYYY-MM-DD")
            return 2
    if a.cmd == "tree":
        phrase_list, problems = [None], []
    else:
        phrase_list, problems = read_phrases(a)
        if not phrase_list:
            say("error: no phrase (give phrases or --phrases FILE)" + ("; " + "; ".join(problems) if problems else ""))
            return 2
    folder = os.environ.get("YANDEX_CLOUD_FOLDER_ID", "").strip()
    cache = Cache(a.cache, a.cache_days)
    bodies = [(p, body_for(a.cmd, p, a, folder)) for p in phrase_list]
    want_names = a.cmd == "regions" and a.names
    tree_body = body_for("tree", None, a, folder)
    todo = [b for _, b in bodies if cache.get(a.cmd, b) is None]
    extra_tree = 1 if want_names and cache.get("tree", tree_body) is None else 0
    if a.dry_run:
        n = len(todo) + extra_tree
        cost = len(todo) * PRICE[a.cmd] / 1000.0
        hours = max(0, len(todo) + extra_tree - 1) // a.per_hour
        say("dry run: %d %s requests to send, %d answered from the cache%s" % (
            len(todo), a.cmd, len(bodies) - len(todo), ", plus 1 free tree request" if extra_tree else ""))
        say("price: about %.2f RUB (%s RUB per 1000, checked 2026-11-26)" % (cost, PRICE[a.cmd]))
        say("time: %s at --per-hour %d" % ("under a minute" if hours == 0 else "about %d h" % hours, a.per_hour)
            if n else "time: nothing to send")
        for p in problems:
            say("skipped: " + p)
        return 0
    key = os.environ.get("YANDEX_CLOUD_API_KEY", "").strip()
    iam = os.environ.get("YANDEX_CLOUD_IAM_TOKEN", "").strip()
    if not key and not iam and (todo or extra_tree):
        say("error: no YANDEX_CLOUD_API_KEY or YANDEX_CLOUD_IAM_TOKEN in the environment (see the docstring of "
            "this script for how to get one); --dry-run works without a key")
        return 2
    client = Client("Api-Key " + key if key else "Bearer " + iam, secrets, Pace(a.per_hour), say)
    names, errors, results, all_rows, cached = {}, list(problems), {}, [], 0
    free = 0      # requests of the free regions tree, sent for --names: not priced
    try:
        if want_names:
            js = cache.get("tree", tree_body)
            if js is None:
                before = client.sent
                js, err = client.post("tree", tree_body)
                free = client.sent - before
                if js is not None:
                    cache.put("tree", tree_body, js)
                else:
                    errors.append("regions tree: " + err)
            names = {r["id"]: r["label"] for r in flat_tree((js or {}).get("regions"))}
        for phrase, body in bodies:
            js = cache.get(a.cmd, body)
            if js is not None:
                cached += 1
            else:
                js, err = client.post(a.cmd, body)
                if js is None:
                    errors.append("%s: %s" % (phrase or "tree", err))
                    continue
                cache.put(a.cmd, body, js)
            rows = rows_for(a.cmd, phrase, js, names)
            results[phrase or "tree"] = js
            all_rows += rows
            say(summary(a.cmd, phrase, rows))
    except KeyRefused as e:
        say("KEY REFUSED: %s: check the key, its role search-api.webSearch.user and YANDEX_CLOUD_FOLDER_ID" % e)
        return 1
    except si.Unreachable as e:
        say("API UNREACHABLE: %s" % e)
        return 2
    cost = (client.sent - free) * PRICE[a.cmd] / 1000.0
    say("requests sent: %d, from the cache: %d, about %.2f RUB; errors: %d" % (client.sent, cached, cost, len(errors)))
    for e in errors:
        say("error: " + e)
    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS[a.cmd])
            w.writeheader()
            for r in all_rows:
                w.writerow({k: "" if r.get(k) is None else r.get(k) for k in COLUMNS[a.cmd]})
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            fh.write(secrets.scrub(json.dumps({
                "version": VERSION, "command": a.cmd,
                "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "requests_sent": client.sent, "from_cache": cached, "cost_rub": round(cost, 4), "errors": errors,
                "rows": all_rows, "answers": results}, ensure_ascii=False, indent=1)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
