import type { Env, EngblogsData } from "./types";
import { cleanText, resolveUrl } from "./util";

const USER_AGENT = "engblogs-rss-bridge/1.0 (+https://github.com/peterc/engblogs)";
const CACHE_KEY = "data:engblogs";
const NEXT_DUE_KEY = "state:engblogs_next_due_at";

const SECTION_RE = /<h2>([^<]+)<\/h2>\s*<div class="entries">([\s\S]*?)<\/div>\s*(?=<h2>|<footer)/g;
const ENTRY_RE =
  /<div class="entry">\s*<span class="source"><a href="([^"]*)">([\s\S]*?)<\/a><\/span>\s*<span class="title"><a href="([^"]*)">([\s\S]*?)<\/a><\/span>\s*<\/div>/g;

const MONTHS = [
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
];

function parseDateHeading(text: string, fallback: Date): Date {
  const cleaned = cleanText(text);
  // Matches "Friday, July 2, 2027" or "July 2, 2027".
  const match = cleaned.match(/(?:\w+,\s*)?(\w+)\s+(\d{1,2}),\s*(\d{4})/);
  if (!match) return fallback;
  const monthIndex = MONTHS.indexOf(match[1].toLowerCase());
  if (monthIndex === -1) return fallback;
  const day = parseInt(match[2], 10);
  const year = parseInt(match[3], 10);
  return new Date(Date.UTC(year, monthIndex, day, 0, 0, 0));
}

interface ParsedBlogItem {
  title: string;
  link: string;
  source_name: string;
  source_url: string;
  pub_date: Date;
}

export function parsePage(htmlText: string, baseUrl: string): ParsedBlogItem[] {
  const items: ParsedBlogItem[] = [];
  const now = new Date();

  for (const section of htmlText.matchAll(SECTION_RE)) {
    const sectionDate = parseDateHeading(section[1], now);
    const body = section[2];

    let i = 0;
    for (const entry of body.matchAll(ENTRY_RE)) {
      const [, sourceHref, sourceName, linkHref, title] = entry;
      const cleanTitle = cleanText(title);
      const link = resolveUrl(linkHref.trim(), baseUrl);
      const cleanSourceName = cleanText(sourceName);
      const sourceUrl = resolveUrl(sourceHref.trim(), baseUrl);

      if (!cleanTitle || !link) continue;

      // Entries within a day aren't individually timestamped on the source
      // page, so fan them out across the day (newest-first order preserved)
      // purely so RSS readers get distinct, monotonically-ordered pubDates.
      const pubDate = new Date(sectionDate);
      pubDate.setUTCHours(23, 59, i < 60 ? Math.max(0, 59 - i) : 0, 0);

      items.push({
        title: cleanTitle,
        link,
        source_name: cleanSourceName || "Unknown source",
        source_url: sourceUrl,
        pub_date: pubDate,
      });
      i += 1;
    }
  }

  return items;
}

export async function fetchHtml(url: string): Promise<string> {
  const resp = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
  if (!resp.ok) {
    throw new Error(`Fetch failed for ${url}: HTTP ${resp.status}`);
  }
  return resp.text();
}

async function fetchAndStoreEngblogs(env: Env, sourceUrl: string): Promise<EngblogsData> {
  const pageHtml = await fetchHtml(sourceUrl);
  const items = parsePage(pageHtml, sourceUrl);
  const data: EngblogsData = {
    source_url: sourceUrl,
    fetched_at: new Date().toISOString(),
    items: items.map((item) => ({
      title: item.title,
      link: item.link,
      source_name: item.source_name,
      source_url: item.source_url,
      published: item.pub_date.toISOString(),
    })),
  };
  await env.NEWSFEED_KV.put(CACHE_KEY, JSON.stringify(data));
  return data;
}

// Mirrors server.py's BlogsCache: fetch+parse the aggregator page at most
// once per CACHE_SECONDS, backed by KV instead of an in-process lock.
export async function getEngblogsData(env: Env, sourceUrl: string, forceRefresh: boolean): Promise<EngblogsData> {
  const ttlSeconds = parseInt(env.CACHE_SECONDS, 10) || 900;

  if (!forceRefresh) {
    const cached = (await env.NEWSFEED_KV.get(CACHE_KEY, "json")) as EngblogsData | null;
    if (cached) {
      const age = (Date.now() - new Date(cached.fetched_at).getTime()) / 1000;
      if (age <= ttlSeconds) return cached;
    }
  }

  return fetchAndStoreEngblogs(env, sourceUrl);
}

// Called from the cron tick so engblogs gets refreshed proactively on its
// own cadence (independent of the reddit round-robin and of request
// traffic), instead of only refreshing lazily on the next /blogs hit.
export async function refreshEngblogsIfDue(env: Env, sourceUrl: string, refreshHours: number): Promise<void> {
  let nextDueAt = await env.NEWSFEED_KV.get(NEXT_DUE_KEY).then((raw) => (raw ? parseInt(raw, 10) || 0 : 0));
  const now = Date.now();
  if (nextDueAt === 0) nextDueAt = now;
  if (now < nextDueAt) return;

  try {
    await fetchAndStoreEngblogs(env, sourceUrl);
    await env.NEWSFEED_KV.put(NEXT_DUE_KEY, String(nextDueAt + refreshHours * 3600 * 1000));
  } catch (err) {
    console.error("engblogs refresh failed, will retry next tick:", err);
  }
}
