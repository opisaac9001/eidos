"""The real world's news, as reported: observations he can read, never world commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class NewsStory:
    story_id: str
    headline: str
    summary: str
    section: str
    published_at: datetime
    source_name: str
    source_url: str


class NewsSource(Protocol):
    def read(self) -> Sequence[NewsStory]: ...
