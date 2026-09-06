"""Replayable repair arcs that never infer another person's forgiveness."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.relationship_dates import interaction_person


@dataclass(frozen=True, slots=True)
class RelationshipRepair:
    repair_id: str
    person_id: str
    rupture_event_id: str
    apology_event_id: str
    topic_id: str
    status: str
    contact_count: int
    opened_at: str
    last_contact_at: str | None = None
    last_contact_source_id: str | None = None


def project_relationship_repairs(
    history: Sequence[DomainEvent],
) -> dict[str, RelationshipRepair]:
    repairs: dict[str, RelationshipRepair] = {}
    seen: dict[str, DomainEvent] = {}
    used_contacts: set[str] = set()
    for event in history:
        if event.kind == "relationship.repair_opened":
            repair_id = _required(event, "repair_id")
            person_id = _required(event, "person_id")
            rupture_id = _required(event, "rupture_event_id")
            apology_id = _required(event, "apology_event_id")
            topic_id = _required(event, "topic_id")
            rupture = seen.get(rupture_id)
            apology = seen.get(apology_id)
            if (
                repair_id in repairs
                or rupture is None
                or apology is None
                or rupture.kind != "disagreement.expressed"
                or apology.kind != "apology.offered"
                or apology.payload.get("actor_id") != "pathos"
                or rupture.payload.get("actor_id") != "pathos"
                or apology.payload.get("target_id") != person_id
                or rupture.payload.get("target_id") != person_id
                or apology.payload.get("topic_id") != topic_id
                or rupture.payload.get("topic_id") != topic_id
                or event.causation_id != apology.event_id
                or _event_time(event) < _event_time(apology)
            ):
                raise ValueError("Relationship repair must cite a matching rupture and apology")
            repairs[repair_id] = RelationshipRepair(
                repair_id,
                person_id,
                rupture_id,
                apology_id,
                topic_id,
                "open",
                0,
                _event_time(event).isoformat(),
            )
        elif event.kind == "relationship.repair_contacted":
            repair_id = _required(event, "repair_id")
            person_id = _required(event, "person_id")
            source_id = _required(event, "source_event_id")
            current = repairs.get(repair_id)
            source = seen.get(source_id)
            contact_number = event.payload.get("contact_number")
            if (
                current is None
                or person_id != current.person_id
                or source is None
                or interaction_person(source) != current.person_id
                or source_id in used_contacts
                or isinstance(contact_number, bool)
                or not isinstance(contact_number, int)
                or contact_number != current.contact_count + 1
                or contact_number > 3
                or _event_time(source) <= _event_time(seen[current.apology_event_id])
                or _event_time(event) < _event_time(source)
                or event.causation_id != source.event_id
            ):
                raise ValueError("Repair contact must cite later direct contact in order")
            repairs[repair_id] = replace(
                current,
                status="improving",
                contact_count=contact_number,
                last_contact_at=_event_time(source).isoformat(),
                last_contact_source_id=source_id,
            )
            used_contacts.add(source_id)
        elif event.kind == "relationship.repair_became_dormant":
            repair_id = _required(event, "repair_id")
            person_id = _required(event, "person_id")
            current = repairs.get(repair_id)
            if current is None or person_id != current.person_id:
                raise ValueError("Unknown relationship repair")
            inactivity_source = current.last_contact_at or current.opened_at
            cause_id = current.last_contact_source_id or current.apology_event_id
            expected_cause = next(
                source.event_id for source in seen.values() if str(source.event_id) == cause_id
            )
            if (
                current.status not in {"open", "improving"}
                or _event_time(event) - datetime.fromisoformat(inactivity_source)
                < timedelta(days=30)
                or event.causation_id != expected_cause
            ):
                raise ValueError("Only an inactive open repair can become dormant")
            repairs[repair_id] = replace(current, status="dormant")
        seen[str(event.event_id)] = event
    return repairs


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _event_time(event: DomainEvent) -> datetime:
    value = _required(event, "simulated_at")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Relationship repair evidence must be timezone-aware")
    return parsed
