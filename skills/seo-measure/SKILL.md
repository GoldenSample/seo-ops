---
name: seo-measure
description: "Measure SEO on a small site so that changes can be judged: analytics and goals before the first change, baseline and decision log, weekly index snapshot, analytics week with AI referrals, monthly CTR pass with control pages, monthly organic-to-orders reconciliation (one attribution model), review tasks at 7, 21 and 90 days for new pages, traffic drop runbook, data outages and core updates as excluded windows. One-time: analytics, baseline log, first read at day 28. Recurring: weekly snapshot and analytics, monthly CTR and orders. Events: traffic drop, data outage. Use for SEO reporting, did this change work, traffic dropped, measuring AI referrals, Search Console versus analytics numbers. RU triggers: замер SEO, журнал решений, базовая линия, упал трафик, просела органика, проверить эффект правки, контрольные страницы, CTR, Метрика цели, модель атрибуции, переходы из нейросетей, органика в заказы."
license: MIT
---

# seo-measure: prove it or do not claim it

Scripts: `${CLAUDE_SKILL_DIR}/../../scripts/` when installed as a plugin, `scripts/` in a clone of the repo.

Without a baseline and a log, nobody can say which change helped. Our own November 2026 audit of a small store found dozens of shipped changes and not one measured effect: there was no analytics counter, no goals, and calls and messages were not logged (Practice). Set measurement up before the first SEO change.

## One-time (new site)

1. `launch-analytics`: privacy policy first, then the counter (Yandex Metrica or GA4), goals for call, form and order, e-commerce events (view item, add to cart, purchase), bot filtering. Test: a test order and a test call appear as goals.
2. `launch-baseline-log`: copy `templates/decision-log.md` into the site repo. Fill the first block: Search Console, Yandex Webmaster and analytics numbers on the day before the first change.
3. `launch-first-read-d28`: four weeks after launch, one log line against the baseline. No conclusions from single-digit numbers.

## The decision log

One line per change: date, what changed (URLs or template), other changes at the same time (ads, prices, promotions, a core update), control pages that did not change, the review date, the result with numbers and their source. The log is the only place where a cause can be claimed. Format: `templates/decision-log.md`.

## Recurring

| Id | Every | What |
|---|---|---|
| weekly-index-snapshot | 7 days | Search Console Pages and Performance; Yandex Webmaster Diagnostics and Pages in search; compare with last week. With the owner's keys file, `python scripts/seo_index.py example.com --keys '${user_config.keys_file}'` lists the published pages missing from each index, with the reason (seo-launch, Index coverage) |
| weekly-analytics | 7 days | organic visits, goals and orders; AI referrals (chatgpt.com, perplexity.ai, claude.ai, gemini.google.com, copilot.microsoft.com and others) as their own source group |
| monthly-ctr-pass | 30 days | pages with impressions but few clicks over 28 to 90 days: rewrite title and description on half, keep comparable control pages unchanged, review in 4 weeks |
| monthly-orders | 30 days | organic orders and revenue from the e-commerce report, reconciled with real orders and calls by order number or ClientID |
| launch-indexing-d14, page reviews | once | `python scripts/seo_calendar.py track <url> --on <date>` gives day 7, 21 and 90 checks for a page |

## Rules for reading numbers

- Compare equal windows with the same weekdays; for seasonal goods compare year over year.
- Search Console clicks are not analytics visits: different counting, consent banners, blockers (Practice). Read trends within one tool.
- Compare Yandex Metrica periods with one attribution model. Four old models were removed on 20 May 2026; automatic, last click and two cross-device models remain (ppc.world, 3 April 2026: https://ppc.world/news/metrika-postepenno-prekratit-podderzhku-ustarevshih-versiy-modeley-atribucii/).
- Data arrives late. Sort each finding into "live defect", "already fixed" or "intended" before acting (Practice).
- Small sites: say "not enough data" instead of a percentage of a tiny number.

## Events

- `event-traffic-drop`:
  1. Check https://status.search.google.com/ and the Yandex Webmaster blog (https://webmaster.yandex.ru/blog/) for updates and outages.
  2. Read dashboard messages: manual actions, security, critical errors.
  3. Run `python scripts/seo_check.py example.com --pages 20` and `python scripts/seo_crawl.py example.com --json crawl-now.json`, with `--compare <an earlier crawl JSON>` when you kept one: new errors, lost pages and changed titles show in the crawl-diff line. With the owner's keys file, `python scripts/seo_index.py example.com --keys '${user_config.keys_file}'` lists the pages missing from the index, with the reason. Read the server logs for 5xx, 403 and 429 sent to robots.
  4. List the deploys and log lines of the last 14 days.
  5. Compare equal windows before and after; find which pages and queries fell.
  6. Roll back one change at a time and write each step in the log.
- `event-core-update`: wait at least one full week after the rollout ends, then compare the week after with the week before the start (Official: https://developers.google.com/search/updates/core-updates).
- `event-data-outage`: mark the window as excluded in the log with a source. Example: Yandex Webmaster tools were limited from 11 October 2026 and partly restored on 23 November 2026, with query monitoring keeping only two weeks (Official: https://webmaster.yandex.ru/blog/webmaster-update ; Topvisor, 23 November 2026: https://journal.topvisor.com/ru/news/23-11-2026-yandex-webmaster-tools-restoration-update/). Metrica data from that window was kept (AdIndex, 16 October 2026: https://adindex.ru/news/digital/2026/10/16/350059.phtml); use Metrica, not Webmaster, for traffic in it.

## Windows to exclude in late 2026 (checked 2026-11-25)

- Google November 2026 core update: from 10 November, about 14 days; the December 2026 core update was announced on 24 November without dates. Source: the dashboard history.
- Yandex Webmaster outage: from 11 October 2026 (above).

## Do not

- Do not claim an effect without a control and a log line written before the result.
- Do not report a percentage change of single-digit numbers.
- Do not mix attribution models or tools in one comparison.
