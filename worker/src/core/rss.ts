import type { RedditCategoryData, EngblogsData } from "./types";
import { escapeXml, formatRfc2822 } from "./util";

function parseIsoOrFallback(value: string, fallback: Date): Date {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed;
}

export function buildRedditRss(data: RedditCategoryData): string {
  const now = new Date();
  const categoryTitle = data.category || "Reddit";

  const allItems: { feedName: string; sourceUrl: string; item: RedditCategoryData["feeds"][string]["items"][number] }[] = [];
  for (const [feedName, feed] of Object.entries(data.feeds ?? {})) {
    for (const item of feed.items) {
      allItems.push({ feedName, sourceUrl: feed.source_url ?? "", item });
    }
  }
  allItems.sort(
    (a, b) =>
      parseIsoOrFallback(b.item.published, now).getTime() -
      parseIsoOrFallback(a.item.published, now).getTime(),
  );

  const itemsXml = allItems.map(({ feedName, sourceUrl, item }) => {
    const title = `${feedName} - ${item.title ?? ""}`;
    const link = item.link ?? "";
    const pubDate = parseIsoOrFallback(item.published, now);
    const thumbnail = item.thumbnail ?? "";
    const selftext = item.selftext ?? "";

    const descriptionParts: string[] = [];
    if (thumbnail) descriptionParts.push(`<img src="${thumbnail}" />`);
    if (selftext) descriptionParts.push(selftext);
    const descriptionXml = descriptionParts.length
      ? `      <description>${escapeXml(descriptionParts.join(""))}</description>\n`
      : "";
    const thumbnailXml = thumbnail ? `      <media:thumbnail url="${escapeXml(thumbnail)}" />\n` : "";

    return (
      "    <item>\n" +
      `      <title>${escapeXml(title)}</title>\n` +
      `      <link>${escapeXml(link)}</link>\n` +
      `      <guid isPermaLink="true">${escapeXml(link)}</guid>\n` +
      `      <pubDate>${formatRfc2822(pubDate)}</pubDate>\n` +
      descriptionXml +
      thumbnailXml +
      `      <source url="${escapeXml(sourceUrl)}">${escapeXml(feedName)}</source>\n` +
      `      <category>${escapeXml(feedName)}</category>\n` +
      "    </item>"
    );
  });

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>${escapeXml(categoryTitle)}</title>
    <link>https://github.com/</link>
    <description>Reddit feeds refreshed by a Cloudflare Worker cron trigger.</description>
    <lastBuildDate>${formatRfc2822(now)}</lastBuildDate>
    <generator>newsfeed-worker</generator>
${itemsXml.join("\n")}
  </channel>
</rss>
`;
}

export function buildEngblogsRss(data: EngblogsData): string {
  const now = new Date();
  const sourceUrl = data.source_url || "";

  const itemsXml = (data.items ?? []).map((item) => {
    const pubDate = parseIsoOrFallback(item.published, now);
    const guid = escapeXml(item.link ?? "");
    const displayTitle = `${item.source_name || "Unknown source"} - ${item.title ?? ""}`;
    return (
      "    <item>\n" +
      `      <title>${escapeXml(displayTitle)}</title>\n` +
      `      <link>${guid}</link>\n` +
      `      <guid isPermaLink="true">${guid}</guid>\n` +
      `      <pubDate>${formatRfc2822(pubDate)}</pubDate>\n` +
      `      <source url="${escapeXml(item.source_url ?? "")}">${escapeXml(item.source_name ?? "")}</source>\n` +
      `      <category>${escapeXml(item.source_name ?? "")}</category>\n` +
      "    </item>"
    );
  });

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Engineering Blogs</title>
    <link>${escapeXml(sourceUrl)}</link>
    <description>RSS feed generated from the Engineering Blogs aggregator page.</description>
    <lastBuildDate>${formatRfc2822(now)}</lastBuildDate>
    <generator>newsfeed-worker</generator>
${itemsXml.join("\n")}
  </channel>
</rss>
`;
}
