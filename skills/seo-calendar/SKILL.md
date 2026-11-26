---
name: seo-calendar
description: "The SEO calendar of one site and its cron jobs: templates/calendar.json (one-time launch tasks, recurring tasks every 1 to 365 days, event tasks), scripts/seo_calendar.py (init, due, done, skip, track, validate) and scheduled GitHub Actions workflows: daily health check and IndexNow, weekly external audit and site crawl, monthly issue with the human tasks for the next 31 days (with the index coverage report when the owner's keys are set), check after every deploy. Use when setting up recurring SEO for a site, asking what is due this week, marking SEO tasks done or not applicable, adding a task, or wiring SEO checks into CI, cron or GitHub Actions. RU triggers: SEO-календарь, регулярные задачи SEO, что сделать на этой неделе, расписание SEO, крон, GitHub Actions, автопроверка сайта, напоминания SEO, ежедневная проверка сайта."
license: MIT
---

# seo-calendar: one file of dates, scripts do the reminding

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo. Templates: `templates/` next to `scripts/`.

## The calendar file

`templates/calendar.json` (schema `seo-ops-calendar/1`) has 62 tasks. Each task:

| Field | Meaning |
|---|---|
| id | stable name, e.g. `launch-robots`, `weekly-audit`, `event-deploy` |
| kind | `once` (due = launch + offset_days), `every` (every `every_days`, first run at launch + `offset_days` or one period), `event` (on `trigger`) |
| what, check | the task and the check that proves it |
| who | `cron` = a script or workflow does it; `human` = a person does it in a dashboard |
| skill | the skill with the details |
| source, checked | the rule's source and the date it was last read |

## One-time (new site)

1. `launch-calendar`: `python scripts/seo_calendar.py init --site example.com --launch 2026-12-01` writes `seo-calendar.json` with real dates. Commit it to the site repo.
2. `python scripts/seo_calendar.py validate` must print `ok`.
3. Copy the workflows from `templates/workflows/` to the site repo `.github/workflows/`:
   - `seo-daily.yml`: health check of home, robots.txt, sitemap and 3 sampled pages; IndexNow for URLs whose lastmod changed in the last 26 hours.
   - `seo-weekly.yml`: full check with 12 pages, then `seo_crawl.py` over the whole site (input `crawl_pages`, default 200 URLs, `0` turns the crawl off; at most 540 seconds); the reports go to the run summary, and a crawl FAIL fails the run like a check FAIL.
   - `seo-monthly.yml`: opens one issue with the human tasks due in the next 31 days. With the index secrets it first runs `seo_index.py` and adds its report to the issue (inputs `index`: `on` or `off`, `gsc_property`, `google_max`); without them that step is skipped.
   - `seo-on-deploy.yml`: check and IndexNow after a deploy. Start it from your deploy workflow, from a deploy script with a `repository_dispatch` event of type `seo-deploy`, or by hand; the file header shows all three.
   They call the reusable workflow `GoldenSample/seo-ops/.github/workflows/seo-cron.yml@v1`.
4. In the repo settings: variable `SEO_SITE` = the canonical host (e.g. `example.com`); secret `INDEXNOW_KEY` if you use IndexNow (seo-yandex). With the secret, every check also checks the key file `https://SITE/KEY.txt`, and the daily and deploy runs send changed URLs. If another tool already sends IndexNow, add `indexnow: check` under `with:` (key file only); `indexnow: off` ignores the secret. Without the secret both are skipped. For the index report in the monthly issue, add the secrets `YANDEX_WEBMASTER_TOKEN` and, for Google, `GSC_CLIENT_ID`, `GSC_CLIENT_SECRET` and `GSC_REFRESH_TOKEN`, then uncomment the `secrets:` block of `seo-monthly.yml` (how to get them: seo-launch, Index coverage). They reach only the index step. A refused key or an index step that gets no answer fails the monthly run; the issue is opened first.
5. `launch-uptime`: an uptime monitor with an alert after two failures in a row. The daily job sees a dead site once a day; an uptime service sees it in minutes.
6. Watch the first scheduled runs in the Actions tab: they must be green. A red run means a FAIL on the site or a site that did not answer; the job summary says which.

## Recurring

| Id | Every | Who | What runs |
|---|---|---|---|
| daily-health | 1 day | cron | `seo_check.py --pages 3` |
| daily-indexnow | 1 day | cron | `indexnow.py --since-hours 26 --submit` |
| daily-console-alerts | 1 day | human | read Search Console, Yandex Webmaster and Bing messages |
| weekly-audit | 7 days | cron | `seo_check.py --pages 12` |
| weekly-crawl | 7 days | cron | `seo_crawl.py --max-pages 200 --max-seconds 540` (input `crawl_pages`) |
| monthly-calendar-issue | 30 days | cron | `seo_calendar.py due --who human --within 31 --format md` as an issue |
| monthly-index-coverage | 30 days | human; cron with the index secrets | `seo_index.py`, its report in the monthly issue |

The other recurring tasks (weekly, monthly, quarterly, yearly) are `human` and arrive in the monthly issue.

## Events

- `event-deploy`: run `seo-on-deploy.yml` after each deploy. In a deploy workflow add a last job with `uses: ./.github/workflows/seo-on-deploy.yml` and `secrets: inherit`; a deploy script on a server sends `{"event_type":"seo-deploy"}` to the repository dispatches API.
- `event-new-page`: `python scripts/seo_calendar.py track https://example.com/new-page/ --on 2026-12-03` adds measurement tasks at day 7, 21 and 90 (seo-measure).

## Daily use

```
python scripts/seo_calendar.py due                    # overdue, today, next 7 days
python scripts/seo_calendar.py due --who human --format md
python scripts/seo_calendar.py due --strict           # exit 1 when something is overdue
python scripts/seo_calendar.py done weekly-index-snapshot --on 2026-12-08
python scripts/seo_calendar.py skip launch-product-feeds --reason "no product catalog"
python scripts/seo_calendar.py skip launch-product-feeds --undo
```

`done` on an `every` task moves its next date by `every_days` from the day it was done. `skip` takes a task out of this site's calendar, with the reason: a one-time task that does not apply (no product catalog, no office), or a recurring task another tool already does. `due` lists skipped tasks apart with the reason, and the monthly issue leaves them out. `done` or `skip --undo` brings a skipped task back. `validate` refuses a skip without a reason. Commit `seo-calendar.json` after each change: the file is the history.

## Change the template

- Add a task: a new object with a unique `id` (lower case, digits, `-`), `kind`, `what`, `who` and the fields of its kind. Run `validate --template templates/calendar.json` on the template or `validate` on a site calendar.
- Change a frequency: edit `every_days`. A task that does not apply to one site: `skip` it in that site's calendar with the reason, not in the template. Remove a task from the template only when no site needs it.
- Keep `source` and `checked` honest: an empty source means the task is practice, not a rule.

## GitHub Actions facts (checked 2026-11-25)

- Scheduled workflows use POSIX cron syntax in UTC, run only on the default branch, and the shortest interval is every 5 minutes; runs can be delayed during high load: https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows (Official)
- In a public repository, scheduled workflows are disabled automatically when the repository has had no activity for 60 days. After a quiet stretch, open the Actions tab and enable the workflow again: https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow (Official)
