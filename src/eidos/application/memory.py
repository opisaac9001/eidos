"""Explainable autobiographical recall over immutable source events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from eidos.domain.events import DomainEvent

WORDS = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "did",
    "do",
    "for",
    "from",
    "has",
    "have",
    "he",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "the",
    "to",
    "was",
    "we",
    "were",
    "what",
    "where",
    "with",
    "you",
    "your",
}


def terms(text: str) -> set[str]:
    return {word for word in WORDS.findall(text.lower()) if word not in STOP_WORDS}


@dataclass(frozen=True, slots=True)
class RecalledMemory:
    event: DomainEvent
    accessibility: float
    relevance: float
    score: float
    reason: str


def _simulated_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return event.occurred_at


def _metadata(event: DomainEvent) -> tuple[float, float]:
    importance = float(event.payload.get("importance", 0.5))
    confidence = float(event.payload.get("confidence", 1.0))
    return max(0.0, min(1.0, importance)), max(0.0, min(1.0, confidence))


def recall(
    history: list[DomainEvent], query: str, now: datetime, limit: int = 7
) -> list[RecalledMemory]:
    """Rank accessible Pathos memories without treating similarity as proof."""
    if now.utcoffset() is None or not 1 <= limit <= 1000:
        raise ValueError("Recall needs an aware time and a limit from 1–1000")
    query_terms = terms(query)
    accesses: dict[str, int] = {}
    for event in history:
        if event.kind == "memory.accessed":
            memory_id = str(event.payload["memory_id"])
            accesses[memory_id] = accesses.get(memory_id, 0) + 1
    ranked = []
    for event in history:
        if event.kind != "memory.recorded" or event.payload.get("owner", "pathos") != "pathos":
            continue
        importance, confidence = _metadata(event)
        age_days = max(0.0, (now - _simulated_time(event)).total_seconds() / 86400)
        half_life = 2.0 + 28.0 * importance
        base_access = 0.5 ** (age_days / half_life)
        rehearsals = min(5, accesses.get(str(event.event_id), 0))
        accessibility = min(1.0, base_access + rehearsals * 0.04)
        memory_terms = terms(str(event.payload["text"]))
        overlap = len(query_terms & memory_terms)
        relevance = overlap / max(1, len(query_terms))
        score = 0.42 * relevance + 0.28 * accessibility + 0.2 * importance + 0.1 * confidence
        reasons = []
        if overlap:
            reasons.append(f"{overlap} cue term{'s' if overlap != 1 else ''}")
        if importance >= 0.7:
            reasons.append("important")
        if age_days < 1:
            reasons.append("recent")
        if rehearsals:
            reasons.append(f"recalled {rehearsals}×")
        ranked.append(
            RecalledMemory(
                event,
                round(accessibility, 4),
                round(relevance, 4),
                round(score, 4),
                ", ".join(reasons) or "background accessibility",
            )
        )
    ranked.sort(
        key=lambda item: (item.score, _simulated_time(item.event), str(item.event.event_id)),
        reverse=True,
    )
    return ranked[:limit]


def memory_view(history: list[DomainEvent], now: datetime) -> list[dict[str, Any]]:
    """Return every memory with current accessibility, without rehearsing it."""
    ranked = recall(
        history,
        "",
        now,
        limit=min(1000, max(1, sum(e.kind == "memory.recorded" for e in history))),
    )
    by_id = {str(item.event.event_id): item for item in ranked}
    views = []
    for event in history:
        if event.kind != "memory.recorded":
            continue
        item = by_id.get(str(event.event_id))
        if item is None:
            item = recall([event], "", now, 1)[0]
        views.append(
            {
                **dict(event.payload),
                "id": str(event.event_id),
                "kind": event.kind,
                "accessibility": item.accessibility,
                "recall_score": item.score,
            }
        )
    return views
