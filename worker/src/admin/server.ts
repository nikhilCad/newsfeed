import http from "node:http";
import { openDb, ensureSchema, writeRaw } from "../kv/pgKv";

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) throw new Error("DATABASE_URL env var is required (postgres connection string)");
const PORT = parseInt(process.env.ADMIN_PORT || "8788", 10);
const HOST = process.env.ADMIN_HOST || "127.0.0.1";

const db = openDb(DATABASE_URL);

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function renderPage(): Promise<string> {
  const { rows } = await db.query<{ key: string; value: string }>("SELECT key, value FROM kv ORDER BY key");
  const rowsHtml = rows
    .map(
      (r) => `
      <form method="post" action="/save" class="row">
        <div class="key">${escapeHtml(r.key)}</div>
        <textarea name="value" rows="3">${escapeHtml(r.value)}</textarea>
        <input type="hidden" name="key" value="${escapeHtml(r.key)}" />
        <button type="submit">Save</button>
      </form>`,
    )
    .join("\n");

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>newsfeed admin</title>
<style>
  body { font-family: monospace; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
  .row { display: flex; gap: 0.5rem; align-items: flex-start; margin-bottom: 1rem; border-bottom: 1px solid #ccc; padding-bottom: 1rem; }
  .key { width: 220px; flex-shrink: 0; word-break: break-all; font-weight: bold; padding-top: 0.4rem; }
  textarea { flex: 1; font-family: monospace; }
</style>
</head>
<body>
<h1>newsfeed admin</h1>
<p>Rows prefixed <code>var:</code> are the config vars (SOURCE_URL, REDDIT_CYCLE_HOURS, ...);
everything else is app state (config:feeds, data:*, state:*).
Edits here write straight to the postgres <code>kv</code> table the local server/cron read from -- next request or tick picks them up, no restart needed.</p>
${rowsHtml}
<h2>Add / overwrite key</h2>
<form method="post" action="/save" class="row">
  <input type="text" name="key" placeholder="key" style="width:220px" />
  <textarea name="value" rows="3" placeholder="value"></textarea>
  <button type="submit">Save</button>
</form>
</body>
</html>`;
}

async function readBody(req: http.IncomingMessage): Promise<URLSearchParams> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return new URLSearchParams(Buffer.concat(chunks).toString("utf-8"));
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(await renderPage());
    return;
  }
  if (req.method === "POST" && req.url === "/save") {
    const body = await readBody(req);
    const key = body.get("key");
    const value = body.get("value") ?? "";
    if (key) await writeRaw(db, key, value);
    res.writeHead(302, { Location: "/" });
    res.end();
    return;
  }
  res.writeHead(404);
  res.end("Not found");
});

ensureSchema(db)
  .then(() => server.listen(PORT, HOST, () => console.log(`newsfeed admin listening on http://${HOST}:${PORT}`)))
  .catch((err) => {
    console.error("failed to initialize database:", err);
    process.exit(1);
  });
