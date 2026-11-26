---
name: seo-content
description: "Content for a small site or store that search engines and AI answers use: own product descriptions, instructions and FAQ inside product pages, buying guides, honest comparisons, what Google and Yandex say about AI-written text, scaled content and low-value pages, listicles ('best X' with yourself first) and statistics pages, demand notes, review at 7, 21 and 90 days, pruning, seasonal planning, links and mentions. One-time: content baseline. Recurring: monthly content, quarterly prune, seasonal plan and links review. Event: new page. Use for content plans, product descriptions, blog or guide pages, listicles, AI-generated content, thin content, link building. RU triggers: контент-план, описания товаров, карточки товаров, гайд как выбрать, сравнение товаров, листикл, лучшие X, страницы статистики, тексты нейросетью, малополезный контент, ЭПОС, ссылки и упоминания, сезонные статьи."
license: MIT
---

# seo-content: pages worth indexing

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

## What the engines say (checked 2026-11-25)

- Google: AI-generated content is allowed when it is useful; generating many pages mainly to rank is scaled content abuse. Check every fact by hand, including title, description, structured data and image alt text. Official: https://developers.google.com/search/docs/fundamentals/using-gen-ai-content , https://developers.google.com/search/docs/essentials/spam-policies
- Yandex: rewritten text is low-value, and so is generated text without editing in many cases; original product descriptions and instructions are named as useful. Official: https://yandex.ru/support/webmaster/ru/threat/useless-content
- Yandex ranks by expertise, usefulness, originality and content depth (ЭПОС) and task relevance; a product that is out of stock or does not ship to the region loses. Official: https://yandex.ru/support/webmaster/ru/epos
- Listicles: Google does not penalize the list format. Think with Google (14 October 2026) asked brands to replace template "Top 10" pieces with first-hand material; nothing about self-promotional lists (SEJ, 20 November 2026: https://www.searchenginejournal.com/google-told-cmos-to-stop-top-10-listicles/598310/). The closest spam policy is thin affiliation (spam policies above).
- Self-promotional "best X" lists in AI Overviews: 14 of 68 top-10 results on 8 US B2B queries were vendor listicles, none was cited (saaslinkbuilding.com, 31 October 2026, small sample: https://saaslinkbuilding.com/blog/self-promotional-listicles-ai-overviews-test/).
- Statistics pages: no study with a method was found for or against them.

## One-time (new site): launch-content-baseline

1. Product pages first. Own description, not the supplier text. Specifications only from the manufacturer's official pages; where data is missing, write "unknown", do not guess. Price, availability, delivery and returns on the page. Real photos where you have them.
2. Instructions and FAQ inside the product page (or one click away from it): setup steps, compatibility, common problems. A translated manual as an HTML page linked from the product answers "manual for <model>" searches (Practice: not measured yet).
3. One guide for the main buying question ("how to choose X"), chosen by measured demand (seo-query-gaps, seo-semantic-core). AI answers in both engines cite guides and comparisons more than product pages (seo-geo).
4. Trust pages and seller details (seo-launch, `launch-trust-pages`).

## Recurring

| Id | Every | What |
|---|---|---|
| monthly-content | 30 days | 1 to 3 new guides or comparisons, or updates of old ones, by measured demand. No single proven cadence exists (practitioners give 1 per quarter to 4 per month); a slow queue with a fact check beats volume. |
| quarterly-prune | 91 days | pages with no impressions in 90 days: merge into a stronger page (301) or remove (410); read the 90-day reviews of new pages |
| quarterly-seasonal | 91 days | plan seasonal guides 6 to 8 weeks before the season (Practice) |
| quarterly-links | 91 days | new referring domains, anchors, brand mentions without links, competitors. No bought links: Google lists link schemes as spam (spam policies above); Yandex has filtered bought links since 2015 (Practice, not re-checked). |

## Event: event-new-page

Before writing, a demand note in the decision log: the query cluster, its numbers and source with a date, the page type, the existing page it could be instead. After publishing:

```
python scripts/seo_calendar.py track https://example.com/new-guide/ --on 2026-12-01
```

This adds review tasks at 7, 21 and 90 days (indexed, impressions, clicks, goals). The rollback rule goes in the note before publishing, for example "no impressions by day 90: merge into the category page".

## Page checklist (each new page)

- One intent per page; the title says it in plain words.
- Every number, model name and specification checked against a primary source; the source is kept in the repo or the note.
- First-hand material: own photos, measurements, test notes, prices with a date.
- A comparison says that you sell the products and shows the losing points of your own products too.
- Internal links from the category and from related product pages.
- Structured data only for what is visible on the page (seo-launch).

## Lessons from our own audit (Practice, November 2026)

- An article factory that published 2 to 3 pieces a day for two months got indexing and impressions but almost no buyers, and its conversion was never measured. Set analytics and goals before scaling content (seo-measure).
- Pages built for demand were left without their day-7 review because no task was in a calendar. `track` exists for that.

## Do not

- Do not publish AI text without a human fact check of every number and name.
- Do not make one page per keyword variant or per city without unique content: scaled content abuse.
- Do not put yourself first in a "best X" list and call it a review; write an honest comparison instead.
- Do not copy ratings from other platforms into your markup (seo-launch, `self-ratings`).
