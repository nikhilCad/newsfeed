import { Pool } from "pg";
import type { KVStore } from "../core/types";

export function openDb(connectionString: string): Pool {
  return new Pool({ connectionString });
}

export async function ensureSchema(pool: Pool): Promise<void> {
  await pool.query(`CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)`);
}

export async function readRaw(pool: Pool, key: string): Promise<string | null> {
  const { rows } = await pool.query<{ value: string }>("SELECT value FROM kv WHERE key = $1", [key]);
  return rows.length > 0 ? rows[0].value : null;
}

export async function writeRaw(pool: Pool, key: string, value: string): Promise<void> {
  await pool.query(
    "INSERT INTO kv (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
    [key, value],
  );
}

export class PgKvStore implements KVStore {
  constructor(private pool: Pool) {}

  get(key: string): Promise<string | null>;
  get(key: string, type: "json"): Promise<unknown>;
  async get(key: string, type?: "json"): Promise<unknown> {
    const raw = await readRaw(this.pool, key);
    if (raw === null) return null;
    return type === "json" ? JSON.parse(raw) : raw;
  }

  async put(key: string, value: string): Promise<void> {
    await writeRaw(this.pool, key, value);
  }
}
