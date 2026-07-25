# newsfeed

## Endpoints (blogs.py)

- `/rss.xml` - Eng blogs feed
- `/reddittext` - combined RSS feed for the "Reddit Text" category
- `/redditupdates` - combined RSS feed for the "Updates" category
- `/` - index page with links to the above
- append `?refresh` to any feed route to force a re-fetch of the underlying source/JSON instead of using the cached copy

## How it works

- `latest_feeds.opml` - source list of reddit feeds (kept for reference; edit `feeds.json` directly to add/remove feeds)
- `feeds.json` - flat ordered list of feeds (13 total) that `scripts/fetch_feed.py` walks through
- `scripts/fetch_feed.py` - fetches exactly one feed per run (reddit rate-limits to ~1 req/min), picking which one via a round-robin counter in `data/fetch_state.json` (not wall-clock time - GitHub's schedule trigger is best-effort and runs get delayed/dropped, so time-derived slots caused most runs to silently no-op). Merges the result into `data/reddittext.json` or `data/redditupdates.json`
- `.github/workflows/refresh-reddit-feeds.yml` - cron, fires every 40 minutes all day (36 runs/day, ~2.7x through all 13 feeds), commits `data/` changes to `main`
- `blogs.py` - single server for all three endpoints. The reddit routes read `data/*.json` from `raw.githubusercontent.com` (60s cache), not from the local checkout - so it doesn't need a redeploy every time the cron job commits.

## Run locally

```
FEED_INDEX=0 python3 scripts/fetch_feed.py # fetch a specific feed by index (0-12), for testing
python3 blogs.py                          # serve on :8000 (set PORT to change)
```

Env vars for `blogs.py`: `SOURCE_URL` (default `https://engineeringblogs.xyz/`), `PORT` (default `8000`), `CACHE_SECONDS` (default `900`, blogs feed), `GITHUB_REPO` (default `nikhilCad/newsfeed`), `GITHUB_BRANCH` (default `main`), `REDDIT_CACHE_SECONDS` (default `60`).

## Deploy notes

- Render: start command `python3 blogs.py`. Turn off auto-deploy on push (or scope it to ignore `data/**`) - the reddit routes read data live from GitHub raw, so a `data/` commit doesn't need a rebuild.
