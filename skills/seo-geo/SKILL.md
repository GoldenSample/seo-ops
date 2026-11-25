---
name: seo-geo
description: "GEO, generative engine optimization, for a small site: how to get cited in AI answers (Google AI Overviews and AI Mode, Yandex Alice AI, ChatGPT search, Claude, Perplexity), which AI crawlers to allow in robots.txt (search and user bots versus training bots, YandexAdditional), whether llms.txt matters, what gets cited, and how to measure AI visibility (Search Console Generative AI report, Yandex Alice AI visibility report, AI referrals, a fixed spot-check protocol). One-time: AI crawler policy, AI features included. Recurring: weekly AI visibility, biweekly AI answer spot check. Use for GEO, AEO, AI search, LLM visibility, AI crawlers, llms.txt, ChatGPT or Perplexity citations. RU triggers: GEO, нейроответы, ответы Алисы, попасть в ответ нейросети, AI Overviews, ИИ-боты в robots.txt, GPTBot, llms.txt, видимость в Алисе AI, цитирование в ChatGPT."
license: MIT
---

# seo-geo: AI answers without myths

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

## The one rule: rank first

AI answers in Google and Yandex are assembled from the ordinary search results.

- Google: ranked results and their snippets are the grounding for AI Overviews and AI Mode; there are no extra technical requirements and no special schema. Official: https://developers.google.com/search/docs/fundamentals/gen-ai-attribution-factuality , https://developers.google.com/search/docs/appearance/ai-features
- Yandex: "no fundamentally new requirements" for Alice AI answers; the same ranking aspects apply. Official: https://yandex.ru/support/webmaster/ru/epos
- Chance to be cited by Alice by Yandex position: 1st 50.6%, 2nd-3rd 48.5%, 4th-5th 42.2%, 6th-10th 34.8%, 11th-30th 19.6%, beyond 7.0%. Google AI answers: 61.9% for position 1, 5.6% beyond position 30. Measured: PromoPult, 23 November 2026, Moscow, September to November 2026, mostly commercial queries: https://blog.promopult.ru/seo/issledovanie-kak-ii-v-poiske-otvechayut-v-raznyh-biznes-nishah.html
- How often an AI answer appears depends on the sample: on commercial queries Alice answered 4.8% and Google 69.8% (PromoPult, same study); another study counted 15% for Alice in July 2026 (Ashmanov and Partners, AdIndex 6 October 2026). Yandex reports AI answers on 44% of all queries in Q3 2026 (company report, Sostav 29 October 2026).

For a store: commercial queries mostly go through ordinary results and product blocks; "how to choose" guides are what AI answers cite. seo-content covers those pages.

## One-time (new site)

1. `launch-search-console` (seo-google): the generative AI setting shows "included".
2. `launch-ai-crawlers`: decide and write down the policy. `seo_check.py` (check `ai-bots`) shows the result.

| Bot | Purpose | Block it and |
|---|---|---|
| OAI-SearchBot | ChatGPT search index | the site does not appear in ChatGPT search answers |
| ChatGPT-User | fetches a page when a user asks; OpenAI says robots.txt may not apply | user-triggered visits can still happen |
| GPTBot | OpenAI model training | no effect on ChatGPT search |
| Claude-SearchBot, Claude-User | Claude search index, user-triggered fetches | lower visibility in Claude answers |
| ClaudeBot | Anthropic model training | no effect on Claude search |
| Google-Extended | Gemini training and grounding outside Search | no effect on Google Search or AI Overviews |
| PerplexityBot, Perplexity-User | Perplexity index, user-triggered fetches | the site is not cited by Perplexity (vendor docs, not re-checked here) |
| YandexAdditional | content shown in Alice AI answers | content not shown in Alice answers; this bot ignores the `*` group, so it needs its own group; changes take 2 to 14 days |
| Applebot-Extended, CCBot | training only | a free choice |

Sources (checked 2026-11-25): https://developers.openai.com/api/docs/bots , https://support.claude.com/en/articles/8896518 , https://developers.google.com/search/docs/fundamentals/gen-ai-controls , https://yandex.ru/support/webmaster/ru/adding-site/indexing-prohibition

A store that wants citations keeps the search and user bots open. Blocking training bots is a business choice, not an SEO lever.

3. `launch-llms-txt`: optional. Google: creating llms.txt "neither harm nor help" visibility, and Search does not use it. Ahrefs: 97% of llms.txt files got no requests in May 2026 (137k domains). No major AI search has said it reads llms.txt for answers. If you keep one, generate it from the same data as the site. Official: https://developers.google.com/search/docs/fundamentals/ai-optimization-guide ; Measured: https://ahrefs.com/blog/llmstxt-study/

## Recurring

| Id | Every | What |
|---|---|---|
| weekly-ai-visibility | 7 days | Search Console Generative AI performance report (impressions only) and Yandex Webmaster "site visibility in Alice AI answers" (share of mentions, sample queries, competitors; updates weekly; does not affect ranking). Write both numbers to the decision log with the report date. |
| biweekly-ai-answers | 14 days | spot check by a fixed protocol (below) |
| weekly-analytics | 7 days | AI referrals in analytics: chatgpt.com, perplexity.ai, claude.ai, gemini.google.com and others (seo-measure) |

Yandex report: https://webmaster.yandex.ru/blog/efficiency-alice (Official). Google report: https://developers.google.com/search/docs/fundamentals/ai-optimization-guide (Official).

### Spot-check protocol

Ten fixed questions your buyers ask (five "how to choose", three comparisons, two product questions). Every two weeks, ask the same ten in: Yandex search (Alice answer), Google (AI Overview or AI Mode), ChatGPT search, Perplexity. Record per row: date, question, engine, is there an AI answer, is the site cited, which domains are cited. Do not change the questions; a new question set starts a new series.

## What gets cited (evidence is thin)

- Comparisons, tables, step lists and FAQ blocks are cited often in practitioner studies, but these are correlations (Practice).
- Self-promotional "best X" listicles: in a test of 8 US B2B queries, 14 of 68 top-10 results were vendor listicles and none was cited in an AI Overview (saaslinkbuilding.com, 31 October 2026, small sample). Prefer honest comparisons with your own photos and measurements (seo-content).
- Statistics pages: no study with a method was found either way.

## Do not

- Do not chunk text, add special markup or write for "LLM readability": Google says this is not needed.
- Do not try to manipulate generative answers: Google lists it as spam. Official: https://developers.google.com/search/docs/essentials/spam-policies
- One screenshot proves nothing: AI answers vary by user, region and day; use the protocol.
