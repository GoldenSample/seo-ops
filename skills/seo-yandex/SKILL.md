---
name: seo-yandex
description: "Yandex for a small site or store: Yandex Webmaster (rights, sitemap, region, Clean-param, diagnostics, reindexing, Alice AI visibility report), Yandex Metrica link, Yandex Products YML feed, IndexNow (one request reaches Yandex, Bing and others; scripts/indexnow.py with dry run, 10-minute resend window, 429 handling), the October-November 2026 Webmaster outage, the ranking aspects Yandex names (ЭПОС). One-time: rights, region, sitemap, feed, IndexNow key. Recurring: daily IndexNow of changed URLs, weekly diagnostics and Pages in search. Events: price or stock change, data outage. Use for Yandex SEO, Yandex Webmaster, IndexNow, Yandex Products, Alice AI answers. RU triggers: Яндекс Вебмастер, продвижение в Яндексе, регион сайта, Clean-param, переобход страниц, IndexNow, Яндекс Товары, YML-фид, ЭПОС, ответы Алисы, сбой Вебмастера."
license: MIT
---

# seo-yandex: Yandex Webmaster, Products and IndexNow

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

Yandex had 70.22% of search in Russia in October 2026, Google 28.36% (StatCounter, read 2026-11-25). For a Russian-language store Yandex comes first.

## What Yandex says it ranks (checked 2026-11-25)

The help page on ranking and Alice AI answers names expertise, usefulness, originality and content depth (ЭПОС), plus relevance to the task. For AI answers "no fundamentally new requirements" arise. A product that is out of stock or does not ship to the user's region loses. Yandex advises sending product data to Yandex Products, registering in Yandex Business and showing the address, company details and contacts. Official: https://yandex.ru/support/webmaster/ru/epos

## One-time (new site)

1. `launch-yandex-webmaster`: verify rights (HTML file, meta tag or DNS TXT record), add the sitemap, link Yandex Metrica. Official: https://yandex.ru/support/webmaster/ru/service/rights
2. Region: in Webmaster (site presentation, regional settings) or through Yandex Business. As a rule one region; several only for sites with branch offices. Moderation takes days to weeks. Write the address with the postal code and the phone with the city code as text on the site. Official: https://yandex.ru/support/webmaster/ru/site-geography/site-region.html
3. robots.txt: `Clean-param:` for tracking parameters. It is cross-section and can stand anywhere in the file. If the file has a `User-agent: Yandex` group, Yandex ignores the `*` group, so repeat every rule there. Official: https://yandex.ru/support/webmaster/ru/robot-workings/clean-param
4. `launch-product-feeds`: a YML feed in the Yandex Products account (Products, Data sources, Feeds); the review takes up to 5 working days. Check the account's current store requirements before you build the feed. Official: https://yandex.ru/support2/products/ru/connect/feed-load
5. `launch-indexnow`: generate a key (8 to 128 characters: letters, digits, `-`), serve it as plain text at `https://example.com/<key>.txt`, keep it in the `INDEXNOW_KEY` secret. Check: `python scripts/indexnow.py --site example.com --check-key`.
6. At launch, send the whole sitemap once: `python scripts/indexnow.py --site example.com --all --submit`.

## IndexNow (checked 2026-11-25)

- One submission reaches Bing, Yandex, Seznam, Naver, Amazon and Yep. Google does not take part. A submission does not guarantee indexing. Send only changed URLs; repeat one URL not more often than every 10 minutes; after 429 wait for Retry-After. Official: https://www.indexnow.org/faq
- Yandex: up to 10,000 URLs in one POST; 429 when one IP sends too much; one URL not more often than every 10 minutes. Official: https://yandex.ru/support/webmaster/ru/indexnow/reference
- After the October 2026 incident, YandexBot made 0 of 24 visits to pages sent by IndexNow within 14 days in one test of 48 pages; Google found 23 of 24 through the sitemap (vc.ru, 13 November 2026, small sample, low confidence by the authors). Treat IndexNow as a hint, keep the sitemap and internal links right.

`scripts/indexnow.py` keeps these rules. Every command reads the key from `INDEXNOW_KEY` or `--key`, a dry run too:

```
python scripts/indexnow.py --site example.com                       # dry run, lastmod in the last 26 hours
python scripts/indexnow.py --site example.com --submit --sent-log indexnow-sent.json
python scripts/indexnow.py --site example.com --state indexnow-state.json --submit   # diff, also removed URLs
python scripts/indexnow.py --site example.com --url https://example.com/new/ --submit
```

The daily workflow uses the 26-hour mode: it needs a sitemap with honest `lastmod`. Without lastmod use `--state` and keep the state file between runs.

## Reindexing in Webmaster

The daily reindex limit is shared by the domain and its subdomains and renews every day; the robot visits within three days, and the search data updates within two weeks. Official: https://yandex.ru/support/webmaster/ru/robot-workings/site-reindex. Put new product pages there when they matter.

## Recurring

| Id | Every | What |
|---|---|---|
| daily-indexnow | 1 day | cron: changed URLs to IndexNow |
| daily-console-alerts | 1 day | Webmaster messages: critical errors, security, sanctions |
| weekly-index-snapshot | 7 days | Diagnostics and Pages in search; compare with last week |
| weekly-ai-visibility | 7 days | the report on site visibility in Alice AI answers (seo-geo) |

## Events

- `event-price-change`: page, JSON-LD and feed show the same price and stock; the sitemap lastmod moves; IndexNow sends the URL; business profile items change one by one (seo-local).
- `event-data-outage`: Yandex Webmaster tools were limited from 11 October 2026; on 23 November 2026 query monitoring (data for the last two weeks only), the Alice AI visibility report, Pages in search, site structure and query statistics with export came back. Do not compare this window with normal periods; for traffic use Metrica, whose data was kept. Official: https://webmaster.yandex.ru/blog/webmaster-update ; Topvisor, 23 November 2026: https://journal.topvisor.com/ru/news/23-11-2026-yandex-webmaster-tools-restoration-update/

## Metrica attribution

Four old attribution models were removed on 20 May 2026; automatic, last click and two cross-device models remain. Compare periods only with one model. ppc.world, 3 April 2026: https://ppc.world/news/metrika-postepenno-prekratit-podderzhku-ustarevshih-versiy-modeley-atribucii/

## Do not

- Do not upload a full price or product file to a business profile without a backup: in one case we observed in November 2026 the upload replaced every item of the profile. Edit items one by one (Practice).
- Do not resend unchanged URLs to IndexNow every day; it does not help and may get you a 429.
