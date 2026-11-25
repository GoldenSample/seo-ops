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

## Try it

Three prompts to type in Claude Code after the install. The results below come from running the same scripts directly on 2026-11-25.

1. **Check a live site before launch.**

   > Check example.com with seo-ops before launch: run the site check, then explain every FAIL and WARN and how to fix it.

   Claude runs `seo_check.py example.com --pages 12` and reads the report with the seo-launch skill. For example.com the check made 12 requests and found 2 FAIL (no permanent redirect from http and from www; no sitemap) and 10 WARN, among them no robots.txt, no meta description and no JSON-LD. Your site gets its own list.

2. **Make the calendar of a new site.**

   > My shop example.com launches on 2026-12-01. Make its SEO calendar in this folder and tell me what is due in the first week: what the cron does and what a person does.

   Claude runs `seo_calendar.py init --site example.com --launch 2026-12-01`, which writes `seo-calendar.json` with 58 tasks, then `seo_calendar.py due --date 2026-12-01 --within 7`. You get 25 launch tasks for the first day and 8 more in the next 7 days: daily health check and IndexNow, weekly audit, index snapshot, AI visibility, reviews. Each line says `cron` or `human`.

3. **Find the pages a site is missing.** Copy `examples/Queries.csv` (a made-up Search Console export of a tea shop) and `examples/pages.csv` (its page list) from this repository into your folder, then ask:

   > Here are my Search Console queries in Queries.csv and my pages in pages.csv. Which new pages should I plan, and which titles should I rewrite?

   Claude runs `gsc_gaps.py Queries.csv --pages pages.csv`. Gap queries: matcha powder (260 impressions, no matching page), how to brew oolong (190) and cast iron teapot (120). Black tea sits at position 9.4, in striking distance. Green tea has 410 impressions but a 2.9% CTR at position 2.1, so its title and description come first in the rewrite.

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
| `scripts/seo_calendar.py` | `init`, `due`, `done`, `skip` (a task that does not apply to this site, with the reason), `track` (day 7, 21 and 90 checks for a new page), `validate` | nothing |
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

All four call `GoldenSample/seo-ops/.github/workflows/seo-cron.yml@v1`. With the `INDEXNOW_KEY` secret, the daily, weekly and deploy checks also check the key file `https://<host>/<key>.txt` (missing or wrong is a FAIL), and the daily and deploy runs send changed URLs. The `indexnow` input of a caller narrows that: `submit` (default) does both, `check` only checks the key file (when another tool already sends), `off` ignores the secret. A red run means a FAIL on the site or a site that did not answer. Schedules run in UTC on the default branch and can start late under load; in a public repository GitHub disables them after 60 days without activity. Details and sources: [skills/seo-calendar/SKILL.md](skills/seo-calendar/SKILL.md).

## What it reads, runs, sends and changes

seo-ops has no server and no telemetry. The skills are text. The scripts run only when you or Claude start them, on your machine or in your own GitHub Actions.

- **Reads:** the files you name (a calendar, a Search Console export, a page list) and the public pages of the site you name.
- **Sends**, only while a script runs:
  - `seo_check.py`: GET and HEAD to the host you name (over https, and once over http to test the redirect) and to its www or non-www twin. On that host it fetches the home page, robots.txt, sampled sitemap URLs, /.well-known/security.txt, /llms.txt, one made-up URL to test the 404, and one script or stylesheet with its source map. It reads the sitemap that robots.txt names (else /sitemap.xml) and up to 3 child sitemaps; one TLS handshake reads the certificate. 2 requests per second, 60 per run by default; it does not follow redirects. With an IndexNow key it also fetches `https://<host>/<key>.txt`.
  - `indexnow.py`: GET of the sitemap; GET of the key file with `--check-key` or `--submit`; one POST per 10,000 URLs to the IndexNow endpoint (default `https://api.indexnow.org/indexnow`), only with `--submit`. The POST body holds the host, the key, the key file URL when you set `--key-location`, and the URLs of that host. The protocol makes the key public: it sits at `https://<host>/<key>.txt`. The script takes it from `--key` or from the `INDEXNOW_KEY` environment variable.
  - `gsc_gaps.py`: nothing, unless you pass `--sitemap`; then GET of the sitemap and of each page, 1 per second, 200 pages at most.
  - `seo_calendar.py`: nothing.
  - Every request carries a User-Agent with the tool name and this repository URL.
- **Writes:** `seo-calendar.json` (`init`, `done`, `skip`, `track`), the reports you name with `--md`, `--json` or `--out`, and the state files you name with `--state` or `--sent-log`. Nothing else.
- **GitHub Actions**, only if you copy the templates: each run checks out `GoldenSample/seo-ops` at `tools_ref` (default `v1`) to get the scripts and writes its report to the job summary, with `contents: read`. The monthly run opens one issue in your repository with the `GITHUB_TOKEN` of that run, so its caller also has `issues: write`. With the `INDEXNOW_KEY` secret, a check run also fetches the key file and the IndexNow step sends changed URLs; the caller's `indexnow` input turns off the sending (`check`) or both (`off`).
- **Does not:** log in anywhere, change Search Console, Webmaster or analytics settings, install packages, or add hooks, MCP servers, agents or commands. It leaves Claude settings and memory alone. The scripts treat web pages as data and never run code or instructions from them.

## Where it works

- **Claude Code:** everything. The skills run the scripts with your Python 3.9+ and your network.
- **Claude chat and Cowork:** the plugin has skills only (no hooks, agents or MCP servers), so it loads there too. Nobody has tested yet whether the scripts run and reach the network in that sandbox; without them the skills still work as checklists and as the calendar.
- **Without Claude:** clone the repository and run the scripts, or copy the GitHub Actions templates.

## Troubleshooting

- **`seo_check.py` exits 2, SITE UNREACHABLE.** The home page did not answer or answered 5xx. Open the site in a browser from the same machine. On Windows, `CERTIFICATE_VERIFY_FAILED` with "unable to get local issuer certificate" means Python cannot find the root certificate of the site's chain, and Python does not download missing roots. Set the environment variable `SSL_CERT_FILE` to a CA bundle file, for example the one whose path `python -m certifi` prints when certifi is installed.
- **A cron run is red.** Exit code 1 means a FAIL on the site, 2 means the site did not answer. The job summary lists every check. A WARN fails the run only when the caller passes `fail_on: warn`.
- **A cron run is red on indexnow-key.** The key file `https://<host>/<key>.txt` is missing or does not hold the key in the `INDEXNOW_KEY` secret. Serve the file with the key as plain text. If another tool sends IndexNow for this site with its own key file, set `indexnow: off` in the caller.
- **A calendar task does not apply to this site** (no product catalog, no office). `python scripts/seo_calendar.py skip launch-product-feeds --reason "no product catalog"` moves it to the Skipped list of `due`, with the reason, and out of the monthly issue; `skip <id> --undo` or `done <id>` brings it back. A skip needs a reason.
- **IndexNow: "no IndexNow key".** Pass `--key` or set `INDEXNOW_KEY`; a dry run needs the key too. A key is 8 to 128 letters, digits or `-`. `python scripts/indexnow.py --site example.com --check-key` checks that `https://example.com/<key>.txt` answers with the key. After a 429 answer, the script sends nothing until Retry-After has passed (with `--sent-log`).
- **Scheduled runs stopped.** In a public repository, GitHub disables schedules after 60 days without activity. Open the Actions tab and enable the workflow again.
- **The monthly issue did not appear.** The monthly caller reads `seo-calendar.json` in the repository root; change its `calendar` input if the file lives elsewhere. The caller needs `issues: write`, which the template already sets.
- **The skills do not show up in Claude Code.** Run `/reload-plugins` or restart Claude Code, then check that `claude plugin list` shows seo-ops.
- **`python` is not found.** The scripts need Python 3.9 or later. On Windows, run them with `py -3`.

## What this is not

Not a crawler, not a rank tracker, not a link tool, and not a replacement for Search Console or Yandex Webmaster. It never logs in anywhere and needs no Search Console, Webmaster or analytics tokens. The only key it uses is your IndexNow key, which is public by design, and the monthly cron opens its issue with the `GITHUB_TOKEN` of its own run. It does not promise rankings; it keeps a small site free of the common defects and makes every change measurable.

## Evidence levels

- **Official**: the search engine's own documentation, with a link and the checked date.
- **Measured**: a study with a method and a sample; the sample is named.
- **Practice**: practitioners' advice or our own observation; treat it as a hypothesis.

Every fact in the skills and the calendar was checked on 2026-11-25. The calendar task `quarterly-rules-recheck` reminds a person to check them again.

## Privacy, support and security

- Privacy: [PRIVACY.md](PRIVACY.md). seo-ops collects nothing.
- Support: open an issue at https://github.com/GoldenSample/seo-ops/issues with the command, the exit code and the report lines. Leave keys and tokens out.
- Security problems: report them privately, as [SECURITY.md](SECURITY.md) explains.

## Contributing

Corrections are welcome as pull requests. A changed fact needs its source and the date you checked it. Run the tests first:

```
python scripts/seo_check.py --selftest
python tests/test_robots.py && python tests/test_calendar.py && python tests/test_gaps.py && python tests/test_indexnow.py
```

The scripts were written by a local model from specs and tests, then reviewed and extended by Claude; the tests are the contract.

## License

MIT. See [LICENSE](LICENSE).
