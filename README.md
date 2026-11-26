# seo-ops: SEO and GEO for a small site, as skills, scripts and cron jobs

[Русская версия](README.ru.md)

A Claude Code plugin and a plain toolbox for one small site or store: Google, Yandex, Bing and AI answers (AI Overviews, AI Mode, Alice AI, ChatGPT search, Perplexity). Every task is marked as **one-time** (do it once for a new site), **recurring** (a calendar runs it) or **event** (a runbook for a deploy, a price change, a traffic drop, a core update). Facts about search engines carry a source and the date they were checked, because they go stale.

- 11 skills that Claude loads when the topic comes up
- 8 scripts in Python 3.9+ with the standard library only: live-site check, site crawl, index coverage, site calendar, IndexNow, query gaps, Wordstat, SERP clustering
- a 62-task calendar template and a decision log template
- a reusable GitHub Actions workflow and 4 caller templates: daily, weekly, monthly, after deploy

## Install

As a Claude Code plugin:

```
/plugin marketplace add GoldenSample/seo-ops
/plugin install seo-ops@goldensample-seo
```

Without Claude: `git clone https://github.com/GoldenSample/seo-ops` and run the scripts. Nothing to install.

## Try it

Four prompts to type in Claude Code after the install. The results below come from running the same scripts directly on 2026-11-26.

1. **Check a live site before launch.**

   > Check example.com with seo-ops before launch: run the site check and the crawl, then explain every FAIL and WARN and how to fix it.

   Claude runs `seo_check.py example.com --pages 12` and `seo_crawl.py example.com` and reads the reports with the seo-launch skill. For example.com the check made 12 requests and found 2 FAIL (no permanent redirect from http and from www; no sitemap) and 10 WARN, among them no robots.txt, no meta description and no JSON-LD. The crawl made 3 requests: example.com has one page and no internal links, so it found no broken link; its two WARN, no readable sitemap and no h1, are ones the check already reported. Your site gets its own lists.

2. **Make the calendar of a new site.**

   > My shop example.com launches on 2026-12-01. Make its SEO calendar in this folder and tell me what is due in the first week: what the cron does and what a person does.

   Claude runs `seo_calendar.py init --site example.com --launch 2026-12-01`, which writes `seo-calendar.json` with 62 tasks, then `seo_calendar.py due --date 2026-12-01 --within 7`. You get 26 launch tasks for the first day, the semantic core among them, and 9 more in the next 7 days: daily health check and IndexNow, weekly audit and site crawl, index snapshot, AI visibility, reviews. Each line says `cron` or `human`.

3. **Find the pages a site is missing.** Copy `examples/Queries.csv` (a made-up Search Console export of a tea shop) and `examples/pages.csv` (its page list) from this repository into your folder, then ask:

   > Here are my Search Console queries in Queries.csv and my pages in pages.csv. Which new pages should I plan, and which titles should I rewrite?

   Claude runs `gsc_gaps.py Queries.csv --pages pages.csv`. Gap queries: matcha powder (260 impressions, no matching page), how to brew oolong (190) and cast iron teapot (120). Black tea sits at position 9.4, in striking distance. Green tea has 410 impressions but a 2.9% CTR at position 2.1, so its title and description come first in the rewrite.

4. **Group phrases by search results.** Copy `examples/serp.csv` (made-up top-10 results for 14 phrases of the same tea shop) and `examples/freq.csv` (their monthly counts), then ask:

   > Here are the top-10 results for my phrases in serp.csv and their counts in freq.csv. Group the phrases by search results and tell me which page of example.com should target each group, which groups need a new page and where my pages compete.

   Claude runs `serp_cluster.py serp.csv --freq freq.csv --site example.com` and reads the result with the seo-semantic-core skill. 14 phrases make 6 clusters. Two have no page of the shop in the top 10 and are candidates for new pages: how to make matcha (with how to prepare matcha, 1920 searches a month) and how to brew oolong (390). /green-tea/ is the main page of two clusters, green tea and matcha powder, so matcha wants a page of its own. The oolong cluster is split between /oolong/ and the home page.

## Start on a new site (one-time)

1. Check the live site and crawl it, then read every FAIL and WARN:
   `python scripts/seo_check.py example.com --pages 12` and `python scripts/seo_crawl.py example.com`
2. In the site repository, make the site calendar and commit it:
   `python scripts/seo_calendar.py init --site example.com --launch 2026-12-01` writes `seo-calendar.json`.
3. Copy `templates/workflows/*.yml` to `.github/workflows/` of the site repository. Set the repository variable `SEO_SITE` (for example `example.com`) and, if you use IndexNow, the secret `INDEXNOW_KEY`.
4. Work through the launch tasks: `python scripts/seo_calendar.py due --who human`, then `python scripts/seo_calendar.py done <id>` for each.
5. Copy `templates/decision-log.md` and write the baseline before the first SEO change.
6. Before the site structure is fixed, build the semantic core with the seo-semantic-core skill.

## Skills

| Skill | One-time (new site) | Recurring and events |
|---|---|---|
| `seo-ops` | site passport, calendar; the map of all skills, laws, evidence levels | quarterly re-check of rules and dates |
| `seo-launch` | 13 launch steps with a check each: redirects, robots, sitemap, canonical, structured data, errors, speed, trust pages; the index check at day 14 | weekly audit and site crawl, monthly index coverage and schema spot check, quarterly deep crawl; deploy, migration |
| `seo-calendar` | calendar and cron workflows | daily health and IndexNow, weekly audit and crawl, monthly issue with the index report when the keys are set; deploy |
| `seo-google` | Search Console, AI features included, Bing Webmaster, product markup, Merchant Center | index snapshot, AI visibility, crawler logs; core update |
| `seo-yandex` | Webmaster rights, region, Clean-param, Yandex Products feed, IndexNow key | daily IndexNow, console alerts; price change, data outage |
| `seo-geo` | AI crawler policy (search and user bots versus training bots), llms.txt only if you want it | AI visibility reports, a fixed AI answer spot check |
| `seo-semantic-core` | semantic core before the structure is fixed: markers, Wordstat counts, stop list, intent, clusters by shared top-10 results, one target page per cluster | quarterly refresh; new category or product line |
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
| `scripts/seo_crawl.py` | crawl of the whole site from the home page and the sitemap: status codes, redirects and chains, canonical, noindex, empty or duplicate title and H1, broken internal links, pages missing from the sitemap, orphans; `--compare` with an earlier crawl; `--selftest` plants known defects and runs a clean control site | GET and HEAD to the host you name, 2 per second, 200 URLs and 600 seconds by default |
| `scripts/seo_index.py` | published pages (the sitemap or a crawl) missing from the Yandex and Google index, with the reason each engine gives | the sitemap; with your keys, the Yandex Webmaster and Search Console APIs |
| `scripts/wordstat.py` | Wordstat through the official API: the count of a phrase and the queries that contain it, dynamics by month, week or day, regions; `--dry-run` shows the price first; answers are cached | with your Yandex Cloud key, the Search API; billed to your Yandex Cloud account |
| `scripts/serp_cluster.py` | clusters of phrases by shared top-10 URLs from a CSV of results (long or wide, English or Russian headers), soft or hard, threshold 3; with `--site`, the page of your site for each cluster, candidates for new pages and pages that compete | nothing |

Exit codes of `seo_check.py`, `seo_crawl.py` and `seo_index.py`: 0 no FAIL, 1 FAIL (or WARN with `--fail-on warn`), 2 the site (for `seo_index.py` also an API) did not answer or the arguments are wrong.

## Optional connectors

Nothing here needs a key by default. Two scripts can use keys of your own, read only from your keys file (below) or, in the cron, from CI secrets, never from the environment; without a key they skip that source. The seo-semantic-core skill can also use Arsenkin's MCP server if you connect it.

| Connector | Used by | Your keys | Price and limits (checked 2026-11-26) |
|---|---|---|---|
| Yandex Webmaster API | `seo_index.py` | `YANDEX_WEBMASTER_TOKEN`: OAuth token of your own app with the Webmaster rights; it lives 6 months | pages in search: up to 50 000 URLs |
| Search Console API | `seo_index.py` | `GSC_CLIENT_ID`, `GSC_CLIENT_SECRET` and `GSC_REFRESH_TOKEN`, or a short-lived `GSC_ACCESS_TOKEN`; `GSC_PROPERTY` optional | URL Inspection: 2000 a day and 600 a minute per site |
| Wordstat API (Yandex Search API) | `wordstat.py` | `YANDEX_CLOUD_API_KEY` of a service account or `YANDEX_CLOUD_IAM_TOKEN`; `YANDEX_CLOUD_FOLDER_ID` | with VAT: 20 ₽ per 1000 requests for counts and dynamics, 50 ₽ for regions, the regions tree free; 100 requests an hour |
| Arsenkin MCP server | seo-semantic-core, optional at each step | your Arsenkin token, connected by you with `claude mcp add` | the Standard or Corporate plan, 2 490 ₽ or 7 990 ₽ a month; 30 requests a minute |

How to get the Webmaster and Search Console keys: [skills/seo-launch/SKILL.md](skills/seo-launch/SKILL.md), "Index coverage". Wordstat and Arsenkin: [skills/seo-semantic-core/SKILL.md](skills/seo-semantic-core/SKILL.md).

### Keys file

The scripts that call an API with your keys (`seo_index.py`, `wordstat.py`, `indexnow.py`, `seo_check.py`) read them only from a keys file you name with `--keys FILE`, never from the environment.

1. Create it outside any repository: `python scripts/seo_keys.py init ~/.config/seo-ops/keys.env` writes a template with every name and empty values (mode 600; it never overwrites a file).
2. Fill in the keys you have, one `NAME=value` per line: the names in the table above, the same as the CI secrets. `python scripts/seo_keys.py check ~/.config/seo-ops/keys.env` shows which names are set and which scripts can use them, never the values.
3. In Claude Code, name the file once as the plugin option "Keys file": `/plugin configure seo-ops@goldensample-seo`, or `claude plugin install seo-ops@goldensample-seo --config keys_file=<path>` at install. The skills then pass it with `--keys`. Claude Code stores only the path; the keys stay in your file.
4. Without Claude, pass it yourself: `python scripts/seo_index.py example.com --keys ~/.config/seo-ops/keys.env`.

The scripts warn when the file sits inside a git repository or other users can read it (POSIX). Coming from 1.1: keys in environment variables are no longer read, move them into the keys file; the CI secret names did not change.

## Cron on GitHub Actions

| Template | When (UTC) | Does |
|---|---|---|
| `seo-daily.yml` | every day | `seo_check.py --pages 3`, then IndexNow for URLs whose lastmod changed in 26 hours |
| `seo-weekly.yml` | Mondays | `seo_check.py --pages 12`, then `seo_crawl.py` over the whole site (200 URLs, input `crawl_pages`); reports in the job summary |
| `seo-monthly.yml` | the 1st | an issue with the human calendar tasks due in 31 days; with the index secrets, the `seo_index.py` report in the same issue |
| `seo-on-deploy.yml` | after a deploy | `seo_check.py --pages 8`, then IndexNow for 3 hours |

All four call `GoldenSample/seo-ops/.github/workflows/seo-cron.yml@v1`. With the `INDEXNOW_KEY` secret, the daily, weekly and deploy checks also check the key file `https://<host>/<key>.txt` (missing or wrong is a FAIL), and the daily and deploy runs send changed URLs. The `indexnow` input of a caller narrows that: `submit` (default) does both, `check` only checks the key file (when another tool already sends), `off` ignores the secret. The weekly crawl fails the run on a crawl FAIL (links to 4xx pages, 5xx answers, a redirect loop, sitemap errors, a page without a title); `crawl_pages: 0` turns the crawl off. The index secrets (`YANDEX_WEBMASTER_TOKEN`, `GSC_CLIENT_ID`, `GSC_CLIENT_SECRET`, `GSC_REFRESH_TOKEN`) reach only the index step of the monthly run. Each step with a secret writes it to a keys file in the runner's temporary folder (mode 600, removed when the step ends) and passes it with `--keys`. A red run means a FAIL on the site or a site that did not answer. Schedules run in UTC on the default branch and can start late under load; in a public repository GitHub disables them after 60 days without activity. Details and sources: [skills/seo-calendar/SKILL.md](skills/seo-calendar/SKILL.md).

## What it reads, runs, sends and changes

seo-ops has no server and no telemetry. The skills are text. The scripts run only when you or Claude start them, on your machine or in your own GitHub Actions.

- **Reads:** the files you name (a calendar, a Search Console export, a page list, a CSV of search results), the public pages of the site you name and, with your keys, that site's data in Yandex Webmaster and Search Console.
- **Sends**, only while a script runs:
  - `seo_check.py`: GET and HEAD to the host you name (over https, and once over http to test the redirect) and to its www or non-www twin. On that host it fetches the home page, robots.txt, sampled sitemap URLs, /.well-known/security.txt, /llms.txt, one made-up URL to test the 404, and one script or stylesheet with its source map. It reads the sitemap that robots.txt names (else /sitemap.xml) and up to 3 child sitemaps; one TLS handshake reads the certificate. 2 requests per second, 60 per run by default; it does not follow redirects. With an IndexNow key it also fetches `https://<host>/<key>.txt`.
  - `indexnow.py`: GET of the sitemap; GET of the key file with `--check-key` or `--submit`; one POST per 10,000 URLs to the IndexNow endpoint (default `https://api.indexnow.org/indexnow`), only with `--submit`. The POST body holds the host, the key, the key file URL when you set `--key-location`, and the URLs of that host. The protocol makes the key public: it sits at `https://<host>/<key>.txt`. The script takes it from `--key` or from `INDEXNOW_KEY` of the keys file named with `--keys`.
  - `gsc_gaps.py`: nothing, unless you pass `--sitemap`; then GET of the sitemap and of each page, 1 per second, 200 pages at most.
  - `seo_calendar.py`: nothing.
  - `seo_crawl.py`: GET and HEAD to the host you name: robots.txt first, then the pages its links reach and the sitemap URLs (files get a HEAD request), and the sitemap files that its robots.txt or sitemap index names. Links to other hosts are counted, never fetched. 2 requests per second, at most 200 URLs and 600 seconds by default; it slows down on 429 and 503.
  - `seo_index.py`: GET of robots.txt and the sitemap (none with `--pages`). With `YANDEX_WEBMASTER_TOKEN`, requests to `api.webmaster.yandex.net`; with the Google keys, the token exchange at `oauth2.googleapis.com`, the site list at `www.googleapis.com` and URL Inspection at `searchconsole.googleapis.com`; at most 5 requests a second. The published URLs of your site go to those APIs; the tokens go nowhere else and never reach the output.
  - `wordstat.py`: with your Yandex Cloud key, POST requests to `searchapi.api.cloud.yandex.net`, one per phrase, at most 100 an hour by default; Yandex Cloud bills them to your account. `--dry-run` sends nothing.
  - `serp_cluster.py`: nothing.
  - Every request carries a User-Agent with the tool name and this repository URL.
- **Writes:** `seo-calendar.json` (`init`, `done`, `skip`, `track`), the reports you name with `--md`, `--json`, `--csv` or `--out`, the state files you name with `--state` or `--sent-log`, and the cache of Wordstat answers (`~/.cache/seo-ops/wordstat` by default, outside any repository; `--cache` moves it). Nothing else.
- **GitHub Actions**, only if you copy the templates: each run checks out `GoldenSample/seo-ops` at `tools_ref` (default `v1`) to get the scripts and writes its report to the job summary, with `contents: read`. The monthly run opens one issue in your repository with the `GITHUB_TOKEN` of that run, so its caller also has `issues: write`. With the `INDEXNOW_KEY` secret, a check run also fetches the key file and the IndexNow step sends changed URLs; the caller's `indexnow` input turns off the sending (`check`) or both (`off`). The weekly run also crawls your site. With the index secrets, the monthly run sends the published URLs of your site with your keys to the Yandex Webmaster and Search Console APIs and puts the report into the issue.
- **Does not:** log in to a dashboard, change Search Console, Webmaster or analytics settings, install packages, or add hooks, MCP servers, agents or commands. The Arsenkin MCP server that seo-semantic-core mentions is one you connect yourself, with your own token. It leaves Claude settings and memory alone. The scripts treat web pages as data and never run code or instructions from them.

## Where it works

- **Claude Code:** everything. The skills run the scripts with your Python 3.9+ and your network.
- **Claude chat and Cowork:** the plugin has skills only (no hooks, agents or MCP servers), so it loads there too. Nobody has tested yet whether the scripts run and reach the network in that sandbox; without them the skills still work as checklists and as the calendar.
- **Without Claude:** clone the repository and run the scripts, or copy the GitHub Actions templates.

## Troubleshooting

- **`seo_check.py` exits 2, SITE UNREACHABLE.** The home page did not answer or answered 5xx. Open the site in a browser from the same machine. On Windows, `CERTIFICATE_VERIFY_FAILED` with "unable to get local issuer certificate" means Python cannot find the root certificate of the site's chain, and Python does not download missing roots. Set the environment variable `SSL_CERT_FILE` to a CA bundle file, for example the one whose path `python -m certifi` prints when certifi is installed.
- **A cron run is red.** Exit code 1 means a FAIL on the site, 2 means the site did not answer. The job summary lists every check. A WARN fails the run only when the caller passes `fail_on: warn`.
- **A weekly run is red on the crawl.** `seo_crawl.py` found a FAIL: links to 4xx pages, 5xx answers, a redirect loop, sitemap URLs that are not 200 or have noindex, or a page without a title. The job summary lists each; broken links come with the pages that link to them. If the server answers 429 to the crawler, the crawl slows down and then stops: let the User-Agent `seo-ops-crawl` through the rate limit or lower `crawl_pages`. `crawl_pages: 0` turns the crawl off.
- **`seo_index.py` says SKIP or a key is refused.** SKIP: no keys file (`--keys`), or no key for that engine in it; keys in the environment are not read. A refused Yandex token has expired (it lives 6 months) or lacks the Webmaster rights, or the site is not in that account. On Google, a refresh token from an app whose consent screen is in the Testing status expires after 7 days: publish the app and authorize again. The property must be in the account: set `GSC_PROPERTY` in the keys file, or pass `--gsc-property`, as `https://example.com/` or `sc-domain:example.com`.
- **`wordstat.py` is slow.** The Wordstat quota is 100 requests an hour, so 300 phrases take a little over two hours. The script waits inside the quota and caches every answer; a rerun goes on where it stopped.
- **A cron run is red on indexnow-key.** The key file `https://<host>/<key>.txt` is missing or does not hold the key in the `INDEXNOW_KEY` secret. Serve the file with the key as plain text. If another tool sends IndexNow for this site with its own key file, set `indexnow: off` in the caller.
- **A calendar task does not apply to this site** (no product catalog, no office). `python scripts/seo_calendar.py skip launch-product-feeds --reason "no product catalog"` moves it to the Skipped list of `due`, with the reason, and out of the monthly issue; `skip <id> --undo` or `done <id>` brings it back. A skip needs a reason.
- **IndexNow: "no IndexNow key".** Pass `--key`, or `--keys` with a keys file that has `INDEXNOW_KEY` (the environment is not read); a dry run needs the key too. A key is 8 to 128 letters, digits or `-`. `python scripts/indexnow.py --site example.com --check-key` checks that `https://example.com/<key>.txt` answers with the key. After a 429 answer, the script sends nothing until Retry-After has passed (with `--sent-log`).
- **Scheduled runs stopped.** In a public repository, GitHub disables schedules after 60 days without activity. Open the Actions tab and enable the workflow again.
- **The monthly issue did not appear.** The monthly caller reads `seo-calendar.json` in the repository root; change its `calendar` input if the file lives elsewhere. The caller needs `issues: write`, which the template already sets.
- **The skills do not show up in Claude Code.** Run `/reload-plugins` or restart Claude Code, then check that `claude plugin list` shows seo-ops.
- **`python` is not found.** The scripts need Python 3.9 or later. On Windows, run them with `py -3`.

## What this is not

Not a rank tracker, not a link tool, and not a replacement for Search Console or Yandex Webmaster. `seo_crawl.py` crawls the pages of your own small site, 200 URLs by default, not the web. No tokens by default: the check, the crawl, the calendar, the query gaps and the clustering need no key, your IndexNow key is public by design, and the monthly cron opens its issue with the `GITHUB_TOKEN` of its own run. The optional keys are your own: `seo_index.py` reads the index with your Yandex Webmaster and Search Console tokens, and `wordstat.py` calls Wordstat with your Yandex Cloud key, billed to your Yandex Cloud account; both read the keys only from your keys file, never from the environment. It never logs in to a dashboard and never changes a setting there. It does not promise rankings; it keeps a small site free of the common defects and makes every change measurable.

## Evidence levels

- **Official**: the search engine's own documentation, with a link and the checked date.
- **Measured**: a study with a method and a sample; the sample is named.
- **Practice**: practitioners' advice or our own observation; treat it as a hypothesis.

Every fact in the skills and the calendar was checked on 2026-11-25; the facts added in 1.1.0 (crawl, index coverage, Wordstat, clustering, semantic core) on 2026-11-26. The calendar task `quarterly-rules-recheck` reminds a person to check them again.

## Privacy, support and security

- Privacy: [PRIVACY.md](PRIVACY.md). seo-ops collects nothing.
- Support: open an issue at https://github.com/GoldenSample/seo-ops/issues with the command, the exit code and the report lines. Leave keys and tokens out.
- Security problems: report them privately, as [SECURITY.md](SECURITY.md) explains.

## Contributing

Corrections are welcome as pull requests. A changed fact needs its source and the date you checked it. Run the tests first:

```
python scripts/seo_check.py --selftest
python scripts/seo_crawl.py --selftest
python tests/test_robots.py && python tests/test_calendar.py && python tests/test_gaps.py && python tests/test_indexnow.py
python tests/test_index.py && python tests/test_wordstat.py && python tests/test_cluster.py
```

The four scripts of 1.0 were written by a local model from specs and tests, then reviewed and extended by Claude. In 1.1.0 the clustering core of `serp_cluster.py` was written the same way (43 known answers); `seo_crawl.py`, `seo_index.py`, `wordstat.py` and the rest of `serp_cluster.py` were written by Claude. The tests are the contract.

## License

MIT. See [LICENSE](LICENSE).
