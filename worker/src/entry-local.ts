import http from "node:http";
import { openDb, ensureSchema } from "./kv/pgKv";
import { loadEnv } from "./kv/localEnv";
import { handleFetch, handleScheduled } from "./core/app";

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) throw new Error("DATABASE_URL env var is required (postgres connection string)");
const PORT = parseInt(process.env.PORT || "8787", 10);

const db = openDb(DATABASE_URL);

async function runCronTick(): Promise<void> {
  await ensureSchema(db);
  await handleScheduled(await loadEnv(db));
}

if (process.argv.includes("--cron")) {
  runCronTick()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error("cron tick failed:", err);
      process.exit(1);
    });
} else {
  ensureSchema(db)
    .then(() => {
      const server = http.createServer(async (req, res) => {
        try {
          const url = `http://${req.headers.host ?? `localhost:${PORT}`}${req.url}`;
          const headers: Record<string, string> = {};
          for (const [name, value] of Object.entries(req.headers)) {
            if (typeof value === "string") headers[name] = value;
          }
          const request = new Request(url, { method: req.method, headers });
          const response = await handleFetch(request, await loadEnv(db));
          res.writeHead(response.status, Object.fromEntries(response.headers));
          res.end(Buffer.from(await response.arrayBuffer()));
        } catch (err) {
          console.error("request failed:", err);
          res.writeHead(500, { "Content-Type": "text/plain" });
          res.end(`Internal error: ${(err as Error).message}`);
        }
      });
      server.listen(PORT, () => console.log(`newsfeed local server listening on :${PORT}`));
    })
    .catch((err) => {
      console.error("failed to initialize database:", err);
      process.exit(1);
    });
}
