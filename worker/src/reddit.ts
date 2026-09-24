import type { Env, Feed, RedditCategoryData, RedditItem } from "./types";
import { cleanText, htmlUnescape } from "./util";

const USER_AGENT = "newsfeed-reddit-bridge/1.0";

// Reddit wraps a post's selftext (if any) in these markers inside <content>,
// e.g. <!-- SC_OFF --><div class="md">...</div><!-- SC_ON -->. Image/gallery
// posts without a text body, and pure link posts, don't have this block.
const SELFTEXT_RE = /<!--\s*SC_OFF\s*-->\s*<div class="md">([\s\S]*?)<\/div>\s*<!--\s*SC_ON\s*-->/;

const ENTRY_RE = /<entry>([\s\S]*?)<\/entry>/g;

function extractTag(entry: string, tag: string): string {
  const match = entry.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`));
  return match ? htmlUnescape(match[1]).trim() : "";
}

function extractLinkHref(entry: string): string {
  const match = entry.match(/<link\b[^>]*\bhref="([^"]*)"[^>]*\/?>/);
  return match ? htmlUnescape(match[1]) : "";
}

function extractThumbnail(entry: string): string {
  const match = entry.match(/<media:thumbnail\b[^>]*\burl="([^"]*)"/);
  return match ? htmlUnescape(match[1]) : "";
}

function extractSelftext(contentHtml: string): string {
  if (!contentHtml) return "";
  const match = contentHtml.match(SELFTEXT_RE);
  return match ? cleanRawHtml(match[1]) : "";
}

// The selftext block is HTML meant to be preserved as-is (it's re-embedded
// into the rendered RSS <description>), so only trim it -- don't collapse
// whitespace the way cleanText does for plain-text fields.
function cleanRawHtml(html: string): string {
  return html.trim();
}

export function parseAtomEntries(xmlText: string): RedditItem[] {
  const items: RedditItem[] = [];
  for (const match of xmlText.matchAll(ENTRY_RE)) {
    const entry = match[1];
    const title = extractTag(entry, "title");
    const link = extractLinkHref(entry);
    const authorBlock = entry.match(/<author>([\s\S]*?)<\/author>/);
    const author = authorBlock ? extractTag(authorBlock[1], "name") : "";
    const published = extractTag(entry, "published") || extractTag(entry, "updated");
    if (!title || !link) continue;

    const thumbnail = extractThumbnail(entry);
    const contentMatch = entry.match(/<content\b[^>]*>([\s\S]*?)<\/content>/);
    const contentHtml = contentMatch ? htmlUnescape(contentMatch[1]) : "";
    const selftext = extractSelftext(contentHtml);

    items.push({ title: cleanText(title), link, author, published, thumbnail, selftext });
  }
  return items;
}

export async function fetchAtom(url: string): Promise<string> {
  const resp = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
  if (!resp.ok) {
    throw new Error(`Fetch failed for ${url}: HTTP ${resp.status}`);
  }
  return resp.text();
}

function dataKey(categoryKey: string): string {
  return `data:${categoryKey}`;
}

export async function loadCategoryData(env: Env, categoryKey: string): Promise<RedditCategoryData | null> {
  return (await env.NEWSFEED_KV.get(dataKey(categoryKey), "json")) as RedditCategoryData | null;
}

export async function mergeCategoryData(
  env: Env,
  categoryKey: string,
  categoryTitle: string,
  feed: Feed,
  items: RedditItem[],
): Promise<void> {
  const existing = await loadCategoryData(env, categoryKey);
  const data: RedditCategoryData = existing ?? { category: categoryTitle, feeds: {} };
  data.category = categoryTitle;
  data.feeds[feed.name] = {
    source_url: feed.url,
    fetched_at: new Date().toISOString(),
    items,
  };
  await env.NEWSFEED_KV.put(dataKey(categoryKey), JSON.stringify(data));
}
