---
name: seo-ops
description: "SEO operations for a small site or online store across Google, Yandex and AI answers (AI Overviews, AI Mode, Alice AI, ChatGPT search, Perplexity). Splits every task into one-time at launch, recurring (daily to yearly, run by a cron job in GitHub Actions or by a person) and on events (deploy, new page, price change, traffic drop, core update, migration). Start here: routes to seo-launch, seo-calendar, seo-google, seo-yandex, seo-geo, seo-semantic-core, seo-content, seo-measure, seo-local and seo-query-gaps. Every rule carries a source and a checked date. Use for: SEO plan for a new site, SEO checklist, SEO audit, what to do every week, SEO calendar, technical SEO, GEO, AI search visibility. RU triggers: SEO для нового сайта, продвижение сайта или магазина, чек-лист SEO, аудит SEO, что делать регулярно, SEO-календарь, Яндекс и Google, Алиса, нейроответы, GEO."
license: MIT
---

# seo-ops: SEO for a small site, one-time and recurring

This pack turns SEO into a calendar. Every task is one of three kinds:

- **once**: done at launch, with a check that can fail;
- **every N days**: run by a cron job (GitHub Actions) or done by a person in a dashboard;
- **on an event**: deploy, new page, price change, traffic drop, Google core update, migration, dashboard data outage.

The calendar is one JSON file, `templates/calendar.json` (62 tasks). `scripts/seo_calendar.py` turns it into the site's own calendar with dates, and four scheduled workflows run the cron part. Answer the user in their language; the skill text is English.

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo. Python 3.9 or newer, standard library only.

## Map

| Skill | Covers |
|---|---|
| seo-launch | launch checklist; what `seo_check.py` (a sample of pages), `seo_crawl.py` (the whole site) and `seo_index.py` (pages missing from the index) check and how to fix each result |
| seo-calendar | the calendar file, the cron jobs in GitHub Actions, the monthly issue with human tasks |
| seo-google | Search Console, Bing Webmaster, AI features eligibility, core updates, crawler logs, Merchant Center |
| seo-yandex | Yandex Webmaster, region, Clean-param, Yandex Products feed, IndexNow and reindexing at Yandex, outages |
| seo-geo | AI answers: crawler policy, llms.txt, what gets cited, how to measure AI visibility |
| seo-semantic-core | semantic core: markers, Wordstat counts (`wordstat.py`), stop list, intent, clusters by shared top-10 results (`serp_cluster.py`), one target page per cluster |
| seo-content | product pages, guides, comparisons, listicles, AI-written text, links, pruning |
| seo-measure | baseline, decision log, control pages, attribution, traffic drop runbook |
| seo-local | Yandex Business, 2GIS, Google Business Profile, reviews, name, address and phone |
| seo-query-gaps | queries where the site is already visible but has no page: export, script, page plan |

## Start on a new site

1. Check the live site: `python scripts/seo_check.py example.com --pages 12` (GET and HEAD only, 2 requests per second, at most 60 requests), then crawl it: `python scripts/seo_crawl.py example.com` (the same politeness, at most 200 URLs by default).
2. Make the calendar: `python scripts/seo_calendar.py init --site example.com --launch 2026-12-01`, commit `seo-calendar.json`.
3. Copy the workflows from `templates/workflows/` into the site repo `.github/workflows/`, set the `SEO_SITE` variable and, for IndexNow, the `INDEXNOW_KEY` secret (seo-calendar); for the index report in the monthly issue, the index secrets (seo-launch, Index coverage).
4. Work the launch list: `python scripts/seo_calendar.py due` shows what is due; `python scripts/seo_calendar.py done <id>` closes a task.
5. Once a month the monthly workflow opens an issue with the human tasks for the next 31 days.

## Laws

1. **Read-only by default.** Checks use GET and HEAD. Anything that writes (IndexNow submission, dashboard edits, file uploads to business profiles) needs an explicit flag or a person.
2. **A check that can fail.** Every one-time task has a check. "Done" without the check is not done.
3. **One change at a time, written down.** Each SEO change gets a line in the decision log (`templates/decision-log.md`): date, what changed, what else changed at the same time, control pages, review date.
4. **Numbers from a source.** No conclusion from single-digit numbers; compare equal windows; mark dashboard outages and core updates as excluded windows.
5. **Facts go stale.** Every fact here has a checked date. Re-read the sources every quarter (`quarterly-rules-recheck`).
6. **No tricks.** No bought links, no keywords added to a business name, no ratings copied from other platforms, no mass pages without value. Google's spam policies and Business Profile guidelines forbid them, and Yandex counts mass pages without value as low-value content.
7. **No keys by default.** `seo_check.py`, `seo_crawl.py`, `seo_calendar.py`, `gsc_gaps.py` and `serp_cluster.py` need no key; `indexnow.py` uses the site's IndexNow key, which the protocol makes public. `seo_index.py` and `wordstat.py` use the owner's own keys from the environment or CI secrets, never print them and send them only to the official API hosts. Yandex Cloud bills Wordstat requests to the owner's account: run `wordstat.py ... --dry-run` first, it shows the requests, the price and the time.

## Evidence levels

- **Official**: the search engine's own documentation, help or blog.
- **Measured**: a published study with a named method and sample. Samples are often small; the line says so.
- **Practice**: practitioner consensus or an observation on live sites. Treat it as a hypothesis and measure it on your site.

## What holds on 2026-11-25

| Claim | Level | Source |
|---|---|---|
| AI Overviews and AI Mode are built from ranked results; the model works on top of core ranking | Official | https://developers.google.com/search/docs/fundamentals/gen-ai-attribution-factuality |
| A page can appear in Google AI features if it is indexed and eligible for a snippet; no extra technical requirement, no special schema | Official | https://developers.google.com/search/docs/appearance/ai-features |
| Search Console has a generative AI setting; sites excluded there get no traffic or impressions from these features | Official | https://developers.google.com/search/docs/fundamentals/gen-ai-controls |
| Creating llms.txt neither helps nor harms visibility in Google Search | Official | https://developers.google.com/search/docs/fundamentals/ai-optimization-guide |
| 97% of llms.txt files got no requests in May 2026 (137k domains) | Measured | https://ahrefs.com/blog/llmstxt-study/ |
| Yandex: no fundamentally new requirements for Alice AI answers; expertise, usefulness, originality and content decide | Official | https://yandex.ru/support/webmaster/ru/epos |
| Alice cites the position-1 page in 50.6% of answers, pages beyond position 30 in 7.0% (Moscow, Sep-Nov 2026, mostly commercial queries) | Measured | https://blog.promopult.ru/seo/issledovanie-kak-ii-v-poiske-otvechayut-v-raznyh-biznes-nishah.html |
| Russia, October 2026: Yandex 70.22% and Google 28.36% of search | Measured | https://gs.statcounter.com/search-engine-market-share/all/russian-federation |
| IndexNow reaches Bing, Yandex, Seznam, Naver, Amazon and Yep; Google does not take part; a submission does not guarantee indexing | Official | https://www.indexnow.org/faq |
| The Google Indexing API is only for pages with JobPosting or BroadcastEvent | Official | https://developers.google.com/search/apis/indexing-api/v3/quickstart |
| After a core update, wait at least one full week after the rollout ends before comparing | Official | https://developers.google.com/search/updates/core-updates |
| Yandex Webmaster tools were limited from 11 October 2026; part of them came back on 23 November 2026 | Official | https://webmaster.yandex.ru/blog/webmaster-update |

## One-time (new site)

- `launch-passport`: write the site passport: canonical host, stack and rendering, where product data lives, the owner of every dashboard account, who may deploy.
- `launch-calendar`: `seo_calendar.py init`, then copy the workflows (seo-calendar).
- Then follow seo-launch step by step.

## Recurring

- `quarterly-rules-recheck`, every 91 days: open each source in the table above and in the calendar; update the checked date or the rule. Search engine rules and dashboards change several times a year.
- Everything else recurring is in the calendar; `seo_calendar.py due --within 31` lists it.

## Myths this pack does not follow

- "llms.txt gets you into AI answers": no evidence, see above.
- "Ping Google with the Indexing API": only for job posting and livestream pages.
- "Send every URL to IndexNow every day": only changed URLs; one URL at most every 10 minutes (seo-yandex).
- "GEO needs special markup or chunked text": neither Google nor Yandex asks for it; rank first (seo-geo).
- "A 'best X' listicle with yourself on top gets you cited": not shown; small tests found no citations (seo-content).
