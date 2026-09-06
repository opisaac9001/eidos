"""Bounded deterministic appraisal connecting experiences to durable needs."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


def baseline_affect_events(
    state: PathosState, simulated_at: datetime
) -> tuple[list[DomainEvent], PathosState]:
    """Move transient affect gently toward baseline without erasing its causes."""
    valence_step = 0.025 if not state.awake else 0.015
    arousal_step = 0.035 if not state.awake else 0.02
    valence = _toward(state.valence, 0.0, valence_step)
    arousal = _toward(state.arousal, 0.35, arousal_step)
    if valence == state.valence and arousal == state.arousal:
        return [], state
    event = DomainEvent(
        "affect.changed",
        "pathos",
        {
            "valence": valence,
            "arousal": arousal,
            "reason": "sleep recovery" if not state.awake else "baseline recovery",
            "simulated_at": simulated_at.isoformat(),
        },
    )
    return [event], state.apply(event)


def affect_episode_events(
    history: Sequence[DomainEvent], state: PathosState, simulated_at: datetime
) -> tuple[list[DomainEvent], PathosState]:
    """Translate each new appraisal into one bounded, source-linked affect episode."""
    processed = {
        str(event.payload["appraisal_id"])
        for event in history
        if event.kind == "affect.episode_started"
    }
    output: list[DomainEvent] = []
    current = state
    for appraisal in history:
        appraisal_id = str(appraisal.event_id)
        if appraisal.kind != "appraisal.recorded" or appraisal_id in processed:
            continue
        desirability = float(appraisal.payload["desirability"])
        novelty = float(appraisal.payload["novelty"])
        already_applied = appraisal.payload.get("need") == "affect"
        valence_delta = 0.0 if already_applied else max(-0.08, min(0.08, desirability * 0.06))
        arousal_delta = max(-0.04, min(0.06, (novelty - 0.25) * 0.08))
        episode = DomainEvent(
            "affect.episode_started",
            "pathos",
            {
                "appraisal_id": appraisal_id,
                "source_event_id": str(appraisal.payload["source_event_id"]),
                "source_kind": str(appraisal.payload["source_kind"]),
                "valence_delta": valence_delta,
                "arousal_delta": arousal_delta,
                "already_applied": already_applied,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=appraisal.event_id,
            correlation_id=appraisal.correlation_id,
        )
        changed = DomainEvent(
            "affect.changed",
            "pathos",
            {
                "valence": max(-1.0, min(1.0, current.valence + valence_delta)),
                "arousal": max(0.0, min(1.0, current.arousal + arousal_delta)),
                "reason": "bounded appraisal episode",
                "appraisal_id": appraisal_id,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=episode.event_id,
            correlation_id=appraisal.correlation_id,
        )
        output.extend((episode, changed))
        processed.add(appraisal_id)
        current = current.apply(changed)
    return output, current


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
    if event.kind == "activity.completed":
        if event.payload.get("activity") == "attend":
            return ("connection", 0.05, 0.45, 0.3, 0.75)
        if event.payload.get("activity") in {"learn", "work"}:
            return ("mastery", 0.06, 0.6, 0.3, 0.85)
    if event.kind == "schedule.interrupted":
        return ("mastery", -0.04, -0.35, 0.5, 0.4)
    if event.kind == "action.accepted" and event.payload.get("action") == "repair":
        return ("mastery", 0.08, 0.7, 0.35, 0.9)
    if event.kind == "commitment.missed":
        return ("connection", -0.08, -0.75, 0.3, 0.65)
    if event.kind == "dream.effect_applied":
        return ("affect", 0.0, float(event.payload.get("valence_delta", 0)), 0.65, 0.15)
    return None


def _toward(value: float, target: float, step: float) -> float:
    if value < target:
        return min(target, value + step)
    if value > target:
        return max(target, value - step)
    return value
