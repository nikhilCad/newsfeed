# newsfeed

## Endpoints (reddit_server.py)

- `/reddittext` - combined RSS feed for the "Reddit Text" category
- `/redditupdates` - combined RSS feed for the "Updates" category
- `/rss.xml` - Eng blogs feed
- `/` - index page with links to the above
- append `?refresh` to either feed route to force a re-fetch of the underlying JSON instead of using the cached copy

## How it works

- `latest_feeds.opml` - source list of reddit feeds, edit this to add/remove feeds
- `scripts/opml_to_json.py` - converts the OPML into `feeds.json` (flat ordered list, 13 feeds)
- `scripts/fetch_feed.py` - fetches exactly one feed per run (reddit rate-limits to ~1 req/min), picks which one from the current IST time, merges result into `data/reddittext.json` or `data/redditupdates.json`
- `.github/workflows/refresh-reddit-feeds.yml` - cron, fires every 5 min during 04:00-05:00 and 16:00-17:00 IST (13 runs per window = all feeds), commits `data/` changes to `main`
- `reddit_server.py` - serves the two RSS endpoints above by reading `data/*.json` from `raw.githubusercontent.com` (60s cache), not from the local checkout - so it doesn't need a redeploy every time the cron job commits

## Run locally

```
python3 scripts/opml_to_json.py          # regenerate feeds.json after editing the OPML
FEED_INDEX=0 python3 scripts/fetch_feed.py # fetch a specific feed by index (0-12), for testing
python3 reddit_server.py                  # serve on :8000 (set PORT to change)
```

Env vars for `reddit_server.py`: `GITHUB_REPO` (default `nikhilCad/newsfeed`), `GITHUB_BRANCH` (default `main`), `PORT` (default `8000`), `CACHE_SECONDS` (default `60`).

## Deploy notes

- Render: start command `python3 reddit_server.py`. Turn off auto-deploy on push (or scope it to ignore `data/**`) - the server reads data live from GitHub raw, it doesn't need a rebuild when the cron job pushes.
- `blogs.py` is a separate, unrelated RSS bridge (engineeringblogs.xyz -> `/rss.xml`).
