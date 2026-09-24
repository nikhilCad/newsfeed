import type { Env, RedditCategoryData } from "./types";
import { flatten, getFeedsConfig, loadNextDueAt, loadNextIndex, saveNextDueAt, saveNextIndex } from "./feedsConfig";
import { fetchAtom, parseAtomEntries, mergeCategoryData, loadCategoryData } from "./reddit";
import { buildRedditRss, buildEngblogsRss } from "./rss";
import { getEngblogsData, refreshEngblogsIfDue } from "./blogs";

async function renderRedditRoute(env: Env, categoryKey: string): Promise<Response> {
  const data = await loadCategoryData(env, categoryKey);
  if (!data) {
    return new Response(
      `data:${categoryKey} doesn't exist yet -- wait for the next cron tick to populate it`,
      { status: 503 },
    );
  }
  return new Response(buildRedditRss(data as RedditCategoryData), {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}

async function handleFetch(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const config = await getFeedsConfig(env);
  const categoryKeys = config.categories.map((c) => c.key);

  if (path.length > 1 && categoryKeys.includes(path.slice(1))) {
    return renderRedditRoute(env, path.slice(1));
  }

  if (path === "/blogs") {
    try {
      const forceRefresh = url.searchParams.has("refresh");
      const data = await getEngblogsData(env, env.SOURCE_URL, forceRefresh);
      return new Response(buildEngblogsRss(data), {
        headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
      });
    } catch (err) {
      return new Response(`Failed to fetch/parse blogs source: ${(err as Error).message}`, { status: 502 });
    }
  }

  if (path === "/" || path === "/index.html") {
    const links = [...categoryKeys.map((k) => `/${k}`), "/blogs"]
      .map((p) => `<li><a href="${p}">${p}</a></li>`)
      .join("");
    return new Response(`<!doctype html><html><body><h1>newsfeed</h1><ul>${links}</ul></body></html>`, {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }

  return new Response("Not found", { status: 404 });
}

// The cron trigger itself still fires every 3 minutes (Reddit rate-limits to
// ~1 req/min, so a tick this frequent is still safe), but each tick is a
// cheap no-op unless a fetch is actually due. Pacing is time-based rather
// than "one feed per tick": REDDIT_CYCLE_HOURS is spread evenly across all
// feeds, so a full round-robin (every feed refreshed once) takes that long
// in total, however many feeds there are. A failed fetch doesn't advance
// the index or the due time, so the same feed is retried on the very next
// tick instead of waiting a full interval.
async function runRedditCycleIfDue(env: Env): Promise<void> {
  const config = await getFeedsConfig(env);
  const order = flatten(config);
  if (order.length === 0) return;

  const now = Date.now();
  let nextDueAt = await loadNextDueAt(env);
  if (nextDueAt === 0) nextDueAt = now;
  if (now < nextDueAt) return;

  const cycleHours = parseFloat(env.REDDIT_CYCLE_HOURS) || 6;
  const intervalMs = (cycleHours * 3600 * 1000) / order.length;

  const nextIndex = await loadNextIndex(env);
  const slot = nextIndex % order.length;
  const { categoryKey, categoryTitle, feed } = order[slot];

  try {
    const xmlText = await fetchAtom(feed.url);
    const items = parseAtomEntries(xmlText);
    await mergeCategoryData(env, categoryKey, categoryTitle, feed, items);
    await saveNextIndex(env, (slot + 1) % order.length);
    await saveNextDueAt(env, nextDueAt + intervalMs);
    console.log(`Slot ${slot}: fetched '${feed.name}' (${items.length} items) -> data:${categoryKey}`);
  } catch (err) {
    console.error(`Slot ${slot}: fetch failed for '${feed.name}', will retry next tick:`, err);
  }
}

async function handleScheduled(env: Env): Promise<void> {
  await runRedditCycleIfDue(env);
  const refreshHours = parseFloat(env.ENGBLOGS_REFRESH_HOURS) || 3;
  await refreshEngblogsIfDue(env, env.SOURCE_URL, refreshHours);
}

export default {
  fetch: (request: Request, env: Env) => handleFetch(request, env),
  scheduled: (_event: ScheduledEvent, env: Env, ctx: ExecutionContext) => {
    ctx.waitUntil(handleScheduled(env));
  },
};
