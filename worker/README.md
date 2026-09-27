# newsfeed-worker

Node port of the Python scripts in `../scripts/`. Runs as a plain long-lived
process plus a periodic cron tick: the cron tick replaces `run_local.py`'s
loop, a `kv` table in PostgreSQL replaces `data/*.json` + `feeds.json` + git
as the state store, and the HTTP server replaces `server.py`.

See the repo-root `README.md` for setup/run instructions.

## Layout

- `src/core/feedsConfig.ts` - reads/writes `feeds.json`-equivalent config
  from the KV store (key `config:feeds`), the round-robin index
  (`state:fetch_index`), and the next-due timestamp for the reddit cycle
  (`state:fetch_next_due_at`). Seeds the store with the current `feeds.json`
  contents on first read.
- `src/core/reddit.ts` - fetches one Reddit Atom feed and merges it into
  `data:<category>` (regex-based Atom parsing, no XML DOM dependency).
- `src/core/blogs.ts` - fetches + parses the Engineering Blogs aggregator
  page. `getEngblogsData` is the lazy path used by `/blogs` (cached for
  `CACHE_SECONDS`, same as `server.py`'s `BlogsCache`); `refreshEngblogsIfDue`
  is the proactive path called from the cron tick, paced by
  `ENGBLOGS_REFRESH_HOURS` via its own `state:engblogs_next_due_at`.
- `src/core/rss.ts` - renders RSS 2.0 XML from the stored data, ported from
  `rss_render.py`.
- `src/core/app.ts` - `handleFetch` (one route per category key in
  `config:feeds`, plus `/blogs` and `/`) and `handleScheduled`, shared by
  the HTTP server and the cron tick.
- `src/entry-local.ts` - HTTP server + cron-tick entrypoint.
- `src/admin/server.ts` - standalone admin UI for editing the `kv` table.
- `src/kv/pgKv.ts` - the `KVStore` implementation backed by PostgreSQL.

## Fetch cadence

The cron tick is meant to run every 3 minutes (comfortably under Reddit's ~1
req/min limit), but most ticks are no-ops -- actual fetch pacing is
time-based, controlled by two config vars stored in the `kv` table
(`var:REDDIT_CYCLE_HOURS`, `var:ENGBLOGS_REFRESH_HOURS`, editable live via the
admin server):

- `REDDIT_CYCLE_HOURS` (default `6`) - how long a full round-robin over
  *all* feeds in `config:feeds` takes, spread evenly regardless of feed
  count (e.g. 13 feeds / 6h means each individual feed refreshes roughly
  every 28 min). A failed fetch doesn't advance the schedule, so it's
  retried on the very next tick instead of waiting a full interval.
- `ENGBLOGS_REFRESH_HOURS` (default `3`) - how often the engineering-blogs
  aggregator page is proactively re-fetched, independent of the reddit
  cycle and of `/blogs` request traffic.

## Editing feeds (add categories / URLs)

Edit the `config:feeds` row through the admin server (see repo-root
`README.md`). The shape is unchanged from the repo-root `feeds.json`:

```json
{
  "categories": [
    { "key": "reddittext", "title": "Reddit Text", "feeds": [
      { "name": "...", "url": "..." }
    ] }
  ]
}
```

A new category's `key` automatically becomes its own `data:<key>` row and
its own `/<key>` RSS route (routes are derived from `config:feeds` at
request time in `src/core/app.ts`) -- no code change or restart needed, it'll
start serving once the cron tick has fetched at least one of its feeds.
