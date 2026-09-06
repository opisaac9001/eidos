"""Propose tiny trait shifts from month-spanning behavioral evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.traits import DEFAULT_TRAITS, MAX_DRIFT, project_traits, trait_evidence

EVIDENCE_SPAN = timedelta(days=30)
CHANGE_COOLDOWN = timedelta(days=30)
DELTA = 0.01


def trait_development_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    if simulated_at.utcoffset() is None:
        raise ValueError("Trait review time must be timezone-aware")
    if simulated_at.hour != 20:
        return []
    changes = [event for event in history if event.kind == "trait.adjusted"]
    if changes and simulated_at - _event_time(changes[-1]) < CHANGE_COOLDOWN:
        return []
    last_by_trait = {
        str(event.payload["trait_id"]): _event_time(event)
        for event in changes
        if isinstance(event.payload.get("trait_id"), str)
    }
    evidence: dict[tuple[str, int], list[DomainEvent]] = defaultdict(list)
    for event in history:
        for trait_id, direction in trait_evidence(event):
            if _event_time(event) > last_by_trait.get(
                trait_id, datetime.min.replace(tzinfo=simulated_at.tzinfo)
            ):
                evidence[(trait_id, direction)].append(event)
    candidates: list[tuple[int, str, int, list[DomainEvent]]] = []
    for (trait_id, direction), sources in evidence.items():
        if len(sources) < 5 or _event_time(sources[-1]) - _event_time(sources[0]) < EVIDENCE_SPAN:
            continue
        candidates.append((len(sources), trait_id, direction, sources))
    if not candidates:
        return []
    _, trait_id, direction, sources = max(candidates, key=lambda item: (item[0], item[1]))
    state = project_traits(history)
    prior = state.levels[trait_id]
    next_level = max(
        DEFAULT_TRAITS[trait_id] - MAX_DRIFT,
        min(DEFAULT_TRAITS[trait_id] + MAX_DRIFT, prior + direction * DELTA),
    )
    if next_level == prior:
        return []
    selected = sources if len(sources) <= 5 else [sources[0], *sources[-4:]]
    return [
        DomainEvent(
            "trait.adjusted",
            "pathos",
            {
                "trait_id": trait_id,
                "direction": direction,
                "delta": DELTA,
                "prior": prior,
                "next": next_level,
                **{
                    f"source_event_{position}": str(source.event_id)
                    for position, source in enumerate(selected, 1)
                },
                "evidence_count": len(sources),
                "simulated_at": simulated_at.isoformat(),
                "owner": "pathos",
            },
            causation_id=selected[-1].event_id,
            correlation_id=f"trait-{trait_id}",
        )
    ]


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Trait evidence needs simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Trait evidence time must be timezone-aware")
    return parsed
