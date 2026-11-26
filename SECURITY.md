# Security

## Report a problem

Use GitHub private vulnerability reporting on this repository (Security, Report a vulnerability). Please do not open a public issue for a security problem. We answer within 7 days.

## What the code does and does not do

- Python standard library only; no packages are installed.
- The scripts read web pages as data. They never execute downloaded code and never follow instructions found in pages.
- `seo_check.py` uses GET and HEAD only, with a request budget (`--max-requests`, default 60) and 2 requests per second.
- `indexnow.py` sends nothing without `--submit`.
- `seo_crawl.py` uses GET and HEAD only, on the host you name, with a URL budget (`--max-pages`, default 200), a time budget (`--max-seconds`, default 600) and 2 requests per second; it obeys robots.txt and slows down on 429 and 503.
- The scripts that use keys (`seo_index.py`, `wordstat.py`, `indexnow.py`, `seo_check.py`) read them only from the keys file named with `--keys`, never from the environment; `seo_keys.py init` creates that file with mode 600, and the scripts warn when it sits inside a git repository or other users can read it. An error about the file names the line, never the value.
- `seo_index.py` and `wordstat.py` send a token only to the official API hosts. `SEO_OPS_API_BASE`, which the tests use to reach a mock server, may point only at 127.0.0.1, localhost or ::1. The printed lines and the Markdown and JSON reports pass a filter that replaces token values with `***`; the Wordstat cache holds the phrases and the API answers, not the key.
- The reusable workflow takes its inputs through environment variables, not by pasting them into shell code, and checks out both repositories without persisting credentials. It needs `contents: read`; the monthly mode also needs `issues: write`.

## Secrets

- The IndexNow key is public by design: it sits at `https://your-host/<key>.txt`. Keep it in the `INDEXNOW_KEY` secret anyway, so it stays out of logs and forks.
- The optional keys of `seo_index.py` (Yandex Webmaster, Search Console) and `wordstat.py` (Yandex Cloud) are yours. Keep them in your keys file outside any repository (mode 600) or in CI secrets, never in a file of a repository. In Claude Code the plugin option keys_file holds the path, not the keys. In the cron, each secret reaches only its own step, through a keys file in the runner's temporary folder (mode 600) that the step removes; the index secrets reach only the index step of the monthly run.

## Supported versions

The newest 1.x release gets the fixes. The moving `v1` tag, which the cron callers use, points to the newest 1.x release that changed the cron workflow or the scripts. A release that changes only documentation, CI or the plugin manifests leaves `v1` where it was; CHANGELOG.md says where `v1` points after each release.
