# newsfeed

Same TypeScript source runs two ways:

- **Cloudflare Workers** (`worker/src/entry-workers.ts`) — deployed with `wrangler`, state in Cloudflare KV.
- **Local Node process** (`worker/src/entry-local.ts` + `worker/src/admin/server.ts`) — runs on any Linux/macOS box with Node 22+, state in a local SQLite file. No Cloudflare account needed for this path.

Business logic lives in `worker/src/core/` and is identical on both targets. The only thing that differs is what backs the `NEWSFEED_KV` key-value store: Cloudflare KV on Workers, a `kv` table in SQLite locally (`worker/src/kv/sqliteKv.ts`).

## Cloudflare Workers

```
cd worker
npm install
npm run dev       # wrangler dev
npm run deploy    # wrangler deploy
npm run tail      # wrangler tail
```

Config lives in `worker/wrangler.toml` ([vars], the `NEWSFEED_KV` binding, the cron trigger).

## Local (Linux VM or any machine with Node 22+)

Requires Node >= 22.5 (uses the built-in `node:sqlite` module).

```
cd worker
npm install
npm run build          # bundles entry-local.ts and admin/server.ts into worker/dist/
npm run start:local    # HTTP server: /reddittext, /redditupdates, /blogs -- listens on :8787 (PORT env var)
```

Run a cron tick (fetches exactly one due feed / refreshes engblogs if due, then exits):

```
npm run start:local:cron
```

Add this to `crontab -e` to replicate the Workers cron trigger (`*/3 * * * *`):

```
*/3 * * * * cd /path/to/newsfeed/worker && npm run start:local:cron >> /var/log/newsfeed-cron.log 2>&1
```

The local server and the cron process are independent short-lived Node processes that share one SQLite file (`worker/data/newsfeed.db` by default, override with `NEWSFEED_DB_PATH`). WAL mode is enabled so they can run concurrently without lock errors.

### Admin server

A small standalone HTTP server for viewing/editing every row of the local SQLite store — the local equivalent of editing Cloudflare KV/`[vars]` from the dashboard: `config:feeds`, `data:*`, `state:*`, and the `var:*` rows that mirror wrangler.toml's `[vars]` (`SOURCE_URL`, `REDDIT_CYCLE_HOURS`, `ENGBLOGS_REFRESH_HOURS`, `CACHE_SECONDS`).

```
npm run start:admin    # listens on 127.0.0.1:8788 by default (ADMIN_HOST / ADMIN_PORT env vars)
```

Edits take effect on the next request or cron tick — no restart needed. It binds to `127.0.0.1` by default and has no auth, so don't expose it beyond localhost/an SSH tunnel without adding one.

### Env vars (local)

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `8787` | local HTTP server port |
| `NEWSFEED_DB_PATH` | `./data/newsfeed.db` | SQLite file path, shared by the server, cron process, and admin server |
| `ADMIN_HOST` | `127.0.0.1` | admin server bind address |
| `ADMIN_PORT` | `8788` | admin server port |

### Type-checking

```
npm run typecheck        # Workers entrypoint + core, against @cloudflare/workers-types
npm run typecheck:local   # local entrypoint + admin + kv + core, against @types/node
```

These are two separate `tsconfig` files (`tsconfig.json`, `tsconfig.local.json`) because the Workers and Node ambient global types conflict if loaded together.
