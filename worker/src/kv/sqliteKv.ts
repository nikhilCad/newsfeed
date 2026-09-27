import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { KVStore } from "../core/types";

// WAL mode lets the local server and the admin server (two separate
// processes) read/write the same file concurrently without lock errors --
// the default rollback-journal mode takes an exclusive lock per write.
export function openDb(path: string): DatabaseSync {
  mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec(`PRAGMA journal_mode = WAL`);
  db.exec(`CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)`);
  return db;
}

export function readRaw(db: DatabaseSync, key: string): string | null {
  const row = db.prepare("SELECT value FROM kv WHERE key = ?").get(key) as { value: string } | undefined;
  return row ? row.value : null;
}

export function writeRaw(db: DatabaseSync, key: string, value: string): void {
  db.prepare(
    "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
  ).run(key, value);
}

export class SqliteKvStore implements KVStore {
  constructor(private db: DatabaseSync) {}

  get(key: string): Promise<string | null>;
  get(key: string, type: "json"): Promise<unknown>;
  async get(key: string, type?: "json"): Promise<unknown> {
    const raw = readRaw(this.db, key);
    if (raw === null) return null;
    return type === "json" ? JSON.parse(raw) : raw;
  }

  async put(key: string, value: string): Promise<void> {
    writeRaw(this.db, key, value);
  }
}
