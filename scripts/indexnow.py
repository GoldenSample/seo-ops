#!/usr/bin/env python3
"""
indexnow.py: tell IndexNow search engines which URLs of a site were added, changed or removed.
Python 3.9+, standard library only.

IndexNow reaches Bing, Yandex, Seznam, Naver, Amazon, Yep and the other participants with one request.
Google does not take part. A submission does not guarantee indexing (https://www.indexnow.org/faq).

Dry run by default: nothing is sent and no file is written without --submit.

Modes (pick one; default --since-hours 26):
  --since-hours N   URLs whose sitemap lastmod is within the last N hours (stateless, for a daily cron)
  --state FILE      URLs whose lastmod changed or that left the sitemap since the last run (first run = baseline)
  --all             every URL in the sitemap (once, at launch)
  --url URL         the given URLs (repeatable)

Usage
  python indexnow.py --site example.com --keys keys.env --check-key   # key from --key or the keys file
  python indexnow.py --site example.com --keys keys.env               # dry run: what would be sent
  python indexnow.py --site example.com --keys keys.env --submit --sent-log indexnow-sent.json

The key comes from --key or from INDEXNOW_KEY of the keys file named with --keys (seo_keys.py), never from
the environment.

Rules kept: only changed URLs; one URL not more often than every 10 minutes (--sent-log); at most 10,000
URLs per POST; after 429 nothing is sent until Retry-After has passed. Exit codes: 0 sent or nothing to send,
1 rejected or blocked, 2 bad key, bad arguments or unreadable sitemap.
Source: https://github.com/GoldenSample/seo-ops (MIT). Written by a local model from a spec and tests
(tests/test_indexnow.py), reviewed by Claude.
"""
import argparse
import datetime
import email.utils
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timezone, timedelta

VERSION = "1.2.0"
UA = "seo-ops-indexnow/1.0 (+https://github.com/GoldenSample/seo-ops)"
ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_BATCH = 10000
RESEND_WINDOW = 600
STATUS_TEXT = {
    200: "OK: URLs received",
    202: "Accepted: URLs received, key validation pending",
    400: "Bad request: invalid format",
    403: "Forbidden: the key is not valid (key file missing or its content does not match)",
    422: "Unprocessable: URLs are not on this host, or the key does not match the protocol",
    429: "Too many requests: the engine suspects spam; wait before sending again",
}


def valid_key(key) -> bool:
    if not isinstance(key, str) or not key:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9-]{8,128}", key))


def parse_lastmod(s) -> datetime.datetime:
    if not isinstance(s, str) or not s:
        return None
    s = s.strip()
    pattern = r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2})(?::(\d{2}))?(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})?)?$"
    match = re.match(pattern, s)
    if not match:
        return None

    date_str, time_h_m, time_s, frac, zone = match.groups()
    try:
        y, m, d = map(int, date_str.split("-"))
        hh, mm, ss, ms = 0, 0, 0, 0
        if time_h_m:
            hh, mm = map(int, time_h_m.split(":"))
            if time_s:
                ss = int(time_s)
            if frac:
                ms = int(frac.ljust(6, "0")[:6])

        tz = timezone.utc
        if zone and zone != "Z":
            sign = 1 if zone[0] == "+" else -1
            zh, zm = map(int, zone[1:].split(":"))
            tz = timezone(timedelta(hours=sign * zh, minutes=sign * zm))

        dt = datetime.datetime(y, m, d, hh, mm, ss, ms, tzinfo=tz)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_sitemap(text) -> tuple:
    if not text:
        raise ValueError("Empty sitemap text")
    text = text.lstrip("\ufeff").strip()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}")

    tag = root.tag.split("}")[-1].lower()
    if tag == "urlset":
        entries = []
        for child in root:
            if child.tag.split("}")[-1].lower() != "url":
                continue
            loc, lastmod = "", ""
            for sub in child:
                sub_tag = sub.tag.split("}")[-1].lower()
                if sub_tag == "loc":
                    loc = sub.text.strip() if sub.text else ""
                elif sub_tag == "lastmod":
                    lastmod = sub.text.strip() if sub.text else ""
            if loc:
                entries.append((loc, lastmod))
        return entries, []
    elif tag == "sitemapindex":
        children = []
        for child in root:
            if child.tag.split("}")[-1].lower() == "sitemap":
                for sub in child:
                    if sub.tag.split("}")[-1].lower() == "loc":
                        loc = sub.text.strip() if sub.text else ""
                        if loc:
                            children.append(loc)
        return [], children
    return [], []


def collect(sitemap_url, fetch, max_children=50) -> tuple:
    status, text = fetch(sitemap_url)
    if status != 200:
        raise ValueError(f"Top sitemap {sitemap_url} returned status {status}")
    try:
        entries, children = parse_sitemap(text)
    except ValueError as e:
        raise ValueError(f"Top sitemap {sitemap_url} is invalid: {e}")

    all_entries, failed, seen_locs = [], [], set()
    if entries:
        for loc, lm in entries:
            if loc not in seen_locs:
                seen_locs.add(loc)
                all_entries.append((loc, lm))
    if children:
        for child_url in children[:max_children]:
            c_status, c_text = fetch(child_url)
            if c_status == 200:
                try:
                    c_entries, _ = parse_sitemap(c_text)
                    for loc, lm in c_entries:
                        if loc not in seen_locs:
                            seen_locs.add(loc)
                            all_entries.append((loc, lm))
                except ValueError:
                    failed.append(child_url)
            else:
                failed.append(child_url)
    return all_entries, failed


def same_host(urls, host) -> tuple:
    kept, dropped, host_low = [], [], host.lower()
    for url in urls:
        if urllib.parse.urlsplit(url).netloc.lower() == host_low:
            kept.append(url)
        else:
            dropped.append(url)
    return kept, dropped


def changed_since(entries, since) -> list:
    return [loc for loc, lm in entries if (dt := parse_lastmod(lm)) and dt >= since]


def diff_state(entries, state) -> tuple:
    new_state = {loc: lm for loc, lm in entries}
    if not state:
        return [], [], new_state
    changed = [loc for loc, lm in entries if loc not in state or state[loc] != lm]
    removed = [loc for loc in state if loc not in new_state]
    return changed, removed, new_state


def filter_recent(urls, sent, now, window=RESEND_WINDOW) -> tuple:
    send, skipped = [], []
    for url in urls:
        if url in sent and now - sent[url] < window:
            skipped.append(url)
        else:
            send.append(url)
    return send, skipped


def batches(urls, size=MAX_BATCH) -> list:
    return [urls[i : i + size] for i in range(0, len(urls), size)] if urls else []


def build_payload(host, key, urls, key_location=None) -> dict:
    p = {"host": host, "key": key}
    if key_location:
        p["keyLocation"] = key_location
    p["urlList"] = list(urls)
    return p


def retry_after_seconds(value, now) -> int:
    if not value: return 3600
    val = value.strip()
    if val.isdigit(): return int(val)
    try:
        dt = email.utils.parsedate_to_datetime(val)
        return max(0, int((dt - datetime.datetime.fromtimestamp(now, timezone.utc)).total_seconds()))
    except Exception: return 3600


def check_key(host, key, fetch, key_location=None) -> tuple:
    url = key_location or f"https://{host}/{key}.txt"
    status, text = fetch(url)
    ok = status == 200 and text.strip() == key
    return ok, f"URL {url} returned {status}. Content matched: {ok}"


def submit(endpoint, payload, post) -> tuple:
    return post(endpoint, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})


def http_fetch(url) -> tuple:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(50 * 1024 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception:
        return 0, ""


def http_post(url, body, headers) -> tuple:
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, {k.lower(): v for k, v in r.getheaders()}
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers} if e.headers else {}
    except Exception:
        return 0, {}


def load_json(path, default):
    if not os.path.exists(path):
        import copy
        return copy.deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        import copy
        return copy.deepcopy(default)


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main(argv=None, fetch=None, post=None, now=None, out=None) -> int:
    if argv is None: argv = sys.argv[1:]
    if fetch is None: fetch = http_fetch
    if post is None: post = http_post
    if now is None: now = time.time()
    if out is None: out = sys.stdout

    parser = argparse.ArgumentParser(description="Send added, changed or removed URLs to IndexNow (dry run by default).")
    parser.add_argument("--site", required=True, help="host, e.g. example.com")
    parser.add_argument("--key", help="IndexNow key (else INDEXNOW_KEY of the --keys file)")
    parser.add_argument("--keys", metavar="FILE", help="keys file (seo_keys.py) with INDEXNOW_KEY; the environment "
                        "is not read for keys")
    parser.add_argument("--key-location", help="URL of the key file when it is not https://HOST/KEY.txt")
    parser.add_argument("--sitemap", help="sitemap URL (default https://HOST/sitemap.xml)")
    parser.add_argument("--endpoint", default=ENDPOINT, help="IndexNow endpoint (default %(default)s)")
    parser.add_argument("--sent-log", help="JSON file that remembers sent URLs and a 429 block")
    parser.add_argument("--submit", action="store_true", help="really send (otherwise a dry run)")
    parser.add_argument("--check-key", action="store_true", help="only check the key file and exit")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--since-hours", type=float, help="lastmod within the last N hours (default 26)")
    group.add_argument("--state", help="JSON state file: send what changed since the last run")
    group.add_argument("--all", action="store_true", help="every sitemap URL")
    group.add_argument("--url", action="append", help="a URL to send (repeatable)")
    args = parser.parse_args(argv)

    host = args.site.replace("http://", "").replace("https://", "").split("/")[0].lower()
    keys = {}
    if args.keys:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import seo_keys  # noqa: E402  (same scripts folder)
        try:
            keys = seo_keys.keys_from_args(args.keys)
        except seo_keys.KeysFileError as e:
            print(f"error: {e}", file=out)
            return 2
    key = args.key or keys.get("INDEXNOW_KEY")
    if not key:
        print("error: no IndexNow key: pass --key KEY or --keys FILE with INDEXNOW_KEY (a dry run needs it too)",
              file=out)
        return 2
    if not valid_key(key):
        print("error: the key must be 8-128 characters of letters, digits or '-'", file=out)
        return 2

    if args.check_key:
        ok, detail = check_key(host, key, fetch, args.key_location)
        print(f"key file {'OK' if ok else 'FAIL'}: {detail}", file=out)
        return 0 if ok else 1

    urls, new_state, failed_children = [], {}, []
    if args.url:
        urls = args.url
    else:
        sitemap_url = args.sitemap or f"https://{host}/sitemap.xml"
        try:
            entries, failed_children = collect(sitemap_url, fetch)
        except ValueError as e:
            print(f"error: {e}", file=out)
            return 2
        if failed_children:
            print(f"warning: {len(failed_children)} child sitemaps failed: {failed_children[0]}", file=out)
        if args.all:
            urls = [loc for loc, lm in entries]
        elif args.state:
            old_state = load_json(args.state, {})
            changed, removed, new_state = diff_state(entries, old_state)
            if failed_children:
                urls, merged = changed, dict(old_state)
                merged.update(new_state)
                new_state = merged
            else:
                urls = changed + removed
        else:
            hrs = args.since_hours if args.since_hours is not None else 26.0
            since_dt = datetime.datetime.fromtimestamp(now, timezone.utc) - timedelta(hours=hrs)
            urls = changed_since(entries, since_dt)
            if entries and not urls and not any(parse_lastmod(lm) for _, lm in entries):
                print("warning: no lastmod found in sitemap; use --state to track changes", file=out)

    kept, dropped = same_host(urls, host)
    if dropped: print(f"dropped {len(dropped)} URLs on other hosts", file=out)
    urls = kept

    log = {"sent": {}, "blocked_until": 0}
    if args.sent_log: log = load_json(args.sent_log, log)
    if args.submit and log["blocked_until"] > now:
        utc_t = datetime.datetime.fromtimestamp(log["blocked_until"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"blocked until {utc_t}", file=out)
        return 1

    if log["sent"]:
        urls, skipped = filter_recent(urls, log["sent"], now)
        if skipped: print(f"skipped {len(skipped)} URLs sent less than 10 minutes ago", file=out)

    if not urls:
        print("nothing to send", file=out)
        if args.submit and args.state: save_json(args.state, new_state)
        return 0

    if not args.submit:
        print(f"dry run: {len(urls)} URLs would be sent to {args.endpoint}", file=out)
        for u in urls[:20]: print(f"  {u}", file=out)
        if len(urls) > 20: print(f"  and {len(urls) - 20} more", file=out)
        return 0

    ok_key, detail_key = check_key(host, key, fetch, args.key_location)
    if not ok_key:
        print(f"key file FAIL: {detail_key}", file=out)
        return 1

    url_batches = batches(urls)
    all_ok = True
    for i, batch in enumerate(url_batches, 1):
        status, headers = submit(args.endpoint, build_payload(host, key, batch, args.key_location), post)
        print(f"batch {i}/{len(url_batches)}: {len(batch)} URLs -> {status} {STATUS_TEXT.get(status, 'unexpected status')}", file=out)
        if status in (200, 202):
            for u in batch: log["sent"][u] = now
        elif status == 429:
            log["blocked_until"] = now + retry_after_seconds(headers.get("retry-after"), now)
            all_ok = False; break
        else:
            all_ok = False; break

    if args.sent_log:
        log["sent"] = {u: t for u, t in log["sent"].items() if now - t <= 86400}
        save_json(args.sent_log, log)
    if all_ok and args.state: save_json(args.state, new_state)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
