---
name: seo-google
description: "Google Search and Bing for a small site or store: Search Console setup, sitemap, the generative AI setting (AI Overviews and AI Mode), the Generative AI performance report, core and spam updates and how to read them, Indexing API limits, crawler logs, Merchant Center and product markup, Bing Webmaster Tools. One-time: verify properties, submit sitemaps, confirm the site is included in AI features. Recurring: weekly index and performance snapshot, crawler log review every two weeks. Events: core update, traffic drop. Use when working with Google Search Console, Bing, AI Overviews, core updates or Google Merchant. RU triggers: Google Search Console, Гугл вебмастер, AI Overviews, AI Mode, апдейт ядра Google, core update, Bing Webmaster, Merchant Center, индексация в Google, просела позиция в Google."
license: MIT
---

# seo-google: Google Search, AI features and Bing

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

## How Google builds AI answers (checked 2026-11-25)

- AI Overviews and AI Mode start from ranked results; their snippets go to the model as grounding, related searches are added (query fan-out), and supporting pages are cited. The model works on top of core ranking. Official: https://developers.google.com/search/docs/fundamentals/gen-ai-attribution-factuality
- A page can appear in AI features when it is indexed and eligible to show with a snippet. There are no extra technical requirements and no special schema. Official: https://developers.google.com/search/docs/appearance/ai-features
- The Search Console generative AI setting decides whether the site appears in AI Overviews and AI Mode; it does not control model training. Google-Extended does not affect inclusion in Search. noindex, nosnippet and max-snippet limit what can be shown. Official: https://developers.google.com/search/docs/fundamentals/gen-ai-controls
- When an AI Overview was shown, organic clicks out of Google fell by 39.8% in a randomized experiment (1,065 desktop Chrome users in the US, January to February 2026). Measured: https://ppc.land/researchers-find-google-ai-overviews-cut-publisher-clicks-39-8/

So the work is ordinary SEO: indexable pages that rank and answer the query. seo-geo covers AI crawlers and AI visibility.

## One-time (new site)

1. `launch-search-console`: add a domain property (DNS verification covers every protocol and subdomain), submit the sitemap, and check that the generative AI setting shows "included". Sites that are excluded get no traffic and no impressions from these features (Official, gen-ai-controls above).
2. `launch-bing-webmaster`: add the site to Bing Webmaster Tools (import from Search Console is offered), submit the sitemap. Bing also takes IndexNow (seo-yandex).
3. Product markup: Product with Offer (price, priceCurrency, availability) on product pages; shipping (OfferShippingDetails) and returns (MerchantReturnPolicy) where you have the data. Merchant listings require price and priceCurrency; availability is recommended. Official: https://developers.google.com/search/docs/appearance/structured-data/merchant-listing
4. Merchant Center only if you can sell to the target country. The Content API for Shopping closed on 18 August 2026; new integrations use the Merchant API. Official: https://developers.google.com/shopping-content/guides/sunset

## Recurring

| Id | Every | What |
|---|---|---|
| weekly-index-snapshot | 7 days | Pages report (indexed, not indexed and why) and Performance (impressions, clicks, CTR, position); compare with last week (seo-measure) |
| weekly-ai-visibility | 7 days | Generative AI performance report: impressions of your pages in AI Overviews and AI Mode by page, country, date and device; no clicks and no queries are reported (seo-geo) |
| biweekly-crawler-logs | 14 days | server logs: Googlebot and Bingbot hits, 4xx and 5xx to robots, any 403 or 429 a firewall sends to search robots |
| monthly-schema-spotcheck | 30 days | Rich Results Test on 5 to 10 product pages; product snippet and merchant listing reports |

## Events

- `event-core-update`: core updates are announced on the Google Search Status Dashboard (https://status.search.google.com/). Wait at least one full week after the rollout ends, then compare the week after with the week before the start. Core updates do not target single sites; the effect of fixes can show in days or take months. Official: https://developers.google.com/search/updates/core-updates
  - 2026 so far: March core (from 27 March, 12 days), May core (from 21 May, 12 days), November core (from 10 November, about 14 days); a December 2026 core update was announced on 24 November without dates. Spam updates in March, June, August and September 2026. Source: the dashboard history, read 2026-11-25.
- `event-traffic-drop`: runbook in seo-measure; check the dashboard first.

## Do not

- Do not use the Indexing API for a store: it is only for pages with JobPosting or BroadcastEvent, with a daily quota, and access can be revoked for misuse. Official: https://developers.google.com/search/apis/indexing-api/v3/quickstart
- Do not look for the robots.txt tester: it was replaced by the robots.txt report in November 2023. Official: https://support.google.com/webmasters/answer/6062598
- Do not expect breadcrumbs in mobile results: Google stopped showing them on mobile on 23 January 2025 (desktop still shows them). Official: https://developers.google.com/search/blog/2025/01/simplifying-breadcrumbs
- Do not mark up ratings of your own business: self-serving reviews of LocalBusiness and Organization are not eligible for star review features. Official: https://developers.google.com/search/docs/appearance/structured-data/review-snippet

## Notes for stores outside the big markets

- Google Ads has paused ads to users in Russia since March 2022, so Shopping ads are not an option there (ppc.land, October 2026). Whether free product listings work for a store selling only in Russia: no data found.
- In the EEA free product listings and the "popular products" carousels were removed in September 2026 (Search Engine Roundtable, September 2026). Product rich results from markup on your own pages still work without Merchant Center.
