#!/usr/bin/env python3
"""Fetch exactly one Reddit feed and merge it into data/<category>.json.

Reddit now rate-limits to ~1 request/minute, so a full refresh of all 13
feeds in feeds.json is spread across a 60-minute window, one feed every 5
minutes. .github/workflows/refresh-reddit-feeds.yml schedules this script to
run only inside two such windows per day (4:00-5:00 and 16:00-17:00 IST).

Which feed to fetch is derived purely from the current time -- slot N is
(minutes since the window started) // 5 -- so no counter/state file has to
be carried between runs. Pass FEED_INDEX to override this for manual testing.

Usage:
    python3 scripts/fetch_feed.py
    FEED_INDEX=3 python3 scripts/fetch_feed.py
"""
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
ATOM_NS = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "newsfeed-reddit-bridge/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDS_JSON = os.path.join(ROOT, "feeds.json")
DATA_DIR = os.path.join(ROOT, "data")

SLOT_MINUTES = 5
NUM_FEEDS = 13
WINDOW_STARTS_MIN = {
    "morning": 4 * 60,   # 04:00 IST
    "evening": 16 * 60,  # 16:00 IST
}


def load_feeds():
    with open(FEEDS_JSON) as f:
        return json.load(f)


def flatten(feeds):
    order = []
    for category in feeds["categories"]:
        for feed in category["feeds"]:
            order.append((category["key"], feed))
    return order


def current_slot(now_ist):
    minutes_of_day = now_ist.hour * 60 + now_ist.minute
    for window_start in WINDOW_STARTS_MIN.values():
        offset = minutes_of_day - window_start
        if 0 <= offset < NUM_FEEDS * SLOT_MINUTES:
            return offset // SLOT_MINUTES
    return None


def fetch_atom(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


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
    if override:
        slot = int(override)
    else:
        slot = current_slot(datetime.now(IST))
        if slot is None:
            print("Not inside a refresh window; nothing to do.")
            return

    if slot >= len(order):
        print(f"Slot {slot} out of range (only {len(order)} feeds); nothing to do.")
        return

    category_key, feed = order[slot]
    category_title = next(c["title"] for c in feeds["categories"] if c["key"] == category_key)

    print(f"Slot {slot}: fetching '{feed['name']}' ({feed['url']})")
    xml_text = fetch_atom(feed["url"])
    items = parse_entries(xml_text)
    update_category_file(category_key, category_title, feed["name"], feed["url"], items)
    print(f"Saved {len(items)} items for '{feed['name']}' into data/{category_key}.json")


if __name__ == "__main__":
    main()
