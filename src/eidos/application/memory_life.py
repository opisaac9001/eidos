"""Memories that behave like memories: kept alive by brooding, routine run together, and
the ones he keeps going back to becoming part of him.

Three things people's memories do that a list of records doesn't. What you keep coming back
to stays vivid (Generative Agents measured recency from the last time a memory was
retrieved, not when it happened): a passing thought that touches a memory counts as
revisiting it. Routine runs together: the separate notes of yesterday's shift merge into
one memory overnight, so the moments that stood out aren't buried (Lyfe Agents' summarise
and forget); the originals are archived, never deleted. And what you go back to again and
again starts to shape you (Dwarf Fortress): such a memory is marked as one that's stayed
with him, and his sense of himself draws on it.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

FORMATIVE = "memory.became_formative"
_WORD = re.compile(r"[a-z']+")
_PLAIN = frozenset(
    "that this with from have just been they them then there what when where about would "
    "could should into over some your were really still today again bit lot".split()
)
_ROUTINE = re.compile(
    r"^(?:made a start: |still at it: |done: |headed out for this: |started the planned activity: |"
    r"stayed with the planned activity: |i completed the planned \w+: )(.+?)\.?$",
    re.IGNORECASE,
)
MERGE_HOUR = 3


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.casefold()) if len(w) >= 4 and w not in _PLAIN}


def _names(text: str) -> set[str]:
    return {w for w in re.findall(r"\b[A-Z][a-z]+\b", text)} - {"I", "The", "A"}


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def _his(history: Sequence[DomainEvent], limit: int = 400) -> list[DomainEvent]:
    archived = {
        str(e.payload.get("memory_id")) for e in events_of(history, "memory.archived")[-2000:]
    }
    return [
        e
        for e in events_of(history, "memory.recorded")[-limit:]
        if e.payload.get("owner", "pathos") == "pathos"
        and e.payload.get("category") != "dream"
        and str(e.event_id) not in archived
    ]


def brooded_access(history: Sequence[DomainEvent], thought: str, at: datetime) -> list[DomainEvent]:
    """The memory a kept passing thought went back to, if it plainly went back to one."""
    words, names = _words(thought), _names(thought)
    best: tuple[int, DomainEvent] | None = None
    for memory in _his(history, 300):
        text = str(memory.payload.get("text", ""))
        if _ROUTINE.match(text):
            continue
        shared = len(words & _words(text)) + 2 * len(names & _names(text))
        if shared >= 3 and (best is None or shared > best[0]):
            best = (shared, memory)
    if best is None:
        return []
    return [
        DomainEvent(
            "memory.accessed",
            "pathos",
            {
                "memory_id": str(best[1].event_id),
                "simulated_at": at.isoformat(),
                "reason": "came back to it in a passing thought",
                "query_source": "inner-stream",
            },
        )
    ]


def routine_merge_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """Overnight, yesterday's routine notes about the same thing become one memory."""
    if at.hour != MERGE_HOUR:
        return []
    day = (at - timedelta(days=1)).date()
    review_id = f"routine-merge-{day.isoformat()}"
    if any(
        e.payload.get("review_id") == review_id
        for e in events_of(history, "memory.archived")[-400:]
    ):
        return []
    groups: dict[str, list[DomainEvent]] = {}
    for memory in _his(history, 600):
        when = _at(memory)
        match = _ROUTINE.match(str(memory.payload.get("text", "")).split(". ")[0] + ".")
        if when is None or when.date() != day or match is None:
            continue
        groups.setdefault(match.group(1).strip().rstrip("."), []).append(memory)
    output: list[DomainEvent] = []
    for title, memories in groups.items():
        if len(memories) < 2:
            continue
        importance = max(float(m.payload.get("importance", 0.3) or 0.3) for m in memories)
        merged = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"{day:%A}: {title}. The usual, more or less.",
                "simulated_at": at.isoformat(),
                "about_day": day.isoformat(),
                "category": "experience",
                "source": "merged-routine",
                "source_event_id": str(memories[0].event_id),
                "owner": "pathos",
                "importance": round(importance, 2),
                "confidence": 1.0,
            },
            causation_id=memories[0].event_id,
        )
        output.append(merged)
        output.extend(
            DomainEvent(
                "memory.archived",
                "pathos",
                {
                    "review_id": review_id,
                    "memory_id": str(memory.event_id),
                    "age_days": 1,
                    "reason": "merged_into_routine",
                    "merged_into": str(merged.event_id),
                    "source_retained": True,
                    "simulated_at": at.isoformat(),
                },
                causation_id=merged.event_id,
            )
            for memory in memories
        )
    return output


def formative_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """A memory he's gone back to again and again in the last month has stayed with him."""
    if at.hour != MERGE_HOUR:
        return []
    already = {str(e.payload.get("memory_id")) for e in events_of(history, FORMATIVE)}
    counts: dict[str, int] = {}
    for access in events_of(history, "memory.accessed")[-3000:]:
        when = _at(access)
        if when is not None and at - when <= timedelta(days=30):
            memory_id = str(access.payload.get("memory_id"))
            counts[memory_id] = counts.get(memory_id, 0) + 1
    memories = {str(m.event_id): m for m in _his(history, 2000)}
    output: list[DomainEvent] = []
    for memory_id, count in sorted(counts.items(), key=lambda item: -item[1]):
        memory = memories.get(memory_id)
        if memory is None or memory_id in already or count < 5:
            continue
        if float(memory.payload.get("importance", 0.3) or 0.3) < 0.5:
            continue
        output.append(
            DomainEvent(
                FORMATIVE,
                "pathos",
                {
                    "memory_id": memory_id,
                    "text": str(memory.payload.get("text", "")),
                    "times_revisited": count,
                    "simulated_at": at.isoformat(),
                },
                causation_id=memory.event_id,
            )
        )
        if len(output) >= 1:
            break  # one a night at most: this is slow change
    return output


def stayed_with_me(history: Sequence[DomainEvent], limit: int = 3) -> list[str]:
    return [str(e.payload.get("text")) for e in events_of(history, FORMATIVE)[-limit:]]
