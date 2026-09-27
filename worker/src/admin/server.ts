import http from "node:http";
import { openDb, writeRaw } from "../kv/sqliteKv";

const DB_PATH = process.env.NEWSFEED_DB_PATH || "./data/newsfeed.db";
const PORT = parseInt(process.env.ADMIN_PORT || "8788", 10);
const HOST = process.env.ADMIN_HOST || "127.0.0.1";

const db = openDb(DB_PATH);

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderPage(): string {
  const rows = db.prepare("SELECT key, value FROM kv ORDER BY key").all() as { key: string; value: string }[];
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
<p>Rows prefixed <code>var:</code> are the old wrangler.toml [vars] (SOURCE_URL, REDDIT_CYCLE_HOURS, ...);
everything else mirrors what used to live in Cloudflare KV (config:feeds, data:*, state:*).
Edits here write straight to the sqlite file the local server/cron read from -- next request or tick picks them up, no restart needed.</p>
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
    res.end(renderPage());
    return;
  }
  if (req.method === "POST" && req.url === "/save") {
    const body = await readBody(req);
    const key = body.get("key");
    const value = body.get("value") ?? "";
    if (key) writeRaw(db, key, value);
    res.writeHead(302, { Location: "/" });
    res.end();
    return;
  }
  res.writeHead(404);
  res.end("Not found");
});

server.listen(PORT, HOST, () => console.log(`newsfeed admin listening on http://${HOST}:${PORT}`));
