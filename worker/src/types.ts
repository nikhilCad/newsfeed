export interface Env {
  NEWSFEED_KV: KVNamespace;
  SOURCE_URL: string;
  CACHE_SECONDS: string;
  REDDIT_CYCLE_HOURS: string;
  ENGBLOGS_REFRESH_HOURS: string;
}

export interface Feed {
  name: string;
  url: string;
}

export interface FeedCategory {
  key: string;
  title: string;
  feeds: Feed[];
}

export interface FeedsConfig {
  categories: FeedCategory[];
}

export interface RedditItem {
  title: string;
  link: string;
  author: string;
  published: string;
  thumbnail: string;
  selftext: string;
}

export interface RedditFeedEntry {
  source_url: string;
  fetched_at: string;
  items: RedditItem[];
}

export interface RedditCategoryData {
  category: string;
  feeds: Record<string, RedditFeedEntry>;
}

export interface BlogItem {
  title: string;
  link: string;
  source_name: string;
  source_url: string;
  published: string;
}

export interface EngblogsData {
  source_url: string;
  fetched_at: string;
  items: BlogItem[];
}
