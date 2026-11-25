---
name: seo-launch
description: "Technical SEO launch checklist for a new site or store, and the reference for scripts/seo_check.py: one canonical host and permanent redirects, robots.txt, sitemap with honest lastmod, canonical and meta tags, structured data (Organization, WebSite, Product with Offer, BreadcrumbList), 404 and 5xx behaviour, images, caching, HTTPS expiry, security.txt, Core Web Vitals. Every step has a check that can fail. Recurring part: weekly external audit, monthly structured data spot check, quarterly crawl, yearly security.txt and trust page review. Events: deploy, redesign or domain move. Use when launching, migrating or auditing a site, or when seo_check.py reports FAIL or WARN. RU triggers: запуск сайта, технический аудит SEO, чек-лист запуска, robots.txt, sitemap, canonical, микроразметка, редиректы, 404, переезд сайта, что проверить перед запуском."
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
12. `launch-indexnow`: a key file at `/<key>.txt` and the key in a CI secret. Checks: indexnow-key (`--indexnow-key KEY` or the `INDEXNOW_KEY` variable), `python scripts/indexnow.py --site example.com --check-key`.
13. `launch-final-check`: `python scripts/seo_check.py example.com --pages 20` exits 0; each WARN is fixed or written down as a decision.

Follow-up: `launch-indexing-d14`, two weeks later: compare sitemap URLs with indexed pages in Search Console and Yandex Webmaster. A page that is crawled but not indexed needs better content or internal links, not daily resubmission.

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

## Recurring

- `weekly-audit` (cron): the weekly workflow runs `seo_check.py --pages 12`; read new WARN lines.
- `monthly-schema-spotcheck`: Rich Results Test on 5 to 10 product pages; product snippet and merchant listing reports in Search Console; the Yandex validator. No errors in price and availability.
- `quarterly-crawl`: a full crawl with a desktop crawler; compare with the last crawl to catch template regressions.
- `yearly-security-txt`: move the Expires date of security.txt.
- `yearly-trust-review`: review the trust pages and seller details.

## Events

- `event-deploy` (cron): the on-deploy workflow runs `seo_check.py` on the live site, then IndexNow for changed URLs.
- `event-migration` (redesign or domain move): a redirect map for every old URL, a crawl before and after, then 4 to 8 weeks of watching indexing. After the move no old URL answers 404.

## Sources (checked 2026-11-25)

- Google, robots.txt errors: 5xx or 429 stops crawling for up to 12 hours, then the last good copy is used for 30 days: https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt (Official)
- Google, review snippets: self-serving reviews of LocalBusiness and Organization are not eligible for star review features: https://developers.google.com/search/docs/appearance/structured-data/review-snippet (Official)
- Google, merchant listings: offers.price and offers.priceCurrency required, availability recommended: https://developers.google.com/search/docs/appearance/structured-data/merchant-listing (Official)
- Google, breadcrumbs are no longer shown on mobile results since 23 January 2025; BreadcrumbList still works on desktop: https://developers.google.com/search/blog/2025/01/simplifying-breadcrumbs (Official)
- Google, the robots.txt tester was replaced by the robots.txt report in November 2023: https://support.google.com/webmasters/answer/6062598 (Official)
- Yandex, Clean-param is cross-section and can stand anywhere in robots.txt: https://yandex.ru/support/webmaster/ru/robot-workings/clean-param (Official)
- Core Web Vitals thresholds: https://web.dev/articles/vitals (Official)
- security.txt: https://www.rfc-editor.org/rfc/rfc9116 (standard)
