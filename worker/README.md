# newsfeed-worker

Cloudflare Workers + KV port of the Python scripts in `../scripts/`. Runs
entirely on the free tier: a Cron Trigger replaces `run_local.py`'s loop, KV
replaces `data/*.json` + `feeds.json` + git as the state store, and the
`fetch` handler replaces `server.py`.

## Layout

- `src/feedsConfig.ts` - reads/writes `feeds.json`-equivalent config from KV
  (key `config:feeds`), the round-robin index (`state:fetch_index`), and the
  next-due timestamp for the reddit cycle (`state:fetch_next_due_at`). Seeds
  KV with the current `feeds.json` contents on first read.
- `src/reddit.ts` - fetches one Reddit Atom feed and merges it into
  `data:<category>` in KV (regex-based Atom parsing -- Workers has no XML
  DOM parser, unlike the Python version's `xml.etree`).
- `src/blogs.ts` - fetches + parses the Engineering Blogs aggregator page.
  `getEngblogsData` is the lazy path used by `/blogs` (KV-cached for
  `CACHE_SECONDS`, same as `server.py`'s `BlogsCache`); `refreshEngblogsIfDue`
  is the proactive path called from the cron tick, paced by
  `ENGBLOGS_REFRESH_HOURS` via its own `state:engblogs_next_due_at`.
- `src/rss.ts` - renders RSS 2.0 XML from the KV data, ported from
  `rss_render.py`.
- `src/index.ts` - `fetch` handler (one route per category key in
  `config:feeds`, plus `/blogs` and `/`) and `scheduled` handler.

## Fetch cadence

The cron trigger fires every 3 minutes (comfortably under Reddit's ~1
req/min limit), but most ticks are no-ops -- actual fetch pacing is
time-based, controlled by two `wrangler.toml` vars:

- `REDDIT_CYCLE_HOURS` (default `6`) - how long a full round-robin over
  *all* feeds in `config:feeds` takes, spread evenly regardless of feed
  count (e.g. 13 feeds / 6h means each individual feed refreshes roughly
  every 28 min). A failed fetch doesn't advance the schedule, so it's
  retried on the very next tick instead of waiting a full interval.
- `ENGBLOGS_REFRESH_HOURS` (default `3`) - how often the engineering-blogs
  aggregator page is proactively re-fetched, independent of the reddit
  cycle and of `/blogs` request traffic.

Changing either requires editing `wrangler.toml` and redeploying (they're
Worker vars, not KV) -- `config:feeds` is the only thing meant to be edited
live without a redeploy.

## One-time setup

```
cd worker
npm install
npx wrangler login

# Create the KV namespace and paste its id into wrangler.toml
npx wrangler kv namespace create NEWSFEED_KV
```

Update `wrangler.toml`'s `id = "REPLACE_WITH_KV_NAMESPACE_ID"` with the id
printed above.

## Migrating existing data (optional)

To carry over your current feeds list and already-fetched items instead of
starting from the seeded defaults / an empty cache:

```
cd ..   # repo root
npx wrangler kv key put --binding=NEWSFEED_KV "config:feeds" --path=feeds.json --config=worker/wrangler.toml
npx wrangler kv key put --binding=NEWSFEED_KV "data:reddittext" --path=data/reddittext.json --config=worker/wrangler.toml
npx wrangler kv key put --binding=NEWSFEED_KV "data:redditupdates" --path=data/redditupdates.json --config=worker/wrangler.toml
npx wrangler kv key put --binding=NEWSFEED_KV "data:engblogs" --path=data/engblogs.json --config=worker/wrangler.toml
```

## Deploy

```
cd worker
npx wrangler deploy
```

This registers the cron trigger (`*/3 * * * *`) and the routes on your
`workers.dev` subdomain. Add a custom domain/route in the Cloudflare
dashboard if you want a nicer URL for your feed reader.

## Editing feeds (add categories / URLs)

There's no admin UI -- edit the KV value directly, either in the Cloudflare
dashboard (Workers & Pages -> KV -> your namespace -> `config:feeds` ->
edit value) or from the CLI:

```
npx wrangler kv key get --binding=NEWSFEED_KV "config:feeds" --config=worker/wrangler.toml > feeds.json
# edit feeds.json: add a category or a feed entry, same shape as before
npx wrangler kv key put --binding=NEWSFEED_KV "config:feeds" --path=feeds.json --config=worker/wrangler.toml
```

The shape is unchanged from the repo-root `feeds.json`:

```json
{
  "categories": [
    { "key": "reddittext", "title": "Reddit Text", "feeds": [
      { "name": "...", "url": "..." }
    ] }
  ]
}
```

A new category's `key` automatically becomes its own `data:<key>` KV entry
and its own `/<key>` RSS route (routes are derived from `config:feeds` at
request time in `src/index.ts`) -- no code change or redeploy needed, it'll
start serving once the cron trigger has fetched at least one of its feeds.

## Local dev

```
npx wrangler dev
```

Runs against local KV storage (seeded with the `DEFAULT_FEEDS` fallback).
Trigger the cron handler manually with `npx wrangler dev --test-scheduled`
and hit `http://localhost:8787/__scheduled`.

## Free-tier limits to keep in mind

- KV: 100k reads/day, 1k writes/day, 1GB storage. Cron ticks every 3 min
  (480/day) but only *writes* when a fetch is actually due: at the default
  cadence that's ~3 writes/feed-fetch (data + index + due-time) x (24h /
  REDDIT_CYCLE_HOURS x feed count) for reddit, plus ~2 writes x (24h /
  ENGBLOGS_REFRESH_HOURS) for engblogs -- with the defaults (6h, 3h, 13
  feeds) that's roughly 150-200 writes/day, well under the limit even if
  you add more feeds or categories.
- Workers: 100k requests/day, 10ms CPU/invocation on the free plan. Cron
  invocations don't count against the request quota.
- Cron Triggers: up to 5 per Worker on the free plan; this project uses 1.
