#!/usr/bin/env python3
"""Convert latest_feeds.opml into feeds.json (a flat, ordered feed list per category).

feeds.json is the source of truth that scripts/fetch_feed.py walks through --
its feed order determines which feed each 5-minute cron slot maps to, so
re-running this after editing the OPML will change that mapping.

Usage:
    python3 scripts/opml_to_json.py
"""
import json
import os
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPML_PATH = os.path.join(ROOT, "latest_feeds.opml")
OUT_PATH = os.path.join(ROOT, "feeds.json")

# Maps OPML top-level folder title -> short key used for data/<key>.json and
# the /<key> HTTP route. Unknown folders fall back to a slugified title.
CATEGORY_KEYS = {
    "Reddit Text": "reddittext",
    "Updates": "redditupdates",
}


def slugify(title: str) -> str:
    return "".join(ch for ch in title.lower() if ch.isalnum())


def main():
    tree = ET.parse(OPML_PATH)
    body = tree.getroot().find("body")

    categories = []
    for group in body.findall("outline"):
        title = group.get("title") or group.get("text")
        key = CATEGORY_KEYS.get(title, slugify(title))
        feeds = []
        for outline in group.findall("outline"):
            feeds.append(
                {
                    "name": outline.get("title") or outline.get("text"),
                    "url": outline.get("xmlUrl"),
                    "category": outline.get("category") or title,
                }
            )
        categories.append({"key": key, "title": title, "feeds": feeds})

    with open(OUT_PATH, "w") as f:
        json.dump({"categories": categories}, f, indent=2, ensure_ascii=False)
        f.write("\n")

    total = sum(len(c["feeds"]) for c in categories)
    print(f"Wrote {OUT_PATH}: {len(categories)} categories, {total} feeds total")
    for c in categories:
        print(f"  {c['key']} ({c['title']}): {len(c['feeds'])} feeds")


if __name__ == "__main__":
    main()
