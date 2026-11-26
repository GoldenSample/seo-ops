---
name: seo-query-gaps
description: "Find the pages a site is missing from its own search data: export 12 months of Search Console queries (Performance, Export) and the Yandex Webmaster query statistics, run scripts/gsc_gaps.py to list gap queries (the site is shown, but no page targets the query), striking-distance queries (average position 8 to 20) and top-5 queries with weak CTR, then turn the accepted gaps into page tasks with a demand note and review dates. Recurring: monthly query gap pass. Event: new page. Use when the user wants content ideas from Search Console, asks which pages to create, uploads Queries.csv, or asks about keyword gaps, striking distance or low CTR queries. RU triggers: выгрузка запросов из Search Console, каких страниц не хватает, пробелы в запросах, запросы без страницы, Queries.csv, запросы на 8-20 позиции, низкий CTR, идеи статей из поисковых запросов, выгрузка Вебмастера."
license: MIT
---

# seo-query-gaps: pages the search data already asks for

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

The idea: a search engine already shows the site for some queries that no page really answers. Those impressions are demand you have proof of. A page made for such a query starts with evidence, not a guess.

## One-time (new site)

Nothing on launch day: a new site has no query data yet. The calendar template starts `monthly-query-gaps` 90 days after launch (`offset_days: 90`), when the exports hold about three months. Until then, plan pages from the semantic core (seo-semantic-core) and from the questions buyers ask.

## Recurring: monthly-query-gaps (every 30 days)

1. **Google export.** Search Console, Performance (Search results). The default view shows the past three months (Official: https://support.google.com/webmasters/answer/7576553 , checked 2026-11-25), so set the date range to the last 12 months first. Then Export, CSV: the download is a zip with one CSV per table tab; take `Queries.csv` (Practice: the help page names the Export button but not the file layout).
2. **Yandex export.** Yandex Webmaster, query statistics, export. After the October 2026 outage, query monitoring keeps data only for the last two weeks (Topvisor, 23 November 2026: https://journal.topvisor.com/ru/news/23-11-2026-yandex-webmaster-tools-restoration-update/). Until a longer history is back, run the Yandex part on what is there and say so in the log.
3. **Run the script.** Pages come from the sitemap (one request per second, up to 200 pages) or from a CSV with `url` and `title` columns:

```
python scripts/gsc_gaps.py Queries.csv --sitemap https://example.com/sitemap.xml --format md --out gaps.md
python scripts/gsc_gaps.py yandex-queries.csv --pages pages.csv --format csv --out gaps-yandex.csv
```

Flags: `--min-impressions` (default 10), `--gap-threshold` (default 0.6), `--top` rows per list in Markdown (default 30), `--max-pages` (default 200), `--format md|json|csv`. Headers in English and Russian are recognized, with comma or semicolon, percent or fraction CTR. Exit code 2 means bad input or no pages.

4. **Read the three lists.** A query can be in more than one.

| List | Rule in the script | What it usually means |
|---|---|---|
| gaps | best word match with any page below the threshold | candidate for a new page or a new section of an existing page |
| striking | average position 8 to 20 | a better page or internal links from strong pages may move it to page one |
| low_ctr | position up to 5 and CTR under half of a rough planning number (25, 15, 10, 7, 5 % for positions 1 to 5) | rewrite title and description; the numbers are planning aids, not a benchmark |

The match is word overlap after simple stemming, with Cyrillic words also tried in Latin transliteration (so `/motogarnitury/` matches "мотогарнитуры"). It cannot see meaning: synonyms and word order fool it. It sorts; you decide.

5. **Decide with Claude.** Give Claude the Markdown and the list of existing pages. For each gap ask: is it one intent or several, does an existing page already answer it (then add a section or an internal link instead of a new page), is it something the business sells or can answer from experience, is it worth a page at its impressions. Merge queries with one intent into one page. When it is unclear whether two queries are one intent, compare their top-10 results: `scripts/serp_cluster.py` puts queries that share at least 3 result URLs into one cluster (seo-semantic-core).
6. **Write tasks, not pages.** Each accepted topic gets a demand note in the decision log (query cluster, impressions and positions with the export date, the page type) and goes through seo-content. After publishing: `python scripts/seo_calendar.py track <url> --on <publish date>` adds review tasks at 7, 21 and 90 days. Accepted gaps also go into the semantic core: `quarterly-semantic-refresh` (seo-semantic-core) clusters them with the rest, so a gap that joins an existing cluster goes to that cluster's page.

## What the export does not show

- Anonymized queries are left out of query data, even in the bulk export (Official: https://support.google.com/webmasters/answer/12918484 , checked 2026-11-25). So the query rows add up to less than the site totals.
- The help pages state no row limit for the interface export. For complete data Google offers a scheduled daily bulk export to BigQuery (Official, same page). For a small site the interface export is usually enough (Practice).
- Impressions are not demand in full: a query where the site is not shown at all never appears. For demand the site does not touch yet, use Wordstat (`scripts/wordstat.py` with the owner's Yandex Cloud key in the keys file, or the Wordstat site) or Keyword Planner (seo-semantic-core).
- Brand and navigational queries show up as gaps when no page title holds the brand; skip them.

## Events

- `event-new-page`: demand note first, then `track` after publishing (seo-content).

## Do not

- Do not create one page per query variant: Google lists scaled content abuse as spam, and Yandex counts thin pages as low-value (seo-content).
- Do not plan from a window broken by a data outage or a core update without saying so (seo-measure, `event-data-outage`).
- Do not paste client data into tools that keep it; the script runs locally and sends nothing except the sitemap and page requests.
