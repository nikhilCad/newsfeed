# newsfeed

Runs as a plain Node process — no Cloudflare account needed.

- **Local Node process** (`worker/src/entry-local.ts` + `worker/src/admin/server.ts`) — runs on any Linux/macOS box with Node 22+, state in PostgreSQL.

Business logic lives in `worker/src/core/` and reads/writes state through the `NEWSFEED_KV` key-value store, backed by a `kv` table in PostgreSQL (`worker/src/kv/pgKv.ts`).

## Setup (Linux VM, or any machine with Node 22+ and a PostgreSQL database)

A PostgreSQL database is required (e.g. an [alwaysdata](https://www.alwaysdata.com/) PostgreSQL add-on, or any Postgres instance) — the app creates its own `kv` table on first run.

```
cd worker
npm install
npm run build          # bundles entry-local.ts and admin/server.ts into worker/dist/
export DATABASE_URL="postgres://user:password@host:port/dbname"
npm run start:local    # HTTP server: /<category>, /blogs -- listens on :8787 (PORT env var)
```

Run a cron tick (fetches exactly one due feed / refreshes engblogs if due, then exits):

```
npm run start:local:cron
```

Add this to `crontab -e` to run it every 3 minutes (Reddit rate-limits to ~1 req/min, but most ticks are no-ops -- actual fetch pacing is controlled by `REDDIT_CYCLE_HOURS`/`ENGBLOGS_REFRESH_HOURS`):

```
*/3 * * * * cd /path/to/newsfeed/worker && DATABASE_URL=... npm run start:local:cron >> /var/log/newsfeed-cron.log 2>&1
```

The local server and the cron process are independent short-lived Node processes that share the same PostgreSQL database, so they can run concurrently without lock errors.

### Admin server

A small standalone HTTP server for viewing/editing every row of the `kv` table: `config:feeds`, `data:*`, `state:*`, and the `var:*` rows (`SOURCE_URL`, `REDDIT_CYCLE_HOURS`, `ENGBLOGS_REFRESH_HOURS`, `CACHE_SECONDS`).

```
export DATABASE_URL="postgres://user:password@host:port/dbname"
npm run start:admin    # listens on 127.0.0.1:8788 by default (ADMIN_HOST / ADMIN_PORT env vars)
```

Edits take effect on the next request or cron tick — no restart needed. It binds to `127.0.0.1` by default and has no auth, so don't expose it beyond localhost/an SSH tunnel without adding one.

### Env vars

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string, shared by the server, cron process, and admin server |
| `PORT` | `8787` | local HTTP server port |
| `ADMIN_HOST` | `127.0.0.1` | admin server bind address |
| `ADMIN_PORT` | `8788` | admin server port |

### Type-checking

```
npm run typecheck
```
