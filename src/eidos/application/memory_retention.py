"""Replayable subjective memory archiving without deleting historical evidence.

Nightly, what has faded past reach (``accessibility_of``, with how often he's gone back to
it) is archived: out of ordinary recall, still in the record, still there to a direct cue.
Important memories, the ones that have stayed with him, and anything he's revisited lately
are kept.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.memory_curve import accessibility_of
from eidos.application.memory_weighing import importance_of, weighed_importance
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, payload_candidates

POLICY_VERSION = 2
MINIMUM_AGE = timedelta(days=14)
RECENT_ACCESS = timedelta(days=90)
MAX_ARCHIVES_PER_REVIEW = 200
REVIEW_HOUR = 3
# Below this it's out of reach: a 0.3 memory gets here in about seven weeks, a 0.5 in six
# months, a 0.7 in over two years.
FADED_BELOW = 0.05


def archived_memory_ids(history: Sequence[DomainEvent]) -> set[str]:
    return {
        str(event.payload["memory_id"])
        for event in events_of(history, "memory.archived")
        if isinstance(event.payload.get("memory_id"), str)
    }


def memory_retention_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Archive cold ordinary memories monthly; immutable source events remain untouched."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Memory retention time must be timezone-aware")
    if simulated_at.hour != REVIEW_HOUR:
        return []
    review_id = f"memory-retention-v{POLICY_VERSION}-{simulated_at:%Y-%m-%d}"
    if any(
        event.payload.get("review_id") == review_id
        for event in payload_candidates(history, "review_id", review_id)
    ):
        return []

    archived = archived_memory_ids(history)
    weighed = weighed_importance(history)
    stayed = {
        str(event.payload.get("memory_id"))
        for event in events_of(history, "memory.became_formative")
    }
    last_access: dict[str, datetime] = {}
    accesses: dict[str, int] = {}
    reminders: dict[str, int] = {}
    for event in events_of(history, "memory.accessed", "memory.reminded"):
        if not isinstance(event.payload.get("memory_id"), str):
            continue
        memory_id = str(event.payload["memory_id"])
        if event.kind == "memory.reminded":
            reminders[memory_id] = reminders.get(memory_id, 0) + 1
            continue
        accessed_at = _time(event)
        last_access[memory_id] = max(accessed_at, last_access.get(memory_id, accessed_at))
        accesses[memory_id] = accesses.get(memory_id, 0) + 1

    eligible: list[tuple[datetime, DomainEvent, int]] = []
    protected = 0
    scanned = 0
    for event in history:
        if event.kind != "memory.recorded" or event.payload.get("owner", "pathos") != "pathos":
            continue
        scanned += 1
        memory_id = str(event.event_id)
        recorded_at = _time(event)
        age = simulated_at - recorded_at
        importance = importance_of(event, weighed)
        # Going back to it lately keeps it; never having gone back to it doesn't.
        recently_accessed = (
            memory_id in last_access and simulated_at - last_access[memory_id] < RECENT_ACCESS
        )
        if memory_id in archived:
            continue
        reach = accessibility_of(
            importance, age.total_seconds() / 86400, accesses.get(memory_id, 0),
            reminders.get(memory_id, 0),
        )  # fmt: skip
        if (
            age < MINIMUM_AGE
            or importance >= 0.75
            or recently_accessed
            or memory_id in stayed
            or reach >= FADED_BELOW
        ):
            protected += 1
            continue
        eligible.append((recorded_at, event, int(age.total_seconds() // 86400)))
    eligible.sort(key=lambda item: (item[0], str(item[1].event_id)))
    selected = eligible[:MAX_ARCHIVES_PER_REVIEW]
    review = DomainEvent(
        "memory.retention_reviewed",
        "pathos",
        {
            "review_id": review_id,
            "policy_version": POLICY_VERSION,
            "scanned_count": scanned,
            "archived_count": len(selected),
            "protected_count": protected,
            "deferred_count": max(0, len(eligible) - len(selected)),
            "minimum_age_days": MINIMUM_AGE.days,
            "recent_access_days": RECENT_ACCESS.days,
            "audit_events_deleted": 0,
            "simulated_at": simulated_at.isoformat(),
        },
        correlation_id=review_id,
    )
    return [
        review,
        *(
            DomainEvent(
                "memory.archived",
                "pathos",
                {
                    "review_id": review_id,
                    "memory_id": str(memory.event_id),
                    "age_days": age_days,
                    "reason": "faded",
                    "source_retained": True,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=review.event_id,
                correlation_id=review_id,
            )
            for _, memory, age_days in selected
        ),
    ]


def _time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError("Memory event time must be timezone-aware")
        return parsed
    return event.occurred_at
