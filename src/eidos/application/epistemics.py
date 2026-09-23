"""Views limited to evidence Pathos has actually encountered."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold

_KNOWING_KINDS = frozenset({"npc.encountered", "memory.recorded", "person.introduced_to_pathos"})


def _known_step(known: frozenset[str], event: DomainEvent) -> frozenset[str]:
    owner = event.payload.get("owner", "pathos")
    if owner not in {"pathos", "user"}:
        return known
    person_id = event.payload.get("person_id")
    if not isinstance(person_id, str) or not person_id:
        return known
    if event.kind in _KNOWING_KINDS and person_id not in known:
        return known | {person_id}
    return known


_KNOWN_FOLD: IncrementalFold[frozenset[str]] = IncrementalFold(frozenset, _known_step)


def pathos_known_person_ids(history: Sequence[DomainEvent]) -> frozenset[str]:
    """Return people supported by Pathos-owned encounter or memory evidence."""
    return _KNOWN_FOLD(history)


def pathos_person_introduction_event(
    history: Sequence[DomainEvent],
    *,
    person_id: str,
    source_event: DomainEvent,
    simulated_at: datetime,
    location_id: str,
    manner: str,
) -> DomainEvent | None:
    """Record the first sourced moment at which Pathos learns who a resident is."""
    if person_id in pathos_known_person_ids(history):
        return None
    return DomainEvent(
        "person.introduced_to_pathos",
        "pathos",
        {
            "person_id": person_id,
            "owner": "pathos",
            "source_event_id": str(source_event.event_id),
            "location_id": location_id,
            "manner": manner,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=source_event.event_id,
        correlation_id=source_event.correlation_id,
    )
