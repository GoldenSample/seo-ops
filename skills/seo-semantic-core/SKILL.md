---
name: seo-semantic-core
description: "Build and refresh the semantic core of a small site or store: markers from the catalog, phrases and counts from the official Wordstat API (scripts/wordstat.py) or by hand, a stop list, commercial and local intent, clusters by shared top-10 results (scripts/serp_cluster.py, soft or hard, threshold 3) and one target page per cluster. One-time: launch-semantic-core. Recurring: quarterly-semantic-refresh. Event: new category or product line. Arsenkin's MCP server is an optional paid source for each step. Use for a semantic core, keyword research, keyword clustering by search results, which page targets which keywords, site structure from keywords, keyword cannibalization. RU triggers: семантическое ядро, собрать семантику, кластеризация запросов, кластеризация по выдаче, группировка запросов, Вордстат, частотность, маркеры, минус-слова, коммерциализация, геозависимость, структура сайта по запросам, каннибализация, Арсенкин, Arsenkin."
license: MIT
---

# seo-semantic-core: the phrases the site answers, grouped the way the results group them

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

The semantic core is the list of phrases the site should rank for, each with its count, its intent and the one page that answers it. The grouping comes from the results: phrases whose top 10 share several URLs are answered by the same pages, so one page can rank for all of them; phrases that share none need different pages. Words that look alike do not decide it, only the results do (Practice: the method of SERP clustering tools, Arsenkin's clustering help, checked 2026-11-26).

## The steps

| Step | With the pack or by hand | Arsenkin MCP tool (optional, paid) | Done when |
|---|---|---|---|
| 1. Markers | catalog categories, product types, services, brands you sell, questions buyers ask | `arsenkin_semantics`: the queries a domain (a competitor's) already ranks for | `markers.txt`, one marker per line |
| 2. Expansion | `wordstat.py top --phrases markers.txt --num 300 --regions 213 --csv top.csv`; or the Wordstat site and Yandex suggestions by hand | `arsenkin_wordstat_phrases`, `arsenkin_suggest` | `top.csv`: the queries that contain each marker, and similar queries |
| 3. Cleaning | strike brands you do not sell, cities you do not serve, "бесплатно", "своими руками", jobs, other products; keep the stop list in `stop-words.txt` | the same tools take a stop list in the prompt | `phrases.txt` and the stop list |
| 4. Counts | the counts come with `top.csv`; for phrases added by hand: `wordstat.py top --phrases extra.txt --num 1 --csv extra.csv` | `arsenkin_wordstat_frequency`: base count and count "in quotes" | every phrase has a count, its date and region |
| 5. Intent | open the top 10 of each big phrase: shops and prices, or articles; compare the top 10 in two regions | `arsenkin_commerce`: commercial and local intent | each cluster marked commercial, informational or mixed, local or not |
| 6. Results | the top 10 of each phrase in one region: by hand into a wide CSV for a small core, or from any service that exports them | `arsenkin_top` | `serp.csv`: phrase, position, url |
| 7. Clusters | `serp_cluster.py serp.csv --freq top.csv --freq extra.csv --site example.com --md clusters.md --csv clusters.csv` | `arsenkin_clustering` | `clusters.md` read with Claude |
| 8. Pages | the Site page column, the new-page list, split clusters, shared pages | `arsenkin_relevant_urls` | every cluster has one target page or a dated "not now" |
| 9. Record | demand notes in the decision log; the core file in the site repo | - | the core can be rebuilt from the files and the log |

Region 213 is Moscow; `python scripts/wordstat.py tree` lists every region ID and costs nothing (it is still a request with your key). Use the same region in steps 2, 4 and 6: counts and results change from region to region (Practice).

## Counts from the official Wordstat API

- `wordstat.py` calls Yandex Search API v2: `top` returns how often a phrase was searched in the last 30 days, up to 2000 queries that contain it and similar queries; `dynamics` gives searches per month, week or day for seasonality (Official: https://aistudio.yandex.ru/ru/docs/search-api/api-ref/Wordstat/getTop , checked 2026-11-26).
- A key of your own, only from the keys file (seo-ops, Keys file), never from the environment: `YANDEX_CLOUD_API_KEY` (service account with the role `search-api.webSearch.user`) or `YANDEX_CLOUD_IAM_TOKEN`, and `YANDEX_CLOUD_FOLDER_ID` (or `--folder-id`). Add `--keys '${user_config.keys_file}'` to every `wordstat.py` command, `tree` included (free, but still a request with the key); only `--dry-run` and answers already in the cache work without it. The key never reaches the output or the cache.
- Price with VAT: 20 ₽ per 1000 requests for `top` and `dynamics`, 50 ₽ for `regions`, the regions tree free; quota 100 requests an hour (Official: https://aistudio.yandex.ru/ru/docs/search-api/pricing , https://aistudio.yandex.ru/ru/docs/search-api/concepts/limits , checked 2026-11-26). `--dry-run` prints the requests, price and time first; answers are cached, so a broken run goes on where it stopped.
- Operators: the Wordstat site documents `-word`, `!form`, `+stopword`, `"quotes"`, `[order]` and `(a|b)` (Official: https://yandex.ru/support2/wordstat/ru/content/operators , checked 2026-11-26). The API pages do not mention them and the pack has not tried them through the API: compare one phrase on the site and through the API before you rely on them.
- A count is searches in Yandex, not visits, and Google is not in it. For Google, read the queries where the site already appears in Search Console (seo-query-gaps).
- A big base count with a tiny count "in quotes" means the exact phrase is rarely searched: Arsenkin's example on its server page shows 3 323 against 6.

## Results and clusters

`serp_cluster.py` reads results from any source; it has no network access and needs no key. Two shapes:

- long: one row per result, `phrase, position, url` (a frequency column is used when present);
- wide: one row per phrase, the phrase and then the URLs in position order; a file whose first row already holds URLs is read as having no header.

Headers in English or Russian, UTF-8 or windows-1251, comma, semicolon or tab. URLs are compared without scheme, www, default port, trailing slash and fragment; percent-encoding and punycode are decoded.

To see the output before collecting your own results, run it on the made-up tea shop in `examples/` (next to `scripts/`): `python scripts/serp_cluster.py examples/serp.csv --freq examples/freq.csv --site example.com`.

| Flag | Default | Meaning |
|---|---|---|
| `--mode soft` | soft | the most frequent phrase not yet placed is the centre; a phrase joins when it shares `--threshold` URLs with the centre. Arsenkin: for articles, traffic projects, large cores |
| `--mode hard` | | a phrase joins only when it shares the threshold with every phrase already in the cluster; more, smaller clusters. Arsenkin: for niche projects and strong competition |
| `--threshold` | 3 | shared URLs needed. Arsenkin: grouping strength 2 to 10, "optimal 3", start with 3 or 4 |
| `--top` | 10 | positions that count. Arsenkin: depth TOP-10 by default, TOP-20 and TOP-30 as options |
| `--site` | | your host: each cluster gets the page of the site that ranks for most of its phrases |

These are a tool's norms, not a search engine rule (Practice: https://arsenkin.ru/tools/clustering/ , https://help.arsenkin.ru/instrumenty/clustering , checked 2026-11-26). Look at a few clusters by eye before trusting the rest.

Getting the results:

- By hand: for a core of a few dozen phrases, copy the top 10 of each phrase into a wide CSV. Results differ by region and device; collect all phrases in one region, signed out (Practice).
- Yandex Search API returns results too, from 25,41 ₽ to 488 ₽ per 1000 requests by mode and time of day, but its v2 answer format is not documented, so the pack does not parse it (Official: https://aistudio.yandex.ru/ru/docs/search-api/pricing , https://aistudio.yandex.ru/ru/docs/search-api/api-ref/WebSearch/search , checked 2026-11-26).
- Arsenkin's `arsenkin_top`: ask Claude to save the results as `serp.csv` with columns phrase, position, url.

## Reading clusters.md with Claude

- **Candidates for new pages**: clusters where the site has no page in the results the file holds. Is it something the business sells or can answer? Is the count worth a page? Then a demand note and seo-content.
- **One cluster, several pages of the site**: the results show different pages of yours for one intent. Pick one target page, point internal links at it, merge or rewrite the others so they answer a different intent (Practice; seo-content).
- **One page, main page of several clusters**: either the clusters are one intent for your site (merge them) or one of them needs its own page.
- **Clusters of one phrase**: a page of its own, a section of a bigger page, or not worth a page; decide by count and intent.

## Arsenkin MCP (optional)

- Server `https://mcp.arsenkin.ru/mcp`, Streamable HTTP, token in `Authorization: Bearer`; 51 tools, 22 of them paid (vendor page https://mcp.arsenkin.ru/ , checked 2026-11-26).
- Connect: `claude mcp add --transport http arsenkin https://mcp.arsenkin.ru/mcp --header "Authorization: Bearer <token>"`, or without the header and then `/mcp`, Authenticate. Keep the token out of the site repo: do not add the server with `--scope project`, which writes `.mcp.json` into the repo.
- Cost: no separate fee for MCP, paid tools spend the account's limits. The API and MCP are open on the Standard and Corporate plans, 2 490 ₽ and 7 990 ₽ a month; Standard has 85 000 limits; a count costs 1 limit per phrase, clustering and index checks 1.5 limits per phrase or URL (vendor page https://arsenkin.ru/tariffs/ , checked 2026-11-26).
- Pace: 30 requests a minute, 5 tasks at once, 50 in the queue. `arsenkin_limits` shows what is left, each task reports its cost. The "Yandex XML" source works only at night Moscow time, so such tasks wait during the day.
- Index checks: `arsenkin_indexation`, or the pack's own `seo_index.py` with your Webmaster and Search Console keys in the keys file (seo-launch).

## One-time: launch-semantic-core

Before the site structure is fixed: steps 1 to 9. Done when the core file (phrase, count with date and region, intent, cluster, target page) is in the site repo, for example `seo/semantic-core.csv` from `clusters.csv` plus intent and target page columns, and every cluster above the count floor the owner chose has a target page or a dated "not now" line in the decision log.

## Recurring: quarterly-semantic-refresh (every 91 days)

1. New phrases: accepted gaps from seo-query-gaps, new products and categories, new Wordstat queries for the markers (`wordstat.py top --cache-days 0`).
2. Seasonality for the big markers: `wordstat.py dynamics --period monthly` (feeds quarterly-seasonal).
3. Fresh results for the new phrases and for clusters whose page lost positions; rerun `serp_cluster.py` on the whole core; compare the target pages with the last core. Every change of a target page goes to the decision log.

## Events

- New category or product line: steps 1 to 8 for its markers before the pages are made, then event-new-page for each new page.
- Traffic drop on one page: check whether the results for its cluster changed and still point to it (seo-measure).

## Do not

- Do not make a page for every phrase variant: Google's spam policies list scaled content abuse, and Yandex counts pages without value as low-value (seo-content).
- Do not cluster by shared words alone, and do not mix regions or devices in one results file (Practice).
- Do not put the Yandex Cloud key or the Arsenkin token in the site repo, a CSV or the decision log.
- Do not plan from counts of one month without a look at seasonality for seasonal goods (Practice).

## Sources (checked 2026-11-26)

- Wordstat API: https://aistudio.yandex.ru/ru/docs/search-api/api-ref/Wordstat/getTop , https://aistudio.yandex.ru/ru/docs/search-api/api-ref/Wordstat/getDynamics , https://aistudio.yandex.ru/ru/docs/search-api/api-ref/Wordstat/getRegionsDistribution , https://aistudio.yandex.ru/ru/docs/search-api/concepts/limits , https://aistudio.yandex.ru/ru/docs/search-api/pricing
- Wordstat operators: https://yandex.ru/support2/wordstat/ru/content/operators
- Clustering modes and defaults: https://arsenkin.ru/tools/clustering/ , https://help.arsenkin.ru/instrumenty/clustering
- Arsenkin MCP server and plans: https://mcp.arsenkin.ru/ , https://arsenkin.ru/tariffs/
