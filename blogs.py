#!/usr/bin/env python3
"""
engblogs_rss_server.py

Fetches the "Engineering Blogs" aggregator page (the peterc/engblogs style
page: date-grouped <div class="entry"> items, each with a source link and a
title link) and re-serves it as a proper RSS 2.0 feed.

Usage:
    python3 engblogs_rss_server.py
    # then visit http://localhost:8000/rss.xml

Also serves /reddittext and /redditupdates, combined RSS feeds built from
data/reddittext.json and data/redditupdates.json (refreshed by
.github/workflows/refresh-reddit-feeds.yml and read live from GitHub's raw
content endpoint, so this server never talks to Reddit directly).

Config via environment variables:
    SOURCE_URL      - page to fetch (default: https://engineeringblogs.xyz/)
    PORT            - port to listen on (default: 8000)
    CACHE_SECONDS   - how long to cache the parsed blogs feed before re-fetching (default: 900)
    GITHUB_REPO     - "owner/repo" to read reddit data files from (default: nikhilCad/newsfeed)
    GITHUB_BRANCH   - branch to read reddit data files from (default: main)
    REDDIT_CACHE_SECONDS - how long to cache each reddit JSON file before re-fetching (default: 60)

Only stdlib is used, no third-party dependencies required.
"""

import json
import os
import re
import html
import time
import unicodedata
import threading
from email.utils import format_datetime
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.parse import urljoin
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOURCE_URL = os.environ.get("SOURCE_URL", "https://engineeringblogs.xyz/")
PORT = int(os.environ.get("PORT", "8000"))
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "900"))
USER_AGENT = "engblogs-rss-bridge/1.0 (+https://github.com/peterc/engblogs)"

GITHUB_REPO = os.environ.get("GITHUB_REPO", "nikhilCad/newsfeed")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
REDDIT_CACHE_SECONDS = int(os.environ.get("REDDIT_CACHE_SECONDS", "60"))
REDDIT_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/data"
REDDIT_ROUTES = {
    "/reddittext": "reddittext.json",
    "/redditupdates": "redditupdates.json",
}

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Matches each dated section: <h2>Date text</h2> ... up to the next <h2> or end
SECTION_RE = re.compile(
    r"<h2>(?P<date>[^<]+)</h2>\s*<div class=\"entries\">(?P<body>.*?)</div>\s*(?=<h2>|<footer)",
    re.DOTALL,
)

# Matches a single entry within a section
ENTRY_RE = re.compile(
    r'<div class="entry">\s*'
    r'<span class="source"><a href="(?P<source_url>[^"]*)">(?P<source_name>.*?)</a></span>\s*'
    r'<span class="title"><a href="(?P<link>[^"]*)">(?P<title>.*?)</a></span>\s*'
    r"</div>",
    re.DOTALL,
)

# Strip invisible / zero-width / formatting unicode characters that can be
# used to hide payloads inside otherwise-innocuous-looking text (some feeds
# in the wild have been observed stuffing zero-width characters into titles).
# We sanitize defensively rather than pass them through into the RSS output.
_INVISIBLE_CATEGORIES = {"Cf", "Cc", "Co", "Cs"}


def strip_invisible_chars(text: str) -> str:
    return "".join(
        ch for ch in text if unicodedata.category(ch) not in _INVISIBLE_CATEGORIES
    )


def clean_text(raw: str) -> str:
    text = html.unescape(raw)
    text = strip_invisible_chars(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date_heading(text: str, fallback: datetime) -> datetime:
    """Parse headings like 'Friday, July 2, 2027' into a datetime (UTC, midnight)."""
    text = clean_text(text)
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return fallback


def parse_page(html_text: str, base_url: str):
    """Return a list of item dicts: title, link, source_name, source_url, pub_date."""
    items = []
    now = datetime.now(timezone.utc)

    for section in SECTION_RE.finditer(html_text):
        section_date = parse_date_heading(section.group("date"), now)
        body = section.group("body")

        for i, entry in enumerate(ENTRY_RE.finditer(body)):
            title = clean_text(entry.group("title"))
            link = urljoin(base_url, entry.group("link").strip())
            source_name = clean_text(entry.group("source_name"))
            source_url = urljoin(base_url, entry.group("source_url").strip())

            if not title or not link:
                continue

            # Entries within a day aren't individually timestamped on the
            # source page, so we fan them out across the day (newest-first
            # ordering preserved) purely so RSS readers get distinct,
            # monotonically-ordered pubDates instead of a single duplicate
            # timestamp for dozens of items.
            pub_dt = section_date.replace(
                hour=23, minute=59, second=max(0, 59 - i) if i < 60 else 0
            )

            items.append(
                {
                    "title": title,
                    "link": link,
                    "source_name": source_name or "Unknown source",
                    "source_url": source_url,
                    "pub_date": pub_dt,
                }
            )

    return items


# ---------------------------------------------------------------------------
# RSS generation
# ---------------------------------------------------------------------------

def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_rss(items, source_url: str) -> str:
    now_str = format_datetime(datetime.now(timezone.utc))

    entries_xml = []
    for item in items:
        guid = escape_xml(item["link"])
        display_title = f"{item['source_name']} - {item['title']}"
        entries_xml.append(
            "    <item>\n"
            f"      <title>{escape_xml(display_title)}</title>\n"
            f"      <link>{guid}</link>\n"
            f"      <guid isPermaLink=\"true\">{guid}</guid>\n"
            f"      <pubDate>{format_datetime(item['pub_date'])}</pubDate>\n"
            f"      <source url=\"{escape_xml(item['source_url'])}\">{escape_xml(item['source_name'])}</source>\n"
            f"      <category>{escape_xml(item['source_name'])}</category>\n"
            "    </item>"
        )

    body = "\n".join(entries_xml)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Engineering Blogs</title>
    <link>{escape_xml(source_url)}</link>
    <description>RSS feed generated from the Engineering Blogs aggregator page.</description>
    <lastBuildDate>{now_str}</lastBuildDate>
    <generator>engblogs_rss_server.py</generator>
{body}
  </channel>
</rss>
"""


# ---------------------------------------------------------------------------
# Reddit RSS generation (from data/reddittext.json, data/redditupdates.json)
# ---------------------------------------------------------------------------

def parse_reddit_pubdate(value: str, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback


def build_reddit_rss(data: dict) -> str:
    now = datetime.now(timezone.utc)
    category_title = data.get("category", "Reddit")

    all_items = []
    for feed_name, feed in data.get("feeds", {}).items():
        for item in feed.get("items", []):
            all_items.append((feed_name, feed.get("source_url", ""), item))

    all_items.sort(key=lambda e: parse_reddit_pubdate(e[2].get("published", ""), now), reverse=True)

    items_xml = []
    for feed_name, source_url, item in all_items:
        title = f"{feed_name} - {item.get('title', '')}"
        link = item.get("link", "")
        pub_dt = parse_reddit_pubdate(item.get("published", ""), now)
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
    <generator>blogs.py</generator>
{body}
  </channel>
</rss>
"""


class RedditRawCache:
    def __init__(self, filename: str, ttl_seconds: int):
        self.filename = filename
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._rss = None
        self._fetched_at = 0.0

    def fetch_json(self) -> dict:
        url = f"{REDDIT_RAW_BASE}/{self.filename}?ts={int(time.time())}"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_rss(self, force: bool = False) -> str:
        with self._lock:
            stale = (time.time() - self._fetched_at) > self.ttl_seconds
            if force or self._rss is None or stale:
                data = self.fetch_json()
                self._rss = build_reddit_rss(data)
                self._fetched_at = time.time()
            return self._rss


reddit_caches = {path: RedditRawCache(filename, REDDIT_CACHE_SECONDS) for path, filename in REDDIT_ROUTES.items()}


# ---------------------------------------------------------------------------
# Fetching + caching
# ---------------------------------------------------------------------------

class FeedCache:
    def __init__(self, source_url: str, ttl_seconds: int):
        self.source_url = source_url
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._rss = None
        self._fetched_at = 0.0

    def fetch_html(self) -> str:
        req = Request(self.source_url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=20) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")

    def get_rss(self, force: bool = False) -> str:
        with self._lock:
            stale = (time.time() - self._fetched_at) > self.ttl_seconds
            if force or self._rss is None or stale:
                page_html = self.fetch_html()
                items = parse_page(page_html, self.source_url)
                self._rss = build_rss(items, self.source_url)
                self._fetched_at = time.time()
            return self._rss


cache = FeedCache(SOURCE_URL, CACHE_SECONDS)


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if self.path.startswith("/rss.xml"):
            try:
                force = "refresh" in self.path
                rss = cache.get_rss(force=force)
            except Exception as exc:  # noqa: BLE001
                self.send_response(502)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Failed to fetch/parse source: {exc}".encode())
                return
            body = rss.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path in REDDIT_ROUTES:
            try:
                force = "refresh" in self.path
                rss = reddit_caches[path].get_rss(force=force)
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
        elif self.path in ("/", "/index.html"):
            info = f"""<!doctype html>
<html><body>
<h1>Engineering Blogs &rarr; RSS bridge</h1>
<p>Source: <a href="{escape_xml(SOURCE_URL)}">{escape_xml(SOURCE_URL)}</a></p>
<p>Feed: <a href="/rss.xml">/rss.xml</a> (add <code>?refresh</code> to force re-fetch)</p>
<p> <a href="/reddittext">/reddittext</a> </p>
<p> <a href="/redditupdates">/redditupdates</a> </p>
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
    print(f"Serving RSS bridge for {SOURCE_URL}")
    print(f"  -> http://localhost:{PORT}/rss.xml")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

