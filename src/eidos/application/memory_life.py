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

from eidos.application.memory_weighing import importance_of, weighed_importance
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


# The notes that carry stock texture; "Done: ..." is kept, it says what he got done.
_TEXTURED = re.compile(
    r"^(?:made a start: |still at it: |headed out for this: |started the planned activity: |"
    r"stayed with the planned activity: |set out for the planned activity: )",
    re.IGNORECASE,
)


def is_routine_note(text: str) -> bool:
    """A routine note with stock texture ("Made a start: ...", "Still at it: ..."), not a
    moment that stood out."""
    return bool(_TEXTURED.match(text.strip()))


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


_NOT_A_MOMENT = re.compile(
    r"^(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day: |lately, most days|i texted |"
    r"i rang |said in the group chat)|\btexted back: |\bon the phone: |\bsaid: [“\"]",
    re.IGNORECASE,
)


def is_a_moment(memory: DomainEvent) -> bool:
    """Something that happened to him, not a day's summary, a gist, a text or a line someone
    said: those are gone over often (every cue brings them back) without having marked him."""
    text = str(memory.payload.get("text", ""))
    source = str(memory.payload.get("source") or "")
    if source in {"merged-gist", "day-summary", "lived-phone"}:
        return False
    return not (is_routine_note(text) or _NOT_A_MOMENT.search(text))


def formative_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """A memory he's gone back to on day after day in the last month has stayed with him.

    Gone back to on different days: a Tuesday's summary his stream cued seventeen times
    one evening hasn't. And a moment, weighed by how it felt: not a text or a quoted line.
    """
    if at.hour != MERGE_HOUR:
        return []
    already = {str(e.payload.get("memory_id")) for e in events_of(history, FORMATIVE)}
    counts: dict[str, int] = {}
    days: dict[str, set[str]] = {}
    for access in events_of(history, "memory.accessed")[-3000:]:
        when = _at(access)
        if when is not None and at - when <= timedelta(days=30):
            memory_id = str(access.payload.get("memory_id"))
            counts[memory_id] = counts.get(memory_id, 0) + 1
            days.setdefault(memory_id, set()).add(when.date().isoformat())
    memories = {str(m.event_id): m for m in _his(history, 2000)}
    weighed = weighed_importance(history)
    output: list[DomainEvent] = []
    for memory_id, count in sorted(counts.items(), key=lambda item: -item[1]):
        memory = memories.get(memory_id)
        if memory is None or memory_id in already or count < 5:
            continue
        if len(days.get(memory_id, ())) < 4 or not is_a_moment(memory):
            continue
        if importance_of(memory, weighed) < 0.55:
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


def gist_merge_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """Overnight, a fortnight of the same ordinary thing becomes one memory of it.

    Six separate "sat in Juniper with a coffee" moments aren't six memories to anyone a
    month on; they're "been in Juniper most mornings lately". The gist is kept as a memory
    of its own (the most recent one's importance), the originals archived, never deleted.
    """
    if at.hour != MERGE_HOUR:
        return []
    review_id = f"gist-merge-{at.date().isoformat()}"
    if any(
        e.payload.get("review_id") == review_id
        for e in events_of(history, "memory.archived")[-600:]
    ):
        return []
    stayed = {str(e.payload.get("memory_id")) for e in events_of(history, FORMATIVE)}
    weighed = weighed_importance(history)
    accessed: set[str] = set()
    for access in events_of(history, "memory.accessed")[-2000:]:
        when = _at(access)
        if when is not None and at - when <= timedelta(days=14):
            accessed.add(str(access.payload.get("memory_id")))
    groups: dict[str, list[DomainEvent]] = {}
    for memory in _his(history, 1500):
        when = _at(memory)
        if when is None or not timedelta(days=2) <= at - when <= timedelta(days=14):
            continue
        memory_id = str(memory.event_id)
        if memory_id in stayed or memory_id in accessed:
            continue
        if importance_of(memory, weighed) >= 0.7:
            continue
        if memory.payload.get("source") in {"merged-routine", "merged-gist"}:
            continue
        gist = _gist_of(str(memory.payload.get("text", "")))
        if gist:
            groups.setdefault(gist, []).append(memory)
    output: list[DomainEvent] = []
    for gist, memories in sorted(groups.items()):
        if len(memories) < 4:
            continue
        latest = max(memories, key=lambda m: str(m.payload.get("simulated_at", "")))
        importance = max(float(m.payload.get("importance", 0.3) or 0.3) for m in memories)
        merged = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"Lately, most days: {gist}. It's run together a bit.",
                "simulated_at": at.isoformat(),
                "category": "experience",
                "source": "merged-gist",
                "source_event_id": str(latest.event_id),
                "owner": "pathos",
                "importance": round(importance, 2),
                "confidence": 0.9,
                **(
                    {"location_id": str(latest.payload["location_id"])}
                    if isinstance(latest.payload.get("location_id"), str)
                    else {}
                ),
            },
            causation_id=latest.event_id,
        )
        output.append(merged)
        output.extend(
            DomainEvent(
                "memory.archived",
                "pathos",
                {
                    "review_id": review_id,
                    "memory_id": str(memory.event_id),
                    "age_days": max(0, (at - (_at(memory) or at)).days),
                    "reason": "merged_into_gist",
                    "merged_into": str(merged.event_id),
                    "source_retained": True,
                    "simulated_at": at.isoformat(),
                },
                causation_id=merged.event_id,
            )
            for memory in memories
        )
        if len(output) >= 40:
            break  # a few a night; this is tidying, not a purge
    return output


def _gist_of(text: str) -> str:
    """The first clause, plain and lower-cased: what the memory is of."""
    first = re.split(r"[.!?;:]", text, maxsplit=1)[0].strip()
    first = re.sub(r"^(?:made a start:|done:|i remember)\s*", "", first, flags=re.IGNORECASE)
    first = re.sub(r"\s+", " ", first).strip(" ,").casefold()
    words = first.split()
    if not 3 <= len(words) <= 14:
        return ""
    return first
