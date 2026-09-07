"""Slowly form fallible general expectations from repeated lived episodes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.recollections import project_recollections
from eidos.domain.semantic_memory import expectation_confidence, project_semantic_expectations


def semantic_expectation_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    if at.utcoffset() is None:
        raise ValueError("Semantic expectation time must be timezone-aware")
    if at.hour != 0:
        return []
    recollections = project_recollections(history).latest
    current = project_semantic_expectations(history).expectations
    grouped: dict[tuple[str, str], dict[str, tuple[DomainEvent, datetime, float]]] = defaultdict(
        dict
    )
    for event in history:
        if (
            event.kind != "memory.recorded"
            or event.payload.get("owner", "pathos") != "pathos"
            or event.payload.get("category") == "dream"
        ):
            continue
        memory_id = str(event.event_id)
        recollection = recollections.get(memory_id)
        person_id = (
            recollection.remembered_person_id
            if recollection is not None and recollection.remembered_person_id is not None
            else _string(event, "person_id")
        )
        location_id = (
            recollection.remembered_location_id
            if recollection is not None and recollection.remembered_location_id is not None
            else _string(event, "location_id")
        )
        remembered_at = (
            recollection.remembered_at
            if recollection is not None and recollection.remembered_at is not None
            else _event_time(event)
        )
        if person_id is None or location_id is None or remembered_at > at:
            continue
        confidence = recollection.confidence if recollection is not None else _confidence(event)
        day = remembered_at.date().isoformat()
        previous = grouped[(person_id, location_id)].get(day)
        if previous is None or confidence > previous[2]:
            grouped[(person_id, location_id)][day] = (event, remembered_at, confidence)

    by_person: dict[str, list[tuple[str, list[tuple[DomainEvent, datetime, float]]]]] = defaultdict(
        list
    )
    for (person_id, location_id), by_day in grouped.items():
        values = sorted(by_day.values(), key=lambda item: (item[1], str(item[0].event_id)))
        if len(values) >= 3:
            by_person[person_id].append((location_id, values))

    candidates = []
    for person_id, locations in by_person.items():
        location_id, values = max(
            locations,
            key=lambda item: (len(item[1]), sum(source[2] for source in item[1]), item[0]),
        )
        candidates.append((person_id, location_id, values))
    candidates.sort(key=lambda item: (-len(item[2]), item[0], item[1]))

    for person_id, location_id, all_sources in candidates:
        sources = all_sources[-8:]
        expectation_id = f"pathos-person-usually-at:{person_id}"
        prior = current.get(expectation_id)
        source_ids = tuple(str(item[0].event_id) for item in sources)
        if prior is not None and prior.source_memory_ids == source_ids:
            continue
        if prior is not None and at - prior.updated_at < timedelta(days=7):
            continue
        revision = prior.revision + 1 if prior is not None else 1
        kind = (
            "semantic.expectation_formed"
            if prior is None
            else "semantic.expectation_reinforced"
            if prior.object_value == location_id
            else "semantic.expectation_revised"
        )
        confidence = expectation_confidence([item[2] for item in sources], len(sources))
        return [
            DomainEvent(
                kind,
                "pathos",
                {
                    "expectation_id": expectation_id,
                    "revision": revision,
                    "subject_id": person_id,
                    "predicate": "usually_at",
                    "object_value": location_id,
                    "confidence": confidence,
                    "source_memory_ids": ",".join(source_ids),
                    "source_count": len(source_ids),
                    "distinct_days": len(sources),
                    "epistemic_status": "subjective_generalization",
                    "text": (
                        f"I expect {person_id} is usually at {location_id}, based on "
                        f"a pattern across {len(sources)} remembered days."
                    ),
                    "simulated_at": at.isoformat(),
                },
                correlation_id=expectation_id,
            )
        ]
    return []


def _string(event: DomainEvent, key: str) -> str | None:
    value = event.payload.get(key)
    return value if isinstance(value, str) and value else None


def _confidence(event: DomainEvent) -> float:
    value = event.payload.get("confidence", 1.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return event.occurred_at
