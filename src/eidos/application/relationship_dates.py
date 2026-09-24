"""Record meaningful first dates and remember their annual recurrence."""

from __future__ import annotations

from datetime import date, datetime
from typing import Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.relationship_dates import (
    INTERACTION_KINDS,
    anniversary_date,
    interaction_person,
    project_relationship_dates,
)


def relationship_date_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    if simulated_at.utcoffset() is None:
        raise ValueError("Relationship date review must be timezone-aware")
    output: list[DomainEvent] = []
    state = project_relationship_dates(history)
    # interaction_person is None for every other kind.
    for source in events_of(history, *INTERACTION_KINDS):
        person_id = interaction_person(source)
        if person_id is None or person_id in state:
            continue
        try:
            source_time = _event_time(source)
        except (TypeError, ValueError):
            # Older imported worlds can contain interactions from before simulated
            # timestamps were required. They remain valid history, but cannot safely
            # establish a calendar date.
            continue
        description = (
            "the first completed visit with the user"
            if person_id == "user"
            else f"the first recorded meaningful time shared with {person_id}"
        )
        milestone = DomainEvent(
            "relationship.milestone_recorded",
            "pathos",
            {
                "person_id": person_id,
                "source_event_id": str(source.event_id),
                "origin_date": source_time.date().isoformat(),
                "description": description,
                "simulated_at": simulated_at.isoformat(),
                "owner": "pathos",
                "visibility": "private",
            },
            causation_id=source.event_id,
            correlation_id=f"relationship-date-{person_id}",
        )
        output.append(milestone)
        state = project_relationship_dates([*history, *output])
    if simulated_at.hour != 8:
        return output
    remembered = {
        (str(event.payload.get("person_id")), event.payload.get("years"))
        for event in events_of(history, "relationship.anniversary_remembered")
    }
    for person_id, relationship_date in state.items():
        origin = date.fromisoformat(relationship_date.origin_date)
        years = simulated_at.year - origin.year
        if (
            years < 1
            or anniversary_date(origin, simulated_at.year) != simulated_at.date()
            or (person_id, years) in remembered
        ):
            continue
        anniversary = DomainEvent(
            "relationship.anniversary_remembered",
            "pathos",
            {
                "person_id": person_id,
                "milestone_event_id": relationship_date.milestone_event_id,
                "years": years,
                "description": relationship_date.description,
                "simulated_at": simulated_at.isoformat(),
                "owner": "pathos",
                "visibility": "private",
            },
            causation_id=_uuid(relationship_date.milestone_event_id),
            correlation_id=f"relationship-date-{person_id}",
        )
        label = "you" if person_id == "user" else person_id
        memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"A year marker returned: {years} year{'s' if years != 1 else ''} since meaningful time with {label}.",
                "owner": "pathos",
                "category": "relationship-date",
                "source": "calendar-recurrence",
                "source_event_id": str(anniversary.event_id),
                "person_id": person_id,
                "importance": 0.72,
                "confidence": 1.0,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=anniversary.event_id,
            correlation_id=anniversary.correlation_id,
        )
        output.extend((anniversary, memory))
    return output


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Relationship interaction requires simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Relationship interaction time must be timezone-aware")
    return parsed


def _uuid(value: str) -> UUID:
    return UUID(value)
