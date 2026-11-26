# Privacy

seo-ops collects nothing. There is no telemetry, no account and no server of ours.

What the scripts send, and where:

| Script | Requests | To |
|---|---|---|
| `scripts/seo_check.py` | GET and HEAD, 2 per second, 60 per run by default; one TLS handshake to read the certificate | the host you name and its www or non-www twin; the sitemap its robots.txt names; with an IndexNow key, the key file `https://<host>/<key>.txt` |
| `scripts/indexnow.py` | GET of the sitemap; GET of the key file with `--check-key` or `--submit`; POST only with `--submit`, with the host, the key, the key file URL when `--key-location` is set, and the URLs of that host | the host you name; the IndexNow endpoint (default `https://api.indexnow.org/indexnow`), which passes the URLs to the other IndexNow search engines |
| `scripts/gsc_gaps.py` | GET of the sitemap and each page title, 1 per second, only with `--sitemap` | the sitemap host |
| `scripts/seo_calendar.py` | none | local files only |
| `scripts/seo_crawl.py` | GET and HEAD, 2 per second, at most 200 URLs and 600 seconds by default; robots.txt first; links to other hosts are counted, never fetched | the host you name; the sitemap files its robots.txt or sitemap index names |
| `scripts/seo_index.py` | GET of robots.txt and the sitemap (none with `--pages`); with your keys, API requests, at most 5 a second, carrying the published URLs of your site | the host you name; with `YANDEX_WEBMASTER_TOKEN`, `api.webmaster.yandex.net`; with the Google keys, `oauth2.googleapis.com` (token exchange), `www.googleapis.com` (site list) and `searchconsole.googleapis.com` (URL Inspection) |
| `scripts/wordstat.py` | POST of each phrase, at most 100 an hour by default; nothing with `--dry-run` | `searchapi.api.cloud.yandex.net`, only with your Yandex Cloud key; Yandex Cloud bills the requests to your account |
| `scripts/serp_cluster.py` | none | local files only |

Every request carries a User-Agent that names the tool and links to this repository, for example `seo-ops-check/<version> (+https://github.com/GoldenSample/seo-ops)`.

The IndexNow key is public by design of the protocol: anyone can read it at `https://<host>/<key>.txt`. The scripts take it from `--key` or from the `INDEXNOW_KEY` environment variable and send it only to the IndexNow endpoint.

Your Search Console or Webmaster exports stay on your machine: `gsc_gaps.py` reads them locally and sends none of their rows anywhere. `serp_cluster.py` reads its CSV of search results the same way.

The optional keys of `seo_index.py` (Yandex Webmaster, Search Console) and `wordstat.py` (Yandex Cloud) are yours. The scripts read them from the environment only, send each only to the official API hosts in the table, and never print them: the printed lines and the Markdown and JSON reports pass a filter that replaces token values with `***`. Wordstat answers are cached in `~/.cache/seo-ops/wordstat` by default, on your machine; the cache holds the phrases and the API answers, not the key. If you connect Arsenkin's MCP server (the seo-semantic-core skill names it), Claude sends the phrases and URLs you ask about to Arsenkin under your account and Arsenkin's terms; seo-ops does not connect it.

The GitHub Actions workflows run in your own repository under your account. Each run checks out `GoldenSample/seo-ops` from GitHub at the `tools_ref` input (default `v1`) to get the scripts, without credentials. Reports go to the job summary of your runs. With the `INDEXNOW_KEY` secret, the check step fetches the key file of your host, and the daily and deploy runs send changed URLs to the IndexNow endpoint; the caller's `indexnow` input turns off the sending (`check`) or both (`off`). The weekly workflow also crawls your site with `seo_crawl.py` (input `crawl_pages`, default 200 URLs, `0` turns it off). The monthly workflow opens one issue in your repository with the `GITHUB_TOKEN` that GitHub creates for that run; the token goes only to the GitHub API. With the index secrets you add, the monthly run sends the published URLs of your site with your keys to the Yandex Webmaster and Search Console APIs and puts the report into that issue; the secrets reach only that step. Nothing is sent to us.

When you use the skills inside Claude, what you share with the model is covered by your agreement with Anthropic, not by this file.
