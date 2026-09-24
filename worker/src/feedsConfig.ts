import type { Env, Feed, FeedsConfig } from "./types";

// Seeds KV on first run so the worker is usable before any manual edit.
// After that, KV (not this constant) is the source of truth -- edit
// "config:feeds" directly instead of redeploying.
const DEFAULT_FEEDS: FeedsConfig = {
  categories: [
    {
      key: "reddittext",
      title: "Reddit Text",
      feeds: [
        { name: "top scoring links : AskIndia", url: "https://old.reddit.com/r/AskIndia/top.rss?limit=5" },
        { name: "AskReddit: search results - nsfw:no", url: "https://old.reddit.com/r/AskReddit/search/.rss?q=nsfw%3Ano&sort=top&restrict_sr=on&t=day&limit=3" },
        { name: "top scoring links : Frugal_Ind", url: "https://old.reddit.com/r/Frugal_Ind/top.rss?limit=5" },
        { name: "top scoring links : delhi", url: "https://old.reddit.com/r/delhi/top.rss?limit=5" },
        { name: "top scoring links : FIRE_Ind", url: "https://old.reddit.com/r/FIRE_Ind/top.rss?limit=1" },
        { name: "top scoring links : hopeposting", url: "https://old.reddit.com/r/hopeposting/top.rss?sort=top&t=day&limit=2" },
        { name: "top scoring links : LifeProTips", url: "https://old.reddit.com/r/lifeprotips/top/.rss?limit=5" },
        { name: "top scoring links : malelivingspace", url: "https://old.reddit.com/r/malelivingspace/top.rss?limit=2" },
        { name: "top scoring links : ProgrammerHumor", url: "https://old.reddit.com/r/programmerhumor/top.rss?limit=3" },
        { name: "top scoring links : Android", url: "https://old.reddit.com/r/android/top.rss?limit=3" },
      ],
    },
    {
      key: "redditupdates",
      title: "Updates",
      feeds: [
        { name: "top scoring links : developersIndia", url: "https://old.reddit.com/r/developersIndia/top.rss?t=day&limit=8" },
        { name: "top scoring links : ExperiencedDevs", url: "https://old.reddit.com/r/ExperiencedDevs/top.rss?limit=3" },
        { name: "top scoring links : LeetcodeDesi", url: "https://old.reddit.com/r/LeetcodeDesi/top.rss?t=day&limit=5" },
      ],
    },
  ],
};

const FEEDS_KEY = "config:feeds";
const STATE_KEY = "state:fetch_index";
const NEXT_DUE_KEY = "state:fetch_next_due_at";

export async function getFeedsConfig(env: Env): Promise<FeedsConfig> {
  const stored = await env.NEWSFEED_KV.get(FEEDS_KEY, "json");
  if (stored) return stored as FeedsConfig;
  await env.NEWSFEED_KV.put(FEEDS_KEY, JSON.stringify(DEFAULT_FEEDS));
  return DEFAULT_FEEDS;
}

export function flatten(config: FeedsConfig): { categoryKey: string; categoryTitle: string; feed: Feed }[] {
  const order: { categoryKey: string; categoryTitle: string; feed: Feed }[] = [];
  for (const category of config.categories) {
    for (const feed of category.feeds) {
      order.push({ categoryKey: category.key, categoryTitle: category.title, feed });
    }
  }
  return order;
}

export async function loadNextIndex(env: Env): Promise<number> {
  const raw = await env.NEWSFEED_KV.get(STATE_KEY);
  return raw ? parseInt(raw, 10) || 0 : 0;
}

export async function saveNextIndex(env: Env, index: number): Promise<void> {
  await env.NEWSFEED_KV.put(STATE_KEY, String(index));
}

// 0 means "never scheduled" -- callers treat that as due-now on the first tick.
export async function loadNextDueAt(env: Env): Promise<number> {
  const raw = await env.NEWSFEED_KV.get(NEXT_DUE_KEY);
  return raw ? parseInt(raw, 10) || 0 : 0;
}

export async function saveNextDueAt(env: Env, epochMs: number): Promise<void> {
  await env.NEWSFEED_KV.put(NEXT_DUE_KEY, String(epochMs));
}
