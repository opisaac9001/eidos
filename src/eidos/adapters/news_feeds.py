"""Opt-in real news from public RSS/Atom feeds (by default, the BBC's)."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Callable, Sequence
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from eidos.ports.news import NewsStory

Fetch = Callable[[Request, float], bytes]

DEFAULT_FEEDS: tuple[tuple[str, str], ...] = (
    ("top", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("uk", "https://feeds.bbci.co.uk/news/uk/rss.xml"),
    ("world", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("culture", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"),
    ("sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
)
_ATOM = "{http://www.w3.org/2005/Atom}"
_TAGS = re.compile(r"<[^>]+>")


class RssNewsAdapter:
    """Reads the latest few stories from each configured feed."""

    def __init__(
        self,
        feeds: Sequence[tuple[str, str]] = DEFAULT_FEEDS,
        *,
        per_feed: int = 6,
        timeout: float = 15,
        fetch: Fetch | None = None,
    ) -> None:
        if not feeds:
            raise ValueError("At least one news feed is needed")
        for section, url in feeds:
            parsed = urlsplit(url)
            if (
                not re.fullmatch(r"[a-z][a-z0-9_-]{0,20}", section)
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("News feeds must be named, credential-free HTTPS URLs")
        self.feeds = tuple(feeds)
        self.per_feed = per_feed
        self.timeout = timeout
        self.fetch = fetch or _fetch

    def read(self) -> list[NewsStory]:
        stories: dict[str, NewsStory] = {}
        failures = 0
        for section, url in self.feeds:
            try:
                raw = self.fetch(Request(url, headers={"User-Agent": "Eidos/0.1"}), self.timeout)
                parsed = _parse(raw, section, url)
            except Exception:
                failures += 1
                continue
            for story in parsed[: self.per_feed]:
                stories.setdefault(story.story_id, story)
        if failures == len(self.feeds):
            raise OSError("No news feed could be read")
        return list(stories.values())


def _parse(raw: bytes, section: str, feed_url: str) -> list[NewsStory]:
    root = ET.fromstring(raw)
    source_name = (
        _text(root.find("channel/title"))
        or _text(root.find(f"{_ATOM}title"))
        or (urlsplit(feed_url).hostname or "news")
    )
    output: list[NewsStory] = []
    for item in root.iter("item"):
        story = _story(
            section,
            source_name,
            _text(item.find("title")),
            _text(item.find("description")),
            _text(item.find("link")),
            _text(item.find("pubDate")),
        )
        if story is not None:
            output.append(story)
    for entry in root.iter(f"{_ATOM}entry"):
        link = entry.find(f"{_ATOM}link")
        story = _story(
            section,
            source_name,
            _text(entry.find(f"{_ATOM}title")),
            _text(entry.find(f"{_ATOM}summary")) or _text(entry.find(f"{_ATOM}content")),
            link.get("href", "") if link is not None else "",
            _text(entry.find(f"{_ATOM}updated")) or _text(entry.find(f"{_ATOM}published")),
        )
        if story is not None:
            output.append(story)
    return output


def _story(
    section: str, source_name: str, title: str, summary: str, link: str, published: str
) -> NewsStory | None:
    headline = _clean(title)[:200]
    if len(headline) < 8 or not link.startswith("https://"):
        return None
    if headline.casefold().startswith(("watch:", "listen:", "live:", "in pictures")):
        return None  # he reads the news; video and live pages aren't stories he'd take in
    return NewsStory(
        story_id=sha256(link.split("?")[0].encode()).hexdigest()[:24],
        headline=headline,
        summary=_clean(summary)[:400],
        section=section,
        published_at=_when(published),
        source_name=_clean(source_name)[:60],
        source_url=link,
    )


def _when(raw: str) -> datetime:
    raw = raw.strip()
    try:
        value = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    return value if value.utcoffset() is not None else value.replace(tzinfo=timezone.utc)


def _clean(text: str) -> str:
    return " ".join(html.unescape(_TAGS.sub(" ", text)).split())


def _text(node: ET.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def _fetch(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 (checked HTTPS above)
        data: bytes = response.read(2_000_000)
        return data
