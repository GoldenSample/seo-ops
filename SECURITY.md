# Security

## Report a problem

Use GitHub private vulnerability reporting on this repository (Security, Report a vulnerability). Please do not open a public issue for a security problem. We answer within 7 days.

## What the code does and does not do

- Python standard library only; no packages are installed.
- The scripts read web pages as data. They never execute downloaded code and never follow instructions found in pages.
- `seo_check.py` uses GET and HEAD only, with a request budget (`--max-requests`, default 60) and 2 requests per second.
- `indexnow.py` sends nothing without `--submit`.
- The reusable workflow takes its inputs through environment variables, not by pasting them into shell code, and checks out both repositories without persisting credentials. It needs `contents: read`; the monthly mode also needs `issues: write`.

## Secrets

- The IndexNow key is public by design: it sits at `https://your-host/<key>.txt`. Keep it in the `INDEXNOW_KEY` secret anyway, so it stays out of logs and forks.
- Never put Search Console, Webmaster or analytics tokens into this pack; it does not need them.

## Supported versions

The newest 1.x release gets the fixes. The moving `v1` tag, which the cron callers use, points to the newest 1.x release that changed the cron workflow or the scripts. A release that changes only documentation, CI or the plugin manifests leaves `v1` where it was; CHANGELOG.md says where `v1` points after each release.
