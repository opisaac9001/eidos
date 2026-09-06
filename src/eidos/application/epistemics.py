"""Views limited to evidence Pathos has actually encountered."""

from __future__ import annotations

from typing import Sequence

from eidos.domain.events import DomainEvent


def pathos_known_person_ids(history: Sequence[DomainEvent]) -> frozenset[str]:
    """Return people supported by Pathos-owned encounter or memory evidence."""
    known: set[str] = set()
    for event in history:
        owner = event.payload.get("owner", "pathos")
        if owner not in {"pathos", "user"}:
            continue
        person_id = event.payload.get("person_id")
        if not isinstance(person_id, str) or not person_id:
            continue
        if event.kind == "npc.encountered" or event.kind == "memory.recorded":
            known.add(person_id)
    return frozenset(known)
