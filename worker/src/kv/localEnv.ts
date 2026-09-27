import type { Pool } from "pg";
import type { Env } from "../core/types";
import { readRaw, writeRaw, PgKvStore } from "./pgKv";

// Default config values -- only used to seed the row the first time it's
// read, so the admin server has something to show and edit before anyone's
// touched it.
const VAR_DEFAULTS: Record<string, string> = {
  SOURCE_URL: "https://engineeringblogs.xyz/",
  REDDIT_CYCLE_HOURS: "6",
  ENGBLOGS_REFRESH_HOURS: "3",
  CACHE_SECONDS: "900",
};

async function readVar(pool: Pool, name: string): Promise<string> {
  const key = `var:${name}`;
  const existing = await readRaw(pool, key);
  if (existing !== null) return existing;
  const fallback = VAR_DEFAULTS[name];
  await writeRaw(pool, key, fallback);
  return fallback;
}

// Rebuilds Env from postgres on every call so an edit made through the admin
// server takes effect on the very next request or cron tick, with no
// restart needed.
export async function loadEnv(pool: Pool): Promise<Env> {
  return {
    NEWSFEED_KV: new PgKvStore(pool),
    SOURCE_URL: await readVar(pool, "SOURCE_URL"),
    REDDIT_CYCLE_HOURS: await readVar(pool, "REDDIT_CYCLE_HOURS"),
    ENGBLOGS_REFRESH_HOURS: await readVar(pool, "ENGBLOGS_REFRESH_HOURS"),
    CACHE_SECONDS: await readVar(pool, "CACHE_SECONDS"),
  };
}
