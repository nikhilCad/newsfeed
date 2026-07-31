#!/usr/bin/env python3
"""Fetch the Engineering Blogs aggregator page and write data/engblogs.json.

Kept as its own file (separate from rss_render.py's shared helpers and from
scripts/fetch_feed.py's reddit round-robin) so scripts/server.py's /blogs
route can trigger a fresh fetch+parse on its own schedule, independent of the
reddit fetch cadence.

Usage:
    python3 scripts/blogs_fetch.py
    SOURCE_URL=https://engineeringblogs.xyz/ python3 scripts/blogs_fetch.py
"""
import json
import os
from datetime import datetime, timezone

from rss_render import fetch_html, parse_page

SOURCE_URL = os.environ.get("SOURCE_URL", "https://engineeringblogs.xyz/")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
JSON_PATH = os.path.join(DATA_DIR, "engblogs.json")


def generate_blogs_json(source_url=None) -> dict:
    """Fetch + parse the aggregator page and write data/engblogs.json.

    Returns the same dict that gets written, so callers (e.g. the /blogs
    server route) can render RSS from it without a second disk read.
    """
    source_url = source_url or SOURCE_URL
    page_html = fetch_html(source_url)
    items = parse_page(page_html, source_url)

    data = {
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": [
            {
                "title": item["title"],
                "link": item["link"],
                "source_name": item["source_name"],
                "source_url": item["source_url"],
                "published": item["pub_date"].isoformat(),
            }
            for item in items
        ],
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return data


def main():
    data = generate_blogs_json()
    print(f"Saved {len(data['items'])} items into data/engblogs.json")


if __name__ == "__main__":
    main()
