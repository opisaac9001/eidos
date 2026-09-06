"""Bounded deterministic appraisal connecting experiences to durable needs."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


def sleep_and_need_events(
    state: PathosState, simulated_at: datetime
) -> tuple[list[DomainEvent], PathosState]:
    """Apply circadian state and modest pressure/recovery for one simulated hour."""
    events: list[DomainEvent] = []
    current = state
    should_be_awake = 7 <= simulated_at.hour < 23
    if should_be_awake != current.awake:
        transition = DomainEvent(
            "sleep.ended" if should_be_awake else "sleep.started",
            "pathos",
            {
                "simulated_at": simulated_at.isoformat(),
                "reason": "circadian boundary",
            },
        )
        events.append(transition)
        current = current.apply(transition)
    deltas = (
        {"rest": -0.03, "connection": -0.012, "curiosity": -0.003, "mastery": -0.006}
        if current.awake
        else {"rest": 0.04, "connection": -0.004, "curiosity": -0.001, "mastery": -0.002}
    )
    payload = {
        name: max(0.0, min(1.0, float(getattr(current, name)) + delta))
        for name, delta in deltas.items()
    }
    drift = DomainEvent(
        "needs.changed",
        "pathos",
        {
            **payload,
            "reason": "sleep recovery" if not current.awake else "hourly need pressure",
            "simulated_at": simulated_at.isoformat(),
        },
    )
    events.append(drift)
    current = current.apply(drift)
    return events, current


def appraisal_events(
    history: Sequence[DomainEvent], state: PathosState, simulated_at: datetime
) -> tuple[list[DomainEvent], PathosState]:
    """Appraise each eligible source once and return updated projected state."""
    appraised = {
        str(event.payload["source_event_id"])
        for event in history
        if event.kind == "appraisal.recorded"
    }
    output: list[DomainEvent] = []
    current = state
    for source in history:
        source_id = str(source.event_id)
        if source_id in appraised:
            continue
        effect = _effect(source)
        if effect is None:
            continue
        need, delta, desirability, novelty, controllability = effect
        appraisal = DomainEvent(
            "appraisal.recorded",
            "pathos",
            {
                "source_event_id": source_id,
                "source_kind": source.kind,
                "need": need,
                "need_delta": delta,
                "desirability": desirability,
                "novelty": novelty,
                "controllability": controllability,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=source.event_id,
            correlation_id=source.correlation_id,
        )
        output.append(appraisal)
        appraised.add(source_id)
        if need != "affect":
            value = max(0.0, min(1.0, float(getattr(current, need)) + delta))
            changed = DomainEvent(
                "needs.changed",
                "pathos",
                {
                    need: value,
                    "reason": f"appraisal of {source.kind}",
                    "source_event_id": source_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=appraisal.event_id,
                correlation_id=source.correlation_id,
            )
            output.append(changed)
            current = current.apply(changed)
    return output, current


def _effect(event: DomainEvent) -> tuple[str, float, float, float, float] | None:
    if event.kind == "memory.recorded" and event.payload.get("source") == "authored-routine":
        location = event.payload.get("location_id")
        if not isinstance(location, str):
            return None
        return {
            "home": ("rest", 0.05, 0.35, 0.1, 0.8),
            "cafe": ("connection", 0.04, 0.3, 0.25, 0.7),
            "park": ("curiosity", 0.05, 0.35, 0.35, 0.8),
            "workshop": ("mastery", 0.04, 0.4, 0.25, 0.85),
        }.get(location)
    if event.kind == "npc.encountered":
        return ("connection", 0.05, 0.4, 0.45, 0.6)
    if event.kind == "social.activity_completed":
        return ("connection", 0.06, 0.55, 0.35, 0.8)
    if event.kind == "schedule.interrupted":
        return ("mastery", -0.04, -0.35, 0.5, 0.4)
    if event.kind == "action.accepted" and event.payload.get("action") == "repair":
        return ("mastery", 0.08, 0.7, 0.35, 0.9)
    if event.kind == "commitment.missed":
        return ("connection", -0.08, -0.75, 0.3, 0.65)
    if event.kind == "dream.effect_applied":
        return ("affect", 0.0, float(event.payload.get("valence_delta", 0)), 0.65, 0.15)
    return None
