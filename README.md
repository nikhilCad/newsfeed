# newsfeed

Fully local now — no GitHub Actions, no Render.com. You run `scripts/run_local.py`
on your own machine, it keeps `data/*.xml` up to date, and you manually commit
+ push `data/` whenever you want your RSS reader to see the update. Point your
reader's feed URLs at the raw GitHub file, e.g.:

```
https://raw.githubusercontent.com/<you>/<repo>/main/data/engblogs.xml
https://raw.githubusercontent.com/<you>/<repo>/main/data/reddittext.xml
https://raw.githubusercontent.com/<you>/<repo>/main/data/redditupdates.xml
```

## How it works

- `latest_feeds.opml` - source list of reddit feeds (kept for reference; edit `feeds.json` directly to add/remove feeds)
- `feeds.json` - flat ordered list of feeds (13 total) that `scripts/fetch_feed.py` walks through
- `scripts/fetch_feed.py` - fetches exactly one feed per call (Reddit rate-limits to ~1 req/min), picking which one via a round-robin counter in `data/fetch_state.json`. Merges the result into `data/reddittext.json` or `data/redditupdates.json`
- `scripts/rss_render.py` - shared RSS-building helpers: fetches+parses the Engineering Blogs aggregator page, and renders `data/*.json` into RSS 2.0 XML
- `scripts/run_local.py` - the daemon you actually run. On startup, fetches the Engineering Blogs page once (no rate limit there) and writes `data/engblogs.xml`. Then loops forever: fetch the next reddit feed round-robin, and on every successful fetch regenerate `data/reddittext.xml` and `data/redditupdates.xml` from the merged JSON. Waits a random 5-10 minutes between fetches (a dedicated home IP can go faster than the old 40-minute GitHub Actions cadence). Never touches git — that's on you.

## Run locally

```
python3 scripts/run_local.py       # the main loop -- leave this running
FEED_INDEX=0 python3 scripts/fetch_feed.py   # fetch a specific feed by index (0-12), for manual testing; doesn't touch fetch_state.json
```

Env vars: `SOURCE_URL` for `run_local.py` (default `https://engineeringblogs.xyz/`).

When you're happy with the current `data/*.xml`, commit and push:

```
git add data/
git commit -m "Refresh feed data"
git push
```
