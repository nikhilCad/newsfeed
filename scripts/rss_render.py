#!/usr/bin/env python3
"""RSS-building helpers shared by scripts/run_local.py.

Extracted from the old blogs.py HTTP server: same parsing/rendering logic,
just used to write static XML files to data/ instead of serving them live.
"""
import html
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urljoin
from urllib.request import Request, urlopen

USER_AGENT = "engblogs-rss-bridge/1.0 (+https://github.com/peterc/engblogs)"

# ---------------------------------------------------------------------------
# Engineering blogs aggregator page -> RSS
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(
    r"<h2>(?P<date>[^<]+)</h2>\s*<div class=\"entries\">(?P<body>.*?)</div>\s*(?=<h2>|<footer)",
    re.DOTALL,
)

ENTRY_RE = re.compile(
    r'<div class="entry">\s*'
    r'<span class="source"><a href="(?P<source_url>[^"]*)">(?P<source_name>.*?)</a></span>\s*'
    r'<span class="title"><a href="(?P<link>[^"]*)">(?P<title>.*?)</a></span>\s*'
    r"</div>",
    re.DOTALL,
)

# Strip invisible / zero-width / formatting unicode characters that can be
# used to hide payloads inside otherwise-innocuous-looking text.
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
    <generator>scripts/run_local.py</generator>
{body}
  </channel>
</rss>
"""


def fetch_html(source_url: str) -> str:
    req = Request(source_url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_engblogs_rss(source_url: str) -> str:
    page_html = fetch_html(source_url)
    items = parse_page(page_html, source_url)
    return build_rss(items, source_url)


# ---------------------------------------------------------------------------
# Reddit data/*.json -> RSS
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
        thumbnail = item.get("thumbnail", "")
        selftext = item.get("selftext", "")

        description_parts = []
        if thumbnail:
            description_parts.append(f'<img src="{thumbnail}" />')
        if selftext:
            description_parts.append(selftext)
        description_xml = (
            f"      <description>{escape_xml(''.join(description_parts))}</description>\n"
            if description_parts
            else ""
        )
        thumbnail_xml = (
            f'      <media:thumbnail url="{escape_xml(thumbnail)}" />\n' if thumbnail else ""
        )

        items_xml.append(
            "    <item>\n"
            f"      <title>{escape_xml(title)}</title>\n"
            f"      <link>{escape_xml(link)}</link>\n"
            f"      <guid isPermaLink=\"true\">{escape_xml(link)}</guid>\n"
            f"      <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            f"{description_xml}"
            f"{thumbnail_xml}"
            f"      <source url=\"{escape_xml(source_url)}\">{escape_xml(feed_name)}</source>\n"
            f"      <category>{escape_xml(feed_name)}</category>\n"
            "    </item>"
        )

    body = "\n".join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>{escape_xml(category_title)}</title>
    <link>https://github.com/</link>
    <description>Reddit feeds refreshed locally by scripts/run_local.py.</description>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
    <generator>scripts/run_local.py</generator>
{body}
  </channel>
</rss>
"""


# ---------------------------------------------------------------------------
# Engineering blogs data/engblogs.json (as written by scripts/blogs_fetch.py) -> RSS
# ---------------------------------------------------------------------------

def build_engblogs_rss(data: dict) -> str:
    now = datetime.now(timezone.utc)
    source_url = data.get("source_url", "")

    items_xml = []
    for item in data.get("items", []):
        pub_dt = parse_reddit_pubdate(item.get("published", ""), now)
        guid = escape_xml(item.get("link", ""))
        display_title = f"{item.get('source_name', 'Unknown source')} - {item.get('title', '')}"
        items_xml.append(
            "    <item>\n"
            f"      <title>{escape_xml(display_title)}</title>\n"
            f"      <link>{guid}</link>\n"
            f"      <guid isPermaLink=\"true\">{guid}</guid>\n"
            f"      <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            f"      <source url=\"{escape_xml(item.get('source_url', ''))}\">{escape_xml(item.get('source_name', ''))}</source>\n"
            f"      <category>{escape_xml(item.get('source_name', ''))}</category>\n"
            "    </item>"
        )

    body = "\n".join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Engineering Blogs</title>
    <link>{escape_xml(source_url)}</link>
    <description>RSS feed generated from the Engineering Blogs aggregator page.</description>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
    <generator>scripts/server.py</generator>
{body}
  </channel>
</rss>
"""
