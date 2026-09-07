"""Let real co-presence turn an introduced-object project into shared activity."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.epistemics import pathos_person_introduction_event
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.relationships import Relationship


def object_collaboration_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    *,
    npc_people: Mapping[str, NPCState],
    relationships: Mapping[str, Relationship],
) -> list[DomainEvent]:
    """Let one co-present neighbor independently join or decline a new-object session."""
    handled_objects = {
        str(event.payload["object_id"])
        for event in history
        if event.kind == "object.collaboration_decided"
    }
    used = next(
        (
            event
            for event in reversed(history)
            if event.kind == "object.used"
            and str(event.payload.get("schedule_id", "")).startswith("use-introduced-")
            and event.payload.get("simulated_at") == simulated_at.isoformat()
            and str(event.payload.get("object_id")) not in handled_objects
        ),
        None,
    )
    if used is None:
        return []
    object_id = str(used.payload["object_id"])
    location_id = str(used.payload["location_id"])
    candidates = [person for person in npc_people.values() if person.location_id == location_id]
    if not candidates:
        return []

    def capacity(person: NPCState) -> float:
        familiarity = relationships.get(person.actor_id, Relationship(person.actor_id)).familiarity
        return max(
            0.05,
            min(
                0.95,
                0.45 * person.energy
                + 0.3 * person.purpose
                + 0.15 * person.connection
                + 0.1 * familiarity,
            ),
        )

    person = max(candidates, key=lambda item: (capacity(item), item.actor_id))
    score = capacity(person)
    sample = _sample(f"object-collaboration-{object_id}-{person.actor_id}")
    joins = sample < score
    correlation = f"object-collaboration-{object_id}"
    decision = DomainEvent(
        "object.collaboration_decided",
        "pathos",
        {
            "object_id": object_id,
            "person_id": person.actor_id,
            "source_object_use_id": str(used.event_id),
            "decision": "join" if joins else "decline",
            "decision_score": score,
            "decision_sample": sample,
            "reason": (
                "The neighbor had the capacity and interest to join the practical activity."
                if joins
                else "The neighbor was present but chose not to join the activity."
            ),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=used.event_id,
        correlation_id=correlation,
    )
    introduction = pathos_person_introduction_event(
        history,
        person_id=person.actor_id,
        source_event=decision,
        simulated_at=simulated_at,
        location_id=location_id,
        manner="shared_practical_activity" if joins else "brief_practical_exchange",
    )
    prefix = [decision, *([introduction] if introduction is not None else [])]
    if not joins:
        return prefix
    shared = DomainEvent(
        "object.shared_use",
        "pathos",
        {
            "object_id": object_id,
            "person_id": person.actor_id,
            "source_object_use_id": str(used.event_id),
            "location_id": location_id,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=decision.event_id,
        correlation_id=correlation,
    )
    relationship = DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": person.actor_id,
            "evidence_actor_id": "pathos",
            "familiarity_delta": 0.03,
            "trust_delta": 0.01,
            "reason": "They chose to spend practical time using a shared object together.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=shared.event_id,
        correlation_id=correlation,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": (
                f"{person.actor_id.replace('-', ' ').title()} joined me while I used "
                "a newly discovered shared object."
            ),
            "owner": "pathos",
            "category": "shared-activity",
            "source": "deterministic-consequence",
            "source_event_id": str(shared.event_id),
            "object_id": object_id,
            "person_id": person.actor_id,
            "location_id": location_id,
            "importance": 0.7,
            "confidence": 1.0,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=shared.event_id,
        correlation_id=correlation,
    )
    return [*prefix, shared, relationship, memory]


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
