# newsfeed

Fully local now — no GitHub Actions, no Render.com. You run `scripts/run_local.py`
on your own machine, and it keeps `data/*.xml` up to date and committed + pushed
to `origin/main` itself. Point your reader's feed URLs at the raw GitHub file, e.g.:

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
- `scripts/run_local.py` - the daemon you actually run. On startup, runs `git fetch origin main && git reset --hard origin/main` to sync with the remote, then fetches the Engineering Blogs page once (no rate limit there) and writes `data/engblogs.xml`. Then loops once per feed in `feeds.json` (round-robin): fetch the next reddit feed, and on every successful fetch regenerate `data/reddittext.xml` and `data/redditupdates.xml` from the merged JSON, then `git commit -am <message> && git push origin main`. A failed fetch doesn't advance the round-robin state, so the next cycle automatically retries the same feed (up to 3 attempts per feed before giving up on the run). Waits a random 2-4 minutes between fetches. Exits once it has successfully fetched every feed once. Git commands are run with `os.system()` in the current working directory, so always run this from the repo root.
- `scripts/blogs_fetch.py` - fetches+parses the Engineering Blogs aggregator page and writes `data/engblogs.json` (a separate file from `run_local.py`'s own `data/engblogs.xml` snapshot). Kept as its own module so the `/blogs` server route can trigger a fresh fetch on its own schedule.
- `scripts/server.py` - a WSGI app (`application(environ, start_response)`) that builds RSS on the fly and serves it, instead of relying on the static `data/*.xml` files. Deploy it under any WSGI host (Alwaysdata's "Python (WSGI)" site type, gunicorn, uwsgi, ...) by pointing at `scripts.server:application`, or run it standalone with `python3 scripts/server.py` (uses `wsgiref`'s threading server):
  - `/reddittext` and `/redditupdates` render straight from `data/reddittext.json` / `data/redditupdates.json` (whatever `run_local.py`/`fetch_feed.py` last wrote there) — no network call.
  - `/blogs` calls `scripts/blogs_fetch.py` to re-fetch the aggregator page and regenerate `data/engblogs.json`, cached for `CACHE_SECONDS` (default 900s); pass `?refresh` to force an immediate re-fetch.

## Run locally

```
python3 scripts/run_local.py       # the main loop -- leave this running, keeps data/*.json fresh + pushed
python3 scripts/server.py          # HTTP server: /reddittext, /redditupdates, /blogs
FEED_INDEX=0 python3 scripts/fetch_feed.py   # fetch a specific feed by index (0-12), for manual testing; doesn't touch fetch_state.json
```

## Alwaysdata setup
Run this in a cron (https://help.alwaysdata.com/en/docs/web-hosting/tasks/)

```
python3 scripts/run_local.py --no-git
```

Serve `/reddittext`, `/redditupdates`, `/blogs` by adding a "Python (WSGI)" site (https://help.alwaysdata.com/en/docs/web-hosting/python/) pointed at:

```
scripts/server.py -> application
```

(working directory: `scripts/`, so `scripts.server:application` resolves)

Env vars: `SOURCE_URL` for `run_local.py`/`server.py` (default `https://engineeringblogs.xyz/`); `PORT` and `CACHE_SECONDS` for `server.py` (defaults `8000` and `900`).

`run_local.py` commits and pushes `data/` itself after each successful feed fetch, so there's nothing manual to do — just make sure the repo has a clean working tree and a configured git remote/credentials before starting it (it force-resets to `origin/main` on startup, discarding any local changes). `server.py` is independent of that push loop — it just reads whatever is currently on disk (and, for `/blogs`, fetches live), so run it alongside `run_local.py` to get live endpoints.
