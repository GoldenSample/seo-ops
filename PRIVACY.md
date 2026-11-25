# Privacy

seo-ops collects nothing. There is no telemetry, no account and no server of ours.

What the scripts send, and where:

| Script | Requests | To |
|---|---|---|
| `scripts/seo_check.py` | GET and HEAD, 2 per second, 60 per run by default; one TLS handshake to read the certificate | the host you name and its www or non-www twin; the sitemap its robots.txt names; with an IndexNow key, the key file `https://<host>/<key>.txt` |
| `scripts/indexnow.py` | GET of the sitemap; GET of the key file with `--check-key` or `--submit`; POST only with `--submit`, with the host, the key, the key file URL when `--key-location` is set, and the URLs of that host | the host you name; the IndexNow endpoint (default `https://api.indexnow.org/indexnow`), which passes the URLs to the other IndexNow search engines |
| `scripts/gsc_gaps.py` | GET of the sitemap and each page title, 1 per second, only with `--sitemap` | the sitemap host |
| `scripts/seo_calendar.py` | none | local files only |

Every request carries a User-Agent that names the tool and links to this repository, for example `seo-ops-check/<version> (+https://github.com/GoldenSample/seo-ops)`.

The IndexNow key is public by design of the protocol: anyone can read it at `https://<host>/<key>.txt`. The scripts take it from `--key` or from the `INDEXNOW_KEY` environment variable and send it only to the IndexNow endpoint.

Your Search Console or Webmaster exports stay on your machine: `gsc_gaps.py` reads them locally and sends none of their rows anywhere.

The GitHub Actions workflows run in your own repository under your account. Each run checks out `GoldenSample/seo-ops` from GitHub at the `tools_ref` input (default `v1`) to get the scripts, without credentials. Reports go to the job summary of your runs. With the `INDEXNOW_KEY` secret, the check step fetches the key file of your host, and the daily and deploy runs send changed URLs to the IndexNow endpoint; the caller's `indexnow` input turns off the sending (`check`) or both (`off`). The monthly workflow opens one issue in your repository with the `GITHUB_TOKEN` that GitHub creates for that run; the token goes only to the GitHub API. Nothing is sent to us.

When you use the skills inside Claude, what you share with the model is covered by your agreement with Anthropic, not by this file.
