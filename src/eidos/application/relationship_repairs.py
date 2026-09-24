"""Let repair attempts evolve only through later contact and elapsed time."""

from __future__ import annotations

from datetime import datetime, timedelta
from itertools import chain
from typing import Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.domain.folding import event_index, events_of, kind_index
from eidos.domain.relationship_dates import INTERACTION_KINDS, interaction_person
from eidos.domain.relationship_repairs import project_relationship_repairs


def relationship_repair_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    if simulated_at.utcoffset() is None:
        raise ValueError("Relationship repair review must be timezone-aware")
    output: list[DomainEvent] = []
    state = project_relationship_repairs(history)
    apology_ids = {item.apology_event_id for item in state.values()}
    kinds = kind_index(history)
    for index, apology in kinds.positioned("apology.offered"):
        if apology.payload.get("actor_id") != "pathos" or str(apology.event_id) in apology_ids:
            continue
        person_id = apology.payload.get("target_id")
        topic_id = apology.payload.get("topic_id")
        if not isinstance(person_id, str) or not isinstance(topic_id, str):
            continue
        rupture = next(
            (
                event
                for position, event in reversed(kinds.positioned("disagreement.expressed"))
                if position < index
                and event.payload.get("actor_id") == apology.payload.get("actor_id")
                and event.payload.get("target_id") == person_id
                and event.payload.get("topic_id") == topic_id
            ),
            None,
        )
        try:
            apology_time = _event_time(apology)
        except (TypeError, ValueError):
            continue
        if rupture is None or apology_time > simulated_at:
            continue
        repair_id = f"repair-{apology.event_id}"
        output.append(
            DomainEvent(
                "relationship.repair_opened",
                "pathos",
                {
                    "repair_id": repair_id,
                    "person_id": person_id,
                    "rupture_event_id": str(rupture.event_id),
                    "apology_event_id": str(apology.event_id),
                    "topic_id": topic_id,
                    "text": (
                        f"Pathos's apology to {person_id} opened a repair attempt; "
                        "their response remains unknown."
                    ),
                    "simulated_at": max(simulated_at, apology_time).isoformat(),
                },
                causation_id=apology.event_id,
                correlation_id=repair_id,
            )
        )
        apology_ids.add(str(apology.event_id))
        state = project_relationship_repairs([*history, *output])
    used_contacts = {
        str(event.payload["source_event_id"])
        for event in chain(events_of(history, "relationship.repair_contacted"), output)
        if event.kind == "relationship.repair_contacted"
    }
    for repair in state.values():
        if repair.contact_count >= 3:
            continue
        # Event ids are unique in a stream, so the indexed event is the first with that id.
        apology_event = event_index(history).get(repair.apology_event_id)
        apology_time = _event_time(
            apology_event
            if apology_event is not None
            else next(event for event in history if str(event.event_id) == repair.apology_event_id)
        )
        # interaction_person is None for every other kind.
        for source in events_of(history, *INTERACTION_KINDS):
            source_id = str(source.event_id)
            if source_id in used_contacts or interaction_person(source) != repair.person_id:
                continue
            try:
                source_time = _event_time(source)
            except (TypeError, ValueError):
                continue
            if source_time <= apology_time or source_time > simulated_at:
                continue
            contact_number = repair.contact_count + 1
            contacted = DomainEvent(
                "relationship.repair_contacted",
                "pathos",
                {
                    "repair_id": repair.repair_id,
                    "person_id": repair.person_id,
                    "source_event_id": source_id,
                    "contact_number": contact_number,
                    "text": (
                        f"Pathos and {repair.person_id} had contact after the apology. "
                        "Continued contact is not proof of forgiveness."
                    ),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=source.event_id,
                correlation_id=repair.repair_id,
            )
            relationship_change = DomainEvent(
                "relationship.changed",
                "pathos",
                {
                    "person_id": repair.person_id,
                    "evidence_actor_id": repair.person_id,
                    "trust_delta": 0.0,
                    "familiarity_delta": 0.005,
                    "tension_delta": -0.01,
                    "reason": (
                        "Later direct contact gently softened Pathos's tension; "
                        "it does not establish the other person's forgiveness."
                    ),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=contacted.event_id,
                correlation_id=repair.repair_id,
            )
            output.extend((contacted, relationship_change))
            used_contacts.add(source_id)
            state = project_relationship_repairs([*history, *output])
            repair = state[repair.repair_id]
            if repair.contact_count >= 3:
                break
    if simulated_at.hour != 8:
        return output
    state = project_relationship_repairs([*history, *output])
    for repair in state.values():
        last_activity = datetime.fromisoformat(repair.last_contact_at or repair.opened_at)
        if repair.status not in {"open", "improving"} or simulated_at - last_activity < timedelta(
            days=30
        ):
            continue
        source_id = (
            next(
                str(event.payload["source_event_id"])
                for event in chain(
                    reversed(output), reversed(events_of(history, "relationship.repair_contacted"))
                )
                if event.kind == "relationship.repair_contacted"
                and event.payload.get("repair_id") == repair.repair_id
            )
            if repair.contact_count
            else repair.apology_event_id
        )
        output.append(
            DomainEvent(
                "relationship.repair_became_dormant",
                "pathos",
                {
                    "repair_id": repair.repair_id,
                    "person_id": repair.person_id,
                    "text": (
                        "The repair attempt became dormant without enough new contact; "
                        "nothing says the rupture was forgiven."
                    ),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=UUID(source_id),
                correlation_id=repair.repair_id,
            )
        )
    return output


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Relationship repair evidence requires simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Relationship repair evidence must be timezone-aware")
    return parsed
