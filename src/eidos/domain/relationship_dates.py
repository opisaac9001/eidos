"""Source-linked relationship dates and their replayable anniversaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class RelationshipDate:
    person_id: str
    source_event_id: str
    milestone_event_id: str
    origin_date: str
    description: str
    anniversaries: int = 0


def interaction_person(event: DomainEvent) -> str | None:
    if event.kind == "social.activity_completed":
        value = event.payload.get("person_id")
    elif event.kind in {"phone.call_completed", "phone.callback_completed"}:
        value = event.payload.get("caller_id")
    elif event.kind == "visitor.departed":
        value = event.payload.get("visitor_id")
    elif event.kind in {"incident.shared_aftermath", "object.shared_use"}:
        value = event.payload.get("person_id")
    elif event.kind == "visit.ended":
        value = "user"
    else:
        return None
    return value if isinstance(value, str) and value not in {"", "pathos"} else None


def project_relationship_dates(history: Sequence[DomainEvent]) -> dict[str, RelationshipDate]:
    dates: dict[str, RelationshipDate] = {}
    seen: dict[str, DomainEvent] = {}
    remembered: set[tuple[str, int]] = set()
    for event in history:
        if event.kind == "relationship.milestone_recorded":
            person_id = _required(event, "person_id")
            source_id = _required(event, "source_event_id")
            source = seen.get(source_id)
            if person_id in dates:
                raise ValueError("Only the first meaningful date is retained per relationship")
            if source is None or interaction_person(source) != person_id:
                raise ValueError("Relationship date must cite shared interaction evidence")
            origin = date.fromisoformat(_required(event, "origin_date"))
            source_time = _event_time(source)
            if (
                origin != source_time.date()
                or _event_time(event) < source_time
                or event.causation_id != source.event_id
            ):
                raise ValueError("Relationship date must preserve its source date and cause")
            dates[person_id] = RelationshipDate(
                person_id,
                source_id,
                str(event.event_id),
                origin.isoformat(),
                _required(event, "description"),
            )
        elif event.kind == "relationship.anniversary_remembered":
            person_id = _required(event, "person_id")
            milestone = dates.get(person_id)
            years = event.payload.get("years")
            if (
                milestone is None
                or isinstance(years, bool)
                or not isinstance(years, int)
                or years < 1
                or (person_id, years) in remembered
                or _required(event, "milestone_event_id") != milestone.milestone_event_id
            ):
                raise ValueError("Relationship anniversary is missing or duplicated")
            observed_at = _event_time(event)
            if observed_at.date() != anniversary_date(
                date.fromisoformat(milestone.origin_date), observed_at.year
            ):
                raise ValueError("Relationship anniversary occurred on the wrong date")
            if observed_at.year - date.fromisoformat(milestone.origin_date).year != years:
                raise ValueError("Relationship anniversary year is incorrect")
            if (
                event.causation_id is None
                or str(event.causation_id) != milestone.milestone_event_id
            ):
                raise ValueError("Relationship anniversary must cite its milestone")
            remembered.add((person_id, years))
            dates[person_id] = RelationshipDate(
                milestone.person_id,
                milestone.source_event_id,
                milestone.milestone_event_id,
                milestone.origin_date,
                milestone.description,
                max(milestone.anniversaries, years),
            )
        seen[str(event.event_id)] = event
    return dates


def anniversary_date(origin: date, year: int) -> date:
    try:
        return origin.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _event_time(event: DomainEvent) -> datetime:
    value = _required(event, "simulated_at")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Relationship dates require timezone-aware evidence")
    return parsed
