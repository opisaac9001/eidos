"""Deterministic concern and dream-effect projections around generated fiction."""

from __future__ import annotations

from typing import Sequence

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


def dream_seed_sources(
    recalled_memories: Sequence[DomainEvent], concerns: Sequence[DomainEvent], limit: int = 3
) -> tuple[DomainEvent, ...]:
    """Choose bounded owned waking evidence; dream memories cannot seed themselves."""
    if not 1 <= limit <= 5:
        raise ValueError("Dream seed limit must be between one and five")
    eligible = [
        event
        for event in concerns
        if event.kind == "concern.opened" and isinstance(event.payload.get("concern_id"), str)
    ]
    eligible.extend(
        event
        for event in recalled_memories
        if event.kind == "memory.recorded"
        and event.payload.get("owner", "pathos") == "pathos"
        and event.payload.get("category") != "dream"
    )
    selected = []
    seen = set()
    for event in eligible:
        identity = str(event.event_id)
        if identity in seen:
            continue
        selected.append(event)
        seen.add(identity)
        if len(selected) == limit:
            break
    return tuple(selected)


def record_dream_events(
    text: str,
    seeds: Sequence[DomainEvent],
    simulated_at: str,
    source: str,
) -> list[DomainEvent]:
    """Record dream fiction plus one auditable link for every accepted seed."""
    if not text.strip():
        raise ValueError("Dream text must not be empty")
    accepted = dream_seed_sources(
        [seed for seed in seeds if seed.kind == "memory.recorded"],
        [seed for seed in seeds if seed.kind == "concern.opened"],
        limit=min(5, max(1, len(seeds))),
    )
    motif = _motif(accepted)
    dream = DomainEvent(
        "dream.recorded",
        "pathos",
        {
            "text": text.strip(),
            "simulated_at": simulated_at,
            "source": source,
            "role": "oneiros",
            "seed_count": len(accepted),
            "primary_seed_id": str(accepted[0].event_id) if accepted else None,
            "motif": motif,
            "fiction": True,
        },
        correlation_id=f"dream-{simulated_at}",
    )
    events = [dream]
    for position, seed in enumerate(accepted, 1):
        events.append(
            DomainEvent(
                "dream.seed_linked",
                "pathos",
                {
                    "dream_id": str(dream.event_id),
                    "seed_event_id": str(seed.event_id),
                    "seed_kind": "concern" if seed.kind == "concern.opened" else "memory",
                    "position": position,
                    "motif": motif,
                    "simulated_at": simulated_at,
                },
                causation_id=seed.event_id,
                correlation_id=dream.correlation_id,
            )
        )
    return events


def _motif(seeds: Sequence[DomainEvent]) -> str:
    text = " ".join(str(seed.payload.get("text", "")).lower() for seed in seeds)
    for motif, cues in (
        ("light", ("lamp", "light", "moon")),
        ("mending", ("repair", "broken", "workshop", "finish")),
        ("growth", ("park", "tree", "garden")),
        ("companionship", ("mara", "ellis", "rowan", "cafe", "together")),
    ):
        if any(cue in text for cue in cues):
            return motif
    return "unfinished_time"


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
