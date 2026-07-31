#!/usr/bin/env python3
"""HTTP server exposing live RSS endpoints on top of data/*.json.

Routes:
    /reddittext    - renders data/reddittext.json as RSS. That JSON is kept
                     fresh by scripts/run_local.py's round-robin loop (or a
                     manual scripts/fetch_feed.py run) -- this route just
                     builds the RSS on the fly from whatever is on disk.
    /redditupdates - same, from data/redditupdates.json.
    /blogs         - triggers scripts/blogs_fetch.py to fetch the Engineering
                     Blogs aggregator page and regenerate data/engblogs.json,
                     then renders that as RSS. Cached for CACHE_SECONDS so
                     repeated requests don't hammer the source page; pass
                     ?refresh to force an immediate re-fetch.

Usage:
    python3 scripts/server.py
    PORT=8000 python3 scripts/server.py

Env vars:
    PORT          - port to listen on (default: 8000)
    CACHE_SECONDS - how long to cache the fetched blogs page before
                    re-fetching (default: 900)
    SOURCE_URL    - blogs aggregator page to fetch (default:
                    https://engineeringblogs.xyz/)
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from blogs_fetch import generate_blogs_json
from rss_render import build_engblogs_rss, build_reddit_rss

PORT = int(os.environ.get("PORT", "8000"))
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "900"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

REDDIT_ROUTES = {
    "/reddittext": "reddittext.json",
    "/redditupdates": "redditupdates.json",
}


def render_reddit_rss(json_name: str) -> str:
    path = os.path.join(DATA_DIR, json_name)
    with open(path) as f:
        data = json.load(f)
    return build_reddit_rss(data)


class BlogsCache:
    """Fetches+regenerates data/engblogs.json at most once per ttl_seconds."""

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._rss = None
        self._fetched_at = 0.0

    def get_rss(self, force: bool = False) -> str:
        with self._lock:
            stale = (time.time() - self._fetched_at) > self.ttl_seconds
            if force or self._rss is None or stale:
                data = generate_blogs_json()
                self._rss = build_engblogs_rss(data)
                self._fetched_at = time.time()
            return self._rss


blogs_cache = BlogsCache(CACHE_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logging
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send_rss(self, rss: str):
        body = rss.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: int, message: str):
        body = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in REDDIT_ROUTES:
            json_name = REDDIT_ROUTES[path]
            try:
                rss = render_reddit_rss(json_name)
            except FileNotFoundError:
                self._send_error(
                    503,
                    f"data/{json_name} doesn't exist yet -- run scripts/run_local.py "
                    "or scripts/fetch_feed.py first",
                )
                return
            except Exception as exc:  # noqa: BLE001
                self._send_error(502, f"Failed to render {path}: {exc}")
                return
            self._send_rss(rss)

        elif path == "/blogs":
            try:
                force = "refresh" in self.path
                rss = blogs_cache.get_rss(force=force)
            except Exception as exc:  # noqa: BLE001
                self._send_error(502, f"Failed to fetch/parse blogs source: {exc}")
                return
            self._send_rss(rss)

        elif path in ("/", "/index.html"):
            routes = list(REDDIT_ROUTES) + ["/blogs"]
            links = "".join(f'<li><a href="{p}">{p}</a></li>' for p in routes)
            info = f"""<!doctype html>
<html><body>
<h1>newsfeed</h1>
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
    print(f"Serving newsfeed endpoints on port {PORT}")
    for path in list(REDDIT_ROUTES) + ["/blogs"]:
        print(f"  -> http://localhost:{PORT}{path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
