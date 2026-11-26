# Changelog

## 1.1.0 (2026-11-26)

- New scripts, Python 3.9+ standard library only:
  - `seo_crawl.py`: crawl of the whole site from the home page and the sitemap, with no keys: status codes, redirects and chains, canonical, noindex, empty or duplicate title and H1, broken internal links, pages missing from the sitemap, orphans; `--compare` with an earlier crawl. It obeys robots.txt (RFC 9309), keeps 2 requests per second and a URL and time budget, and slows down on 429 and 503. A self-test plants known defects and runs a clean control site.
  - `seo_index.py`: published pages missing from the Yandex and Google index, with the reason each engine gives, through the Yandex Webmaster API and Search Console URL Inspection, with the owner's keys from the environment. Token values never reach the output.
  - `wordstat.py`: the official Wordstat API (Yandex Search API): counts and the queries that contain a phrase, dynamics, regions, the regions tree. `--dry-run` shows the requests, the price and the time; the hourly quota is kept; answers are cached.
  - `serp_cluster.py`: clusters of phrases by shared top-10 URLs from any CSV of results, soft or hard, threshold 3. With `--site` it names the page of the site for each cluster, the candidates for new pages and the pages that compete.
- `seo_check.py`: its HTML parser also keeps the H1 texts, the links and `<base href>` for the crawl, and every response is closed after reading. Its checks and reports are unchanged.
- New skill seo-semantic-core: markers, counts, stop list, intent, clusters, one target page per cluster; Arsenkin's MCP server as an optional paid source at each step. seo-launch explains the crawl and index coverage; seo-ops, seo-calendar, seo-measure, seo-query-gaps and seo-content link the new tools.
- Calendar: 62 tasks (was 58). New: `launch-semantic-core`, `weekly-crawl`, `monthly-index-coverage`, `quarterly-semantic-refresh`. `quarterly-crawl`, `launch-indexing-d14`, `event-migration` and `event-traffic-drop` name the new scripts.
- Cron: the weekly run also crawls the site (input `crawl_pages`, default 200 URLs, `0` turns it off) and fails on a crawl FAIL. With the index secrets (`YANDEX_WEBMASTER_TOKEN`, `GSC_CLIENT_ID`, `GSC_CLIENT_SECRET`, `GSC_REFRESH_TOKEN`; inputs `index`, `gsc_property`, `google_max`) the monthly run adds the index report to its issue; without them that step is skipped. The issue body is cut to 60 000 bytes.
- `examples/serp.csv` and `examples/freq.csv`: made-up search results and counts for `serp_cluster.py`; the tests check the README example against them.
- README in English and Russian: four checked prompts, the new scripts, optional connectors, troubleshooting. It no longer says "not a crawler"; it still needs no tokens by default, and the optional keys are the owner's own.
- CI runs the crawl self-test and the tests of the index, Wordstat and cluster scripts.
- Behaviour change for callers of `@v1`: once `v1` points to 1.1.0, the weekly run crawls up to 200 URLs and goes red on a crawl FAIL. Set `crawl_pages: 0` in the weekly caller to keep the 1.0 behaviour.
- Scripts, the cron workflow and the templates changed, so `v1` moves to 1.1.0.

## 1.0.2 (2026-11-25)

- Plugin manifest: fields for the Claude plugin directory listing (icon, documentation, support and privacy policy URLs). The icon is the publisher mark of GoldenSample, a square PNG.
- README in English and Russian: Try it with three checked prompts, what the plugin reads, runs, sends and changes, where it works (Claude Code, chat, Cowork), troubleshooting, privacy and support links. The line about API tokens now names the IndexNow key and the `GITHUB_TOKEN` of the monthly run.
- `examples/`: a made-up Search Console export and page list for `gsc_gaps.py`.
- PRIVACY.md lists the checkout of this repository by the cron, the monthly issue and the IndexNow key file request. SECURITY.md says where `v1` points.
- Fixes from running 1.0.1 on live sites:
  - Cron: the `INDEXNOW_KEY` secret now reaches the site check, so cron runs check the key file; before, `indexnow-key` was always SKIP there. A run with the secret and a missing or wrong key file now fails on `indexnow-key`. New input `indexnow`: `submit` (default: check the key file and send changed URLs), `check` (key file only, when another tool sends) or `off`. The weekly template passes the secret too.
  - `seo_check.py` samples the biggest sitemap section first, so a large section listed after many small ones is checked as well.
  - `seo_check.py` gives the one-year cache advice only for a static file with a content hash in its name; a file without one gets an INFO line: put a content hash in the name first.
  - `seo_calendar.py skip <id> --reason "..."` marks a task that does not apply to this site. `due` lists skipped tasks apart, the monthly issue leaves them out, `validate` needs the reason, and `skip --undo` or `done` brings a task back.
  - `seo_calendar.py validate --template FILE` takes the file, as `init --template FILE` does. `validate --calendar FILE --template` still works; `--as-template` is the plain name for it.
- Scripts, the cron workflow, the templates and the seo-calendar skill changed, so `v1` moves to 1.0.2.

## 1.0.1 (2026-11-25)

- CI: Python 3.9 runs on ubuntu-24.04, because actions/python-versions has no 3.9 build for Ubuntu 26.04 (ubuntu-latest); a third job runs the tests with the runner's own python3, the interpreter `seo-cron.yml` uses. CI runs on pushes to main and on pull requests, not on tags.
- Skills, scripts and the cron workflows work as in 1.0.0; only the version strings changed. The `v1` tag stays on 1.0.0, so callers of `@v1` run the same cron code.

## 1.0.0 (2026-11-25)

First release.

- Ten skills: seo-ops (hub), seo-launch, seo-calendar, seo-google, seo-yandex, seo-geo, seo-content, seo-measure, seo-local, seo-query-gaps. Each splits its work into one-time (new site), recurring and event tasks; facts carry a source and the checked date 2026-11-25.
- Scripts, Python 3.9+ standard library only:
  - `seo_check.py`: external live-site check with 30 checks, Markdown and JSON reports, a self-test that plants a known defect for 28 of them;
  - `seo_calendar.py`: site calendar from a 58-task template (init, due, done, track, validate);
  - `indexnow.py`: changed, new or removed sitemap URLs to IndexNow, dry run by default, 10-minute resend window, 429 handling;
  - `gsc_gaps.py`: gap, striking-distance and weak-CTR queries from a Search Console or Yandex Webmaster export.
- GitHub Actions: reusable `seo-cron.yml` (daily, weekly, monthly, deploy) and four caller templates; CI on Python 3.9 and 3.12.
