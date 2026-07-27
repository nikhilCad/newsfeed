#!/usr/bin/env python3
"""Long-running local replacement for the old GitHub Actions + Render setup.

Run this on your own machine (not a shared-IP CI runner) from the repo root,
and it keeps data/*.xml up to date and pushed to origin/main:

  - On startup: runs `git fetch origin main && git reset --hard origin/main`
    to sync with the remote, then fetches the Engineering Blogs aggregator
    page once (that site has no rate limit) and writes data/engblogs.xml.
  - Then loops exactly once per feed in feeds.json (round-robin, one feed per
    cycle, since Reddit rate-limits to ~1 req/min): fetches the next feed
    and, on every successful fetch, regenerates data/reddittext.xml and
    data/redditupdates.xml, then runs `git commit -am <message> && git push
    origin main`. Waits a random 5-10 minutes between cycles. Exits once it
    has run one full round-robin cycle (one iteration per feed).

Git commands are shelled out with os.system() against the current working
directory -- run this script from the repo root.

Usage:
    python3 scripts/run_local.py
    SOURCE_URL=https://engineeringblogs.xyz/ python3 scripts/run_local.py
"""
import json
import os
import random
import shlex
import time
import traceback
from datetime import datetime, timezone

from fetch_feed import fetch_one_feed, flatten, load_feeds
from rss_render import build_reddit_rss, fetch_engblogs_rss

SOURCE_URL = os.environ.get("SOURCE_URL", "https://engineeringblogs.xyz/")
MIN_DELAY_SECONDS = 2 * 60
MAX_DELAY_SECONDS = 4 * 60
MAX_ATTEMPTS_PER_FEED = 3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

REDDIT_JSON_TO_XML = {
    "reddittext.json": "reddittext.xml",
    "redditupdates.json": "redditupdates.xml",
}


def log(message):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


def git_sync_from_remote():
    log("Syncing with origin/main: git fetch origin main && git reset --hard origin/main")
    ret = os.system("git fetch origin main && git reset --hard origin/main")
    if ret != 0:
        log(f"git sync failed with exit code {ret}")


def git_commit_and_push(message):
    cmd = f"git add . && git commit -am {shlex.quote(message)} && git push origin main"
    log(f"Running: {cmd}")
    ret = os.system(cmd)
    if ret != 0:
        log(f"git commit/push failed or nothing to commit (exit code {ret})")


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
    """Fetch+regenerate one feed. Returns (category_key, feed_name, count) on
    success, None on failure (caller skips the git commit for that cycle)."""
    try:
        category_key, feed_name, count = fetch_one_feed()
        log(f"Fetched '{feed_name}' ({count} items) -> data/{category_key}.json")
        regenerate_reddit_feeds()
        return category_key, feed_name, count
    except Exception:
        log("Reddit fetch cycle failed, will retry next cycle:")
        traceback.print_exc()
        return None


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    git_sync_from_remote()

    log(f"Fetching engineering blogs feed from {SOURCE_URL}")
    try:
        write_engblogs_feed()
    except Exception:
        log("Engineering blogs fetch failed (continuing to reddit loop anyway):")
        traceback.print_exc()

    num_feeds = len(flatten(load_feeds()))
    max_attempts = num_feeds * MAX_ATTEMPTS_PER_FEED
    log(f"Starting reddit fetch loop for one full round-robin cycle ({num_feeds} feeds)")
    successes = 0
    attempts = 0
    try:
        while True:
            result = run_reddit_cycle()
            attempts += 1
            if result is not None:
                successes += 1
                category_key, feed_name, count = result
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                message = f"Refresh {category_key}: '{feed_name}' ({count} items) at {stamp}"
                git_commit_and_push(message)
            else:
                # fetch_one_feed only advances its round-robin index on success,
                # so the next cycle automatically retries this same feed.
                log(f"Will retry the same feed next cycle (attempt {attempts}/{max_attempts})")

            if successes >= num_feeds:
                log(f"Completed {successes}/{num_feeds} feeds in {attempts} attempts, exiting.")
                break
            if attempts >= max_attempts:
                log(f"Hit max attempts ({max_attempts}) with only {successes}/{num_feeds} feeds "
                    "fetched -- giving up for this run.")
                break

            delay = random.randint(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
            log(f"Sleeping {delay}s ({delay / 60:.1f} min) until next fetch")
            time.sleep(delay)
    except KeyboardInterrupt:
        log("Stopped.")


if __name__ == "__main__":
    main()
