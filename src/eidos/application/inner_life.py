"""Deterministic concern and dream-effect projections around generated fiction."""

from __future__ import annotations

from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


def active_concerns(events: list[DomainEvent]) -> list[DomainEvent]:
    concerns = {}
    for event in events:
        if event.kind == "concern.opened":
            concerns[event.payload["concern_id"]] = event
        elif event.kind == "concern.resolved":
            concerns.pop(event.payload["concern_id"], None)
    return list(concerns.values())


def waking_dream_events(
    events: list[DomainEvent], state: PathosState, simulated_at: str
) -> list[DomainEvent]:
    applied = {
        event.payload["source_dream_id"] for event in events if event.kind == "dream.effect_applied"
    }
    pending_effects = [
        event
        for event in events
        if event.kind == "dream.effect_scheduled"
        and event.payload["source_dream_id"] not in applied
    ]
    if not pending_effects:
        return []
    effect = pending_effects[-1]
    dream_id = effect.payload["source_dream_id"]
    dream = next(
        event
        for event in events
        if event.kind == "dream.recorded" and str(event.event_id) == dream_id
    )
    delta = max(-0.12, min(0.12, float(effect.payload["valence_delta"])))
    return [
        DomainEvent(
            "dream.recalled",
            "pathos",
            {
                "text": "A dream lingered after waking.",
                "simulated_at": simulated_at,
                "source_dream_id": dream_id,
            },
        ),
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"I remember dreaming: {dream.payload['text']}",
                "simulated_at": simulated_at,
                "source": "dream-recall",
                "source_event_id": dream_id,
                "category": "dream",
                "location_id": state.location_id,
                "owner": "pathos",
                "importance": 0.6,
                "confidence": 1.0,
            },
        ),
        DomainEvent(
            "affect.changed",
            "pathos",
            {
                "valence": max(-1.0, min(1.0, state.valence + delta)),
                "simulated_at": simulated_at,
                "source_dream_id": dream_id,
                "reason": "bounded waking dream residue",
            },
        ),
        DomainEvent(
            "dream.effect_applied",
            "pathos",
            {
                "source_dream_id": dream_id,
                "simulated_at": simulated_at,
                "valence_delta": delta,
            },
        ),
    ]
