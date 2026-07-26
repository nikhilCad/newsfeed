#!/usr/bin/env python3
"""Long-running local replacement for the old GitHub Actions + Render setup.

Run this on your own machine (not a shared-IP CI runner), leave it running,
and it keeps data/*.xml up to date:

  - On startup: fetches the Engineering Blogs aggregator page once (that
    site has no rate limit) and writes data/engblogs.xml.
  - Then forever: fetches the next Reddit feed in feeds.json (round-robin,
    same one-feed-per-cycle approach as before, since Reddit rate-limits to
    ~1 req/min) and, on every successful fetch, regenerates both
    data/reddittext.xml and data/redditupdates.xml from the merged JSON in
    data/. Waits a random 5-10 minutes between cycles.

Nothing here commits or pushes to git -- commit data/ yourself when you want
your RSS reader (pointed at raw.githubusercontent.com) to see the update.

Usage:
    python3 scripts/run_local.py
    SOURCE_URL=https://engineeringblogs.xyz/ python3 scripts/run_local.py
"""
import json
import os
import random
import time
import traceback
from datetime import datetime, timezone

from fetch_feed import fetch_one_feed
from rss_render import build_reddit_rss, fetch_engblogs_rss

SOURCE_URL = os.environ.get("SOURCE_URL", "https://engineeringblogs.xyz/")
MIN_DELAY_SECONDS = 5 * 60
MAX_DELAY_SECONDS = 10 * 60

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

REDDIT_JSON_TO_XML = {
    "reddittext.json": "reddittext.xml",
    "redditupdates.json": "redditupdates.xml",
}


def log(message):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


def write_engblogs_feed():
    rss = fetch_engblogs_rss(SOURCE_URL)
    path = os.path.join(DATA_DIR, "engblogs.xml")
    with open(path, "w") as f:
        f.write(rss)
    log(f"Wrote {path}")


def regenerate_reddit_feeds():
    for json_name, xml_name in REDDIT_JSON_TO_XML.items():
        json_path = os.path.join(DATA_DIR, json_name)
        if not os.path.exists(json_path):
            continue
        with open(json_path) as f:
            data = json.load(f)
        rss = build_reddit_rss(data)
        xml_path = os.path.join(DATA_DIR, xml_name)
        with open(xml_path, "w") as f:
            f.write(rss)
        log(f"Wrote {xml_path}")


def run_reddit_cycle():
    try:
        category_key, feed_name, count = fetch_one_feed()
        log(f"Fetched '{feed_name}' ({count} items) -> data/{category_key}.json")
        regenerate_reddit_feeds()
    except Exception:
        log("Reddit fetch cycle failed, will retry next cycle:")
        traceback.print_exc()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    log(f"Fetching engineering blogs feed from {SOURCE_URL}")
    try:
        write_engblogs_feed()
    except Exception:
        log("Engineering blogs fetch failed (continuing to reddit loop anyway):")
        traceback.print_exc()

    log("Starting reddit fetch loop (Ctrl+C to stop)")
    try:
        while True:
            run_reddit_cycle()
            delay = random.randint(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
            log(f"Sleeping {delay}s ({delay / 60:.1f} min) until next fetch")
            time.sleep(delay)
    except KeyboardInterrupt:
        log("Stopped.")


if __name__ == "__main__":
    main()
