# Privacy

seo-ops collects nothing. There is no telemetry, no account and no server of ours.

What the scripts send, and where:

| Script | Requests | To |
|---|---|---|
| `scripts/seo_check.py` | GET and HEAD, 2 per second, 60 per run by default | the host you name, and the URLs listed in its sitemap |
| `scripts/indexnow.py` | GET of the sitemap and the key file; POST only with `--submit` | the host you name; the IndexNow endpoint (default `https://api.indexnow.org/indexnow`) |
| `scripts/gsc_gaps.py` | GET of the sitemap and each page title, 1 per second, only with `--sitemap` | the sitemap host |
| `scripts/seo_calendar.py` | none | local files only |

Every request carries a User-Agent that names the tool and links to this repository, for example `seo-ops-check/<version> (+https://github.com/GoldenSample/seo-ops)`.

Your Search Console or Webmaster exports stay on your machine: `gsc_gaps.py` reads them locally and sends none of their rows anywhere.

The GitHub Actions workflows run in your own repository under your account. Reports go to the job summary of your runs, and the monthly workflow opens an issue in your repository. Nothing is sent to us.

When you use the skills inside Claude Code, what you share with the model is covered by your agreement with Anthropic, not by this file.
