const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  mdash: "—",
  ndash: "–",
  hellip: "…",
  lsquo: "‘",
  rsquo: "’",
  ldquo: "“",
  rdquo: "”",
};

export function htmlUnescape(text: string): string {
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, entity: string) => {
    if (entity[0] === "#") {
      const codePoint = entity[1] === "x" || entity[1] === "X"
        ? parseInt(entity.slice(2), 16)
        : parseInt(entity.slice(1), 10);
      return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : match;
    }
    return NAMED_ENTITIES[entity] ?? match;
  });
}

// Strips invisible/formatting Unicode categories that can hide payloads in
// otherwise-innocuous text (ported from rss_render.py's strip_invisible_chars).
export function stripInvisibleChars(text: string): string {
  return text.replace(/[\p{Cf}\p{Cc}\p{Co}\p{Cs}]/gu, "");
}

export function cleanText(raw: string): string {
  return stripInvisibleChars(htmlUnescape(raw)).replace(/\s+/g, " ").trim();
}

export function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

// RFC 2822 date, matching Python's email.utils.format_datetime output.
export function formatRfc2822(date: Date): string {
  return date.toUTCString().replace("GMT", "+0000");
}

export function resolveUrl(relative: string, base: string): string {
  try {
    return new URL(relative, base).toString();
  } catch {
    return relative;
  }
}
