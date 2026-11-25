# Changelog

## 1.0.2 (2026-11-25)

- Plugin manifest: fields for the Claude plugin directory listing (icon, documentation, support and privacy policy URLs). The icon is the publisher mark of GoldenSample, a square PNG.
- README in English and Russian: Try it with three checked prompts, what the plugin reads, runs, sends and changes, where it works (Claude Code, chat, Cowork), troubleshooting, privacy and support links. The line about API tokens now names the IndexNow key and the `GITHUB_TOKEN` of the monthly run.
- `examples/`: a made-up Search Console export and page list for `gsc_gaps.py`.
- PRIVACY.md lists the checkout of this repository by the cron, the monthly issue and the IndexNow key file request. SECURITY.md says where `v1` points.
- Fixes from running 1.0.1 on live sites:
  - Cron: the `INDEXNOW_KEY` secret now reaches the site check, so cron runs check the key file; before, `indexnow-key` was always SKIP there. A run with the secret and a missing or wrong key file now fails on `indexnow-key`. New input `indexnow`: `submit` (default: check the key file and send changed URLs), `check` (key file only, when another tool sends) or `off`. The weekly template passes the secret too.
  - `seo_check.py` samples the biggest sitemap section first, so a large section listed after many small ones is checked as well.
  - `seo_check.py` gives the one-year cache advice only for a static file with a content hash in its name; a file without one gets an INFO line: put a content hash in the name first.
  - `seo_calendar.py skip <id> --reason "..."` marks a task that does not apply to this site. `due` lists skipped tasks apart, the monthly issue leaves them out, `validate` needs the reason, and `skip --undo` or `done` brings a task back.
  - `seo_calendar.py validate --template FILE` takes the file, as `init --template FILE` does. `validate --calendar FILE --template` still works; `--as-template` is the plain name for it.
- Scripts, the cron workflow, the templates and the seo-calendar skill changed, so `v1` moves to 1.0.2.

## 1.0.1 (2026-11-25)

- CI: Python 3.9 runs on ubuntu-24.04, because actions/python-versions has no 3.9 build for Ubuntu 26.04 (ubuntu-latest); a third job runs the tests with the runner's own python3, the interpreter `seo-cron.yml` uses. CI runs on pushes to main and on pull requests, not on tags.
- Skills, scripts and the cron workflows work as in 1.0.0; only the version strings changed. The `v1` tag stays on 1.0.0, so callers of `@v1` run the same cron code.

## 1.0.0 (2026-11-25)

First release.

- Ten skills: seo-ops (hub), seo-launch, seo-calendar, seo-google, seo-yandex, seo-geo, seo-content, seo-measure, seo-local, seo-query-gaps. Each splits its work into one-time (new site), recurring and event tasks; facts carry a source and the checked date 2026-11-25.
- Scripts, Python 3.9+ standard library only:
  - `seo_check.py`: external live-site check with 30 checks, Markdown and JSON reports, a self-test that plants a known defect for 28 of them;
  - `seo_calendar.py`: site calendar from a 58-task template (init, due, done, track, validate);
  - `indexnow.py`: changed, new or removed sitemap URLs to IndexNow, dry run by default, 10-minute resend window, 429 handling;
  - `gsc_gaps.py`: gap, striking-distance and weak-CTR queries from a Search Console or Yandex Webmaster export.
- GitHub Actions: reusable `seo-cron.yml` (daily, weekly, monthly, deploy) and four caller templates; CI on Python 3.9 and 3.12.
