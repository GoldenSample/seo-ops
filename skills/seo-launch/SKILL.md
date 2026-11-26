---
name: seo-launch
description: "Technical SEO launch checklist for a new site or store, and the reference for scripts/seo_check.py (sampled live-site check), scripts/seo_crawl.py (crawl of the whole site, no keys: broken links, redirects, sitemap gaps, orphans, canonical, noindex, titles, H1) and scripts/seo_index.py (published pages missing from the Yandex and Google index, with the owner's keys): canonical host and redirects, robots.txt, sitemap, canonical and meta tags, structured data, 404 and 5xx, images, caching, HTTPS, security.txt, Core Web Vitals. Every step has a check that can fail. Recurring: weekly audit and crawl, monthly index coverage and schema spot check, quarterly deep crawl. Events: deploy, redesign or domain move. Use when launching, migrating or auditing a site, or when a script reports FAIL or WARN. RU triggers: запуск сайта, технический аудит, чек-лист запуска, robots.txt, sitemap, canonical, редиректы, 404, переезд сайта, обход сайта, битые ссылки, страницы-сироты, страницы не в индексе."
license: MIT
---

# seo-launch: launch a site that search engines can read

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

Run the external check first: `python scripts/seo_check.py example.com --pages 12`. Pass the canonical host (with or without www, as the site uses it). Most steps below map to a check id.

## One-time (new site)

Launch day (`offset_days` 0 in the calendar):

1. `launch-passport`: one page in the site repo: canonical host, stack and rendering (server or client), where product data lives, the owner of every dashboard account, who may deploy.
2. `launch-redirects`: http and the other www variant answer 301 or 308 to the same path on the canonical host, in one hop. Checks: redirects, trailing-slash, open-redirect.
3. `launch-tls`: write down the certificate expiry date and who renews it. Check: tls-expiry.
4. `launch-robots`: everything that must rank is open; CSS and JS are open; an absolute `Sitemap:` line. For Yandex, `Clean-param:` for tracking parameters (it is cross-section: Yandex reads it anywhere in the file). Checks: robots-txt, ai-bots. The AI crawler policy is a decision: seo-geo.
5. `launch-sitemap`: built from data; only canonical, indexable URLs that answer 200; `lastmod` is the date the content changed, not the build date. Checks: sitemap, sitemap-urls.
6. `launch-canonical-meta`: absolute self-canonical; a unique title (up to about 70 characters) and description (50 to 160); one h1; `<html lang>`; viewport; og:title, absolute og:image, twitter:card; `<meta name="robots" content="max-image-preview:large">`. Checks: titles, descriptions, h1, lang-viewport, open-graph, image-preview.
7. `launch-structured-data`: one JSON-LD graph: Organization or a store type with `@id`, WebSite, BreadcrumbList, and Product with Offer on pages that show a price. Checks: json-ld, organization, website, product-offer, self-ratings. Then the Rich Results Test and the Yandex structured data validator on three pages.
8. `launch-error-pages`: unknown URLs answer 404 or 410; the 404 page links to the catalog; a 5xx page never carries noindex; a removed product gets a 301 to the closest page or a 410. Check: not-found.
9. `launch-assets`: webp or avif images with width, height and alt; hashed static files cached for a year; no public source maps; gzip or br; HTTP/2. Checks: images, static-cache, source-maps, transport.
10. `launch-speed`: Core Web Vitals at the 75th percentile: LCP up to 2.5 s, INP up to 200 ms, CLS up to 0.1. PageSpeed Insights on the home page, a category and a product page; field data appears only after enough visits.
11. `launch-trust-pages`: contacts with address and phone as text, delivery, returns and warranty, privacy policy, terms, seller details. Yandex lists address, details and contacts among the signals for search and Alice answers.
12. `launch-indexnow`: a key file at `/<key>.txt`, the key in the `INDEXNOW_KEY` CI secret and in the owner's keys file (seo-ops, Keys file). Checks: indexnow-key (`--indexnow-key KEY`, or `INDEXNOW_KEY` of the file named with `--keys`), `python scripts/indexnow.py --site example.com --keys '${user_config.keys_file}' --check-key`.
13. `launch-final-check`: `python scripts/seo_check.py example.com --pages 20 --keys '${user_config.keys_file}'` exits 0; each WARN is fixed or written down as a decision.

Follow-up: `launch-indexing-d14`, two weeks later: which sitemap URLs are indexed. `python scripts/seo_index.py example.com --keys '${user_config.keys_file}'` lists the missing ones with the reason when the owner's keys file has the keys (Index coverage below); without keys, compare in Search Console and Yandex Webmaster by hand. A page that is crawled but not indexed needs better content or internal links, not daily resubmission.

Dashboards, analytics, business profiles and feeds have their own skills: seo-google, seo-yandex, seo-measure, seo-local.

## Reading seo_check.py

FAIL breaks crawling, indexing or rich results. WARN loses value or puts it at risk. INFO is a choice to make. SKIP means not enough data (raise `--pages`, give the key). Exit code 0 = no FAIL, 1 = at least one FAIL (with `--fail-on warn` also any WARN), 2 = the home page did not answer or answered 5xx.

| Check | What FAIL or WARN means | Fix |
|---|---|---|
| home | the home page does not answer 200 | serve 200 on the canonical home URL |
| redirects | http or the other host variant does not answer a permanent redirect to the canonical URL (FAIL); a temporary 302, 303 or 307 (WARN) | one 301 or 308 hop that keeps the path |
| trailing-slash | the other slash form answers 200 without a canonical to the sitemap form | redirect to one form, or a canonical to it |
| open-redirect | `//example.com/` on your host redirects to another host | fix path normalization in the server or framework |
| robots-txt | 5xx or 429 (FAIL: Google stops crawling while robots.txt fails); the home page blocked for a checked engine; CSS or JS blocked; no absolute Sitemap line (WARN) | serve robots.txt as a static 200 file |
| ai-bots | an AI search or answer bot is blocked (WARN): that product will not cite the site | see seo-geo; training bots are a free choice |
| sitemap | not 200, not XML, or no URLs (FAIL); no lastmod, one lastmod on every URL, dates in the future, URLs on another host (WARN) | generate from data; lastmod = content change date |
| sitemap-urls | a sampled sitemap URL does not answer 200, has noindex or a canonical to another URL (FAIL); no canonical or a relative one (WARN) | list only canonical indexable URLs |
| not-found | an unknown URL answers 200 (soft 404, FAIL) or redirects (WARN) | answer 404 or 410 |
| transport | no gzip or br, or no HTTP/2 | enable compression and h2 |
| tls-expiry | under 7 days or handshake failed (FAIL); under 21 days (WARN) | renew, automate renewal |
| response-time | the home page took over 2 s from the runner | cache, CDN, server rendering cost |
| static-cache | a hashed JS or CSS file without a long cache | `Cache-Control: public, max-age=31536000, immutable` |
| source-maps | the `.map` of a JS file is public | do not deploy maps, or restrict them |
| security-headers | no Strict-Transport-Security or no `X-Content-Type-Options: nosniff` | add both headers |
| titles | a page without a title (FAIL); duplicates or over 70 characters (WARN) | one unique title per page |
| descriptions | missing or under 50 characters (WARN); over 160 (INFO) | write one per page template |
| h1 | no h1 (WARN); several (INFO) | one h1 with the page subject |
| lang-viewport | no `<html lang>` or no viewport meta | add both to the layout |
| open-graph | no og:title, no absolute og:image or no twitter:card | add to the layout, absolute image URL |
| image-preview | no `max-image-preview:large` (INFO) | add it to the robots meta |
| images | `<img>` without alt or without width and height | alt text; fixed dimensions against layout shift |
| json-ld | a JSON-LD block does not parse (FAIL); no JSON-LD (WARN) | valid JSON, one graph per page |
| organization | no Organization or store node on the home page (WARN); no `@id` (INFO) | Organization or a store type with `@id` |
| website | no WebSite node on the home page | WebSite node with name and url |
| product-offer | an Offer without price or priceCurrency (FAIL); without availability, or Product without offers (WARN) | price and currency as shown on the page |
| self-ratings | rating or review markup on the organization itself (WARN) | remove it: self-serving reviews of LocalBusiness and Organization are not eligible for review stars |
| security-txt | missing, no Contact, no Expires or expired (WARN) | `/.well-known/security.txt` (RFC 9116) |
| indexnow-key | the key file is missing or its content is not the key (FAIL) | serve `/<key>.txt` with the key as plain text |
| llms-txt | INFO only | optional, see seo-geo |

Politeness: at most 2 requests per second and 60 per run (`--max-requests`), an honest User-Agent, no redirects followed. `--resolve host=IP` checks a server before the DNS switch.

## Crawling the whole site: seo_crawl.py

`seo_check.py` samples a dozen pages; `seo_crawl.py` walks the site with no keys: robots.txt first, then every internal link from the home page, then the sitemap URLs that no link reached. GET and HEAD only, at most 2 requests per second, at most `--max-pages` URLs (default 200) and `--max-seconds` (default 600).

```
python scripts/seo_crawl.py example.com --max-pages 500 --md crawl.md --json crawl-2026-12-01.json
python scripts/seo_crawl.py example.com --max-pages 500 --compare crawl-2026-12-01.json
```

| Check | FAIL or WARN means | Fix |
|---|---|---|
| crawl-coverage | robots.txt answers 5xx, 429 or nothing, or the home page is closed, redirects to another host or answers 4xx (FAIL); the server kept answering 429 (WARN) | fix robots.txt or the home page; let the crawler through the rate limit or crawl with `--delay 2` |
| broken-links | internal links to 4xx pages, with the pages that link to them (FAIL); to 401 or 403 (WARN) | fix the link, or redirect the old URL to the closest page |
| server-errors | 5xx (FAIL); 429 or no answer (WARN: those URLs were not checked) | read the server log for those URLs |
| redirect-links | links that point to a redirect (WARN) | link to the final URL |
| redirect-chains | a loop, a redirect without Location or one that ends in an error (FAIL); two or more hops (WARN) | one hop to the final URL |
| sitemap-errors | a sitemap URL that is not 200, has noindex or a canonical to another URL (FAIL); closed by robots.txt or on another host (WARN) | list only canonical indexable 200 URLs |
| not-in-sitemap | indexable pages that links reach but the sitemap does not list (WARN) | add them, or noindex them if they should not rank |
| orphans | sitemap URLs that no chain of links from the home page reaches (WARN; needs a complete crawl) | link them from a category or hub page, or drop them from the sitemap |
| canonical | a canonical to another host, to a redirect, an error or a noindex page (WARN); relative canonicals (INFO) | an absolute canonical to the right indexable URL |
| titles | a page without a title (FAIL); one title on several pages (WARN) | one unique title per page |
| h1 | no h1, an empty h1, or one h1 text on several pages (WARN); several h1 (INFO) | one h1 with the page subject |
| mixed-host-links | links to the other scheme or www form of the host (WARN): each costs a redirect | link to the canonical form |
| noindex, robots-blocked, query-urls, depth | INFO | check that each noindex and each closed section is meant; links with a query string are crawled only with `--include-query`; depth counts clicks from the home page |
| crawl-diff | with `--compare`: new errors, lost pages and changed titles since an earlier crawl JSON | read every new line |

A 429 or 503 makes the crawler wait (Retry-After, else 10 s doubling) and slow down; URLs it could not fetch count as not checked, not as errors of the site. Exit codes: 0 no FAIL, 1 FAIL (or WARN with `--fail-on warn`), 2 the site did not answer.

## Index coverage: seo_index.py

Which published pages each engine has not indexed, and the reason it gives. Published pages are the sitemap URLs, or with `--pages crawl.json` the indexable 200 pages of a crawl. The keys are the owner's own, read only from the keys file named with `--keys` (seo-ops, Keys file; in the cron, a file the workflow writes from the CI secrets), never from the environment; the pack has none, and without a key that engine's line is SKIP.

```
python scripts/seo_index.py example.com --keys '${user_config.keys_file}' --md index.md --json index.json
python scripts/seo_index.py example.com --keys '${user_config.keys_file}' --pages crawl-2026-12-01.json --google-max 300
```

- **Yandex**: create an app at https://oauth.yandex.ru/client/new with the Webmaster rights (`webmaster:hostinfo`, `webmaster:verify`), then open `https://oauth.yandex.ru/authorize?response_type=token&client_id=<id>` and put the token into `YANDEX_WEBMASTER_TOKEN` of the keys file (and of the CI secrets for the cron). It lives 6 months (Official: https://yandex.ru/dev/webmaster/doc/ru/tasks/how-to-get-oauth , checked 2026-11-26). The script reads the pages in search, the search events (appeared, removed, with the reason) and the robot's crawl samples.
- **Google**: an OAuth client in a Google Cloud project with the Search Console API enabled; authorize once with `access_type=offline` and the scope `https://www.googleapis.com/auth/webmasters.readonly`, then put `GSC_CLIENT_ID`, `GSC_CLIENT_SECRET` and `GSC_REFRESH_TOKEN` into the keys file and the CI secrets (Official: https://developers.google.com/identity/protocols/oauth2/web-server , checked 2026-11-26). While the consent screen of an external app is in the Testing status, Google issues refresh tokens that expire after seven days, and a refresh token unused for six months stops working (Official: https://developers.google.com/identity/protocols/oauth2 , checked 2026-11-26): for the monthly cron, publish the app first. `GSC_PROPERTY` of the keys file or `--gsc-property` (the cron input `gsc_property`) names the property (`https://example.com/` or `sc-domain:example.com`); without it the account's site list is searched. URL Inspection runs for up to `--google-max` URLs (default 100); Google allows 2000 a day and 600 a minute per site (Official: https://developers.google.com/webmaster-tools/limits , checked 2026-11-26).
- Token values never reach the output: every line, the JSON and the Markdown pass a filter that replaces them with `***`, and a token goes only to the official API hosts.

| Line | Meaning |
|---|---|
| yandex-index, google-index | FAIL: a key refused, the site not in the account or not verified. WARN: published pages missing from the index, each with the reason (Webmaster event status such as `NOT_CANONICAL`, `DUPLICATE`, `LOW_QUALITY`, `NO_INDEX`, `HTTP_ERROR`, or the last crawl; Google's coverage state and fetch state) |
| yandex-extra | INFO: pages in Yandex search that the site does not publish (old URLs, parameters, duplicates): redirect them or close them |

Reasons decide the fix: a technical one (noindex, canonical elsewhere, redirect, error) goes back to the crawl report; a duplicate or low-quality one needs better or merged content and internal links; a page that is not crawled yet needs links from crawled pages and, for Yandex, IndexNow. Resubmitting the same URLs every day fixes none of them.

## Recurring

- `weekly-audit` (cron): the weekly workflow runs `seo_check.py --pages 12`; read new WARN lines.
- `weekly-crawl` (cron): the same workflow then runs `seo_crawl.py` over the whole site (input `crawl_pages`, default 200 URLs, 0 turns it off); a FAIL fails the run.
- `monthly-index-coverage`: with the index secrets the monthly workflow runs `seo_index.py` and puts the report into the monthly issue; without them run it locally with the owner's keys file, or compare by hand in Search Console and Yandex Webmaster.
- `monthly-schema-spotcheck`: Rich Results Test on 5 to 10 product pages; product snippet and merchant listing reports in Search Console; the Yandex validator. No errors in price and availability.
- `quarterly-crawl`: a deep crawl, `python scripts/seo_crawl.py example.com --max-pages 2000 --max-seconds 0 --json crawl-<date>.json --compare <last crawl JSON>`, or a desktop crawler; compare with the last crawl to catch template regressions.
- `yearly-security-txt`: move the Expires date of security.txt.
- `yearly-trust-review`: review the trust pages and seller details.

## Events

- `event-deploy` (cron): the on-deploy workflow runs `seo_check.py` on the live site, then IndexNow for changed URLs.
- `event-migration` (redesign or domain move): a redirect map for every old URL; `seo_crawl.py --json before.json` before the move and `--compare before.json` after it. The crawl-diff line lists old pages that answer an error now (lost) and old pages that no link or sitemap reaches any more (not met); the crawler does not request those, so request each and check that it redirects to its new page. Then 4 to 8 weeks of watching indexing with `seo_index.py`. After the move no old URL answers 404.

## Sources (checked 2026-11-25)

- Google, robots.txt errors: 5xx or 429 stops crawling for up to 12 hours, then the last good copy is used for 30 days: https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt (Official)
- Google, review snippets: self-serving reviews of LocalBusiness and Organization are not eligible for star review features: https://developers.google.com/search/docs/appearance/structured-data/review-snippet (Official)
- Google, merchant listings: offers.price and offers.priceCurrency required, availability recommended: https://developers.google.com/search/docs/appearance/structured-data/merchant-listing (Official)
- Google, breadcrumbs are no longer shown on mobile results since 23 January 2025; BreadcrumbList still works on desktop: https://developers.google.com/search/blog/2025/01/simplifying-breadcrumbs (Official)
- Google, the robots.txt tester was replaced by the robots.txt report in November 2023: https://support.google.com/webmasters/answer/6062598 (Official)
- Yandex, Clean-param is cross-section and can stand anywhere in robots.txt: https://yandex.ru/support/webmaster/ru/robot-workings/clean-param (Official)
- Core Web Vitals thresholds: https://web.dev/articles/vitals (Official)
- security.txt: https://www.rfc-editor.org/rfc/rfc9116 (standard)
- Robots Exclusion Protocol: a robots.txt that answers 5xx or cannot be reached means complete disallow for the crawler: https://www.rfc-editor.org/rfc/rfc9309 (standard)

## Sources for the crawl and index tools (checked 2026-11-26)

- Yandex Webmaster API v4: pages in search, search events with the exclusion status, crawl samples, errors and quotas: https://yandex.ru/dev/webmaster/doc/ru/reference/hosts-indexing-insearch-samples , https://yandex.ru/dev/webmaster/doc/ru/reference/hosts-search-events-samples , https://yandex.ru/dev/webmaster/doc/ru/reference/hosts-indexing-samples , https://yandex.ru/dev/webmaster/doc/ru/reference/errors (Official)
- Search Console URL Inspection: only the version in the Google index is shown: https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect (Official)
- Google OAuth 2.0: refresh tokens, the seven-day expiry in the Testing status: https://developers.google.com/identity/protocols/oauth2 (Official)
