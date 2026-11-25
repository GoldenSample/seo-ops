---
name: seo-local
description: "Local SEO and business profiles for a small business with an address or pickup point: Yandex Business, 2GIS and Google Business Profile with the same name, address, phone and hours as the site (NAP table), main category, exact map pin, business name rules, reviews and answers, ratings on the site that match the map, safe edits of profile items and prices, Yandex Business tiers. One-time: profiles and NAP table. Recurring: weekly review answers, monthly profile check against the site. Event: price or stock change. Use for Google Business Profile, Yandex Business, 2GIS, maps, local pack, reviews, NAP consistency. RU triggers: Яндекс Бизнес, карточка организации, 2ГИС, Google Business Profile, Google Мой бизнес, карты, отзывы, ответы на отзывы, рейтинг на картах, адрес и телефон, рубрика, локальная выдача, прайс в карточке."
license: MIT
---

# seo-local: maps, profiles and reviews

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

## Why it matters (checked 2026-11-25)

- Yandex tells sites that want to rank and appear in Alice AI answers to register in Yandex Business and to show address, company details and contacts. Official: https://yandex.ru/support/webmaster/ru/epos
- The site region in Yandex can be set through Yandex Business. Official: https://yandex.ru/support/webmaster/ru/site-geography/site-region.html
- Google Business Profile: the business name must match the real-world name (signage, branding); adding keywords or extra details can get the profile suspended. Official: https://support.google.com/business/answer/3038177
- Whitespark Local Search Ranking Factors 2026 (6 November 2025, 47 experts, 187 factors) puts "open at the time of search" fifth among local pack factors: wrong hours cost visibility. Measured as an expert survey: https://whitespark.ca/local-search-ranking-factors/ . Percentage weights quoted around the web are not in the report text.

## One-time (new site): launch-business-profiles

1. **NAP table first.** One table with the name, address (with postal code), phone (with city code), hours, site URL and main category, exactly as on the site. Every profile is filled from this table, character by character.
2. **Yandex Business:** verify rights, main category, exact map pin, the site URL as in Yandex Webmaster. Region and profile then show in Webmaster.
3. **2GIS:** the same data from the table (Practice: no official ranking guidance found).
4. **Google Business Profile** where the business is eligible: name as on the sign, no keywords; categories; hours, including special hours. Whether it works fully for a business in Russia: no reliable data found (2026-11-25).
5. **Site side:** address and phone as text (not an image) on the contacts page and in the footer; an Organization or LocalBusiness JSON-LD block with the same data (seo-launch).

## Recurring

| Id | Every | What |
|---|---|---|
| weekly-reviews | 7 days | every new review on maps and platforms has an answer; aim for a day (Practice). Answer the problem, not with a template. |
| monthly-profiles | 30 days | profiles against the site: photos, products and prices, hours, phone. A rating shown on the site equals the rating on the map and links to the reviews. |

## Event: event-price-change

The page, its structured data and the feed show the same price first (seo-yandex). Then change profile items one by one.

## Yandex Business tiers (checked 2026-11-25)

Since August 2026, in beta, three tiers: Base (free), Extended and Advanced; pinning a review or photos, news and stories are in the paid tiers only (Sostav, 21 August 2026: https://www.sostav.ru/blogs/287854/102815 , secondary source). Plan profile news only if the tier has it.

## Do not

- Do not upload a full price or product file to a profile without a backup: in one case we observed in November 2026 the upload replaced every item of the profile. Edit items one by one (Practice).
- Do not add keywords or a city to the business name.
- Do not buy reviews, write them yourself or offer rewards for good ones.
- Do not mark up your own business with review stars: self-serving reviews of LocalBusiness and Organization are not eligible for review rich results. Official: https://developers.google.com/search/docs/appearance/structured-data/review-snippet
- Do not show a rating on the site that differs from the map, and do not copy ratings from other platforms into markup.
