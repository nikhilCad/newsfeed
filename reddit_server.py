#!/usr/bin/env python3
"""reddit_server.py

Serves the Reddit feeds refreshed by .github/workflows/refresh-reddit-feeds.yml
as combined RSS 2.0 feeds, at /reddittext and /redditupdates.

Reddit now rate-limits to ~1 request/minute, so a GitHub Actions cron job
fetches one feed at a time and commits the merged result to
data/reddittext.json / data/redditupdates.json in this repo. This server
never talks to Reddit directly -- it pulls those two JSON files from GitHub's
raw content endpoint and re-serves them as RSS, so it can run continuously
(e.g. on Render) without ever being rate-limited itself, and without needing
a redeploy every time the cron job commits new data.

Usage:
    python3 reddit_server.py
    # then visit http://localhost:8000/reddittext and /redditupdates

Config via environment variables:
    GITHUB_REPO   - "owner/repo" to read data files from (default: nikhilCad/newsfeed)
    GITHUB_BRANCH - branch to read from (default: main)
    PORT          - port to listen on (default: 8000)
    CACHE_SECONDS - how long to cache each raw JSON file before re-fetching (default: 60)
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.request import urlopen, Request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GITHUB_REPO = os.environ.get("GITHUB_REPO", "nikhilCad/newsfeed")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
PORT = int(os.environ.get("PORT", "8000"))
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "60"))
USER_AGENT = "newsfeed-reddit-server/1.0"

RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/data"

ROUTES = {
    "/reddittext": "reddittext.json",
    "/redditupdates": "redditupdates.json",
}


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def parse_pubdate(value: str, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback


def build_rss(data: dict) -> str:
    now = datetime.now(timezone.utc)
    category_title = data.get("category", "Reddit")

    all_items = []
    for feed_name, feed in data.get("feeds", {}).items():
        for item in feed.get("items", []):
            all_items.append((feed_name, feed.get("source_url", ""), item))

    all_items.sort(key=lambda e: parse_pubdate(e[2].get("published", ""), now), reverse=True)

    items_xml = []
    for feed_name, source_url, item in all_items:
        title = f"{feed_name} - {item.get('title', '')}"
        link = item.get("link", "")
        pub_dt = parse_pubdate(item.get("published", ""), now)
        items_xml.append(
            "    <item>\n"
            f"      <title>{escape_xml(title)}</title>\n"
            f"      <link>{escape_xml(link)}</link>\n"
            f"      <guid isPermaLink=\"true\">{escape_xml(link)}</guid>\n"
            f"      <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            f"      <source url=\"{escape_xml(source_url)}\">{escape_xml(feed_name)}</source>\n"
            f"      <category>{escape_xml(feed_name)}</category>\n"
            "    </item>"
        )

    body = "\n".join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{escape_xml(category_title)}</title>
    <link>https://github.com/{GITHUB_REPO}</link>
    <description>Reddit feeds refreshed on a schedule via GitHub Actions.</description>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
    <generator>reddit_server.py</generator>
{body}
  </channel>
</rss>
"""


class RawCache:
    def __init__(self, filename: str, ttl_seconds: int):
        self.filename = filename
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._rss = None
        self._fetched_at = 0.0

    def fetch_json(self) -> dict:
        url = f"{RAW_BASE}/{self.filename}?ts={int(time.time())}"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_rss(self, force: bool = False) -> str:
        with self._lock:
            stale = (time.time() - self._fetched_at) > self.ttl_seconds
            if force or self._rss is None or stale:
                data = self.fetch_json()
                self._rss = build_rss(data)
                self._fetched_at = time.time()
            return self._rss


caches = {path: RawCache(filename, CACHE_SECONDS) for path, filename in ROUTES.items()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ROUTES:
            try:
                force = "refresh" in self.path
                rss = caches[path].get_rss(force=force)
            except Exception as exc:  # noqa: BLE001
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Failed to fetch/parse data file: {exc}".encode())
                return
            body = rss.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path in ("/", "/index.html"):
            links = "".join(f'<li><a href="{p}">{p}</a></li>' for p in ROUTES)
            info = f"""<!doctype html>
<html><body>
<h1>Reddit feeds</h1>
<p>Source data: <a href="https://github.com/{GITHUB_REPO}">{GITHUB_REPO}</a>@{GITHUB_BRANCH}</p>
<ul>{links}</ul>
</body></html>"""
            body = info.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Serving reddit feeds from {GITHUB_REPO}@{GITHUB_BRANCH}")
    for path in ROUTES:
        print(f"  -> http://localhost:{PORT}{path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
