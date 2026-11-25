# Changelog

## 1.0.0 (2026-11-25)

First release.

- Ten skills: seo-ops (hub), seo-launch, seo-calendar, seo-google, seo-yandex, seo-geo, seo-content, seo-measure, seo-local, seo-query-gaps. Each splits its work into one-time (new site), recurring and event tasks; facts carry a source and the checked date 2026-11-25.
- Scripts, Python 3.9+ standard library only:
  - `seo_check.py`: external live-site check with 30 checks, Markdown and JSON reports, a self-test that plants a known defect for 28 of them;
  - `seo_calendar.py`: site calendar from a 58-task template (init, due, done, track, validate);
  - `indexnow.py`: changed, new or removed sitemap URLs to IndexNow, dry run by default, 10-minute resend window, 429 handling;
  - `gsc_gaps.py`: gap, striking-distance and weak-CTR queries from a Search Console or Yandex Webmaster export.
- GitHub Actions: reusable `seo-cron.yml` (daily, weekly, monthly, deploy) and four caller templates; CI on Python 3.9 and 3.12.
