#!/usr/bin/env python3
"""
RSS Feed Merger
Аб'ядноўвае некалькі RSS-стужак у адну з прыярытэтнымі тэмамі і чорным спісам.
"""

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

# ─── Канфігурацыя праз env / secrets ────────────────────────────────────────

def parse_list(raw: str) -> list[str]:
    """Разбірае радок праз коску або новы радок у спіс."""
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

OUTPUT_PATH = Path("docs/feed.xml")

# ─── Загрузка і разбор ──────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (RSS Merger Bot; +https://github.com)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_feed(url: str) -> feedparser.FeedParserDict | None:
    """Загружае і разбірае адзін RSS-фід."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            log.warning("Пашкоджаны фід: %s — %s", url, feed.bozo_exception)
            return None
        log.info("✓ %s — %d запісаў", url, len(feed.entries))
        return feed
    except Exception as exc:
        log.warning("Памылка загрузкі %s: %s", url, exc)
        return None


# ─── Дублікаты ──────────────────────────────────────────────────────────────

def entry_fingerprint(entry) -> str:
    """Унікальны адбітак запісу для выяўлення дублікатаў."""
    # Спачатку спрабуем GUID/link, потым хэш загалоўка
    guid = getattr(entry, "id", "") or getattr(entry, "link", "")
    if guid:
        return hashlib.sha1(guid.encode()).hexdigest()
    title = getattr(entry, "title", "")
    return hashlib.sha1(title.strip().lower().encode()).hexdigest()


# ─── Фільтрацыя ─────────────────────────────────────────────────────────────

def entry_text(entry) -> str:
    """Усе тэкставыя палі запісу для пошуку ключавых слоў."""
    parts = [
        getattr(entry, "title", ""),
        getattr(entry, "cathegory", ""),
        " ".join(t.get("term", "") for t in getattr(entry, "tags", [])),
    ]
    return " ".join(parts).lower()


def is_blacklisted(entry) -> bool:
    text = entry_text(entry)
    return any(kw.lower() in text for kw in BLACKLIST_TOPICS)


def priority_score(entry) -> int:
    """0 = звычайны; >0 = прыярытэтны (колькасць супадзенняў)."""
    text = entry_text(entry)
    return sum(1 for kw in PRIORITY_TOPICS if kw.lower() in text)


# ─── Час запісу ─────────────────────────────────────────────────────────────

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def entry_datetime(entry) -> datetime:
    """Вяртае усведамляльны datetime запісу або эпоху."""
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = dateparser.parse(raw)
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt:
                    return dt
            except Exception:
                pass
    # Спрабуем структуры _parsed
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return EPOCH


# ─── Генерацыя XML ──────────────────────────────────────────────────────────

RFC822 = "%a, %d %b %Y %H:%M:%S +0000"


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
        title   = safe(getattr(entry, "title", "(без назвы)"))
        link    = safe(getattr(entry, "link", ""))
        guid    = safe(getattr(entry, "id", link))
        pub     = to_rfc822(entry_datetime(entry))

        # Апісанне: аддаём перавагу content:encoded → summary → ""
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
            lines.append(
                f"      <description><![CDATA[{content}]]></description>"
            )

        # Тэгі
        for tag in getattr(entry, "tags", []):
            term = safe(tag.get("term", ""))
            if term:
                lines.append(f"      <category>{term}</category>")

        lines.append("    </item>")

    lines += ["  </channel>", "</rss>"]
    return "\n".join(lines)


# ─── Галоўная логіка ─────────────────────────────────────────────────────────

def main():
    if not RSS_FEEDS:
        log.error("Зменная RSS_FEEDS пустая. Дадайце URL у Secrets.")
        raise SystemExit(1)

    log.info("Загрузка %d фідаў…", len(RSS_FEEDS))
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
            if is_blacklisted(entry):
                log.debug("Заблакавана: %s", getattr(entry, "title", ""))
                continue
            all_entries.append(entry)

    log.info("Усяго унікальных запісаў пасля фільтрацыі: %d", len(all_entries))

    # Сартыроўка: прыярытэтныя ўверх, потым па часе (ад новых да старых)
    def sort_key(e):
        prio = priority_score(e)
        dt   = entry_datetime(e)
        return (-prio, -dt.timestamp())

    all_entries.sort(key=sort_key)
    trimmed = [(e, priority_score(e)) for e in all_entries[:MAX_ITEMS]]

    # Лічым прыярытэтных
    prio_count = sum(1 for _, s in trimmed if s > 0)
    log.info("Прыярытэтных: %d, звычайных: %d", prio_count, len(trimmed) - prio_count)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    xml = build_xml(trimmed)
    OUTPUT_PATH.write_text(xml, encoding="utf-8")
    log.info("✓ Запісана ў %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()

