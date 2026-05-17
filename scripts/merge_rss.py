#!/usr/bin/env python3

import os
import re
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import feedparser
import requests
from dateutil import parser as dateparser

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ─── Config via env / vars / secrets ─────────────────────────────────────────

def parse_list(raw: str) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in re.split(r"[,\n]+", raw) if s.strip()]


RSS_FEEDS: list[str]        = parse_list(os.environ.get("RSS_FEEDS", ""))
PRIORITY_TOPICS: list[str]  = parse_list(os.environ.get("PRIORITY_TOPICS", ""))
BLACKLIST_TOPICS: list[str] = parse_list(os.environ.get("BLACKLIST_TOPICS", ""))
OUTPUT_TITLE: str           = os.environ.get("OUTPUT_TITLE", "Merged RSS Feed")
OUTPUT_DESCRIPTION: str     = os.environ.get("OUTPUT_DESCRIPTION", "Combined RSS feed")
OUTPUT_LINK: str            = os.environ.get("OUTPUT_LINK", "https://github.com")
MAX_ITEMS: int              = int(os.environ.get("MAX_ITEMS", "200"))
MAX_AGE_DAYS: int           = int(os.environ.get("MAX_AGE_DAYS", "30"))

OUTPUT_PATH = Path("docs/feed.xml")

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
RFC822 = "%a, %d %b %Y %H:%M:%S +0000"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (RSS Merger Bot; +https://github.com)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# ─── Fetch ────────────────────────────────────────────────────────────────────

def fetch_feed(url: str) -> feedparser.FeedParserDict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            log.warning("Damaged feed: %s -- %s", url, feed.bozo_exception)
            return None
        log.info("OK %s -- [%d] entries", url, len(feed.entries))
        return feed
    except Exception as exc:
        log.warning("Failed to load %s: %s", url, exc)
        return None

# ─── Deduplication ───────────────────────────────────────────────────────────

def entry_fingerprint(entry) -> str:
    guid = getattr(entry, "id", "") or getattr(entry, "link", "")
    if guid:
        return hashlib.sha1(guid.encode()).hexdigest()
    title = getattr(entry, "title", "")
    return hashlib.sha1(title.strip().lower().encode()).hexdigest()

# ─── Text extraction ─────────────────────────────────────────────────────────

def entry_text(entry) -> str:
    parts = [
        getattr(entry, "title", ""),
        getattr(entry, "cathegory", ""),
        " ".join(t.get("term", "") for t in getattr(entry, "tags", [])),
    ]
    return " ".join(parts).lower()

# ─── Blacklist ───────────────────────────────────────────────────────────────

def _word_boundary(text: str, kw: str) -> bool:
    kw_escaped = re.escape(kw.lower())
    pattern = r"(?<![^\W_])(" + kw_escaped + r")(?![^\W_])"
    return bool(re.search(pattern, text, flags=re.UNICODE))


def is_blacklisted(entry) -> tuple[bool, str]:
    text = entry_text(entry)
    for kw in BLACKLIST_TOPICS:
        if _word_boundary(text, kw):
            return True, kw
    return False, ""

# ─── Priority ────────────────────────────────────────────────────────────────

def priority_score(entry) -> int:
    text = entry_text(entry)
    return sum(1 for kw in PRIORITY_TOPICS if kw.lower() in text)

# ─── Date parsing ─────────────────────────────────────────────────────────────

def entry_datetime(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = dateparser.parse(raw)
                if dt:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
            except Exception:
                pass
    return EPOCH

# ─── XML generation ───────────────────────────────────────────────────────────

def to_rfc822(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(RFC822)


def safe(text: str | None) -> str:
    return escape(text or "")


def build_xml(items: list) -> str:
    now = to_rfc822(datetime.now(timezone.utc))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"',
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        "  <channel>",
        f"    <title>{safe(OUTPUT_TITLE)}</title>",
        f"    <link>{safe(OUTPUT_LINK)}</link>",
        f"    <description>{safe(OUTPUT_DESCRIPTION)}</description>",
        f"    <lastBuildDate>{now}</lastBuildDate>",
        f'    <atom:link href="{safe(OUTPUT_LINK)}" rel="self" type="application/rss+xml"/>',
        f"    <generator>RSS Merger / GitHub Actions</generator>",
    ]

    for entry, _ in items:
        title   = safe(getattr(entry, "title", "(no title)"))
        link    = safe(getattr(entry, "link", ""))
        guid    = safe(getattr(entry, "id", link))
        pub     = to_rfc822(entry_datetime(entry))

        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        if not content:
            content = getattr(entry, "summary", "")

        lines += [
            "    <item>",
            f"      <title>{title}</title>",
            f"      <link>{link}</link>",
            f"      <guid isPermaLink=\"false\">{guid}</guid>",
            f"      <pubDate>{pub}</pubDate>",
        ]

        if content:
            lines.append(f"      <description><![CDATA[{content}]]></description>")

        for tag in getattr(entry, "tags", []):
            term = safe(tag.get("term", ""))
            if term:
                lines.append(f"      <category>{term}</category>")

        lines.append("    </item>")

    lines += ["  </channel>", "</rss>"]
    return "\n".join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not RSS_FEEDS:
        log.error("RSS_FEEDS is empty. Add URLs to Secrets.")
        raise SystemExit(1)

    log.info("Loading %d feeds...", len(RSS_FEEDS))
    all_entries: list = []
    seen: set[str] = set()

    for url in RSS_FEEDS:
        feed = fetch_feed(url)
        if not feed:
            continue
        for entry in feed.entries:
            fp = entry_fingerprint(entry)
            if fp in seen:
                continue
            seen.add(fp)
            blocked, kw = is_blacklisted(entry)
            if blocked:
                log.info("BLOCKED [%s]: %s", kw, getattr(entry, "title", "(no title)"))
                continue
            all_entries.append(entry)

    log.info("Total unique entries after filtering: %d", len(all_entries))

    # Remove old entries
    if MAX_AGE_DAYS > 0:
        cutoff_ts = datetime.now(timezone.utc).timestamp() - MAX_AGE_DAYS * 86400
        cutoff_label = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        before = len(all_entries)
        fresh = []
        for e in all_entries:
            dt = entry_datetime(e)
            if dt == EPOCH:
                log.warning("DATE UNKNOWN, keeping: %s", getattr(e, "title", "(no title)"))
                fresh.append(e)
            elif dt.timestamp() >= cutoff_ts:
                fresh.append(e)
            else:
                log.info("OLD [%s]: %s", dt.strftime("%Y-%m-%d"), getattr(e, "title", "(no title)"))
        removed = before - len(fresh)
        all_entries = fresh
        if removed:
            log.info("Removed old entries (before %s): %d", cutoff_label, removed)
        else:
            log.info("No old entries found (cutoff %s)", cutoff_label)

    # Sort: priority first, then newest to oldest
    def sort_key(e):
        return (-priority_score(e), -entry_datetime(e).timestamp())

    all_entries.sort(key=sort_key)
    trimmed = [(e, priority_score(e)) for e in all_entries[:MAX_ITEMS]]

    prio_count = sum(1 for _, s in trimmed if s > 0)
    log.info("Priority: %d, regular: %d", prio_count, len(trimmed) - prio_count)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_xml(trimmed), encoding="utf-8")
    log.info("Written to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()