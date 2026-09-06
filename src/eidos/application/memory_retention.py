"""Replayable subjective memory archiving without deleting historical evidence."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent

POLICY_VERSION = 1
MINIMUM_AGE = timedelta(days=180)
RECENT_ACCESS = timedelta(days=90)
MAX_ARCHIVES_PER_REVIEW = 200


def archived_memory_ids(history: Sequence[DomainEvent]) -> set[str]:
    return {
        str(event.payload["memory_id"])
        for event in history
        if event.kind == "memory.archived" and isinstance(event.payload.get("memory_id"), str)
    }


def memory_retention_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Archive cold ordinary memories monthly; immutable source events remain untouched."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Memory retention time must be timezone-aware")
    if simulated_at.day != 1 or simulated_at.hour != 1:
        return []
    review_id = f"memory-retention-v{POLICY_VERSION}-{simulated_at:%Y-%m}"
    if any(event.payload.get("review_id") == review_id for event in history):
        return []

    archived = archived_memory_ids(history)
    last_access: dict[str, datetime] = {}
    for event in history:
        if event.kind != "memory.accessed" or not isinstance(event.payload.get("memory_id"), str):
            continue
        accessed_at = _time(event)
        memory_id = str(event.payload["memory_id"])
        last_access[memory_id] = max(accessed_at, last_access.get(memory_id, accessed_at))

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
        importance = float(event.payload.get("importance", 0.5))
        recently_accessed = simulated_at - last_access.get(memory_id, recorded_at) < RECENT_ACCESS
        if memory_id in archived:
            continue
        if age < MINIMUM_AGE or importance >= 0.75 or recently_accessed:
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
                    "reason": "cold_ordinary_memory",
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
