import type { DatabaseSync } from "node:sqlite";
import type { Env } from "../core/types";
import { readRaw, writeRaw, SqliteKvStore } from "./sqliteKv";

// Mirrors wrangler.toml's [vars] defaults -- only used to seed the sqlite
// row the first time it's read, so the admin server has something to show
// and edit before anyone's touched it.
const VAR_DEFAULTS: Record<string, string> = {
  SOURCE_URL: "https://engineeringblogs.xyz/",
  REDDIT_CYCLE_HOURS: "6",
  ENGBLOGS_REFRESH_HOURS: "3",
  CACHE_SECONDS: "900",
};

function readVar(db: DatabaseSync, name: string): string {
  const key = `var:${name}`;
  const existing = readRaw(db, key);
  if (existing !== null) return existing;
  const fallback = VAR_DEFAULTS[name];
  writeRaw(db, key, fallback);
  return fallback;
}

// Rebuilds Env from sqlite on every call (cheap, synchronous) so an edit
// made through the admin server takes effect on the very next request or
// cron tick, with no restart needed -- same as editing CF vars/KV live.
export function loadEnv(db: DatabaseSync): Env {
  return {
    NEWSFEED_KV: new SqliteKvStore(db),
    SOURCE_URL: readVar(db, "SOURCE_URL"),
    REDDIT_CYCLE_HOURS: readVar(db, "REDDIT_CYCLE_HOURS"),
    ENGBLOGS_REFRESH_HOURS: readVar(db, "ENGBLOGS_REFRESH_HOURS"),
    CACHE_SECONDS: readVar(db, "CACHE_SECONDS"),
  };
}
