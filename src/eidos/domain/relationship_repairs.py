"""Replayable repair arcs that never infer another person's forgiveness."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping, NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import GrowOnlyMap, IncrementalFold, PersistentMap
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


class _RepairFold(NamedTuple):
    repairs: Mapping[str, RelationshipRepair]
    seen: PersistentMap[str, DomainEvent]
    used_contacts: GrowOnlyMap[str, bool]


_REPAIR_KINDS = frozenset(
    {
        "relationship.repair_opened",
        "relationship.repair_contacted",
        "relationship.repair_became_dormant",
    }
)


def _repair_step(fold: _RepairFold, event: DomainEvent) -> _RepairFold:
    seen = fold.seen
    if event.kind not in _REPAIR_KINDS:
        return fold._replace(seen=seen.with_item(str(event.event_id), event))
    # Repair events are rare; copying the small repair map keeps earlier states immutable.
    repairs = dict(fold.repairs)
    used_contacts = fold.used_contacts
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
        used_contacts = used_contacts.with_item(source_id, True)
    elif event.kind == "relationship.repair_became_dormant":
        repair_id = _required(event, "repair_id")
        person_id = _required(event, "person_id")
        current = repairs.get(repair_id)
        if current is None or person_id != current.person_id:
            raise ValueError("Unknown relationship repair")
        inactivity_source = current.last_contact_at or current.opened_at
        cause_id = current.last_contact_source_id or current.apology_event_id
        # Every value is held under its own id, so the former scan of ``seen.values()``
        # for this id found exactly ``seen[cause_id]``, and stopped iteration without it.
        cause = seen.get(cause_id)
        if cause is None:
            raise StopIteration
        expected_cause = cause.event_id
        if (
            current.status not in {"open", "improving"}
            or _event_time(event) - datetime.fromisoformat(inactivity_source) < timedelta(days=30)
            or event.causation_id != expected_cause
        ):
            raise ValueError("Only an inactive open repair can become dormant")
        repairs[repair_id] = replace(current, status="dormant")
    return _RepairFold(
        MappingProxyType(repairs), seen.with_item(str(event.event_id), event), used_contacts
    )


_REPAIR_FOLD: IncrementalFold[_RepairFold] = IncrementalFold(
    lambda: _RepairFold(MappingProxyType({}), PersistentMap(), GrowOnlyMap()), _repair_step
)


def project_relationship_repairs(
    history: Sequence[DomainEvent],
) -> dict[str, RelationshipRepair]:
    # A fresh dict each call: callers own the returned mapping, the fold state is shared.
    return dict(_REPAIR_FOLD(history).repairs)


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
