#!/usr/bin/env python3
"""
seo_calendar.py: the SEO calendar of one site. Python 3.9+, standard library only.

The template (templates/calendar.json) lists what to do once at launch, what to repeat and on which
events. `init` turns it into the site's own calendar with real dates; `due` shows what is due;
`done` records a finished task (a recurring task moves to its next date); `skip` records that a task does
not apply to this site, with the reason; `track` adds day-7, day-21 and day-90 measurements for a new or
changed page.

Usage
  python seo_calendar.py init --site example.com --launch 2026-12-01 [--out seo-calendar.json]
  python seo_calendar.py due [--within 7] [--who human|cron|all] [--format text|json|md] [--strict]
  python seo_calendar.py done launch-robots [--on 2026-12-01]
  python seo_calendar.py skip launch-product-feeds --reason "no product catalog" [--on 2026-12-01] [--undo]
  python seo_calendar.py track https://example.com/new-page/ [--on 2026-12-03]
  python seo_calendar.py validate [--calendar FILE]          a site calendar
  python seo_calendar.py validate --template [FILE]          a template (FILE, else --calendar)

Exit codes: 0 ok; 1 with --strict when something is overdue; 2 bad input.
Source: https://github.com/GoldenSample/seo-ops (MIT). Written by a local model from a spec and
tests (tests/test_calendar.py), reviewed by Claude.
"""
import argparse
import copy
import datetime
import json
import os
import re
import sys
import tempfile
from urllib.parse import urlsplit

VERSION = "1.1.1"

def to_date(s) -> datetime.date:
    if not isinstance(s, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        raise ValueError(f"Invalid date format: {s}")
    try:
        return datetime.date.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"Invalid date: {s}") from e

def validate(cal, template=False) -> list:
    errors = []
    if not isinstance(cal, dict):
        return ["Calendar must be a dictionary"]
    
    tasks = cal.get("tasks")
    if not isinstance(tasks, list):
        return ["'tasks' must be a list"]

    ids = set()
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"Task {i} is not a dictionary")
            continue
        
        tid = task.get("id")
        if not tid or not isinstance(tid, str) or not re.match(r'^[a-z0-9][a-z0-9-]*$', tid):
            errors.append(f"Task {i} has invalid or missing id")
        elif tid in ids:
            errors.append(f"Duplicate task id: {tid}")
        else:
            ids.add(tid)

        kind = task.get("kind")
        if kind not in ("once", "every", "event"):
            errors.append(f"Task {tid or i} has invalid kind: {kind}")
        
        who = task.get("who")
        if who not in ("cron", "human"):
            errors.append(f"Task {tid or i} has invalid who: {who}")
        
        what = task.get("what")
        if not what or not isinstance(what, str):
            errors.append(f"Task {tid or i} has empty or missing 'what'")

        if kind == "once":
            off = task.get("offset_days")
            if not isinstance(off, int) or isinstance(off, bool) or off < 0:
                errors.append(f"Task {tid or i} (once) must have int offset_days >= 0")
        elif kind == "every":
            ev = task.get("every_days")
            if not isinstance(ev, int) or isinstance(ev, bool) or ev < 1:
                errors.append(f"Task {tid or i} (every) must have int every_days >= 1")
            off = task.get("offset_days")
            if off is not None and (not isinstance(off, int) or isinstance(off, bool) or off < 0):
                errors.append(f"Task {tid or i} (every) offset_days must be int >= 0")
        elif kind == "event":
            trig = task.get("trigger")
            if not trig or not isinstance(trig, str):
                errors.append(f"Task {tid or i} (event) must have non-empty str trigger")

        if not template:
            if kind == "once":
                due = task.get("due")
                if not due:
                    errors.append(f"Task {tid or i} (once) missing due date")
                else:
                    try: to_date(due)
                    except ValueError: errors.append(f"Task {tid or i} (once) has invalid due date")
            elif kind == "every":
                nxt = task.get("next")
                if not nxt:
                    errors.append(f"Task {tid or i} (every) missing next date")
                else:
                    try: to_date(nxt)
                    except ValueError: errors.append(f"Task {tid or i} (every) has invalid next date")
            
            for field in ("done", "last"):
                val = task.get(field)
                if val is not None:
                    try: to_date(val)
                    except ValueError: errors.append(f"Task {tid or i} has invalid {field} date")

        sk = task.get("skipped")
        if sk is not None and template:
            errors.append(f"Task {tid or i} is skipped in a template: skip tasks in the site calendar")
        elif sk is not None:
            if not isinstance(sk, dict) or not isinstance(sk.get("reason"), str) or not sk["reason"].strip():
                errors.append(f"Task {tid or i} is skipped without a reason")
            else:
                try: to_date(sk.get("on"))
                except ValueError: errors.append(f"Task {tid or i} has invalid skipped date")

    if not template:
        site = cal.get("site")
        if not site or not isinstance(site, str):
            errors.append("Site calendar must have a non-empty 'site' string")
        
        launch = cal.get("launch")
        if launch:
            try: to_date(launch)
            except ValueError: errors.append("Invalid launch date")

    return errors

def init(template, site, launch) -> dict:
    errs = validate(template, template=True)
    if errs:
        raise ValueError("; ".join(errs))
    
    cal = copy.deepcopy(template)
    cal["site"] = site
    cal["launch"] = launch.isoformat()
    
    for task in cal["tasks"]:
        if task["kind"] == "once":
            task["due"] = (launch + datetime.timedelta(days=task["offset_days"])).isoformat()
        elif task["kind"] == "every":
            off = task.get("offset_days", task["every_days"])
            task["next"] = (launch + datetime.timedelta(days=off)).isoformat()
            task["last"] = None
    return cal

def due_date(task) -> datetime.date or None:
    if task["kind"] == "once":
        if task.get("done"): return None
        return to_date(task.get("due"))
    if task["kind"] == "every":
        return to_date(task.get("next"))
    return None

def buckets(cal, today, within=7, who="all") -> dict:
    b = {"overdue": [], "today": [], "soon": [], "later": [], "event": [], "done": [], "skipped": []}
    for task in cal.get("tasks", []):
        if who != "all" and task.get("who") != who:
            continue
        
        t_copy = task.copy()
        due = due_date(task)
        t_copy["due_on"] = due.isoformat() if due else None
        t_copy["days"] = (due - today).days if due else None
        
        if task.get("skipped"):
            b["skipped"].append(t_copy)
        elif task["kind"] == "once" and task.get("done"):
            b["done"].append(t_copy)
        elif task["kind"] == "event":
            b["event"].append(t_copy)
        elif t_copy["days"] is None:
            continue
        elif t_copy["days"] < 0:
            b["overdue"].append(t_copy)
        elif t_copy["days"] == 0:
            b["today"].append(t_copy)
        elif t_copy["days"] <= within:
            b["soon"].append(t_copy)
        else:
            b["later"].append(t_copy)

    for k in ("overdue", "today", "soon", "later"):
        b[k].sort(key=lambda x: (x["due_on"], x["id"]))
    for k in ("event", "done", "skipped"):
        b[k].sort(key=lambda x: x["id"])
    return b

def mark_done(cal, task_id, on) -> dict:
    task = next((t for t in cal["tasks"] if t["id"] == task_id), None)
    if not task:
        raise KeyError(f"Task {task_id} not found")
    task.pop("skipped", None)  # done after skip: the task applies after all
    if task["kind"] == "once":
        task["done"] = on.isoformat()
    elif task["kind"] == "every":
        task["last"] = on.isoformat()
        task["next"] = (on + datetime.timedelta(days=task["every_days"])).isoformat()
    elif task["kind"] == "event":
        task["last"] = on.isoformat()
    return cal

def skip_task(cal, task_id, on, reason) -> dict:
    """Record that a task does not apply to this site. `done` or `unskip_task` brings it back."""
    task = next((t for t in cal["tasks"] if t["id"] == task_id), None)
    if not task:
        raise KeyError(f"Task {task_id} not found")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError('skip needs a reason: --reason "..."')
    task["skipped"] = {"on": on.isoformat(), "reason": reason}
    return cal


def unskip_task(cal, task_id) -> bool:
    task = next((t for t in cal["tasks"] if t["id"] == task_id), None)
    if not task:
        raise KeyError(f"Task {task_id} not found")
    return task.pop("skipped", None) is not None


def slug(url) -> str:
    path = urlsplit(url).path
    s = path.lower()
    s = re.sub(r'[^a-z0-9]', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    s = s[:40].strip('-')
    return s if s else "home"

def track_page(cal, url, published, offsets=(7, 21, 90)) -> list:
    added = []
    s_val = slug(url)
    existing_ids = {t["id"] for t in cal["tasks"]}
    for n in offsets:
        tid = f"page-{s_val}-d{n}"
        if tid not in existing_ids:
            due = (published + datetime.timedelta(days=n)).isoformat()
            cal["tasks"].append({
                "id": tid, "kind": "once", "offset_days": n, "due": due,
                "what": f"Measure {url} at day {n}: impressions, clicks, position and AI citations against the baseline; apply the rollback rule if it got worse.",
                "who": "human", "skill": "seo-measure"
            })
            added.append(tid)
    return added

def to_markdown(b, site, today) -> str:
    lines = [f"# SEO calendar: {site}, {today.isoformat()}"]
    sections = [("overdue", "## Overdue"), ("today", "## Today"), ("soon", "## Next days")]
    any_due = False
    for key, header in sections:
        if b[key]:
            any_due = True
            lines.append(f"\n{header}")
            for t in b[key]:
                lines.append(f"- [ ] `{t['id']}` {t['what']} (due {t['due_on']}, {t['who']})")
    
    if not any_due:
        lines.append("\nNothing due.")
    
    return "\n".join(lines) + "\n"

def load(path) -> dict:
    try:
        with open(path, 'rt', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception as e:
        raise ValueError(f"Load error: {e}")

def save(path, cal):
    dir_name = os.path.dirname(path)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, encoding='utf-8', delete=False) as tf:
        json.dump(cal, tf, ensure_ascii=False, indent=2)
        tf.write('\n')
        temp_name = tf.name
    os.replace(temp_name, path)

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SEO calendar of one site: one-time launch tasks, recurring checks and event tasks.")
    subparsers = parser.add_subparsers(dest="cmd")

    p_init = subparsers.add_parser("init", help="make the site calendar from the template")
    p_init.add_argument("--site", required=True)
    p_init.add_argument("--launch", required=True)
    p_init.add_argument("--template")
    p_init.add_argument("--out")
    p_init.add_argument("--force", action="store_true")

    p_due = subparsers.add_parser("due", help="show what is due")
    p_due.add_argument("--calendar")
    p_due.add_argument("--date")
    p_due.add_argument("--within", type=int, default=7)
    p_due.add_argument("--who", choices=("all", "cron", "human"), default="all")
    p_due.add_argument("--format", choices=("text", "json", "md"), default="text")
    p_due.add_argument("--strict", action="store_true")

    p_done = subparsers.add_parser("done", help="mark a task done")
    p_done.add_argument("id")
    p_done.add_argument("--calendar")
    p_done.add_argument("--on")

    p_skip = subparsers.add_parser("skip", help="record that a task does not apply to this site, with the reason")
    p_skip.add_argument("id")
    p_skip.add_argument("--reason", help="why the task does not apply (required)")
    p_skip.add_argument("--calendar")
    p_skip.add_argument("--on")
    p_skip.add_argument("--undo", action="store_true", help="bring a skipped task back")

    p_track = subparsers.add_parser("track", help="add day 7, 21 and 90 checks for a page")
    p_track.add_argument("url")
    p_track.add_argument("--calendar")
    p_track.add_argument("--on")

    p_val = subparsers.add_parser("validate", help="check a site calendar, or a template with --template")
    p_val.add_argument("--calendar", help="site calendar (default seo-calendar.json)")
    p_val.add_argument("--as-template", action="store_true", help="check the --calendar file as a template")
    p_val.add_argument("--template", nargs="?", const=True, default=None, metavar="FILE",
                       help="check FILE as a template, like init --template FILE; without FILE, the --calendar file")

    args = parser.parse_args(argv)
    
    def get_default_paths():
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return "seo-calendar.json", os.path.join(base, "templates", "calendar.json")

    cal_def, tpl_def = get_default_paths()

    try:
        if args.cmd == "init":
            out_path = args.out or cal_def
            if os.path.exists(out_path) and not args.force:
                print(f"Error: {out_path} exists. Use --force to overwrite.")
                return 2
            tpl_path = args.template or tpl_def
            tpl = load(tpl_path)
            launch_date = to_date(args.launch)
            cal = init(tpl, args.site, launch_date)
            save(out_path, cal)
            print(f"created {out_path}: {len(cal['tasks'])} tasks")
            return 0

        elif args.cmd == "due":
            cal_path = args.calendar or cal_def
            cal = load(cal_path)
            errs = validate(cal)
            if errs:
                for e in errs: print(e)
                return 2
            today = to_date(args.date) if args.date else datetime.date.today()
            b = buckets(cal, today, args.within, args.who)
            if args.format == "text":
                for k in ("overdue", "today", "soon", "later", "event", "done", "skipped"):
                    print(f"{k.capitalize()} ({len(b[k])})")
                    for t in b[k]:
                        if k == "skipped":
                            print(f"  {t['id']}  {t['skipped'].get('on')}  {t['who']}  {t['skipped'].get('reason')}")
                        else:
                            print(f"  {t['id']}  {t.get('due_on') or '-'}  {t['who']}  {t['what']}")
            elif args.format == "json":
                print(json.dumps({"site": cal.get("site"), "date": today.isoformat(), "within": args.within, "buckets": b}, ensure_ascii=False, indent=2))
            elif args.format == "md":
                print(to_markdown(b, cal.get("site", ""), today), end="")
            
            if args.strict and b["overdue"]:
                return 1
            return 0

        elif args.cmd == "done":
            cal_path = args.calendar or cal_def
            cal = load(cal_path)
            on_date = to_date(args.on) if args.on else datetime.date.today()
            try:
                mark_done(cal, args.id, on_date)
                save(cal_path, cal)
                print(f"done {args.id} on {on_date}")
                return 0
            except KeyError as e:
                print(f"Error: {e}")
                return 2

        elif args.cmd == "skip":
            cal_path = args.calendar or cal_def
            cal = load(cal_path)
            try:
                if args.undo:
                    if not unskip_task(cal, args.id):
                        print(f"{args.id} is not skipped")
                        return 0
                    save(cal_path, cal)
                    print(f"{args.id} is back in the calendar")
                    return 0
                on_date = to_date(args.on) if args.on else datetime.date.today()
                skip_task(cal, args.id, on_date, args.reason)
            except KeyError as e:
                print(f"Error: {e}")
                return 2
            save(cal_path, cal)
            print(f"skipped {args.id} on {on_date}: {args.reason.strip()}")
            return 0

        elif args.cmd == "track":
            cal_path = args.calendar or cal_def
            cal = load(cal_path)
            on_date = to_date(args.on) if args.on else datetime.date.today()
            added = track_page(cal, args.url, on_date)
            if added:
                save(cal_path, cal)
                print(" ".join(added))
            else:
                print("already tracked")
            return 0

        elif args.cmd == "validate":
            as_template = args.as_template or args.template is not None
            cal_path = args.calendar or cal_def
            if isinstance(args.template, str):
                if args.calendar and os.path.abspath(args.calendar) != os.path.abspath(args.template):
                    print("Error: give one file: --template FILE, or --calendar FILE --as-template")
                    return 2
                cal_path = args.template
            cal = load(cal_path)
            errs = validate(cal, template=as_template)
            if errs:
                for e in errs: print(e)
                return 2
            print(f"ok: {len(cal.get('tasks', []))} tasks")
            return 0
        
        else:
            parser.print_help()
            return 0

    except ValueError as e:
        print(f"Error: {e}")
        return 2
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 2

if __name__ == "__main__":
    sys.exit(main())
