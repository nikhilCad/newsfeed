#!/usr/bin/env python3
"""Fetch exactly one Reddit feed and merge it into data/<category>.json.

Reddit rate-limits to ~1 request/minute, so .github/workflows/refresh-reddit-feeds.yml
runs this script every 40 minutes, and each run fetches just the next feed in
feeds.json (round-robin). Which feed that is comes from data/fetch_state.json
(the index of the last feed fetched), not from wall-clock time -- GitHub's
schedule trigger is best-effort and runs get delayed or dropped, so deriving
the slot from "what time is it" caused most runs to either fetch the wrong
feed or silently no-op. Advancing a persisted counter instead means every run
that actually fires does useful work, in order, regardless of when it lands.

Pass FEED_INDEX to fetch a specific feed by index for manual testing --
this does not touch or advance the persisted state.

Usage:
    python3 scripts/fetch_feed.py
    FEED_INDEX=3 python3 scripts/fetch_feed.py
"""
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ATOM_NS = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "newsfeed-reddit-bridge/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDS_JSON = os.path.join(ROOT, "feeds.json")
DATA_DIR = os.path.join(ROOT, "data")
STATE_PATH = os.path.join(DATA_DIR, "fetch_state.json")


def load_feeds():
    with open(FEEDS_JSON) as f:
        return json.load(f)


def flatten(feeds):
    order = []
    for category in feeds["categories"]:
        for feed in category["feeds"]:
            order.append((category["key"], feed))
    return order


def load_next_index():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f).get("next_index", 0)
    return 0


def save_next_index(index):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({"next_index": index}, f, indent=2)
        f.write("\n")


def fetch_atom(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        content_type = resp.headers.get_content_type()
        return resp.read().decode(charset, errors="replace"), content_type


def describe_parse_error(xml_text, content_type, error):
    line, col = error.position
    lines = xml_text.splitlines() or [xml_text]
    bad_line = lines[line - 1] if 0 < line <= len(lines) else xml_text
    snippet = bad_line[max(0, col - 80):col + 80]
    pointer = " " * min(col, 80) + "^"
    return (
        f"Failed to parse feed as XML at line {line}, column {col}: {error}\n"
        f"Response Content-Type: {content_type}\n"
        f"Context around error:\n{snippet}\n{pointer}\n"
        f"First 200 chars of raw response: {xml_text[:200]!r}\n"
        "This is usually not a bug in the feed itself -- Reddit occasionally serves "
        "a rate-limit/interstitial HTML page instead of the RSS/Atom feed (shared-IP "
        "runners like GitHub Actions hit this more than a home IP would). Check the "
        "Content-Type and snippet above: if it looks like HTML rather than XML, this "
        "run just needs to be retried later rather than the parser fixed."
    )


def parse_entries(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip()
        link_el = entry.find(f"{ATOM_NS}link")
        link = link_el.get("href") if link_el is not None else ""
        author = (entry.findtext(f"{ATOM_NS}author/{ATOM_NS}name") or "").strip()
        published = (
            entry.findtext(f"{ATOM_NS}published")
            or entry.findtext(f"{ATOM_NS}updated")
            or ""
        )
        if not title or not link:
            continue
        items.append({"title": title, "link": link, "author": author, "published": published})
    return items


def update_category_file(category_key, category_title, feed_name, feed_url, items):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{category_key}.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    else:
        data = {"category": category_title, "feeds": {}}

    data["category"] = category_title
    data.setdefault("feeds", {})[feed_name] = {
        "source_url": feed_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    feeds = load_feeds()
    order = flatten(feeds)

    override = os.environ.get("FEED_INDEX")
    advance_state = not override
    slot = int(override) % len(order) if override else load_next_index() % len(order)

    category_key, feed = order[slot]
    category_title = next(c["title"] for c in feeds["categories"] if c["key"] == category_key)

    print(f"Slot {slot}: fetching '{feed['name']}' ({feed['url']})")
    xml_text, content_type = fetch_atom(feed["url"])
    try:
        items = parse_entries(xml_text)
    except ET.ParseError as e:
        raise SystemExit(describe_parse_error(xml_text, content_type, e)) from e
    update_category_file(category_key, category_title, feed["name"], feed["url"], items)
    print(f"Saved {len(items)} items for '{feed['name']}' into data/{category_key}.json")

    if advance_state:
        save_next_index((slot + 1) % len(order))


if __name__ == "__main__":
    main()
