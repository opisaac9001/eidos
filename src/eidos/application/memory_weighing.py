"""What he keeps is decided by how it felt and how unusual it was, not by who wrote it down.

Every part of his life records memories with an importance of its own choosing, so a dull
hour's note and a striking one fade alike. People don't keep memories that way: what was
emotionally charged, surprising, or talked about stays, and sleep does the sorting. Each
night the previous day's memories are weighed again (``memory.weighed``) from:

- **how it felt:** the appraisal of the moment it records (how good or bad, how novel);
- **how unusual:** how many much-alike memories he already has from the last month;
- **whether it stayed with him through the day:** he brooded on it, or told someone.

The adjustment is bounded, so what a system meant as a big moment stays a big one, and
the source record is never changed; recall, archiving and the believability measures
read the weighed importance.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, payload_candidates

WEIGHED = "memory.weighed"
WEIGH_HOUR = 3
_WORD = re.compile(r"[a-z']{4,}")
_PLAIN = frozenset(
    "that this with from have just still some about later today really there their "
    "they them were what when which would could should might again then than".split()
)
# How far importance may move from what the source gave it.
MOST_DOWN, MOST_UP = -0.25, 0.3


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def _words(text: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(text.casefold()) if w not in _PLAIN)


def weighed_importance(history: Sequence[DomainEvent]) -> dict[str, float]:
    """The latest weighed importance of each memory that has been weighed."""
    found: dict[str, float] = {}
    for event in events_of(history, WEIGHED):
        memory_id = event.payload.get("memory_id")
        value = event.payload.get("importance")
        if isinstance(memory_id, str) and isinstance(value, (int, float)):
            found[memory_id] = float(value)
    return found


def importance_of(event: DomainEvent, weighed: Mapping[str, float]) -> float:
    """A memory's importance as it stands: weighed if it has been, else as recorded."""
    given = weighed.get(str(event.event_id))
    if given is not None:
        return given
    return max(0.0, min(1.0, float(event.payload.get("importance", 0.5) or 0.5)))


def weigh_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """Overnight, yesterday's memories weighed by how they felt and how unusual they were."""
    if at.hour != WEIGH_HOUR:
        return []
    day = (at - timedelta(days=1)).date()
    review_id = f"memory-weighing-{day.isoformat()}"
    if any(e.payload.get("review_id") == review_id for e in events_of(history, WEIGHED)[-400:]):
        return []
    already = {str(e.payload.get("memory_id")) for e in events_of(history, WEIGHED)}
    month_ago = at - timedelta(days=31)
    recent: list[tuple[DomainEvent, frozenset[str]]] = []
    yesterday: list[DomainEvent] = []
    for memory in events_of(history, "memory.recorded")[-3000:]:
        if memory.payload.get("owner", "pathos") != "pathos":
            continue
        when = _at(memory)
        if when is None or when < month_ago:
            continue
        if memory.payload.get("category") == "dream":
            continue
        words = _words(str(memory.payload.get("text", "")))
        if (
            when.date() == day
            and str(memory.event_id) not in already
            and not str(memory.payload.get("source", "")).startswith("merged-")
        ):
            yesterday.append(memory)
        elif when.date() < day:
            recent.append((memory, words))
    if not yesterday:
        return []
    talked: set[str] = set()
    for access in events_of(history, "memory.accessed")[-600:]:
        when = _at(access)
        if (
            when is not None
            and when.date() == day
            and access.payload.get("query_source")
            in {
                "inner-stream",
                "user-conversation",
            }
        ):
            talked.add(str(access.payload.get("memory_id")))
    output: list[DomainEvent] = []
    for memory in yesterday:
        memory_id = str(memory.event_id)
        source = max(0.0, min(1.0, float(memory.payload.get("importance", 0.5) or 0.5)))
        felt = _felt(history, memory)
        words = _words(str(memory.payload.get("text", "")))
        alike = sum(
            1
            for _, theirs in recent
            if words and theirs and len(words & theirs) / len(words | theirs) >= 0.4
        )
        novel = 1.0 / (1.0 + alike)
        adjustment = 0.3 * (felt - 0.35) + 0.3 * (novel - 0.5) + (0.1 if memory_id in talked else 0)
        adjustment = max(MOST_DOWN, min(MOST_UP, adjustment))
        weighed = round(max(0.05, min(0.95, source + adjustment)), 3)
        if abs(weighed - source) < 0.05:
            continue
        output.append(
            DomainEvent(
                WEIGHED,
                "pathos",
                {
                    "review_id": review_id,
                    "memory_id": memory_id,
                    "importance": weighed,
                    "was": round(source, 3),
                    "felt": round(felt, 3),
                    "novel": round(novel, 3),
                    "talked": memory_id in talked,
                    "simulated_at": at.isoformat(),
                },
                causation_id=memory.event_id,
            )
        )
    return output


def _felt(history: Sequence[DomainEvent], memory: DomainEvent) -> float:
    """How the moment felt, from its appraisal: how good or bad, and how novel; 0 to 1."""
    source_id = memory.payload.get("source_event_id")
    candidates = payload_candidates(history, "source_event_id", source_id) if source_id else []
    for event in reversed(candidates):
        if event.kind != "appraisal.recorded" or event.payload.get("source_event_id") != source_id:
            continue
        desirability = event.payload.get("desirability")
        novelty = event.payload.get("novelty")
        strength = abs(float(desirability)) if isinstance(desirability, (int, float)) else 0.0
        surprise = float(novelty) if isinstance(novelty, (int, float)) else 0.0
        return min(1.0, strength + 0.5 * surprise)
    # No appraisal of its own: an ordinary moment.
    return 0.3
