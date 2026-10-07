"""When someone asks about a particular time ("what did you do Monday evening?", "how was
last night?"), he thinks back to that stretch of his life, not whatever comes to mind.

The rules find the time being asked about and hand his voice what he remembers of it, in
order; if nothing stands out, he says it was an ordinary one rather than making one up.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_PARTS = {
    "morning": (5, 12),
    "afternoon": (12, 18),
    "evening": (17, 24),
    "night": (18, 28),
}
_ASKED = re.compile(
    r"\b(?:(last|this|on)\s+)?(yesterday|today|tonight|weekend|"
    + "|".join(_DAYS)
    + r"|morning|afternoon|evening|night)"
    r"(?:\s+(morning|afternoon|evening|night))?\b",
    re.IGNORECASE,
)
# A question about the past, not a plan.
_PAST = re.compile(
    r"\b(did|was|were|went|had|got|how'?s|how was|what happened|up to|been)\b", re.IGNORECASE
)


def asked_about(text: str, at: datetime) -> tuple[datetime, datetime, str] | None:
    """The stretch of time a question asks about, as (start, end, how to say it)."""
    if not _PAST.search(text):
        return None
    for match in _ASKED.finditer(text):
        lead, word, part = (g.casefold() if g else "" for g in match.groups())
        today = at.replace(hour=0, minute=0, second=0, microsecond=0)
        if word in _PARTS:
            # "this morning", "last night", "this evening"
            if word == "night" and lead == "last":
                day, part = today - timedelta(days=1), "night"
            elif lead in {"this", ""} and word != "night":
                day, part = today, word
            else:
                continue
            label = f"{lead or 'this'} {word}"
        elif word == "yesterday":
            day, label = today - timedelta(days=1), "yesterday" + (f" {part}" if part else "")
        elif word in {"today", "tonight"}:
            day, label = today, word
            part = part or ("night" if word == "tonight" else "")
        elif word == "weekend":
            back = (at.weekday() - 5) % 7  # back to the latest Saturday
            if lead == "last" and back < 2:
                back += 7  # in the middle of one: "last weekend" is the one before
            saturday = today - timedelta(days=back)
            end = min(saturday + timedelta(days=2), at)
            return (saturday, end, "the weekend") if end > saturday else None
        else:
            back = (at.weekday() - _DAYS.index(word)) % 7
            if back == 0 and lead == "last":
                back = 7
            day = today - timedelta(days=back)
            label = f"{'last ' if lead == 'last' else ''}{word.title()}" + (
                f" {part}" if part else ""
            )
        start_hour, end_hour = _PARTS.get(part, (0, 24)) if part else (0, 24)
        start = day + timedelta(hours=start_hour)
        end = min(day + timedelta(hours=end_hour), at)
        if end <= start:
            continue
        return start, end, label
    return None


def _when(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def that_time(
    history: Sequence[DomainEvent], start: datetime, end: datetime, limit: int = 8
) -> list[str]:
    """What he remembers of that stretch, in order, the things that mattered first kept."""
    found: list[tuple[datetime, float, str]] = []
    seen: set[str] = set()
    for event in reversed(events_of(history, "memory.recorded")[-2000:]):
        when = _when(event)
        if when is None:
            continue
        if when < start:
            break
        p = event.payload
        text = " ".join(str(p.get("text", "")).split())
        if (
            when >= end
            or p.get("owner", "pathos") != "pathos"
            or p.get("category") == "dream"
            or not text
            or text.casefold() in seen
        ):
            continue
        seen.add(text.casefold())
        found.append((when, float(p.get("importance", 0.3) or 0.3), text))
    kept = sorted(found, key=lambda item: -item[1])[:limit]
    return [f"{when:%A %H:%M}: {text}" for when, _, text in sorted(kept)]


def recall_of_that_time(
    history: Sequence[DomainEvent], text: str, at: datetime
) -> dict[str, object] | None:
    asked = asked_about(text, at)
    if asked is None:
        return None
    start, end, label = asked
    return {"when": label, "what_he_remembers": that_time(history, start, end)}
