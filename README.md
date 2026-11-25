# seo-ops: SEO and GEO for a small site, as skills, scripts and cron jobs

[Русская версия](README.ru.md)

A Claude Code plugin and a plain toolbox for one small site or store: Google, Yandex, Bing and AI answers (AI Overviews, AI Mode, Alice AI, ChatGPT search, Perplexity). Every task is marked as **one-time** (do it once for a new site), **recurring** (a calendar runs it) or **event** (a runbook for a deploy, a price change, a traffic drop, a core update). Facts about search engines carry a source and the date they were checked, because they go stale.

- 10 skills that Claude loads when the topic comes up
- 4 scripts in Python 3.9+ with the standard library only: live-site check, site calendar, IndexNow, query gaps
- a 58-task calendar template and a decision log template
- a reusable GitHub Actions workflow and 4 caller templates: daily, weekly, monthly, after deploy

## Install

As a Claude Code plugin:

```
/plugin marketplace add GoldenSample/seo-ops
/plugin install seo-ops@goldensample-seo
```

Without Claude: `git clone https://github.com/GoldenSample/seo-ops` and run the scripts. Nothing to install.

## Start on a new site (one-time)

1. Check the live site and read every FAIL and WARN:
   `python scripts/seo_check.py example.com --pages 12`
2. In the site repository, make the site calendar and commit it:
   `python scripts/seo_calendar.py init --site example.com --launch 2026-12-01` writes `seo-calendar.json`.
3. Copy `templates/workflows/*.yml` to `.github/workflows/` of the site repository. Set the repository variable `SEO_SITE` (for example `example.com`) and, if you use IndexNow, the secret `INDEXNOW_KEY`.
4. Work through the launch tasks: `python scripts/seo_calendar.py due --who human`, then `python scripts/seo_calendar.py done <id>` for each.
5. Copy `templates/decision-log.md` and write the baseline before the first SEO change.

## Skills

| Skill | One-time (new site) | Recurring and events |
|---|---|---|
| `seo-ops` | site passport, calendar; the map of all skills, laws, evidence levels | quarterly re-check of rules and dates |
| `seo-launch` | 13 launch steps with a check each: redirects, robots, sitemap, canonical, structured data, errors, speed, trust pages | weekly audit, schema spot check, quarterly crawl; deploy, migration |
| `seo-calendar` | calendar and cron workflows | daily health and IndexNow, weekly audit, monthly issue; deploy |
| `seo-google` | Search Console, AI features included, Bing Webmaster, product markup, Merchant Center | index snapshot, AI visibility, crawler logs; core update |
| `seo-yandex` | Webmaster rights, region, Clean-param, Yandex Products feed, IndexNow key | daily IndexNow, console alerts; price change, data outage |
| `seo-geo` | AI crawler policy (search and user bots versus training bots), llms.txt only if you want it | AI visibility reports, a fixed AI answer spot check |
| `seo-content` | own product descriptions, instructions and FAQ, one buying guide | 1 to 3 pieces a month by demand, pruning, seasons, links; new page |
| `seo-measure` | analytics and goals, baseline, decision log | weekly snapshot, CTR pass with control pages, organic to orders; traffic drop |
| `seo-local` | NAP table, Yandex Business, 2GIS, Google Business Profile | review answers, profile check against the site; price change |
| `seo-query-gaps` | none on launch day; first pass at day 90 | monthly: queries the site is shown for but has no page for |

## Scripts

| Script | What it does | Sends |
|---|---|---|
| `scripts/seo_check.py` | 30 external checks of a live site; Markdown and JSON reports; `--selftest` plants a known defect for 28 of them (the home page answer is checked inline, llms.txt only informs) | GET and HEAD, 2 per second, 60 per run |
| `scripts/seo_calendar.py` | `init`, `due`, `done`, `track` (day 7, 21 and 90 checks for a new page), `validate` | nothing |
| `scripts/indexnow.py` | changed, new or removed sitemap URLs to IndexNow; dry run unless `--submit`; one URL not more often than every 10 minutes; honors 429 Retry-After | POST only with `--submit` |
| `scripts/gsc_gaps.py` | gap, striking-distance and weak-CTR queries from a Search Console or Yandex Webmaster export | page GETs only with `--sitemap` |

Exit codes of `seo_check.py`: 0 no FAIL, 1 FAIL (or WARN with `--fail-on warn`), 2 the site did not answer.

## Cron on GitHub Actions

| Template | When (UTC) | Does |
|---|---|---|
| `seo-daily.yml` | every day | `seo_check.py --pages 3`, then IndexNow for URLs whose lastmod changed in 26 hours |
| `seo-weekly.yml` | Mondays | `seo_check.py --pages 12`, report in the job summary |
| `seo-monthly.yml` | the 1st | an issue with the human calendar tasks due in 31 days |
| `seo-on-deploy.yml` | after a deploy | `seo_check.py --pages 8`, then IndexNow for 3 hours |

All four call `GoldenSample/seo-ops/.github/workflows/seo-cron.yml@v1`. A red run means a FAIL on the site or a site that did not answer. Schedules run in UTC on the default branch and can start late under load; in a public repository GitHub disables them after 60 days without activity. Details and sources: [skills/seo-calendar/SKILL.md](skills/seo-calendar/SKILL.md).

## Evidence levels

- **Official**: the search engine's own documentation, with a link and the checked date.
- **Measured**: a study with a method and a sample; the sample is named.
- **Practice**: practitioners' advice or our own observation; treat it as a hypothesis.

Every fact in the skills and the calendar was checked on 2026-11-25. The calendar task `quarterly-rules-recheck` is the reminder to check them again.

## What this is not

Not a crawler, not a rank tracker, not a link tool, and not a replacement for Search Console or Yandex Webmaster. It never logs in anywhere and needs no API tokens. It does not promise rankings; it keeps a small site free of the common defects and makes every change measurable.

## Contributing

Corrections are welcome as pull requests. A changed fact needs its source and the date you checked it. Run the tests first:

```
python scripts/seo_check.py --selftest
python tests/test_robots.py && python tests/test_calendar.py && python tests/test_gaps.py && python tests/test_indexnow.py
```

The scripts were written by a local model from specs and tests, then reviewed and extended by Claude; the tests are the contract.

## License

MIT. See [LICENSE](LICENSE), [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md).
